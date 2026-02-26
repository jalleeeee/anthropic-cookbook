"""
ROM (Rough Order of Magnitude) Estimator

Generates a preliminary construction estimate in seconds using:
1. The Deductive Engine — derives ALL quantities from seed values (SF, stories, etc.)
2. The Live Catalog — looks up real-time pricing from DDC-CWICR database
3. AIA G703 Schedule of Values — organizes per-building, per-CSI division

A ROM estimate is the FIRST estimate produced — before any detailed takeoff.
Industry standard accuracy: +/- 25% (AACE Class 5).

The workflow:
  Customer provides: building SF, stories, unit count, construction type
  ROM produces: full envelope estimate with labor, material, equipment breakdown
  Time: < 5 seconds (no PDF upload required)

This bridges the gap between "I need a quick number" and the full AI takeoff.
The detailed takeoff (pdf_takeoff.py) then refines these numbers.

Per AIA G703:
  - Every line item has a CSI MasterFormat code
  - Split per building for commercial multifamily
  - Material / Labor / Equipment breakdown on each line
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import Settings
from modules.deductive_engine import (
    DeductiveEngine,
    SeedValues,
    DerivedQuantities,
    BuildingScheduleOfValues,
)
from modules.live_catalog import LiveCatalog, SOV_TO_CATALOG_MAP

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ROM data structures
# ---------------------------------------------------------------------------

@dataclass
class ROMLineItem:
    """A single line in the ROM estimate."""
    item_number: str
    description: str
    csi_division: str
    quantity: float
    unit: str
    # Pricing
    unit_price: float = 0.0
    material_cost: float = 0.0
    labor_cost: float = 0.0
    equipment_cost: float = 0.0
    extended_price: float = 0.0
    # Metadata
    pricing_source: str = ""
    confidence: str = "ROM"    # ROM, budget, definitive


@dataclass
class ROMBuildingEstimate:
    """ROM estimate for one building."""
    building_id: str
    seeds: Optional[SeedValues] = None
    derived: Optional[DerivedQuantities] = None
    line_items: list[ROMLineItem] = field(default_factory=list)
    # Totals
    total_material: float = 0.0
    total_labor: float = 0.0
    total_equipment: float = 0.0
    subtotal_direct: float = 0.0
    overhead: float = 0.0
    profit: float = 0.0
    bond: float = 0.0
    tax: float = 0.0
    grand_total: float = 0.0
    cost_per_sf: float = 0.0
    cost_per_unit: float = 0.0
    # Math trace
    derivation_log: list[str] = field(default_factory=list)


@dataclass
class ROMEstimate:
    """Complete ROM estimate for a project (may have multiple buildings)."""
    project_name: str
    buildings: list[ROMBuildingEstimate] = field(default_factory=list)
    # Project totals
    total_buildings: int = 0
    total_units: int = 0
    total_sf: float = 0.0
    project_total_material: float = 0.0
    project_total_labor: float = 0.0
    project_total_equipment: float = 0.0
    project_grand_total: float = 0.0
    project_cost_per_sf: float = 0.0
    project_cost_per_unit: float = 0.0
    # Confidence
    accuracy_range: str = "+/- 25%"
    aace_class: str = "Class 5 — ROM"
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The ROM Estimator
# ---------------------------------------------------------------------------

class ROMEstimator:
    """Generates ROM estimates by combining DeductiveEngine + LiveCatalog.

    This is the quick-estimate path:
    1. User provides minimal inputs (SF, stories, units, type)
    2. DeductiveEngine derives all quantities via math
    3. LiveCatalog prices each line item from DDC-CWICR
    4. Result: full priced SOV per building in < 5 seconds

    Usage:
        rom = ROMEstimator(settings)
        estimate = rom.estimate(
            project_name="Parkview Apartments",
            buildings=[
                {"building_id": "Bldg A", "footprint_sf": 12000,
                 "stories_above_grade": 4, "unit_count": 48},
                {"building_id": "Bldg B", "footprint_sf": 10000,
                 "stories_above_grade": 3, "unit_count": 36},
            ]
        )
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = DeductiveEngine()
        self.catalog = LiveCatalog(settings)

    def estimate(
        self,
        project_name: str,
        buildings: list[dict],
        overhead_pct: Optional[float] = None,
        profit_pct: Optional[float] = None,
    ) -> ROMEstimate:
        """Generate a ROM estimate for a project.

        Args:
            project_name: Project name/identifier
            buildings: List of dicts with seed values per building.
                Required keys: footprint_sf, stories_above_grade
                Optional: unit_count, perimeter_lf, floor_to_floor_ft,
                          primary_cladding, roof_pitch, building_shape, etc.
            overhead_pct: Override company overhead (default from settings)
            profit_pct: Override company profit (default from settings)

        Returns:
            ROMEstimate with full pricing breakdown
        """
        company = self.settings.company
        oh_pct = overhead_pct if overhead_pct is not None else company.overhead_percent
        pr_pct = profit_pct if profit_pct is not None else company.profit_percent

        rom = ROMEstimate(project_name=project_name)

        for bldg_input in buildings:
            # Build seed values
            seeds = SeedValues(
                building_id=bldg_input.get("building_id", "Building A"),
                footprint_sf=float(bldg_input.get("footprint_sf", 0)),
                stories_above_grade=int(bldg_input.get("stories_above_grade", 0)),
                stories_below_grade=int(bldg_input.get("stories_below_grade", 0)),
                footprint_length_ft=float(bldg_input.get("footprint_length_ft", 0)),
                footprint_width_ft=float(bldg_input.get("footprint_width_ft", 0)),
                perimeter_lf=float(bldg_input.get("perimeter_lf", 0)),
                floor_to_floor_ft=float(bldg_input.get("floor_to_floor_ft", 0)),
                total_building_height_ft=float(
                    bldg_input.get("total_building_height_ft", 0)
                ),
                parapet_height_ft=float(bldg_input.get("parapet_height_ft", 0)),
                unit_count=int(bldg_input.get("unit_count", 0)),
                unit_mix=bldg_input.get("unit_mix", {}),
                roof_pitch=bldg_input.get("roof_pitch", "flat"),
                roof_type=bldg_input.get("roof_type", "TPO membrane"),
                building_shape=bldg_input.get(
                    "building_shape", "typical_multifamily"
                ),
                construction_type=bldg_input.get("construction_type", "V-A"),
                has_podium=bldg_input.get("has_podium", False),
                podium_height_ft=float(bldg_input.get("podium_height_ft", 0)),
                primary_cladding=bldg_input.get(
                    "primary_cladding", "fiber_cement_lap"
                ),
                secondary_cladding=bldg_input.get("secondary_cladding", ""),
                secondary_cladding_floors=bldg_input.get(
                    "secondary_cladding_floors", ""
                ),
                corridor_type=bldg_input.get("corridor_type", "interior"),
                balcony_count=int(bldg_input.get("balcony_count", 0)),
                avg_balcony_sf=float(bldg_input.get("avg_balcony_sf", 60)),
                window_count_from_schedule=int(
                    bldg_input.get("window_count_from_schedule", 0)
                ),
                door_count_from_schedule=int(
                    bldg_input.get("door_count_from_schedule", 0)
                ),
            )

            # Step 1: Derive all quantities
            derived = self.engine.derive(seeds)

            # Step 2: Generate base SOV (with default prices)
            sov = self.engine.generate_schedule_of_values(seeds, derived)

            # Step 3: Re-price SOV using live catalog
            sov_dicts = [
                {
                    "item": i.item_number,
                    "description": i.description,
                    "csi": i.csi_division,
                    "qty": i.quantity,
                    "unit": i.unit,
                    "unit_price": i.unit_price,
                    "value": i.scheduled_value,
                }
                for i in sov.items
            ]
            priced_items = self.catalog.price_schedule_of_values(sov_dicts)

            # Step 4: Build ROM line items
            bldg_estimate = ROMBuildingEstimate(
                building_id=seeds.building_id,
                seeds=seeds,
                derived=derived,
                derivation_log=derived.derivation_log,
            )

            for pi in priced_items:
                qty = float(pi.get("qty", 0))
                up = float(pi.get("unit_price", 0))
                mat = float(pi.get("material_cost", 0))
                lab = float(pi.get("labor_cost", 0))
                extended = float(pi.get("value", 0))

                line = ROMLineItem(
                    item_number=pi.get("item", ""),
                    description=pi.get("description", ""),
                    csi_division=pi.get("csi", ""),
                    quantity=qty,
                    unit=pi.get("unit", ""),
                    unit_price=up,
                    material_cost=mat,
                    labor_cost=lab,
                    equipment_cost=extended - mat - lab,
                    extended_price=extended,
                    pricing_source=pi.get("pricing_source", ""),
                )
                bldg_estimate.line_items.append(line)

            # Step 5: Compute building totals
            bldg_estimate.total_material = sum(
                li.material_cost for li in bldg_estimate.line_items
            )
            bldg_estimate.total_labor = sum(
                li.labor_cost for li in bldg_estimate.line_items
            )
            bldg_estimate.total_equipment = sum(
                li.equipment_cost for li in bldg_estimate.line_items
            )
            bldg_estimate.subtotal_direct = sum(
                li.extended_price for li in bldg_estimate.line_items
            )

            # Markups
            bldg_estimate.overhead = round(
                bldg_estimate.subtotal_direct * oh_pct, 2
            )
            bldg_estimate.profit = round(
                (bldg_estimate.subtotal_direct + bldg_estimate.overhead) * pr_pct, 2
            )
            bldg_estimate.bond = round(
                bldg_estimate.subtotal_direct * company.bond_percent, 2
            )
            bldg_estimate.tax = round(
                bldg_estimate.total_material * company.tax_rate, 2
            )
            bldg_estimate.grand_total = round(
                bldg_estimate.subtotal_direct
                + bldg_estimate.overhead
                + bldg_estimate.profit
                + bldg_estimate.bond
                + bldg_estimate.tax,
                2,
            )

            # Per-unit metrics
            total_bldg_sf = seeds.footprint_sf * max(seeds.stories_above_grade, 1)
            if total_bldg_sf > 0:
                bldg_estimate.cost_per_sf = round(
                    bldg_estimate.grand_total / total_bldg_sf, 2
                )
            if seeds.unit_count > 0:
                bldg_estimate.cost_per_unit = round(
                    bldg_estimate.grand_total / seeds.unit_count, 2
                )

            rom.buildings.append(bldg_estimate)

        # Project totals
        rom.total_buildings = len(rom.buildings)
        rom.total_units = sum(
            b.seeds.unit_count for b in rom.buildings if b.seeds
        )
        rom.total_sf = sum(
            b.seeds.footprint_sf * max(b.seeds.stories_above_grade, 1)
            for b in rom.buildings if b.seeds
        )
        rom.project_total_material = round(
            sum(b.total_material for b in rom.buildings), 2
        )
        rom.project_total_labor = round(
            sum(b.total_labor for b in rom.buildings), 2
        )
        rom.project_total_equipment = round(
            sum(b.total_equipment for b in rom.buildings), 2
        )
        rom.project_grand_total = round(
            sum(b.grand_total for b in rom.buildings), 2
        )
        if rom.total_sf > 0:
            rom.project_cost_per_sf = round(
                rom.project_grand_total / rom.total_sf, 2
            )
        if rom.total_units > 0:
            rom.project_cost_per_unit = round(
                rom.project_grand_total / rom.total_units, 2
            )

        rom.notes = [
            "ROM (Rough Order of Magnitude) estimate — AACE Class 5",
            f"Accuracy range: {rom.accuracy_range}",
            "Quantities derived mathematically from seed values (not measured from plans)",
            "Pricing from DDC-CWICR live catalog where available, US averages otherwise",
            "Detailed takeoff from plans will refine these numbers",
        ]

        logger.info(
            f"ROM estimate complete: {rom.total_buildings} buildings, "
            f"{rom.total_units} units, "
            f"${rom.project_grand_total:,.0f} total"
        )

        return rom

    def estimate_to_dict(self, rom: ROMEstimate) -> dict:
        """Convert ROM estimate to a JSON-serializable dict."""
        return {
            "project_name": rom.project_name,
            "accuracy_range": rom.accuracy_range,
            "aace_class": rom.aace_class,
            "summary": {
                "total_buildings": rom.total_buildings,
                "total_units": rom.total_units,
                "total_sf": rom.total_sf,
                "total_material": rom.project_total_material,
                "total_labor": rom.project_total_labor,
                "total_equipment": rom.project_total_equipment,
                "grand_total": rom.project_grand_total,
                "cost_per_sf": rom.project_cost_per_sf,
                "cost_per_unit": rom.project_cost_per_unit,
            },
            "buildings": [
                {
                    "building_id": b.building_id,
                    "seeds": {
                        "footprint_sf": b.seeds.footprint_sf if b.seeds else 0,
                        "stories": b.seeds.stories_above_grade if b.seeds else 0,
                        "unit_count": b.seeds.unit_count if b.seeds else 0,
                        "perimeter_lf": b.derived.perimeter_lf if b.derived else 0,
                        "gross_wall_sf": b.derived.gross_wall_area_sf if b.derived else 0,
                        "net_wall_sf": b.derived.net_wall_area_sf if b.derived else 0,
                    },
                    "totals": {
                        "material": b.total_material,
                        "labor": b.total_labor,
                        "equipment": b.total_equipment,
                        "subtotal_direct": b.subtotal_direct,
                        "overhead": b.overhead,
                        "profit": b.profit,
                        "bond": b.bond,
                        "tax": b.tax,
                        "grand_total": b.grand_total,
                        "cost_per_sf": b.cost_per_sf,
                        "cost_per_unit": b.cost_per_unit,
                    },
                    "line_items": [
                        {
                            "item": li.item_number,
                            "description": li.description,
                            "csi": li.csi_division,
                            "qty": li.quantity,
                            "unit": li.unit,
                            "unit_price": li.unit_price,
                            "material": li.material_cost,
                            "labor": li.labor_cost,
                            "equipment": li.equipment_cost,
                            "extended": li.extended_price,
                            "source": li.pricing_source,
                        }
                        for li in b.line_items
                    ],
                    "derivation_log": b.derivation_log,
                }
                for b in rom.buildings
            ],
            "notes": rom.notes,
        }
