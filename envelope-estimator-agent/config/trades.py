"""
Trade definitions for the Envelope Estimator Agent.

Each trade defines:
- measurement_type: what to extract from blueprints (area, linear, count)
- unit: standard unit of measure
- waste_factor: default waste percentage
- search_terms: keywords for DDC-CWICR Qdrant vector search
- components: sub-items that make up a complete installation
- pitch_adjusted: whether roof pitch multiplier applies
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MeasurementType(Enum):
    AREA = "area"            # square feet / square meters
    LINEAR = "linear"        # linear feet / meters
    COUNT = "count"          # individual units
    AREA_LINEAR = "both"     # area for main + linear for trim


class Phase(Enum):
    PHASE_1 = 1
    PHASE_2 = 2


@dataclass
class TradeComponent:
    name: str
    measurement_type: MeasurementType
    unit: str
    waste_factor: float
    search_terms: list[str]
    pitch_adjusted: bool = False
    notes: str = ""


@dataclass
class Trade:
    name: str
    code: str
    phase: Phase
    description: str
    components: list[TradeComponent]
    blueprint_sheets: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PHASE 1 TRADES - Core Envelope
# ---------------------------------------------------------------------------

SIDING = Trade(
    name="Siding",
    code="SID",
    phase=Phase.PHASE_1,
    description="Exterior wall cladding systems",
    blueprint_sheets=["elevations", "wall_sections", "details"],
    components=[
        TradeComponent(
            name="Siding Material",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.10,
            search_terms=[
                "vinyl siding installation",
                "fiber cement siding",
                "hardie plank siding",
                "lap siding installation",
                "board and batten siding",
                "metal wall panel installation",
            ],
        ),
        TradeComponent(
            name="House Wrap / WRB",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.10,
            search_terms=[
                "weather resistive barrier",
                "house wrap installation",
                "building wrap membrane",
            ],
        ),
        TradeComponent(
            name="J-Channel & Trim",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "siding trim channel",
                "j-channel installation",
                "corner post siding",
                "starter strip siding",
            ],
        ),
        TradeComponent(
            name="Soffit",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.08,
            search_terms=[
                "soffit panel installation",
                "vinyl soffit",
                "aluminum soffit",
                "vented soffit",
            ],
        ),
        TradeComponent(
            name="Fascia",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "fascia board installation",
                "aluminum fascia cover",
                "fascia trim",
            ],
        ),
    ],
)

ROOFING = Trade(
    name="Roofing",
    code="ROF",
    phase=Phase.PHASE_1,
    description="Roof systems - metal, shingle, and single-ply membrane",
    blueprint_sheets=["roof_plan", "elevations", "sections", "details"],
    components=[
        TradeComponent(
            name="Shingle Roofing",
            measurement_type=MeasurementType.AREA,
            unit="SQ",  # 1 square = 100 SF
            waste_factor=0.12,
            pitch_adjusted=True,
            search_terms=[
                "asphalt shingle roofing",
                "architectural shingle installation",
                "30 year shingle roof",
                "composition shingle roofing",
            ],
        ),
        TradeComponent(
            name="Metal Roofing",
            measurement_type=MeasurementType.AREA,
            unit="SQ",
            waste_factor=0.08,
            pitch_adjusted=True,
            search_terms=[
                "standing seam metal roof",
                "metal roofing panel installation",
                "corrugated metal roofing",
                "metal roof system",
            ],
        ),
        TradeComponent(
            name="Single-Ply Membrane",
            measurement_type=MeasurementType.AREA,
            unit="SQ",
            waste_factor=0.10,
            pitch_adjusted=False,  # typically flat/low-slope
            search_terms=[
                "TPO membrane roofing",
                "EPDM rubber roofing",
                "PVC single ply membrane",
                "modified bitumen roofing",
            ],
        ),
        TradeComponent(
            name="Underlayment",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.10,
            pitch_adjusted=True,
            search_terms=[
                "roofing underlayment felt",
                "synthetic underlayment",
                "ice and water shield",
            ],
        ),
        TradeComponent(
            name="Ridge Cap",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "ridge cap shingle",
                "metal ridge cap",
                "ridge vent cap",
            ],
        ),
        TradeComponent(
            name="Drip Edge",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "drip edge flashing",
                "eave drip edge metal",
                "rake drip edge",
            ],
        ),
        TradeComponent(
            name="Flashing",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.10,
            search_terms=[
                "roof flashing installation",
                "step flashing",
                "valley flashing",
                "counter flashing",
                "pipe boot flashing",
            ],
        ),
    ],
)

GUTTERS = Trade(
    name="Gutters",
    code="GUT",
    phase=Phase.PHASE_1,
    description="Gutter systems for roof drainage",
    blueprint_sheets=["elevations", "roof_plan", "details"],
    components=[
        TradeComponent(
            name="Gutters",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "seamless gutter installation",
                "K-style gutter",
                "half round gutter",
                "commercial box gutter",
                "aluminum gutter installation",
            ],
        ),
        TradeComponent(
            name="Gutter Guards",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "gutter guard screen",
                "leaf guard gutter",
                "gutter protection system",
            ],
        ),
        TradeComponent(
            name="Gutter Accessories",
            measurement_type=MeasurementType.COUNT,
            unit="EA",
            waste_factor=0.0,
            search_terms=[
                "gutter end cap",
                "gutter corner miter",
                "gutter hanger bracket",
                "gutter outlet",
            ],
        ),
    ],
)

DOWNSPOUTS = Trade(
    name="Downspouts",
    code="DSP",
    phase=Phase.PHASE_1,
    description="Downspout systems for roof water discharge",
    blueprint_sheets=["elevations", "details", "site_plan"],
    components=[
        TradeComponent(
            name="Downspouts",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "downspout installation",
                "rectangular downspout",
                "round downspout pipe",
                "aluminum downspout",
            ],
        ),
        TradeComponent(
            name="Elbows & Offsets",
            measurement_type=MeasurementType.COUNT,
            unit="EA",
            waste_factor=0.0,
            search_terms=[
                "downspout elbow",
                "downspout offset",
                "downspout adapter",
            ],
        ),
        TradeComponent(
            name="Splash Blocks / Boots",
            measurement_type=MeasurementType.COUNT,
            unit="EA",
            waste_factor=0.0,
            search_terms=[
                "splash block",
                "downspout boot",
                "downspout discharge",
            ],
        ),
    ],
)

COPING = Trade(
    name="Coping",
    code="COP",
    phase=Phase.PHASE_1,
    description="Parapet wall and flat roof edge coping",
    blueprint_sheets=["roof_plan", "sections", "details", "elevations"],
    components=[
        TradeComponent(
            name="Metal Coping",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "metal coping cap parapet",
                "aluminum coping installation",
                "parapet wall coping",
                "wall cap flashing",
                "coping metal fabrication",
            ],
        ),
        TradeComponent(
            name="Coping Cleats & Fasteners",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "coping cleat installation",
                "continuous cleat metal",
            ],
        ),
    ],
)

WINDOWS = Trade(
    name="Windows",
    code="WIN",
    phase=Phase.PHASE_1,
    description="Window units and installation",
    blueprint_sheets=["elevations", "window_schedule", "details", "sections"],
    components=[
        TradeComponent(
            name="Window Units",
            measurement_type=MeasurementType.COUNT,
            unit="EA",
            waste_factor=0.0,
            search_terms=[
                "vinyl window installation",
                "aluminum window commercial",
                "double hung window",
                "casement window installation",
                "fixed window unit",
                "sliding window installation",
            ],
        ),
        TradeComponent(
            name="Window Flashing & Sealant",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.10,
            search_terms=[
                "window flashing tape",
                "window sealant caulk",
                "window pan flashing",
            ],
        ),
        TradeComponent(
            name="Window Trim / Casing",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.08,
            search_terms=[
                "window exterior trim",
                "window casing installation",
                "window surround trim",
            ],
        ),
    ],
)

# ---------------------------------------------------------------------------
# PHASE 2 TRADES - Extended Envelope & Interior
# ---------------------------------------------------------------------------

DECKING = Trade(
    name="Decking",
    code="DEC",
    phase=Phase.PHASE_2,
    description="Exterior deck and balcony systems",
    blueprint_sheets=["floor_plans", "elevations", "details", "sections"],
    components=[
        TradeComponent(
            name="Deck Boards",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.10,
            search_terms=[
                "composite decking installation",
                "wood decking boards",
                "PVC deck board installation",
                "Trex decking",
            ],
        ),
        TradeComponent(
            name="Deck Framing",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.08,
            search_terms=[
                "deck joist framing",
                "deck beam installation",
                "deck ledger board",
            ],
        ),
        TradeComponent(
            name="Deck Hardware",
            measurement_type=MeasurementType.COUNT,
            unit="EA",
            waste_factor=0.0,
            search_terms=[
                "joist hanger deck",
                "post base connector",
                "deck fastener hidden",
            ],
        ),
    ],
)

EXTERIOR_DOORS = Trade(
    name="Exterior Doors",
    code="EXD",
    phase=Phase.PHASE_2,
    description="Exterior door units and hardware",
    blueprint_sheets=["elevations", "door_schedule", "details", "floor_plans"],
    components=[
        TradeComponent(
            name="Door Units",
            measurement_type=MeasurementType.COUNT,
            unit="EA",
            waste_factor=0.0,
            search_terms=[
                "exterior door installation",
                "entry door unit",
                "patio door sliding",
                "french door exterior",
                "commercial storefront door",
            ],
        ),
        TradeComponent(
            name="Door Hardware",
            measurement_type=MeasurementType.COUNT,
            unit="SET",
            waste_factor=0.0,
            search_terms=[
                "door hardware set",
                "commercial door closer",
                "door lockset exterior",
            ],
        ),
        TradeComponent(
            name="Door Frame & Trim",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "door frame installation",
                "exterior door trim casing",
                "door threshold",
            ],
        ),
    ],
)

RAILING = Trade(
    name="Railing",
    code="RLG",
    phase=Phase.PHASE_2,
    description="Exterior railing and guardrail systems",
    blueprint_sheets=["elevations", "details", "floor_plans", "sections"],
    components=[
        TradeComponent(
            name="Railing Systems",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "aluminum railing installation",
                "metal guardrail exterior",
                "cable railing system",
                "glass railing panel",
                "composite railing system",
            ],
        ),
        TradeComponent(
            name="Railing Posts",
            measurement_type=MeasurementType.COUNT,
            unit="EA",
            waste_factor=0.0,
            search_terms=[
                "railing post installation",
                "newel post exterior",
                "railing post base",
            ],
        ),
    ],
)

FRAMING = Trade(
    name="Framing",
    code="FRM",
    phase=Phase.PHASE_2,
    description="Structural and non-structural framing",
    blueprint_sheets=["floor_plans", "sections", "framing_plans", "details"],
    components=[
        TradeComponent(
            name="Wall Framing",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.08,
            search_terms=[
                "wood stud wall framing",
                "metal stud framing",
                "exterior wall framing",
                "load bearing wall framing",
            ],
        ),
        TradeComponent(
            name="Floor/Ceiling Framing",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.08,
            search_terms=[
                "floor joist framing",
                "ceiling joist installation",
                "engineered floor joist",
                "truss installation",
            ],
        ),
        TradeComponent(
            name="Headers & Beams",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "header beam installation",
                "LVL beam framing",
                "structural beam wood",
            ],
        ),
    ],
)

PAINTING = Trade(
    name="Interior / Exterior Painting",
    code="PNT",
    phase=Phase.PHASE_2,
    description="Interior and exterior painting and coatings",
    blueprint_sheets=["elevations", "finish_schedule", "floor_plans"],
    components=[
        TradeComponent(
            name="Exterior Paint",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.05,
            search_terms=[
                "exterior wall painting",
                "exterior paint application",
                "exterior primer coating",
                "exterior stain application",
            ],
        ),
        TradeComponent(
            name="Interior Paint",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.05,
            search_terms=[
                "interior wall painting",
                "interior ceiling painting",
                "interior primer application",
                "interior paint two coat",
            ],
        ),
        TradeComponent(
            name="Trim & Detail Paint",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "trim painting interior",
                "baseboard painting",
                "door frame painting",
                "window trim painting",
            ],
        ),
    ],
)

DRYWALL = Trade(
    name="Drywall",
    code="DRY",
    phase=Phase.PHASE_2,
    description="Drywall installation and finishing",
    blueprint_sheets=["floor_plans", "sections", "details", "ceiling_plans"],
    components=[
        TradeComponent(
            name="Drywall Board",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.10,
            search_terms=[
                "gypsum board installation",
                "drywall hanging",
                "drywall board installation",
                "moisture resistant drywall",
                "fire rated drywall",
            ],
        ),
        TradeComponent(
            name="Drywall Finishing",
            measurement_type=MeasurementType.AREA,
            unit="SF",
            waste_factor=0.0,
            search_terms=[
                "drywall taping finishing",
                "drywall joint compound",
                "drywall level 4 finish",
                "drywall level 5 finish",
            ],
        ),
        TradeComponent(
            name="Drywall Accessories",
            measurement_type=MeasurementType.LINEAR,
            unit="LF",
            waste_factor=0.05,
            search_terms=[
                "corner bead drywall",
                "drywall j-bead",
                "drywall control joint",
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Trade Registry
# ---------------------------------------------------------------------------

PHASE_1_TRADES = [SIDING, ROOFING, GUTTERS, DOWNSPOUTS, COPING, WINDOWS]
PHASE_2_TRADES = [DECKING, EXTERIOR_DOORS, RAILING, FRAMING, PAINTING, DRYWALL]
ALL_TRADES = PHASE_1_TRADES + PHASE_2_TRADES

TRADE_BY_CODE = {t.code: t for t in ALL_TRADES}
TRADE_BY_NAME = {t.name.lower(): t for t in ALL_TRADES}


# ---------------------------------------------------------------------------
# Pitch Multipliers (rise:run → multiplier)
# ---------------------------------------------------------------------------

PITCH_MULTIPLIERS = {
    "flat":  1.000,  # 0:12
    "1:12":  1.003,
    "2:12":  1.014,
    "3:12":  1.031,
    "4:12":  1.054,
    "5:12":  1.083,
    "6:12":  1.118,
    "7:12":  1.158,
    "8:12":  1.202,
    "9:12":  1.250,
    "10:12": 1.302,
    "11:12": 1.357,
    "12:12": 1.414,
    "14:12": 1.537,
    "16:12": 1.667,
    "18:12": 1.803,
}


def get_pitch_multiplier(pitch_str: str) -> float:
    """Return the roof pitch multiplier for a given pitch string."""
    normalized = pitch_str.strip().lower().replace(" ", "")
    if normalized in PITCH_MULTIPLIERS:
        return PITCH_MULTIPLIERS[normalized]
    # Try parsing "X/12" or "X:12" format
    for sep in [":", "/"]:
        if sep in normalized:
            parts = normalized.split(sep)
            if len(parts) == 2:
                try:
                    rise = float(parts[0])
                    run = float(parts[1])
                    import math
                    return math.sqrt(1 + (rise / run) ** 2)
                except ValueError:
                    pass
    return 1.0  # default to no adjustment
