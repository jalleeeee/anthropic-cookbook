"""
Commercial Multifamily Takeoff Template

Defines the project template, building types, envelope assemblies, and
enhanced AI prompts for commercial multifamily construction takeoffs.

Aligned with:
- CSI MasterFormat Divisions 04-09 (envelope trades)
- DDC CWICR resource-based cost methodology (rate_code → resource breakdown)
- Standard commercial multifamily construction practices

Building Types Supported:
- Type V-A/V-B  — Wood-frame, 3-4 story
- Type III-A/B  — Wood over podium, 4-5 story (1+4, 1+5)
- Type I/II     — Steel/concrete frame, 5+ story
"""

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Building classification
# ---------------------------------------------------------------------------

class ConstructionType(Enum):
    TYPE_V_A = "V-A"        # Wood frame, sprinklered, 3-4 stories
    TYPE_V_B = "V-B"        # Wood frame, 3 stories max
    TYPE_III_A = "III-A"    # Wood over podium (concrete 1st floor)
    TYPE_III_B = "III-B"    # Mixed, noncombustible + combustible
    TYPE_II_A = "II-A"      # Steel frame, sprinklered
    TYPE_II_B = "II-B"      # Steel frame
    TYPE_I_A = "I-A"        # Fire-resistive (high rise)


class RoofSystem(Enum):
    TPO_SINGLE_PLY = "tpo_single_ply"
    PVC_SINGLE_PLY = "pvc_single_ply"
    EPDM_SINGLE_PLY = "epdm_single_ply"
    MODIFIED_BITUMEN = "mod_bit"
    BUILT_UP = "built_up"
    STEEP_SLOPE_SHINGLE = "steep_slope_shingle"
    STANDING_SEAM_METAL = "standing_seam_metal"


class CladdingSystem(Enum):
    FIBER_CEMENT_LAP = "fiber_cement_lap"
    FIBER_CEMENT_PANEL = "fiber_cement_panel"
    VINYL_SIDING = "vinyl_siding"
    METAL_PANEL = "metal_panel"
    STUCCO_EIFS = "stucco_eifs"
    BRICK_VENEER = "brick_veneer"
    STONE_VENEER = "stone_veneer"
    COMPOSITE_PANEL = "composite_panel"
    MIXED_CLADDING = "mixed_cladding"


# ---------------------------------------------------------------------------
# Multifamily-specific envelope components
# ---------------------------------------------------------------------------

@dataclass
class ElevationZone:
    """A distinct zone on one elevation face with its own cladding/treatment."""
    name: str                  # e.g., "Ground floor retail", "Upper floors"
    floor_range: str           # e.g., "1", "2-5"
    cladding_type: str         # e.g., "brick_veneer", "fiber_cement_lap"
    area_sf: float = 0.0
    perimeter_lf: float = 0.0
    notes: str = ""


@dataclass
class BuildingDefinition:
    """A single building within a multifamily project."""
    building_id: str             # e.g., "Bldg-A", "Building 1"
    building_name: str           # e.g., "The Aspen"
    construction_type: str       # V-A, III-A, etc.
    stories_above_grade: int = 0
    stories_below_grade: int = 0
    has_podium: bool = False     # Concrete podium (Type III over I)
    unit_count: int = 0          # Residential units
    footprint_sf: float = 0.0
    perimeter_lf: float = 0.0
    building_height_ft: float = 0.0
    floor_to_floor_ft: float = 0.0
    gross_wall_area_sf: float = 0.0
    roof_area_plan_sf: float = 0.0
    roof_system: str = ""
    primary_cladding: str = ""
    secondary_cladding: str = ""
    elevation_zones: list[ElevationZone] = field(default_factory=list)
    notes: str = ""


@dataclass
class MultifamilyProject:
    """Top-level commercial multifamily project definition."""
    project_name: str
    project_address: str = ""
    buildings: list[BuildingDefinition] = field(default_factory=list)
    total_units: int = 0
    total_buildings: int = 0
    site_amenities: list[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# CSI MasterFormat mapping for envelope trades
# ---------------------------------------------------------------------------

CSI_ENVELOPE_DIVISIONS = {
    # Division 04 — Masonry
    "04 21 13": "Brick Masonry Veneer",
    "04 22 00": "Concrete Unit Masonry",
    "04 43 00": "Stone Masonry Veneer",
    "04 72 00": "Cast Stone",

    # Division 05 — Metals
    "05 40 00": "Cold-Formed Metal Framing",
    "05 50 00": "Metal Fabrications (lintels, shelf angles, relieving angles)",
    "05 52 00": "Metal Railings",
    "05 73 00": "Decorative Metal Balcony Railings",

    # Division 06 — Wood, Plastics, Composites
    "06 10 00": "Rough Carpentry (wall sheathing, blocking, nailers)",
    "06 16 00": "Exterior Sheathing",
    "06 20 00": "Finish Carpentry (exterior trim)",

    # Division 07 — Thermal and Moisture Protection (PRIMARY)
    "07 10 00": "Dampproofing and Waterproofing",
    "07 11 00": "Dampproofing (foundation walls)",
    "07 12 00": "Built-Up Bituminous Waterproofing",
    "07 13 00": "Sheet Waterproofing (balcony decks, podium)",
    "07 14 00": "Fluid-Applied Waterproofing",
    "07 21 00": "Thermal Insulation (batt, rigid, spray foam)",
    "07 21 13": "Board Insulation (rigid polyiso, XPS, EPS)",
    "07 21 16": "Blanket Insulation (batt, mineral wool)",
    "07 21 29": "Sprayed Insulation",
    "07 25 00": "Weather Barriers (WRB, house wrap, air barriers)",
    "07 25 10": "Self-Adhered Air/Vapor Barrier",
    "07 25 20": "Fluid-Applied Air Barrier",
    "07 26 00": "Vapor Retarders",
    "07 27 00": "Air Barriers (sheet, self-adhered, fluid-applied)",
    "07 31 00": "Asphalt Shingles",
    "07 41 00": "Roof Panels (standing seam metal)",
    "07 42 00": "Wall Panels (metal wall panels, ACM)",
    "07 46 00": "Siding (fiber cement, wood, vinyl, composite)",
    "07 46 23": "Fiber Cement Siding",
    "07 46 33": "Vinyl Siding",
    "07 46 46": "Composite Siding",
    "07 50 00": "Membrane Roofing",
    "07 52 00": "Modified Bitumen Membrane Roofing",
    "07 54 00": "Thermoplastic Membrane Roofing (TPO)",
    "07 55 00": "Thermoset Membrane Roofing (EPDM)",
    "07 60 00": "Flashing and Sheet Metal",
    "07 62 00": "Sheet Metal Flashing and Trim",
    "07 63 00": "Sheet Metal Roofing Specialties",
    "07 71 00": "Roof Specialties (copings, gravel stops, fascias)",
    "07 72 00": "Roof Accessories (hatches, vents, curbs)",
    "07 84 00": "Firestopping (rated wall penetrations)",
    "07 90 00": "Joint Sealants (caulking, backer rod, expansion joints)",
    "07 92 00": "Joint Sealants",

    # Division 08 — Openings
    "08 11 00": "Metal Doors and Frames",
    "08 14 00": "Wood Doors",
    "08 41 00": "Entrances and Storefronts",
    "08 43 00": "Curtain Wall (if applicable)",
    "08 51 00": "Aluminum Windows",
    "08 52 00": "Wood Windows",
    "08 53 00": "Vinyl Windows",
    "08 61 00": "Roof Windows and Skylights",
    "08 71 00": "Door Hardware",
    "08 80 00": "Glazing",

    # Division 09 — Finishes (exterior)
    "09 24 00": "Exterior Portland Cement Plastering (stucco)",
    "09 26 00": "Veneer Plastering",
    "09 91 00": "Painting (exterior)",
}


# ---------------------------------------------------------------------------
# DDC CWICR field mapping
# ---------------------------------------------------------------------------

DDC_CWICR_FIELD_GROUPS = {
    "classification": [
        "category_type", "collection_code", "collection_name",
        "department_code", "department_name", "department_type",
        "section_name", "section_type", "subsection_code", "subsection_name",
    ],
    "work_item": [
        "rate_code", "rate_original_name", "rate_final_name", "rate_unit",
        "row_type", "is_scope", "is_abstract", "is_machine", "is_labor",
        "is_material", "work_composition_text",
    ],
    "resource": [
        "resource_code", "resource_name", "resource_unit",
        "resource_quantity", "resource_price_per_unit_eur_current",
        "resource_cost_eur",
    ],
    "labor": [
        "workers_count", "engineers_count", "machinists_count",
        "labor_hours", "labor_cost",
    ],
    "machinery": [
        "machine_class", "personnel_codes", "wages",
        "relocation_costs", "electricity_consumption",
        "total_machinery_value",
    ],
}


# ---------------------------------------------------------------------------
# Commercial multifamily envelope components (extended from base trades)
# ---------------------------------------------------------------------------

MULTIFAMILY_ENVELOPE_COMPONENTS = {
    "exterior_wall_assembly": {
        "csi_division": "07",
        "components": [
            {"name": "Exterior Sheathing (OSB/plywood)", "unit": "SF", "waste": 0.08, "csi": "06 16 00"},
            {"name": "Weather-Resistive Barrier (WRB)", "unit": "SF", "waste": 0.10, "csi": "07 25 00"},
            {"name": "Air Barrier (self-adhered or fluid-applied)", "unit": "SF", "waste": 0.10, "csi": "07 27 00"},
            {"name": "Continuous Insulation (rigid CI)", "unit": "SF", "waste": 0.05, "csi": "07 21 13"},
            {"name": "Rainscreen Furring / Hat Channel", "unit": "SF", "waste": 0.05, "csi": "07 42 00"},
            {"name": "Primary Cladding Material", "unit": "SF", "waste": 0.10, "csi": "07 46 00"},
            {"name": "Secondary/Accent Cladding", "unit": "SF", "waste": 0.12, "csi": "07 46 00"},
            {"name": "J-Channel and Starter Strip", "unit": "LF", "waste": 0.05, "csi": "07 46 00"},
            {"name": "Corner Trim (inside + outside)", "unit": "LF", "waste": 0.05, "csi": "07 46 00"},
            {"name": "Window/Door Trim and Casing", "unit": "LF", "waste": 0.08, "csi": "06 20 00"},
            {"name": "Soffit (vented + non-vented)", "unit": "SF", "waste": 0.08, "csi": "07 46 00"},
            {"name": "Fascia Board/Panel", "unit": "LF", "waste": 0.05, "csi": "07 46 00"},
            {"name": "Band/Belly Board (floor line transition)", "unit": "LF", "waste": 0.05, "csi": "07 46 00"},
        ],
    },
    "roofing_assembly": {
        "csi_division": "07",
        "components": [
            {"name": "Roof Membrane (TPO/PVC/EPDM)", "unit": "SQ", "waste": 0.10, "csi": "07 54 00", "pitch_adjusted": False},
            {"name": "Steep-Slope Shingles", "unit": "SQ", "waste": 0.12, "csi": "07 31 00", "pitch_adjusted": True},
            {"name": "Standing Seam Metal Roof", "unit": "SQ", "waste": 0.08, "csi": "07 41 00", "pitch_adjusted": True},
            {"name": "Roof Insulation (polyiso tapered)", "unit": "SF", "waste": 0.05, "csi": "07 21 13"},
            {"name": "Cover Board", "unit": "SF", "waste": 0.05, "csi": "07 21 13"},
            {"name": "Vapor Barrier/Retarder", "unit": "SF", "waste": 0.10, "csi": "07 26 00"},
            {"name": "Underlayment (ice & water + synthetic)", "unit": "SF", "waste": 0.10, "csi": "07 25 00", "pitch_adjusted": True},
            {"name": "Metal Coping", "unit": "LF", "waste": 0.05, "csi": "07 71 00"},
            {"name": "Edge Metal / Gravel Stop", "unit": "LF", "waste": 0.05, "csi": "07 71 00"},
            {"name": "Drip Edge", "unit": "LF", "waste": 0.05, "csi": "07 62 00"},
            {"name": "Ridge Cap", "unit": "LF", "waste": 0.05, "csi": "07 62 00"},
            {"name": "Valley Flashing", "unit": "LF", "waste": 0.10, "csi": "07 62 00"},
            {"name": "Step Flashing (at walls)", "unit": "LF", "waste": 0.10, "csi": "07 62 00"},
            {"name": "Counterflashing / Through-Wall Flashing", "unit": "LF", "waste": 0.10, "csi": "07 62 00"},
            {"name": "Pipe/Vent Boots", "unit": "EA", "waste": 0.0, "csi": "07 72 00"},
            {"name": "Roof Curbs (HVAC)", "unit": "EA", "waste": 0.0, "csi": "07 72 00"},
        ],
    },
    "gutters_downspouts": {
        "csi_division": "07",
        "components": [
            {"name": "Gutters (K-style or half-round)", "unit": "LF", "waste": 0.05, "csi": "07 63 00"},
            {"name": "Gutter Guards/Screens", "unit": "LF", "waste": 0.05, "csi": "07 63 00"},
            {"name": "Downspouts", "unit": "LF", "waste": 0.05, "csi": "07 63 00"},
            {"name": "Downspout Elbows", "unit": "EA", "waste": 0.0, "csi": "07 63 00"},
            {"name": "Downspout Boots/Splash Blocks", "unit": "EA", "waste": 0.0, "csi": "07 63 00"},
            {"name": "Scupper Boxes (flat roof drainage)", "unit": "EA", "waste": 0.0, "csi": "07 63 00"},
            {"name": "Internal Roof Drains", "unit": "EA", "waste": 0.0, "csi": "07 63 00"},
        ],
    },
    "fenestration": {
        "csi_division": "08",
        "components": [
            {"name": "Windows (by type from schedule)", "unit": "EA", "waste": 0.0, "csi": "08 51 00"},
            {"name": "Sliding Glass Doors / Patio Doors", "unit": "EA", "waste": 0.0, "csi": "08 51 00"},
            {"name": "Storefront System (ground floor)", "unit": "SF", "waste": 0.05, "csi": "08 41 00"},
            {"name": "Unit Entry Doors", "unit": "EA", "waste": 0.0, "csi": "08 14 00"},
            {"name": "Exterior Doors (lobby, service, fire exit)", "unit": "EA", "waste": 0.0, "csi": "08 11 00"},
            {"name": "Garage Overhead Doors", "unit": "EA", "waste": 0.0, "csi": "08 33 00"},
            {"name": "Window Flashing (pan + jamb + head)", "unit": "LF", "waste": 0.10, "csi": "07 62 00"},
            {"name": "Window/Door Sealant (backer rod + caulk)", "unit": "LF", "waste": 0.10, "csi": "07 92 00"},
            {"name": "Door Hardware Sets", "unit": "SET", "waste": 0.0, "csi": "08 71 00"},
        ],
    },
    "waterproofing_moisture": {
        "csi_division": "07",
        "components": [
            {"name": "Foundation Dampproofing", "unit": "SF", "waste": 0.10, "csi": "07 11 00"},
            {"name": "Below-Grade Waterproofing Membrane", "unit": "SF", "waste": 0.10, "csi": "07 13 00"},
            {"name": "Balcony/Deck Waterproofing (sheet or fluid)", "unit": "SF", "waste": 0.10, "csi": "07 14 00"},
            {"name": "Podium Deck Waterproofing", "unit": "SF", "waste": 0.10, "csi": "07 13 00"},
            {"name": "Shower Pan Liner (per unit)", "unit": "EA", "waste": 0.0, "csi": "07 14 00"},
            {"name": "Through-Wall Flashing (masonry)", "unit": "LF", "waste": 0.10, "csi": "07 62 00"},
            {"name": "Expansion Joint Covers", "unit": "LF", "waste": 0.05, "csi": "07 90 00"},
        ],
    },
    "balcony_deck_railing": {
        "csi_division": "05/07",
        "components": [
            {"name": "Balcony Decking (composite/wood/concrete)", "unit": "SF", "waste": 0.10, "csi": "06 73 00"},
            {"name": "Balcony Railing Systems", "unit": "LF", "waste": 0.05, "csi": "05 73 00"},
            {"name": "Railing Posts", "unit": "EA", "waste": 0.0, "csi": "05 73 00"},
            {"name": "Breezeway/Corridor Railing", "unit": "LF", "waste": 0.05, "csi": "05 52 00"},
            {"name": "Stair Railing (exterior)", "unit": "LF", "waste": 0.05, "csi": "05 52 00"},
        ],
    },
    "joint_sealants": {
        "csi_division": "07",
        "components": [
            {"name": "Perimeter Sealant (window/door)", "unit": "LF", "waste": 0.10, "csi": "07 92 00"},
            {"name": "Control Joint Sealant", "unit": "LF", "waste": 0.10, "csi": "07 92 00"},
            {"name": "Expansion Joint Sealant", "unit": "LF", "waste": 0.10, "csi": "07 92 00"},
            {"name": "Cladding-to-Cladding Transition Sealant", "unit": "LF", "waste": 0.10, "csi": "07 92 00"},
            {"name": "Firestopping (rated wall penetrations)", "unit": "EA", "waste": 0.0, "csi": "07 84 00"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Multifamily-specific productivity and crew data
# ---------------------------------------------------------------------------

MULTIFAMILY_CREW_DATA = {
    "fiber_cement_siding": {
        "crew_size": 4,
        "daily_output_sf": 480,
        "unit_labor_hours_per_sf": 0.067,
        "notes": "4-person crew: 2 carpenters + 2 laborers",
    },
    "vinyl_siding": {
        "crew_size": 3,
        "daily_output_sf": 640,
        "unit_labor_hours_per_sf": 0.038,
        "notes": "3-person crew: 2 installers + 1 laborer",
    },
    "tpo_roofing": {
        "crew_size": 5,
        "daily_output_sq": 20,
        "unit_labor_hours_per_sq": 2.0,
        "notes": "5-person crew: 2 roofers + 2 helpers + 1 foreman",
    },
    "shingle_roofing": {
        "crew_size": 5,
        "daily_output_sq": 25,
        "unit_labor_hours_per_sq": 1.6,
        "notes": "5-person crew including 1 foreman",
    },
    "gutters_aluminum": {
        "crew_size": 2,
        "daily_output_lf": 200,
        "unit_labor_hours_per_lf": 0.08,
        "notes": "2-person crew with machine",
    },
    "windows_install": {
        "crew_size": 2,
        "daily_output_ea": 8,
        "unit_labor_hours_per_ea": 2.0,
        "notes": "2 carpenters per window, includes flashing",
    },
    "air_barrier_self_adhered": {
        "crew_size": 3,
        "daily_output_sf": 800,
        "unit_labor_hours_per_sf": 0.030,
        "notes": "3-person crew: 1 mechanic + 2 helpers",
    },
    "metal_coping": {
        "crew_size": 2,
        "daily_output_lf": 120,
        "unit_labor_hours_per_lf": 0.133,
        "notes": "2 sheet metal workers",
    },
    "balcony_railing": {
        "crew_size": 3,
        "daily_output_lf": 60,
        "unit_labor_hours_per_lf": 0.40,
        "notes": "3-person crew: 2 ironworkers + 1 helper",
    },
}


# ---------------------------------------------------------------------------
# STEP 0: Document Review & Scope Identification
# (Based on Dagostino & Feigenbaum, "Estimating in Building Construction")
# ---------------------------------------------------------------------------

DOCUMENT_REVIEW_PROMPT = """You are a senior construction estimator performing the INITIAL DOCUMENT REVIEW
before starting a quantity takeoff. This is the most critical step — you must understand the
project before you measure anything.

Based on Dagostino & Feigenbaum's methodology, answer EVERY question below by reading
the drawings. If you cannot determine an answer, write "NOT FOUND — need RFI".

## ARCHITECTURAL DRAWINGS REVIEW

1. **Building Footprint:** What shape is the building footprint? How many total SF?
2. **Architect's Area:** Is the architect's number for building area correct? Is the
   architect measuring from the inside corner of the building, and counting balconies in or out?
3. **Floors:** How many floors are planned, and what is on each floor?
   What is the SF for each floor?
4. **Floor-to-Floor:** What is the distance from floor to floor, and from floor to ceiling?
5. **Perimeter:** What is the building perimeter on each floor?
   (Note: upper floors may have different perimeters due to setbacks)
6. **Exterior Walls:** How high is the exterior wall, and what is it made of?
   Note EVERY cladding type visible (siding, brick, stone, stucco, metal panel, etc.)
   and which floors/zones each covers.
7. **Exterior Finish Materials:** What are the principal exterior finish materials?
   List every material visible on elevations.
8. **Windows & Doors:** What types of doors and windows are planned?
   Is there a window schedule? Door schedule? Count totals if visible.
9. **Roof Systems:** What types of roof systems are specified?
   (shingle, TPO, metal, built-up, etc.) What is the pitch?
10. **Building Projections:** Are there balconies, canopies, walkways, soffits, parapets?
    Count them and estimate sizes.
11. **Multiple Buildings:** Are there multiple buildings? How many?
    Are they identical or different? Identify each building.

## PROJECT SCOPE QUICK CHECKLIST

Check all that apply based on what you see in the drawings:

**Lower Floor:** [ ] Concrete [ ] Basement [ ] Crawl space [ ] Slab-on-grade
**Upper Floors:** [ ] Wood framed [ ] Steel deck [ ] Suspended concrete [ ] Hollow core
**Roof Structure:** [ ] Wood framing/truss [ ] Steel deck [ ] Precast concrete [ ] Steel joists
**Exterior Walls:** [ ] Siding [ ] Stone [ ] Block [ ] Brick [ ] Stucco [ ] Concrete [ ] Metal Panel [ ] EIFS [ ] Trims
**Exterior Openings:** [ ] Curtain wall [ ] Storefront [ ] Windows [ ] Doors
**Roof Finish:** [ ] Shingle [ ] Built up [ ] Single ply [ ] Metal [ ] Standing seam
**Building Projections:** [ ] Soffit [ ] Balcony [ ] Patio [ ] Parapet [ ] Canopy [ ] Sidewalk [ ] Breezeway

Return a JSON object:
{{
  "document_review": {{
    "building_footprint_shape": "",
    "total_building_sf": 0,
    "architect_area_correct": true,
    "floors": [
      {{"floor": 1, "description": "", "sf": 0}},
      {{"floor": 2, "description": "", "sf": 0}}
    ],
    "floor_to_floor_ft": 0,
    "floor_to_ceiling_ft": 0,
    "perimeter_lf": 0,
    "perimeter_varies_by_floor": false,
    "exterior_wall_height_ft": 0,
    "exterior_wall_materials": [
      {{"material": "", "location": "", "floors": "", "approx_pct": 0}}
    ],
    "window_schedule_found": false,
    "window_count_total": 0,
    "door_schedule_found": false,
    "ext_door_count_total": 0,
    "roof_system": "",
    "roof_pitch": "",
    "balcony_count": 0,
    "has_parapet": false,
    "parapet_height_ft": 0,
    "building_count": 1,
    "buildings_identical": true,
    "building_ids": []
  }},
  "scope_checklist": {{
    "lower_floor": "",
    "upper_floors": "",
    "roof_structure": "",
    "exterior_walls": [],
    "exterior_openings": [],
    "roof_finish": "",
    "building_projections": []
  }},
  "seed_values_extracted": {{
    "footprint_sf": 0,
    "stories_above_grade": 0,
    "perimeter_lf": 0,
    "floor_to_floor_ft": 0,
    "total_building_height_ft": 0,
    "parapet_height_ft": 0,
    "unit_count": 0,
    "roof_pitch": "",
    "primary_cladding": "",
    "secondary_cladding": "",
    "secondary_cladding_floors": "",
    "window_count": 0,
    "balcony_count": 0
  }},
  "rfi_needed": [],
  "notes": ""
}}

CRITICAL: The "seed_values_extracted" section feeds directly into the deductive
ratio engine. Extract LABELED DIMENSIONS from the plans — do not measure pixels.
Read the numbers that the architect already calculated.
Return ONLY the JSON object."""


# ---------------------------------------------------------------------------
# Enhanced AI prompts for commercial multifamily takeoffs
# ---------------------------------------------------------------------------

MULTIFAMILY_SHEET_ID_PROMPT = """You are a senior commercial construction estimator reviewing architectural
drawings for a MULTIFAMILY residential project (apartments, condos, townhomes).

Analyze these construction drawing pages. For each page, identify:

1. **Sheet ID** (e.g., A-201, A-301, A-501, S-101)
2. **Sheet type** — one of:
   [elevation, roof_plan, floor_plan, unit_plan, section, wall_section,
    detail, window_schedule, door_schedule, finish_schedule,
    enlarged_plan, site_plan, general_notes, cover_sheet, life_safety]
3. **Sheet title** as shown in the title block
4. **Drawing scale** if visible (e.g., 1/4" = 1'-0")
5. **Building reference** — which building(s) does this sheet apply to?
   (e.g., "Building A", "All Buildings", "Typical Unit")
6. **Which envelope trades** are shown: {trade_names}

MULTIFAMILY-SPECIFIC GUIDANCE:
- Look for BUILDING IDENTIFIERS in the title block (Bldg A, Phase 1, etc.)
- Typical unit plans show REPEATING layouts — note the unit type (1BR, 2BR, etc.)
- Enlarged plans often show stair towers, corridors, balcony details
- Elevations may show DIFFERENT CLADDING ZONES (e.g., brick on lower 2 floors,
  fiber cement on upper floors) — note these transitions
- Section cuts through corridor/breezeway show wall assembly layers
- Look for PODIUM LEVEL distinction (concrete vs wood-frame floors above)

Return a JSON array:
[
  {{
    "page_number": 1,
    "sheet_id": "A-201",
    "sheet_type": "elevation",
    "title": "Building A — North & East Elevations",
    "scale": "1/8\\" = 1'-0\\"",
    "building_ref": "Building A",
    "relevant_trades": ["Siding", "Windows", "Gutters"],
    "cladding_zones_noted": ["brick veneer floors 1-2", "fiber cement floors 3-5"],
    "notes": ""
  }}
]

Only include pages with architectural drawings relevant to envelope trades.
Skip MEP sheets, structural-only sheets (unless showing wall sections),
interior-only finish sheets, and landscape plans.
Return ONLY the JSON array."""


MULTIFAMILY_BUILDING_DIMS_PROMPT = """You are a senior commercial estimator extracting building dimensions
from a MULTIFAMILY RESIDENTIAL project. These drawings may show MULTIPLE
BUILDINGS. Extract dimensions for EACH building separately.

CRITICAL INSTRUCTIONS:
- Read the DRAWING SCALE from the title block and use it for ALL measurements
- For EACH building, calculate dimensions independently
- Multifamily buildings are often RECTANGULAR or L/U/T-SHAPED — measure
  the full perimeter including all jogs, notches, and setbacks
- Count STORIES carefully: note if there's a podium (concrete ground floor)
  with wood-frame floors above (e.g., "1+4" = 5 stories, podium + 4 wood)
- FLOOR-TO-FLOOR height is typically 9'-4" to 10'-0" for residential floors,
  12'-0" to 14'-0" for ground-floor retail/podium
- Gross wall area = perimeter × total building height (NOT per-story height × stories,
  because ground floor may be taller than upper floors)
- PARAPET: commercial flat roofs almost always have a parapet wall (2'-6" to 4'-0"
  above roof line) — measure the parapet perimeter separately
- Note any ELEVATION SETBACKS where upper floors step back from lower floors

Return a JSON object:
{{
  "buildings": [
    {{
      "building_id": "Building A",
      "footprint_sf": 0,
      "footprint_length_ft": 0,
      "footprint_width_ft": 0,
      "perimeter_lf": 0,
      "stories_above_grade": 0,
      "stories_below_grade": 0,
      "has_podium": false,
      "podium_height_ft": 0,
      "typical_floor_height_ft": 0,
      "total_building_height_ft": 0,
      "gross_wall_area_sf": 0,
      "parapet_height_ft": 0,
      "parapet_perimeter_lf": 0,
      "roof_area_plan_sf": 0,
      "roof_pitch": "flat",
      "roof_type": "TPO membrane",
      "balcony_count": 0,
      "balcony_avg_sf": 0,
      "corridor_type": "interior",
      "unit_count_estimate": 0,
      "notes": ""
    }}
  ],
  "site_totals": {{
    "total_buildings": 0,
    "total_units": 0,
    "total_gross_wall_sf": 0,
    "total_roof_sf": 0
  }},
  "notes": ""
}}

IMPORTANT:
- If you can only identify ONE building, still use the "buildings" array
- For wall area: account for ground floor being taller if there's retail/podium
- Note cladding transitions (e.g., "brick floors 1-2, siding floors 3-5")
- Count balconies visible on elevations — they affect railing and waterproofing quantities
- corridor_type: "interior" (enclosed), "exterior_breezeway" (open-air), or "single_loaded"
- Return ONLY the JSON object"""


MULTIFAMILY_TRADE_MEASUREMENT_PROMPT = """You are an expert commercial construction estimator specializing in the
BUILDING ENVELOPE for multifamily residential projects. Analyze these
drawings for the **{trade_name}** trade.

PROJECT CONTEXT:
{building_context}

Components to measure:
{component_desc}

MULTIFAMILY MEASUREMENT RULES:

**For SIDING / CLADDING (SF):**
- Measure EACH ELEVATION FACE separately (North, South, East, West)
- For each face: gross area = face width × building height
- DEDUCT all window and door openings from gross area to get NET cladding area
- If multiple cladding types on one face (e.g., brick lower + siding upper),
  measure EACH ZONE separately and note the cladding type
- Include GABLE ENDS above the eave line for pitched-roof buildings
- Include PARAPET WALLS (interior AND exterior faces if both are clad)
- Do NOT include areas covered by storefront or curtain wall systems in siding qty

**For ROOFING (SQ = 100 SF):**
- Flat roofs: measure plan-view area (footprint of roof)
- Pitched roofs: multiply plan-view area by pitch multiplier
- Include all ROOF LEVELS (main roof, lower roofs over porches/entries,
  canopies over walkways)
- Note PENETRATIONS: count HVAC curbs, vents, pipes for flashing quantities

**For WINDOWS (EA):**
- Count from WINDOW SCHEDULE if available (preferred — most accurate)
- Cross-reference schedule counts against ELEVATIONS to verify
- Note each window TYPE, SIZE (W×H), and QUANTITY separately
- For multifamily: window count = (windows per typical unit × unit count)
  + corridor windows + stairwell windows + lobby/amenity windows
- Sliding glass doors / patio doors are counted separately

**For GUTTERS / DOWNSPOUTS (LF):**
- Gutters run along ALL eave edges (for pitched roofs)
- For flat roofs with parapets: likely INTERNAL DRAINS or SCUPPERS instead
- Downspouts: typically every 40-50 LF of gutter run, calculate count
- Measure total downspout run: count × (building height + 2 ft for elbows)

**For WATERPROOFING:**
- Balcony decks: count × average SF per balcony
- Podium deck: full podium roof area where occupied space is below
- Foundation: perimeter × below-grade wall height

**For RAILING (LF):**
- Balcony railings: count balconies × average railing run per balcony
- Corridor/breezeway railings: corridor length × number of open-corridor floors
- Stair railings: stair count × (building height / floor height × stair run per floor)

For EACH component, return measurements:

[
  {{
    "component_name": "component name here",
    "value": 0,
    "unit": "SF",
    "source_sheet": "A-201",
    "source_description": "Measured from north elevation: 120 ft wide × 45 ft tall",
    "confidence": 0.9,
    "is_estimated": false,
    "building_ref": "Building A",
    "elevation_face": "North",
    "calculation": "120 × 45 = 5,400 SF gross, minus 840 SF windows = 4,560 SF net",
    "notes": ""
  }}
]

CRITICAL RULES:
- Show your CALCULATION for every measurement (length × height, count × size, etc.)
- Note which SHEET and which DRAWING on that sheet you measured from
- For repeating elements (unit windows), show: qty per unit × units per floor × floors
- Confidence 1.0 = dimension clearly labeled; 0.7 = measured from scale; 0.5 = estimated
- Return ONLY the JSON array"""


MULTIFAMILY_DEDUCTIONS_PROMPT = """Extract window and door schedules from these MULTIFAMILY drawings.
Calculate total opening areas to deduct from gross wall area.

MULTIFAMILY-SPECIFIC INSTRUCTIONS:
- The WINDOW SCHEDULE typically shows: Type, Size (W×H), Frame material,
  Glass type, Quantity per typical unit, and TOTAL quantity for the project
- Multifamily projects have HIGH WINDOW COUNTS — a 200-unit building might
  have 600-1200 windows
- Look for the schedule TABLE first (most accurate), then verify against elevations
- DOOR SCHEDULE: separate EXTERIOR doors (entry, patio, balcony, fire exit,
  service, garage) from interior doors — we only need EXTERIOR for deductions
- Storefront/curtain wall glazing areas should be listed SEPARATELY from
  punch windows — they deduct differently

Return JSON:
{{
  "windows": [
    {{
      "type": "A",
      "description": "Double-hung vinyl, bedroom",
      "width_ft": 3.0,
      "height_ft": 5.0,
      "quantity": 240,
      "area_each_sf": 15.0,
      "total_area_sf": 3600.0,
      "per_unit_count": 1.2,
      "notes": "Typical in all bedrooms, 200 units × 1.2 avg"
    }}
  ],
  "exterior_doors": [
    {{
      "type": "1",
      "description": "Entry door, hollow metal frame",
      "width_ft": 3.0,
      "height_ft": 7.0,
      "quantity": 200,
      "area_each_sf": 21.0,
      "total_area_sf": 4200.0,
      "notes": "1 per unit"
    }}
  ],
  "sliding_glass_doors": [
    {{
      "type": "SGD-1",
      "description": "6'-0\" sliding glass door to balcony",
      "width_ft": 6.0,
      "height_ft": 6.83,
      "quantity": 160,
      "area_each_sf": 41.0,
      "total_area_sf": 6560.0,
      "notes": "80% of units have balcony access"
    }}
  ],
  "storefront_glazing": [
    {{
      "location": "Ground floor lobby",
      "area_sf": 480,
      "notes": "Measured from elevation A-201"
    }}
  ],
  "summary": {{
    "total_window_area_sf": 0,
    "total_door_area_sf": 0,
    "total_sgd_area_sf": 0,
    "total_storefront_sf": 0,
    "grand_total_deduction_sf": 0,
    "total_window_count": 0,
    "total_ext_door_count": 0
  }}
}}

Return ONLY the JSON object."""


MULTIFAMILY_VALIDATION_PROMPT = """You are a SENIOR ESTIMATING MANAGER performing a QA review on a
commercial multifamily envelope takeoff. You have 30+ years of experience
estimating 3-5 story wood-frame and podium multifamily projects.

TAKEOFF TO VERIFY:
{summary}

VALIDATION CHECKS TO PERFORM:

1. **RATIO CHECK — Wall Area vs Footprint:**
   - Typical wall-to-floor ratio for multifamily: 1.0–1.4× footprint per floor
   - If wall area seems too high or low, flag it

2. **WINDOW COUNT vs UNIT COUNT:**
   - Typical: 5–8 windows per residential unit (varies by unit mix)
   - 200-unit building should have roughly 1,000–1,600 windows
   - If count is wildly off, flag it

3. **ROOF AREA vs FOOTPRINT:**
   - Flat roof: roof area ≈ footprint (within 5%)
   - Pitched roof: roof area = footprint × pitch multiplier (within 10%)

4. **CLADDING QUANTITY SANITY:**
   - Net cladding SF should be 60-75% of gross wall SF (after opening deductions)
   - If net/gross ratio is outside this range, investigate

5. **GUTTER/DOWNSPOUT:**
   - Gutter LF should approximately equal eave perimeter
   - 1 downspout per ~40 LF of gutter is standard
   - Flat roofs with parapets may have 0 gutters (internal drains instead)

6. **PER-UNIT CROSS CHECK:**
   - Divide total cladding SF by unit count — should be ~200-400 SF/unit for exterior
   - Divide total window count by unit count — should be 5-8 windows/unit

For each major line item, independently estimate the quantity and compare.

Return JSON:
{{
  "verified_items": [
    {{
      "component": "name",
      "takeoff_qty": 0,
      "verified_qty": 0,
      "variance_pct": 0,
      "status": "pass",
      "check_method": "ratio check: 22,400 SF wall / 5,600 SF footprint / 4 stories = 1.0× ratio, normal"
    }}
  ],
  "ratio_checks": {{
    "wall_to_floor_ratio": 0,
    "net_to_gross_wall_ratio": 0,
    "windows_per_unit": 0,
    "cladding_sf_per_unit": 0,
    "roof_to_footprint_ratio": 0
  }},
  "overall_variance_pct": 0,
  "issues": [],
  "recommendation": "approve"
}}

Return ONLY the JSON object."""


# ---------------------------------------------------------------------------
# Default template for a "quick start" commercial multifamily project
# ---------------------------------------------------------------------------

def get_default_multifamily_template() -> dict:
    """Return a default template for a typical 4-story, 200-unit multifamily project.

    This serves as a starting point that the AI refines based on actual drawings.
    """
    return {
        "project_type": "commercial_multifamily",
        "typical_building": {
            "construction_type": "V-A",
            "stories": 4,
            "units_per_floor": 12,
            "total_units": 48,
            "footprint_sf": 12000,
            "perimeter_lf": 480,
            "floor_to_floor_ft": 9.67,
            "total_height_ft": 42,
            "parapet_height_ft": 3,
            "corridor_type": "interior",
        },
        "envelope_assumptions": {
            "primary_cladding": "fiber_cement_lap",
            "secondary_cladding": "brick_veneer",
            "secondary_cladding_floors": "1",
            "roof_system": "tpo_single_ply",
            "window_type": "vinyl_double_hung",
            "windows_per_unit": 6,
            "balcony_pct_of_units": 0.75,
            "avg_balcony_sf": 60,
            "wrb_type": "self_adhered_air_barrier",
            "continuous_insulation": "2_inch_polyiso",
        },
        "waste_factors": {
            "cladding_sf": 0.10,
            "roofing_sq": 0.10,
            "wrb_sf": 0.10,
            "insulation_sf": 0.05,
            "gutters_lf": 0.05,
            "trim_lf": 0.05,
            "windows_ea": 0.00,
            "flashing_lf": 0.10,
            "sealant_lf": 0.10,
        },
        "ddc_cwicr_search_terms": {
            "cladding": [
                "fiber cement siding installation",
                "lap siding exterior wall",
                "vinyl siding residential building",
                "brick veneer installation masonry",
            ],
            "roofing": [
                "TPO membrane roofing installation",
                "single ply roofing commercial flat",
                "roof insulation polyisocyanurate tapered",
                "asphalt shingle roofing residential",
            ],
            "waterproofing": [
                "self-adhered air barrier membrane wall",
                "fluid applied waterproofing balcony deck",
                "below grade waterproofing foundation",
                "weather resistive barrier exterior sheathing",
            ],
            "fenestration": [
                "vinyl window installation residential",
                "aluminum storefront glazing",
                "sliding glass door installation balcony",
                "hollow metal door frame exterior",
            ],
            "sheet_metal": [
                "metal coping parapet wall",
                "aluminum gutter installation",
                "downspout installation exterior",
                "flashing step counter through wall",
            ],
        },
    }
