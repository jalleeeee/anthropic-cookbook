"""
PDF Blueprint Takeoff Module

Uses Claude Vision to read 2D construction drawings and perform a thorough
quantity takeoff focused on the BUILDING ENVELOPE.

Pipeline:
1. Identify relevant sheets (elevations, roof plans, sections, details, schedules)
2. Detect drawing scale and building type (single-family vs multifamily)
3. Extract building dimensions (per-building for multifamily)
4. Extract per-trade quantities with per-elevation measurement
5. Extract window/door schedules for deductions
6. Compute line items with waste factors and pitch multipliers
7. Validate with independent secondary AI pass + ratio checks

Supports both:
- Residential single-family (simple footprint, pitched roof)
- Commercial multifamily (multiple buildings, podium, mixed cladding zones,
  balconies, corridors, flat/mixed roofs, high window counts)

Aligned with:
- CSI MasterFormat Divisions 04-09 for envelope scope
- DDC CWICR resource-based cost methodology for downstream pricing
"""

import base64
import io
import json
import logging
import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import anthropic

from config.settings import Settings
from config.trades import (
    ALL_TRADES,
    MeasurementType,
    Trade,
    TradeComponent,
    get_pitch_multiplier,
)
from config.multifamily_template import (
    MULTIFAMILY_SHEET_ID_PROMPT,
    MULTIFAMILY_BUILDING_DIMS_PROMPT,
    MULTIFAMILY_TRADE_MEASUREMENT_PROMPT,
    MULTIFAMILY_DEDUCTIONS_PROMPT,
    MULTIFAMILY_VALIDATION_PROMPT,
    get_default_multifamily_template,
)

logger = logging.getLogger(__name__)


@dataclass
class SheetInfo:
    """Identified drawing sheet."""
    page_number: int
    sheet_id: str           # e.g. "A-201", "A-501"
    sheet_type: str         # elevation, roof_plan, section, detail, schedule
    title: str
    scale: str              # e.g. "1/4\" = 1'-0\""
    relevant_trades: list[str] = field(default_factory=list)


@dataclass
class Measurement:
    """A single extracted measurement."""
    component_name: str
    trade_code: str
    value: float
    unit: str
    source_sheet: str
    source_description: str
    confidence: float           # 0.0 to 1.0
    is_estimated: bool = False  # True if AI estimated vs read directly
    notes: str = ""


@dataclass
class TakeoffLineItem:
    """Computed takeoff line item with waste and adjustments."""
    trade_code: str
    trade_name: str
    component_name: str
    raw_quantity: float
    unit: str
    waste_factor: float
    pitch_multiplier: float
    adjusted_quantity: float     # raw × pitch × (1 + waste)
    measurements: list[Measurement] = field(default_factory=list)
    notes: str = ""


@dataclass
class TakeoffResult:
    """Complete takeoff for a project."""
    project_id: str
    sheets_identified: list[SheetInfo]
    line_items: list[TakeoffLineItem]
    roof_pitch: str = ""
    roof_pitch_multiplier: float = 1.0
    building_footprint_sf: float = 0.0
    building_perimeter_lf: float = 0.0
    wall_height_ft: float = 0.0
    story_count: int = 0
    gross_wall_area_sf: float = 0.0
    window_deductions_sf: float = 0.0
    door_deductions_sf: float = 0.0
    net_wall_area_sf: float = 0.0
    validation_variance_pct: float = 0.0
    confidence_score: float = 0.0
    warnings: list[str] = field(default_factory=list)
    raw_ai_responses: list[dict] = field(default_factory=list)
    # Multifamily extensions
    is_multifamily: bool = False
    building_count: int = 1
    total_units: int = 0
    buildings_data: list[dict] = field(default_factory=list)
    ratio_checks: dict = field(default_factory=dict)


class PDFTakeoff:
    """Extracts quantities from PDF blueprints using Claude Vision.

    Supports two modes:
    - Standard (single-family / small commercial): simple prompts
    - Multifamily (commercial apartments/condos): enhanced prompts with
      per-building measurement, elevation zones, ratio checks, and
      DDC CWICR-aligned component breakdowns
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic.api_key)

    def process(
        self,
        pdf_paths: list[str],
        trades: list[Trade],
        project_id: str = "",
        project_type: str = "",
    ) -> TakeoffResult:
        """Run full takeoff pipeline on PDF plans.

        Args:
            pdf_paths: List of PDF file paths to process.
            trades: List of Trade objects defining what to measure.
            project_id: Unique project identifier.
            project_type: "multifamily" to use enhanced commercial prompts.
                          Auto-detected from drawings if empty.
        """
        is_multifamily = project_type.lower() in (
            "multifamily", "commercial_multifamily", "apartments", "condos",
        )

        result = TakeoffResult(
            project_id=project_id,
            sheets_identified=[],
            line_items=[],
            is_multifamily=is_multifamily,
        )

        # Step 1: Convert PDFs to images for Claude Vision
        all_pages = []
        for pdf_path in pdf_paths:
            pages = self._pdf_to_images(pdf_path)
            all_pages.extend(pages)

        if not all_pages:
            result.warnings.append("No pages could be extracted from PDFs")
            return result

        logger.info(f"Extracted {len(all_pages)} pages from {len(pdf_paths)} PDFs")

        # Step 2: Identify relevant sheets
        result.sheets_identified = self._identify_sheets(
            all_pages, trades, is_multifamily=is_multifamily
        )
        logger.info(
            f"Identified {len(result.sheets_identified)} relevant sheets"
        )

        # Auto-detect multifamily if not explicitly set
        if not is_multifamily:
            mf_signals = sum(
                1 for s in result.sheets_identified
                if any(kw in s.title.lower() for kw in (
                    "bldg", "building", "unit plan", "typical unit",
                    "corridor", "breezeway", "podium",
                ))
            )
            if mf_signals >= 2:
                is_multifamily = True
                result.is_multifamily = True
                logger.info("Auto-detected multifamily project from sheet titles")

        if not result.sheets_identified:
            result.warnings.append("No relevant sheets identified in plans")
            return result

        # Step 3: Extract building dimensions (global measurements)
        building_dims = self._extract_building_dimensions(
            all_pages, result.sheets_identified,
            is_multifamily=is_multifamily,
        )

        # For multifamily: aggregate across buildings
        if is_multifamily and "buildings" in building_dims:
            buildings = building_dims["buildings"]
            result.buildings_data = buildings
            result.building_count = len(buildings)
            result.total_units = sum(
                b.get("unit_count_estimate", 0) for b in buildings
            )
            # Aggregate totals
            result.building_footprint_sf = sum(
                b.get("footprint_sf", 0) for b in buildings
            )
            result.building_perimeter_lf = sum(
                b.get("perimeter_lf", 0) for b in buildings
            )
            result.gross_wall_area_sf = sum(
                b.get("gross_wall_area_sf", 0) for b in buildings
            )
            # Use first building's roof pitch as default
            first = buildings[0] if buildings else {}
            result.roof_pitch = first.get("roof_pitch", "flat")
            result.wall_height_ft = first.get("total_building_height_ft", 0)
            result.story_count = max(
                (b.get("stories_above_grade", 1) for b in buildings), default=1
            )
            site_totals = building_dims.get("site_totals", {})
            if site_totals.get("total_gross_wall_sf"):
                result.gross_wall_area_sf = site_totals["total_gross_wall_sf"]
        else:
            result.roof_pitch = building_dims.get("roof_pitch", "")
            result.building_footprint_sf = building_dims.get("footprint_sf", 0)
            result.building_perimeter_lf = building_dims.get("perimeter_lf", 0)
            result.wall_height_ft = building_dims.get("wall_height_ft", 0)
            result.story_count = building_dims.get("story_count", 1)
            result.gross_wall_area_sf = building_dims.get("gross_wall_area_sf", 0)

        result.roof_pitch_multiplier = get_pitch_multiplier(result.roof_pitch)

        # Step 4: Extract per-trade measurements
        measurements = []
        for trade in trades:
            relevant_sheets = [
                s for s in result.sheets_identified
                if trade.code in s.relevant_trades
                or any(st in s.sheet_type for st in trade.blueprint_sheets)
            ]
            if not relevant_sheets:
                # Fall back to elevations and sections
                relevant_sheets = [
                    s for s in result.sheets_identified
                    if s.sheet_type in ("elevation", "section", "roof_plan")
                ]

            trade_measurements = self._extract_trade_measurements(
                all_pages, relevant_sheets, trade, building_dims,
                is_multifamily=is_multifamily,
            )
            measurements.extend(trade_measurements)

        # Step 5: Extract window/door deductions
        deductions = self._extract_deductions(
            all_pages, result.sheets_identified,
            is_multifamily=is_multifamily,
        )
        # Multifamily deductions have a richer structure
        if is_multifamily and "summary" in deductions:
            summary = deductions["summary"]
            result.window_deductions_sf = (
                summary.get("total_window_area_sf", 0)
                + summary.get("total_sgd_area_sf", 0)
                + summary.get("total_storefront_sf", 0)
            )
            result.door_deductions_sf = summary.get("total_door_area_sf", 0)
        else:
            result.window_deductions_sf = deductions.get("window_area_sf", 0)
            result.door_deductions_sf = deductions.get("door_area_sf", 0)
        result.net_wall_area_sf = (
            result.gross_wall_area_sf
            - result.window_deductions_sf
            - result.door_deductions_sf
        )

        # Step 6: Compute line items with waste and pitch adjustments
        result.line_items = self._compute_line_items(
            measurements, trades, result
        )

        # Step 7: Validate with secondary AI pass
        result.validation_variance_pct = self._validate_takeoff(
            all_pages, result, is_multifamily=is_multifamily,
        )
        result.confidence_score = self._compute_confidence(result)

        logger.info(
            f"Takeoff complete: {len(result.line_items)} line items, "
            f"confidence={result.confidence_score:.0%}, "
            f"variance={result.validation_variance_pct:.1f}%"
        )

        return result

    # ------------------------------------------------------------------
    # PDF to images
    # ------------------------------------------------------------------

    def _pdf_to_images(self, pdf_path: str) -> list[dict]:
        """Convert PDF pages to base64 images for Claude Vision.

        Returns list of {page_number, image_base64, source_pdf}.
        Uses pdftoppm (poppler) if available, falls back to pdf2image.
        """
        pages = []
        path = Path(pdf_path)
        if not path.exists():
            logger.error(f"PDF not found: {pdf_path}")
            return pages

        try:
            # Try using pdf2image (requires poppler)
            from pdf2image import convert_from_path

            images = convert_from_path(
                pdf_path,
                dpi=200,  # balance between quality and size
                fmt="png",
            )
            for i, img in enumerate(images):
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
                pages.append({
                    "page_number": i + 1,
                    "image_base64": b64,
                    "source_pdf": pdf_path,
                    "media_type": "image/png",
                })

        except ImportError:
            logger.warning(
                "pdf2image not installed. Attempting pdftoppm directly."
            )
            try:
                import tempfile

                with tempfile.TemporaryDirectory() as tmpdir:
                    subprocess.run(
                        [
                            "pdftoppm", "-png", "-r", "200",
                            pdf_path, f"{tmpdir}/page",
                        ],
                        check=True,
                        capture_output=True,
                    )
                    for img_path in sorted(Path(tmpdir).glob("page-*.png")):
                        b64 = base64.standard_b64encode(
                            img_path.read_bytes()
                        ).decode("utf-8")
                        page_num = int(
                            img_path.stem.split("-")[-1]
                        )
                        pages.append({
                            "page_number": page_num,
                            "image_base64": b64,
                            "source_pdf": pdf_path,
                            "media_type": "image/png",
                        })
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.error(
                    f"Cannot convert PDF to images. Install poppler-utils "
                    f"or pdf2image: {e}"
                )

        return pages

    # ------------------------------------------------------------------
    # Sheet identification
    # ------------------------------------------------------------------

    def _identify_sheets(
        self, pages: list[dict], trades: list[Trade],
        is_multifamily: bool = False,
    ) -> list[SheetInfo]:
        """Use Claude Vision to identify relevant drawing sheets."""

        trade_names = [t.name for t in trades]
        # Send first few pages + last few to identify the drawing index
        sample_pages = pages[:min(6, len(pages))]

        content = []
        for page in sample_pages:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": page["media_type"],
                    "data": page["image_base64"],
                },
            })

        if is_multifamily:
            prompt_text = MULTIFAMILY_SHEET_ID_PROMPT.format(
                trade_names=trade_names
            )
        else:
            prompt_text = f"""Analyze these construction drawing pages. For each page,
identify:
1. Sheet ID (e.g., A-201, S-101, A-501)
2. Sheet type: one of [elevation, roof_plan, floor_plan, section, detail,
   window_schedule, door_schedule, wall_section, general_notes]
3. Sheet title
4. Drawing scale if visible
5. Which of these trades it's relevant to: {trade_names}

Return a JSON array:
[
  {{
    "page_number": 1,
    "sheet_id": "A-201",
    "sheet_type": "elevation",
    "title": "North & South Elevations",
    "scale": "1/4\\" = 1'-0\\"",
    "relevant_trades": ["Siding", "Windows", "Gutters"]
  }}
]

Only include pages that contain architectural drawings relevant to the
envelope trades listed. Skip cover sheets, site plans, MEP sheets, etc.
Return ONLY the JSON array."""

        content.append({"type": "text", "text": prompt_text})

        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_vision,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )
            text = response.content[0].text.strip()
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                sheets_data = json.loads(json_match.group())
            else:
                sheets_data = []

        except Exception as e:
            logger.error(f"Sheet identification failed: {e}")
            return []

        from config.trades import TRADE_BY_NAME

        sheets = []
        for s in sheets_data:
            trade_codes = []
            for tn in s.get("relevant_trades", []):
                t = TRADE_BY_NAME.get(tn.lower())
                if t:
                    trade_codes.append(t.code)
            sheets.append(SheetInfo(
                page_number=s.get("page_number", 0),
                sheet_id=s.get("sheet_id", ""),
                sheet_type=s.get("sheet_type", ""),
                title=s.get("title", ""),
                scale=s.get("scale", ""),
                relevant_trades=trade_codes,
            ))

        return sheets

    # ------------------------------------------------------------------
    # Building dimension extraction
    # ------------------------------------------------------------------

    def _extract_building_dimensions(
        self, pages: list[dict], sheets: list[SheetInfo],
        is_multifamily: bool = False,
    ) -> dict:
        """Extract global building dimensions from plans."""

        # Find elevation and section sheets
        target_types = {"elevation", "section", "floor_plan", "roof_plan"}
        relevant_pages = [
            p for p in pages
            for s in sheets
            if s.page_number == p["page_number"]
            and s.sheet_type in target_types
        ][:8]  # limit to 8 pages for context window

        if not relevant_pages:
            relevant_pages = pages[:4]

        content = []
        for page in relevant_pages:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": page["media_type"],
                    "data": page["image_base64"],
                },
            })

        if is_multifamily:
            prompt_text = MULTIFAMILY_BUILDING_DIMS_PROMPT
        else:
            prompt_text = """Analyze these construction drawings and extract the
building's key dimensions. You are an expert construction estimator.

Measure carefully using the drawing scale. Return a JSON object:
{
  "footprint_sf": 0,
  "footprint_length_ft": 0,
  "footprint_width_ft": 0,
  "perimeter_lf": 0,
  "wall_height_ft": 0,
  "story_count": 1,
  "plate_height_ft": 0,
  "roof_pitch": "6:12",
  "roof_type": "gable",
  "overhang_depth_ft": 0,
  "gross_wall_area_sf": 0,
  "gross_roof_area_plan_sf": 0,
  "ridge_length_lf": 0,
  "eave_length_lf": 0,
  "rake_length_lf": 0,
  "valley_length_lf": 0,
  "hip_length_lf": 0,
  "parapet_length_lf": 0,
  "notes": ""
}

IMPORTANT:
- Use the drawing scale shown on the sheets to calculate real dimensions
- gross_wall_area = perimeter × wall_height × story_count
- Include overhang in roof area calculations
- Note if any values are estimated vs measured directly
- Return ONLY the JSON object"""

        content.append({"type": "text", "text": prompt_text})

        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_vision,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )
            text = response.content[0].text.strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"Building dimension extraction failed: {e}")

        return {}

    # ------------------------------------------------------------------
    # Per-trade measurement extraction
    # ------------------------------------------------------------------

    def _extract_trade_measurements(
        self,
        pages: list[dict],
        sheets: list[SheetInfo],
        trade: Trade,
        building_dims: dict,
        is_multifamily: bool = False,
    ) -> list[Measurement]:
        """Extract measurements for a specific trade from relevant sheets."""

        relevant_pages = [
            p for p in pages
            for s in sheets
            if s.page_number == p["page_number"]
        ][:6]

        if not relevant_pages:
            return []

        component_desc = "\n".join(
            f"  - {c.name} ({c.measurement_type.value}, unit: {c.unit})"
            for c in trade.components
        )

        content = []
        for page in relevant_pages:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": page["media_type"],
                    "data": page["image_base64"],
                },
            })

        if is_multifamily:
            # Build rich building context from multifamily dims
            if "buildings" in building_dims:
                bldg_lines = []
                for b in building_dims["buildings"]:
                    bldg_lines.append(
                        f"  {b.get('building_id', 'Building')}: "
                        f"{b.get('footprint_sf', '?')} SF footprint, "
                        f"{b.get('perimeter_lf', '?')} LF perimeter, "
                        f"{b.get('stories_above_grade', '?')} stories, "
                        f"{b.get('total_building_height_ft', '?')} ft tall, "
                        f"gross wall: {b.get('gross_wall_area_sf', '?')} SF, "
                        f"roof: {b.get('roof_area_plan_sf', '?')} SF, "
                        f"~{b.get('unit_count_estimate', '?')} units, "
                        f"balconies: {b.get('balcony_count', '?')}"
                    )
                building_context = "\n".join(bldg_lines)
            else:
                building_context = (
                    f"Footprint: {building_dims.get('footprint_sf', '?')} SF, "
                    f"Perimeter: {building_dims.get('perimeter_lf', '?')} LF, "
                    f"Stories: {building_dims.get('story_count', '?')}"
                )

            prompt_text = MULTIFAMILY_TRADE_MEASUREMENT_PROMPT.format(
                trade_name=trade.name,
                building_context=building_context,
                component_desc=component_desc,
            )
        else:
            prompt_text = f"""You are an expert commercial construction estimator
specializing in the building envelope. Analyze these drawings for the
**{trade.name}** trade.

Known building dimensions:
- Footprint: {building_dims.get('footprint_sf', 'unknown')} SF
- Perimeter: {building_dims.get('perimeter_lf', 'unknown')} LF
- Wall height: {building_dims.get('wall_height_ft', 'unknown')} ft
- Stories: {building_dims.get('story_count', 'unknown')}
- Roof pitch: {building_dims.get('roof_pitch', 'unknown')}

Components to measure:
{component_desc}

For EACH component, extract the quantity from the drawings.
Use the drawing scale to calculate actual dimensions.

Return a JSON array:
[
  {{
    "component_name": "{trade.components[0].name}",
    "value": 0,
    "unit": "{trade.components[0].unit}",
    "source_sheet": "A-201",
    "source_description": "Measured from north elevation",
    "confidence": 0.9,
    "is_estimated": false,
    "notes": ""
  }}
]

RULES:
- For area measurements (SF): calculate length × height from drawings
- For linear measurements (LF): measure total run from drawings
- For count (EA): count each unit from schedules and elevations
- Always note which sheet/drawing you measured from
- Set confidence 0.0-1.0 (1.0 = dimension clearly labeled on drawing)
- Set is_estimated=true if you had to infer the dimension
- Return ONLY the JSON array"""

        content.append({"type": "text", "text": prompt_text})

        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_vision,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )
            text = response.content[0].text.strip()
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = []
        except Exception as e:
            logger.error(f"Trade measurement failed for {trade.name}: {e}")
            data = []

        measurements = []
        for item in data:
            measurements.append(Measurement(
                component_name=item.get("component_name", ""),
                trade_code=trade.code,
                value=float(item.get("value", 0)),
                unit=item.get("unit", ""),
                source_sheet=item.get("source_sheet", ""),
                source_description=item.get("source_description", ""),
                confidence=float(item.get("confidence", 0.5)),
                is_estimated=item.get("is_estimated", False),
                notes=item.get("notes", ""),
            ))

        return measurements

    # ------------------------------------------------------------------
    # Window / door deductions
    # ------------------------------------------------------------------

    def _extract_deductions(
        self, pages: list[dict], sheets: list[SheetInfo],
        is_multifamily: bool = False,
    ) -> dict:
        """Extract window and door schedules for wall area deductions."""

        schedule_sheets = [
            p for p in pages
            for s in sheets
            if s.page_number == p["page_number"]
            and s.sheet_type in ("window_schedule", "door_schedule", "elevation")
        ][:4]

        if not schedule_sheets:
            return {"window_area_sf": 0, "door_area_sf": 0}

        content = []
        for page in schedule_sheets:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": page["media_type"],
                    "data": page["image_base64"],
                },
            })

        if is_multifamily:
            prompt_text = MULTIFAMILY_DEDUCTIONS_PROMPT
        else:
            prompt_text = """Extract the window schedule and door schedule from
these drawings. Calculate the total area to deduct from gross wall area.

For each window type: width × height × quantity = total area
For each door: width × height × quantity = total area

Return JSON:
{
  "windows": [
    {"type": "A", "width_ft": 3, "height_ft": 5, "quantity": 10, "area_sf": 150}
  ],
  "doors": [
    {"type": "1", "width_ft": 3, "height_ft": 7, "quantity": 2, "area_sf": 42}
  ],
  "window_area_sf": 0,
  "door_area_sf": 0,
  "total_deduction_sf": 0
}

Return ONLY the JSON object."""

        content.append({"type": "text", "text": prompt_text})

        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_vision,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )
            text = response.content[0].text.strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"Deduction extraction failed: {e}")

        return {"window_area_sf": 0, "door_area_sf": 0}

    # ------------------------------------------------------------------
    # Compute final line items
    # ------------------------------------------------------------------

    def _compute_line_items(
        self,
        measurements: list[Measurement],
        trades: list[Trade],
        result: TakeoffResult,
    ) -> list[TakeoffLineItem]:
        """Aggregate measurements into final line items with adjustments."""

        from config.trades import TRADE_BY_CODE

        line_items = []

        # Group measurements by trade_code + component_name
        groups: dict[str, list[Measurement]] = {}
        for m in measurements:
            key = f"{m.trade_code}:{m.component_name}"
            groups.setdefault(key, []).append(m)

        for key, group in groups.items():
            trade_code = group[0].trade_code
            component_name = group[0].component_name
            trade = TRADE_BY_CODE.get(trade_code)
            if not trade:
                continue

            # Find matching component definition
            comp = None
            for c in trade.components:
                if c.name == component_name:
                    comp = c
                    break
            if not comp:
                comp = trade.components[0]  # fallback

            # Sum raw quantities
            raw_qty = sum(m.value for m in group)

            # Apply pitch multiplier if applicable
            pitch_mult = (
                result.roof_pitch_multiplier if comp.pitch_adjusted else 1.0
            )

            # Apply waste factor
            adjusted_qty = raw_qty * pitch_mult * (1.0 + comp.waste_factor)

            # Convert to standard units if needed
            unit = comp.unit
            if unit == "SQ" and comp.measurement_type == MeasurementType.AREA:
                # Roofing squares: 1 SQ = 100 SF
                adjusted_qty = math.ceil(adjusted_qty / 100.0)

            line_items.append(TakeoffLineItem(
                trade_code=trade_code,
                trade_name=trade.name,
                component_name=component_name,
                raw_quantity=raw_qty,
                unit=unit,
                waste_factor=comp.waste_factor,
                pitch_multiplier=pitch_mult,
                adjusted_quantity=round(adjusted_qty, 2),
                measurements=group,
            ))

        return line_items

    # ------------------------------------------------------------------
    # Validation (secondary AI pass)
    # ------------------------------------------------------------------

    def _validate_takeoff(
        self, pages: list[dict], result: TakeoffResult,
        is_multifamily: bool = False,
    ) -> float:
        """Run a verification pass using the secondary model.

        Returns the variance percentage between primary and verification.
        For multifamily, also performs ratio checks against industry benchmarks.
        """
        if not result.line_items:
            return 0.0

        summary = self._format_takeoff_summary(result)

        # Use a few key pages for verification
        verify_pages = pages[:4]
        content = []
        for page in verify_pages:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": page["media_type"],
                    "data": page["image_base64"],
                },
            })

        if is_multifamily:
            prompt_text = MULTIFAMILY_VALIDATION_PROMPT.format(summary=summary)
        else:
            prompt_text = f"""You are a senior estimator performing a QA review.
Verify this takeoff against the drawings.

TAKEOFF TO VERIFY:
{summary}

For each major line item, independently estimate the quantity from the
drawings and compare to the takeoff values.

Return JSON:
{{
  "verified_items": [
    {{
      "component": "name",
      "takeoff_qty": 0,
      "verified_qty": 0,
      "variance_pct": 0,
      "status": "pass"
    }}
  ],
  "overall_variance_pct": 0,
  "issues": [],
  "recommendation": "approve" or "review_needed"
}}

Return ONLY the JSON object."""

        content.append({"type": "text", "text": prompt_text})

        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_verify,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )
            text = response.content[0].text.strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                variance = data.get("overall_variance_pct", 0)

                if data.get("issues"):
                    for issue in data["issues"]:
                        result.warnings.append(f"Validation: {issue}")

                # Store ratio checks for multifamily
                if is_multifamily and "ratio_checks" in data:
                    result.ratio_checks = data["ratio_checks"]

                return abs(float(variance))
        except Exception as e:
            logger.error(f"Validation pass failed: {e}")

        return 0.0

    def _compute_confidence(self, result: TakeoffResult) -> float:
        """Compute overall confidence score for the takeoff."""
        if not result.line_items:
            return 0.0

        confidences = []
        for item in result.line_items:
            for m in item.measurements:
                confidences.append(m.confidence)

        if not confidences:
            return 0.5

        avg_confidence = sum(confidences) / len(confidences)

        # Penalize for high validation variance
        variance_penalty = min(result.validation_variance_pct / 10.0, 0.3)

        return max(0.0, min(1.0, avg_confidence - variance_penalty))

    def _format_takeoff_summary(self, result: TakeoffResult) -> str:
        """Format takeoff results as readable text."""
        lines = []

        if result.is_multifamily and result.buildings_data:
            lines.append(
                f"PROJECT TYPE: Commercial Multifamily — "
                f"{result.building_count} building(s), "
                f"~{result.total_units} units"
            )
            for b in result.buildings_data:
                lines.append(
                    f"  {b.get('building_id', 'Building')}: "
                    f"{b.get('footprint_sf', '?')} SF footprint, "
                    f"{b.get('stories_above_grade', '?')} stories, "
                    f"{b.get('gross_wall_area_sf', '?')} SF wall area"
                )
            lines.append("")

        lines.extend([
            f"TOTALS: {result.building_footprint_sf} SF footprint, "
            f"{result.story_count} stories, "
            f"roof pitch {result.roof_pitch}",
            f"Gross wall area: {result.gross_wall_area_sf} SF",
            f"Window deductions: {result.window_deductions_sf} SF",
            f"Door deductions: {result.door_deductions_sf} SF",
            f"Net wall area: {result.net_wall_area_sf} SF",
            "",
            "LINE ITEMS:",
        ])
        for item in result.line_items:
            lines.append(
                f"  {item.trade_name} - {item.component_name}: "
                f"{item.adjusted_quantity} {item.unit} "
                f"(raw: {item.raw_quantity}, "
                f"waste: {item.waste_factor:.0%}, "
                f"pitch: {item.pitch_multiplier:.3f})"
            )
        return "\n".join(lines)
