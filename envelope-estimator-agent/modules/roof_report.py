"""
Satellite Roof Measurement Report Module (EagleView-style)

Generates professional roof measurement reports from an address alone using:
1. Google Geocoding API → lat/lng from address
2. Google Solar API (buildingInsights) → footprint, segments, pitch
3. Google Solar API (DataLayers) → DSM GeoTIFF for precise slope/area
4. Google Static Maps API → multi-zoom satellite imagery
5. Claude Vision → AI roof geometry analysis (facets, edges, penetrations)
6. Calculation engine → 3D area, edges, materials BOM, cost estimate

Output: 3-page professional HTML report (print-to-PDF compatible)

Reference architecture: RoofReport-v2 (Hono/Cloudflare Workers)
Adapted to Python for integration with the Envelope Estimator Agent.
"""

import base64
import io
import json
import logging
import math
import re
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import requests

from config.settings import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GeoPoint:
    latitude: float
    longitude: float


@dataclass
class RoofSegment:
    """A single roof facet/plane."""
    name: str
    pitch_degrees: float
    azimuth_degrees: float         # 0=N, 90=E, 180=S, 270=W
    area_sqft: float               # flat (plan) area
    true_area_sqft: float = 0.0    # 3D pitch-adjusted area
    bounding_box: dict = field(default_factory=dict)
    color: str = ""


@dataclass
class EdgeMeasurement:
    edge_type: str                 # ridge, hip, valley, eave, rake
    plan_length_ft: float
    true_length_ft: float = 0.0
    connected_segments: list[str] = field(default_factory=list)


@dataclass
class EdgeSummary:
    total_ridge_ft: float = 0.0
    total_hip_ft: float = 0.0
    total_valley_ft: float = 0.0
    total_eave_ft: float = 0.0
    total_rake_ft: float = 0.0
    total_drip_edge_ft: float = 0.0


@dataclass
class MaterialLineItem:
    name: str
    category: str                  # shingles, underlayment, flashing, etc.
    net_quantity: float
    waste_percent: float
    gross_quantity: float
    order_quantity: float
    unit: str
    unit_cost: float
    line_total: float
    notes: str = ""


@dataclass
class MaterialEstimate:
    line_items: list[MaterialLineItem]
    subtotal: float = 0.0
    total_cost: float = 0.0
    gross_squares: float = 0.0
    bundle_count: int = 0
    currency: str = "USD"


@dataclass
class Penetration:
    """Roof penetration (chimney, vent, skylight, etc.)."""
    type: str
    count: int
    estimated_flashing_lf: float = 0.0


@dataclass
class QualityMetrics:
    confidence_score: int = 0      # 0-100
    imagery_quality: str = "HIGH"
    imagery_date: str = ""
    field_verification_recommended: bool = False
    provider: str = ""


@dataclass
class RoofReport:
    """Complete roof measurement report."""
    report_id: str = ""
    report_number: str = ""
    generated_at: str = ""

    # Property
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    homeowner_name: str = ""
    requester_name: str = ""

    # Measurements
    total_footprint_sqft: float = 0.0
    total_true_area_sqft: float = 0.0
    area_multiplier: float = 1.0
    roof_pitch_degrees: float = 0.0
    roof_pitch_ratio: str = ""
    roof_azimuth_degrees: float = 0.0
    waste_factor: float = 1.10

    # Components
    segments: list[RoofSegment] = field(default_factory=list)
    edges: list[EdgeMeasurement] = field(default_factory=list)
    edge_summary: EdgeSummary = field(default_factory=EdgeSummary)
    penetrations: list[Penetration] = field(default_factory=list)
    materials: MaterialEstimate = field(default_factory=lambda: MaterialEstimate(line_items=[]))

    # Imagery URLs
    satellite_overhead_url: str = ""
    satellite_context_url: str = ""
    satellite_detail_url: str = ""
    satellite_full_url: str = ""
    satellite_neighbourhood_url: str = ""

    # AI analysis
    ai_geometry: dict = field(default_factory=dict)

    # Quality
    quality: QualityMetrics = field(default_factory=QualityMetrics)

    # Output
    professional_report_html: str = ""


# ---------------------------------------------------------------------------
# Pitch/area calculation helpers
# ---------------------------------------------------------------------------

PITCH_TABLE = {
    0: (1.000, "flat"),
    1: (1.003, "1:12"), 2: (1.014, "2:12"), 3: (1.031, "3:12"),
    4: (1.054, "4:12"), 5: (1.083, "5:12"), 6: (1.118, "6:12"),
    7: (1.158, "7:12"), 8: (1.202, "8:12"), 9: (1.250, "9:12"),
    10: (1.302, "10:12"), 11: (1.357, "11:12"), 12: (1.414, "12:12"),
    14: (1.537, "14:12"), 16: (1.667, "16:12"), 18: (1.803, "18:12"),
}

FACET_COLORS = [
    "#4FC3F7", "#FFB74D", "#81C784", "#E57373",
    "#BA68C8", "#FFD54F", "#4DB6AC", "#FF8A65",
    "#7986CB", "#AED581", "#F06292", "#90A4AE",
]


def degrees_to_ratio(degrees: float) -> str:
    rise_per_12 = round(math.tan(math.radians(degrees)) * 12, 1)
    return f"{rise_per_12}:12"


def pitch_multiplier(degrees: float) -> float:
    if degrees <= 0:
        return 1.0
    return 1.0 / math.cos(math.radians(degrees))


def true_area(flat_sqft: float, pitch_deg: float) -> float:
    return flat_sqft * pitch_multiplier(pitch_deg)


def compute_waste_factor(area_sqft: float) -> float:
    if area_sqft > 3000:
        return 1.15
    elif area_sqft > 2000:
        return 1.12
    elif area_sqft > 1000:
        return 1.10
    return 1.05


def azimuth_label(degrees: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int(((degrees + 22.5) % 360) / 45)
    return dirs[idx]


# ---------------------------------------------------------------------------
# Module class
# ---------------------------------------------------------------------------

class RoofReportGenerator:
    """Generates satellite-based roof measurement reports from an address."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic.api_key)
        self.google_api_key = settings.google_api_key
        self.output_dir = Path(settings.output_dir) / "roof_reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def generate(
        self,
        address: str,
        city: str = "",
        state: str = "",
        postal_code: str = "",
        homeowner_name: str = "",
        requester_name: str = "",
    ) -> RoofReport:
        """Generate a complete roof measurement report from an address."""
        start_time = time.time()

        report = RoofReport(
            report_id=f"RR-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            report_number=f"RM-{datetime.now().strftime('%Y%m%d')}-{int(time.time()) % 10000:04d}",
            generated_at=datetime.now().isoformat(),
            address=address,
            city=city,
            state=state,
            postal_code=postal_code,
            homeowner_name=homeowner_name,
            requester_name=requester_name,
        )

        full_address = f"{address}, {city}, {state} {postal_code}".strip(", ")

        # Step 1: Geocode address
        logger.info(f"[1/7] Geocoding: {full_address}")
        geo = self._geocode(full_address)
        if geo:
            report.latitude = geo.latitude
            report.longitude = geo.longitude
        else:
            logger.error("Geocoding failed")
            report.quality.provider = "geocoding_failed"
            return report

        # Step 2: Fetch building insights from Google Solar API
        logger.info("[2/7] Fetching building insights (Solar API)...")
        insights = self._fetch_building_insights(geo)

        # Step 3: Fetch DataLayers (DSM GeoTIFF) for precise measurements
        logger.info("[3/7] Fetching DataLayers (DSM GeoTIFF)...")
        datalayers = self._fetch_datalayers(geo)

        # Step 4: Generate satellite imagery URLs
        logger.info("[4/7] Generating satellite imagery...")
        self._generate_satellite_urls(report, geo)

        # Step 5: Process measurements
        logger.info("[5/7] Computing roof measurements...")
        self._compute_measurements(report, insights, datalayers)

        # Step 6: AI vision analysis
        logger.info("[6/7] Running AI roof geometry analysis...")
        self._ai_analyze_roof(report)

        # Step 7: Generate materials BOM and HTML report
        logger.info("[7/7] Generating materials and report...")
        self._compute_materials(report)
        report.professional_report_html = self._generate_report_html(report)

        # Save outputs
        elapsed = time.time() - start_time
        self._save_report(report)
        logger.info(
            f"Report complete in {elapsed:.1f}s: "
            f"{report.total_true_area_sqft:.0f} sqft, "
            f"pitch {report.roof_pitch_ratio}"
        )

        return report

    # ------------------------------------------------------------------
    # Step 1: Geocoding
    # ------------------------------------------------------------------

    def _geocode(self, address: str) -> Optional[GeoPoint]:
        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": self.google_api_key},
                timeout=15,
            )
            data = resp.json()
            if data.get("status") == "OK" and data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                return GeoPoint(latitude=loc["lat"], longitude=loc["lng"])
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
        return None

    # ------------------------------------------------------------------
    # Step 2: Building Insights (Solar API)
    # ------------------------------------------------------------------

    def _fetch_building_insights(self, geo: GeoPoint) -> dict:
        try:
            resp = requests.get(
                "https://solar.googleapis.com/v1/buildingInsights:findClosest",
                params={
                    "location.latitude": geo.latitude,
                    "location.longitude": geo.longitude,
                    "key": self.google_api_key,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Building insights returned {resp.status_code}")
        except Exception as e:
            logger.error(f"Building insights error: {e}")
        return {}

    # ------------------------------------------------------------------
    # Step 3: DataLayers (DSM GeoTIFF)
    # ------------------------------------------------------------------

    def _fetch_datalayers(self, geo: GeoPoint) -> dict:
        try:
            resp = requests.get(
                "https://solar.googleapis.com/v1/dataLayers:get",
                params={
                    "location.latitude": geo.latitude,
                    "location.longitude": geo.longitude,
                    "radiusMeters": 50,
                    "view": "FULL_LAYERS",
                    "requiredQuality": "HIGH",
                    "pixelSizeMeters": 0.5,
                    "key": self.google_api_key,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"DataLayers returned {resp.status_code}")
        except Exception as e:
            logger.error(f"DataLayers error: {e}")
        return {}

    def _process_dsm_geotiff(self, dsm_url: str, mask_url: str) -> dict:
        """Download and process DSM GeoTIFF for slope/pitch analysis.

        Uses tifffile if available, otherwise falls back to basic parsing.
        """
        result = {
            "flat_area_sqm": 0,
            "mean_pitch_degrees": 0,
            "pixel_count": 0,
            "pixel_size_m": 0.5,
        }

        try:
            import tifffile
            import numpy as np

            # Download DSM
            dsm_resp = requests.get(dsm_url, timeout=60)
            dsm_data = io.BytesIO(dsm_resp.content)
            dsm_img = tifffile.imread(dsm_data)

            # Download mask
            mask_resp = requests.get(mask_url, timeout=60)
            mask_data = io.BytesIO(mask_resp.content)
            mask_img = tifffile.imread(mask_data)

            # Resample mask to DSM dimensions if needed
            if mask_img.shape != dsm_img.shape:
                from PIL import Image
                mask_pil = Image.fromarray(mask_img)
                mask_pil = mask_pil.resize(
                    (dsm_img.shape[1], dsm_img.shape[0]),
                    Image.NEAREST,
                )
                mask_img = np.array(mask_pil)

            # Filter to building pixels
            building_mask = mask_img > 0
            pixel_size = 0.5  # meters

            if not building_mask.any():
                return result

            # Compute gradient (slope)
            dz_dy, dz_dx = np.gradient(dsm_img, pixel_size)
            slope = np.sqrt(dz_dx ** 2 + dz_dy ** 2)
            pitch_rad = np.arctan(slope)
            pitch_deg = np.degrees(pitch_rad)

            # Stats over building pixels only
            building_pitches = pitch_deg[building_mask]
            pixel_count = int(building_mask.sum())
            flat_area_sqm = pixel_count * (pixel_size ** 2)
            mean_pitch = float(np.median(building_pitches))

            result["flat_area_sqm"] = flat_area_sqm
            result["mean_pitch_degrees"] = mean_pitch
            result["pixel_count"] = pixel_count
            result["pixel_size_m"] = pixel_size

        except ImportError:
            logger.warning(
                "tifffile/numpy not available for GeoTIFF processing. "
                "Using buildingInsights only."
            )
        except Exception as e:
            logger.error(f"GeoTIFF processing error: {e}")

        return result

    # ------------------------------------------------------------------
    # Step 4: Satellite imagery
    # ------------------------------------------------------------------

    def _generate_satellite_urls(self, report: RoofReport, geo: GeoPoint):
        base = "https://maps.googleapis.com/maps/api/staticmap"
        params_base = {
            "center": f"{geo.latitude},{geo.longitude}",
            "size": "640x640",
            "maptype": "satellite",
            "scale": "2",
            "key": self.google_api_key,
        }

        zooms = {
            "satellite_overhead_url": 21,
            "satellite_detail_url": 20,
            "satellite_context_url": 19,
            "satellite_full_url": 18,
            "satellite_neighbourhood_url": 17,
        }

        for attr, zoom in zooms.items():
            params = {**params_base, "zoom": zoom}
            url = f"{base}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
            setattr(report, attr, url)

    # ------------------------------------------------------------------
    # Step 5: Compute measurements
    # ------------------------------------------------------------------

    def _compute_measurements(
        self, report: RoofReport, insights: dict, datalayers: dict
    ):
        """Compute roof area, pitch, segments, edges from API data."""

        # Try DataLayers first (most accurate)
        dsm_result = {}
        if datalayers.get("dsmUrl") and datalayers.get("maskUrl"):
            dsm_result = self._process_dsm_geotiff(
                datalayers["dsmUrl"], datalayers["maskUrl"]
            )
            if dsm_result.get("flat_area_sqm"):
                report.quality.provider = "google_solar_datalayers"
                report.quality.confidence_score = 95
                if datalayers.get("imageryDate"):
                    d = datalayers["imageryDate"]
                    report.quality.imagery_date = (
                        f"{d.get('year', '')}-{d.get('month', ''):02d}-{d.get('day', ''):02d}"
                    )

        # Extract segments from buildingInsights
        solar = insights.get("solarPotential", {})
        roof_segments_raw = solar.get("roofSegmentStats", [])
        whole_roof = solar.get("wholeRoofStats", {})

        if roof_segments_raw:
            for i, seg in enumerate(roof_segments_raw):
                pitch = seg.get("pitchDegrees", 0)
                azimuth = seg.get("azimuthDegrees", 0)
                area_m2 = seg.get("stats", {}).get("areaMeters2", 0)
                area_sqft = area_m2 * 10.7639

                report.segments.append(RoofSegment(
                    name=f"Facet {i + 1} ({azimuth_label(azimuth)})",
                    pitch_degrees=pitch,
                    azimuth_degrees=azimuth,
                    area_sqft=area_sqft,
                    true_area_sqft=true_area(area_sqft, pitch),
                    color=FACET_COLORS[i % len(FACET_COLORS)],
                ))

        # Compute totals
        if dsm_result.get("flat_area_sqm"):
            report.total_footprint_sqft = dsm_result["flat_area_sqm"] * 10.7639
            report.roof_pitch_degrees = dsm_result["mean_pitch_degrees"]
        elif report.segments:
            report.total_footprint_sqft = sum(s.area_sqft for s in report.segments)
            # Weighted average pitch
            total_area = sum(s.area_sqft for s in report.segments)
            if total_area > 0:
                report.roof_pitch_degrees = sum(
                    s.pitch_degrees * s.area_sqft for s in report.segments
                ) / total_area
        elif whole_roof.get("areaMeters2"):
            report.total_footprint_sqft = whole_roof["areaMeters2"] * 10.7639
            report.quality.provider = "google_solar_api"
            report.quality.confidence_score = 85

        if not report.quality.provider:
            report.quality.provider = "estimated"
            report.quality.confidence_score = 50
            report.quality.field_verification_recommended = True

        # Pitch ratio
        report.roof_pitch_ratio = degrees_to_ratio(report.roof_pitch_degrees)
        report.area_multiplier = pitch_multiplier(report.roof_pitch_degrees)
        report.total_true_area_sqft = (
            report.total_footprint_sqft * report.area_multiplier
        )
        report.waste_factor = compute_waste_factor(report.total_true_area_sqft)

        # Generate edge measurements
        self._compute_edges(report)

    def _compute_edges(self, report: RoofReport):
        """Estimate edge measurements from segments and footprint."""
        n_segments = len(report.segments)
        footprint = report.total_footprint_sqft
        side_len = math.sqrt(footprint) if footprint > 0 else 40

        # Heuristic edge estimation based on segment count and footprint
        perimeter = side_len * 4
        pm = report.area_multiplier

        # Ridge: ~40-50% of building length
        ridge_ft = side_len * 0.9
        # Hip: depends on hip/gable style
        hip_ft = side_len * 0.3 * max(1, (n_segments - 2) / 2) if n_segments > 2 else 0
        # Valley: internal corners
        valley_ft = side_len * 0.2 * max(0, n_segments - 4) if n_segments > 4 else 0
        # Eave: roughly perimeter minus gables
        eave_ft = perimeter * 0.7
        # Rake: gable ends
        rake_ft = perimeter * 0.3 * pm

        edges = [
            ("ridge", ridge_ft),
            ("hip", hip_ft),
            ("valley", valley_ft),
            ("eave", eave_ft),
            ("rake", rake_ft),
        ]

        for edge_type, plan_len in edges:
            true_len = plan_len * pm if edge_type in ("hip", "rake", "valley") else plan_len
            report.edges.append(EdgeMeasurement(
                edge_type=edge_type,
                plan_length_ft=round(plan_len, 1),
                true_length_ft=round(true_len, 1),
            ))

        report.edge_summary = EdgeSummary(
            total_ridge_ft=round(ridge_ft, 1),
            total_hip_ft=round(hip_ft * pm, 1),
            total_valley_ft=round(valley_ft * pm, 1),
            total_eave_ft=round(eave_ft, 1),
            total_rake_ft=round(rake_ft, 1),
            total_drip_edge_ft=round(eave_ft + rake_ft, 1),
        )

        # Estimate penetrations from segment count
        report.penetrations = [
            Penetration("Pipe Boot", max(2, n_segments // 2), 3.0),
            Penetration("Exhaust Vent", max(1, n_segments // 3), 4.0),
        ]
        if n_segments >= 6:
            report.penetrations.append(
                Penetration("Chimney", 1, 16.0)
            )

    # ------------------------------------------------------------------
    # Step 6: AI Vision Analysis
    # ------------------------------------------------------------------

    def _ai_analyze_roof(self, report: RoofReport):
        """Use Claude Vision to analyze overhead satellite imagery."""
        if not report.satellite_overhead_url:
            return

        try:
            # Download the satellite image
            img_resp = requests.get(report.satellite_overhead_url, timeout=30)
            if img_resp.status_code != 200:
                logger.warning("Could not download satellite image for AI analysis")
                return

            img_b64 = base64.standard_b64encode(img_resp.content).decode("utf-8")

            response = self.client.messages.create(
                model=self.settings.anthropic.model_vision,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": """Analyze this overhead satellite image of a roof.
Identify and describe:

1. **Roof facets**: Count distinct roof planes, estimate their relative sizes
2. **Roof type**: gable, hip, flat, mansard, gambrel, combination
3. **Edge lines**: Identify ridge lines, hip lines, valley lines, eave lines, rake lines
4. **Penetrations**: Count chimneys, vents, skylights, pipes, HVAC units
5. **Roof material**: shingle type, metal, tile, membrane
6. **Condition**: visible damage, wear, missing materials, debris
7. **Complexity**: simple, moderate, complex, very complex

Return JSON:
{
  "roof_type": "",
  "facet_count": 0,
  "facets": [
    {"name": "", "relative_size": "large/medium/small", "orientation": "N/S/E/W"}
  ],
  "edges": {
    "ridge_count": 0,
    "hip_count": 0,
    "valley_count": 0
  },
  "penetrations": {
    "chimneys": 0,
    "vents": 0,
    "skylights": 0,
    "pipes": 0,
    "hvac_units": 0
  },
  "material": "",
  "condition": "",
  "complexity": "",
  "notes": ""
}

Return ONLY the JSON object.""",
                        },
                    ],
                }],
            )

            text = response.content[0].text.strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                report.ai_geometry = json.loads(json_match.group())

                # Update penetrations from AI analysis
                ai_pen = report.ai_geometry.get("penetrations", {})
                report.penetrations = []
                if ai_pen.get("chimneys", 0) > 0:
                    report.penetrations.append(
                        Penetration("Chimney", ai_pen["chimneys"], 16.0)
                    )
                if ai_pen.get("pipes", 0) > 0:
                    report.penetrations.append(
                        Penetration("Pipe Boot", ai_pen["pipes"], 3.0)
                    )
                if ai_pen.get("vents", 0) > 0:
                    report.penetrations.append(
                        Penetration("Exhaust Vent", ai_pen["vents"], 4.0)
                    )
                if ai_pen.get("skylights", 0) > 0:
                    report.penetrations.append(
                        Penetration("Skylight", ai_pen["skylights"], 12.0)
                    )
                if ai_pen.get("hvac_units", 0) > 0:
                    report.penetrations.append(
                        Penetration("HVAC Unit", ai_pen["hvac_units"], 8.0)
                    )

        except Exception as e:
            logger.error(f"AI roof analysis error: {e}")

    # ------------------------------------------------------------------
    # Step 7: Materials & BOM
    # ------------------------------------------------------------------

    def _compute_materials(self, report: RoofReport):
        """Generate Bill of Materials for the roof."""
        area = report.total_true_area_sqft
        waste = report.waste_factor
        es = report.edge_summary

        items = []

        # Shingles (architectural)
        net_squares = area / 100
        gross_squares = net_squares * waste
        bundles = math.ceil(gross_squares * 3)  # 3 bundles per square
        items.append(MaterialLineItem(
            name="Architectural Shingles (30-yr)",
            category="shingles",
            net_quantity=round(net_squares, 1),
            waste_percent=(waste - 1) * 100,
            gross_quantity=round(gross_squares, 1),
            order_quantity=bundles,
            unit="bundle",
            unit_cost=35.00,
            line_total=round(bundles * 35.00, 2),
        ))

        # Underlayment (synthetic)
        underlayment_rolls = math.ceil(area / 1000 * waste)
        items.append(MaterialLineItem(
            name="Synthetic Underlayment",
            category="underlayment",
            net_quantity=round(area / 1000, 1),
            waste_percent=(waste - 1) * 100,
            gross_quantity=underlayment_rolls,
            order_quantity=underlayment_rolls,
            unit="roll",
            unit_cost=65.00,
            line_total=round(underlayment_rolls * 65.00, 2),
        ))

        # Ice & water shield (eaves + valleys)
        iw_lf = es.total_eave_ft + es.total_valley_ft
        iw_rolls = math.ceil(iw_lf * 3 / 75) if iw_lf > 0 else 1  # 3ft width, 75ft/roll
        items.append(MaterialLineItem(
            name="Ice & Water Shield",
            category="underlayment",
            net_quantity=round(iw_lf, 1),
            waste_percent=5,
            gross_quantity=iw_rolls,
            order_quantity=iw_rolls,
            unit="roll",
            unit_cost=85.00,
            line_total=round(iw_rolls * 85.00, 2),
        ))

        # Starter strip
        starter_lf = es.total_eave_ft + es.total_rake_ft
        starter_packs = math.ceil(starter_lf / 60) if starter_lf > 0 else 1
        items.append(MaterialLineItem(
            name="Starter Strip Shingles",
            category="shingles",
            net_quantity=round(starter_lf, 1),
            waste_percent=5,
            gross_quantity=starter_packs,
            order_quantity=starter_packs,
            unit="pack",
            unit_cost=28.00,
            line_total=round(starter_packs * 28.00, 2),
        ))

        # Ridge cap
        ridge_lf = es.total_ridge_ft + es.total_hip_ft
        ridge_bundles = math.ceil(ridge_lf / 25) if ridge_lf > 0 else 1
        items.append(MaterialLineItem(
            name="Ridge Cap Shingles",
            category="shingles",
            net_quantity=round(ridge_lf, 1),
            waste_percent=5,
            gross_quantity=ridge_bundles,
            order_quantity=ridge_bundles,
            unit="bundle",
            unit_cost=45.00,
            line_total=round(ridge_bundles * 45.00, 2),
        ))

        # Drip edge
        drip_lf = es.total_drip_edge_ft
        drip_pieces = math.ceil(drip_lf / 10) if drip_lf > 0 else 1
        items.append(MaterialLineItem(
            name="Drip Edge (10ft sections)",
            category="flashing",
            net_quantity=round(drip_lf, 1),
            waste_percent=5,
            gross_quantity=drip_pieces,
            order_quantity=drip_pieces,
            unit="piece",
            unit_cost=8.50,
            line_total=round(drip_pieces * 8.50, 2),
        ))

        # Valley flashing
        if es.total_valley_ft > 0:
            valley_rolls = math.ceil(es.total_valley_ft / 50)
            items.append(MaterialLineItem(
                name="Valley Flashing (W-type)",
                category="flashing",
                net_quantity=round(es.total_valley_ft, 1),
                waste_percent=10,
                gross_quantity=valley_rolls,
                order_quantity=valley_rolls,
                unit="roll",
                unit_cost=55.00,
                line_total=round(valley_rolls * 55.00, 2),
            ))

        # Step flashing (penetrations)
        step_flash_count = sum(
            int(p.estimated_flashing_lf / 3) for p in report.penetrations
        )
        if step_flash_count > 0:
            items.append(MaterialLineItem(
                name="Step Flashing Pieces",
                category="flashing",
                net_quantity=step_flash_count,
                waste_percent=10,
                gross_quantity=math.ceil(step_flash_count * 1.1),
                order_quantity=math.ceil(step_flash_count * 1.1),
                unit="piece",
                unit_cost=1.50,
                line_total=round(math.ceil(step_flash_count * 1.1) * 1.50, 2),
            ))

        # Pipe boots
        pipe_boots = sum(p.count for p in report.penetrations if p.type == "Pipe Boot")
        if pipe_boots > 0:
            items.append(MaterialLineItem(
                name="Pipe Boot Flashing",
                category="flashing",
                net_quantity=pipe_boots,
                waste_percent=0,
                gross_quantity=pipe_boots,
                order_quantity=pipe_boots,
                unit="each",
                unit_cost=12.00,
                line_total=round(pipe_boots * 12.00, 2),
            ))

        # Nails
        nail_lbs = math.ceil(gross_squares * 1.5)
        items.append(MaterialLineItem(
            name="Roofing Nails (1-1/4\" coil)",
            category="fasteners",
            net_quantity=nail_lbs,
            waste_percent=10,
            gross_quantity=math.ceil(nail_lbs * 1.1),
            order_quantity=math.ceil(nail_lbs * 1.1),
            unit="lb",
            unit_cost=3.50,
            line_total=round(math.ceil(nail_lbs * 1.1) * 3.50, 2),
        ))

        # Caulk / roofing cement
        caulk_tubes = max(2, math.ceil(gross_squares / 5))
        items.append(MaterialLineItem(
            name="Roofing Cement / Caulk",
            category="sealant",
            net_quantity=caulk_tubes,
            waste_percent=0,
            gross_quantity=caulk_tubes,
            order_quantity=caulk_tubes,
            unit="tube",
            unit_cost=6.50,
            line_total=round(caulk_tubes * 6.50, 2),
        ))

        total = sum(i.line_total for i in items)

        report.materials = MaterialEstimate(
            line_items=items,
            subtotal=round(total, 2),
            total_cost=round(total, 2),
            gross_squares=round(gross_squares, 1),
            bundle_count=bundles,
            currency=self.settings.currency,
        )

    # ------------------------------------------------------------------
    # HTML Report Generation
    # ------------------------------------------------------------------

    def _generate_report_html(self, report: RoofReport) -> str:
        """Generate professional 3-page HTML roof measurement report."""

        segments_html = ""
        for i, seg in enumerate(report.segments):
            segments_html += f"""
            <tr>
              <td><span style="display:inline-block;width:12px;height:12px;
                background:{seg.color};border-radius:50%;margin-right:6px;"></span>
                {seg.name}</td>
              <td>{seg.area_sqft:,.0f}</td>
              <td>{seg.true_area_sqft:,.0f}</td>
              <td>{seg.pitch_degrees:.1f}&deg; ({degrees_to_ratio(seg.pitch_degrees)})</td>
              <td>{azimuth_label(seg.azimuth_degrees)} ({seg.azimuth_degrees:.0f}&deg;)</td>
              <td>{pitch_multiplier(seg.pitch_degrees):.3f}x</td>
            </tr>"""

        materials_html = ""
        for item in report.materials.line_items:
            materials_html += f"""
            <tr>
              <td>{item.name}</td>
              <td>{item.net_quantity:,.1f}</td>
              <td>{item.waste_percent:.0f}%</td>
              <td>{item.gross_quantity:,.0f}</td>
              <td>{item.order_quantity:,.0f} {item.unit}</td>
              <td>${item.unit_cost:,.2f}</td>
              <td>${item.line_total:,.2f}</td>
            </tr>"""

        edges_html = ""
        for edge in report.edges:
            edges_html += f"""
            <tr>
              <td style="text-transform:capitalize;">{edge.edge_type}</td>
              <td>{edge.plan_length_ft:,.1f} ft</td>
              <td>{edge.true_length_ft:,.1f} ft</td>
            </tr>"""

        penetrations_html = ""
        for pen in report.penetrations:
            penetrations_html += f"""
            <tr>
              <td>{pen.type}</td>
              <td>{pen.count}</td>
              <td>{pen.estimated_flashing_lf:.0f} LF</td>
            </tr>"""

        ai_notes = ""
        if report.ai_geometry:
            ai = report.ai_geometry
            ai_notes = f"""
            <div class="ai-analysis">
              <h3>AI Roof Analysis</h3>
              <p><strong>Roof Type:</strong> {ai.get('roof_type', 'N/A')}</p>
              <p><strong>Material:</strong> {ai.get('material', 'N/A')}</p>
              <p><strong>Condition:</strong> {ai.get('condition', 'N/A')}</p>
              <p><strong>Complexity:</strong> {ai.get('complexity', 'N/A')}</p>
              <p><strong>Notes:</strong> {ai.get('notes', '')}</p>
            </div>"""

        complexity = "Simple"
        n_seg = len(report.segments)
        if n_seg > 8:
            complexity = "Very Complex"
        elif n_seg > 5:
            complexity = "Complex"
        elif n_seg > 3:
            complexity = "Moderate"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Roof Measurement Report - {report.report_number}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
         color: #1a1a2e; background: #f0f2f5; }}

  @media print {{
    body {{ background: white; }}
    .page {{ page-break-after: always; box-shadow: none !important;
             margin: 0 !important; }}
    .no-print {{ display: none !important; }}
    * {{ -webkit-print-color-adjust: exact !important;
         print-color-adjust: exact !important; }}
  }}

  .page {{
    width: 8.5in; min-height: 11in; margin: 20px auto;
    padding: 0.4in; background: white;
    box-shadow: 0 2px 12px rgba(0,0,0,0.12);
  }}

  /* Page 1: Dark Dashboard */
  .page-1 {{
    background: linear-gradient(135deg, #0B1E2F 0%, #162d44 100%);
    color: #e0e8f0;
  }}
  .page-1 h1 {{ color: #4FC3F7; font-size: 22px; margin-bottom: 4px; }}
  .page-1 h2 {{ color: #81D4FA; font-size: 16px; margin-bottom: 12px; }}
  .page-1 .header {{ display: flex; justify-content: space-between;
                     align-items: flex-start; margin-bottom: 16px;
                     border-bottom: 2px solid #4FC3F7; padding-bottom: 12px; }}
  .page-1 .address-bar {{
    background: rgba(79,195,247,0.1); border: 1px solid rgba(79,195,247,0.3);
    border-radius: 6px; padding: 8px 14px; margin-bottom: 16px;
    font-size: 13px;
  }}

  .metric-grid {{
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 10px; margin-bottom: 16px;
  }}
  .metric-card {{
    background: rgba(255,255,255,0.06); border: 1px solid rgba(79,195,247,0.2);
    border-radius: 8px; padding: 12px; text-align: center;
  }}
  .metric-card .value {{
    font-size: 24px; font-weight: 700; color: #4FC3F7;
  }}
  .metric-card .label {{
    font-size: 11px; color: #90CAF9; text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  .edge-grid {{
    display: grid; grid-template-columns: repeat(6, 1fr);
    gap: 8px; margin-bottom: 16px;
  }}
  .edge-card {{
    background: rgba(255,255,255,0.05); border: 1px solid rgba(79,195,247,0.15);
    border-radius: 6px; padding: 8px; text-align: center;
  }}
  .edge-card .value {{ font-size: 16px; font-weight: 600; color: #81D4FA; }}
  .edge-card .label {{ font-size: 10px; color: #78909C; }}

  .imagery-grid {{
    display: grid; grid-template-columns: 1.6fr 1fr; gap: 10px;
    margin-bottom: 16px;
  }}
  .imagery-grid img {{ width: 100%; border-radius: 6px;
                       border: 1px solid rgba(79,195,247,0.3); }}
  .sub-images {{ display: grid; grid-template-columns: 1fr 1fr;
                 gap: 6px; }}

  .quality-badge {{
    display: inline-block; background: rgba(76,175,80,0.2);
    border: 1px solid #66BB6A; border-radius: 12px;
    padding: 2px 10px; font-size: 11px; color: #A5D6A7;
  }}

  /* Page 2: Materials (Light) */
  .page-2 {{
    background: #E8F4FD;
  }}
  .page-2 h1 {{ color: #0D47A1; font-size: 20px; margin-bottom: 4px; }}
  .page-2 h2 {{ color: #1565C0; font-size: 15px; }}
  .page-2 .section {{ background: white; border-radius: 8px;
                      padding: 14px; margin-bottom: 14px;
                      border: 1px solid #BBDEFB; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ background: #E3F2FD; color: #0D47A1; padding: 8px 6px;
       text-align: left; font-size: 11px; text-transform: uppercase;
       letter-spacing: 0.3px; }}
  td {{ padding: 6px; border-bottom: 1px solid #E3F2FD; }}
  tr:hover {{ background: #F5F9FF; }}

  .total-row {{ font-weight: 700; background: #E3F2FD !important; }}
  .total-row td {{ border-top: 2px solid #1565C0; }}

  /* Page 3: Detail (Light grey-blue) */
  .page-3 {{
    background: #E0ECF5;
  }}
  .page-3 h1 {{ color: #1A237E; font-size: 20px; margin-bottom: 4px; }}
  .page-3 h2 {{ color: #283593; font-size: 15px; margin-bottom: 8px; }}
  .page-3 .section {{ background: white; border-radius: 8px;
                      padding: 14px; margin-bottom: 14px;
                      border: 1px solid #C5CAE9; }}

  .ai-analysis {{
    background: rgba(79,195,247,0.06); border: 1px solid #B3E5FC;
    border-radius: 8px; padding: 12px; margin-top: 12px;
  }}
  .ai-analysis h3 {{ color: #0288D1; margin-bottom: 6px; font-size: 14px; }}
  .ai-analysis p {{ font-size: 12px; margin-bottom: 3px; }}

  .print-btn {{
    position: fixed; top: 16px; right: 16px; z-index: 999;
    background: #1565C0; color: white; border: none;
    padding: 10px 20px; border-radius: 6px; cursor: pointer;
    font-size: 14px; font-weight: 600;
  }}
  .print-btn:hover {{ background: #0D47A1; }}

  .footer {{
    text-align: center; font-size: 10px; color: #78909C;
    margin-top: 12px; padding-top: 8px;
    border-top: 1px solid rgba(0,0,0,0.1);
  }}
</style>
</head>
<body>

<button class="print-btn no-print" onclick="window.print()">Print / Save PDF</button>

<!-- =================== PAGE 1: DARK DASHBOARD =================== -->
<div class="page page-1">
  <div class="header">
    <div>
      <h1>ROOF MEASUREMENT REPORT</h1>
      <h2>Professional Satellite Analysis</h2>
    </div>
    <div style="text-align:right;">
      <div style="font-size:18px;font-weight:700;color:#4FC3F7;">
        {report.report_number}</div>
      <div style="font-size:11px;color:#78909C;">
        {datetime.now().strftime('%B %d, %Y')}</div>
      <span class="quality-badge">
        {report.quality.confidence_score}% Confidence
      </span>
    </div>
  </div>

  <div class="address-bar">
    <strong>{report.address}</strong>
    {f', {report.city}' if report.city else ''}
    {f', {report.state}' if report.state else ''}
    {f' {report.postal_code}' if report.postal_code else ''}
    &nbsp;&bull;&nbsp;
    <span style="color:#78909C;">
      {report.latitude:.6f}, {report.longitude:.6f}
    </span>
    {f'&nbsp;&bull;&nbsp; Homeowner: {report.homeowner_name}' if report.homeowner_name else ''}
  </div>

  <div class="imagery-grid">
    <div>
      <img src="{report.satellite_overhead_url}" alt="Overhead Satellite">
    </div>
    <div class="sub-images">
      <img src="{report.satellite_detail_url}" alt="Detail">
      <img src="{report.satellite_context_url}" alt="Context">
      <img src="{report.satellite_full_url}" alt="Full Lot">
      <img src="{report.satellite_neighbourhood_url}" alt="Neighbourhood">
    </div>
  </div>

  <div class="metric-grid">
    <div class="metric-card">
      <div class="value">{report.total_true_area_sqft:,.0f}</div>
      <div class="label">Total Area (3D) SF</div>
    </div>
    <div class="metric-card">
      <div class="value">{report.roof_pitch_ratio}</div>
      <div class="label">Pitch ({report.roof_pitch_degrees:.1f}&deg;)</div>
    </div>
    <div class="metric-card">
      <div class="value">{report.area_multiplier:.3f}x</div>
      <div class="label">Area Multiplier</div>
    </div>
    <div class="metric-card">
      <div class="value">{report.waste_factor:.0%}</div>
      <div class="label">Waste Factor</div>
    </div>
    <div class="metric-card">
      <div class="value">{complexity}</div>
      <div class="label">Complexity</div>
    </div>
    <div class="metric-card">
      <div class="value">{len(report.segments)}</div>
      <div class="label">Roof Facets</div>
    </div>
  </div>

  <div class="edge-grid">
    <div class="edge-card">
      <div class="value">{report.edge_summary.total_ridge_ft:,.0f}'</div>
      <div class="label">Ridge</div>
    </div>
    <div class="edge-card">
      <div class="value">{report.edge_summary.total_hip_ft:,.0f}'</div>
      <div class="label">Hip</div>
    </div>
    <div class="edge-card">
      <div class="value">{report.edge_summary.total_valley_ft:,.0f}'</div>
      <div class="label">Valley</div>
    </div>
    <div class="edge-card">
      <div class="value">{report.edge_summary.total_eave_ft:,.0f}'</div>
      <div class="label">Eave</div>
    </div>
    <div class="edge-card">
      <div class="value">{report.edge_summary.total_rake_ft:,.0f}'</div>
      <div class="label">Rake</div>
    </div>
    <div class="edge-card">
      <div class="value">{report.edge_summary.total_drip_edge_ft:,.0f}'</div>
      <div class="label">Drip Edge</div>
    </div>
  </div>

  <div class="footer">
    Provider: {report.quality.provider} &bull;
    Imagery: {report.quality.imagery_date or 'N/A'} &bull;
    Quality: {report.quality.imagery_quality}
    {'&bull; <span style="color:#EF9A9A;">Field Verification Recommended</span>'
     if report.quality.field_verification_recommended else ''}
  </div>
</div>

<!-- =================== PAGE 2: MATERIAL ORDER =================== -->
<div class="page page-2">
  <h1>MATERIAL ORDER</h1>
  <h2>Bill of Materials &bull; {report.report_number}</h2>

  <div class="section" style="margin-top:14px;">
    <table>
      <thead>
        <tr>
          <th>Item</th>
          <th>Net Qty</th>
          <th>Waste</th>
          <th>Gross Qty</th>
          <th>Order</th>
          <th>Unit Cost</th>
          <th>Total</th>
        </tr>
      </thead>
      <tbody>
        {materials_html}
        <tr class="total-row">
          <td colspan="5"></td>
          <td><strong>TOTAL</strong></td>
          <td><strong>${report.materials.total_cost:,.2f}</strong></td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="section">
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">
      <div>
        <div style="font-size:12px;color:#666;">Gross Squares</div>
        <div style="font-size:20px;font-weight:700;color:#0D47A1;">
          {report.materials.gross_squares:.1f} SQ</div>
      </div>
      <div>
        <div style="font-size:12px;color:#666;">Total Bundles</div>
        <div style="font-size:20px;font-weight:700;color:#0D47A1;">
          {report.materials.bundle_count}</div>
      </div>
      <div>
        <div style="font-size:12px;color:#666;">Material Cost</div>
        <div style="font-size:20px;font-weight:700;color:#0D47A1;">
          ${report.materials.total_cost:,.2f} {report.materials.currency}</div>
      </div>
    </div>
  </div>

  <div class="footer">
    Pricing: US Market Average 2026 &bull; Prices subject to regional variation
  </div>
</div>

<!-- =================== PAGE 3: DETAILED MEASUREMENTS =================== -->
<div class="page page-3">
  <h1>DETAILED MEASUREMENTS</h1>
  <h2>Facets, Edges &amp; Penetrations &bull; {report.report_number}</h2>

  <div class="section" style="margin-top:14px;">
    <h2 style="margin-bottom:8px;">Roof Facets</h2>
    <table>
      <thead>
        <tr>
          <th>Facet</th>
          <th>Plan Area (SF)</th>
          <th>True Area (SF)</th>
          <th>Pitch</th>
          <th>Direction</th>
          <th>Multiplier</th>
        </tr>
      </thead>
      <tbody>
        {segments_html}
        <tr class="total-row">
          <td><strong>TOTAL</strong></td>
          <td><strong>{report.total_footprint_sqft:,.0f}</strong></td>
          <td><strong>{report.total_true_area_sqft:,.0f}</strong></td>
          <td><strong>{report.roof_pitch_degrees:.1f}&deg;</strong></td>
          <td></td>
          <td><strong>{report.area_multiplier:.3f}x</strong></td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2 style="margin-bottom:8px;">Linear Measurements</h2>
    <table>
      <thead>
        <tr>
          <th>Edge Type</th>
          <th>Plan Length</th>
          <th>True Length</th>
        </tr>
      </thead>
      <tbody>
        {edges_html}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2 style="margin-bottom:8px;">Penetrations</h2>
    <table>
      <thead>
        <tr>
          <th>Type</th>
          <th>Count</th>
          <th>Est. Flashing</th>
        </tr>
      </thead>
      <tbody>
        {penetrations_html}
      </tbody>
    </table>
  </div>

  {ai_notes}

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

    def _save_report(self, report: RoofReport):
        safe_addr = re.sub(r"[^\w\s-]", "", report.address).strip()[:40]
        base_name = f"{report.report_id}_{safe_addr}"

        # Save HTML
        html_path = self.output_dir / f"{base_name}.html"
        html_path.write_text(report.professional_report_html)
        logger.info(f"Saved report HTML: {html_path}")

        # Save JSON summary
        json_path = self.output_dir / f"{base_name}.json"
        summary = {
            "report_id": report.report_id,
            "report_number": report.report_number,
            "generated_at": report.generated_at,
            "address": report.address,
            "city": report.city,
            "state": report.state,
            "latitude": report.latitude,
            "longitude": report.longitude,
            "total_footprint_sqft": round(report.total_footprint_sqft, 1),
            "total_true_area_sqft": round(report.total_true_area_sqft, 1),
            "area_multiplier": round(report.area_multiplier, 3),
            "roof_pitch_degrees": round(report.roof_pitch_degrees, 1),
            "roof_pitch_ratio": report.roof_pitch_ratio,
            "waste_factor": report.waste_factor,
            "segments": len(report.segments),
            "edge_summary": {
                "ridge_ft": report.edge_summary.total_ridge_ft,
                "hip_ft": report.edge_summary.total_hip_ft,
                "valley_ft": report.edge_summary.total_valley_ft,
                "eave_ft": report.edge_summary.total_eave_ft,
                "rake_ft": report.edge_summary.total_rake_ft,
            },
            "penetrations": [
                {"type": p.type, "count": p.count}
                for p in report.penetrations
            ],
            "materials": {
                "total_cost": report.materials.total_cost,
                "gross_squares": report.materials.gross_squares,
                "bundle_count": report.materials.bundle_count,
                "currency": report.materials.currency,
            },
            "quality": {
                "confidence_score": report.quality.confidence_score,
                "provider": report.quality.provider,
                "imagery_quality": report.quality.imagery_quality,
                "imagery_date": report.quality.imagery_date,
                "field_verification_recommended": report.quality.field_verification_recommended,
            },
            "ai_geometry": report.ai_geometry,
        }
        json_path.write_text(json.dumps(summary, indent=2))
        logger.info(f"Saved report JSON: {json_path}")
