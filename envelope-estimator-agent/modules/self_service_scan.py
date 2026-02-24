"""
Self-Service Scan → 5D Construction Cost Estimate Module

Zero-salesman pipeline:
1. Customer fills out intake form (web/API)
2. System generates a unique scan session + magic link
3. Customer receives link via email/SMS
4. Link opens guided scan portal (photo capture + measurements)
5. Customer submits photos/data through the portal
6. AI processes submission → damage/condition assessment
7. System auto-generates a full 5D estimate (3D scope + schedule + cost)
8. Customer receives professional estimate instantly

5D = 3D spatial model + time (schedule) + cost

No site visit required. Fully automated from intake to delivery.
"""

import hashlib
import json
import logging
import math
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

import anthropic

from config.settings import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and constants
# ---------------------------------------------------------------------------

class ProjectType(str, Enum):
    RESIDENTIAL_ROOF = "residential_roof"
    RESIDENTIAL_SIDING = "residential_siding"
    RESIDENTIAL_FULL_EXTERIOR = "residential_full_exterior"
    RESIDENTIAL_INTERIOR = "residential_interior"
    COMMERCIAL_ROOF = "commercial_roof"
    COMMERCIAL_EXTERIOR = "commercial_exterior"
    INSURANCE_CLAIM = "insurance_claim"
    NEW_CONSTRUCTION = "new_construction"
    RENOVATION = "renovation"


class ScanSessionStatus(str, Enum):
    CREATED = "created"
    LINK_SENT = "link_sent"
    CUSTOMER_OPENED = "customer_opened"
    SCAN_IN_PROGRESS = "scan_in_progress"
    SCAN_SUBMITTED = "scan_submitted"
    PROCESSING = "processing"
    ESTIMATE_READY = "estimate_ready"
    DELIVERED = "delivered"
    EXPIRED = "expired"


class ScanPhotoType(str, Enum):
    FRONT_ELEVATION = "front_elevation"
    REAR_ELEVATION = "rear_elevation"
    LEFT_ELEVATION = "left_elevation"
    RIGHT_ELEVATION = "right_elevation"
    ROOF_OVERVIEW = "roof_overview"
    CLOSE_UP_DAMAGE = "close_up_damage"
    INTERIOR_ROOM = "interior_room"
    MEASUREMENT_REFERENCE = "measurement_reference"
    MATERIAL_DETAIL = "material_detail"
    UTILITY_AREA = "utility_area"


# Guided photo requirements per project type
SCAN_REQUIREMENTS = {
    ProjectType.RESIDENTIAL_ROOF: {
        "required_photos": [
            {"type": ScanPhotoType.FRONT_ELEVATION, "label": "Front of house (full view)",
             "instructions": "Stand at the street and capture the entire front of the house including the roofline. Include a reference object (car, person) for scale."},
            {"type": ScanPhotoType.REAR_ELEVATION, "label": "Back of house (full view)",
             "instructions": "Capture the full rear elevation showing the complete roofline and any dormers or valleys."},
            {"type": ScanPhotoType.LEFT_ELEVATION, "label": "Left side of house",
             "instructions": "Capture the entire left side showing roof slope and any penetrations (vents, pipes)."},
            {"type": ScanPhotoType.RIGHT_ELEVATION, "label": "Right side of house",
             "instructions": "Capture the entire right side showing roof slope and any penetrations."},
            {"type": ScanPhotoType.ROOF_OVERVIEW, "label": "Roof close-up (from ground)",
             "instructions": "Zoom in on the roof surface. We need to see the material type (shingles, metal, tile) and condition."},
        ],
        "optional_photos": [
            {"type": ScanPhotoType.CLOSE_UP_DAMAGE, "label": "Any visible damage",
             "instructions": "If you see any damage (missing shingles, dents, cracks), take a close-up photo."},
            {"type": ScanPhotoType.UTILITY_AREA, "label": "Gutters and downspouts",
             "instructions": "Capture the gutter system showing condition and any damage."},
        ],
        "min_required": 4,
        "measurements_needed": ["approx_square_footage", "number_of_stories", "garage_count"],
    },
    ProjectType.RESIDENTIAL_SIDING: {
        "required_photos": [
            {"type": ScanPhotoType.FRONT_ELEVATION, "label": "Front of house",
             "instructions": "Full front view showing all siding, trim, and windows."},
            {"type": ScanPhotoType.REAR_ELEVATION, "label": "Back of house",
             "instructions": "Full rear view showing all siding surfaces."},
            {"type": ScanPhotoType.LEFT_ELEVATION, "label": "Left side",
             "instructions": "Full left side showing siding from foundation to soffit."},
            {"type": ScanPhotoType.RIGHT_ELEVATION, "label": "Right side",
             "instructions": "Full right side showing siding from foundation to soffit."},
            {"type": ScanPhotoType.MATERIAL_DETAIL, "label": "Siding close-up",
             "instructions": "Close-up of the siding material showing profile, condition, and color."},
        ],
        "optional_photos": [
            {"type": ScanPhotoType.CLOSE_UP_DAMAGE, "label": "Damage areas",
             "instructions": "Photos of any damaged, rotted, or deteriorated siding sections."},
        ],
        "min_required": 4,
        "measurements_needed": ["approx_square_footage", "number_of_stories", "wall_height_estimate"],
    },
    ProjectType.RESIDENTIAL_FULL_EXTERIOR: {
        "required_photos": [
            {"type": ScanPhotoType.FRONT_ELEVATION, "label": "Front elevation (full)",
             "instructions": "Full front view from the street — capture roof, siding, windows, doors, and landscaping line."},
            {"type": ScanPhotoType.REAR_ELEVATION, "label": "Rear elevation (full)",
             "instructions": "Full rear view showing all exterior components."},
            {"type": ScanPhotoType.LEFT_ELEVATION, "label": "Left elevation",
             "instructions": "Full left side from foundation to ridge."},
            {"type": ScanPhotoType.RIGHT_ELEVATION, "label": "Right elevation",
             "instructions": "Full right side from foundation to ridge."},
            {"type": ScanPhotoType.ROOF_OVERVIEW, "label": "Roof surface detail",
             "instructions": "Close-up of roof material. Show condition of shingles/metal/tile."},
            {"type": ScanPhotoType.MATERIAL_DETAIL, "label": "Siding material detail",
             "instructions": "Close-up of siding. Show profile type, condition, fasteners."},
        ],
        "optional_photos": [
            {"type": ScanPhotoType.CLOSE_UP_DAMAGE, "label": "Damage photos (any area)",
             "instructions": "Close-ups of any damage to any exterior component."},
            {"type": ScanPhotoType.UTILITY_AREA, "label": "Gutters, soffit, fascia",
             "instructions": "Photos of gutter system, soffit, and fascia board condition."},
            {"type": ScanPhotoType.MEASUREMENT_REFERENCE, "label": "Window/door detail",
             "instructions": "Close-up of a window showing frame condition and type. Include a tape measure if possible."},
        ],
        "min_required": 5,
        "measurements_needed": [
            "approx_square_footage", "number_of_stories", "garage_count",
            "window_count_approx", "exterior_door_count",
        ],
    },
    ProjectType.INSURANCE_CLAIM: {
        "required_photos": [
            {"type": ScanPhotoType.FRONT_ELEVATION, "label": "Full property view",
             "instructions": "Full front view showing the overall property and visible damage areas."},
            {"type": ScanPhotoType.CLOSE_UP_DAMAGE, "label": "Primary damage area #1",
             "instructions": "Close-up of the most significant damage. Include a ruler or coin for scale."},
            {"type": ScanPhotoType.CLOSE_UP_DAMAGE, "label": "Primary damage area #2",
             "instructions": "Close-up of the second most significant damage area."},
            {"type": ScanPhotoType.MATERIAL_DETAIL, "label": "Affected material close-up",
             "instructions": "Close-up showing the damaged material type and brand if visible."},
        ],
        "optional_photos": [
            {"type": ScanPhotoType.REAR_ELEVATION, "label": "Rear view"},
            {"type": ScanPhotoType.LEFT_ELEVATION, "label": "Left side damage"},
            {"type": ScanPhotoType.RIGHT_ELEVATION, "label": "Right side damage"},
            {"type": ScanPhotoType.INTERIOR_ROOM, "label": "Interior damage (if applicable)"},
        ],
        "min_required": 3,
        "measurements_needed": ["approx_square_footage", "number_of_stories", "cause_of_damage"],
    },
}

# Default scan requirements for project types without specific config
DEFAULT_SCAN_REQUIREMENTS = {
    "required_photos": [
        {"type": ScanPhotoType.FRONT_ELEVATION, "label": "Front view of project area",
         "instructions": "Full view of the primary area of work."},
        {"type": ScanPhotoType.REAR_ELEVATION, "label": "Rear/opposite view",
         "instructions": "View from the opposite side."},
        {"type": ScanPhotoType.MATERIAL_DETAIL, "label": "Material close-up",
         "instructions": "Close-up of existing materials showing condition."},
    ],
    "optional_photos": [
        {"type": ScanPhotoType.CLOSE_UP_DAMAGE, "label": "Problem areas"},
        {"type": ScanPhotoType.MEASUREMENT_REFERENCE, "label": "Measurements"},
    ],
    "min_required": 2,
    "measurements_needed": ["approx_square_footage", "project_description"],
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CustomerIntakeForm:
    """Data submitted by customer through the intake form."""
    # Contact
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    company_name: str = ""

    # Property
    property_address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    property_type: str = "residential"  # residential / commercial / industrial

    # Project
    project_type: ProjectType = ProjectType.RESIDENTIAL_FULL_EXTERIOR
    project_description: str = ""
    urgency: str = "standard"  # standard / priority / emergency
    preferred_start_date: str = ""
    budget_range: str = ""  # "under_10k", "10k_25k", "25k_50k", "50k_100k", "over_100k"

    # Insurance (if applicable)
    is_insurance_claim: bool = False
    insurance_company: str = ""
    policy_number: str = ""
    claim_number: str = ""
    cause_of_loss: str = ""
    date_of_loss: str = ""

    # Consent
    agreed_to_terms: bool = False
    marketing_opt_in: bool = False


@dataclass
class ScanPhoto:
    """A photo submitted through the scan portal."""
    photo_type: ScanPhotoType
    file_path: str
    label: str = ""
    timestamp: str = ""
    gps_latitude: float = 0.0
    gps_longitude: float = 0.0
    compass_heading: float = 0.0  # degrees, 0=N
    device_tilt: float = 0.0  # degrees from horizontal


@dataclass
class ScanMeasurement:
    """A measurement entered by the customer."""
    field_name: str
    value: str
    unit: str = ""


@dataclass
class ScanSubmission:
    """Complete customer scan submission."""
    session_id: str
    photos: list[ScanPhoto] = field(default_factory=list)
    measurements: list[ScanMeasurement] = field(default_factory=list)
    notes: str = ""
    submitted_at: str = ""
    device_info: str = ""  # browser/device user agent


@dataclass
class FiveDLineItem:
    """A single line item in the 5D estimate."""
    category: str           # e.g., "Roofing", "Siding", "Windows"
    component: str          # e.g., "3-tab shingle removal and replacement"
    quantity: float
    unit: str               # SF, LF, EA, SQ
    unit_material_cost: float
    unit_labor_cost: float
    extended_material: float = 0.0
    extended_labor: float = 0.0
    extended_total: float = 0.0
    # Schedule dimension
    crew_size: int = 0
    hours_per_unit: float = 0.0
    total_labor_hours: float = 0.0
    task_duration_days: float = 0.0
    # Sequencing
    phase: str = ""
    predecessor_tasks: list[str] = field(default_factory=list)
    can_parallel: bool = False


@dataclass
class SchedulePhase:
    """A phase in the construction schedule."""
    phase_name: str
    phase_number: int
    tasks: list[str] = field(default_factory=list)
    start_day: int = 0
    end_day: int = 0
    duration_days: int = 0
    crew_type: str = ""
    crew_size: int = 0


@dataclass
class FiveDEstimate:
    """Complete 5D construction cost estimate.

    5D = 3D (spatial scope) + time (schedule) + cost
    """
    # Identity
    estimate_id: str = ""
    session_id: str = ""
    generated_at: str = ""

    # Customer
    customer_name: str = ""
    property_address: str = ""

    # 3D Scope
    project_type: str = ""
    scope_summary: str = ""
    total_area_sf: float = 0.0
    building_footprint_sf: float = 0.0
    stories: int = 1
    roof_pitch: str = ""
    exterior_wall_sf: float = 0.0

    # Line items
    line_items: list[FiveDLineItem] = field(default_factory=list)

    # Cost summary
    subtotal_materials: float = 0.0
    subtotal_labor: float = 0.0
    subtotal_equipment: float = 0.0
    subtotal_direct: float = 0.0
    overhead_percent: float = 0.10
    overhead_amount: float = 0.0
    profit_percent: float = 0.10
    profit_amount: float = 0.0
    tax_amount: float = 0.0
    grand_total: float = 0.0
    cost_per_sf: float = 0.0

    # Schedule (4th dimension)
    schedule_phases: list[SchedulePhase] = field(default_factory=list)
    total_project_days: int = 0
    estimated_start: str = ""
    estimated_completion: str = ""
    total_labor_hours: float = 0.0

    # Quality / confidence
    confidence_score: float = 0.0  # 0-1
    data_quality_notes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    # AI analysis
    condition_assessment: str = ""
    damage_findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    # Output files
    report_html_path: str = ""
    report_json_path: str = ""


@dataclass
class ScanSession:
    """A self-service scan session tracking the full lifecycle."""
    session_id: str = ""
    token: str = ""  # secure token for the magic link
    status: ScanSessionStatus = ScanSessionStatus.CREATED
    created_at: str = ""
    expires_at: str = ""
    scan_link: str = ""

    # Customer data
    intake: CustomerIntakeForm = field(default_factory=CustomerIntakeForm)

    # Scan data
    submission: Optional[ScanSubmission] = None

    # Result
    estimate: Optional[FiveDEstimate] = None

    # Tracking
    link_sent_at: str = ""
    opened_at: str = ""
    submitted_at: str = ""
    estimated_at: str = ""
    delivered_at: str = ""


# ---------------------------------------------------------------------------
# Photo analysis prompts
# ---------------------------------------------------------------------------

PHOTO_ANALYSIS_SYSTEM_PROMPT = """You are an expert construction estimator and property inspector with 30+ years
of experience in residential and commercial construction. You are analyzing photos
submitted by a homeowner/property owner through a self-service scan portal.

Your job is to extract every possible measurement, material identification, condition
assessment, and construction detail from these photos to generate an accurate
construction cost estimate WITHOUT a physical site visit.

Be extremely thorough. Construction estimates live or die on accurate quantities."""


def _build_photo_analysis_prompt(
    project_type: ProjectType,
    measurements: list[ScanMeasurement],
) -> str:
    """Build the Claude Vision prompt for analyzing scan photos."""
    measurement_context = ""
    if measurements:
        measurement_context = "\n\nCustomer-provided measurements:\n"
        for m in measurements:
            measurement_context += f"- {m.field_name}: {m.value} {m.unit}\n"

    return f"""Analyze these property photos for a {project_type.value.replace('_', ' ')} project.
{measurement_context}

Extract and return a JSON object with the following structure:

{{
    "property_assessment": {{
        "building_type": "single_family | multi_family | commercial | ...",
        "stories": <int>,
        "estimated_footprint_sf": <float>,
        "estimated_total_sf": <float>,
        "architectural_style": "<style>",
        "year_built_estimate": "<decade or range>"
    }},
    "roof_analysis": {{
        "material_type": "3-tab shingle | architectural shingle | metal standing seam | tile | flat/TPO | ...",
        "estimated_pitch": "<X/12>",
        "pitch_multiplier": <float>,
        "estimated_roof_sf": <float>,
        "number_of_facets": <int>,
        "complexity": "simple_gable | cross_gable | hip | complex_hip_valley | mansard",
        "condition": "good | fair | poor | failed",
        "damage_observed": ["<description>", ...],
        "penetrations": ["<vents, pipes, skylights, chimney>"],
        "ridge_length_ft": <float>,
        "eave_length_ft": <float>,
        "valley_count": <int>
    }},
    "exterior_walls": {{
        "primary_material": "vinyl siding | fiber cement | wood | brick | stucco | stone | ...",
        "secondary_material": "<if mixed>",
        "estimated_wall_sf": <float>,
        "condition": "good | fair | poor",
        "damage_observed": ["<description>", ...],
        "wall_height_ft": <float>
    }},
    "windows_doors": {{
        "window_count": <int>,
        "avg_window_size": "<WxH>",
        "window_type": "single hung | double hung | casement | sliding | ...",
        "window_material": "vinyl | wood | aluminum | ...",
        "door_count": <int>,
        "door_types": ["<entry door, sliding glass, garage, ...>"],
        "garage_doors": <int>,
        "condition": "good | fair | poor"
    }},
    "gutters_downspouts": {{
        "gutter_material": "aluminum | copper | vinyl | steel",
        "gutter_style": "K-style | half-round | box",
        "estimated_linear_ft": <float>,
        "downspout_count": <int>,
        "condition": "good | fair | poor"
    }},
    "additional_components": {{
        "soffit_type": "<material>",
        "fascia_type": "<material>",
        "trim_type": "<material>",
        "deck_porch": "<description or null>",
        "fencing": "<description or null>",
        "landscaping_notes": "<anything affecting access or work>"
    }},
    "damage_assessment": {{
        "damage_present": true | false,
        "damage_type": "hail | wind | water | fire | age | impact | none",
        "severity": "minor | moderate | severe | critical",
        "affected_components": ["roof", "siding", "gutters", ...],
        "detailed_findings": ["<finding 1>", "<finding 2>", ...],
        "photos_with_damage": [<photo indices with damage visible>]
    }},
    "measurement_estimates": {{
        "confidence_level": "high | medium | low",
        "notes": ["<any caveats about photo quality or visibility>"],
        "reference_objects_used": ["<car, door, person, etc. used for scale>"]
    }},
    "scope_of_work": {{
        "recommended_repairs": ["<item 1>", "<item 2>", ...],
        "code_upgrades_needed": ["<item>", ...],
        "optional_improvements": ["<item>", ...]
    }}
}}

Be as precise as possible with quantities. Use reference objects in the photos
(doors are ~6'8" tall, garage doors ~7-8' tall, standard windows ~3'x4',
cars ~15' long) to estimate dimensions. If you cannot determine something,
provide your best estimate and note the uncertainty."""


ESTIMATE_GENERATION_PROMPT = """You are a senior construction estimator generating a 5D cost estimate
(3D spatial scope + schedule + cost) from AI-analyzed property data.

Given the property analysis below, generate a complete construction estimate as JSON.

Use current {region} market rates for materials and labor. Apply standard
waste factors: roofing 15%, siding 10%, trim 10%, flat materials 5%.

PROPERTY ANALYSIS:
{analysis_json}

PROJECT TYPE: {project_type}
CUSTOMER NOTES: {customer_notes}

Generate a JSON response with this structure:

{{
    "scope_summary": "<1-2 sentence project description>",
    "line_items": [
        {{
            "category": "<trade category>",
            "component": "<specific work item description>",
            "quantity": <float>,
            "unit": "SF | LF | EA | SQ | HR",
            "unit_material_cost": <float>,
            "unit_labor_cost": <float>,
            "crew_size": <int>,
            "hours_per_unit": <float>,
            "phase": "demolition | preparation | installation | finishing | cleanup",
            "can_parallel": <bool>,
            "predecessor_tasks": ["<task that must complete first>"]
        }},
        ...
    ],
    "schedule": {{
        "phases": [
            {{
                "phase_name": "<name>",
                "phase_number": <int>,
                "tasks": ["<task descriptions>"],
                "duration_days": <int>,
                "crew_type": "<roofing crew | siding crew | general labor | ...>",
                "crew_size": <int>
            }}
        ],
        "total_project_days": <int>,
        "weather_contingency_days": <int>
    }},
    "assumptions": ["<assumption 1>", "<assumption 2>", ...],
    "recommendations": ["<recommendation 1>", ...],
    "confidence_score": <float 0-1>,
    "confidence_notes": ["<note about data quality>"]
}}

Price every component needed for a complete, code-compliant project. Include
tear-off/demolition, materials, labor, equipment, permits, dumpster, and cleanup.
Do NOT include overhead/profit — those are applied separately."""


# ---------------------------------------------------------------------------
# Main module
# ---------------------------------------------------------------------------

class SelfServiceScanManager:
    """Manages the full self-service scan → 5D estimate pipeline."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic.api_key)
        self.output_dir = Path(settings.output_dir) / "self_service"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir = self.output_dir / "sessions"
        self.sessions_dir.mkdir(exist_ok=True)

        # Base URL for scan portal (configured per deployment)
        self.portal_base_url = "https://scan.envelopeestimator.com"

    # ------------------------------------------------------------------
    # Step 1: Create scan session from intake form
    # ------------------------------------------------------------------

    def create_session(
        self,
        intake: CustomerIntakeForm,
        expiry_hours: int = 72,
    ) -> ScanSession:
        """Create a new scan session from a customer intake form.

        Returns a ScanSession with a unique magic link for the customer.
        """
        # Generate secure session ID and token
        session_id = f"SS-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(6).upper()}"
        token = secrets.token_urlsafe(32)

        # Build magic link
        scan_link = f"{self.portal_base_url}/scan/{session_id}?token={token}"

        session = ScanSession(
            session_id=session_id,
            token=token,
            status=ScanSessionStatus.CREATED,
            created_at=datetime.now().isoformat(),
            expires_at=(datetime.now() + timedelta(hours=expiry_hours)).isoformat(),
            scan_link=scan_link,
            intake=intake,
        )

        # Persist session
        self._save_session(session)

        logger.info(f"Created scan session {session_id} for {intake.customer_name}")
        return session

    # ------------------------------------------------------------------
    # Step 2: Send scan link to customer
    # ------------------------------------------------------------------

    def send_scan_link(
        self,
        session: ScanSession,
        delivery_method: str = "email",  # email | sms | both
    ) -> dict:
        """Send the scan link to the customer via email and/or SMS.

        Returns delivery status dict.
        """
        scan_requirements = SCAN_REQUIREMENTS.get(
            session.intake.project_type, DEFAULT_SCAN_REQUIREMENTS
        )
        delivery_result = {"session_id": session.session_id, "channels": []}

        if delivery_method in ("email", "both") and session.intake.customer_email:
            email_result = self._send_scan_email(session, scan_requirements)
            delivery_result["channels"].append(email_result)

        if delivery_method in ("sms", "both") and session.intake.customer_phone:
            sms_result = self._send_scan_sms(session)
            delivery_result["channels"].append(sms_result)

        # Update session status
        session.status = ScanSessionStatus.LINK_SENT
        session.link_sent_at = datetime.now().isoformat()
        self._save_session(session)

        return delivery_result

    def _send_scan_email(self, session: ScanSession, requirements: dict) -> dict:
        """Compose and send the scan instruction email."""
        required_photos = requirements.get("required_photos", [])
        optional_photos = requirements.get("optional_photos", [])

        # Build photo checklist
        photo_checklist = ""
        for i, photo in enumerate(required_photos, 1):
            photo_checklist += f"  {i}. {photo['label']} (REQUIRED)\n"
            if "instructions" in photo:
                photo_checklist += f"     → {photo['instructions']}\n"
        for photo in optional_photos:
            photo_checklist += f"  • {photo['label']} (optional)\n"

        email_body = f"""Hi {session.intake.customer_name},

Thank you for your interest in getting a construction estimate for your property
at {session.intake.property_address}.

We can generate an accurate estimate without an on-site visit! Here's how:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STEP 1: Click the link below to open your scan portal
  STEP 2: Follow the guided photo instructions
  STEP 3: Enter the requested measurements
  STEP 4: Submit — your estimate generates instantly!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔗 YOUR SCAN LINK: {session.scan_link}

This link expires in 72 hours.

PHOTOS YOU'LL NEED:
{photo_checklist}

TIPS FOR BEST RESULTS:
  • Take photos during daylight hours
  • Stand back far enough to capture the full elevation
  • Hold phone level (not tilted up)
  • Include a reference object for scale (car, person, tape measure)
  • Take extra close-ups of any damage or problem areas

Once you submit your scan, our AI system will analyze your photos and generate
a detailed 5D estimate (scope + schedule + cost) within minutes.

Questions? Reply to this email or call us at {self.settings.company.phone}.

Best regards,
{self.settings.company.name}
"""
        # In production: integrate with SendGrid / SES / SMTP
        logger.info(f"Scan email composed for {session.intake.customer_email}")
        return {
            "channel": "email",
            "recipient": session.intake.customer_email,
            "subject": f"Your Property Scan Link — {session.intake.property_address}",
            "body": email_body,
            "status": "queued",
        }

    def _send_scan_sms(self, session: ScanSession) -> dict:
        """Compose and send the scan link via SMS."""
        sms_body = (
            f"Hi {session.intake.customer_name.split()[0]}! "
            f"Your property scan link is ready. "
            f"Tap to start: {session.scan_link} "
            f"— {self.settings.company.name}"
        )

        # In production: integrate with Twilio / AWS SNS
        logger.info(f"Scan SMS composed for {session.intake.customer_phone}")
        return {
            "channel": "sms",
            "recipient": session.intake.customer_phone,
            "body": sms_body,
            "status": "queued",
        }

    # ------------------------------------------------------------------
    # Step 3: Get scan portal configuration (served to frontend)
    # ------------------------------------------------------------------

    def get_scan_portal_config(self, session_id: str, token: str) -> dict:
        """Return the scan portal configuration for the frontend.

        This is called when the customer opens the scan link.
        Validates the token and returns photo requirements.
        """
        session = self._load_session(session_id)
        if not session:
            return {"error": "Session not found", "valid": False}

        if session.token != token:
            return {"error": "Invalid token", "valid": False}

        if datetime.fromisoformat(session.expires_at) < datetime.now():
            session.status = ScanSessionStatus.EXPIRED
            self._save_session(session)
            return {"error": "Session expired", "valid": False}

        # Mark as opened
        if session.status == ScanSessionStatus.LINK_SENT:
            session.status = ScanSessionStatus.CUSTOMER_OPENED
            session.opened_at = datetime.now().isoformat()
            self._save_session(session)

        # Get scan requirements for this project type
        requirements = SCAN_REQUIREMENTS.get(
            session.intake.project_type, DEFAULT_SCAN_REQUIREMENTS
        )

        return {
            "valid": True,
            "session_id": session_id,
            "customer_name": session.intake.customer_name,
            "property_address": session.intake.property_address,
            "project_type": session.intake.project_type.value,
            "required_photos": requirements["required_photos"],
            "optional_photos": requirements.get("optional_photos", []),
            "min_required_photos": requirements["min_required"],
            "measurements_needed": requirements.get("measurements_needed", []),
            "instructions": {
                "welcome": f"Welcome, {session.intake.customer_name.split()[0]}! "
                           f"Follow the steps below to scan your property at "
                           f"{session.intake.property_address}.",
                "photo_tips": [
                    "Take photos during daylight for best results",
                    "Stand far enough back to capture the full view",
                    "Hold your phone level — don't tilt up",
                    "Include a reference object (car, door, tape measure) for scale",
                    "More photos = more accurate estimate",
                ],
                "time_estimate": "5-10 minutes",
            },
        }

    # ------------------------------------------------------------------
    # Step 4: Process customer scan submission
    # ------------------------------------------------------------------

    def process_submission(self, submission: ScanSubmission) -> FiveDEstimate:
        """Process a completed scan submission and generate a 5D estimate.

        This is the core pipeline:
        1. Validate submission completeness
        2. Analyze photos with Claude Vision
        3. Cross-reference with satellite data (if address available)
        4. Generate 5D estimate (scope + schedule + cost)
        5. Produce professional report
        """
        session = self._load_session(submission.session_id)
        if not session:
            raise ValueError(f"Session {submission.session_id} not found")

        session.submission = submission
        session.status = ScanSessionStatus.PROCESSING
        session.submitted_at = datetime.now().isoformat()
        self._save_session(session)

        logger.info(
            f"Processing scan submission {submission.session_id}: "
            f"{len(submission.photos)} photos, "
            f"{len(submission.measurements)} measurements"
        )

        # Step 4a: Validate submission
        print(f"\n[1/5] Validating submission...")
        validation = self._validate_submission(session, submission)
        if not validation["valid"]:
            logger.warning(f"Submission validation issues: {validation['issues']}")
        print(f"       Photos: {len(submission.photos)} | Measurements: {len(submission.measurements)}")
        if validation["issues"]:
            for issue in validation["issues"]:
                print(f"       NOTE: {issue}")

        # Step 4b: AI photo analysis
        print(f"\n[2/5] Analyzing photos with AI vision...")
        property_analysis = self._analyze_photos(session, submission)
        print(f"       Building type: {property_analysis.get('property_assessment', {}).get('building_type', 'N/A')}")
        print(f"       Stories: {property_analysis.get('property_assessment', {}).get('stories', 'N/A')}")
        print(f"       Condition: {property_analysis.get('damage_assessment', {}).get('severity', 'N/A')}")

        # Step 4c: Satellite cross-reference (if available)
        print(f"\n[3/5] Cross-referencing with satellite data...")
        satellite_data = self._get_satellite_crossref(session.intake.property_address)
        if satellite_data:
            property_analysis["satellite_crossref"] = satellite_data
            print(f"       Satellite footprint: {satellite_data.get('footprint_sf', 'N/A')} SF")
        else:
            print(f"       Satellite data: not available (using photo-only estimates)")

        # Step 4d: Generate 5D estimate
        print(f"\n[4/5] Generating 5D estimate (scope + schedule + cost)...")
        estimate = self._generate_5d_estimate(session, property_analysis)
        print(f"       Line items: {len(estimate.line_items)}")
        print(f"       Materials:  ${estimate.subtotal_materials:,.2f}")
        print(f"       Labor:      ${estimate.subtotal_labor:,.2f}")
        print(f"       Grand Total: ${estimate.grand_total:,.2f}")
        print(f"       Duration:   {estimate.total_project_days} days")
        print(f"       Confidence: {estimate.confidence_score:.0%}")

        # Step 4e: Generate report
        print(f"\n[5/5] Generating professional estimate report...")
        self._generate_report(session, estimate, property_analysis)
        print(f"       Report: {estimate.report_html_path}")

        # Update session
        session.estimate = estimate
        session.status = ScanSessionStatus.ESTIMATE_READY
        session.estimated_at = datetime.now().isoformat()
        self._save_session(session)

        return estimate

    # ------------------------------------------------------------------
    # Internal: Photo analysis with Claude Vision
    # ------------------------------------------------------------------

    def _analyze_photos(
        self,
        session: ScanSession,
        submission: ScanSubmission,
    ) -> dict:
        """Analyze all submitted photos with Claude Vision."""
        import base64

        # Build image content blocks
        content_blocks = []

        # Add text context
        prompt = _build_photo_analysis_prompt(
            session.intake.project_type,
            submission.measurements,
        )
        content_blocks.append({"type": "text", "text": prompt})

        # Add each photo as an image block
        for i, photo in enumerate(submission.photos):
            photo_path = Path(photo.file_path)
            if not photo_path.exists():
                logger.warning(f"Photo not found: {photo.file_path}")
                continue

            # Read and encode photo
            image_data = photo_path.read_bytes()
            b64_data = base64.b64encode(image_data).decode("utf-8")

            # Detect media type
            suffix = photo_path.suffix.lower()
            media_type_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".gif": "image/gif",
            }
            media_type = media_type_map.get(suffix, "image/jpeg")

            # Add label
            label = photo.label or photo.photo_type.value.replace("_", " ").title()
            content_blocks.append({
                "type": "text",
                "text": f"\n--- Photo {i+1}: {label} ---",
            })
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_data,
                },
            })

        # Call Claude Vision
        response = self.client.messages.create(
            model=self.settings.anthropic.model_vision,
            max_tokens=self.settings.anthropic.max_tokens,
            system=PHOTO_ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content_blocks}],
        )

        # Parse JSON response
        response_text = response.content[0].text
        json_match = _extract_json(response_text)
        if json_match:
            return json.loads(json_match)

        logger.error("Failed to parse photo analysis JSON")
        return {"error": "Failed to parse analysis", "raw": response_text}

    # ------------------------------------------------------------------
    # Internal: Satellite cross-reference
    # ------------------------------------------------------------------

    def _get_satellite_crossref(self, address: str) -> Optional[dict]:
        """Cross-reference photo analysis with satellite data if available.

        Uses Google Solar API for building footprint and roof data.
        """
        if not self.settings.google_api_key or not address:
            return None

        try:
            import requests

            # Geocode the address
            geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
            geo_resp = requests.get(geocode_url, params={
                "address": address,
                "key": self.settings.google_api_key,
            }, timeout=10)

            if geo_resp.status_code != 200:
                return None

            geo_data = geo_resp.json()
            if not geo_data.get("results"):
                return None

            location = geo_data["results"][0]["geometry"]["location"]
            lat, lng = location["lat"], location["lng"]

            # Get building insights from Solar API
            solar_url = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
            solar_resp = requests.get(solar_url, params={
                "location.latitude": lat,
                "location.longitude": lng,
                "requiredQuality": "MEDIUM",
                "key": self.settings.google_api_key,
            }, timeout=15)

            if solar_resp.status_code != 200:
                return None

            solar_data = solar_resp.json()
            solar_info = solar_data.get("solarPotential", {})

            # Extract building footprint and roof data
            roof_segments = solar_info.get("roofSegmentStats", [])
            total_area_m2 = sum(seg.get("stats", {}).get("areaMeters2", 0) for seg in roof_segments)
            total_area_sf = total_area_m2 * 10.7639

            avg_pitch = 0.0
            if roof_segments:
                pitches = [seg.get("pitchDegrees", 0) for seg in roof_segments]
                avg_pitch = sum(pitches) / len(pitches)

            return {
                "latitude": lat,
                "longitude": lng,
                "footprint_sf": round(total_area_sf, 0),
                "roof_segments": len(roof_segments),
                "avg_pitch_degrees": round(avg_pitch, 1),
                "source": "google_solar_api",
            }

        except Exception as e:
            logger.warning(f"Satellite cross-reference failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Internal: 5D estimate generation
    # ------------------------------------------------------------------

    def _generate_5d_estimate(
        self,
        session: ScanSession,
        property_analysis: dict,
    ) -> FiveDEstimate:
        """Generate a full 5D estimate from the property analysis."""
        prompt = ESTIMATE_GENERATION_PROMPT.format(
            region=self.settings.region.upper() if self.settings.region else "US",
            analysis_json=json.dumps(property_analysis, indent=2),
            project_type=session.intake.project_type.value.replace("_", " ").title(),
            customer_notes=session.intake.project_description or "None provided",
        )

        response = self.client.messages.create(
            model=self.settings.anthropic.model_vision,
            max_tokens=self.settings.anthropic.max_tokens,
            system=(
                "You are a senior construction estimator. Generate accurate, "
                "detailed cost estimates based on AI property analysis data. "
                "Use current market rates. Always respond with valid JSON."
            ),
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text
        json_match = _extract_json(response_text)

        if not json_match:
            logger.error("Failed to parse estimate JSON")
            return FiveDEstimate(
                estimate_id=f"EST-{session.session_id}",
                session_id=session.session_id,
                confidence_score=0.0,
                data_quality_notes=["Failed to generate estimate from analysis"],
            )

        estimate_data = json.loads(json_match)
        return self._build_estimate_from_ai(session, estimate_data, property_analysis)

    def _build_estimate_from_ai(
        self,
        session: ScanSession,
        estimate_data: dict,
        property_analysis: dict,
    ) -> FiveDEstimate:
        """Convert AI estimate JSON into a structured FiveDEstimate."""
        estimate = FiveDEstimate(
            estimate_id=f"EST-{session.session_id}",
            session_id=session.session_id,
            generated_at=datetime.now().isoformat(),
            customer_name=session.intake.customer_name,
            property_address=session.intake.property_address,
            project_type=session.intake.project_type.value,
            scope_summary=estimate_data.get("scope_summary", ""),
        )

        # Property dimensions from analysis
        prop = property_analysis.get("property_assessment", {})
        estimate.building_footprint_sf = prop.get("estimated_footprint_sf", 0)
        estimate.total_area_sf = prop.get("estimated_total_sf", 0)
        estimate.stories = prop.get("stories", 1)

        roof = property_analysis.get("roof_analysis", {})
        estimate.roof_pitch = roof.get("estimated_pitch", "")

        walls = property_analysis.get("exterior_walls", {})
        estimate.exterior_wall_sf = walls.get("estimated_wall_sf", 0)

        # Build line items
        for item_data in estimate_data.get("line_items", []):
            qty = item_data.get("quantity", 0)
            unit_mat = item_data.get("unit_material_cost", 0)
            unit_lab = item_data.get("unit_labor_cost", 0)
            hours_per_unit = item_data.get("hours_per_unit", 0)
            crew_size = item_data.get("crew_size", 2)

            total_hours = qty * hours_per_unit
            # Assume 8-hour work days
            task_days = math.ceil(total_hours / (8 * max(crew_size, 1))) if total_hours > 0 else 0

            line_item = FiveDLineItem(
                category=item_data.get("category", "General"),
                component=item_data.get("component", ""),
                quantity=qty,
                unit=item_data.get("unit", "EA"),
                unit_material_cost=unit_mat,
                unit_labor_cost=unit_lab,
                extended_material=round(qty * unit_mat, 2),
                extended_labor=round(qty * unit_lab, 2),
                extended_total=round(qty * (unit_mat + unit_lab), 2),
                crew_size=crew_size,
                hours_per_unit=hours_per_unit,
                total_labor_hours=round(total_hours, 1),
                task_duration_days=task_days,
                phase=item_data.get("phase", "installation"),
                predecessor_tasks=item_data.get("predecessor_tasks", []),
                can_parallel=item_data.get("can_parallel", False),
            )
            estimate.line_items.append(line_item)

        # Sum costs
        estimate.subtotal_materials = sum(li.extended_material for li in estimate.line_items)
        estimate.subtotal_labor = sum(li.extended_labor for li in estimate.line_items)
        estimate.subtotal_direct = estimate.subtotal_materials + estimate.subtotal_labor
        estimate.total_labor_hours = sum(li.total_labor_hours for li in estimate.line_items)

        # Apply markups
        estimate.overhead_percent = self.settings.company.overhead_percent
        estimate.profit_percent = self.settings.company.profit_percent
        estimate.overhead_amount = round(estimate.subtotal_direct * estimate.overhead_percent, 2)
        estimate.profit_amount = round(
            (estimate.subtotal_direct + estimate.overhead_amount) * estimate.profit_percent, 2
        )
        estimate.grand_total = round(
            estimate.subtotal_direct + estimate.overhead_amount + estimate.profit_amount, 2
        )

        if estimate.total_area_sf > 0:
            estimate.cost_per_sf = round(estimate.grand_total / estimate.total_area_sf, 2)

        # Build schedule
        schedule_data = estimate_data.get("schedule", {})
        for phase_data in schedule_data.get("phases", []):
            phase = SchedulePhase(
                phase_name=phase_data.get("phase_name", ""),
                phase_number=phase_data.get("phase_number", 0),
                tasks=phase_data.get("tasks", []),
                duration_days=phase_data.get("duration_days", 0),
                crew_type=phase_data.get("crew_type", ""),
                crew_size=phase_data.get("crew_size", 0),
            )
            estimate.schedule_phases.append(phase)

        estimate.total_project_days = schedule_data.get("total_project_days", 0)
        weather_days = schedule_data.get("weather_contingency_days", 0)
        estimate.total_project_days += weather_days

        # Confidence and notes
        estimate.confidence_score = estimate_data.get("confidence_score", 0.7)
        estimate.assumptions = estimate_data.get("assumptions", [])
        estimate.recommendations = estimate_data.get("recommendations", [])
        estimate.data_quality_notes = estimate_data.get("confidence_notes", [])

        # Damage findings from analysis
        damage = property_analysis.get("damage_assessment", {})
        estimate.condition_assessment = damage.get("severity", "not assessed")
        estimate.damage_findings = damage.get("detailed_findings", [])

        return estimate

    # ------------------------------------------------------------------
    # Internal: Report generation
    # ------------------------------------------------------------------

    def _generate_report(
        self,
        session: ScanSession,
        estimate: FiveDEstimate,
        analysis: dict,
    ):
        """Generate a professional HTML report for the 5D estimate."""
        report_dir = self.output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        html_path = report_dir / f"{estimate.estimate_id}_5d_report.html"
        json_path = report_dir / f"{estimate.estimate_id}_data.json"

        # Build line item rows
        line_item_rows = ""
        for li in estimate.line_items:
            line_item_rows += f"""
            <tr>
                <td>{li.category}</td>
                <td>{li.component}</td>
                <td class="num">{li.quantity:,.1f}</td>
                <td>{li.unit}</td>
                <td class="num">${li.unit_material_cost:,.2f}</td>
                <td class="num">${li.unit_labor_cost:,.2f}</td>
                <td class="num">${li.extended_total:,.2f}</td>
                <td class="num">{li.total_labor_hours:,.1f}</td>
            </tr>"""

        # Build schedule rows
        schedule_rows = ""
        running_day = 1
        for phase in estimate.schedule_phases:
            phase.start_day = running_day
            phase.end_day = running_day + phase.duration_days - 1
            task_list = "<br>".join(f"• {t}" for t in phase.tasks)
            schedule_rows += f"""
            <tr>
                <td><strong>{phase.phase_name}</strong></td>
                <td class="num">{phase.duration_days}</td>
                <td>Day {phase.start_day}–{phase.end_day}</td>
                <td>{phase.crew_type}</td>
                <td class="num">{phase.crew_size}</td>
                <td style="font-size:0.85em">{task_list}</td>
            </tr>"""
            running_day = phase.end_day + 1

        # Build damage findings
        damage_html = ""
        if estimate.damage_findings:
            damage_html = "<h3>Damage Findings</h3><ul>"
            for finding in estimate.damage_findings:
                damage_html += f"<li>{finding}</li>"
            damage_html += "</ul>"

        # Build recommendations
        reco_html = ""
        if estimate.recommendations:
            reco_html = "<h3>Recommendations</h3><ul>"
            for rec in estimate.recommendations:
                reco_html += f"<li>{rec}</li>"
            reco_html += "</ul>"

        # Assumptions
        assumptions_html = ""
        if estimate.assumptions:
            assumptions_html = "<h3>Assumptions &amp; Qualifications</h3><ul>"
            for a in estimate.assumptions:
                assumptions_html += f"<li>{a}</li>"
            assumptions_html += "</ul>"

        # Confidence bar
        conf_pct = int(estimate.confidence_score * 100)
        conf_color = "#27ae60" if conf_pct >= 80 else "#f39c12" if conf_pct >= 60 else "#e74c3c"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>5D Construction Estimate — {estimate.estimate_id}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color:#1a1a2e; background:#f0f2f5; }}
  .report {{ max-width:1100px; margin:0 auto; background:#fff; }}
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color:#fff; padding:40px; }}
  .header h1 {{ font-size:1.8em; margin-bottom:8px; }}
  .header .subtitle {{ opacity:0.85; font-size:1.05em; }}
  .badge-5d {{ display:inline-block; background:#e94560; color:#fff; padding:6px 18px; border-radius:20px;
               font-weight:700; font-size:0.9em; margin-top:12px; letter-spacing:1px; }}
  .meta-grid {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px; padding:30px 40px; background:#f8f9fa; }}
  .meta-card {{ background:#fff; border-radius:8px; padding:16px; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
  .meta-card .label {{ font-size:0.8em; color:#666; text-transform:uppercase; letter-spacing:0.5px; }}
  .meta-card .value {{ font-size:1.4em; font-weight:700; color:#1a1a2e; margin-top:4px; }}
  .meta-card .value.money {{ color:#27ae60; }}
  .meta-card .value.schedule {{ color:#2980b9; }}
  section {{ padding:30px 40px; border-bottom:1px solid #eee; }}
  h2 {{ font-size:1.3em; color:#1a1a2e; margin-bottom:16px; padding-bottom:8px; border-bottom:2px solid #e94560; }}
  h3 {{ font-size:1.1em; color:#333; margin:16px 0 8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.9em; }}
  th {{ background:#1a1a2e; color:#fff; padding:10px 12px; text-align:left; font-weight:600; }}
  td {{ padding:8px 12px; border-bottom:1px solid #eee; }}
  tr:hover td {{ background:#f8f9fa; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .summary-row td {{ font-weight:700; background:#f0f2f5; border-top:2px solid #1a1a2e; }}
  .grand-total td {{ font-size:1.15em; background:#1a1a2e; color:#fff; }}
  .confidence-bar {{ background:#eee; border-radius:10px; height:20px; margin:8px 0; overflow:hidden; }}
  .confidence-fill {{ height:100%; border-radius:10px; background:{conf_color}; width:{conf_pct}%; transition:width 0.5s; }}
  .scope {{ background:#f8f9fa; padding:16px; border-radius:8px; border-left:4px solid #e94560; margin-bottom:16px; }}
  ul {{ margin-left:20px; margin-bottom:12px; }}
  li {{ margin-bottom:4px; }}
  .footer {{ background:#1a1a2e; color:#fff; padding:30px 40px; text-align:center; font-size:0.85em; opacity:0.9; }}
  @media print {{ .report {{ box-shadow:none; }} body {{ background:#fff; }} }}
</style>
</head>
<body>
<div class="report">

  <!-- HEADER -->
  <div class="header">
    <h1>{self.settings.company.name or 'Envelope Estimator'}</h1>
    <div class="subtitle">5D Construction Cost Estimate</div>
    <div class="badge-5d">5D ESTIMATE — 3D SCOPE + SCHEDULE + COST</div>
  </div>

  <!-- SUMMARY CARDS -->
  <div class="meta-grid">
    <div class="meta-card">
      <div class="label">Estimate ID</div>
      <div class="value">{estimate.estimate_id}</div>
      <div class="label" style="margin-top:8px">Date</div>
      <div style="font-size:0.95em">{datetime.now().strftime('%B %d, %Y')}</div>
    </div>
    <div class="meta-card">
      <div class="label">Customer</div>
      <div class="value" style="font-size:1.1em">{estimate.customer_name}</div>
      <div class="label" style="margin-top:8px">Property</div>
      <div style="font-size:0.95em">{estimate.property_address}</div>
    </div>
    <div class="meta-card">
      <div class="label">Grand Total</div>
      <div class="value money">${estimate.grand_total:,.2f}</div>
      <div class="label" style="margin-top:8px">Project Duration</div>
      <div class="value schedule" style="font-size:1.1em">{estimate.total_project_days} Days</div>
    </div>
  </div>

  <!-- SCOPE OVERVIEW -->
  <section>
    <h2>Project Scope</h2>
    <div class="scope"><strong>Summary:</strong> {estimate.scope_summary}</div>
    <table>
      <tr><td><strong>Project Type</strong></td><td>{estimate.project_type.replace('_', ' ').title()}</td>
          <td><strong>Building Footprint</strong></td><td>{estimate.building_footprint_sf:,.0f} SF</td></tr>
      <tr><td><strong>Stories</strong></td><td>{estimate.stories}</td>
          <td><strong>Roof Pitch</strong></td><td>{estimate.roof_pitch or 'N/A'}</td></tr>
      <tr><td><strong>Exterior Wall Area</strong></td><td>{estimate.exterior_wall_sf:,.0f} SF</td>
          <td><strong>Cost / SF</strong></td><td>${estimate.cost_per_sf:,.2f}</td></tr>
    </table>
    {damage_html}
  </section>

  <!-- LINE ITEMS -->
  <section>
    <h2>Detailed Line Items</h2>
    <table>
      <thead>
        <tr>
          <th>Category</th><th>Component</th><th>Qty</th><th>Unit</th>
          <th>Mat/Unit</th><th>Lab/Unit</th><th>Extended</th><th>Labor Hrs</th>
        </tr>
      </thead>
      <tbody>
        {line_item_rows}
      </tbody>
      <tfoot>
        <tr class="summary-row">
          <td colspan="4">Subtotal — Materials</td>
          <td colspan="3" class="num">${estimate.subtotal_materials:,.2f}</td>
          <td></td>
        </tr>
        <tr class="summary-row">
          <td colspan="4">Subtotal — Labor</td>
          <td colspan="3" class="num">${estimate.subtotal_labor:,.2f}</td>
          <td class="num">{estimate.total_labor_hours:,.1f}</td>
        </tr>
        <tr class="summary-row">
          <td colspan="4">Subtotal Direct Cost</td>
          <td colspan="3" class="num">${estimate.subtotal_direct:,.2f}</td>
          <td></td>
        </tr>
        <tr class="summary-row">
          <td colspan="4">Overhead ({estimate.overhead_percent:.0%})</td>
          <td colspan="3" class="num">${estimate.overhead_amount:,.2f}</td>
          <td></td>
        </tr>
        <tr class="summary-row">
          <td colspan="4">Profit ({estimate.profit_percent:.0%})</td>
          <td colspan="3" class="num">${estimate.profit_amount:,.2f}</td>
          <td></td>
        </tr>
        <tr class="grand-total">
          <td colspan="4"><strong>GRAND TOTAL</strong></td>
          <td colspan="3" class="num"><strong>${estimate.grand_total:,.2f}</strong></td>
          <td></td>
        </tr>
      </tfoot>
    </table>
  </section>

  <!-- SCHEDULE -->
  <section>
    <h2>Project Schedule (4th Dimension)</h2>
    <table>
      <thead>
        <tr><th>Phase</th><th>Duration</th><th>Timeline</th><th>Crew Type</th><th>Crew Size</th><th>Tasks</th></tr>
      </thead>
      <tbody>{schedule_rows}</tbody>
      <tfoot>
        <tr class="summary-row">
          <td><strong>Total Project Duration</strong></td>
          <td class="num"><strong>{estimate.total_project_days} days</strong></td>
          <td colspan="4">Including weather contingency</td>
        </tr>
        <tr class="summary-row">
          <td><strong>Total Labor Hours</strong></td>
          <td class="num"><strong>{estimate.total_labor_hours:,.1f} hrs</strong></td>
          <td colspan="4"></td>
        </tr>
      </tfoot>
    </table>
  </section>

  <!-- CONFIDENCE & NOTES -->
  <section>
    <h2>Estimate Confidence</h2>
    <p>AI Confidence Score: <strong>{conf_pct}%</strong></p>
    <div class="confidence-bar"><div class="confidence-fill"></div></div>
    {reco_html}
    {assumptions_html}
    <h3>Data Quality Notes</h3>
    <ul>
      {"".join(f"<li>{n}</li>" for n in estimate.data_quality_notes) if estimate.data_quality_notes else "<li>Standard photo-based analysis</li>"}
    </ul>
  </section>

  <!-- FOOTER -->
  <div class="footer">
    <p>Generated by {self.settings.company.name or 'Envelope Estimator'} — AI-Powered 5D Construction Estimating</p>
    <p>This estimate is based on AI analysis of customer-submitted photos and may vary from final project costs.</p>
    <p>Estimate ID: {estimate.estimate_id} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
  </div>

</div>
</body>
</html>"""

        html_path.write_text(html)
        estimate.report_html_path = str(html_path)

        # Save JSON data
        json_data = {
            "estimate_id": estimate.estimate_id,
            "session_id": estimate.session_id,
            "generated_at": estimate.generated_at,
            "customer": {
                "name": estimate.customer_name,
                "address": estimate.property_address,
            },
            "scope": {
                "project_type": estimate.project_type,
                "summary": estimate.scope_summary,
                "footprint_sf": estimate.building_footprint_sf,
                "total_sf": estimate.total_area_sf,
                "stories": estimate.stories,
                "roof_pitch": estimate.roof_pitch,
                "wall_sf": estimate.exterior_wall_sf,
            },
            "costs": {
                "materials": estimate.subtotal_materials,
                "labor": estimate.subtotal_labor,
                "direct": estimate.subtotal_direct,
                "overhead": estimate.overhead_amount,
                "profit": estimate.profit_amount,
                "grand_total": estimate.grand_total,
                "cost_per_sf": estimate.cost_per_sf,
            },
            "schedule": {
                "total_days": estimate.total_project_days,
                "total_labor_hours": estimate.total_labor_hours,
                "phases": [
                    {
                        "name": p.phase_name,
                        "duration_days": p.duration_days,
                        "crew": p.crew_type,
                    }
                    for p in estimate.schedule_phases
                ],
            },
            "confidence": estimate.confidence_score,
            "line_items": [
                {
                    "category": li.category,
                    "component": li.component,
                    "qty": li.quantity,
                    "unit": li.unit,
                    "material": li.extended_material,
                    "labor": li.extended_labor,
                    "total": li.extended_total,
                }
                for li in estimate.line_items
            ],
            "analysis": analysis,
        }
        json_path.write_text(json.dumps(json_data, indent=2))
        estimate.report_json_path = str(json_path)

    # ------------------------------------------------------------------
    # Internal: Validation
    # ------------------------------------------------------------------

    def _validate_submission(
        self,
        session: ScanSession,
        submission: ScanSubmission,
    ) -> dict:
        """Validate that the submission meets minimum requirements."""
        requirements = SCAN_REQUIREMENTS.get(
            session.intake.project_type, DEFAULT_SCAN_REQUIREMENTS
        )
        issues = []

        min_photos = requirements.get("min_required", 2)
        if len(submission.photos) < min_photos:
            issues.append(
                f"Only {len(submission.photos)} photos submitted "
                f"(minimum {min_photos} recommended)"
            )

        # Check for required measurement fields
        provided_fields = {m.field_name for m in submission.measurements}
        for needed in requirements.get("measurements_needed", []):
            if needed not in provided_fields:
                issues.append(f"Missing measurement: {needed}")

        return {"valid": len(issues) == 0, "issues": issues}

    # ------------------------------------------------------------------
    # Internal: Session persistence
    # ------------------------------------------------------------------

    def _save_session(self, session: ScanSession):
        """Persist session state to disk."""
        path = self.sessions_dir / f"{session.session_id}.json"
        data = {
            "session_id": session.session_id,
            "token": session.token,
            "status": session.status.value,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "scan_link": session.scan_link,
            "link_sent_at": session.link_sent_at,
            "opened_at": session.opened_at,
            "submitted_at": session.submitted_at,
            "estimated_at": session.estimated_at,
            "delivered_at": session.delivered_at,
            "intake": {
                "customer_name": session.intake.customer_name,
                "customer_email": session.intake.customer_email,
                "customer_phone": session.intake.customer_phone,
                "property_address": session.intake.property_address,
                "project_type": session.intake.project_type.value,
                "project_description": session.intake.project_description,
            },
        }
        path.write_text(json.dumps(data, indent=2))

    def _load_session(self, session_id: str) -> Optional[ScanSession]:
        """Load a session from disk."""
        path = self.sessions_dir / f"{session_id}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text())

        intake = CustomerIntakeForm(
            customer_name=data.get("intake", {}).get("customer_name", ""),
            customer_email=data.get("intake", {}).get("customer_email", ""),
            customer_phone=data.get("intake", {}).get("customer_phone", ""),
            property_address=data.get("intake", {}).get("property_address", ""),
            project_type=ProjectType(data.get("intake", {}).get("project_type", "residential_full_exterior")),
            project_description=data.get("intake", {}).get("project_description", ""),
        )

        return ScanSession(
            session_id=data["session_id"],
            token=data["token"],
            status=ScanSessionStatus(data["status"]),
            created_at=data.get("created_at", ""),
            expires_at=data.get("expires_at", ""),
            scan_link=data.get("scan_link", ""),
            intake=intake,
            link_sent_at=data.get("link_sent_at", ""),
            opened_at=data.get("opened_at", ""),
            submitted_at=data.get("submitted_at", ""),
            estimated_at=data.get("estimated_at", ""),
            delivered_at=data.get("delivered_at", ""),
        )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[str]:
    """Extract JSON from a Claude response (may be wrapped in markdown)."""
    # Try to find JSON in code blocks first
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()

    # Try to find raw JSON object
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return None
