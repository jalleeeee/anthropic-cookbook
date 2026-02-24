"""
Property Loss / Insurance Estimate Report Module (Xactimate-style)

Generates insurance damage assessment reports combining:
1. AI-powered photo damage detection (Claude Vision)
2. Satellite roof measurements (via roof_report module)
3. Xactimate-compatible line item pricing (XactNet price list)
4. Industry-standard damage classification (IICRC / Xactimate categories)
5. Depreciation schedules (ACV vs RCV calculations)
6. Professional claim-ready PDF reports

Reference architecture: SureSight (Next.js/Supabase) + ConstructI patterns
Adapted to Python for integration with the Envelope Estimator Agent.

Output:
- Multi-page HTML report (Xactimate-style scope of loss)
- Line-item estimate with labor, material, O&P breakdowns
- Photo documentation with AI annotations
- ACV/RCV depreciation schedule
"""

import base64
import io
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic

from config.settings import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Xactimate-compatible category codes and pricing
# ---------------------------------------------------------------------------

# Standard Xactimate category selectors
XACT_CATEGORIES = {
    "RFG": {"name": "Roofing", "description": "Roof systems and components"},
    "SID": {"name": "Siding", "description": "Exterior wall cladding"},
    "GUT": {"name": "Gutters & Downspouts", "description": "Rain water management"},
    "WIN": {"name": "Windows", "description": "Window units and glazing"},
    "EXD": {"name": "Exterior Doors", "description": "Entry and patio doors"},
    "FEN": {"name": "Fencing", "description": "Fences and gates"},
    "INT": {"name": "Interior", "description": "Interior walls, ceilings, floors"},
    "PLM": {"name": "Plumbing", "description": "Plumbing systems"},
    "ELC": {"name": "Electrical", "description": "Electrical systems"},
    "PNT": {"name": "Painting", "description": "Interior and exterior painting"},
    "DRY": {"name": "Drywall", "description": "Drywall and plaster"},
    "FLR": {"name": "Flooring", "description": "Floor coverings"},
    "INS": {"name": "Insulation", "description": "Thermal and acoustic insulation"},
    "CLN": {"name": "Cleaning", "description": "Cleaning and deodorizing"},
    "DEM": {"name": "Demolition", "description": "Tear-out and disposal"},
    "GEN": {"name": "General", "description": "General conditions and requirements"},
    "WTR": {"name": "Water Mitigation", "description": "Water extraction and drying"},
}

# Damage severity levels (IICRC-aligned)
SEVERITY_LEVELS = {
    "minor": {"label": "Minor", "repair_percent": 0.15, "depreciation_rate": 0.02},
    "moderate": {"label": "Moderate", "repair_percent": 0.40, "depreciation_rate": 0.05},
    "severe": {"label": "Severe", "repair_percent": 0.75, "depreciation_rate": 0.08},
    "critical": {"label": "Critical / Total Loss", "repair_percent": 1.00, "depreciation_rate": 0.10},
}

# Damage types with associated Xactimate categories
DAMAGE_TYPES = {
    "hail": {
        "label": "Hail Damage",
        "categories": ["RFG", "SID", "GUT", "WIN"],
        "keywords": ["hail", "dent", "dimple", "bruise", "impact mark", "granule loss"],
    },
    "wind": {
        "label": "Wind Damage",
        "categories": ["RFG", "SID", "FEN"],
        "keywords": ["wind", "blown off", "lifted", "torn", "missing", "displaced"],
    },
    "water": {
        "label": "Water Damage",
        "categories": ["INT", "DRY", "FLR", "PLM", "CLN", "WTR"],
        "keywords": ["water", "leak", "moisture", "stain", "mold", "mildew", "wet"],
    },
    "fire": {
        "label": "Fire / Smoke Damage",
        "categories": ["INT", "DRY", "PNT", "ELC", "CLN", "DEM"],
        "keywords": ["fire", "smoke", "soot", "char", "burn", "scorch"],
    },
    "impact": {
        "label": "Impact Damage",
        "categories": ["RFG", "SID", "WIN", "FEN", "EXD"],
        "keywords": ["impact", "hit", "crack", "shatter", "break", "hole", "puncture"],
    },
    "wear": {
        "label": "Normal Wear & Deterioration",
        "categories": ["RFG", "SID", "PNT"],
        "keywords": ["wear", "age", "deterioration", "fading", "peeling", "cracking"],
    },
    "structural": {
        "label": "Structural Damage",
        "categories": ["GEN", "DEM"],
        "keywords": ["structural", "foundation", "settling", "collapse", "buckle"],
    },
}


# ---------------------------------------------------------------------------
# Xactimate-compatible price database (US averages, per-unit)
# ---------------------------------------------------------------------------

XACT_PRICE_LIST = {
    # Roofing
    "RFG_SHINGLE_REMOVE": {"desc": "Remove composition shingles", "unit": "SQ", "material": 0, "labor": 45.00, "total": 45.00},
    "RFG_SHINGLE_3TAB": {"desc": "3-tab composition shingles - 25yr", "unit": "SQ", "material": 95.00, "labor": 75.00, "total": 170.00},
    "RFG_SHINGLE_ARCH": {"desc": "Architectural shingles - 30yr", "unit": "SQ", "material": 125.00, "labor": 85.00, "total": 210.00},
    "RFG_SHINGLE_PREM": {"desc": "Premium/designer shingles - 50yr", "unit": "SQ", "material": 225.00, "labor": 95.00, "total": 320.00},
    "RFG_FELT_15": {"desc": "#15 felt underlayment", "unit": "SQ", "material": 12.00, "labor": 10.00, "total": 22.00},
    "RFG_SYNTH_UL": {"desc": "Synthetic underlayment", "unit": "SQ", "material": 18.00, "labor": 10.00, "total": 28.00},
    "RFG_ICE_WATER": {"desc": "Ice & water shield membrane", "unit": "SQ", "material": 45.00, "labor": 15.00, "total": 60.00},
    "RFG_RIDGE_CAP": {"desc": "Ridge cap shingles", "unit": "LF", "material": 2.50, "labor": 2.00, "total": 4.50},
    "RFG_DRIP_EDGE": {"desc": "Drip edge - aluminum", "unit": "LF", "material": 1.25, "labor": 1.00, "total": 2.25},
    "RFG_VALLEY": {"desc": "Valley flashing - W type", "unit": "LF", "material": 3.50, "labor": 3.00, "total": 6.50},
    "RFG_STEP_FLASH": {"desc": "Step flashing", "unit": "EA", "material": 1.50, "labor": 3.00, "total": 4.50},
    "RFG_PIPE_BOOT": {"desc": "Pipe boot flashing", "unit": "EA", "material": 12.00, "labor": 15.00, "total": 27.00},
    "RFG_VENT_RESET": {"desc": "Reset/replace roof vent", "unit": "EA", "material": 25.00, "labor": 35.00, "total": 60.00},
    "RFG_CHIMNEY_FLASH": {"desc": "Chimney flashing - step & counter", "unit": "EA", "material": 85.00, "labor": 175.00, "total": 260.00},
    # Siding
    "SID_VINYL_REMOVE": {"desc": "Remove vinyl siding", "unit": "SF", "material": 0, "labor": 0.65, "total": 0.65},
    "SID_VINYL_STD": {"desc": "Vinyl siding - standard grade", "unit": "SF", "material": 2.25, "labor": 2.50, "total": 4.75},
    "SID_VINYL_PREM": {"desc": "Vinyl siding - premium insulated", "unit": "SF", "material": 3.75, "labor": 2.75, "total": 6.50},
    "SID_FIBER_CEMENT": {"desc": "Fiber cement siding (HardiPlank)", "unit": "SF", "material": 3.50, "labor": 4.50, "total": 8.00},
    "SID_WOOD_LAP": {"desc": "Wood lap siding", "unit": "SF", "material": 4.00, "labor": 5.00, "total": 9.00},
    "SID_HOUSEWRAP": {"desc": "House wrap / WRB", "unit": "SF", "material": 0.35, "labor": 0.40, "total": 0.75},
    # Gutters
    "GUT_ALUM_5K": {"desc": "Aluminum gutter - 5\" K-style", "unit": "LF", "material": 4.50, "labor": 5.50, "total": 10.00},
    "GUT_ALUM_6K": {"desc": "Aluminum gutter - 6\" K-style", "unit": "LF", "material": 5.50, "labor": 6.00, "total": 11.50},
    "GUT_DOWNSPOUT": {"desc": "Downspout - 2x3 aluminum", "unit": "LF", "material": 3.50, "labor": 4.00, "total": 7.50},
    "GUT_ELBOW": {"desc": "Downspout elbow", "unit": "EA", "material": 5.00, "labor": 4.00, "total": 9.00},
    # Windows
    "WIN_VINYL_DH": {"desc": "Vinyl double-hung window", "unit": "EA", "material": 285.00, "labor": 175.00, "total": 460.00},
    "WIN_VINYL_SLIDER": {"desc": "Vinyl sliding window", "unit": "EA", "material": 250.00, "labor": 165.00, "total": 415.00},
    "WIN_GLASS_ONLY": {"desc": "Replace glass only (sealed unit)", "unit": "EA", "material": 125.00, "labor": 95.00, "total": 220.00},
    "WIN_SCREEN": {"desc": "Window screen replacement", "unit": "EA", "material": 25.00, "labor": 15.00, "total": 40.00},
    # Exterior Doors
    "EXD_ENTRY_STD": {"desc": "Exterior entry door - standard", "unit": "EA", "material": 350.00, "labor": 225.00, "total": 575.00},
    "EXD_PATIO_SLIDE": {"desc": "Sliding patio door", "unit": "EA", "material": 650.00, "labor": 275.00, "total": 925.00},
    "EXD_GARAGE": {"desc": "Garage door - 16x7 steel", "unit": "EA", "material": 850.00, "labor": 350.00, "total": 1200.00},
    # Interior
    "INT_DRYWALL_HANG": {"desc": "Drywall - hang 1/2\"", "unit": "SF", "material": 0.55, "labor": 1.25, "total": 1.80},
    "INT_DRYWALL_FINISH": {"desc": "Drywall - tape, mud, sand (L4)", "unit": "SF", "material": 0.25, "labor": 1.50, "total": 1.75},
    "INT_PAINT_WALL": {"desc": "Paint interior walls - 2 coats", "unit": "SF", "material": 0.35, "labor": 0.85, "total": 1.20},
    "INT_PAINT_CEIL": {"desc": "Paint interior ceiling - 2 coats", "unit": "SF", "material": 0.35, "labor": 0.95, "total": 1.30},
    "INT_BASEBOARD": {"desc": "Baseboard trim - MDF primed", "unit": "LF", "material": 1.75, "labor": 2.50, "total": 4.25},
    "INT_CARPET": {"desc": "Carpet - mid grade w/ pad", "unit": "SF", "material": 3.50, "labor": 1.50, "total": 5.00},
    "INT_LVP": {"desc": "Luxury vinyl plank flooring", "unit": "SF", "material": 3.25, "labor": 2.75, "total": 6.00},
    # Water mitigation
    "WTR_EXTRACT": {"desc": "Water extraction - truck mount", "unit": "SF", "material": 0, "labor": 0.75, "total": 0.75},
    "WTR_DRY_STRUCT": {"desc": "Structural drying (per day)", "unit": "DAY", "material": 0, "labor": 75.00, "total": 75.00},
    "WTR_DEHUMIDIFIER": {"desc": "Dehumidifier rental (per day)", "unit": "DAY", "material": 0, "labor": 55.00, "total": 55.00},
    "WTR_AIR_MOVER": {"desc": "Air mover rental (per day)", "unit": "DAY", "material": 0, "labor": 35.00, "total": 35.00},
    "WTR_ANTIMICROBIAL": {"desc": "Apply antimicrobial treatment", "unit": "SF", "material": 0.35, "labor": 0.40, "total": 0.75},
    # Demolition / Tear-out
    "DEM_DRYWALL": {"desc": "Remove drywall", "unit": "SF", "material": 0, "labor": 0.85, "total": 0.85},
    "DEM_FLOORING": {"desc": "Remove flooring", "unit": "SF", "material": 0, "labor": 0.75, "total": 0.75},
    "DEM_BASEBOARD": {"desc": "Remove baseboard trim", "unit": "LF", "material": 0, "labor": 0.65, "total": 0.65},
    "DEM_DEBRIS": {"desc": "Haul debris (per load)", "unit": "EA", "material": 0, "labor": 175.00, "total": 175.00},
    # Cleaning
    "CLN_CONTENTS": {"desc": "Clean contents - light", "unit": "SF", "material": 0.15, "labor": 0.35, "total": 0.50},
    "CLN_SMOKE": {"desc": "Smoke/soot cleaning - walls", "unit": "SF", "material": 0.25, "labor": 0.75, "total": 1.00},
    # Painting (exterior)
    "PNT_EXT_WALL": {"desc": "Paint exterior - body (2 coats)", "unit": "SF", "material": 0.40, "labor": 1.10, "total": 1.50},
    "PNT_EXT_TRIM": {"desc": "Paint exterior trim", "unit": "LF", "material": 0.35, "labor": 0.90, "total": 1.25},
    # General
    "GEN_PERMIT": {"desc": "Building permit", "unit": "EA", "material": 0, "labor": 350.00, "total": 350.00},
    "GEN_DUMPSTER": {"desc": "Dumpster rental (20yd)", "unit": "EA", "material": 0, "labor": 450.00, "total": 450.00},
    "GEN_SCAFFOLD": {"desc": "Scaffolding setup & rental", "unit": "DAY", "material": 0, "labor": 125.00, "total": 125.00},
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DamagePhoto:
    """An uploaded damage photo with AI analysis."""
    photo_path: str
    photo_b64: str = ""
    damage_detected: bool = False
    damage_type: str = ""           # hail, wind, water, fire, impact, wear
    damage_severity: str = ""       # minor, moderate, severe, critical
    confidence: float = 0.0
    affected_component: str = ""    # roof, siding, window, interior, etc.
    description: str = ""
    location_notes: str = ""
    ai_raw_analysis: dict = field(default_factory=dict)


@dataclass
class ClaimLineItem:
    """Xactimate-compatible estimate line item."""
    line_number: int
    category_code: str
    xact_code: str
    description: str
    quantity: float
    unit: str
    material_cost: float
    labor_cost: float
    total_cost: float              # material + labor for this line
    depreciation_pct: float = 0.0
    depreciation_amt: float = 0.0
    acv_amount: float = 0.0        # Actual Cash Value = total - depreciation
    notes: str = ""


@dataclass
class CategorySummary:
    """Summary for one Xactimate category."""
    code: str
    name: str
    line_items: list[ClaimLineItem]
    subtotal_material: float = 0.0
    subtotal_labor: float = 0.0
    subtotal: float = 0.0
    depreciation: float = 0.0
    acv: float = 0.0


@dataclass
class PropertyLossReport:
    """Complete property loss / insurance estimate report."""
    report_id: str = ""
    claim_number: str = ""
    generated_at: str = ""

    # Property info
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    homeowner_name: str = ""
    homeowner_phone: str = ""
    homeowner_email: str = ""

    # Claim info
    date_of_loss: str = ""
    cause_of_loss: str = ""         # hail, wind, water, fire, etc.
    policy_number: str = ""
    insurance_company: str = ""
    adjuster_name: str = ""
    adjuster_phone: str = ""

    # Damage assessment
    photos: list[DamagePhoto] = field(default_factory=list)
    primary_damage_type: str = ""
    overall_severity: str = ""
    affected_areas: list[str] = field(default_factory=list)

    # Estimate
    category_summaries: list[CategorySummary] = field(default_factory=list)
    total_material: float = 0.0
    total_labor: float = 0.0
    subtotal: float = 0.0
    overhead_percent: float = 10.0
    overhead_amount: float = 0.0
    profit_percent: float = 10.0
    profit_amount: float = 0.0
    replacement_cost_value: float = 0.0  # RCV
    total_depreciation: float = 0.0
    actual_cash_value: float = 0.0       # ACV = RCV - depreciation
    deductible: float = 0.0
    net_claim: float = 0.0               # ACV - deductible
    tax: float = 0.0
    grand_total: float = 0.0             # RCV + tax

    # Roof measurements (from roof_report module if available)
    roof_area_sqft: float = 0.0
    roof_pitch_ratio: str = ""
    roof_segments: int = 0

    # Output
    professional_report_html: str = ""


# ---------------------------------------------------------------------------
# Module class
# ---------------------------------------------------------------------------

class PropertyLossEstimator:
    """Generates Xactimate-style property loss estimates."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic.api_key)
        self.output_dir = Path(settings.output_dir) / "loss_reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def generate(
        self,
        address: str,
        photo_paths: list[str],
        cause_of_loss: str = "",
        date_of_loss: str = "",
        homeowner_name: str = "",
        homeowner_phone: str = "",
        homeowner_email: str = "",
        policy_number: str = "",
        insurance_company: str = "",
        adjuster_name: str = "",
        deductible: float = 1000.0,
        city: str = "",
        state: str = "",
        postal_code: str = "",
        roof_report=None,          # Optional RoofReport from roof_report module
    ) -> PropertyLossReport:
        """Generate a complete property loss estimate."""
        start_time = time.time()

        report = PropertyLossReport(
            report_id=f"PL-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            claim_number=f"CLM-{datetime.now().strftime('%Y%m%d')}-{int(time.time()) % 10000:04d}",
            generated_at=datetime.now().isoformat(),
            address=address,
            city=city,
            state=state,
            postal_code=postal_code,
            homeowner_name=homeowner_name,
            homeowner_phone=homeowner_phone,
            homeowner_email=homeowner_email,
            date_of_loss=date_of_loss or datetime.now().strftime("%Y-%m-%d"),
            cause_of_loss=cause_of_loss,
            policy_number=policy_number,
            insurance_company=insurance_company,
            adjuster_name=adjuster_name,
            deductible=deductible,
        )

        # Import roof measurements if available
        if roof_report:
            report.roof_area_sqft = roof_report.total_true_area_sqft
            report.roof_pitch_ratio = roof_report.roof_pitch_ratio
            report.roof_segments = len(roof_report.segments)

        # Step 1: Analyze damage photos with AI
        print("\n[1/5] Analyzing damage photos (AI Vision)...")
        report.photos = self._analyze_photos(photo_paths)
        print(f"       Photos analyzed: {len(report.photos)}")
        for photo in report.photos:
            if photo.damage_detected:
                print(
                    f"       - {photo.damage_type} ({photo.damage_severity}) "
                    f"confidence: {photo.confidence:.0%}"
                )

        # Step 2: Determine overall damage profile
        print("\n[2/5] Assessing damage profile...")
        self._assess_damage_profile(report)
        print(f"       Primary cause: {report.primary_damage_type}")
        print(f"       Severity: {report.overall_severity}")
        print(f"       Affected areas: {', '.join(report.affected_areas)}")

        # Step 3: Generate Xactimate-compatible line items
        print("\n[3/5] Generating estimate line items...")
        self._generate_estimate(report)
        print(f"       Categories: {len(report.category_summaries)}")
        for cat in report.category_summaries:
            print(f"         {cat.name}: ${cat.subtotal:,.2f}")

        # Step 4: Calculate O&P, depreciation, ACV/RCV
        print("\n[4/5] Computing financials (O&P, depreciation, ACV/RCV)...")
        self._compute_financials(report)
        print(f"       RCV: ${report.replacement_cost_value:,.2f}")
        print(f"       Depreciation: ${report.total_depreciation:,.2f}")
        print(f"       ACV: ${report.actual_cash_value:,.2f}")
        print(f"       Net Claim: ${report.net_claim:,.2f}")

        # Step 5: Generate HTML report
        print("\n[5/5] Generating professional report...")
        report.professional_report_html = self._generate_report_html(report)

        # Save
        elapsed = time.time() - start_time
        self._save_report(report)
        print(f"\nComplete in {elapsed:.1f}s")
        print(f"  Report: {self.output_dir}")
        print(f"  Grand Total (RCV): ${report.grand_total:,.2f}")

        return report

    # ------------------------------------------------------------------
    # Step 1: Photo analysis
    # ------------------------------------------------------------------

    def _analyze_photos(self, photo_paths: list[str]) -> list[DamagePhoto]:
        photos = []
        for path in photo_paths:
            photo = self._analyze_single_photo(path)
            photos.append(photo)
        return photos

    def _analyze_single_photo(self, photo_path: str) -> DamagePhoto:
        """Analyze a single damage photo using Claude Vision."""
        photo = DamagePhoto(photo_path=photo_path)

        try:
            path = Path(photo_path)
            if not path.exists():
                logger.error(f"Photo not found: {photo_path}")
                return photo

            img_bytes = path.read_bytes()
            photo.photo_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

            # Determine media type
            suffix = path.suffix.lower()
            media_types = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
            }
            media_type = media_types.get(suffix, "image/jpeg")

            response = self.client.messages.create(
                model=self.settings.anthropic.model_vision,
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": photo.photo_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": """You are an expert insurance property damage assessor.
Analyze this photo for property damage. Provide your assessment as JSON:

{
  "damage_detected": true/false,
  "damage_type": "hail|wind|water|fire|impact|wear|structural|none",
  "severity": "minor|moderate|severe|critical",
  "confidence": 0.0-1.0,
  "affected_component": "roof|siding|window|gutter|door|interior_wall|ceiling|floor|structural|other",
  "description": "Detailed description of the damage observed",
  "measurements_needed": ["list of areas needing measurement"],
  "repair_action": "repair|replace|clean|none",
  "xactimate_categories": ["RFG", "SID", etc.],
  "estimated_affected_area_sqft": 0,
  "notes": "Any additional observations"
}

Be specific about:
- Type and pattern of damage (e.g., "circular hail dents 1-2 inches in diameter")
- Location on the structure
- Whether this is storm damage vs normal wear
- Material type visible (asphalt shingle, vinyl siding, etc.)

Return ONLY the JSON object.""",
                        },
                    ],
                }],
            )

            text = response.content[0].text.strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                photo.damage_detected = data.get("damage_detected", False)
                photo.damage_type = data.get("damage_type", "none")
                photo.damage_severity = data.get("severity", "minor")
                photo.confidence = float(data.get("confidence", 0))
                photo.affected_component = data.get("affected_component", "other")
                photo.description = data.get("description", "")
                photo.ai_raw_analysis = data

        except Exception as e:
            logger.error(f"Photo analysis error for {photo_path}: {e}")

        return photo

    # ------------------------------------------------------------------
    # Step 2: Damage profile assessment
    # ------------------------------------------------------------------

    def _assess_damage_profile(self, report: PropertyLossReport):
        """Determine overall damage profile from photo analyses."""

        # Count damage types
        type_counts: dict[str, int] = {}
        severity_scores: dict[str, list[float]] = {}
        all_components = set()

        for photo in report.photos:
            if not photo.damage_detected:
                continue

            dt = photo.damage_type
            type_counts[dt] = type_counts.get(dt, 0) + 1

            sev_map = {"minor": 1, "moderate": 2, "severe": 3, "critical": 4}
            score = sev_map.get(photo.damage_severity, 1) * photo.confidence
            severity_scores.setdefault(dt, []).append(score)

            all_components.add(photo.affected_component)

        # Primary damage type = most frequent
        if type_counts:
            report.primary_damage_type = max(type_counts, key=type_counts.get)
        elif report.cause_of_loss:
            report.primary_damage_type = report.cause_of_loss
        else:
            report.primary_damage_type = "unknown"

        # Overall severity = highest average score
        if severity_scores:
            max_avg = 0
            for dt, scores in severity_scores.items():
                avg = sum(scores) / len(scores)
                if avg > max_avg:
                    max_avg = avg
            if max_avg > 3:
                report.overall_severity = "critical"
            elif max_avg > 2:
                report.overall_severity = "severe"
            elif max_avg > 1.2:
                report.overall_severity = "moderate"
            else:
                report.overall_severity = "minor"
        else:
            report.overall_severity = "moderate"

        # Affected areas
        component_to_area = {
            "roof": "Roofing", "siding": "Siding", "window": "Windows",
            "gutter": "Gutters", "door": "Exterior Doors",
            "interior_wall": "Interior Walls", "ceiling": "Ceilings",
            "floor": "Flooring", "structural": "Structural",
        }
        report.affected_areas = [
            component_to_area.get(c, c.title()) for c in all_components
        ]

    # ------------------------------------------------------------------
    # Step 3: Generate estimate line items
    # ------------------------------------------------------------------

    def _generate_estimate(self, report: PropertyLossReport):
        """Generate Xactimate-compatible estimate based on damage assessment."""

        severity_info = SEVERITY_LEVELS.get(
            report.overall_severity, SEVERITY_LEVELS["moderate"]
        )
        repair_pct = severity_info["repair_percent"]

        line_num = 1
        items_by_category: dict[str, list[ClaimLineItem]] = {}

        # Get relevant damage type config
        damage_config = DAMAGE_TYPES.get(
            report.primary_damage_type, DAMAGE_TYPES.get("impact", {})
        )
        relevant_categories = damage_config.get("categories", ["GEN"]) if damage_config else ["GEN"]

        # Generate line items based on affected components from photos
        for photo in report.photos:
            if not photo.damage_detected:
                continue

            ai = photo.ai_raw_analysis
            affected_area = ai.get("estimated_affected_area_sqft", 0) or 100
            repair_action = ai.get("repair_action", "replace")
            xact_cats = ai.get("xactimate_categories", [])

            # Generate items based on component type
            component = photo.affected_component
            items = self._items_for_component(
                component, affected_area, repair_action, repair_pct,
                report, photo
            )

            for item_data in items:
                cat_code = item_data["category"]
                price = XACT_PRICE_LIST.get(item_data["xact_code"], {})
                if not price:
                    continue

                qty = item_data["quantity"]
                mat = round(price["material"] * qty, 2)
                lab = round(price["labor"] * qty, 2)
                total = round(mat + lab, 2)

                dep_rate = severity_info["depreciation_rate"]
                dep_amt = round(total * dep_rate, 2) if repair_action == "replace" else 0

                item = ClaimLineItem(
                    line_number=line_num,
                    category_code=cat_code,
                    xact_code=item_data["xact_code"],
                    description=price["desc"],
                    quantity=qty,
                    unit=price["unit"],
                    material_cost=mat,
                    labor_cost=lab,
                    total_cost=total,
                    depreciation_pct=dep_rate * 100 if dep_amt else 0,
                    depreciation_amt=dep_amt,
                    acv_amount=round(total - dep_amt, 2),
                    notes=item_data.get("notes", ""),
                )
                items_by_category.setdefault(cat_code, []).append(item)
                line_num += 1

        # Add general conditions if any work is being done
        if items_by_category:
            gen_items = self._general_conditions_items(report, line_num)
            for item_data in gen_items:
                price = XACT_PRICE_LIST.get(item_data["xact_code"], {})
                if not price:
                    continue
                qty = item_data["quantity"]
                mat = round(price["material"] * qty, 2)
                lab = round(price["labor"] * qty, 2)
                total = round(mat + lab, 2)
                item = ClaimLineItem(
                    line_number=line_num,
                    category_code="GEN",
                    xact_code=item_data["xact_code"],
                    description=price["desc"],
                    quantity=qty,
                    unit=price["unit"],
                    material_cost=mat,
                    labor_cost=lab,
                    total_cost=total,
                    notes=item_data.get("notes", ""),
                )
                items_by_category.setdefault("GEN", []).append(item)
                line_num += 1

        # Build category summaries
        for cat_code, items in items_by_category.items():
            cat_info = XACT_CATEGORIES.get(cat_code, {"name": cat_code})
            summary = CategorySummary(
                code=cat_code,
                name=cat_info["name"],
                line_items=items,
                subtotal_material=sum(i.material_cost for i in items),
                subtotal_labor=sum(i.labor_cost for i in items),
                subtotal=sum(i.total_cost for i in items),
                depreciation=sum(i.depreciation_amt for i in items),
                acv=sum(i.acv_amount for i in items),
            )
            report.category_summaries.append(summary)

    def _items_for_component(
        self, component: str, affected_area: float, repair_action: str,
        repair_pct: float, report: PropertyLossReport, photo: DamagePhoto,
    ) -> list[dict]:
        """Generate specific line items for a damaged component."""
        items = []

        if component == "roof":
            roof_sqft = report.roof_area_sqft or affected_area
            repair_area = roof_sqft * repair_pct
            squares = math.ceil(repair_area / 100)

            if repair_action == "replace":
                items.append({"category": "RFG", "xact_code": "RFG_SHINGLE_REMOVE",
                              "quantity": squares, "notes": "Tear off existing"})
                items.append({"category": "RFG", "xact_code": "RFG_SHINGLE_ARCH",
                              "quantity": squares, "notes": "Install new"})
                items.append({"category": "RFG", "xact_code": "RFG_SYNTH_UL",
                              "quantity": squares, "notes": "Underlayment"})
                items.append({"category": "RFG", "xact_code": "RFG_ICE_WATER",
                              "quantity": max(1, squares // 4), "notes": "Eaves & valleys"})
                # Edges
                ridge_lf = math.sqrt(repair_area) * 0.9
                items.append({"category": "RFG", "xact_code": "RFG_RIDGE_CAP",
                              "quantity": round(ridge_lf), "notes": "Ridge cap"})
                drip_lf = math.sqrt(repair_area) * 3
                items.append({"category": "RFG", "xact_code": "RFG_DRIP_EDGE",
                              "quantity": round(drip_lf), "notes": "Drip edge"})
            else:
                items.append({"category": "RFG", "xact_code": "RFG_SHINGLE_ARCH",
                              "quantity": max(1, squares // 3), "notes": "Patch repair"})

            # Flashing items
            items.append({"category": "RFG", "xact_code": "RFG_PIPE_BOOT",
                          "quantity": 2, "notes": "Replace pipe boots"})

        elif component == "siding":
            repair_area = affected_area * repair_pct
            if repair_action == "replace":
                items.append({"category": "SID", "xact_code": "SID_VINYL_REMOVE",
                              "quantity": round(repair_area), "notes": "Remove damaged"})
                items.append({"category": "SID", "xact_code": "SID_VINYL_STD",
                              "quantity": round(repair_area), "notes": "Install new"})
                items.append({"category": "SID", "xact_code": "SID_HOUSEWRAP",
                              "quantity": round(repair_area), "notes": "Replace WRB"})
            else:
                items.append({"category": "SID", "xact_code": "SID_VINYL_STD",
                              "quantity": round(repair_area * 0.3), "notes": "Repair sections"})

        elif component == "window":
            count = max(1, int(affected_area / 20))
            if repair_action == "replace":
                items.append({"category": "WIN", "xact_code": "WIN_VINYL_DH",
                              "quantity": count, "notes": "Replace window units"})
            else:
                items.append({"category": "WIN", "xact_code": "WIN_GLASS_ONLY",
                              "quantity": count, "notes": "Replace glass only"})
            items.append({"category": "WIN", "xact_code": "WIN_SCREEN",
                          "quantity": count, "notes": "Replace screens"})

        elif component == "gutter":
            linear_ft = math.sqrt(affected_area) * 4
            items.append({"category": "GUT", "xact_code": "GUT_ALUM_5K",
                          "quantity": round(linear_ft * repair_pct),
                          "notes": "Replace gutters"})
            ds_count = max(2, int(linear_ft / 30))
            items.append({"category": "GUT", "xact_code": "GUT_DOWNSPOUT",
                          "quantity": round(ds_count * 10 * repair_pct),
                          "notes": "Replace downspouts"})

        elif component in ("interior_wall", "ceiling"):
            repair_area = affected_area * repair_pct
            # Tear out
            items.append({"category": "DEM", "xact_code": "DEM_DRYWALL",
                          "quantity": round(repair_area), "notes": "Remove damaged drywall"})
            # Replace
            items.append({"category": "DRY", "xact_code": "INT_DRYWALL_HANG",
                          "quantity": round(repair_area), "notes": "Hang new drywall"})
            items.append({"category": "DRY", "xact_code": "INT_DRYWALL_FINISH",
                          "quantity": round(repair_area), "notes": "Tape and finish"})
            # Paint
            paint_code = "INT_PAINT_WALL" if component == "interior_wall" else "INT_PAINT_CEIL"
            items.append({"category": "PNT", "xact_code": paint_code,
                          "quantity": round(repair_area), "notes": "Paint to match"})

        elif component == "floor":
            repair_area = affected_area * repair_pct
            items.append({"category": "DEM", "xact_code": "DEM_FLOORING",
                          "quantity": round(repair_area), "notes": "Remove damaged"})
            items.append({"category": "FLR", "xact_code": "INT_LVP",
                          "quantity": round(repair_area), "notes": "Install new"})
            items.append({"category": "DEM", "xact_code": "DEM_BASEBOARD",
                          "quantity": round(math.sqrt(repair_area) * 4),
                          "notes": "Remove baseboard"})
            items.append({"category": "INT", "xact_code": "INT_BASEBOARD",
                          "quantity": round(math.sqrt(repair_area) * 4),
                          "notes": "Install baseboard"})

        elif component == "door":
            items.append({"category": "EXD", "xact_code": "EXD_ENTRY_STD",
                          "quantity": 1, "notes": "Replace entry door"})

        # Water mitigation items if water damage
        if photo.damage_type == "water" and repair_action in ("replace", "repair"):
            items.append({"category": "WTR", "xact_code": "WTR_EXTRACT",
                          "quantity": round(affected_area), "notes": "Water extraction"})
            items.append({"category": "WTR", "xact_code": "WTR_DRY_STRUCT",
                          "quantity": 3, "notes": "3 days structural drying"})
            items.append({"category": "WTR", "xact_code": "WTR_DEHUMIDIFIER",
                          "quantity": 3, "notes": "3 days dehumidifier"})
            items.append({"category": "WTR", "xact_code": "WTR_AIR_MOVER",
                          "quantity": 3, "notes": "3 days air movers"})
            items.append({"category": "WTR", "xact_code": "WTR_ANTIMICROBIAL",
                          "quantity": round(affected_area), "notes": "Prevent mold"})

        return items

    def _general_conditions_items(
        self, report: PropertyLossReport, line_num: int
    ) -> list[dict]:
        """Add general conditions items (permits, dumpsters, etc.)."""
        items = []

        # Permit if significant work
        if report.overall_severity in ("severe", "critical"):
            items.append({"category": "GEN", "xact_code": "GEN_PERMIT",
                          "quantity": 1, "notes": "Building permit required"})

        # Dumpster
        items.append({"category": "GEN", "xact_code": "GEN_DUMPSTER",
                      "quantity": 1, "notes": "Debris removal"})

        # Debris haul
        items.append({"category": "GEN", "xact_code": "DEM_DEBRIS",
                      "quantity": 1, "notes": "Haul to landfill"})

        return items

    # ------------------------------------------------------------------
    # Step 4: Financial calculations
    # ------------------------------------------------------------------

    def _compute_financials(self, report: PropertyLossReport):
        """Compute O&P, depreciation, ACV/RCV."""

        report.total_material = sum(
            c.subtotal_material for c in report.category_summaries
        )
        report.total_labor = sum(
            c.subtotal_labor for c in report.category_summaries
        )
        report.subtotal = sum(c.subtotal for c in report.category_summaries)

        # Overhead & Profit (standard 10% + 10%)
        report.overhead_amount = round(report.subtotal * report.overhead_percent / 100, 2)
        report.profit_amount = round(
            (report.subtotal + report.overhead_amount) * report.profit_percent / 100, 2
        )

        # Replacement Cost Value
        report.replacement_cost_value = round(
            report.subtotal + report.overhead_amount + report.profit_amount, 2
        )

        # Total depreciation
        report.total_depreciation = sum(
            c.depreciation for c in report.category_summaries
        )

        # Actual Cash Value
        report.actual_cash_value = round(
            report.replacement_cost_value - report.total_depreciation, 2
        )

        # Net claim
        report.net_claim = round(
            max(0, report.actual_cash_value - report.deductible), 2
        )

        # Grand total (RCV)
        report.grand_total = report.replacement_cost_value

    # ------------------------------------------------------------------
    # Step 5: HTML report generation
    # ------------------------------------------------------------------

    def _generate_report_html(self, report: PropertyLossReport) -> str:
        """Generate professional Xactimate-style HTML report."""

        # Category line items
        estimate_html = ""
        for cat in report.category_summaries:
            estimate_html += f"""
            <tr class="category-header">
              <td colspan="7"><strong>{cat.code} - {cat.name}</strong></td>
            </tr>"""
            for item in cat.line_items:
                estimate_html += f"""
            <tr>
              <td>{item.line_number}</td>
              <td>{item.description}</td>
              <td class="num">{item.quantity:,.1f} {item.unit}</td>
              <td class="num">${item.material_cost:,.2f}</td>
              <td class="num">${item.labor_cost:,.2f}</td>
              <td class="num">${item.total_cost:,.2f}</td>
              <td class="num">${item.depreciation_amt:,.2f}</td>
            </tr>"""
            estimate_html += f"""
            <tr class="subtotal-row">
              <td colspan="3" style="text-align:right;"><em>{cat.name} Subtotal</em></td>
              <td class="num"><em>${cat.subtotal_material:,.2f}</em></td>
              <td class="num"><em>${cat.subtotal_labor:,.2f}</em></td>
              <td class="num"><em>${cat.subtotal:,.2f}</em></td>
              <td class="num"><em>${cat.depreciation:,.2f}</em></td>
            </tr>"""

        # Photo gallery
        photos_html = ""
        for i, photo in enumerate(report.photos):
            if photo.damage_detected:
                sev_color = {
                    "minor": "#4CAF50", "moderate": "#FF9800",
                    "severe": "#F44336", "critical": "#9C27B0",
                }.get(photo.damage_severity, "#666")

                photos_html += f"""
            <div class="photo-card">
              <div class="photo-header" style="border-left:4px solid {sev_color};">
                <strong>Photo {i + 1}</strong> &mdash;
                <span style="color:{sev_color};text-transform:capitalize;">
                  {photo.damage_severity} {photo.damage_type}</span>
                <span class="confidence">({photo.confidence:.0%} confidence)</span>
              </div>
              <p class="photo-desc">{photo.description}</p>
              <p class="photo-component">
                Component: <strong>{photo.affected_component}</strong>
              </p>
            </div>"""

        # Depreciation schedule
        dep_html = ""
        for cat in report.category_summaries:
            if cat.depreciation > 0:
                for item in cat.line_items:
                    if item.depreciation_amt > 0:
                        dep_html += f"""
            <tr>
              <td>{item.description}</td>
              <td class="num">${item.total_cost:,.2f}</td>
              <td class="num">{item.depreciation_pct:.1f}%</td>
              <td class="num">${item.depreciation_amt:,.2f}</td>
              <td class="num">${item.acv_amount:,.2f}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Property Loss Estimate - {report.claim_number}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif;
         color: #212121; background: #f5f5f5; font-size: 12px; }}

  @media print {{
    body {{ background: white; font-size: 11px; }}
    .page {{ page-break-after: always; box-shadow: none !important;
             margin: 0 !important; }}
    .no-print {{ display: none !important; }}
    * {{ -webkit-print-color-adjust: exact !important;
         print-color-adjust: exact !important; }}
  }}

  .page {{
    width: 8.5in; min-height: 11in; margin: 16px auto;
    padding: 0.5in 0.6in; background: white;
    box-shadow: 0 1px 8px rgba(0,0,0,0.1);
  }}

  h1 {{ font-size: 20px; color: #1565C0; margin-bottom: 2px; }}
  h2 {{ font-size: 15px; color: #1976D2; margin-bottom: 8px;
       border-bottom: 2px solid #BBDEFB; padding-bottom: 4px; }}
  h3 {{ font-size: 13px; color: #1E88E5; margin: 10px 0 6px; }}

  .header {{
    display: flex; justify-content: space-between;
    border-bottom: 3px solid #1565C0; padding-bottom: 12px;
    margin-bottom: 16px;
  }}
  .header .title {{ font-size: 22px; font-weight: 700; color: #0D47A1; }}
  .header .claim-num {{ font-size: 16px; color: #1565C0; font-weight: 600; }}
  .header .date {{ font-size: 11px; color: #666; }}

  .info-grid {{
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 16px; margin-bottom: 16px;
  }}
  .info-box {{
    background: #F5F9FF; border: 1px solid #BBDEFB;
    border-radius: 6px; padding: 10px 14px;
  }}
  .info-box label {{
    font-size: 10px; color: #1976D2; text-transform: uppercase;
    letter-spacing: 0.5px; display: block; margin-bottom: 2px;
  }}
  .info-box .value {{ font-size: 13px; font-weight: 500; }}

  table {{ width: 100%; border-collapse: collapse; margin-bottom: 14px; }}
  th {{
    background: #E3F2FD; color: #0D47A1; padding: 6px 8px;
    text-align: left; font-size: 10px; text-transform: uppercase;
    letter-spacing: 0.3px; border-bottom: 2px solid #90CAF9;
  }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #E3F2FD; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}

  .category-header {{
    background: #E8EAF6 !important;
  }}
  .category-header td {{ font-weight: 600; color: #283593;
                         border-bottom: 2px solid #9FA8DA; }}

  .subtotal-row {{ background: #F5F5F5; }}
  .subtotal-row td {{ border-top: 1px solid #BDBDBD; }}

  .total-row {{ background: #E3F2FD !important; font-weight: 700; }}
  .total-row td {{ border-top: 2px solid #1565C0; font-size: 13px; }}

  .grand-total {{ background: #0D47A1 !important; color: white !important; }}
  .grand-total td {{ color: white; font-size: 14px; font-weight: 700; }}

  .summary-grid {{
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 10px; margin: 16px 0;
  }}
  .summary-card {{
    background: #F5F9FF; border: 1px solid #BBDEFB;
    border-radius: 6px; padding: 10px; text-align: center;
  }}
  .summary-card .value {{
    font-size: 20px; font-weight: 700; color: #0D47A1;
  }}
  .summary-card .label {{
    font-size: 10px; color: #1976D2; text-transform: uppercase;
  }}

  .photo-card {{
    background: #FAFAFA; border: 1px solid #E0E0E0;
    border-radius: 6px; padding: 10px; margin-bottom: 8px;
  }}
  .photo-header {{ font-size: 12px; padding: 4px 8px; margin-bottom: 4px; }}
  .photo-desc {{ font-size: 11px; color: #424242; margin: 4px 0; }}
  .photo-component {{ font-size: 11px; color: #666; }}
  .confidence {{ font-size: 10px; color: #999; }}

  .severity-badge {{
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 10px; font-weight: 600; text-transform: uppercase;
  }}
  .sev-minor {{ background: #E8F5E9; color: #2E7D32; }}
  .sev-moderate {{ background: #FFF3E0; color: #E65100; }}
  .sev-severe {{ background: #FFEBEE; color: #C62828; }}
  .sev-critical {{ background: #F3E5F5; color: #6A1B9A; }}

  .footer {{
    text-align: center; font-size: 9px; color: #999;
    margin-top: 12px; padding-top: 8px;
    border-top: 1px solid #E0E0E0;
  }}

  .disclaimer {{
    background: #FFF8E1; border: 1px solid #FFE082;
    border-radius: 4px; padding: 8px 12px; margin-top: 12px;
    font-size: 10px; color: #F57F17;
  }}

  .print-btn {{
    position: fixed; top: 16px; right: 16px; z-index: 999;
    background: #1565C0; color: white; border: none;
    padding: 10px 20px; border-radius: 6px; cursor: pointer;
    font-size: 14px; font-weight: 600;
  }}
  .print-btn:hover {{ background: #0D47A1; }}
</style>
</head>
<body>

<button class="print-btn no-print" onclick="window.print()">Print / Save PDF</button>

<!-- =================== PAGE 1: CLAIM SUMMARY =================== -->
<div class="page">
  <div class="header">
    <div>
      <div class="title">PROPERTY LOSS ESTIMATE</div>
      <div style="font-size:12px;color:#666;">Scope of Loss &amp; Repair Estimate</div>
    </div>
    <div style="text-align:right;">
      <div class="claim-num">{report.claim_number}</div>
      <div class="date">{datetime.now().strftime('%B %d, %Y')}</div>
      <span class="severity-badge sev-{report.overall_severity}">
        {report.overall_severity.upper()}
      </span>
    </div>
  </div>

  <div class="info-grid">
    <div class="info-box">
      <label>Property</label>
      <div class="value">{report.address}</div>
      <div style="font-size:11px;color:#666;">
        {report.city}{f', {report.state}' if report.state else ''}
        {f' {report.postal_code}' if report.postal_code else ''}
      </div>
    </div>
    <div class="info-box">
      <label>Homeowner</label>
      <div class="value">{report.homeowner_name or 'N/A'}</div>
      <div style="font-size:11px;color:#666;">
        {report.homeowner_phone or ''}
        {f' | {report.homeowner_email}' if report.homeowner_email else ''}
      </div>
    </div>
    <div class="info-box">
      <label>Date of Loss</label>
      <div class="value">{report.date_of_loss}</div>
      <div style="font-size:11px;color:#666;">
        Cause: <strong>{report.cause_of_loss or report.primary_damage_type}</strong>
      </div>
    </div>
    <div class="info-box">
      <label>Insurance</label>
      <div class="value">{report.insurance_company or 'N/A'}</div>
      <div style="font-size:11px;color:#666;">
        Policy: {report.policy_number or 'N/A'}
        {f' | Adjuster: {report.adjuster_name}' if report.adjuster_name else ''}
      </div>
    </div>
  </div>

  <div class="summary-grid">
    <div class="summary-card">
      <div class="value">${report.replacement_cost_value:,.2f}</div>
      <div class="label">RCV (Replacement)</div>
    </div>
    <div class="summary-card">
      <div class="value">${report.total_depreciation:,.2f}</div>
      <div class="label">Depreciation</div>
    </div>
    <div class="summary-card">
      <div class="value">${report.actual_cash_value:,.2f}</div>
      <div class="label">ACV (Actual Cash)</div>
    </div>
    <div class="summary-card">
      <div class="value">${report.net_claim:,.2f}</div>
      <div class="label">Net Claim</div>
    </div>
  </div>

  <h2>Damage Assessment Summary</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
    <div>
      <p><strong>Primary Damage:</strong>
        {DAMAGE_TYPES.get(report.primary_damage_type, {}).get('label', report.primary_damage_type)}</p>
      <p><strong>Overall Severity:</strong>
        <span class="severity-badge sev-{report.overall_severity}">
          {report.overall_severity}</span></p>
      <p><strong>Photos Analyzed:</strong> {len(report.photos)}</p>
      <p><strong>Damage Detected In:</strong> {len([p for p in report.photos if p.damage_detected])} photos</p>
    </div>
    <div>
      <p><strong>Affected Areas:</strong></p>
      <ul style="margin-left:16px;font-size:11px;">
        {''.join(f'<li>{a}</li>' for a in report.affected_areas)}
      </ul>
      {f'<p><strong>Roof Area:</strong> {report.roof_area_sqft:,.0f} SF ({report.roof_pitch_ratio})</p>' if report.roof_area_sqft else ''}
    </div>
  </div>

  <h2>Photo Documentation</h2>
  {photos_html if photos_html else '<p style="color:#999;">No damage photos analyzed.</p>'}

  <div class="footer">
    Claim {report.claim_number} &bull; Generated {datetime.now().strftime('%B %d, %Y')}
  </div>
</div>

<!-- =================== PAGE 2: LINE ITEM ESTIMATE =================== -->
<div class="page">
  <h1>LINE ITEM ESTIMATE</h1>
  <h2>{report.claim_number} &bull; Detailed Scope of Repairs</h2>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Description</th>
        <th>Quantity</th>
        <th>Material</th>
        <th>Labor</th>
        <th>Total</th>
        <th>Deprec.</th>
      </tr>
    </thead>
    <tbody>
      {estimate_html}
      <tr class="total-row">
        <td colspan="3" style="text-align:right;">Subtotal</td>
        <td class="num">${report.total_material:,.2f}</td>
        <td class="num">${report.total_labor:,.2f}</td>
        <td class="num">${report.subtotal:,.2f}</td>
        <td class="num">${report.total_depreciation:,.2f}</td>
      </tr>
      <tr>
        <td colspan="5" style="text-align:right;">
          Overhead ({report.overhead_percent:.0f}%)</td>
        <td class="num">${report.overhead_amount:,.2f}</td>
        <td></td>
      </tr>
      <tr>
        <td colspan="5" style="text-align:right;">
          Profit ({report.profit_percent:.0f}%)</td>
        <td class="num">${report.profit_amount:,.2f}</td>
        <td></td>
      </tr>
      <tr class="grand-total">
        <td colspan="5" style="text-align:right;">
          REPLACEMENT COST VALUE (RCV)</td>
        <td class="num">${report.replacement_cost_value:,.2f}</td>
        <td></td>
      </tr>
    </tbody>
  </table>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;">
    <div class="info-box">
      <h3>ACV Calculation</h3>
      <table style="font-size:11px;">
        <tr><td>Replacement Cost Value (RCV)</td>
            <td class="num">${report.replacement_cost_value:,.2f}</td></tr>
        <tr><td>Less: Depreciation</td>
            <td class="num">-${report.total_depreciation:,.2f}</td></tr>
        <tr style="font-weight:700;"><td>Actual Cash Value (ACV)</td>
            <td class="num">${report.actual_cash_value:,.2f}</td></tr>
        <tr><td>Less: Deductible</td>
            <td class="num">-${report.deductible:,.2f}</td></tr>
        <tr style="font-weight:700;border-top:2px solid #1565C0;">
            <td>NET CLAIM AMOUNT</td>
            <td class="num">${report.net_claim:,.2f}</td></tr>
      </table>
    </div>
    <div class="info-box">
      <h3>Cost Breakdown</h3>
      <table style="font-size:11px;">
        <tr><td>Materials</td>
            <td class="num">${report.total_material:,.2f}</td></tr>
        <tr><td>Labor</td>
            <td class="num">${report.total_labor:,.2f}</td></tr>
        <tr><td>Direct Cost</td>
            <td class="num">${report.subtotal:,.2f}</td></tr>
        <tr><td>Overhead</td>
            <td class="num">${report.overhead_amount:,.2f}</td></tr>
        <tr><td>Profit</td>
            <td class="num">${report.profit_amount:,.2f}</td></tr>
        <tr style="font-weight:700;border-top:2px solid #1565C0;">
            <td>Total (RCV)</td>
            <td class="num">${report.replacement_cost_value:,.2f}</td></tr>
      </table>
    </div>
  </div>

  <div class="footer">
    Pricing: US Average Market Rates (Xactimate-compatible) &bull;
    O&amp;P: {report.overhead_percent:.0f}% / {report.profit_percent:.0f}%
  </div>
</div>

<!-- =================== PAGE 3: DEPRECIATION SCHEDULE =================== -->
<div class="page">
  <h1>DEPRECIATION SCHEDULE</h1>
  <h2>{report.claim_number} &bull; ACV vs RCV Breakdown</h2>

  {'<table><thead><tr><th>Item</th><th>RCV</th><th>Dep. Rate</th><th>Depreciation</th><th>ACV</th></tr></thead><tbody>' + dep_html + '</tbody></table>' if dep_html else '<p style="color:#999;">No depreciable items in this estimate.</p>'}

  <div style="margin-top:24px;">
    <h2>Recoverable Depreciation</h2>
    <div class="info-box" style="max-width:400px;">
      <p style="font-size:12px;">Upon completion of repairs, the homeowner may
      recover the depreciation holdback from the insurance company.</p>
      <table style="font-size:12px;margin-top:8px;">
        <tr><td>Total Depreciation Held Back</td>
            <td class="num" style="font-weight:700;">
              ${report.total_depreciation:,.2f}</td></tr>
        <tr><td>Initial Payment (ACV - deductible)</td>
            <td class="num">${report.net_claim:,.2f}</td></tr>
        <tr style="border-top:2px solid #1565C0;font-weight:700;">
            <td>Total After Recovery (RCV - deductible)</td>
            <td class="num">
              ${max(0, report.replacement_cost_value - report.deductible):,.2f}</td>
        </tr>
      </table>
    </div>
  </div>

  <div class="disclaimer">
    <strong>Disclaimer:</strong> This estimate is generated using AI-assisted
    damage assessment and standard Xactimate-compatible pricing. Actual costs
    may vary based on local market conditions, material availability, and
    specific project requirements. This report should be reviewed by a
    licensed contractor and/or insurance adjuster before being used for
    claim settlement. Field verification of all damage is recommended.
  </div>

  <div class="footer">
    Generated by Envelope Estimator Agent &bull;
    {datetime.now().strftime('%B %d, %Y at %I:%M %p')} &bull;
    Report ID: {report.report_id}
  </div>
</div>

</body>
</html>"""

        return html

    # ------------------------------------------------------------------
    # Save outputs
    # ------------------------------------------------------------------

    def _save_report(self, report: PropertyLossReport):
        safe_addr = re.sub(r"[^\w\s-]", "", report.address).strip()[:40]
        base_name = f"{report.report_id}_{safe_addr}"

        # Save HTML
        html_path = self.output_dir / f"{base_name}.html"
        html_path.write_text(report.professional_report_html)
        logger.info(f"Saved loss report HTML: {html_path}")

        # Save JSON summary
        json_path = self.output_dir / f"{base_name}.json"
        summary = {
            "report_id": report.report_id,
            "claim_number": report.claim_number,
            "generated_at": report.generated_at,
            "address": report.address,
            "city": report.city,
            "state": report.state,
            "homeowner_name": report.homeowner_name,
            "date_of_loss": report.date_of_loss,
            "cause_of_loss": report.cause_of_loss,
            "primary_damage_type": report.primary_damage_type,
            "overall_severity": report.overall_severity,
            "affected_areas": report.affected_areas,
            "photos_analyzed": len(report.photos),
            "damage_photos": len([p for p in report.photos if p.damage_detected]),
            "categories": [
                {
                    "code": c.code,
                    "name": c.name,
                    "subtotal": c.subtotal,
                    "depreciation": c.depreciation,
                }
                for c in report.category_summaries
            ],
            "financials": {
                "total_material": report.total_material,
                "total_labor": report.total_labor,
                "subtotal": report.subtotal,
                "overhead": report.overhead_amount,
                "profit": report.profit_amount,
                "rcv": report.replacement_cost_value,
                "depreciation": report.total_depreciation,
                "acv": report.actual_cash_value,
                "deductible": report.deductible,
                "net_claim": report.net_claim,
            },
        }
        json_path.write_text(json.dumps(summary, indent=2))
        logger.info(f"Saved loss report JSON: {json_path}")
