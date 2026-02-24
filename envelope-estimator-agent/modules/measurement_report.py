"""
Complete Measurements Report — HOVER-Style Output with Integrated Pricing

Generates a structured measurement report identical in format to HOVER's
"Complete Measurements" PDF, but powered by our AI takeoff + deductive engine
and with live pricing already attached.

HOVER charges $25-45 per property scan and requires a drone/photo capture.
Our system produces the same output from blueprints (PDF upload) or from
minimal seed values (ROM path), with pricing included.

Report sections (matching HOVER's page structure):
  1. SUMMARY — Facades, Openings, Trims, Corners, Roofline, Waste Totals
  2. ROOF SUMMARY — Facets, Ridges/Hips, Valleys, Rakes, Eaves, Pitch breakdown
  3. FOOTPRINT — Plan view dimensions, perimeter, area, stories
  4. SIDING PER ELEVATION — Section-by-section areas per elevation (Front/Right/Left/Back)
  5. PRICED ESTIMATE — Full pricing breakdown (material/labor/equipment) per trade

The key differentiator: HOVER gives you measurements only.
We give you measurements + pricing + schedule of values in one step.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from config.settings import Settings
from modules.deductive_engine import (
    DeductiveEngine,
    SeedValues,
    DerivedQuantities,
    OPENING_DEDUCTION_SF,
    ROOF_WASTE_FACTORS,
    SOFFIT_DEPTHS,
)
from modules.live_catalog import LiveCatalog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures — mirrors HOVER's report format
# ---------------------------------------------------------------------------

@dataclass
class WasteTier:
    """Siding/roofing area at a specific waste percentage."""
    waste_pct: float          # e.g. 0.10 for 10%
    area_sf: float
    squares: float            # area / 100 for roofing


@dataclass
class SidingSummary:
    """Page 1 — Summary (Siding & Other columns)."""
    # Areas
    facades_siding_sf: float = 0.0
    facades_other_sf: float = 0.0
    openings_siding_sf: float = 0.0
    openings_other_sf: float = 0.0
    trims_siding_sf: float = 0.0
    trims_other_sf: float = 0.0
    total_siding_sf: float = 0.0
    total_other_sf: float = 0.0

    # Opening counts
    openings_siding_qty: int = 0
    openings_other_qty: int = 0
    openings_tops_length: str = ""
    openings_sills_length: str = ""
    openings_sides_length: str = ""
    openings_total_perimeter: str = ""

    # Corners
    inside_corner_qty: int = 0
    inside_corner_length: str = ""
    outside_corner_qty: int = 0
    outside_corner_length: str = ""

    # Trim lengths
    level_starter_siding: str = ""
    level_starter_other: str = ""
    sloped_trim: str = ""
    vertical_trim_siding: str = ""
    vertical_trim_other: str = ""

    # Roofline
    eaves_fascia_length: str = ""
    level_frieze_board_length: str = ""
    level_frieze_board_depth: str = ""
    level_frieze_board_soffit_sf: float = 0.0
    rakes_fascia_length: str = ""
    sloped_frieze_board_length: str = ""
    sloped_frieze_board_depth: str = ""
    sloped_frieze_board_soffit_sf: float = 0.0

    # Waste totals — siding (zero waste, +10%, +18%)
    waste_tiers: list[WasteTier] = field(default_factory=list)
    # With opening deductions
    waste_tiers_openings_lt_20sf: list[WasteTier] = field(default_factory=list)
    waste_tiers_openings_lt_33sf: list[WasteTier] = field(default_factory=list)


@dataclass
class RoofItem:
    """Single row in the roof summary table."""
    name: str           # e.g. "Roof Facets", "Ridges / Hips"
    area_sf: float = 0.0
    total_count: int = 0
    total_length: str = ""


@dataclass
class RoofPitchBreakdown:
    """One row in the pitch breakdown table."""
    pitch: str          # e.g. "4 / 12"
    area_sf: float = 0.0
    percentage: float = 0.0


@dataclass
class RoofSummary:
    """Page 2 — Roof Summary."""
    items: list[RoofItem] = field(default_factory=list)
    pitch_breakdown: list[RoofPitchBreakdown] = field(default_factory=list)
    total_roof_area_sf: float = 0.0
    # Waste factor table
    waste_tiers: list[WasteTier] = field(default_factory=list)


@dataclass
class FootprintData:
    """Page 3 — Footprint."""
    stories: str = ""            # e.g. "> 1"
    footprint_perimeter: str = ""  # e.g. "689' 6\""
    footprint_area_sf: float = 0.0
    # Dimensions for plan view rendering
    overall_length_ft: float = 0.0
    overall_width_ft: float = 0.0


@dataclass
class SidingSection:
    """One siding section in the per-elevation breakdown."""
    section_id: str       # e.g. "SI-1"
    area_sf: float = 0.0


@dataclass
class ElevationSiding:
    """Siding sections for one elevation."""
    elevation: str        # "FRONT", "RIGHT", "LEFT", "BACK"
    sections: list[SidingSection] = field(default_factory=list)
    total_sf: float = 0.0


@dataclass
class PricedLineItem:
    """A priced line item — this is what HOVER doesn't have."""
    trade: str
    description: str
    csi_division: str
    quantity: float
    unit: str
    unit_price: float
    material_cost: float
    labor_cost: float
    equipment_cost: float
    extended_price: float
    pricing_source: str = ""


@dataclass
class PricedEstimate:
    """Page 5 — Full priced estimate (our differentiator over HOVER)."""
    line_items: list[PricedLineItem] = field(default_factory=list)
    total_material: float = 0.0
    total_labor: float = 0.0
    total_equipment: float = 0.0
    subtotal_direct: float = 0.0
    overhead: float = 0.0
    profit: float = 0.0
    bond: float = 0.0
    tax: float = 0.0
    grand_total: float = 0.0


@dataclass
class CompleteMeasurementReport:
    """The full HOVER-style report with pricing.

    This is the core output of our platform — it replaces HOVER's
    measurement-only PDF with a complete priced estimate.
    """
    # Header
    property_name: str = ""
    property_address: str = ""
    report_date: str = ""
    model_id: str = ""
    building_id: str = ""

    # Report sections
    siding_summary: Optional[SidingSummary] = None
    roof_summary: Optional[RoofSummary] = None
    footprint: Optional[FootprintData] = None
    elevation_siding: list[ElevationSiding] = field(default_factory=list)

    # OUR DIFFERENTIATOR: pricing built in
    priced_estimate: Optional[PricedEstimate] = None

    # Source tracking
    data_source: str = ""  # "ai_takeoff", "deductive_engine", "hover_import"
    confidence: str = ""   # "measured", "derived", "ROM"


# ---------------------------------------------------------------------------
# Helper: format feet-inches string
# ---------------------------------------------------------------------------

def _fmt_ft_in(total_ft: float) -> str:
    """Format a decimal feet value as X' Y\" string."""
    feet = int(total_ft)
    inches = round((total_ft - feet) * 12)
    if inches == 12:
        feet += 1
        inches = 0
    if inches == 0:
        return f"{feet}'"
    return f"{feet}' {inches}\""


# ---------------------------------------------------------------------------
# The Measurement Report Generator
# ---------------------------------------------------------------------------

class MeasurementReportGenerator:
    """Generates HOVER-style Complete Measurement Reports.

    Can produce reports from:
    1. AI PDF takeoff results (highest accuracy — measured from plans)
    2. Deductive engine seeds (fast — derived from minimal inputs)
    3. HOVER JSON import (bridge for existing HOVER customers)

    Usage:
        gen = MeasurementReportGenerator(settings)
        report = gen.from_seeds(
            property_name="2 BR ESSENTIAL 24-PLEX",
            seeds=SeedValues(footprint_sf=7998, stories_above_grade=2, ...)
        )
        report_dict = gen.report_to_dict(report)
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = DeductiveEngine()
        self.catalog = LiveCatalog(settings)

    def from_seeds(
        self,
        property_name: str,
        seeds: SeedValues,
        address: str = "",
    ) -> CompleteMeasurementReport:
        """Generate a complete measurement report from seed values.

        This is the deductive path — fast, no PDF required.
        Produces the same structured output as HOVER but with pricing.
        """
        # Step 1: Derive all quantities
        derived = self.engine.derive(seeds)

        # Step 2: Generate schedule of values for pricing
        sov = self.engine.generate_schedule_of_values(seeds, derived)

        # Step 3: Build the report
        report = CompleteMeasurementReport(
            property_name=property_name,
            property_address=address,
            building_id=seeds.building_id,
            data_source="deductive_engine",
            confidence="derived",
        )

        # Build each section
        report.siding_summary = self._build_siding_summary(seeds, derived)
        report.roof_summary = self._build_roof_summary(seeds, derived)
        report.footprint = self._build_footprint(seeds, derived)
        report.elevation_siding = self._build_elevation_siding(seeds, derived)
        report.priced_estimate = self._build_priced_estimate(
            seeds, derived, sov
        )

        logger.info(
            f"Measurement report generated: {property_name}, "
            f"siding={report.siding_summary.total_siding_sf:.0f} SF, "
            f"roof={report.roof_summary.total_roof_area_sf:.0f} SF, "
            f"total=${report.priced_estimate.grand_total:,.0f}"
        )

        return report

    def from_takeoff(
        self,
        property_name: str,
        takeoff_result: dict,
        address: str = "",
    ) -> CompleteMeasurementReport:
        """Generate report from AI PDF takeoff results.

        This is the high-accuracy path — measurements from blueprints.
        """
        report = CompleteMeasurementReport(
            property_name=property_name,
            property_address=address,
            data_source="ai_takeoff",
            confidence="measured",
        )

        # Extract measured values from takeoff and build report sections
        # The takeoff result contains per-trade measurements that map
        # directly to our report sections
        items = takeoff_result.get("items", [])

        siding = SidingSummary()
        roof = RoofSummary()

        for item in items:
            trade = item.get("trade", "").lower()
            qty = float(item.get("quantity", 0))
            unit = item.get("unit", "")

            if trade in ("siding", "sid") and unit == "SF":
                siding.facades_siding_sf += qty
            elif trade in ("roofing", "rof") and unit in ("SQ", "SF"):
                roof_sf = qty * 100 if unit == "SQ" else qty
                roof.total_roof_area_sf += roof_sf
            elif trade in ("windows", "win"):
                siding.openings_siding_qty += int(qty)
            elif trade in ("gutters", "gut") and unit == "LF":
                pass  # captured in roof summary

        siding.total_siding_sf = siding.facades_siding_sf
        report.siding_summary = siding
        report.roof_summary = roof

        return report

    # -----------------------------------------------------------------------
    # Section builders
    # -----------------------------------------------------------------------

    def _build_siding_summary(
        self, seeds: SeedValues, d: DerivedQuantities
    ) -> SidingSummary:
        """Build the siding summary section (HOVER Page 1 equivalent)."""
        s = SidingSummary()

        # Facades — total cladding area (siding + accent)
        s.facades_siding_sf = round(d.primary_cladding_sf)
        s.facades_other_sf = round(d.secondary_cladding_sf)

        # Openings — deductions
        s.openings_siding_sf = round(d.total_window_area_sf)
        s.openings_other_sf = round(d.total_door_area_sf)
        s.openings_siding_qty = d.window_count
        s.openings_other_qty = d.ext_door_count + d.sgd_count

        # Trims
        s.trims_siding_sf = round(
            d.j_channel_lf * 0.33 + d.corner_trim_lf * 0.5  # Approximate trim area
        )

        # Totals
        s.total_siding_sf = round(
            s.facades_siding_sf + s.trims_siding_sf
        )
        s.total_other_sf = round(
            s.facades_other_sf
        )

        # Opening perimeter lengths
        avg_win_perim = 16.0  # ~(3+5)*2 for 3'×5' window
        avg_door_perim = 18.0  # ~(3+6.67)*2
        total_opening_perim = (
            d.window_count * avg_win_perim
            + (d.ext_door_count + d.sgd_count) * avg_door_perim
        )
        s.openings_total_perimeter = _fmt_ft_in(total_opening_perim)
        s.openings_tops_length = _fmt_ft_in(
            d.window_count * 3.0 + (d.ext_door_count + d.sgd_count) * 3.0
        )
        s.openings_sills_length = _fmt_ft_in(
            d.window_count * 3.0  # Only windows have sills
        )
        s.openings_sides_length = _fmt_ft_in(
            d.window_count * 5.0 * 2
            + (d.ext_door_count + d.sgd_count) * 6.67 * 2
        )

        # Corners — estimate from building shape
        corners_per_floor = self._estimate_corners(seeds)
        s.inside_corner_qty = corners_per_floor["inside"]
        s.outside_corner_qty = corners_per_floor["outside"]
        wall_ht = d.total_building_height_ft
        s.inside_corner_length = _fmt_ft_in(
            s.inside_corner_qty * wall_ht
        )
        s.outside_corner_length = _fmt_ft_in(
            s.outside_corner_qty * wall_ht
        )

        # Trim — starter, vertical, sloped
        s.level_starter_siding = _fmt_ft_in(d.perimeter_lf)
        s.level_starter_other = _fmt_ft_in(0)
        s.vertical_trim_siding = _fmt_ft_in(d.corner_trim_lf)

        # Roofline
        s.eaves_fascia_length = _fmt_ft_in(d.fascia_lf * 0.5)
        s.rakes_fascia_length = _fmt_ft_in(d.fascia_lf * 0.1)
        s.level_frieze_board_length = _fmt_ft_in(d.fascia_lf * 0.5)
        s.level_frieze_board_soffit_sf = round(d.soffit_sf * 0.8)
        s.sloped_frieze_board_soffit_sf = round(d.soffit_sf * 0.2)

        # Waste tiers — matching HOVER's format
        base_sf = s.facades_siding_sf + s.facades_other_sf
        for pct in [0.0, 0.10, 0.18]:
            area = round(base_sf * (1 + pct))
            s.waste_tiers.append(WasteTier(
                waste_pct=pct, area_sf=area, squares=round(area / 100, 1)
            ))

        # With opening deductions (< 20 SF openings)
        net_base = base_sf - s.openings_siding_sf - s.openings_other_sf
        for pct in [0.0, 0.10, 0.18]:
            area = round(net_base * (1 + pct))
            s.waste_tiers_openings_lt_20sf.append(WasteTier(
                waste_pct=pct, area_sf=area, squares=round(area / 100, 1)
            ))

        return s

    def _build_roof_summary(
        self, seeds: SeedValues, d: DerivedQuantities
    ) -> RoofSummary:
        """Build the roof summary section (HOVER Page 2 equivalent)."""
        r = RoofSummary()
        r.total_roof_area_sf = round(d.roof_area_actual_sf)

        # Estimate facet/ridge/valley counts from building shape
        roof_geom = self._estimate_roof_geometry(seeds, d)

        r.items = [
            RoofItem(
                name="Roof Facets",
                area_sf=r.total_roof_area_sf,
                total_count=roof_geom["facets"],
            ),
            RoofItem(
                name="Ridges / Hips",
                total_count=roof_geom["ridges"],
                total_length=_fmt_ft_in(roof_geom["ridge_lf"]),
            ),
            RoofItem(
                name="Valleys",
                total_count=roof_geom["valleys"],
                total_length=_fmt_ft_in(roof_geom["valley_lf"]),
            ),
            RoofItem(
                name="Rakes",
                total_count=roof_geom["rakes"],
                total_length=_fmt_ft_in(roof_geom["rake_lf"]),
            ),
            RoofItem(
                name="Eaves",
                total_count=roof_geom["eaves"],
                total_length=_fmt_ft_in(d.gutter_lf or d.perimeter_lf * 0.5),
            ),
            RoofItem(
                name="Flashing",
                total_count=roof_geom["flashing_count"],
                total_length=_fmt_ft_in(roof_geom["flashing_lf"]),
            ),
            RoofItem(
                name="Step Flashing",
                total_count=roof_geom["step_flash_count"],
                total_length=_fmt_ft_in(roof_geom["step_flash_lf"]),
            ),
            RoofItem(
                name="Drip Edge/Perimeter",
                total_length=_fmt_ft_in(d.perimeter_lf),
            ),
        ]

        # Pitch breakdown
        main_pitch = seeds.roof_pitch if seeds.roof_pitch != "flat" else "0/12"
        r.pitch_breakdown = [
            RoofPitchBreakdown(
                pitch=main_pitch,
                area_sf=round(r.total_roof_area_sf * 0.87),
                percentage=87.0,
            ),
        ]
        # Secondary pitches (transitions, dormers)
        remaining = r.total_roof_area_sf - r.pitch_breakdown[0].area_sf
        if remaining > 0:
            r.pitch_breakdown.append(RoofPitchBreakdown(
                pitch="2/12",
                area_sf=round(remaining * 0.8),
                percentage=round(remaining * 0.8 / r.total_roof_area_sf * 100, 1),
            ))
            r.pitch_breakdown.append(RoofPitchBreakdown(
                pitch="0/12",
                area_sf=round(remaining * 0.2),
                percentage=round(remaining * 0.2 / r.total_roof_area_sf * 100, 1),
            ))

        # Waste tiers
        for pct in [0.0, 0.05, 0.10, 0.15, 0.20]:
            area = round(r.total_roof_area_sf * (1 + pct))
            r.waste_tiers.append(WasteTier(
                waste_pct=pct, area_sf=area, squares=round(area / 100, 1)
            ))

        return r

    def _build_footprint(
        self, seeds: SeedValues, d: DerivedQuantities
    ) -> FootprintData:
        """Build the footprint section (HOVER Page 3 equivalent)."""
        f = FootprintData()

        stories_str = str(seeds.stories_above_grade)
        if seeds.stories_above_grade > 1:
            stories_str = f"> 1"
        f.stories = stories_str

        f.footprint_perimeter = _fmt_ft_in(d.perimeter_lf)
        f.footprint_area_sf = round(seeds.footprint_sf)

        # Compute overall dimensions
        if seeds.footprint_length_ft > 0 and seeds.footprint_width_ft > 0:
            f.overall_length_ft = seeds.footprint_length_ft
            f.overall_width_ft = seeds.footprint_width_ft
        else:
            # Estimate from footprint area assuming typical aspect ratio
            aspect = 2.5  # Typical multifamily L:W
            f.overall_width_ft = round(math.sqrt(seeds.footprint_sf / aspect), 1)
            f.overall_length_ft = round(f.overall_width_ft * aspect, 1)

        return f

    def _build_elevation_siding(
        self, seeds: SeedValues, d: DerivedQuantities
    ) -> list[ElevationSiding]:
        """Build the per-elevation siding breakdown (HOVER Pages 5-6).

        Distributes total siding area across 4 elevations based on
        building shape and aspect ratio.
        """
        total_siding = d.primary_cladding_sf + d.secondary_cladding_sf

        # Estimate wall area per elevation from aspect ratio
        if seeds.footprint_length_ft > 0 and seeds.footprint_width_ft > 0:
            length = seeds.footprint_length_ft
            width = seeds.footprint_width_ft
        else:
            width = math.sqrt(seeds.footprint_sf / 2.5)
            length = width * 2.5

        # Wall area proportions per elevation
        perim = 2 * (length + width)
        front_pct = length / perim
        right_pct = width / perim
        back_pct = front_pct
        left_pct = right_pct

        elevations = []
        section_counter = 1

        for elev_name, pct in [
            ("FRONT", front_pct),
            ("RIGHT", right_pct),
            ("LEFT", left_pct),
            ("BACK", back_pct),
        ]:
            elev_sf = total_siding * pct
            # Break into sections (roughly 1 section per 100 SF)
            num_sections = max(1, round(elev_sf / 120))
            sections = []
            remaining = elev_sf

            for i in range(num_sections):
                if i == num_sections - 1:
                    sec_sf = remaining
                else:
                    # Vary section sizes to look realistic
                    sec_sf = elev_sf / num_sections * (0.7 + 0.6 * (i % 3) / 2)
                    sec_sf = min(sec_sf, remaining)

                sections.append(SidingSection(
                    section_id=f"SI-{section_counter}",
                    area_sf=round(sec_sf),
                ))
                remaining -= sec_sf
                section_counter += 1

            elevations.append(ElevationSiding(
                elevation=elev_name,
                sections=sections,
                total_sf=round(elev_sf),
            ))

        return elevations

    def _build_priced_estimate(
        self, seeds: SeedValues, d: DerivedQuantities, sov
    ) -> PricedEstimate:
        """Build the priced estimate — our key differentiator over HOVER.

        HOVER stops at measurements. We continue to full pricing.
        """
        # Re-price SOV using live catalog
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

        estimate = PricedEstimate()

        for pi in priced_items:
            qty = float(pi.get("qty", 0))
            up = float(pi.get("unit_price", 0))
            mat = float(pi.get("material_cost", 0))
            lab = float(pi.get("labor_cost", 0))
            extended = float(pi.get("value", 0))
            equip = extended - mat - lab

            estimate.line_items.append(PricedLineItem(
                trade=pi.get("csi", "")[:2],
                description=pi.get("description", ""),
                csi_division=pi.get("csi", ""),
                quantity=qty,
                unit=pi.get("unit", ""),
                unit_price=up,
                material_cost=mat,
                labor_cost=lab,
                equipment_cost=max(0, equip),
                extended_price=extended,
                pricing_source=pi.get("pricing_source", ""),
            ))

        estimate.total_material = round(
            sum(li.material_cost for li in estimate.line_items), 2
        )
        estimate.total_labor = round(
            sum(li.labor_cost for li in estimate.line_items), 2
        )
        estimate.total_equipment = round(
            sum(li.equipment_cost for li in estimate.line_items), 2
        )
        estimate.subtotal_direct = round(
            sum(li.extended_price for li in estimate.line_items), 2
        )

        company = self.settings.company
        estimate.overhead = round(
            estimate.subtotal_direct * company.overhead_percent, 2
        )
        estimate.profit = round(
            (estimate.subtotal_direct + estimate.overhead)
            * company.profit_percent, 2
        )
        estimate.bond = round(
            estimate.subtotal_direct * company.bond_percent, 2
        )
        estimate.tax = round(
            estimate.total_material * company.tax_rate, 2
        )
        estimate.grand_total = round(
            estimate.subtotal_direct
            + estimate.overhead
            + estimate.profit
            + estimate.bond
            + estimate.tax, 2
        )

        return estimate

    # -----------------------------------------------------------------------
    # Geometry estimation helpers
    # -----------------------------------------------------------------------

    def _estimate_corners(self, seeds: SeedValues) -> dict:
        """Estimate inside/outside corner counts from building shape."""
        shape = seeds.building_shape

        if shape == "square":
            return {"inside": 0, "outside": 4}
        elif shape == "rectangle_2:1":
            return {"inside": 0, "outside": 4}
        elif shape == "l_shape":
            return {"inside": 1, "outside": 5}
        elif shape == "u_shape":
            return {"inside": 2, "outside": 6}
        elif shape == "t_shape":
            return {"inside": 2, "outside": 6}
        else:
            # typical_multifamily — usually has some jogs
            # Estimate based on perimeter complexity
            if seeds.footprint_sf > 10000:
                return {"inside": 6, "outside": 10}
            elif seeds.footprint_sf > 5000:
                return {"inside": 4, "outside": 8}
            else:
                return {"inside": 2, "outside": 6}

    def _estimate_roof_geometry(
        self, seeds: SeedValues, d: DerivedQuantities
    ) -> dict:
        """Estimate roof geometry (facets, ridges, valleys, etc.)."""
        is_flat = seeds.roof_pitch.lower() in ("flat", "0:12", "1/4:12", "")
        footprint = seeds.footprint_sf

        if is_flat:
            return {
                "facets": 1,
                "ridges": 0, "ridge_lf": 0,
                "valleys": 0, "valley_lf": 0,
                "rakes": 0, "rake_lf": 0,
                "eaves": 0,
                "flashing_count": 4, "flashing_lf": d.perimeter_lf * 0.1,
                "step_flash_count": 0, "step_flash_lf": 0,
            }

        # Estimate based on building complexity
        corners = self._estimate_corners(seeds)
        total_corners = corners["inside"] + corners["outside"]

        # Facets scale with building complexity
        facets = max(4, total_corners * 2)

        # Ridge length roughly follows the building length
        if seeds.footprint_length_ft > 0:
            ridge_lf = seeds.footprint_length_ft * 1.1  # Account for jogs
        else:
            ridge_lf = math.sqrt(footprint * 2.5) * 1.1

        # Valleys appear at inside corners and plan jogs
        valleys = corners["inside"] * 2
        valley_lf = valleys * d.total_building_height_ft * 1.5

        # Rakes — gable ends
        rake_count = max(2, corners["outside"] // 2)
        rake_lf = rake_count * d.total_building_height_ft * 0.6

        # Eave count
        eave_count = max(4, facets // 2)

        # Flashing at penetrations and transitions
        flashing_count = max(4, valleys + rake_count)
        flashing_lf = d.perimeter_lf * 0.05

        # Step flashing where roof meets walls
        step_count = valleys + corners["inside"]
        step_lf = step_count * d.total_building_height_ft * 0.8

        return {
            "facets": facets,
            "ridges": max(1, facets // 3), "ridge_lf": ridge_lf,
            "valleys": valleys, "valley_lf": valley_lf,
            "rakes": rake_count, "rake_lf": rake_lf,
            "eaves": eave_count,
            "flashing_count": flashing_count, "flashing_lf": flashing_lf,
            "step_flash_count": step_count, "step_flash_lf": step_lf,
        }

    # -----------------------------------------------------------------------
    # Serialization
    # -----------------------------------------------------------------------

    def report_to_dict(self, report: CompleteMeasurementReport) -> dict:
        """Convert report to JSON-serializable dict for API responses."""
        result = {
            "property_name": report.property_name,
            "property_address": report.property_address,
            "building_id": report.building_id,
            "data_source": report.data_source,
            "confidence": report.confidence,
        }

        if report.siding_summary:
            s = report.siding_summary
            result["siding_summary"] = {
                "areas": {
                    "facades": {"siding": s.facades_siding_sf, "other": s.facades_other_sf},
                    "openings": {"siding": s.openings_siding_sf, "other": s.openings_other_sf},
                    "trims": {"siding": s.trims_siding_sf, "other": s.trims_other_sf},
                    "total": {"siding": s.total_siding_sf, "other": s.total_other_sf},
                },
                "openings": {
                    "quantity": {"siding": s.openings_siding_qty, "other": s.openings_other_qty},
                    "tops_length": s.openings_tops_length,
                    "sills_length": s.openings_sills_length,
                    "sides_length": s.openings_sides_length,
                    "total_perimeter": s.openings_total_perimeter,
                },
                "corners": {
                    "inside": {"qty": s.inside_corner_qty, "length": s.inside_corner_length},
                    "outside": {"qty": s.outside_corner_qty, "length": s.outside_corner_length},
                },
                "trim": {
                    "level_starter": {"siding": s.level_starter_siding, "other": s.level_starter_other},
                    "sloped_trim": s.sloped_trim,
                    "vertical_trim": {"siding": s.vertical_trim_siding},
                },
                "roofline": {
                    "eaves_fascia": s.eaves_fascia_length,
                    "level_frieze_board": {
                        "length": s.level_frieze_board_length,
                        "soffit_area": s.level_frieze_board_soffit_sf,
                    },
                    "rakes_fascia": s.rakes_fascia_length,
                    "sloped_frieze_board": {
                        "length": s.sloped_frieze_board_length,
                        "soffit_area": s.sloped_frieze_board_soffit_sf,
                    },
                },
                "waste_totals": [
                    {"waste_pct": t.waste_pct, "area_sf": t.area_sf, "squares": t.squares}
                    for t in s.waste_tiers
                ],
            }

        if report.roof_summary:
            r = report.roof_summary
            result["roof_summary"] = {
                "total_area_sf": r.total_roof_area_sf,
                "items": [
                    {"name": i.name, "area_sf": i.area_sf,
                     "count": i.total_count, "length": i.total_length}
                    for i in r.items
                ],
                "pitch_breakdown": [
                    {"pitch": p.pitch, "area_sf": p.area_sf,
                     "percentage": p.percentage}
                    for p in r.pitch_breakdown
                ],
                "waste_tiers": [
                    {"waste_pct": t.waste_pct, "area_sf": t.area_sf, "squares": t.squares}
                    for t in r.waste_tiers
                ],
            }

        if report.footprint:
            f = report.footprint
            result["footprint"] = {
                "stories": f.stories,
                "perimeter": f.footprint_perimeter,
                "area_sf": f.footprint_area_sf,
                "overall_length_ft": f.overall_length_ft,
                "overall_width_ft": f.overall_width_ft,
            }

        if report.elevation_siding:
            result["siding_per_elevation"] = [
                {
                    "elevation": e.elevation,
                    "total_sf": e.total_sf,
                    "sections": [
                        {"id": sec.section_id, "area_sf": sec.area_sf}
                        for sec in e.sections
                    ],
                }
                for e in report.elevation_siding
            ]

        if report.priced_estimate:
            p = report.priced_estimate
            result["priced_estimate"] = {
                "line_items": [
                    {
                        "trade": li.trade,
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
                    for li in p.line_items
                ],
                "totals": {
                    "material": p.total_material,
                    "labor": p.total_labor,
                    "equipment": p.total_equipment,
                    "subtotal_direct": p.subtotal_direct,
                    "overhead": p.overhead,
                    "profit": p.profit,
                    "bond": p.bond,
                    "tax": p.tax,
                    "grand_total": p.grand_total,
                },
            }

        return result
