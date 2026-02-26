"""
AI Learning Engine — Continuous Improvement for Construction Estimating

This module makes the Envelope Estimator Agent smarter with every project.
It learns from:

1. ESTIMATE FEEDBACK LOOPS
   - Tracks predicted vs actual costs when actuals are reported back
   - Identifies systematic over/under-estimation by trade, material, region
   - Auto-calibrates pricing multipliers per trade and region

2. PATTERN RECOGNITION
   - Clusters similar projects (by type, size, region, vintage)
   - Surfaces "projects like this typically cost X" benchmarks
   - Detects material/labor cost drift over time (inflation tracking)

3. PHOTO ANALYSIS LEARNING
   - Tracks AI damage detection accuracy vs adjuster findings
   - Builds a library of confirmed damage patterns by type
   - Improves measurement estimation accuracy over time

4. REGIONAL INTELLIGENCE
   - Learns pricing differences across markets
   - Tracks permit/code requirement variations
   - Monitors material availability and lead times

5. QUALITY SCORING
   - Rates every estimate on completeness, accuracy, client satisfaction
   - Identifies which project types have highest/lowest accuracy
   - Flags estimates that need human review based on confidence patterns

Architecture:
- All learning data stored as JSON files (swappable to Postgres/Supabase)
- Lightweight — no heavy ML framework needed, uses Claude for reasoning
- Every workflow (1-4) feeds into the learning engine automatically
"""

import json
import logging
import math
import statistics
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

class FeedbackType(str, Enum):
    ACTUAL_COST = "actual_cost"         # Real project cost reported back
    CLIENT_RATING = "client_rating"     # Customer satisfaction (1-5)
    ADJUSTER_REVIEW = "adjuster_review" # Insurance adjuster corrections
    FIELD_CORRECTION = "field_correction"  # Field crew found different conditions
    SCOPE_CHANGE = "scope_change"       # Scope changed after estimate
    WON_LOST = "won_lost"              # Did we win or lose the bid?
    PHOTO_ACCURACY = "photo_accuracy"   # How accurate was photo analysis?


class ProjectCluster(str, Enum):
    SMALL_RESIDENTIAL_ROOF = "small_res_roof"       # < 2000 SF
    MEDIUM_RESIDENTIAL_ROOF = "med_res_roof"        # 2000-3500 SF
    LARGE_RESIDENTIAL_ROOF = "large_res_roof"       # > 3500 SF
    RESIDENTIAL_SIDING = "res_siding"
    RESIDENTIAL_FULL_EXTERIOR = "res_full_ext"
    SMALL_COMMERCIAL = "small_commercial"           # < 10,000 SF
    MEDIUM_COMMERCIAL = "med_commercial"            # 10-50K SF
    LARGE_COMMERCIAL = "large_commercial"           # > 50K SF
    INSURANCE_CLAIM_MINOR = "ins_minor"             # < $10K
    INSURANCE_CLAIM_MODERATE = "ins_moderate"        # $10-50K
    INSURANCE_CLAIM_MAJOR = "ins_major"             # > $50K


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EstimateRecord:
    """A completed estimate stored in the learning database."""
    estimate_id: str
    workflow: str              # "commercial", "roof_report", "loss_report", "self_service"
    project_type: str
    region: str
    city: str = ""
    state: str = ""
    postal_code: str = ""

    # Dimensions
    total_sf: float = 0.0
    roof_sf: float = 0.0
    wall_sf: float = 0.0
    stories: int = 1
    roof_pitch: str = ""
    year_built: str = ""
    building_type: str = ""

    # Cost breakdown
    estimated_materials: float = 0.0
    estimated_labor: float = 0.0
    estimated_total: float = 0.0
    cost_per_sf: float = 0.0
    overhead_pct: float = 0.0
    profit_pct: float = 0.0

    # Trade-level costs (code → amount)
    trade_costs: dict = field(default_factory=dict)

    # Line item count and breakdown
    line_item_count: int = 0
    category_breakdown: dict = field(default_factory=dict)  # category → total

    # Schedule
    estimated_days: int = 0
    estimated_labor_hours: float = 0.0

    # Quality
    confidence_score: float = 0.0
    data_source: str = ""      # "pdf_plans", "satellite", "photos", "self_service_scan"
    photo_count: int = 0

    # Timestamps
    created_at: str = ""
    cluster: str = ""


@dataclass
class FeedbackRecord:
    """Feedback on a completed estimate."""
    feedback_id: str
    estimate_id: str
    feedback_type: FeedbackType
    submitted_at: str = ""
    submitted_by: str = ""     # "customer", "adjuster", "field_crew", "salesman"

    # Actual vs estimated
    actual_total: float = 0.0
    actual_materials: float = 0.0
    actual_labor: float = 0.0
    actual_days: int = 0
    variance_percent: float = 0.0   # (actual - estimated) / estimated

    # Trade-level actuals
    actual_trade_costs: dict = field(default_factory=dict)

    # Qualitative
    client_rating: int = 0         # 1-5
    won_bid: Optional[bool] = None
    lost_reason: str = ""          # "price_too_high", "competitor", "scope", "timing"
    adjuster_corrections: list = field(default_factory=list)
    field_notes: str = ""

    # Photo accuracy
    photo_accuracy_score: float = 0.0  # 0-1
    missed_items: list = field(default_factory=list)
    extra_items: list = field(default_factory=list)


@dataclass
class CalibrationFactor:
    """A learned pricing calibration for a specific dimension."""
    dimension: str         # "trade:RFG", "region:CO", "cluster:small_res_roof"
    factor: float          # multiplier (1.0 = no adjustment, 1.05 = 5% over)
    sample_size: int = 0
    avg_variance: float = 0.0
    last_updated: str = ""
    confidence: float = 0.0


@dataclass
class PricingTrend:
    """Tracked pricing trend over time."""
    dimension: str          # "materials:shingles:architectural", "labor:roofing:CO"
    data_points: list = field(default_factory=list)  # [{date, value}]
    trend_direction: str = ""    # "rising", "falling", "stable"
    monthly_change_pct: float = 0.0
    last_updated: str = ""


@dataclass
class ProjectBenchmark:
    """Benchmark data for a project cluster."""
    cluster: str
    sample_size: int = 0
    avg_cost_per_sf: float = 0.0
    median_cost_per_sf: float = 0.0
    p25_cost_per_sf: float = 0.0    # 25th percentile
    p75_cost_per_sf: float = 0.0    # 75th percentile
    avg_total: float = 0.0
    avg_days: int = 0
    avg_labor_hours: float = 0.0
    win_rate: float = 0.0           # bid win rate for this cluster
    avg_confidence: float = 0.0
    last_updated: str = ""


@dataclass
class LearningInsight:
    """An AI-generated insight from the learning data."""
    insight_id: str
    category: str          # "pricing", "accuracy", "market", "operations"
    severity: str          # "info", "warning", "action_required"
    title: str
    description: str
    recommendation: str
    data_basis: str        # what data this was derived from
    generated_at: str = ""
    acknowledged: bool = False


@dataclass
class LearningDashboard:
    """Summary dashboard of the learning engine state."""
    total_estimates: int = 0
    total_feedback_records: int = 0
    avg_accuracy: float = 0.0        # average (1 - abs(variance))
    win_rate: float = 0.0
    avg_client_rating: float = 0.0
    top_calibration_factors: list = field(default_factory=list)
    pricing_trends: list = field(default_factory=list)
    recent_insights: list = field(default_factory=list)
    cluster_benchmarks: list = field(default_factory=list)
    last_analysis_at: str = ""


# ---------------------------------------------------------------------------
# Main learning engine
# ---------------------------------------------------------------------------

class AILearningEngine:
    """Continuous learning engine that improves estimates over time."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic.api_key)

        # Storage directories
        self.data_dir = Path(settings.output_dir) / "learning_engine"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "estimates").mkdir(exist_ok=True)
        (self.data_dir / "feedback").mkdir(exist_ok=True)
        (self.data_dir / "calibration").mkdir(exist_ok=True)
        (self.data_dir / "trends").mkdir(exist_ok=True)
        (self.data_dir / "benchmarks").mkdir(exist_ok=True)
        (self.data_dir / "insights").mkdir(exist_ok=True)

    # ==================================================================
    # 1. RECORD ESTIMATES (every workflow feeds into this)
    # ==================================================================

    def record_estimate(
        self,
        estimate_id: str,
        workflow: str,
        project_type: str,
        total_sf: float = 0.0,
        roof_sf: float = 0.0,
        wall_sf: float = 0.0,
        stories: int = 1,
        roof_pitch: str = "",
        estimated_materials: float = 0.0,
        estimated_labor: float = 0.0,
        estimated_total: float = 0.0,
        trade_costs: dict | None = None,
        line_item_count: int = 0,
        category_breakdown: dict | None = None,
        estimated_days: int = 0,
        estimated_labor_hours: float = 0.0,
        confidence_score: float = 0.0,
        data_source: str = "",
        photo_count: int = 0,
        city: str = "",
        state: str = "",
        postal_code: str = "",
    ) -> EstimateRecord:
        """Record a completed estimate for learning purposes.

        Called automatically at the end of every estimation workflow.
        """
        record = EstimateRecord(
            estimate_id=estimate_id,
            workflow=workflow,
            project_type=project_type,
            region=self.settings.region,
            city=city,
            state=state,
            postal_code=postal_code,
            total_sf=total_sf,
            roof_sf=roof_sf,
            wall_sf=wall_sf,
            stories=stories,
            roof_pitch=roof_pitch,
            estimated_materials=estimated_materials,
            estimated_labor=estimated_labor,
            estimated_total=estimated_total,
            cost_per_sf=round(estimated_total / total_sf, 2) if total_sf > 0 else 0,
            overhead_pct=self.settings.company.overhead_percent,
            profit_pct=self.settings.company.profit_percent,
            trade_costs=trade_costs or {},
            line_item_count=line_item_count,
            category_breakdown=category_breakdown or {},
            estimated_days=estimated_days,
            estimated_labor_hours=estimated_labor_hours,
            confidence_score=confidence_score,
            data_source=data_source,
            photo_count=photo_count,
            created_at=datetime.now().isoformat(),
            cluster=self._classify_cluster(project_type, total_sf, estimated_total),
        )

        self._save_estimate_record(record)
        logger.info(f"Recorded estimate {estimate_id} ({workflow}) — ${estimated_total:,.2f}")

        # Check if we have enough data to trigger recalibration
        self._check_recalibration_trigger()

        return record

    # ==================================================================
    # 2. RECORD FEEDBACK (actual costs, ratings, win/loss, corrections)
    # ==================================================================

    def record_feedback(
        self,
        estimate_id: str,
        feedback_type: FeedbackType,
        actual_total: float = 0.0,
        actual_materials: float = 0.0,
        actual_labor: float = 0.0,
        actual_days: int = 0,
        actual_trade_costs: dict | None = None,
        client_rating: int = 0,
        won_bid: bool | None = None,
        lost_reason: str = "",
        adjuster_corrections: list | None = None,
        field_notes: str = "",
        photo_accuracy_score: float = 0.0,
        missed_items: list | None = None,
        extra_items: list | None = None,
        submitted_by: str = "",
    ) -> FeedbackRecord:
        """Record feedback on a completed estimate.

        This is the core input that drives learning. Every time actuals come
        back, adjusters make corrections, or we win/lose a bid — record it.
        """
        # Load the original estimate to compute variance
        estimate = self._load_estimate_record(estimate_id)
        variance = 0.0
        if estimate and estimate.estimated_total > 0 and actual_total > 0:
            variance = (actual_total - estimate.estimated_total) / estimate.estimated_total

        feedback_id = f"FB-{datetime.now().strftime('%Y%m%d%H%M%S')}-{estimate_id[-6:]}"

        record = FeedbackRecord(
            feedback_id=feedback_id,
            estimate_id=estimate_id,
            feedback_type=feedback_type,
            submitted_at=datetime.now().isoformat(),
            submitted_by=submitted_by,
            actual_total=actual_total,
            actual_materials=actual_materials,
            actual_labor=actual_labor,
            actual_days=actual_days,
            variance_percent=round(variance * 100, 2),
            actual_trade_costs=actual_trade_costs or {},
            client_rating=client_rating,
            won_bid=won_bid,
            lost_reason=lost_reason,
            adjuster_corrections=adjuster_corrections or [],
            field_notes=field_notes,
            photo_accuracy_score=photo_accuracy_score,
            missed_items=missed_items or [],
            extra_items=extra_items or [],
        )

        self._save_feedback_record(record)
        logger.info(
            f"Recorded feedback {feedback_id} for {estimate_id} "
            f"(type={feedback_type.value}, variance={variance:+.1%})"
        )

        # Immediately update calibration factors if this is cost feedback
        if feedback_type in (FeedbackType.ACTUAL_COST, FeedbackType.ADJUSTER_REVIEW):
            self._update_calibration_from_feedback(estimate, record)

        return record

    # ==================================================================
    # 3. CALIBRATION — Auto-adjust pricing factors
    # ==================================================================

    def get_calibration_factor(self, dimension: str) -> float:
        """Get the current calibration factor for a dimension.

        Examples:
            get_calibration_factor("trade:RFG")       → 1.03 (roofing 3% under)
            get_calibration_factor("region:CO")        → 0.98 (Colorado 2% over)
            get_calibration_factor("cluster:small_res_roof") → 1.05
        """
        path = self.data_dir / "calibration" / f"{dimension.replace(':', '_')}.json"
        if not path.exists():
            return 1.0

        data = json.loads(path.read_text())
        factor = data.get("factor", 1.0)

        # Don't apply factors with low confidence (< 3 samples)
        if data.get("sample_size", 0) < 3:
            return 1.0

        return factor

    def get_all_calibration_factors(self) -> list[CalibrationFactor]:
        """Get all current calibration factors."""
        factors = []
        cal_dir = self.data_dir / "calibration"
        for path in sorted(cal_dir.glob("*.json")):
            data = json.loads(path.read_text())
            factors.append(CalibrationFactor(
                dimension=data["dimension"],
                factor=data["factor"],
                sample_size=data.get("sample_size", 0),
                avg_variance=data.get("avg_variance", 0),
                last_updated=data.get("last_updated", ""),
                confidence=data.get("confidence", 0),
            ))
        return factors

    def apply_calibration(
        self,
        base_estimate: float,
        project_type: str = "",
        trade_code: str = "",
        state: str = "",
        cluster: str = "",
    ) -> tuple[float, list[str]]:
        """Apply all relevant calibration factors to a base estimate.

        Returns (calibrated_amount, [list of adjustments applied]).
        """
        adjustments = []
        total_factor = 1.0

        # Trade-level calibration
        if trade_code:
            factor = self.get_calibration_factor(f"trade:{trade_code}")
            if factor != 1.0:
                total_factor *= factor
                adjustments.append(
                    f"Trade {trade_code}: {factor:.3f} ({(factor-1)*100:+.1f}%)"
                )

        # Regional calibration
        if state:
            factor = self.get_calibration_factor(f"region:{state}")
            if factor != 1.0:
                total_factor *= factor
                adjustments.append(
                    f"Region {state}: {factor:.3f} ({(factor-1)*100:+.1f}%)"
                )

        # Cluster calibration
        if cluster:
            factor = self.get_calibration_factor(f"cluster:{cluster}")
            if factor != 1.0:
                total_factor *= factor
                adjustments.append(
                    f"Cluster {cluster}: {factor:.3f} ({(factor-1)*100:+.1f}%)"
                )

        calibrated = round(base_estimate * total_factor, 2)

        if adjustments:
            logger.info(
                f"Calibration applied: ${base_estimate:,.2f} → ${calibrated:,.2f} "
                f"(factor: {total_factor:.4f})"
            )

        return calibrated, adjustments

    def _update_calibration_from_feedback(
        self,
        estimate: Optional[EstimateRecord],
        feedback: FeedbackRecord,
    ):
        """Update calibration factors based on new feedback."""
        if not estimate or feedback.actual_total <= 0:
            return

        variance = feedback.variance_percent / 100.0  # as decimal

        # Update trade-level calibrations from trade cost breakdowns
        if feedback.actual_trade_costs and estimate.trade_costs:
            for trade_code, actual_cost in feedback.actual_trade_costs.items():
                estimated_cost = estimate.trade_costs.get(trade_code, 0)
                if estimated_cost > 0:
                    trade_variance = (actual_cost - estimated_cost) / estimated_cost
                    self._update_single_calibration(
                        f"trade:{trade_code}", trade_variance
                    )

        # Update overall project-level calibration
        self._update_single_calibration(f"overall:{estimate.workflow}", variance)

        # Update regional calibration
        if estimate.state:
            self._update_single_calibration(f"region:{estimate.state}", variance)

        # Update cluster calibration
        if estimate.cluster:
            self._update_single_calibration(f"cluster:{estimate.cluster}", variance)

    def _update_single_calibration(self, dimension: str, variance: float):
        """Update a single calibration factor with a new variance data point.

        Uses exponential moving average (EMA) with alpha=0.3 to weight
        recent feedback more heavily while maintaining stability.
        """
        safe_name = dimension.replace(":", "_")
        path = self.data_dir / "calibration" / f"{safe_name}.json"

        if path.exists():
            data = json.loads(path.read_text())
            old_factor = data.get("factor", 1.0)
            old_samples = data.get("sample_size", 0)
            old_avg_var = data.get("avg_variance", 0)

            # EMA with alpha=0.3
            alpha = 0.3
            new_avg_var = alpha * variance + (1 - alpha) * old_avg_var

            # Calibration factor: if we're consistently under by 5%, factor = 1.05
            # Dampen the correction to avoid overreaction
            correction = new_avg_var * 0.5  # apply 50% of the observed variance
            new_factor = 1.0 + correction

            # Clamp to reasonable bounds (0.80 to 1.20 — max 20% adjustment)
            new_factor = max(0.80, min(1.20, new_factor))

            data = {
                "dimension": dimension,
                "factor": round(new_factor, 4),
                "sample_size": old_samples + 1,
                "avg_variance": round(new_avg_var, 4),
                "last_updated": datetime.now().isoformat(),
                "confidence": min(1.0, (old_samples + 1) / 20),  # full confidence at 20 samples
                "history": data.get("history", []) + [{
                    "date": datetime.now().isoformat(),
                    "variance": round(variance, 4),
                    "factor_after": round(new_factor, 4),
                }],
            }
        else:
            # First data point — don't adjust yet, just record
            data = {
                "dimension": dimension,
                "factor": 1.0,
                "sample_size": 1,
                "avg_variance": round(variance, 4),
                "last_updated": datetime.now().isoformat(),
                "confidence": 0.05,
                "history": [{
                    "date": datetime.now().isoformat(),
                    "variance": round(variance, 4),
                    "factor_after": 1.0,
                }],
            }

        path.write_text(json.dumps(data, indent=2))
        logger.debug(f"Updated calibration {dimension}: factor={data['factor']}")

    # ==================================================================
    # 4. BENCHMARKS — "Projects like this typically cost X"
    # ==================================================================

    def get_benchmark(self, cluster: str) -> Optional[ProjectBenchmark]:
        """Get benchmark data for a project cluster."""
        path = self.data_dir / "benchmarks" / f"{cluster}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text())
        return ProjectBenchmark(**data)

    def get_comparable_estimates(
        self,
        project_type: str,
        total_sf: float,
        state: str = "",
        max_results: int = 5,
    ) -> list[dict]:
        """Find comparable past estimates for a new project.

        Returns similar past estimates ranked by similarity.
        """
        estimates_dir = self.data_dir / "estimates"
        candidates = []

        for path in estimates_dir.glob("*.json"):
            data = json.loads(path.read_text())

            # Skip if different project type
            if data.get("project_type") != project_type:
                continue

            # Compute similarity score
            sf_diff = abs(data.get("total_sf", 0) - total_sf) / max(total_sf, 1)
            sf_score = max(0, 1.0 - sf_diff)  # closer SF = higher score

            region_score = 1.0 if data.get("state") == state else 0.5
            stories_score = 1.0  # could compare stories too

            similarity = (sf_score * 0.5) + (region_score * 0.3) + (stories_score * 0.2)

            candidates.append({
                "estimate_id": data["estimate_id"],
                "total_sf": data.get("total_sf", 0),
                "estimated_total": data.get("estimated_total", 0),
                "cost_per_sf": data.get("cost_per_sf", 0),
                "state": data.get("state", ""),
                "cluster": data.get("cluster", ""),
                "confidence": data.get("confidence_score", 0),
                "similarity": round(similarity, 3),
                "created_at": data.get("created_at", ""),
            })

        # Sort by similarity descending
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[:max_results]

    def rebuild_benchmarks(self):
        """Rebuild all benchmark data from recorded estimates and feedback.

        Should be run periodically (e.g., nightly) or after bulk feedback import.
        """
        estimates_dir = self.data_dir / "estimates"
        feedback_dir = self.data_dir / "feedback"

        # Group estimates by cluster
        clusters: dict[str, list] = {}
        for path in estimates_dir.glob("*.json"):
            data = json.loads(path.read_text())
            cluster = data.get("cluster", "unknown")
            if cluster not in clusters:
                clusters[cluster] = []
            clusters[cluster].append(data)

        # Load all feedback for win/loss and rating data
        feedback_by_estimate: dict[str, list] = {}
        for path in feedback_dir.glob("*.json"):
            fb = json.loads(path.read_text())
            eid = fb.get("estimate_id", "")
            if eid not in feedback_by_estimate:
                feedback_by_estimate[eid] = []
            feedback_by_estimate[eid].append(fb)

        # Compute benchmarks per cluster
        for cluster, estimates in clusters.items():
            cost_per_sf_values = [e["cost_per_sf"] for e in estimates if e.get("cost_per_sf", 0) > 0]
            totals = [e["estimated_total"] for e in estimates if e.get("estimated_total", 0) > 0]
            days = [e["estimated_days"] for e in estimates if e.get("estimated_days", 0) > 0]
            hours = [e["estimated_labor_hours"] for e in estimates if e.get("estimated_labor_hours", 0) > 0]
            confs = [e["confidence_score"] for e in estimates if e.get("confidence_score", 0) > 0]

            # Win rate from feedback
            wins = 0
            total_bids = 0
            ratings = []
            for est in estimates:
                for fb in feedback_by_estimate.get(est["estimate_id"], []):
                    if fb.get("won_bid") is not None:
                        total_bids += 1
                        if fb["won_bid"]:
                            wins += 1
                    if fb.get("client_rating", 0) > 0:
                        ratings.append(fb["client_rating"])

            benchmark = {
                "cluster": cluster,
                "sample_size": len(estimates),
                "avg_cost_per_sf": round(statistics.mean(cost_per_sf_values), 2) if cost_per_sf_values else 0,
                "median_cost_per_sf": round(statistics.median(cost_per_sf_values), 2) if cost_per_sf_values else 0,
                "p25_cost_per_sf": round(_percentile(cost_per_sf_values, 25), 2) if len(cost_per_sf_values) >= 4 else 0,
                "p75_cost_per_sf": round(_percentile(cost_per_sf_values, 75), 2) if len(cost_per_sf_values) >= 4 else 0,
                "avg_total": round(statistics.mean(totals), 2) if totals else 0,
                "avg_days": round(statistics.mean(days)) if days else 0,
                "avg_labor_hours": round(statistics.mean(hours), 1) if hours else 0,
                "win_rate": round(wins / total_bids, 2) if total_bids > 0 else 0,
                "avg_confidence": round(statistics.mean(confs), 2) if confs else 0,
                "last_updated": datetime.now().isoformat(),
            }

            bench_path = self.data_dir / "benchmarks" / f"{cluster}.json"
            bench_path.write_text(json.dumps(benchmark, indent=2))

        logger.info(f"Rebuilt benchmarks for {len(clusters)} clusters")

    # ==================================================================
    # 5. PRICING TRENDS — Track cost drift over time
    # ==================================================================

    def record_pricing_datapoint(
        self,
        dimension: str,
        value: float,
        date: str = "",
    ):
        """Record a pricing data point for trend tracking.

        Examples:
            record_pricing_datapoint("materials:shingles:architectural", 95.50)
            record_pricing_datapoint("labor:roofing:CO", 75.00)
        """
        safe_name = dimension.replace(":", "_").replace("/", "_")
        path = self.data_dir / "trends" / f"{safe_name}.json"

        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = {"dimension": dimension, "data_points": []}

        data["data_points"].append({
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "value": value,
        })

        # Keep only last 365 data points
        data["data_points"] = data["data_points"][-365:]

        # Compute trend
        if len(data["data_points"]) >= 3:
            recent = [dp["value"] for dp in data["data_points"][-30:]]
            older = [dp["value"] for dp in data["data_points"][-60:-30]] if len(data["data_points"]) >= 60 else []

            if recent and older:
                recent_avg = statistics.mean(recent)
                older_avg = statistics.mean(older)
                change = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
                data["trend_direction"] = "rising" if change > 0.02 else "falling" if change < -0.02 else "stable"
                data["monthly_change_pct"] = round(change * 100, 2)
            else:
                data["trend_direction"] = "insufficient_data"
                data["monthly_change_pct"] = 0

        data["last_updated"] = datetime.now().isoformat()
        path.write_text(json.dumps(data, indent=2))

    def get_pricing_trends(self) -> list[PricingTrend]:
        """Get all tracked pricing trends."""
        trends = []
        for path in sorted((self.data_dir / "trends").glob("*.json")):
            data = json.loads(path.read_text())
            trends.append(PricingTrend(
                dimension=data["dimension"],
                data_points=data.get("data_points", []),
                trend_direction=data.get("trend_direction", "unknown"),
                monthly_change_pct=data.get("monthly_change_pct", 0),
                last_updated=data.get("last_updated", ""),
            ))
        return trends

    # ==================================================================
    # 6. AI-POWERED INSIGHTS — Periodic analysis of all learning data
    # ==================================================================

    def generate_insights(self, force: bool = False) -> list[LearningInsight]:
        """Use Claude to analyze all learning data and generate actionable insights.

        Called periodically or on-demand. Analyzes:
        - Accuracy patterns
        - Pricing trends
        - Win/loss patterns
        - Regional differences
        - Data quality issues
        """
        # Check if we have enough data
        estimates = list((self.data_dir / "estimates").glob("*.json"))
        feedback = list((self.data_dir / "feedback").glob("*.json"))

        if len(estimates) < 5 and not force:
            logger.info("Not enough data for insights (need 5+ estimates)")
            return []

        # Gather summary data for Claude
        summary = self._build_insights_summary()

        prompt = f"""You are a construction estimating analytics advisor. Analyze this performance data
from an AI estimating platform and generate actionable insights.

PLATFORM DATA SUMMARY:
{json.dumps(summary, indent=2)}

Generate 3-5 insights as a JSON array. Each insight should be:

[
    {{
        "category": "pricing | accuracy | market | operations",
        "severity": "info | warning | action_required",
        "title": "<concise title>",
        "description": "<what the data shows>",
        "recommendation": "<specific action to take>",
        "data_basis": "<what data supports this insight>"
    }}
]

Focus on insights that would help a construction company:
- Win more bids at better margins
- Improve estimate accuracy
- Spot market changes early
- Optimize operations and crew scheduling"""

        response = self.client.messages.create(
            model=self.settings.anthropic.model_fast,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse insights
        response_text = response.content[0].text
        json_match = _extract_json(response_text)
        insights = []

        if json_match:
            insight_data = json.loads(json_match)
            for i, item in enumerate(insight_data):
                insight = LearningInsight(
                    insight_id=f"INS-{datetime.now().strftime('%Y%m%d')}-{i+1:03d}",
                    category=item.get("category", "general"),
                    severity=item.get("severity", "info"),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    recommendation=item.get("recommendation", ""),
                    data_basis=item.get("data_basis", ""),
                    generated_at=datetime.now().isoformat(),
                )
                insights.append(insight)

                # Save insight
                path = self.data_dir / "insights" / f"{insight.insight_id}.json"
                path.write_text(json.dumps({
                    "insight_id": insight.insight_id,
                    "category": insight.category,
                    "severity": insight.severity,
                    "title": insight.title,
                    "description": insight.description,
                    "recommendation": insight.recommendation,
                    "data_basis": insight.data_basis,
                    "generated_at": insight.generated_at,
                }, indent=2))

        logger.info(f"Generated {len(insights)} learning insights")
        return insights

    def _build_insights_summary(self) -> dict:
        """Build a summary of all learning data for AI analysis."""
        summary = {
            "estimates": {"total": 0, "by_workflow": {}, "by_cluster": {}},
            "feedback": {"total": 0, "avg_variance": 0, "win_rate": 0, "avg_rating": 0},
            "calibration_factors": [],
            "pricing_trends": [],
        }

        # Summarize estimates
        variances = []
        wins = 0
        total_bids = 0
        ratings = []

        for path in (self.data_dir / "estimates").glob("*.json"):
            data = json.loads(path.read_text())
            summary["estimates"]["total"] += 1
            wf = data.get("workflow", "unknown")
            summary["estimates"]["by_workflow"][wf] = summary["estimates"]["by_workflow"].get(wf, 0) + 1
            cl = data.get("cluster", "unknown")
            summary["estimates"]["by_cluster"][cl] = summary["estimates"]["by_cluster"].get(cl, 0) + 1

        # Summarize feedback
        for path in (self.data_dir / "feedback").glob("*.json"):
            data = json.loads(path.read_text())
            summary["feedback"]["total"] += 1
            if data.get("variance_percent"):
                variances.append(data["variance_percent"])
            if data.get("won_bid") is not None:
                total_bids += 1
                if data["won_bid"]:
                    wins += 1
            if data.get("client_rating", 0) > 0:
                ratings.append(data["client_rating"])

        if variances:
            summary["feedback"]["avg_variance"] = round(statistics.mean(variances), 2)
            summary["feedback"]["median_variance"] = round(statistics.median(variances), 2)
        if total_bids:
            summary["feedback"]["win_rate"] = round(wins / total_bids * 100, 1)
        if ratings:
            summary["feedback"]["avg_rating"] = round(statistics.mean(ratings), 2)

        # Top calibration factors
        for factor in self.get_all_calibration_factors():
            if factor.sample_size >= 2:
                summary["calibration_factors"].append({
                    "dimension": factor.dimension,
                    "factor": factor.factor,
                    "samples": factor.sample_size,
                    "avg_variance": factor.avg_variance,
                })

        # Pricing trends
        for trend in self.get_pricing_trends():
            if trend.trend_direction != "insufficient_data":
                summary["pricing_trends"].append({
                    "dimension": trend.dimension,
                    "direction": trend.trend_direction,
                    "monthly_change": trend.monthly_change_pct,
                })

        return summary

    # ==================================================================
    # 7. DASHBOARD — Overall learning engine health
    # ==================================================================

    def get_dashboard(self) -> LearningDashboard:
        """Get the current learning engine dashboard."""
        dashboard = LearningDashboard()

        # Count estimates
        dashboard.total_estimates = len(list((self.data_dir / "estimates").glob("*.json")))

        # Count and analyze feedback
        variances = []
        wins = 0
        total_bids = 0
        ratings = []

        for path in (self.data_dir / "feedback").glob("*.json"):
            dashboard.total_feedback_records += 1
            data = json.loads(path.read_text())
            if data.get("variance_percent"):
                variances.append(abs(data["variance_percent"]))
            if data.get("won_bid") is not None:
                total_bids += 1
                if data["won_bid"]:
                    wins += 1
            if data.get("client_rating", 0) > 0:
                ratings.append(data["client_rating"])

        # Accuracy: 100% - avg absolute variance
        if variances:
            dashboard.avg_accuracy = round(100 - statistics.mean(variances), 1)
        if total_bids:
            dashboard.win_rate = round(wins / total_bids * 100, 1)
        if ratings:
            dashboard.avg_client_rating = round(statistics.mean(ratings), 2)

        # Top calibration factors (furthest from 1.0)
        all_factors = self.get_all_calibration_factors()
        all_factors.sort(key=lambda f: abs(f.factor - 1.0), reverse=True)
        dashboard.top_calibration_factors = [
            {"dimension": f.dimension, "factor": f.factor, "samples": f.sample_size}
            for f in all_factors[:5]
        ]

        # Recent insights
        insight_files = sorted(
            (self.data_dir / "insights").glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in insight_files[:5]:
            data = json.loads(path.read_text())
            dashboard.recent_insights.append({
                "title": data.get("title", ""),
                "severity": data.get("severity", ""),
                "category": data.get("category", ""),
            })

        dashboard.last_analysis_at = datetime.now().isoformat()
        return dashboard

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify_cluster(
        self,
        project_type: str,
        total_sf: float,
        estimated_total: float,
    ) -> str:
        """Classify a project into a benchmark cluster."""
        pt = project_type.lower()

        if "roof" in pt:
            if total_sf < 2000:
                return ProjectCluster.SMALL_RESIDENTIAL_ROOF.value
            elif total_sf < 3500:
                return ProjectCluster.MEDIUM_RESIDENTIAL_ROOF.value
            else:
                return ProjectCluster.LARGE_RESIDENTIAL_ROOF.value
        elif "siding" in pt:
            return ProjectCluster.RESIDENTIAL_SIDING.value
        elif "full_exterior" in pt or "exterior" in pt:
            return ProjectCluster.RESIDENTIAL_FULL_EXTERIOR.value
        elif "commercial" in pt:
            if total_sf < 10000:
                return ProjectCluster.SMALL_COMMERCIAL.value
            elif total_sf < 50000:
                return ProjectCluster.MEDIUM_COMMERCIAL.value
            else:
                return ProjectCluster.LARGE_COMMERCIAL.value
        elif "insurance" in pt or "claim" in pt or "loss" in pt:
            if estimated_total < 10000:
                return ProjectCluster.INSURANCE_CLAIM_MINOR.value
            elif estimated_total < 50000:
                return ProjectCluster.INSURANCE_CLAIM_MODERATE.value
            else:
                return ProjectCluster.INSURANCE_CLAIM_MAJOR.value

        return "uncategorized"

    def _check_recalibration_trigger(self):
        """Check if we should trigger a full recalibration.

        Triggers when we hit milestones: every 10 estimates, or every 5 feedback records.
        """
        est_count = len(list((self.data_dir / "estimates").glob("*.json")))
        fb_count = len(list((self.data_dir / "feedback").glob("*.json")))

        if est_count > 0 and est_count % 10 == 0:
            logger.info(f"Recalibration trigger: {est_count} estimates reached")
            self.rebuild_benchmarks()

        if fb_count > 0 and fb_count % 5 == 0:
            logger.info(f"Insight trigger: {fb_count} feedback records reached")
            self.generate_insights()

    def _save_estimate_record(self, record: EstimateRecord):
        path = self.data_dir / "estimates" / f"{record.estimate_id}.json"
        path.write_text(json.dumps({
            "estimate_id": record.estimate_id,
            "workflow": record.workflow,
            "project_type": record.project_type,
            "region": record.region,
            "city": record.city,
            "state": record.state,
            "postal_code": record.postal_code,
            "total_sf": record.total_sf,
            "roof_sf": record.roof_sf,
            "wall_sf": record.wall_sf,
            "stories": record.stories,
            "roof_pitch": record.roof_pitch,
            "estimated_materials": record.estimated_materials,
            "estimated_labor": record.estimated_labor,
            "estimated_total": record.estimated_total,
            "cost_per_sf": record.cost_per_sf,
            "overhead_pct": record.overhead_pct,
            "profit_pct": record.profit_pct,
            "trade_costs": record.trade_costs,
            "line_item_count": record.line_item_count,
            "category_breakdown": record.category_breakdown,
            "estimated_days": record.estimated_days,
            "estimated_labor_hours": record.estimated_labor_hours,
            "confidence_score": record.confidence_score,
            "data_source": record.data_source,
            "photo_count": record.photo_count,
            "created_at": record.created_at,
            "cluster": record.cluster,
        }, indent=2))

    def _load_estimate_record(self, estimate_id: str) -> Optional[EstimateRecord]:
        path = self.data_dir / "estimates" / f"{estimate_id}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text())
        return EstimateRecord(**{k: v for k, v in data.items() if k != "year_built" and k != "building_type" or k in ("year_built", "building_type")})

    def _save_feedback_record(self, record: FeedbackRecord):
        path = self.data_dir / "feedback" / f"{record.feedback_id}.json"
        path.write_text(json.dumps({
            "feedback_id": record.feedback_id,
            "estimate_id": record.estimate_id,
            "feedback_type": record.feedback_type.value,
            "submitted_at": record.submitted_at,
            "submitted_by": record.submitted_by,
            "actual_total": record.actual_total,
            "actual_materials": record.actual_materials,
            "actual_labor": record.actual_labor,
            "actual_days": record.actual_days,
            "variance_percent": record.variance_percent,
            "actual_trade_costs": record.actual_trade_costs,
            "client_rating": record.client_rating,
            "won_bid": record.won_bid,
            "lost_reason": record.lost_reason,
            "adjuster_corrections": record.adjuster_corrections,
            "field_notes": record.field_notes,
            "photo_accuracy_score": record.photo_accuracy_score,
            "missed_items": record.missed_items,
            "extra_items": record.extra_items,
        }, indent=2))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _percentile(data: list, percentile: float) -> float:
    """Calculate percentile from a sorted list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[int(f)] * (c - k) + sorted_data[int(c)] * (k - f)


def _extract_json(text: str) -> Optional[str]:
    """Extract JSON from a Claude response."""
    import re
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        return bracket_match.group(0)
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)
    return None
