"""
Deductive Ratio Engine — Mathematical Takeoff by Derivation

Instead of measuring pixels on drawings, this engine uses the LAW OF
DEDUCTION: start from KNOWN SEED VALUES that are explicitly labeled on
the blueprints (total SF, stories, unit count, building height) and
mathematically derive ALL envelope quantities using proven industry
ratios and geometric relationships.

The AI agent's job becomes:
1. READ labeled dimensions from the plans (not measure pixels)
2. Feed those seed values into this engine
3. The engine DERIVES every quantity via math
4. The AI VERIFIES the derived values against the drawings

This is dramatically more reliable than pixel measurement because:
- Architects already calculated the exact dimensions
- Labeled numbers are high-confidence reads (the AI just OCRs them)
- Mathematical derivation is deterministic (no measurement error)
- Industry ratios are validated across thousands of projects

Algorithm: DEDUCTIVE CHAIN
  Building SF (from plans) → Footprint shape → Perimeter
  Perimeter + Stories + Floor Height → Gross Wall Area
  Gross Wall Area × WWR → Window/Door Deductions → Net Wall Area
  Net Wall Area → Siding, WRB, Insulation, Trim quantities
  Footprint + Pitch → Roof Area → Roofing, Underlayment quantities
  Eave Perimeter → Gutter, Downspout quantities
  Unit Count × Per-Unit Ratios → Windows, Doors, Balconies

Per-Building AIA G703 Schedule of Values breakdown included.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Industry ratios — validated across commercial multifamily projects
# ---------------------------------------------------------------------------

# Perimeter-to-area ratio: P = k × sqrt(A)
# For a perfect square: k = 4.0 (P = 4 × sqrt(A))
# Real buildings are rectangular/L-shaped, so k is higher
SHAPE_FACTORS = {
    "square": 4.0,           # P = 4√A
    "rectangle_2:1": 4.47,   # P = 2(L+W) where L=2W, A=L×W
    "rectangle_3:1": 4.62,   # Common for apartment wings
    "l_shape": 4.8,          # L-shaped with equal wings
    "u_shape": 5.0,          # U-shaped courtyard
    "t_shape": 4.9,          # T-shaped
    "typical_multifamily": 4.6,  # Empirical average for 3-5 story MF
}

# Window-to-Wall Ratio (WWR) by building type
# Validated against DOE Commercial Prototype Building Models & CBECS data
# ASHRAE 90.1 baseline cap: 40% of gross above-grade wall area
# California Title 24 max: 40% WWR
WINDOW_WALL_RATIOS = {
    # Multifamily — DOE prototype: 20% mid-rise, 30-35% high-rise
    "multifamily_standard": 0.20,    # 20% — DOE mid-rise prototype (3-5 story garden)
    "multifamily_upscale": 0.28,     # 28% — upscale mid-rise, more glass
    "multifamily_highrise": 0.33,    # 33% — DOE high-rise prototype (8+ stories)
    "multifamily_affordable": 0.15,  # 15% — code minimum, smaller windows
    # Commercial — DOE prototypes
    "office_small": 0.20,            # 20% — DOE small office (1-story)
    "office_medium": 0.33,           # 33% — DOE medium office (2-4 story)
    "office_large": 0.40,            # 40% — DOE large office (>4 story), ASHRAE cap
    "retail_box": 0.18,              # 18% — DOE retail prototype
    "retail_ground_floor": 0.70,     # 70% — DOE storefront glazing
    "hospital": 0.27,                # 27% — DOE hospital prototype
    "school_k12": 0.33,              # 33% — DOE K-12 school prototype
    # Residential
    "single_family": 0.15,           # 15% — residential
}

# Windows per residential unit (by unit type)
WINDOWS_PER_UNIT = {
    "studio": 3,
    "1br": 5,
    "2br": 7,
    "3br": 9,
    "average_mix": 6,     # Typical mix of 1BR/2BR
    "upscale_mix": 7.5,   # Larger windows, more per unit
}

# Doors per unit (exterior only)
EXT_DOORS_PER_UNIT = {
    "entry_door": 1.0,             # Every unit has 1 entry
    "balcony_sgd": 0.75,           # ~75% of units have a sliding glass door
    "common_ext_doors_per_unit": 0.05,  # Lobby, fire exits, service doors
}

# Floor-to-floor heights (ft)
FLOOR_HEIGHTS = {
    "residential_wood_frame": 9.67,   # 9'-8" (8' ceiling + joists + floor)
    "residential_steel_frame": 10.0,
    "ground_floor_retail": 13.0,
    "ground_floor_podium": 12.0,
    "parking_garage": 10.5,
}

# Gutter and downspout ratios — validated industry standards
# Research: 1 DS per 30-35 LF most common; 1 per 600-800 SF roof (5" gutter, 2×3 DS)
# Residential rule of thumb: building SF / 10 ≈ gutter LF
GUTTER_RATIOS = {
    "downspout_spacing_lf": 35,     # 1 downspout per 35 LF of gutter (industry standard)
    "downspout_by_roof_sf": 700,    # 1 downspout per 700 SF of roof area (5" K-style)
    "downspout_by_roof_sf_6in": 1100,  # 1 per 1100 SF (6" gutter, 3×4 DS)
    "downspout_height_adder_ft": 4, # Add 4 ft for elbows at top and bottom
    "elbow_count_per_downspout": 3, # Typical: top offset + bottom offset
    "cross_section_rule": 100,      # 1 sq in of DS cross-section per 100 SF roof
    # Gutter length by roof type
    "gable_eave_ratio": 0.50,       # Gable: gutters on eaves = ~50% of perimeter
    "hip_eave_ratio": 1.00,         # Hip: gutters on all sides = full perimeter at eave
}

# Trim and accessory ratios (LF per SF of cladding)
TRIM_RATIOS = {
    "j_channel_per_sf": 0.08,        # LF of J-channel per SF of siding
    "corner_trim_per_sf": 0.015,     # Inside + outside corners
    "starter_strip_per_sf": 0.02,    # Bottom edge
    "band_board_per_floor": 1.0,     # Perimeter × (floors - 1) ratio
}

# Sealant ratios
SEALANT_RATIOS = {
    "lf_per_window": 16,    # ~16 LF of sealant per window (perimeter)
    "lf_per_door": 18,      # ~18 LF per exterior door
    "control_joint_spacing_ft": 24,  # Control joint every 24 LF of wall
}

# Balcony ratios
BALCONY_RATIOS = {
    "pct_units_with_balcony": 0.75,
    "avg_balcony_sf": 60,
    "avg_railing_lf_per_balcony": 18,  # 3 sides × 6 LF average
}

# Waterproofing ratios
WATERPROOFING_RATIOS = {
    "foundation_depth_ft": 4.0,   # Typical below-grade depth
}

# Validated standard deduction sizes (Dagostino/Peterson textbook)
OPENING_DEDUCTION_SF = {
    "window_avg_sf": 15.0,        # ~3' × 5' standard window
    "door_avg_sf": 20.0,          # ~3' × 6'-8" standard exterior door
    "sgd_avg_sf": 40.0,           # ~6' × 6'-8" sliding glass door
}

# Roofing waste factors by complexity tier — validated from research
# Source: Deductive takeoff methods research, industry data
ROOF_WASTE_FACTORS = {
    "simple_gable": 0.08,         # 5-10% — simple gable, no valleys
    "standard_gable": 0.10,       # 7-10% — standard residential gable
    "standard_hip": 0.13,         # 12-15% — standard hip roof
    "complex_hip": 0.18,          # 15-22% — complex hip with valleys/dormers
    "extreme": 0.22,              # 25%+ — extreme complexity, many intersections
    "flat_membrane": 0.05,        # 5% — flat/low-slope membrane (laps only)
    # Add-ons (cumulative)
    "addon_skylights": 0.01,      # +1% for skylights
    "addon_dormers": 0.015,       # +1.5% per dormer zone
    "addon_multiple_valleys": 0.02,  # +2% for multiple valleys
    "addon_steep_pitch": 0.025,   # +2.5% for pitch ≥ 8:12 (handling difficulty)
}

# Wall-to-Floor Area Ratio (WFR) — validated from research
# WFR = External Wall Area / Gross Floor Area
# A 0.1 change in WFR impacts construction costs by 4-5%
WALL_FLOOR_RATIOS = {
    "office_large_deep_plate": 0.40,   # Large office, deep floor plates
    "office_midrise_benchmark": 0.46,  # Mid-rise office benchmark
    "office_high_range": 0.50,         # High-end office
    "multifamily_efficient": 0.50,     # Efficient square multifamily
    "multifamily_typical": 0.60,       # Typical apartment building
    "multifamily_tower": 0.70,         # Narrow tower, high WFR
    "residential_narrow": 0.80,        # Long/narrow residential (worst case)
}

# Parametric cost impact constants — RSMeans method
PARAMETRIC_COST_IMPACTS = {
    "perimeter_cost_per_100lf_per_sf": 1.60,  # Each +100 LF perimeter adds $1.60/SF
    "scaling_exponent": 0.6,                   # Six-Tenths Rule for economy of scale
}

# Soffit depth constants
SOFFIT_DEPTHS = {
    "typical_residential": 1.5,   # 1.5 ft soffit depth — standard
    "wide_overhang": 2.0,         # 2 ft overhang — craftsman/ranch style
    "minimal": 1.0,               # 1 ft — tight urban, code minimum
    "commercial_flat": 0.0,       # No soffit on flat commercial roofs
}


# ---------------------------------------------------------------------------
# Seed Values — what the AI reads from labeled dimensions on plans
# ---------------------------------------------------------------------------

@dataclass
class SeedValues:
    """Known dimensions read directly from the blueprints.

    The AI agent OCRs these labeled values from the plans.
    These are HIGH-CONFIDENCE inputs — architects calculated them.
    """
    # Required seed values (at least footprint_sf and stories)
    building_id: str = "Building A"
    footprint_sf: float = 0.0            # From floor plan area schedule
    stories_above_grade: int = 0         # Count from sections/elevations
    stories_below_grade: int = 0

    # High-value seeds (read from plans if available)
    footprint_length_ft: float = 0.0     # From floor plan dimensions
    footprint_width_ft: float = 0.0      # From floor plan dimensions
    perimeter_lf: float = 0.0            # From floor plan if dimensioned
    floor_to_floor_ft: float = 0.0       # From building section
    total_building_height_ft: float = 0.0  # From elevation dimension string
    parapet_height_ft: float = 0.0       # From wall section detail

    # Unit data (from unit plans / general notes)
    unit_count: int = 0
    unit_mix: dict = field(default_factory=dict)  # {"1br": 80, "2br": 100, "3br": 20}

    # Roof data
    roof_pitch: str = "flat"             # From section or roof plan
    roof_type: str = "TPO membrane"      # From roof plan notes

    # Building shape
    building_shape: str = "typical_multifamily"  # square, rectangle_2:1, l_shape, etc.

    # Construction type
    construction_type: str = "V-A"       # From general notes / code analysis
    has_podium: bool = False             # Concrete podium level
    podium_height_ft: float = 0.0

    # Cladding (from elevation notes / specs)
    primary_cladding: str = "fiber_cement_lap"
    secondary_cladding: str = ""
    secondary_cladding_floors: str = ""  # e.g., "1" or "1-2"

    # Corridor type (from floor plan)
    corridor_type: str = "interior"      # interior, exterior_breezeway, single_loaded

    # Balcony data (from elevations / unit plans)
    balcony_count: int = 0               # If known, otherwise derived
    avg_balcony_sf: float = 60.0

    # Extra seeds the AI might find
    window_count_from_schedule: int = 0  # If window schedule is readable
    door_count_from_schedule: int = 0    # If door schedule is readable
    gross_wall_area_from_plans: float = 0.0  # Sometimes labeled on plans


# ---------------------------------------------------------------------------
# Derived Values — mathematically computed from seeds
# ---------------------------------------------------------------------------

@dataclass
class DerivedQuantities:
    """All quantities derived mathematically from seed values."""
    building_id: str = ""

    # Geometry
    perimeter_lf: float = 0.0
    total_building_height_ft: float = 0.0
    gross_wall_area_sf: float = 0.0
    parapet_area_sf: float = 0.0
    total_envelope_wall_sf: float = 0.0

    # Deductions
    window_wall_ratio: float = 0.0
    total_window_area_sf: float = 0.0
    total_door_area_sf: float = 0.0
    total_deductions_sf: float = 0.0
    net_wall_area_sf: float = 0.0
    net_to_gross_ratio: float = 0.0

    # Counts
    window_count: int = 0
    ext_door_count: int = 0
    sgd_count: int = 0
    balcony_count: int = 0

    # Cladding
    primary_cladding_sf: float = 0.0
    secondary_cladding_sf: float = 0.0
    wrb_air_barrier_sf: float = 0.0
    continuous_insulation_sf: float = 0.0
    sheathing_sf: float = 0.0

    # Roofing
    roof_area_plan_sf: float = 0.0
    roof_area_actual_sf: float = 0.0
    roof_area_with_waste_sf: float = 0.0
    roof_pitch_multiplier: float = 1.0
    roof_waste_factor: float = 0.0

    # Sheet metal / trim
    soffit_sf: float = 0.0
    fascia_lf: float = 0.0
    j_channel_lf: float = 0.0
    corner_trim_lf: float = 0.0
    band_board_lf: float = 0.0
    coping_lf: float = 0.0

    # Gutters / drainage
    gutter_lf: float = 0.0
    downspout_lf: float = 0.0
    downspout_count: int = 0
    downspout_elbows: int = 0
    scupper_count: int = 0
    internal_drain_count: int = 0

    # Sealant
    perimeter_sealant_lf: float = 0.0
    control_joint_sealant_lf: float = 0.0

    # Waterproofing
    balcony_waterproofing_sf: float = 0.0
    foundation_waterproofing_sf: float = 0.0
    podium_waterproofing_sf: float = 0.0

    # Railing
    balcony_railing_lf: float = 0.0
    corridor_railing_lf: float = 0.0
    stair_railing_lf: float = 0.0

    # Derivation log — shows the math for every line
    derivation_log: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AIA G703 Schedule of Values per building
# ---------------------------------------------------------------------------

@dataclass
class ScheduleOfValuesItem:
    """One line item in the AIA G703 Schedule of Values."""
    item_number: str
    description: str
    csi_division: str
    scheduled_value: float = 0.0
    unit: str = ""
    quantity: float = 0.0
    unit_price: float = 0.0
    notes: str = ""


@dataclass
class BuildingScheduleOfValues:
    """AIA G703 Schedule of Values for one building."""
    building_id: str
    items: list[ScheduleOfValuesItem] = field(default_factory=list)
    total_value: float = 0.0


# ---------------------------------------------------------------------------
# The Deductive Engine
# ---------------------------------------------------------------------------

class DeductiveEngine:
    """Derives all envelope quantities from seed values using math.

    The core algorithm:
    1. Read SEED VALUES from labeled dimensions on plans (AI does OCR, not measurement)
    2. DERIVE perimeter from footprint using shape factor: P = k × √A
    3. DERIVE wall area: gross_wall = perimeter × total_height
    4. DERIVE deductions using WWR: deductions = gross_wall × WWR
    5. DERIVE net wall = gross - deductions → drives cladding, WRB, insulation
    6. DERIVE roof from footprint × pitch multiplier
    7. DERIVE all accessories from primary quantities using ratios
    """

    def derive(
        self,
        seeds: SeedValues,
        wwr_override: Optional[float] = None,
    ) -> DerivedQuantities:
        """Run the full deductive chain from seed values to quantities."""

        d = DerivedQuantities(building_id=seeds.building_id)
        log = d.derivation_log

        # ------------------------------------------------------------------
        # Step 1: PERIMETER from footprint
        # ------------------------------------------------------------------
        if seeds.perimeter_lf > 0:
            d.perimeter_lf = seeds.perimeter_lf
            log.append(
                f"Perimeter: {d.perimeter_lf:.0f} LF "
                f"(READ from plans — high confidence)"
            )
        elif seeds.footprint_length_ft > 0 and seeds.footprint_width_ft > 0:
            d.perimeter_lf = 2 * (
                seeds.footprint_length_ft + seeds.footprint_width_ft
            )
            log.append(
                f"Perimeter: 2 × ({seeds.footprint_length_ft:.0f} + "
                f"{seeds.footprint_width_ft:.0f}) = {d.perimeter_lf:.0f} LF "
                f"(derived from L×W — high confidence)"
            )
        elif seeds.footprint_sf > 0:
            k = SHAPE_FACTORS.get(
                seeds.building_shape, SHAPE_FACTORS["typical_multifamily"]
            )
            d.perimeter_lf = k * math.sqrt(seeds.footprint_sf)
            log.append(
                f"Perimeter: {k} × √{seeds.footprint_sf:.0f} = "
                f"{d.perimeter_lf:.0f} LF "
                f"(derived from shape factor k={k} for '{seeds.building_shape}')"
            )
            d.confidence_notes.append(
                "Perimeter derived from shape factor — verify against plans"
            )
        else:
            log.append("WARNING: Cannot derive perimeter — no footprint data")
            return d

        # ------------------------------------------------------------------
        # Step 2: BUILDING HEIGHT
        # ------------------------------------------------------------------
        if seeds.total_building_height_ft > 0:
            d.total_building_height_ft = seeds.total_building_height_ft
            log.append(
                f"Height: {d.total_building_height_ft:.1f} ft "
                f"(READ from elevation — high confidence)"
            )
        else:
            ftf = seeds.floor_to_floor_ft
            if ftf <= 0:
                ftf = FLOOR_HEIGHTS.get(
                    "residential_wood_frame",
                    9.67,
                )
                log.append(
                    f"Floor-to-floor: using default {ftf:.2f} ft "
                    f"(not found on plans)"
                )

            d.total_building_height_ft = 0
            # Podium floor (taller)
            if seeds.has_podium and seeds.podium_height_ft > 0:
                d.total_building_height_ft += seeds.podium_height_ft
                wood_floors = seeds.stories_above_grade - 1
                d.total_building_height_ft += wood_floors * ftf
                log.append(
                    f"Height: {seeds.podium_height_ft:.1f} ft podium + "
                    f"{wood_floors} × {ftf:.2f} ft = "
                    f"{d.total_building_height_ft:.1f} ft"
                )
            else:
                d.total_building_height_ft = seeds.stories_above_grade * ftf
                log.append(
                    f"Height: {seeds.stories_above_grade} stories × "
                    f"{ftf:.2f} ft = {d.total_building_height_ft:.1f} ft"
                )

        # ------------------------------------------------------------------
        # Step 3: GROSS WALL AREA
        # ------------------------------------------------------------------
        if seeds.gross_wall_area_from_plans > 0:
            d.gross_wall_area_sf = seeds.gross_wall_area_from_plans
            log.append(
                f"Gross wall: {d.gross_wall_area_sf:.0f} SF "
                f"(READ from plans)"
            )
        else:
            d.gross_wall_area_sf = (
                d.perimeter_lf * d.total_building_height_ft
            )
            log.append(
                f"Gross wall: {d.perimeter_lf:.0f} LF × "
                f"{d.total_building_height_ft:.1f} ft = "
                f"{d.gross_wall_area_sf:.0f} SF"
            )

        # Add parapet walls
        if seeds.parapet_height_ft > 0:
            d.parapet_area_sf = d.perimeter_lf * seeds.parapet_height_ft * 2
            # × 2 because both interior and exterior faces
            log.append(
                f"Parapet: {d.perimeter_lf:.0f} LF × "
                f"{seeds.parapet_height_ft:.1f} ft × 2 faces = "
                f"{d.parapet_area_sf:.0f} SF"
            )
            d.coping_lf = d.perimeter_lf
            log.append(f"Coping: {d.coping_lf:.0f} LF (= parapet perimeter)")

        d.total_envelope_wall_sf = d.gross_wall_area_sf + d.parapet_area_sf

        # ------------------------------------------------------------------
        # Step 4: DEDUCTIONS (Window-to-Wall Ratio)
        # ------------------------------------------------------------------
        wwr = wwr_override
        if wwr is None:
            # Select WWR based on building type — DOE/CBECS validated
            if seeds.stories_above_grade >= 8:
                wwr = WINDOW_WALL_RATIOS["multifamily_highrise"]
            elif seeds.construction_type in ("V-A", "V-B", "III-A"):
                wwr = WINDOW_WALL_RATIOS["multifamily_standard"]
            else:
                wwr = WINDOW_WALL_RATIOS.get(
                    "multifamily_standard", 0.20
                )

        d.window_wall_ratio = wwr

        # Use validated deduction sizes to compute opening areas
        avg_win_sf = OPENING_DEDUCTION_SF["window_avg_sf"]  # 15 SF
        avg_door_sf = OPENING_DEDUCTION_SF["door_avg_sf"]   # 20 SF
        d.total_window_area_sf = d.gross_wall_area_sf * wwr * 0.75
        # Windows are ~75% of total openings; doors are ~25%
        d.total_door_area_sf = d.gross_wall_area_sf * wwr * 0.25
        d.total_deductions_sf = d.total_window_area_sf + d.total_door_area_sf
        d.net_wall_area_sf = d.gross_wall_area_sf - d.total_deductions_sf
        d.net_to_gross_ratio = (
            d.net_wall_area_sf / d.gross_wall_area_sf
            if d.gross_wall_area_sf > 0 else 0
        )

        log.append(
            f"WWR: {wwr:.0%} → window area: "
            f"{d.gross_wall_area_sf:.0f} × {wwr:.2f} × 0.75 = "
            f"{d.total_window_area_sf:.0f} SF"
        )
        log.append(
            f"Door area: {d.gross_wall_area_sf:.0f} × {wwr:.2f} × 0.25 = "
            f"{d.total_door_area_sf:.0f} SF"
        )
        log.append(
            f"Net wall: {d.gross_wall_area_sf:.0f} - "
            f"{d.total_deductions_sf:.0f} = {d.net_wall_area_sf:.0f} SF "
            f"(net/gross = {d.net_to_gross_ratio:.0%})"
        )

        # ------------------------------------------------------------------
        # Step 5: WINDOW & DOOR COUNTS
        # ------------------------------------------------------------------
        if seeds.window_count_from_schedule > 0:
            d.window_count = seeds.window_count_from_schedule
            log.append(
                f"Windows: {d.window_count} EA "
                f"(READ from schedule — high confidence)"
            )
        elif seeds.unit_count > 0:
            wpmu = WINDOWS_PER_UNIT.get("average_mix", 6)
            if seeds.unit_mix:
                # Weighted average
                total_windows = sum(
                    count * WINDOWS_PER_UNIT.get(utype, 6)
                    for utype, count in seeds.unit_mix.items()
                )
                d.window_count = round(total_windows)
                log.append(
                    f"Windows: {d.window_count} EA "
                    f"(from unit mix: {seeds.unit_mix})"
                )
            else:
                d.window_count = round(seeds.unit_count * wpmu)
                log.append(
                    f"Windows: {seeds.unit_count} units × "
                    f"{wpmu} windows/unit = {d.window_count} EA"
                )
        else:
            # Estimate from window area / validated deduction size
            d.window_count = round(d.total_window_area_sf / avg_win_sf)
            log.append(
                f"Windows: {d.total_window_area_sf:.0f} SF / "
                f"{avg_win_sf} SF/window = {d.window_count} EA (estimated)"
            )

        # Exterior doors
        if seeds.door_count_from_schedule > 0:
            d.ext_door_count = seeds.door_count_from_schedule
        elif seeds.unit_count > 0:
            d.ext_door_count = round(
                seeds.unit_count * EXT_DOORS_PER_UNIT["entry_door"]
                + seeds.unit_count * EXT_DOORS_PER_UNIT["common_ext_doors_per_unit"]
            )
            log.append(
                f"Ext doors: {d.ext_door_count} EA "
                f"(1 entry/unit + common doors)"
            )

        # Sliding glass doors
        if seeds.unit_count > 0:
            d.sgd_count = round(
                seeds.unit_count * EXT_DOORS_PER_UNIT["balcony_sgd"]
            )
            log.append(f"SGDs: {d.sgd_count} EA (~75% of units)")

        # ------------------------------------------------------------------
        # Step 6: CLADDING QUANTITIES
        # ------------------------------------------------------------------
        if seeds.secondary_cladding and seeds.secondary_cladding_floors:
            # Split cladding between primary and secondary
            try:
                sec_floors = seeds.secondary_cladding_floors.split("-")
                if len(sec_floors) == 2:
                    sec_floor_count = (
                        int(sec_floors[1]) - int(sec_floors[0]) + 1
                    )
                else:
                    sec_floor_count = 1
            except (ValueError, IndexError):
                sec_floor_count = 1

            sec_ratio = sec_floor_count / max(seeds.stories_above_grade, 1)
            d.secondary_cladding_sf = d.net_wall_area_sf * sec_ratio
            d.primary_cladding_sf = d.net_wall_area_sf * (1 - sec_ratio)
            log.append(
                f"Secondary cladding ({seeds.secondary_cladding}): "
                f"floors {seeds.secondary_cladding_floors} = "
                f"{sec_ratio:.0%} of wall → {d.secondary_cladding_sf:.0f} SF"
            )
            log.append(
                f"Primary cladding ({seeds.primary_cladding}): "
                f"remaining {1-sec_ratio:.0%} → {d.primary_cladding_sf:.0f} SF"
            )
        else:
            d.primary_cladding_sf = d.net_wall_area_sf
            log.append(
                f"Cladding: {d.primary_cladding_sf:.0f} SF "
                f"(= net wall area, single cladding type)"
            )

        # WRB / Air Barrier covers the FULL gross wall (under cladding)
        d.wrb_air_barrier_sf = d.gross_wall_area_sf
        d.continuous_insulation_sf = d.gross_wall_area_sf
        d.sheathing_sf = d.gross_wall_area_sf
        log.append(
            f"WRB / Air Barrier: {d.wrb_air_barrier_sf:.0f} SF "
            f"(= gross wall — covers behind all openings)"
        )
        log.append(
            f"Continuous insulation: {d.continuous_insulation_sf:.0f} SF")
        log.append(f"Sheathing: {d.sheathing_sf:.0f} SF")

        # ------------------------------------------------------------------
        # Step 7: ROOF
        # ------------------------------------------------------------------
        from config.trades import get_pitch_multiplier as gpm

        d.roof_area_plan_sf = seeds.footprint_sf  # Plan view = footprint
        d.roof_pitch_multiplier = gpm(seeds.roof_pitch)
        d.roof_area_actual_sf = d.roof_area_plan_sf * d.roof_pitch_multiplier

        # Determine waste factor by roof complexity — validated tiers
        if is_flat:
            d.roof_waste_factor = ROOF_WASTE_FACTORS["flat_membrane"]
        elif seeds.roof_type.lower() in ("hip", "hip shingle"):
            d.roof_waste_factor = ROOF_WASTE_FACTORS["standard_hip"]
        else:
            d.roof_waste_factor = ROOF_WASTE_FACTORS["standard_gable"]
        # Add steep pitch penalty
        if d.roof_pitch_multiplier >= 1.202:  # 8:12 or steeper
            d.roof_waste_factor += ROOF_WASTE_FACTORS["addon_steep_pitch"]

        d.roof_area_with_waste_sf = round(
            d.roof_area_actual_sf * (1 + d.roof_waste_factor)
        )
        log.append(
            f"Roof: {d.roof_area_plan_sf:.0f} SF plan × "
            f"{d.roof_pitch_multiplier:.3f} pitch = "
            f"{d.roof_area_actual_sf:.0f} SF actual"
        )
        log.append(
            f"Roof waste: {d.roof_waste_factor:.0%} → "
            f"{d.roof_area_with_waste_sf:.0f} SF with waste"
        )

        # ------------------------------------------------------------------
        # Step 8: GUTTERS / DRAINAGE — validated spacing rules
        # ------------------------------------------------------------------
        is_flat = seeds.roof_pitch.lower() in ("flat", "0:12", "1/4:12", "")
        if is_flat:
            # Flat roofs typically use internal drains or scuppers
            d.gutter_lf = 0
            d.internal_drain_count = max(
                1, round(d.roof_area_plan_sf / 5000)
            )
            d.scupper_count = max(
                2, round(d.perimeter_lf / 80)
            )
            log.append(
                f"Flat roof drainage: {d.internal_drain_count} internal drains "
                f"+ {d.scupper_count} overflow scuppers (no gutters)"
            )
        else:
            # Pitched roof: gutters along eave edges
            # Gable roofs: eaves on 2 sides (~50%), Hip roofs: all 4 sides (~100%)
            is_hip = seeds.roof_type.lower() in (
                "hip", "hip shingle", "hip metal",
            )
            eave_ratio = (
                GUTTER_RATIOS["hip_eave_ratio"] if is_hip
                else GUTTER_RATIOS["gable_eave_ratio"]
            )
            d.gutter_lf = d.perimeter_lf * eave_ratio
            # Use validated 35 LF spacing, cross-check with roof area method
            ds_by_spacing = round(
                d.gutter_lf / GUTTER_RATIOS["downspout_spacing_lf"]
            )
            ds_by_area = round(
                d.roof_area_actual_sf / GUTTER_RATIOS["downspout_by_roof_sf"]
            )
            d.downspout_count = max(2, max(ds_by_spacing, ds_by_area))
            d.downspout_lf = d.downspout_count * (
                d.total_building_height_ft
                + GUTTER_RATIOS["downspout_height_adder_ft"]
            )
            d.downspout_elbows = (
                d.downspout_count
                * GUTTER_RATIOS["elbow_count_per_downspout"]
            )
            roof_type_label = "hip (all sides)" if is_hip else "gable (eaves)"
            log.append(
                f"Gutters: {d.gutter_lf:.0f} LF "
                f"({roof_type_label}, {eave_ratio:.0%} of perimeter)"
            )
            log.append(
                f"Downspouts: {d.downspout_count} EA "
                f"(max of {ds_by_spacing} by 35 LF spacing, "
                f"{ds_by_area} by roof area) × "
                f"({d.total_building_height_ft:.0f} + 4) ft = "
                f"{d.downspout_lf:.0f} LF total"
            )

        # ------------------------------------------------------------------
        # Step 9: TRIM & ACCESSORIES
        # ------------------------------------------------------------------
        soffit_depth = SOFFIT_DEPTHS.get("typical_residential", 1.5)
        if is_flat:
            soffit_depth = SOFFIT_DEPTHS["commercial_flat"]
        d.soffit_sf = d.perimeter_lf * soffit_depth
        d.fascia_lf = d.perimeter_lf
        d.j_channel_lf = d.net_wall_area_sf * TRIM_RATIOS["j_channel_per_sf"]
        d.corner_trim_lf = (
            d.net_wall_area_sf * TRIM_RATIOS["corner_trim_per_sf"]
        )
        if seeds.stories_above_grade > 1:
            d.band_board_lf = (
                d.perimeter_lf * (seeds.stories_above_grade - 1)
            )
        log.append(
            f"Soffit: {d.soffit_sf:.0f} SF, "
            f"Fascia: {d.fascia_lf:.0f} LF, "
            f"J-Channel: {d.j_channel_lf:.0f} LF, "
            f"Band board: {d.band_board_lf:.0f} LF"
        )

        # ------------------------------------------------------------------
        # Step 10: SEALANT
        # ------------------------------------------------------------------
        d.perimeter_sealant_lf = (
            d.window_count * SEALANT_RATIOS["lf_per_window"]
            + d.ext_door_count * SEALANT_RATIOS["lf_per_door"]
            + d.sgd_count * SEALANT_RATIOS["lf_per_door"]
        )
        d.control_joint_sealant_lf = (
            d.total_building_height_ft
            * (d.perimeter_lf / SEALANT_RATIOS["control_joint_spacing_ft"])
        )
        log.append(
            f"Sealant: {d.perimeter_sealant_lf:.0f} LF perimeter + "
            f"{d.control_joint_sealant_lf:.0f} LF control joints"
        )

        # ------------------------------------------------------------------
        # Step 11: BALCONIES & RAILING
        # ------------------------------------------------------------------
        if seeds.balcony_count > 0:
            d.balcony_count = seeds.balcony_count
        elif seeds.unit_count > 0:
            d.balcony_count = round(
                seeds.unit_count * BALCONY_RATIOS["pct_units_with_balcony"]
            )
        d.balcony_waterproofing_sf = d.balcony_count * seeds.avg_balcony_sf
        d.balcony_railing_lf = (
            d.balcony_count * BALCONY_RATIOS["avg_railing_lf_per_balcony"]
        )
        log.append(
            f"Balconies: {d.balcony_count} EA × "
            f"{seeds.avg_balcony_sf:.0f} SF = "
            f"{d.balcony_waterproofing_sf:.0f} SF waterproofing, "
            f"{d.balcony_railing_lf:.0f} LF railing"
        )

        # Corridor railing (breezeway style)
        if seeds.corridor_type == "exterior_breezeway":
            corridor_lf_per_floor = d.perimeter_lf * 0.3  # ~30% is corridor
            d.corridor_railing_lf = (
                corridor_lf_per_floor * seeds.stories_above_grade
            )
            log.append(
                f"Corridor railing: {d.corridor_railing_lf:.0f} LF "
                f"(breezeway style)"
            )

        # ------------------------------------------------------------------
        # Step 12: WATERPROOFING
        # ------------------------------------------------------------------
        d.foundation_waterproofing_sf = (
            d.perimeter_lf * WATERPROOFING_RATIOS["foundation_depth_ft"]
        )
        if seeds.has_podium:
            d.podium_waterproofing_sf = seeds.footprint_sf
            log.append(
                f"Podium waterproofing: {d.podium_waterproofing_sf:.0f} SF "
                f"(= footprint)"
            )
        log.append(
            f"Foundation WP: {d.foundation_waterproofing_sf:.0f} SF "
            f"({d.perimeter_lf:.0f} LF × "
            f"{WATERPROOFING_RATIOS['foundation_depth_ft']} ft)"
        )

        return d

    def generate_schedule_of_values(
        self,
        seeds: SeedValues,
        derived: DerivedQuantities,
        unit_prices: Optional[dict] = None,
    ) -> BuildingScheduleOfValues:
        """Generate AIA G703 Schedule of Values for one building.

        Breaks down the envelope scope into CSI-organized line items
        per building, as required for commercial multifamily pay applications.
        """
        prices = unit_prices or {}
        items = []
        item_num = 1

        def add(desc, csi, qty, unit, default_price=0):
            nonlocal item_num
            up = prices.get(desc, default_price)
            items.append(ScheduleOfValuesItem(
                item_number=str(item_num).zfill(3),
                description=f"{seeds.building_id} — {desc}",
                csi_division=csi,
                quantity=round(qty, 1),
                unit=unit,
                unit_price=up,
                scheduled_value=round(qty * up, 2),
            ))
            item_num += 1

        # Division 06 — Sheathing
        add("Exterior Sheathing", "06 16 00",
            derived.sheathing_sf, "SF", 2.50)

        # Division 07 — Thermal & Moisture
        add("Weather-Resistive Barrier / Air Barrier", "07 27 00",
            derived.wrb_air_barrier_sf, "SF", 1.85)
        add("Continuous Insulation (rigid)", "07 21 13",
            derived.continuous_insulation_sf, "SF", 2.10)
        add(f"Primary Cladding — {seeds.primary_cladding}", "07 46 00",
            derived.primary_cladding_sf, "SF", 8.50)
        if derived.secondary_cladding_sf > 0:
            add(f"Accent Cladding — {seeds.secondary_cladding}", "07 46 00",
                derived.secondary_cladding_sf, "SF", 12.00)
        add("Soffit", "07 46 00", derived.soffit_sf, "SF", 6.00)
        add("Fascia", "07 46 00", derived.fascia_lf, "LF", 8.00)
        add("J-Channel & Starter", "07 46 00",
            derived.j_channel_lf, "LF", 2.50)
        add("Corner Trim", "07 46 00", derived.corner_trim_lf, "LF", 4.00)
        if derived.band_board_lf > 0:
            add("Band Board / Floor Line Transition", "07 46 00",
                derived.band_board_lf, "LF", 6.50)

        # Roofing
        roof_sq = derived.roof_area_actual_sf / 100.0
        add(f"Roofing — {seeds.roof_type}", "07 54 00",
            roof_sq, "SQ", 350.00)
        add("Roof Insulation", "07 21 13",
            derived.roof_area_plan_sf, "SF", 2.80)
        if derived.coping_lf > 0:
            add("Metal Coping", "07 71 00", derived.coping_lf, "LF", 22.00)

        # Flashing
        add("Flashing & Sheet Metal", "07 62 00",
            derived.perimeter_lf * 0.5, "LF", 12.00)

        # Gutters / Drainage
        if derived.gutter_lf > 0:
            add("Gutters", "07 63 00", derived.gutter_lf, "LF", 8.50)
            add("Downspouts", "07 63 00", derived.downspout_lf, "LF", 6.00)
        if derived.internal_drain_count > 0:
            add("Internal Roof Drains", "07 63 00",
                derived.internal_drain_count, "EA", 850.00)
        if derived.scupper_count > 0:
            add("Overflow Scuppers", "07 63 00",
                derived.scupper_count, "EA", 350.00)

        # Joint Sealants
        add("Perimeter Sealant (windows/doors)", "07 92 00",
            derived.perimeter_sealant_lf, "LF", 3.50)
        add("Control Joint Sealant", "07 92 00",
            derived.control_joint_sealant_lf, "LF", 4.00)

        # Waterproofing
        if derived.balcony_waterproofing_sf > 0:
            add("Balcony Deck Waterproofing", "07 14 00",
                derived.balcony_waterproofing_sf, "SF", 8.00)
        add("Foundation Dampproofing", "07 11 00",
            derived.foundation_waterproofing_sf, "SF", 3.00)
        if derived.podium_waterproofing_sf > 0:
            add("Podium Deck Waterproofing", "07 13 00",
                derived.podium_waterproofing_sf, "SF", 12.00)

        # Division 08 — Openings
        add("Windows (supply & install)", "08 51 00",
            derived.window_count, "EA", 450.00)
        add("Sliding Glass Doors", "08 51 00",
            derived.sgd_count, "EA", 1200.00)
        add("Exterior Doors", "08 11 00",
            derived.ext_door_count, "EA", 850.00)

        # Railing
        if derived.balcony_railing_lf > 0:
            add("Balcony Railing", "05 73 00",
                derived.balcony_railing_lf, "LF", 85.00)
        if derived.corridor_railing_lf > 0:
            add("Corridor / Breezeway Railing", "05 52 00",
                derived.corridor_railing_lf, "LF", 75.00)

        total = sum(i.scheduled_value for i in items)

        return BuildingScheduleOfValues(
            building_id=seeds.building_id,
            items=items,
            total_value=round(total, 2),
        )
