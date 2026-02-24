"""
Envelope Estimator Agent - Main Orchestrator

Three integrated workflows:

  1. COMMERCIAL ESTIMATING (ITB → Takeoff → Estimate → Proposal)
     python agent.py --pdf plans.pdf

  2. SATELLITE ROOF REPORT (Address → EagleView-style measurement report)
     python agent.py --roof-report --address "123 Main St, Denver, CO 80202"

  3. PROPERTY LOSS ESTIMATE (Photos → Xactimate-style insurance claim)
     python agent.py --loss-report --address "123 Main St" --photos dmg1.jpg dmg2.jpg

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

        return report

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

    if args.roof_report:
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
        print("  THREE WORKFLOWS:")
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
        print('     python agent.py --loss-report --address "789 Elm St" --photos *.jpg \\')
        print('       --cause wind --homeowner "John Doe" --insurance "State Farm" --deductible 2500')


if __name__ == "__main__":
    main()
