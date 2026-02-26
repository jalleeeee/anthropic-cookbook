"""
Bid Dashboard — Centralized project & bid tracking.

Clones BEAM AI's bid management functionality:
- Track bid status, owners, due dates, trade scope
- RFI and addenda tracking per project
- Priority levels and win/loss tracking
- Team assignment and workload visibility

Our advantage over BEAM AI:
  BEAM tracks bids but doesn't price them.
  We track bids AND produce priced estimates in one platform.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BidStatus(Enum):
    RECEIVED = "received"           # ITB received, not started
    IN_REVIEW = "in_review"         # Plans being reviewed
    TAKEOFF_IN_PROGRESS = "takeoff_in_progress"
    TAKEOFF_COMPLETE = "takeoff_complete"
    PRICING = "pricing"             # Adding costs
    ESTIMATE_COMPLETE = "estimate_complete"
    PROPOSAL_SENT = "proposal_sent"
    WON = "won"
    LOST = "lost"
    NO_BID = "no_bid"
    WITHDRAWN = "withdrawn"


class BidPriority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TradeScope(Enum):
    SIDING = "siding"
    ROOFING = "roofing"
    GUTTERS = "gutters"
    WINDOWS = "windows"
    DOORS = "doors"
    COPING = "coping"
    RAILING = "railing"
    WATERPROOFING = "waterproofing"
    INSULATION = "insulation"
    PAINTING = "painting"
    FRAMING = "framing"
    DRYWALL = "drywall"
    FULL_ENVELOPE = "full_envelope"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RFI:
    """Request for Information on a bid."""
    rfi_id: str = ""
    rfi_number: int = 0
    subject: str = ""
    question: str = ""
    response: str = ""
    submitted_date: str = ""
    response_date: str = ""
    status: str = "open"  # open, answered, closed


@dataclass
class Addendum:
    """Plan revision/addendum for a bid."""
    addendum_id: str = ""
    addendum_number: int = 0
    description: str = ""
    date_issued: str = ""
    sheets_affected: list[str] = field(default_factory=list)
    quantity_changes: dict = field(default_factory=dict)
    acknowledged: bool = False


@dataclass
class BidProject:
    """A single bid/project in the dashboard."""
    # Identity
    project_id: str = ""
    project_name: str = ""
    project_number: str = ""

    # Location
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""

    # Client
    owner: str = ""
    general_contractor: str = ""
    architect: str = ""
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""

    # Bid details
    status: BidStatus = BidStatus.RECEIVED
    priority: BidPriority = BidPriority.MEDIUM
    bid_due_date: str = ""
    bid_due_time: str = ""
    pre_bid_meeting: str = ""
    site_visit_date: str = ""

    # Scope
    trade_scope: list[TradeScope] = field(default_factory=list)
    building_count: int = 1
    total_sf: float = 0.0
    stories: int = 0
    construction_type: str = ""
    description: str = ""

    # Team
    estimator: str = ""
    reviewer: str = ""

    # Financials
    estimated_value: float = 0.0
    bid_amount: float = 0.0
    cost_per_sf: float = 0.0

    # Documents
    plan_files: list[str] = field(default_factory=list)
    spec_files: list[str] = field(default_factory=list)

    # RFIs and Addenda
    rfis: list[RFI] = field(default_factory=list)
    addenda: list[Addendum] = field(default_factory=list)

    # Tracking
    created_at: str = ""
    updated_at: str = ""
    takeoff_started_at: str = ""
    takeoff_completed_at: str = ""
    proposal_sent_at: str = ""
    result_date: str = ""
    lost_reason: str = ""
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Bid Dashboard Manager
# ---------------------------------------------------------------------------

class BidDashboard:
    """Manages all bid projects — the central nerve center.

    Provides:
    - CRUD for bid projects
    - Status tracking and transitions
    - Filtering and search
    - Team workload visibility
    - Pipeline analytics (win rate, avg bid value, etc.)

    Usage:
        dashboard = BidDashboard()
        project = dashboard.create_project(
            project_name="Parkview Apartments",
            bid_due_date="2026-03-15",
            trade_scope=[TradeScope.FULL_ENVELOPE],
            estimator="John Smith",
        )
        dashboard.update_status(project.project_id, BidStatus.TAKEOFF_IN_PROGRESS)
    """

    def __init__(self):
        self._projects: dict[str, BidProject] = {}

    def create_project(self, **kwargs) -> BidProject:
        """Create a new bid project."""
        project = BidProject(**kwargs)
        if not project.project_id:
            project.project_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        project.created_at = now
        project.updated_at = now

        self._projects[project.project_id] = project
        logger.info(
            f"Bid project created: {project.project_name} "
            f"(ID: {project.project_id}, due: {project.bid_due_date})"
        )
        return project

    def get_project(self, project_id: str) -> Optional[BidProject]:
        """Get a project by ID."""
        return self._projects.get(project_id)

    def update_status(
        self, project_id: str, new_status: BidStatus
    ) -> Optional[BidProject]:
        """Update a project's bid status."""
        project = self._projects.get(project_id)
        if not project:
            return None

        old_status = project.status
        project.status = new_status
        project.updated_at = datetime.now().isoformat()

        # Track timestamps for key transitions
        if new_status == BidStatus.TAKEOFF_IN_PROGRESS:
            project.takeoff_started_at = project.updated_at
        elif new_status == BidStatus.TAKEOFF_COMPLETE:
            project.takeoff_completed_at = project.updated_at
        elif new_status == BidStatus.PROPOSAL_SENT:
            project.proposal_sent_at = project.updated_at
        elif new_status in (BidStatus.WON, BidStatus.LOST):
            project.result_date = project.updated_at

        logger.info(
            f"Bid {project.project_name}: "
            f"{old_status.value} → {new_status.value}"
        )
        return project

    def update_project(self, project_id: str, **kwargs) -> Optional[BidProject]:
        """Update project fields."""
        project = self._projects.get(project_id)
        if not project:
            return None

        for key, value in kwargs.items():
            if hasattr(project, key):
                setattr(project, key, value)

        project.updated_at = datetime.now().isoformat()
        return project

    def add_rfi(self, project_id: str, subject: str, question: str) -> Optional[RFI]:
        """Add an RFI to a project."""
        project = self._projects.get(project_id)
        if not project:
            return None

        rfi = RFI(
            rfi_id=str(uuid.uuid4())[:8],
            rfi_number=len(project.rfis) + 1,
            subject=subject,
            question=question,
            submitted_date=datetime.now().isoformat(),
            status="open",
        )
        project.rfis.append(rfi)
        project.updated_at = datetime.now().isoformat()
        return rfi

    def add_addendum(
        self,
        project_id: str,
        description: str,
        sheets_affected: list[str] = None,
        quantity_changes: dict = None,
    ) -> Optional[Addendum]:
        """Add an addendum to a project."""
        project = self._projects.get(project_id)
        if not project:
            return None

        addendum = Addendum(
            addendum_id=str(uuid.uuid4())[:8],
            addendum_number=len(project.addenda) + 1,
            description=description,
            date_issued=datetime.now().isoformat(),
            sheets_affected=sheets_affected or [],
            quantity_changes=quantity_changes or {},
        )
        project.addenda.append(addendum)
        project.updated_at = datetime.now().isoformat()
        return addendum

    # -----------------------------------------------------------------------
    # Query / Filter
    # -----------------------------------------------------------------------

    def list_projects(
        self,
        status: Optional[BidStatus] = None,
        estimator: Optional[str] = None,
        priority: Optional[BidPriority] = None,
        due_within_days: Optional[int] = None,
    ) -> list[BidProject]:
        """List projects with optional filters."""
        projects = list(self._projects.values())

        if status:
            projects = [p for p in projects if p.status == status]
        if estimator:
            projects = [
                p for p in projects
                if p.estimator.lower() == estimator.lower()
            ]
        if priority:
            projects = [p for p in projects if p.priority == priority]
        if due_within_days is not None:
            cutoff = (
                datetime.now() + timedelta(days=due_within_days)
            ).isoformat()
            projects = [
                p for p in projects
                if p.bid_due_date and p.bid_due_date <= cutoff
            ]

        # Sort by due date (soonest first)
        projects.sort(key=lambda p: p.bid_due_date or "9999")
        return projects

    def get_active_bids(self) -> list[BidProject]:
        """Get all bids that are currently being worked on."""
        active_statuses = {
            BidStatus.RECEIVED,
            BidStatus.IN_REVIEW,
            BidStatus.TAKEOFF_IN_PROGRESS,
            BidStatus.TAKEOFF_COMPLETE,
            BidStatus.PRICING,
            BidStatus.ESTIMATE_COMPLETE,
        }
        return [
            p for p in self._projects.values()
            if p.status in active_statuses
        ]

    def get_overdue_bids(self) -> list[BidProject]:
        """Get bids past their due date that haven't been submitted."""
        now = datetime.now().isoformat()
        submitted = {
            BidStatus.PROPOSAL_SENT, BidStatus.WON,
            BidStatus.LOST, BidStatus.NO_BID, BidStatus.WITHDRAWN,
        }
        return [
            p for p in self._projects.values()
            if p.bid_due_date and p.bid_due_date < now
            and p.status not in submitted
        ]

    # -----------------------------------------------------------------------
    # Analytics
    # -----------------------------------------------------------------------

    def get_pipeline_stats(self) -> dict:
        """Get pipeline analytics — win rate, avg value, volume, etc."""
        all_projects = list(self._projects.values())
        if not all_projects:
            return {
                "total_bids": 0, "active_bids": 0,
                "won": 0, "lost": 0, "win_rate": 0,
                "total_pipeline_value": 0, "avg_bid_value": 0,
            }

        won = [p for p in all_projects if p.status == BidStatus.WON]
        lost = [p for p in all_projects if p.status == BidStatus.LOST]
        active = self.get_active_bids()
        decided = len(won) + len(lost)

        return {
            "total_bids": len(all_projects),
            "active_bids": len(active),
            "won": len(won),
            "lost": len(lost),
            "no_bid": len([
                p for p in all_projects if p.status == BidStatus.NO_BID
            ]),
            "win_rate": round(
                len(won) / decided * 100, 1
            ) if decided > 0 else 0,
            "total_pipeline_value": sum(
                p.estimated_value for p in active
            ),
            "avg_bid_value": round(
                sum(p.bid_amount for p in won) / len(won), 2
            ) if won else 0,
            "total_won_value": sum(p.bid_amount for p in won),
            "overdue_count": len(self.get_overdue_bids()),
            "by_status": {
                s.value: len([
                    p for p in all_projects if p.status == s
                ])
                for s in BidStatus
            },
            "by_estimator": self._group_by_estimator(all_projects),
        }

    def _group_by_estimator(self, projects: list[BidProject]) -> dict:
        """Group project counts by estimator."""
        result = {}
        for p in projects:
            name = p.estimator or "Unassigned"
            if name not in result:
                result[name] = {"active": 0, "won": 0, "total": 0}
            result[name]["total"] += 1
            if p.status == BidStatus.WON:
                result[name]["won"] += 1
            elif p.status not in (
                BidStatus.LOST, BidStatus.NO_BID, BidStatus.WITHDRAWN
            ):
                result[name]["active"] += 1
        return result

    # -----------------------------------------------------------------------
    # Serialization
    # -----------------------------------------------------------------------

    def project_to_dict(self, project: BidProject) -> dict:
        """Convert project to JSON-serializable dict."""
        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "project_number": project.project_number,
            "address": project.address,
            "city": project.city,
            "state": project.state,
            "owner": project.owner,
            "general_contractor": project.general_contractor,
            "architect": project.architect,
            "contact": {
                "name": project.contact_name,
                "email": project.contact_email,
                "phone": project.contact_phone,
            },
            "status": project.status.value,
            "priority": project.priority.value,
            "bid_due_date": project.bid_due_date,
            "bid_due_time": project.bid_due_time,
            "trade_scope": [t.value for t in project.trade_scope],
            "building_count": project.building_count,
            "total_sf": project.total_sf,
            "stories": project.stories,
            "estimator": project.estimator,
            "reviewer": project.reviewer,
            "estimated_value": project.estimated_value,
            "bid_amount": project.bid_amount,
            "cost_per_sf": project.cost_per_sf,
            "plan_files": project.plan_files,
            "rfis": [
                {
                    "rfi_id": r.rfi_id,
                    "number": r.rfi_number,
                    "subject": r.subject,
                    "question": r.question,
                    "response": r.response,
                    "status": r.status,
                    "submitted": r.submitted_date,
                    "responded": r.response_date,
                }
                for r in project.rfis
            ],
            "addenda": [
                {
                    "addendum_id": a.addendum_id,
                    "number": a.addendum_number,
                    "description": a.description,
                    "date_issued": a.date_issued,
                    "sheets_affected": a.sheets_affected,
                    "quantity_changes": a.quantity_changes,
                    "acknowledged": a.acknowledged,
                }
                for a in project.addenda
            ],
            "timestamps": {
                "created": project.created_at,
                "updated": project.updated_at,
                "takeoff_started": project.takeoff_started_at,
                "takeoff_completed": project.takeoff_completed_at,
                "proposal_sent": project.proposal_sent_at,
                "result": project.result_date,
            },
            "notes": project.notes,
            "lost_reason": project.lost_reason,
        }
