"""
Envelope Estimator — Web Application

FastAPI web app wrapping all 5 estimation workflows into a browser-based platform.

Endpoints:
  /                          → Main dashboard
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
