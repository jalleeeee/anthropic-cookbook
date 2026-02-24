"""
Envelope Estimator Agent - Main Orchestrator

Coordinates the full commercial estimating workflow:
  ITB Intake → PDF Takeoff → Cost Estimation → Proposal Generation

Usage:
  # Process a single set of plans
  python agent.py --pdf plans.pdf

  # Process a folder of plans
  python agent.py --folder /path/to/plans/

  # Start in continuous monitoring mode (email + watched folder)
  python agent.py --monitor

  # Process with specific trades only
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

logger = logging.getLogger("envelope_estimator")


class EnvelopeEstimatorAgent:
    """Main orchestrator for the estimating pipeline."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self._setup_logging()

        self.intake = ITBIntake(self.settings)
        self.takeoff = PDFTakeoff(self.settings)
        self.cost_engine = CostEngine(self.settings)
        self.proposal_gen = ProposalGenerator(self.settings)

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

    # ------------------------------------------------------------------
    # Single project processing
    # ------------------------------------------------------------------

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
        description="Envelope Estimator Agent - AI Commercial Estimating"
    )
    parser.add_argument(
        "--pdf", nargs="+",
        help="PDF plan file(s) to process",
    )
    parser.add_argument(
        "--folder",
        help="Folder containing PDF plans",
    )
    parser.add_argument(
        "--monitor", action="store_true",
        help="Run in continuous monitoring mode (email + folder watch)",
    )
    parser.add_argument(
        "--trades",
        help="Comma-separated trade codes (e.g., SID,ROF,GUT,WIN)",
    )
    parser.add_argument(
        "--name",
        help="Project name (default: derived from filename)",
    )
    parser.add_argument(
        "--phases",
        help="Comma-separated phase numbers to enable (e.g., 1,2)",
    )

    args = parser.parse_args()

    # Load settings
    settings = load_settings()

    # Override phases if specified
    if args.phases:
        settings.enabled_phases = [
            int(p.strip()) for p in args.phases.split(",")
        ]

    agent = EnvelopeEstimatorAgent(settings)

    # Parse trade codes
    trade_codes = None
    if args.trades:
        trade_codes = [c.strip().upper() for c in args.trades.split(",")]

    if args.monitor:
        agent.monitor()
    elif args.pdf:
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
        agent.process_plans(
            pdf_paths=[str(p) for p in pdfs],
            project_name=args.name or folder.name,
            trade_codes=trade_codes,
        )
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python agent.py --pdf plans.pdf")
        print("  python agent.py --pdf sheet1.pdf sheet2.pdf --trades SID,ROF")
        print("  python agent.py --folder ./my_project_plans/")
        print("  python agent.py --monitor")
        print("  python agent.py --pdf plans.pdf --phases 1,2")


if __name__ == "__main__":
    main()
