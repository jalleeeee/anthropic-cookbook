"""
Envelope Estimator — Web Application

FastAPI web app wrapping all 5 estimation workflows into a browser-based platform.

Endpoints:
  /                          → Main dashboard
  /takeoff                   → 2D Plan Takeoff (upload PDFs → AI reads drawings → 5D estimate)
  /self-service              → Customer intake form (public-facing)
  /scan/{session_id}         → Customer scan portal (guided photo upload)
  /estimates                 → All estimates list
  /estimates/{id}            → Single estimate detail
  /learning                  → AI learning engine dashboard
  /api/v1/...               → JSON API for all workflows

Run:
  uvicorn webapp:app --reload --port 8000
"""

import json
import logging
import os
import re
import secrets
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.settings import load_settings
from config.trades import ALL_TRADES, TRADE_BY_CODE, PHASE_1_TRADES, PHASE_2_TRADES
from modules.itb_intake import ITBIntake, ProjectInfo
from modules.pdf_takeoff import PDFTakeoff, TakeoffResult
from modules.cost_engine import CostEngine, EstimateResult
from modules.proposal_gen import ProposalGenerator
from modules.deductive_engine import DeductiveEngine, SeedValues, DerivedQuantities
from modules.live_catalog import LiveCatalog
from modules.rom_estimator import ROMEstimator
from modules.self_service_scan import (
    CustomerIntakeForm,
    FiveDEstimate,
    ProjectType,
    ScanMeasurement,
    ScanPhoto,
    ScanPhotoType,
    ScanSubmission,
    SelfServiceScanManager,
)
from modules.ai_learning_engine import AILearningEngine, FeedbackType

logger = logging.getLogger("envelope_estimator.web")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

settings = load_settings()

app = FastAPI(
    title="Envelope Estimator",
    description="AI-Powered Construction Estimating Platform",
    version="1.0.0",
)

# Static files and templates
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "uploads").mkdir(exist_ok=True)

TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Module instances
scan_manager = SelfServiceScanManager(settings)
learning_engine = AILearningEngine(settings)
pdf_takeoff = PDFTakeoff(settings)
cost_engine = CostEngine(settings)
proposal_gen = ProposalGenerator(settings)
itb_intake = ITBIntake(settings)
deductive = DeductiveEngine()
live_catalog = LiveCatalog(settings)
rom_estimator = ROMEstimator(settings)


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

def format_currency(value):
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"


def format_percent(value):
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return "0.0%"


templates.env.filters["currency"] = format_currency
templates.env.filters["percent"] = format_percent


# ---------------------------------------------------------------------------
# PAGE ROUTES — HTML pages served to browser
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard — overview of all workflows, recent estimates, learning stats."""
    # Gather dashboard data
    learning_dash = learning_engine.get_dashboard()

    # Recent sessions
    sessions_dir = scan_manager.sessions_dir
    recent_sessions = []
    if sessions_dir.exists():
        session_files = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for sf in session_files[:10]:
            data = json.loads(sf.read_text())
            recent_sessions.append(data)

    # Recent estimates from learning engine
    estimates_dir = learning_engine.data_dir / "estimates"
    recent_estimates = []
    if estimates_dir.exists():
        est_files = sorted(estimates_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for ef in est_files[:10]:
            recent_estimates.append(json.loads(ef.read_text()))

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "learning": learning_dash,
        "recent_sessions": recent_sessions,
        "recent_estimates": recent_estimates,
        "now": datetime.now(),
    })


@app.get("/self-service", response_class=HTMLResponse)
async def self_service_form(request: Request):
    """Customer-facing intake form — public page for new estimate requests."""
    project_types = [
        {"value": pt.value, "label": pt.value.replace("_", " ").title()}
        for pt in ProjectType
    ]
    return templates.TemplateResponse("self_service_form.html", {
        "request": request,
        "project_types": project_types,
        "company_name": settings.company.name or "Envelope Estimator",
        "company_phone": settings.company.phone,
        "company_email": settings.company.email,
    })


@app.get("/scan/{session_id}", response_class=HTMLResponse)
async def scan_portal(request: Request, session_id: str, token: str = ""):
    """Customer scan portal — guided photo upload page (magic link destination)."""
    config = scan_manager.get_scan_portal_config(session_id, token)

    if not config.get("valid"):
        return templates.TemplateResponse("scan_error.html", {
            "request": request,
            "error": config.get("error", "Invalid session"),
        })

    return templates.TemplateResponse("scan_portal.html", {
        "request": request,
        "config": config,
        "session_id": session_id,
        "token": token,
    })


@app.get("/estimates", response_class=HTMLResponse)
async def estimates_list(request: Request):
    """List all estimates across all workflows."""
    estimates_dir = learning_engine.data_dir / "estimates"
    estimates = []
    if estimates_dir.exists():
        for ef in sorted(estimates_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            estimates.append(json.loads(ef.read_text()))

    return templates.TemplateResponse("estimates_list.html", {
        "request": request,
        "estimates": estimates,
    })


@app.get("/estimates/{estimate_id}", response_class=HTMLResponse)
async def estimate_detail(request: Request, estimate_id: str):
    """Single estimate detail view."""
    # Check for 5D report HTML
    report_dir = scan_manager.output_dir / "reports"
    html_report = report_dir / f"{estimate_id}_5d_report.html"
    json_data_path = report_dir / f"{estimate_id}_data.json"

    estimate_data = None
    report_html = None

    if json_data_path.exists():
        estimate_data = json.loads(json_data_path.read_text())
    if html_report.exists():
        report_html = html_report.read_text()

    # Also check learning engine records
    learning_record = None
    learning_path = learning_engine.data_dir / "estimates" / f"{estimate_id}.json"
    if learning_path.exists():
        learning_record = json.loads(learning_path.read_text())

    if not estimate_data and not learning_record:
        raise HTTPException(status_code=404, detail="Estimate not found")

    return templates.TemplateResponse("estimate_detail.html", {
        "request": request,
        "estimate_id": estimate_id,
        "estimate_data": estimate_data,
        "learning_record": learning_record,
        "report_html": report_html,
    })


@app.get("/learning", response_class=HTMLResponse)
async def learning_dashboard(request: Request):
    """AI Learning Engine dashboard — accuracy, calibration, trends, insights."""
    dashboard_data = learning_engine.get_dashboard()
    calibrations = learning_engine.get_all_calibration_factors()
    trends = learning_engine.get_pricing_trends()

    # Load recent insights
    insights = []
    insights_dir = learning_engine.data_dir / "insights"
    if insights_dir.exists():
        for ifile in sorted(insights_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
            insights.append(json.loads(ifile.read_text()))

    # Load benchmarks
    benchmarks = []
    bench_dir = learning_engine.data_dir / "benchmarks"
    if bench_dir.exists():
        for bfile in sorted(bench_dir.glob("*.json")):
            benchmarks.append(json.loads(bfile.read_text()))

    return templates.TemplateResponse("learning_dashboard.html", {
        "request": request,
        "dashboard": dashboard_data,
        "calibrations": calibrations,
        "trends": trends,
        "insights": insights,
        "benchmarks": benchmarks,
    })


@app.get("/takeoff", response_class=HTMLResponse)
async def takeoff_page(request: Request):
    """2D Plan Takeoff — upload PDFs and run the full envelope takeoff pipeline."""
    trade_list = [
        {
            "code": t.code,
            "name": t.name,
            "phase": 1 if t.code in [tt.code for tt in PHASE_1_TRADES] else 2,
        }
        for t in ALL_TRADES
    ]
    return templates.TemplateResponse("takeoff.html", {
        "request": request,
        "trades": trade_list,
    })


# ---------------------------------------------------------------------------
# API ROUTES — JSON endpoints for programmatic access + AJAX
# ---------------------------------------------------------------------------

@app.post("/api/v1/self-service/create")
async def api_create_session(
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(""),
    property_address: str = Form(...),
    city: str = Form(""),
    state: str = Form(""),
    postal_code: str = Form(""),
    project_type: str = Form("residential_full_exterior"),
    project_description: str = Form(""),
    is_insurance_claim: bool = Form(False),
    cause_of_loss: str = Form(""),
    delivery_method: str = Form("email"),
):
    """Create a self-service scan session and send the customer a link."""
    intake = CustomerIntakeForm(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        property_address=property_address,
        city=city,
        state=state,
        postal_code=postal_code,
        project_type=ProjectType(project_type),
        project_description=project_description,
        is_insurance_claim=is_insurance_claim,
        cause_of_loss=cause_of_loss,
        agreed_to_terms=True,
    )

    session = scan_manager.create_session(intake)
    delivery = scan_manager.send_scan_link(session, delivery_method)

    return JSONResponse({
        "success": True,
        "session_id": session.session_id,
        "scan_link": session.scan_link,
        "expires_at": session.expires_at,
        "delivery": delivery,
    })


@app.post("/api/v1/scan/{session_id}/submit")
async def api_submit_scan(
    session_id: str,
    token: str = Form(...),
    notes: str = Form(""),
    photos: list[UploadFile] = File(...),
    approx_square_footage: str = Form(""),
    number_of_stories: str = Form(""),
    window_count_approx: str = Form(""),
    exterior_door_count: str = Form(""),
):
    """Process uploaded scan photos and generate a 5D estimate."""
    # Validate session
    session = scan_manager._load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.token != token:
        raise HTTPException(status_code=403, detail="Invalid token")

    # Save uploaded photos
    upload_dir = STATIC_DIR / "uploads" / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    scan_photos = []
    photo_type_cycle = [
        ScanPhotoType.FRONT_ELEVATION,
        ScanPhotoType.REAR_ELEVATION,
        ScanPhotoType.LEFT_ELEVATION,
        ScanPhotoType.RIGHT_ELEVATION,
        ScanPhotoType.ROOF_OVERVIEW,
        ScanPhotoType.CLOSE_UP_DAMAGE,
        ScanPhotoType.MATERIAL_DETAIL,
    ]

    for i, photo_file in enumerate(photos):
        safe_name = f"photo_{i+1}_{photo_file.filename}"
        save_path = upload_dir / safe_name
        content = await photo_file.read()
        save_path.write_bytes(content)

        scan_photos.append(ScanPhoto(
            photo_type=photo_type_cycle[i % len(photo_type_cycle)],
            file_path=str(save_path),
            label=photo_file.filename or f"Photo {i+1}",
            timestamp=datetime.now().isoformat(),
        ))

    # Build measurements
    measurements = []
    if approx_square_footage:
        measurements.append(ScanMeasurement(field_name="approx_square_footage", value=approx_square_footage, unit="SF"))
    if number_of_stories:
        measurements.append(ScanMeasurement(field_name="number_of_stories", value=number_of_stories))
    if window_count_approx:
        measurements.append(ScanMeasurement(field_name="window_count_approx", value=window_count_approx))
    if exterior_door_count:
        measurements.append(ScanMeasurement(field_name="exterior_door_count", value=exterior_door_count))

    submission = ScanSubmission(
        session_id=session_id,
        photos=scan_photos,
        measurements=measurements,
        notes=notes,
        submitted_at=datetime.now().isoformat(),
    )

    # Process — this runs the full AI pipeline
    estimate = scan_manager.process_submission(submission)

    # Also record in learning engine
    learning_engine.record_estimate(
        estimate_id=estimate.estimate_id,
        workflow="self_service",
        project_type=estimate.project_type,
        total_sf=estimate.total_area_sf,
        wall_sf=estimate.exterior_wall_sf,
        stories=estimate.stories,
        roof_pitch=estimate.roof_pitch,
        estimated_materials=estimate.subtotal_materials,
        estimated_labor=estimate.subtotal_labor,
        estimated_total=estimate.grand_total,
        line_item_count=len(estimate.line_items),
        estimated_days=estimate.total_project_days,
        estimated_labor_hours=estimate.total_labor_hours,
        confidence_score=estimate.confidence_score,
        data_source="self_service_scan",
        photo_count=len(scan_photos),
    )

    return JSONResponse({
        "success": True,
        "estimate_id": estimate.estimate_id,
        "grand_total": estimate.grand_total,
        "total_days": estimate.total_project_days,
        "confidence": estimate.confidence_score,
        "report_url": f"/estimates/{estimate.estimate_id}",
        "line_items": len(estimate.line_items),
    })


@app.post("/api/v1/takeoff/upload")
async def api_takeoff_upload(
    project_name: str = Form(""),
    address: str = Form(""),
    homeowner: str = Form(""),
    trade_codes: str = Form(""),
    project_type: str = Form(""),
    construction_type: str = Form(""),
    unit_count: str = Form(""),
    primary_cladding: str = Form(""),
    roof_system: str = Form(""),
    pdfs: list[UploadFile] = File(...),
):
    """Run the full PDF takeoff → cost estimate → proposal pipeline.

    This is the CORE workflow: upload 2D construction drawings (PDF), and the AI
    reads every sheet to extract envelope quantities, prices them via DDC-CWICR,
    and generates a bid-ready proposal.
    """
    if not pdfs:
        raise HTTPException(status_code=400, detail="At least one PDF is required")

    # Save uploaded PDFs
    project_id = f"TKO-{secrets.token_hex(4).upper()}"
    upload_dir = STATIC_DIR / "uploads" / project_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths = []
    for pdf_file in pdfs:
        safe_name = re.sub(r'[^\w.\-]', '_', pdf_file.filename or "plan.pdf")
        save_path = upload_dir / safe_name
        content = await pdf_file.read()
        save_path.write_bytes(content)
        pdf_paths.append(str(save_path))

    # Resolve selected trades
    selected_codes = [c.strip() for c in trade_codes.split(",") if c.strip()]
    if selected_codes:
        trades = [TRADE_BY_CODE[c] for c in selected_codes if c in TRADE_BY_CODE]
    else:
        trades = list(PHASE_1_TRADES)  # Default to Phase 1 envelope trades

    # Create project info via ITB intake
    project = itb_intake.process_api_submission(
        project_name=project_name or f"Takeoff {project_id}",
        pdf_paths=pdf_paths,
        metadata={
            "address": address,
            "homeowner": homeowner,
            "source": "web_upload",
        },
    )
    project.project_id = project_id
    if address:
        parts = address.split(",")
        project.project_address = parts[0].strip() if parts else address
        if len(parts) >= 2:
            project.project_city = parts[1].strip()
        if len(parts) >= 3:
            project.project_state = parts[2].strip()

    # Step 1: Run PDF takeoff (Claude Vision reads every sheet)
    takeoff_result = pdf_takeoff.process(
        pdf_paths=pdf_paths,
        trades=trades,
        project_id=project_id,
        project_type=project_type,
    )

    # Step 2: Run cost engine (DDC-CWICR pricing)
    estimate_result = cost_engine.estimate(
        takeoff=takeoff_result,
        trades=trades,
    )

    # Step 3: Generate proposal
    proposal = proposal_gen.generate(
        project=project,
        takeoff=takeoff_result,
        estimate=estimate_result,
        include_detail=True,
    )

    # Step 4: Record in learning engine
    total_sf = takeoff_result.building_footprint_sf or 1.0
    learning_engine.record_estimate(
        estimate_id=project_id,
        workflow="pdf_takeoff",
        project_type=project.project_type or "envelope",
        total_sf=total_sf,
        wall_sf=takeoff_result.net_wall_area_sf,
        stories=takeoff_result.story_count,
        roof_pitch=takeoff_result.roof_pitch,
        estimated_materials=estimate_result.total_material,
        estimated_labor=estimate_result.total_labor,
        estimated_total=estimate_result.grand_total,
        line_item_count=len(takeoff_result.line_items),
        confidence_score=takeoff_result.confidence_score,
        data_source="pdf_blueprint",
        state=project.project_state,
        region=project.project_state,
    )

    # Build JSON response
    return JSONResponse({
        "success": True,
        "project_id": project_id,
        "takeoff": {
            "sheets_count": len(takeoff_result.sheets_identified),
            "line_items_count": len(takeoff_result.line_items),
            "confidence": takeoff_result.confidence_score,
            "variance": takeoff_result.validation_variance_pct,
            "building_dims": {
                "footprint_sf": takeoff_result.building_footprint_sf,
                "perimeter_lf": takeoff_result.building_perimeter_lf,
                "wall_height_ft": takeoff_result.wall_height_ft,
                "stories": takeoff_result.story_count,
                "gross_wall_sf": takeoff_result.gross_wall_area_sf,
                "window_deductions_sf": takeoff_result.window_deductions_sf,
                "door_deductions_sf": takeoff_result.door_deductions_sf,
                "net_wall_sf": takeoff_result.net_wall_area_sf,
                "roof_pitch": takeoff_result.roof_pitch,
                "roof_pitch_multiplier": takeoff_result.roof_pitch_multiplier,
            },
            "line_items": [
                {
                    "trade": li.trade_name,
                    "component": li.component_name,
                    "raw_qty": li.raw_quantity,
                    "waste": li.waste_factor,
                    "pitch": li.pitch_multiplier,
                    "adjusted_qty": li.adjusted_quantity,
                    "unit": li.unit,
                    "notes": li.notes,
                }
                for li in takeoff_result.line_items
            ],
            "warnings": takeoff_result.warnings,
        },
        "estimate": {
            "trades": [
                {
                    "code": ts.trade_code,
                    "name": ts.trade_name,
                    "material": ts.subtotal_material,
                    "labor": ts.subtotal_labor,
                    "total": ts.trade_total,
                }
                for ts in estimate_result.trade_summaries
            ],
            "total_material": estimate_result.total_material,
            "total_labor": estimate_result.total_labor,
            "grand_total": estimate_result.grand_total,
            "cost_per_sf": estimate_result.cost_per_sf,
        },
        "proposal": proposal,
        # Include deductive engine ROM if Step 0 produced seeds
        "deductive_rom": {
            "available": len(takeoff_result.deductive_sov) > 0,
            "buildings": [
                {
                    "building_id": sov.get("building_id", ""),
                    "rom_total": sov.get("total_value", 0),
                    "line_items": len(sov.get("items", [])),
                }
                for sov in takeoff_result.deductive_sov
            ],
            "rom_total": sum(
                s.get("total_value", 0) for s in takeoff_result.deductive_sov
            ),
            "note": (
                "ROM from deductive engine (seed values → math → DDC pricing). "
                "Compare against AI vision takeoff above for validation."
            ),
        } if takeoff_result.deductive_sov else None,
    })


@app.post("/api/v1/deductive/derive")
async def api_deductive_derive(request: Request):
    """Deductive Ratio Engine — derive all envelope quantities from seed values.

    Instead of pixel measurement, the AI reads labeled dimensions from plans
    and this engine mathematically derives every quantity using industry ratios.

    Returns per-building quantities + AIA G703 Schedule of Values.
    """
    body = await request.json()
    buildings_input = body.get("buildings", [body])

    results = []
    for bldg in buildings_input:
        seeds = SeedValues(
            building_id=bldg.get("building_id", "Building A"),
            footprint_sf=float(bldg.get("footprint_sf", 0)),
            stories_above_grade=int(bldg.get("stories_above_grade", 0)),
            stories_below_grade=int(bldg.get("stories_below_grade", 0)),
            footprint_length_ft=float(bldg.get("footprint_length_ft", 0)),
            footprint_width_ft=float(bldg.get("footprint_width_ft", 0)),
            perimeter_lf=float(bldg.get("perimeter_lf", 0)),
            floor_to_floor_ft=float(bldg.get("floor_to_floor_ft", 0)),
            total_building_height_ft=float(bldg.get("total_building_height_ft", 0)),
            parapet_height_ft=float(bldg.get("parapet_height_ft", 0)),
            unit_count=int(bldg.get("unit_count", 0)),
            unit_mix=bldg.get("unit_mix", {}),
            roof_pitch=bldg.get("roof_pitch", "flat"),
            roof_type=bldg.get("roof_type", "TPO membrane"),
            building_shape=bldg.get("building_shape", "typical_multifamily"),
            construction_type=bldg.get("construction_type", "V-A"),
            has_podium=bldg.get("has_podium", False),
            podium_height_ft=float(bldg.get("podium_height_ft", 0)),
            primary_cladding=bldg.get("primary_cladding", "fiber_cement_lap"),
            secondary_cladding=bldg.get("secondary_cladding", ""),
            secondary_cladding_floors=bldg.get("secondary_cladding_floors", ""),
            corridor_type=bldg.get("corridor_type", "interior"),
            balcony_count=int(bldg.get("balcony_count", 0)),
            avg_balcony_sf=float(bldg.get("avg_balcony_sf", 60)),
            window_count_from_schedule=int(bldg.get("window_count_from_schedule", 0)),
            door_count_from_schedule=int(bldg.get("door_count_from_schedule", 0)),
        )

        derived = deductive.derive(seeds)
        sov = deductive.generate_schedule_of_values(seeds, derived)

        results.append({
            "building_id": seeds.building_id,
            "seeds_used": {
                "footprint_sf": seeds.footprint_sf,
                "stories": seeds.stories_above_grade,
                "unit_count": seeds.unit_count,
                "perimeter_lf": seeds.perimeter_lf or derived.perimeter_lf,
            },
            "derived": {
                "perimeter_lf": derived.perimeter_lf,
                "total_height_ft": derived.total_building_height_ft,
                "gross_wall_sf": derived.gross_wall_area_sf,
                "net_wall_sf": derived.net_wall_area_sf,
                "net_to_gross_ratio": derived.net_to_gross_ratio,
                "window_count": derived.window_count,
                "ext_door_count": derived.ext_door_count,
                "sgd_count": derived.sgd_count,
                "primary_cladding_sf": derived.primary_cladding_sf,
                "secondary_cladding_sf": derived.secondary_cladding_sf,
                "wrb_sf": derived.wrb_air_barrier_sf,
                "roof_area_sf": derived.roof_area_actual_sf,
                "gutter_lf": derived.gutter_lf,
                "downspout_lf": derived.downspout_lf,
                "balcony_count": derived.balcony_count,
                "balcony_wp_sf": derived.balcony_waterproofing_sf,
                "balcony_railing_lf": derived.balcony_railing_lf,
                "coping_lf": derived.coping_lf,
                "sealant_lf": derived.perimeter_sealant_lf,
            },
            "derivation_log": derived.derivation_log,
            "confidence_notes": derived.confidence_notes,
            "schedule_of_values": {
                "building_id": sov.building_id,
                "total_value": sov.total_value,
                "items": [
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
                ],
            },
        })

    return JSONResponse({
        "success": True,
        "building_count": len(results),
        "buildings": results,
        "project_total": sum(r["schedule_of_values"]["total_value"] for r in results),
    })


@app.post("/api/v1/rom/estimate")
async def api_rom_estimate(request: Request):
    """ROM (Rough Order of Magnitude) preliminary estimate.

    Generates a quick envelope estimate from minimal inputs using the
    Deductive Ratio Engine + Live DDC-CWICR Cost Catalog.

    No PDF upload required — just provide building SF, stories, and unit count.
    Accuracy: +/- 25% (AACE Class 5).

    Request body:
    {
        "project_name": "Parkview Apartments",
        "buildings": [
            {
                "building_id": "Bldg A",
                "footprint_sf": 12000,
                "stories_above_grade": 4,
                "unit_count": 48,
                "primary_cladding": "fiber_cement_lap",
                "roof_pitch": "flat"
            }
        ]
    }
    """
    body = await request.json()
    project_name = body.get("project_name", "ROM Estimate")
    buildings_input = body.get("buildings", [body])

    rom = rom_estimator.estimate(
        project_name=project_name,
        buildings=buildings_input,
        overhead_pct=body.get("overhead_pct"),
        profit_pct=body.get("profit_pct"),
    )

    return JSONResponse(rom_estimator.estimate_to_dict(rom))


@app.get("/api/v1/catalog/search")
async def api_catalog_search(
    q: str = "",
    limit: int = 10,
    csi: str = "",
    catalog_type: str = "all",
):
    """Search the live cost catalog (labor + material).

    Connected to DDC-CWICR database via Qdrant vector search when available,
    falls back to built-in US national average catalog.

    Query params:
        q: Search query (e.g., "fiber cement siding", "TPO roofing")
        limit: Max results (default 10)
        csi: CSI division filter (e.g., "07 46" for siding)
        catalog_type: "labor", "material", or "all"
    """
    if not q:
        return JSONResponse({"error": "Query parameter 'q' is required"}, status_code=400)

    result = live_catalog.search(
        query=q,
        limit=limit,
        csi_filter=csi,
        catalog_type=catalog_type,
    )

    return JSONResponse({
        "query": result.query,
        "total_found": result.total_found,
        "search_type": result.search_type,
        "entries": [
            {
                "rate_code": e.rate_code,
                "description": e.description,
                "csi_division": e.csi_division,
                "unit": e.unit,
                "total_unit_price": e.total_unit_price,
                "material_unit_price": e.material_unit_price,
                "labor_unit_price": e.labor_unit_price,
                "equipment_unit_price": e.equipment_unit_price,
                "source": e.source,
                "match_score": e.match_score,
                "labor": {
                    "crew_size": e.labor.crew_size,
                    "labor_hours_per_unit": e.labor.labor_hours_per_unit,
                    "labor_cost_per_unit": e.labor.labor_cost_per_unit,
                } if e.labor else None,
                "materials": [
                    {
                        "resource_code": m.resource_code,
                        "resource_name": m.resource_name,
                        "unit": m.unit,
                        "unit_price": m.unit_price,
                    }
                    for m in e.materials
                ] if e.materials else [],
            }
            for e in result.entries
        ],
    })


@app.get("/api/v1/catalog/division/{csi_code}")
async def api_catalog_division(csi_code: str):
    """Browse all catalog entries for a CSI MasterFormat division.

    Examples:
        /api/v1/catalog/division/07 46  → Siding
        /api/v1/catalog/division/07 54  → TPO Roofing
        /api/v1/catalog/division/08 51  → Windows
    """
    entries = live_catalog.browse_division(csi_code)
    return JSONResponse({
        "csi_division": csi_code,
        "total_entries": len(entries),
        "entries": [
            {
                "description": e.description,
                "unit": e.unit,
                "total_unit_price": e.total_unit_price,
                "material_unit_price": e.material_unit_price,
                "labor_unit_price": e.labor_unit_price,
                "equipment_unit_price": e.equipment_unit_price,
                "source": e.source,
            }
            for e in entries
        ],
    })


@app.get("/api/v1/catalog/labor")
async def api_catalog_labor(q: str = ""):
    """Search the labor rate catalog.

    Returns crew compositions, labor hours, and wage rates from DDC-CWICR.
    """
    if not q:
        return JSONResponse({"error": "Query parameter 'q' is required"}, status_code=400)

    rates = live_catalog.get_labor_rates(q)
    return JSONResponse({
        "query": q,
        "total_found": len(rates),
        "labor_rates": [
            {
                "rate_code": r.rate_code,
                "description": r.description,
                "unit": r.unit,
                "crew_size": r.crew_size,
                "workers": r.workers_count,
                "engineers": r.engineers_count,
                "machinists": r.machinists_count,
                "labor_hours_per_unit": r.labor_hours_per_unit,
                "labor_cost_per_unit": r.labor_cost_per_unit,
                "source": r.source,
            }
            for r in rates
        ],
    })


@app.get("/api/v1/catalog/materials")
async def api_catalog_materials(q: str = ""):
    """Search the material pricing catalog.

    Returns material unit costs from DDC-CWICR database.
    """
    if not q:
        return JSONResponse({"error": "Query parameter 'q' is required"}, status_code=400)

    prices = live_catalog.get_material_prices(q)
    return JSONResponse({
        "query": q,
        "total_found": len(prices),
        "materials": [
            {
                "resource_code": m.resource_code,
                "resource_name": m.resource_name,
                "unit": m.unit,
                "unit_price": m.unit_price,
                "category": m.category,
                "source": m.source,
            }
            for m in prices
        ],
    })


@app.post("/api/v1/feedback")
async def api_record_feedback(
    estimate_id: str = Form(...),
    actual_cost: float = Form(0),
    client_rating: int = Form(0),
    won_bid: Optional[str] = Form(None),
    lost_reason: str = Form(""),
    notes: str = Form(""),
):
    """Record feedback on a past estimate."""
    feedback_type = FeedbackType.ACTUAL_COST
    if client_rating > 0:
        feedback_type = FeedbackType.CLIENT_RATING

    won = None
    if won_bid == "true":
        won = True
        feedback_type = FeedbackType.WON_LOST
    elif won_bid == "false":
        won = False
        feedback_type = FeedbackType.WON_LOST

    record = learning_engine.record_feedback(
        estimate_id=estimate_id,
        feedback_type=feedback_type,
        actual_total=actual_cost,
        client_rating=client_rating,
        won_bid=won,
        lost_reason=lost_reason,
        field_notes=notes,
    )

    return JSONResponse({
        "success": True,
        "feedback_id": record.feedback_id,
        "variance_percent": record.variance_percent,
    })


@app.post("/api/v1/learning/generate-insights")
async def api_generate_insights():
    """Trigger AI insight generation."""
    insights = learning_engine.generate_insights(force=True)
    return JSONResponse({
        "success": True,
        "insights_count": len(insights),
        "insights": [
            {
                "title": ins.title,
                "category": ins.category,
                "severity": ins.severity,
                "description": ins.description,
                "recommendation": ins.recommendation,
            }
            for ins in insights
        ],
    })


@app.get("/api/v1/learning/dashboard")
async def api_learning_dashboard():
    """Get learning engine dashboard data as JSON."""
    dashboard = learning_engine.get_dashboard()
    return JSONResponse({
        "total_estimates": dashboard.total_estimates,
        "total_feedback": dashboard.total_feedback_records,
        "avg_accuracy": dashboard.avg_accuracy,
        "win_rate": dashboard.win_rate,
        "avg_client_rating": dashboard.avg_client_rating,
        "calibrations": dashboard.top_calibration_factors,
        "recent_insights": dashboard.recent_insights,
    })


@app.get("/api/v1/estimates")
async def api_list_estimates():
    """List all recorded estimates."""
    estimates_dir = learning_engine.data_dir / "estimates"
    results = []
    if estimates_dir.exists():
        for ef in sorted(estimates_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            results.append(json.loads(ef.read_text()))
    return JSONResponse(results)


# ---------------------------------------------------------------------------
# AI ASSISTANT CHAT — Handoff-style integrated agent
# ---------------------------------------------------------------------------

# Anthropic client for AI chat
_chat_client = None

def _get_chat_client():
    global _chat_client
    if _chat_client is None:
        _chat_client = anthropic.Anthropic(api_key=settings.anthropic.api_key)
    return _chat_client


AI_CHAT_SYSTEM = """You are the AI Estimating Agent for Envelope Estimator, a construction estimating platform.
You help contractors and homeowners with:

1. Creating construction cost estimates from project descriptions, photos, or plans
2. Explaining estimate line items, pricing, and trade breakdowns
3. Answering construction questions (materials, methods, codes, best practices)
4. Providing pricing benchmarks ("how much does X typically cost?")
5. Interpreting the AI Learning Engine data (accuracy, calibration, trends)

When a user describes a project, provide a helpful estimate range and suggest
they use the Self-Service Scan workflow for a detailed 5D estimate.

Keep responses concise, professional, and actionable. Use bullet points for lists.
Format currency as $X,XXX. You are an expert with 30+ years of construction estimating experience."""


@app.post("/api/v1/ai/chat")
async def api_ai_chat(request: Request):
    """AI assistant chat endpoint — powers the Handoff-style agent."""
    body = await request.json()
    message = body.get("message", "").strip()

    if not message:
        return JSONResponse({"response": "Please type a message to get started."})

    # Gather context from learning engine for grounding
    dashboard = learning_engine.get_dashboard()
    context = (
        f"Platform stats: {dashboard.total_estimates} estimates recorded, "
        f"{dashboard.avg_accuracy:.1f}% accuracy, {dashboard.win_rate:.1f}% win rate. "
    )

    # Check for recent comparable data
    estimates_dir = learning_engine.data_dir / "estimates"
    recent_count = len(list(estimates_dir.glob("*.json"))) if estimates_dir.exists() else 0
    context += f"{recent_count} projects in the database."

    try:
        client = _get_chat_client()
        response = client.messages.create(
            model=settings.anthropic.model_fast,
            max_tokens=2048,
            system=AI_CHAT_SYSTEM,
            messages=[
                {"role": "user", "content": f"[Platform context: {context}]\n\nUser question: {message}"},
            ],
        )
        reply = response.content[0].text

        # Convert markdown-style formatting to simple HTML
        reply = reply.replace("\n\n", "<br><br>")
        reply = reply.replace("\n- ", "<br>&bull; ")
        reply = reply.replace("\n* ", "<br>&bull; ")
        reply = reply.replace("**", "<strong>", 1)
        # Handle remaining bold markers
        reply = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', reply)

        return JSONResponse({"response": reply})

    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return JSONResponse({
            "response": (
                "I'm having trouble connecting to the AI service right now. "
                "Please check that your <strong>ANTHROPIC_API_KEY</strong> is set correctly.<br><br>"
                "In the meantime, you can:<br>"
                "&bull; <a href='/self-service'>Create a new estimate</a> using the intake form<br>"
                "&bull; <a href='/estimates'>View existing estimates</a><br>"
                "&bull; <a href='/learning'>Check the AI Learning dashboard</a>"
            )
        })
