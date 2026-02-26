"""
Envelope Estimator Agent - Main Orchestrator

Seven integrated workflows:

  1. COMMERCIAL ESTIMATING (ITB → Takeoff → Estimate → Proposal)
     python agent.py --pdf plans.pdf

  2. SATELLITE ROOF REPORT (Address → EagleView-style measurement report)
     python agent.py --roof-report --address "123 Main St, Denver, CO 80202"

  3. PROPERTY LOSS ESTIMATE (Photos → Xactimate-style insurance claim)
     python agent.py --loss-report --address "123 Main St" --photos dmg1.jpg dmg2.jpg

  4. SELF-SERVICE SCAN → 5D ESTIMATE (Customer form → scan link → instant estimate)
     python agent.py --self-service --customer-name "Jane Doe" --customer-email "jane@example.com" \
       --address "123 Main St" --project-type residential_roof
     python agent.py --process-scan --session-id SS-20260224-ABC123 --scan-photos front.jpg back.jpg

  5. LEARNING DASHBOARD (View AI learning engine stats and insights)
     python agent.py --learning-dashboard
     python agent.py --record-feedback --estimate-id EST-SS-... --actual-cost 45000

Additional modes:
  python agent.py --monitor          # Continuous email/folder watch
  python agent.py --pdf plans.pdf --trades SID,ROF,GUT,WIN
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from config.settings import Settings, load_settings
from config.trades import (
    ALL_TRADES,
    PHASE_1_TRADES,
    PHASE_2_TRADES,
    TRADE_BY_CODE,
    Phase,
)
from modules.cost_engine import CostEngine, EstimateResult
from modules.itb_intake import ITBIntake, ProjectInfo
from modules.pdf_takeoff import PDFTakeoff, TakeoffResult
from modules.proposal_gen import ProposalGenerator
from modules.roof_report import RoofReportGenerator, RoofReport
from modules.property_loss import PropertyLossEstimator, PropertyLossReport
from modules.self_service_scan import (
    SelfServiceScanManager,
    CustomerIntakeForm,
    ScanSubmission,
    ScanPhoto,
    ScanMeasurement,
    ScanPhotoType,
    ProjectType,
    FiveDEstimate,
)
from modules.ai_learning_engine import AILearningEngine, FeedbackType

logger = logging.getLogger("envelope_estimator")


class EnvelopeEstimatorAgent:
    """Main orchestrator for all estimating pipelines."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self._setup_logging()

        # Commercial estimating modules
        self.intake = ITBIntake(self.settings)
        self.takeoff = PDFTakeoff(self.settings)
        self.cost_engine = CostEngine(self.settings)
        self.proposal_gen = ProposalGenerator(self.settings)

        # Satellite roof report module
        self.roof_report_gen = RoofReportGenerator(self.settings)

        # Property loss / insurance estimate module
        self.loss_estimator = PropertyLossEstimator(self.settings)

        # Self-service scan → 5D estimate module
        self.scan_manager = SelfServiceScanManager(self.settings)

        # AI learning engine (feeds from ALL workflows)
        self.learning = AILearningEngine(self.settings)

        # Determine active trades based on enabled phases
        self.active_trades = []
        for phase_num in self.settings.enabled_phases:
            if phase_num == 1:
                self.active_trades.extend(PHASE_1_TRADES)
            elif phase_num == 2:
                self.active_trades.extend(PHASE_2_TRADES)

        logger.info(
            f"Agent initialized with {len(self.active_trades)} trades "
            f"(phases: {self.settings.enabled_phases})"
        )

    def _setup_logging(self):
        logging.basicConfig(
            level=getattr(logging, self.settings.log_level, logging.INFO),
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # ==================================================================
    # WORKFLOW 1: Commercial Estimating (ITB → Takeoff → Estimate → Proposal)
    # ==================================================================

    def process_plans(
        self,
        pdf_paths: list[str],
        project_name: str = "",
        trade_codes: list[str] | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Process a set of plans through the full pipeline.

        Returns dict with proposal paths and summary data.
        """
        start_time = time.time()

        # Determine which trades to estimate
        if trade_codes:
            trades = [
                TRADE_BY_CODE[c] for c in trade_codes if c in TRADE_BY_CODE
            ]
        else:
            trades = self.active_trades

        logger.info(
            f"Processing {len(pdf_paths)} PDFs for "
            f"{len(trades)} trades: {[t.name for t in trades]}"
        )

        # Step 1: Create project info
        print("\n[1/4] Registering project...")
        project = self.intake.process_api_submission(
            project_name=project_name or Path(pdf_paths[0]).stem,
            pdf_paths=pdf_paths,
            metadata=metadata,
        )
        print(f"       Project: {project.project_name} ({project.project_id})")
        if project.requested_trades:
            print(f"       Detected trades: {project.requested_trades}")

        # Step 2: Run takeoff
        print("\n[2/4] Running PDF takeoff (Claude Vision)...")
        takeoff_result = self.takeoff.process(
            pdf_paths=pdf_paths,
            trades=trades,
            project_id=project.project_id,
        )
        print(
            f"       Sheets identified: {len(takeoff_result.sheets_identified)}"
        )
        print(f"       Line items: {len(takeoff_result.line_items)}")
        print(
            f"       Confidence: {takeoff_result.confidence_score:.0%} | "
            f"Variance: {takeoff_result.validation_variance_pct:.1f}%"
        )
        if takeoff_result.roof_pitch:
            print(
                f"       Roof: {takeoff_result.roof_pitch} "
                f"(multiplier: {takeoff_result.roof_pitch_multiplier:.3f})"
            )
        if takeoff_result.warnings:
            for w in takeoff_result.warnings:
                print(f"       WARNING: {w}")

        # Step 3: Price it
        print("\n[3/4] Running cost estimation (DDC-CWICR)...")
        estimate = self.cost_engine.estimate(
            takeoff=takeoff_result,
            trades=trades,
        )
        print(f"       Trades priced: {len(estimate.trade_summaries)}")
        for ts in estimate.trade_summaries:
            print(f"         {ts.trade_name}: ${ts.trade_total:,.2f}")
        print(f"       Grand Total: ${estimate.grand_total:,.2f}")
        if estimate.cost_per_sf:
            print(f"       Cost/SF: ${estimate.cost_per_sf:,.2f}")

        # Step 4: Generate proposal
        print("\n[4/4] Generating proposal...")
        proposal = self.proposal_gen.generate(
            project=project,
            takeoff=takeoff_result,
            estimate=estimate,
        )

        elapsed = time.time() - start_time
        print(f"\nComplete in {elapsed:.1f}s")
        print(f"  Proposal: {proposal['html']}")
        print(f"  Summary:  {proposal['json']}")
        print(f"  Total:    ${proposal['grand_total']:,.2f}")

        # Save full pipeline output
        self._save_pipeline_output(
            project, takeoff_result, estimate, proposal
        )

        # Feed into learning engine
        trade_costs = {
            ts.trade_name: ts.trade_total for ts in estimate.trade_summaries
        }
        self.learning.record_estimate(
            estimate_id=project.project_id,
            workflow="commercial",
            project_type="commercial",
            total_sf=takeoff_result.building_footprint_sf,
            roof_sf=0,
            wall_sf=takeoff_result.net_wall_area_sf,
            stories=1,
            roof_pitch=takeoff_result.roof_pitch or "",
            estimated_materials=estimate.grand_total * 0.45,  # approx split
            estimated_labor=estimate.grand_total * 0.45,
            estimated_total=estimate.grand_total,
            trade_costs=trade_costs,
            line_item_count=len(takeoff_result.line_items),
            confidence_score=takeoff_result.confidence_score,
            data_source="pdf_plans",
        )

        return {
            "project": project,
            "takeoff": takeoff_result,
            "estimate": estimate,
            "proposal": proposal,
            "elapsed_seconds": elapsed,
        }

    # ==================================================================
    # WORKFLOW 2: Satellite Roof Report (address → EagleView-style report)
    # ==================================================================

    def generate_roof_report(
        self,
        address: str,
        city: str = "",
        state: str = "",
        postal_code: str = "",
        homeowner_name: str = "",
    ) -> RoofReport:
        """Generate a satellite-based roof measurement report from an address.

        Uses Google Solar API + DataLayers GeoTIFF + Claude Vision to produce
        a professional 3-page HTML report with area, pitch, edges, materials BOM.
        """
        print("=" * 60)
        print("  SATELLITE ROOF MEASUREMENT REPORT")
        print("=" * 60)
        print(f"  Address: {address}")
        if city:
            print(f"  City:    {city}, {state} {postal_code}")
        print()

        report = self.roof_report_gen.generate(
            address=address,
            city=city,
            state=state,
            postal_code=postal_code,
            homeowner_name=homeowner_name,
        )

        print(f"\n  Report: {report.report_number}")
        print(f"  Area:   {report.total_true_area_sqft:,.0f} SF (3D)")
        print(f"  Pitch:  {report.roof_pitch_ratio} ({report.roof_pitch_degrees:.1f} deg)")
        print(f"  Facets: {len(report.segments)}")
        print(f"  Materials: ${report.materials.total_cost:,.2f}")
        print(f"  Provider: {report.quality.provider}")
        print(f"  Confidence: {report.quality.confidence_score}%")

        # Feed into learning engine
        self.learning.record_estimate(
            estimate_id=report.report_number,
            workflow="roof_report",
            project_type="residential_roof",
            total_sf=report.total_true_area_sqft,
            roof_sf=report.total_true_area_sqft,
            estimated_materials=report.materials.total_cost,
            estimated_total=report.materials.total_cost,
            confidence_score=report.quality.confidence_score / 100.0,
            data_source="satellite",
            city=city,
            state=state,
            postal_code=postal_code,
        )

        return report

    # ==================================================================
    # WORKFLOW 3: Property Loss Estimate (photos → Xactimate-style claim)
    # ==================================================================

    def generate_loss_report(
        self,
        address: str,
        photo_paths: list[str],
        cause_of_loss: str = "",
        date_of_loss: str = "",
        homeowner_name: str = "",
        homeowner_phone: str = "",
        policy_number: str = "",
        insurance_company: str = "",
        deductible: float = 1000.0,
        city: str = "",
        state: str = "",
        postal_code: str = "",
        include_roof_report: bool = False,
    ) -> PropertyLossReport:
        """Generate an Xactimate-style property loss / insurance estimate.

        Analyzes damage photos with AI, generates line-item estimate with
        labor/material breakdowns, depreciation, and ACV/RCV calculations.

        If include_roof_report=True, also runs satellite roof measurement
        to get accurate roof area/pitch for the damage estimate.
        """
        print("=" * 60)
        print("  PROPERTY LOSS / INSURANCE ESTIMATE")
        print("=" * 60)
        print(f"  Address: {address}")
        print(f"  Photos:  {len(photo_paths)}")
        if cause_of_loss:
            print(f"  Cause:   {cause_of_loss}")
        print()

        # Optionally run roof report first
        roof_report = None
        if include_roof_report and self.settings.google_api_key:
            print("[Pre-step] Generating satellite roof measurements...")
            roof_report = self.roof_report_gen.generate(
                address=address, city=city, state=state, postal_code=postal_code,
            )
            print(f"  Roof: {roof_report.total_true_area_sqft:,.0f} SF @ {roof_report.roof_pitch_ratio}\n")

        report = self.loss_estimator.generate(
            address=address,
            photo_paths=photo_paths,
            cause_of_loss=cause_of_loss,
            date_of_loss=date_of_loss,
            homeowner_name=homeowner_name,
            homeowner_phone=homeowner_phone,
            policy_number=policy_number,
            insurance_company=insurance_company,
            deductible=deductible,
            city=city,
            state=state,
            postal_code=postal_code,
            roof_report=roof_report,
        )

        # Feed into learning engine
        self.learning.record_estimate(
            estimate_id=report.claim_number,
            workflow="loss_report",
            project_type="insurance_claim",
            total_sf=report.total_area_sf if hasattr(report, "total_area_sf") else 0,
            roof_sf=report.roof_area_sf if hasattr(report, "roof_area_sf") else 0,
            estimated_materials=report.total_materials if hasattr(report, "total_materials") else 0,
            estimated_labor=report.total_labor if hasattr(report, "total_labor") else 0,
            estimated_total=report.rcv_total if hasattr(report, "rcv_total") else 0,
            confidence_score=report.confidence_score if hasattr(report, "confidence_score") else 0,
            data_source="photos",
            photo_count=len(photo_paths),
            city=city,
            state=state,
            postal_code=postal_code,
        )

        return report

    # ==================================================================
    # WORKFLOW 4: Self-Service Scan → 5D Estimate (no salesman needed)
    # ==================================================================

    def create_self_service_session(
        self,
        customer_name: str,
        customer_email: str,
        property_address: str,
        project_type: str = "residential_full_exterior",
        customer_phone: str = "",
        city: str = "",
        state: str = "",
        postal_code: str = "",
        project_description: str = "",
        is_insurance_claim: bool = False,
        cause_of_loss: str = "",
        delivery_method: str = "email",
    ) -> dict:
        """Create a self-service scan session and send the customer a scan link.

        The customer receives a magic link, takes guided photos of their property,
        and submits. The system auto-generates a 5D estimate (scope + schedule + cost)
        without any salesman visiting the site.
        """
        print("=" * 60)
        print("  SELF-SERVICE SCAN → 5D ESTIMATE")
        print("=" * 60)
        print(f"  Customer: {customer_name}")
        print(f"  Email:    {customer_email}")
        print(f"  Address:  {property_address}")
        print(f"  Type:     {project_type}")
        print()

        # Build intake form
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

        # Create session
        print("[1/2] Creating scan session...")
        session = self.scan_manager.create_session(intake)
        print(f"       Session ID: {session.session_id}")
        print(f"       Scan Link:  {session.scan_link}")
        print(f"       Expires:    {session.expires_at}")

        # Send link to customer
        print(f"\n[2/2] Sending scan link via {delivery_method}...")
        delivery = self.scan_manager.send_scan_link(session, delivery_method)
        for channel in delivery.get("channels", []):
            print(f"       {channel['channel'].upper()}: {channel['status']} → {channel['recipient']}")

        print(f"\nSession created. Customer will receive scan instructions.")
        print(f"When they submit, run:")
        print(f"  python agent.py --process-scan --session-id {session.session_id} --scan-photos <photos>")

        return {
            "session_id": session.session_id,
            "scan_link": session.scan_link,
            "expires_at": session.expires_at,
            "delivery": delivery,
        }

    def process_self_service_scan(
        self,
        session_id: str,
        photo_paths: list[str],
        measurements: dict | None = None,
        notes: str = "",
    ) -> FiveDEstimate:
        """Process a completed self-service scan and generate a 5D estimate.

        Called after the customer submits their photos through the scan portal.
        """
        print("=" * 60)
        print("  PROCESSING SELF-SERVICE SCAN → 5D ESTIMATE")
        print("=" * 60)
        print(f"  Session: {session_id}")
        print(f"  Photos:  {len(photo_paths)}")
        print()

        # Build scan submission
        photos = []
        photo_type_cycle = [
            ScanPhotoType.FRONT_ELEVATION,
            ScanPhotoType.REAR_ELEVATION,
            ScanPhotoType.LEFT_ELEVATION,
            ScanPhotoType.RIGHT_ELEVATION,
            ScanPhotoType.ROOF_OVERVIEW,
            ScanPhotoType.CLOSE_UP_DAMAGE,
            ScanPhotoType.MATERIAL_DETAIL,
        ]
        for i, path in enumerate(photo_paths):
            photo_type = photo_type_cycle[i % len(photo_type_cycle)]
            photos.append(ScanPhoto(
                photo_type=photo_type,
                file_path=path,
                label=Path(path).stem.replace("_", " ").replace("-", " ").title(),
                timestamp=datetime.now().isoformat(),
            ))

        scan_measurements = []
        if measurements:
            for field_name, value in measurements.items():
                scan_measurements.append(ScanMeasurement(
                    field_name=field_name,
                    value=str(value),
                ))

        submission = ScanSubmission(
            session_id=session_id,
            photos=photos,
            measurements=scan_measurements,
            notes=notes,
            submitted_at=datetime.now().isoformat(),
        )

        # Process through the 5D pipeline
        estimate = self.scan_manager.process_submission(submission)

        print(f"\n{'=' * 60}")
        print(f"  5D ESTIMATE COMPLETE")
        print(f"{'=' * 60}")
        print(f"  Estimate ID:  {estimate.estimate_id}")
        print(f"  Grand Total:  ${estimate.grand_total:,.2f}")
        print(f"  Duration:     {estimate.total_project_days} days")
        print(f"  Labor Hours:  {estimate.total_labor_hours:,.1f}")
        print(f"  Confidence:   {estimate.confidence_score:.0%}")
        print(f"  Report:       {estimate.report_html_path}")

        # Feed into learning engine
        self.learning.record_estimate(
            estimate_id=estimate.estimate_id,
            workflow="self_service",
            project_type=estimate.project_type,
            total_sf=estimate.total_area_sf,
            roof_sf=0,
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
            photo_count=len(photo_paths),
        )

        return estimate

    # ==================================================================
    # WORKFLOW 5: Learning Dashboard & Feedback
    # ==================================================================

    def show_learning_dashboard(self):
        """Display the AI learning engine dashboard."""
        print("=" * 60)
        print("  AI LEARNING ENGINE — DASHBOARD")
        print("=" * 60)

        dashboard = self.learning.get_dashboard()

        print(f"\n  Estimates Recorded:    {dashboard.total_estimates}")
        print(f"  Feedback Records:     {dashboard.total_feedback_records}")
        print(f"  Avg Accuracy:         {dashboard.avg_accuracy:.1f}%")
        print(f"  Bid Win Rate:         {dashboard.win_rate:.1f}%")
        print(f"  Avg Client Rating:    {dashboard.avg_client_rating:.1f}/5")

        if dashboard.top_calibration_factors:
            print(f"\n  Top Calibration Adjustments:")
            for cf in dashboard.top_calibration_factors:
                direction = "+" if cf["factor"] > 1.0 else ""
                print(f"    {cf['dimension']}: {direction}{(cf['factor']-1)*100:.1f}% ({cf['samples']} samples)")

        if dashboard.recent_insights:
            print(f"\n  Recent Insights:")
            for insight in dashboard.recent_insights:
                icon = {"info": "i", "warning": "!", "action_required": "*"}.get(insight["severity"], "-")
                print(f"    [{icon}] {insight['title']}")

        print(f"\n  Last Analysis: {dashboard.last_analysis_at}")
        return dashboard

    def record_feedback(
        self,
        estimate_id: str,
        actual_cost: float = 0.0,
        actual_materials: float = 0.0,
        actual_labor: float = 0.0,
        actual_days: int = 0,
        client_rating: int = 0,
        won_bid: bool | None = None,
        lost_reason: str = "",
        notes: str = "",
    ):
        """Record feedback on a past estimate (actual costs, ratings, win/loss)."""
        feedback_type = FeedbackType.ACTUAL_COST
        if client_rating > 0:
            feedback_type = FeedbackType.CLIENT_RATING
        if won_bid is not None:
            feedback_type = FeedbackType.WON_LOST

        record = self.learning.record_feedback(
            estimate_id=estimate_id,
            feedback_type=feedback_type,
            actual_total=actual_cost,
            actual_materials=actual_materials,
            actual_labor=actual_labor,
            actual_days=actual_days,
            client_rating=client_rating,
            won_bid=won_bid,
            lost_reason=lost_reason,
            field_notes=notes,
        )

        print(f"Feedback recorded: {record.feedback_id}")
        if record.variance_percent:
            print(f"  Variance: {record.variance_percent:+.1f}%")
        if client_rating:
            print(f"  Rating: {client_rating}/5")
        if won_bid is not None:
            print(f"  Bid: {'WON' if won_bid else 'LOST'}")

    # ------------------------------------------------------------------
    # Continuous monitoring mode
    # ------------------------------------------------------------------

    def monitor(self):
        """Run in continuous mode, watching email and folders for ITBs."""
        logger.info("Starting monitoring mode...")
        print("Envelope Estimator Agent - Monitoring Mode")
        print(f"  Email: {self.settings.email.imap_server or 'not configured'}")
        print(
            f"  Folder: {self.settings.watched_folder.path or 'not configured'}"
        )
        print(f"  Trades: {[t.name for t in self.active_trades]}")
        print("  Press Ctrl+C to stop\n")

        while True:
            try:
                # Check email
                email_projects = self.intake.check_email()
                for project in email_projects:
                    logger.info(
                        f"New ITB from email: {project.project_name}"
                    )
                    self._process_itb(project)

                # Check watched folder
                folder_projects = self.intake.check_watched_folder()
                for project in folder_projects:
                    logger.info(
                        f"New plans from folder: {project.project_name}"
                    )
                    self._process_itb(project)

                # Sleep between checks
                interval = min(
                    self.settings.email.check_interval_seconds,
                    self.settings.watched_folder.check_interval_seconds or 300,
                )
                time.sleep(interval)

            except KeyboardInterrupt:
                print("\nMonitoring stopped.")
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(60)  # back off on error

    def _process_itb(self, project: ProjectInfo):
        """Process a detected ITB through the full pipeline."""
        if not project.pdf_paths:
            logger.warning(
                f"No PDFs for project {project.project_name}, skipping"
            )
            return

        try:
            result = self.process_plans(
                pdf_paths=project.pdf_paths,
                project_name=project.project_name,
            )

            if self.settings.require_human_review:
                logger.info(
                    f"Proposal ready for review: "
                    f"{result['proposal']['html']}"
                )
            else:
                logger.info(
                    f"Proposal auto-generated: "
                    f"{result['proposal']['html']}"
                )

        except Exception as e:
            logger.error(
                f"Failed to process ITB {project.project_name}: {e}"
            )

    # ------------------------------------------------------------------
    # Output persistence
    # ------------------------------------------------------------------

    def _save_pipeline_output(
        self,
        project: ProjectInfo,
        takeoff: TakeoffResult,
        estimate: EstimateResult,
        proposal: dict,
    ):
        """Save complete pipeline data for audit trail."""
        output_dir = Path(self.settings.output_dir) / "pipeline"
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{project.project_id}_pipeline.json"
        data = {
            "timestamp": datetime.now().isoformat(),
            "project_id": project.project_id,
            "project_name": project.project_name,
            "takeoff_summary": {
                "sheets": len(takeoff.sheets_identified),
                "line_items": len(takeoff.line_items),
                "confidence": takeoff.confidence_score,
                "variance": takeoff.validation_variance_pct,
                "building_footprint_sf": takeoff.building_footprint_sf,
                "roof_pitch": takeoff.roof_pitch,
                "gross_wall_sf": takeoff.gross_wall_area_sf,
                "net_wall_sf": takeoff.net_wall_area_sf,
            },
            "estimate_summary": {
                "trades": len(estimate.trade_summaries),
                "grand_total": estimate.grand_total,
                "cost_per_sf": estimate.cost_per_sf,
                "currency": estimate.currency,
            },
            "proposal_files": proposal,
        }
        (output_dir / filename).write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Envelope Estimator Agent - AI Construction Estimating Platform"
    )

    # Workflow 1: Commercial plans
    parser.add_argument(
        "--pdf", nargs="+",
        help="PDF plan file(s) to process (commercial estimating)",
    )
    parser.add_argument("--folder", help="Folder containing PDF plans")
    parser.add_argument(
        "--monitor", action="store_true",
        help="Continuous monitoring mode (email + folder watch)",
    )
    parser.add_argument("--trades", help="Trade codes (e.g., SID,ROF,GUT,WIN)")
    parser.add_argument("--name", help="Project name")
    parser.add_argument("--phases", help="Phase numbers (e.g., 1,2)")

    # Workflow 2: Satellite roof report
    parser.add_argument(
        "--roof-report", action="store_true",
        help="Generate satellite roof measurement report",
    )

    # Workflow 3: Property loss / insurance estimate
    parser.add_argument(
        "--loss-report", action="store_true",
        help="Generate property loss / insurance estimate",
    )
    parser.add_argument("--photos", nargs="+", help="Damage photo file(s)")

    # Workflow 4: Self-service scan → 5D estimate
    parser.add_argument(
        "--self-service", action="store_true",
        help="Create self-service scan session (sends customer a scan link)",
    )
    parser.add_argument("--customer-name", help="Customer full name")
    parser.add_argument("--customer-email", help="Customer email address")
    parser.add_argument("--customer-phone", help="Customer phone number", default="")
    parser.add_argument(
        "--project-type", default="residential_full_exterior",
        help="Project type (residential_roof, residential_siding, residential_full_exterior, insurance_claim, etc.)",
    )
    parser.add_argument("--project-desc", help="Project description", default="")
    parser.add_argument(
        "--process-scan", action="store_true",
        help="Process a submitted self-service scan into a 5D estimate",
    )
    parser.add_argument("--session-id", help="Scan session ID to process")
    parser.add_argument("--scan-photos", nargs="+", help="Scan photo file(s)")
    parser.add_argument("--scan-notes", help="Customer notes from scan", default="")

    # Workflow 5: Learning engine
    parser.add_argument(
        "--learning-dashboard", action="store_true",
        help="Show AI learning engine dashboard",
    )
    parser.add_argument(
        "--record-feedback", action="store_true",
        help="Record feedback on a past estimate",
    )
    parser.add_argument("--estimate-id", help="Estimate ID for feedback")
    parser.add_argument("--actual-cost", type=float, help="Actual project cost", default=0)
    parser.add_argument("--client-rating", type=int, help="Client rating (1-5)", default=0)
    parser.add_argument("--won", action="store_true", help="Mark bid as won", default=None)
    parser.add_argument("--lost", help="Mark bid as lost (provide reason)", default=None)
    parser.add_argument(
        "--generate-insights", action="store_true",
        help="Generate AI learning insights from accumulated data",
    )

    # Shared arguments
    parser.add_argument("--address", help="Property address")
    parser.add_argument("--city", help="City", default="")
    parser.add_argument("--state", help="State", default="")
    parser.add_argument("--zip", help="Postal/ZIP code", default="")
    parser.add_argument("--homeowner", help="Homeowner name", default="")
    parser.add_argument("--cause", help="Cause of loss (hail/wind/water/fire)")
    parser.add_argument("--date-of-loss", help="Date of loss (YYYY-MM-DD)")
    parser.add_argument("--policy", help="Insurance policy number")
    parser.add_argument("--insurance", help="Insurance company name")
    parser.add_argument(
        "--deductible", type=float, default=1000.0,
        help="Insurance deductible amount (default: $1000)",
    )
    parser.add_argument(
        "--with-roof", action="store_true",
        help="Include satellite roof measurement with loss report",
    )

    args = parser.parse_args()
    settings = load_settings()

    if args.phases:
        settings.enabled_phases = [
            int(p.strip()) for p in args.phases.split(",")
        ]

    agent = EnvelopeEstimatorAgent(settings)

    # ---- Workflow routing ----

    if args.self_service:
        if not args.customer_name or not args.customer_email or not args.address:
            print("Error: --customer-name, --customer-email, and --address are required for --self-service")
            sys.exit(1)
        agent.create_self_service_session(
            customer_name=args.customer_name,
            customer_email=args.customer_email,
            customer_phone=args.customer_phone,
            property_address=args.address,
            project_type=args.project_type,
            project_description=args.project_desc,
            city=args.city,
            state=args.state,
            postal_code=args.zip,
            is_insurance_claim=(args.project_type == "insurance_claim"),
            cause_of_loss=args.cause or "",
        )

    elif args.process_scan:
        if not args.session_id or not args.scan_photos:
            print("Error: --session-id and --scan-photos are required for --process-scan")
            sys.exit(1)
        agent.process_self_service_scan(
            session_id=args.session_id,
            photo_paths=args.scan_photos,
            notes=args.scan_notes,
        )

    elif args.learning_dashboard:
        agent.show_learning_dashboard()

    elif args.record_feedback:
        if not args.estimate_id:
            print("Error: --estimate-id is required for --record-feedback")
            sys.exit(1)
        won_bid = None
        lost_reason = ""
        if args.won:
            won_bid = True
        elif args.lost is not None:
            won_bid = False
            lost_reason = args.lost
        agent.record_feedback(
            estimate_id=args.estimate_id,
            actual_cost=args.actual_cost,
            client_rating=args.client_rating,
            won_bid=won_bid,
            lost_reason=lost_reason,
        )

    elif args.generate_insights:
        insights = agent.learning.generate_insights(force=True)
        print(f"\nGenerated {len(insights)} insights:")
        for ins in insights:
            print(f"\n  [{ins.severity.upper()}] {ins.title}")
            print(f"  {ins.description}")
            print(f"  → {ins.recommendation}")

    elif args.roof_report:
        if not args.address:
            print("Error: --address is required for --roof-report")
            sys.exit(1)
        agent.generate_roof_report(
            address=args.address,
            city=args.city,
            state=args.state,
            postal_code=args.zip,
            homeowner_name=args.homeowner,
        )

    elif args.loss_report:
        if not args.address:
            print("Error: --address is required for --loss-report")
            sys.exit(1)
        if not args.photos:
            print("Error: --photos is required for --loss-report")
            sys.exit(1)
        agent.generate_loss_report(
            address=args.address,
            photo_paths=args.photos,
            cause_of_loss=args.cause or "",
            date_of_loss=args.date_of_loss or "",
            homeowner_name=args.homeowner,
            policy_number=args.policy or "",
            insurance_company=args.insurance or "",
            deductible=args.deductible,
            city=args.city,
            state=args.state,
            postal_code=args.zip,
            include_roof_report=args.with_roof,
        )

    elif args.monitor:
        agent.monitor()

    elif args.pdf:
        trade_codes = None
        if args.trades:
            trade_codes = [c.strip().upper() for c in args.trades.split(",")]
        agent.process_plans(
            pdf_paths=args.pdf,
            project_name=args.name or "",
            trade_codes=trade_codes,
        )

    elif args.folder:
        folder = Path(args.folder)
        pdfs = sorted(
            list(folder.glob("*.pdf")) + list(folder.glob("*.PDF"))
        )
        if not pdfs:
            print(f"No PDF files found in {args.folder}")
            sys.exit(1)
        trade_codes = None
        if args.trades:
            trade_codes = [c.strip().upper() for c in args.trades.split(",")]
        agent.process_plans(
            pdf_paths=[str(p) for p in pdfs],
            project_name=args.name or folder.name,
            trade_codes=trade_codes,
        )

    else:
        parser.print_help()
        print("\n" + "=" * 60)
        print("  FIVE WORKFLOWS:")
        print("=" * 60)
        print("\n  1. COMMERCIAL ESTIMATING (plans → proposal):")
        print("     python agent.py --pdf plans.pdf")
        print("     python agent.py --pdf sheet1.pdf sheet2.pdf --trades SID,ROF")
        print("     python agent.py --folder ./project_plans/")
        print("     python agent.py --monitor")
        print("\n  2. SATELLITE ROOF REPORT (address → measurement report):")
        print('     python agent.py --roof-report --address "123 Main St, Denver, CO"')
        print('     python agent.py --roof-report --address "456 Oak Ave" --city "Austin" --state TX')
        print("\n  3. PROPERTY LOSS ESTIMATE (photos → insurance claim):")
        print('     python agent.py --loss-report --address "789 Elm St" --photos dmg1.jpg dmg2.jpg')
        print('     python agent.py --loss-report --address "789 Elm St" --photos *.jpg --cause hail --with-roof')
        print("\n  4. SELF-SERVICE SCAN → 5D ESTIMATE (no salesman needed):")
        print('     python agent.py --self-service --customer-name "Jane Doe" \\')
        print('       --customer-email "jane@example.com" --address "123 Main St" --project-type residential_roof')
        print('     python agent.py --process-scan --session-id SS-20260224-ABC123 --scan-photos front.jpg back.jpg')
        print("\n  5. AI LEARNING ENGINE:")
        print("     python agent.py --learning-dashboard")
        print('     python agent.py --record-feedback --estimate-id EST-SS-... --actual-cost 45000')
        print('     python agent.py --record-feedback --estimate-id EST-SS-... --won')
        print("     python agent.py --generate-insights")


if __name__ == "__main__":
    main()
