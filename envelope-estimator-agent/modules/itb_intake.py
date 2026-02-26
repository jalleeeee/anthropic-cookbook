"""
ITB (Invitation to Bid) Intake Module

Monitors multiple sources for incoming bid requests:
- IMAP email folders
- Watched local directories (for plan drops)
- Webhook/API endpoint (for integration with estimating software)

Extracts project metadata and PDF attachments, then queues them for processing.
"""

import email
import imaplib
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from email.header import decode_header
from pathlib import Path
from typing import Optional

import anthropic

from config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class ProjectInfo:
    """Extracted project metadata from an ITB."""
    project_id: str = ""
    project_name: str = ""
    general_contractor: str = ""
    gc_contact_name: str = ""
    gc_contact_email: str = ""
    gc_contact_phone: str = ""
    bid_due_date: Optional[str] = None
    bid_due_time: Optional[str] = None
    project_address: str = ""
    project_city: str = ""
    project_state: str = ""
    project_type: str = ""          # multifamily, commercial, mixed-use
    building_count: int = 0
    unit_count: int = 0
    story_count: int = 0
    requested_trades: list[str] = field(default_factory=list)
    scope_notes: str = ""
    addenda: list[str] = field(default_factory=list)
    source: str = ""                # "email", "folder", "api"
    source_details: str = ""        # email subject, folder path, etc.
    received_at: str = ""
    pdf_paths: list[str] = field(default_factory=list)
    raw_text: str = ""


class ITBIntake:
    """Monitors sources for incoming ITBs and extracts project info."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic.api_key)
        self.output_dir = Path(settings.output_dir) / "itb_inbox"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Email monitoring
    # ------------------------------------------------------------------

    def check_email(self) -> list[ProjectInfo]:
        """Check IMAP inbox for new ITB emails with plan attachments."""
        cfg = self.settings.email
        if not cfg.imap_server:
            logger.debug("Email not configured, skipping")
            return []

        projects = []
        try:
            mail = imaplib.IMAP4_SSL(cfg.imap_server, cfg.imap_port)
            mail.login(cfg.username, cfg.password)
            mail.select(cfg.watched_folder)

            # Search for unseen messages
            status, message_ids = mail.search(None, "UNSEEN")
            if status != "OK":
                return []

            for msg_id in message_ids[0].split():
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Extract subject
                subject = ""
                raw_subject = decode_header(msg["Subject"])[0]
                if isinstance(raw_subject[0], bytes):
                    subject = raw_subject[0].decode(raw_subject[1] or "utf-8")
                else:
                    subject = raw_subject[0]

                # Check if this looks like an ITB
                itb_keywords = [
                    "invitation to bid", "itb", "request for proposal",
                    "rfp", "bid request", "subcontractor bid",
                    "plans attached", "drawings attached",
                    "bid due", "scope of work",
                ]
                subject_lower = subject.lower()
                body_text = self._extract_email_body(msg)
                combined_text = f"{subject_lower} {body_text.lower()}"

                is_itb = any(kw in combined_text for kw in itb_keywords)
                if not is_itb:
                    continue

                logger.info(f"ITB detected: {subject}")

                # Extract PDF attachments
                project_dir = self.output_dir / _safe_dirname(subject)
                project_dir.mkdir(parents=True, exist_ok=True)
                pdf_paths = self._save_attachments(msg, project_dir)

                if not pdf_paths:
                    logger.warning(f"No PDF attachments in ITB: {subject}")
                    # Still process - might have links to plan rooms
                    # Save the email body for link extraction
                    (project_dir / "email_body.txt").write_text(body_text)

                # Use Claude to extract project metadata from the email
                project = self._extract_project_info(
                    subject=subject,
                    body=body_text,
                    sender=msg.get("From", ""),
                    pdf_paths=pdf_paths,
                    source="email",
                )
                projects.append(project)

                # Mark as processed
                mail.store(msg_id, "+FLAGS", "\\Flagged")

            mail.logout()

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
        except Exception as e:
            logger.error(f"Email check failed: {e}")

        return projects

    def _extract_email_body(self, msg: email.message.Message) -> str:
        """Extract plain text body from email message."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")
        return body

    def _save_attachments(
        self, msg: email.message.Message, dest_dir: Path
    ) -> list[str]:
        """Save PDF attachments from email to disk."""
        pdf_paths = []
        for part in msg.walk():
            content_type = part.get_content_type()
            filename = part.get_filename()
            if filename and (
                content_type == "application/pdf"
                or filename.lower().endswith(".pdf")
            ):
                filepath = dest_dir / filename
                with open(filepath, "wb") as f:
                    f.write(part.get_payload(decode=True))
                pdf_paths.append(str(filepath))
                logger.info(f"  Saved attachment: {filename}")
        return pdf_paths

    # ------------------------------------------------------------------
    # Watched folder monitoring
    # ------------------------------------------------------------------

    def check_watched_folder(self) -> list[ProjectInfo]:
        """Check watched folder for new PDF plan sets."""
        cfg = self.settings.watched_folder
        if not cfg.enabled or not cfg.path:
            return []

        folder = Path(cfg.path)
        if not folder.exists():
            logger.warning(f"Watched folder does not exist: {cfg.path}")
            return []

        projects = []
        for item in folder.iterdir():
            if item.suffix.lower() == ".pdf":
                # Single PDF file
                project_dir = self.output_dir / item.stem
                project_dir.mkdir(parents=True, exist_ok=True)
                dest = project_dir / item.name
                shutil.copy2(item, dest)

                project = self._extract_project_info(
                    subject=item.stem,
                    body="",
                    sender="",
                    pdf_paths=[str(dest)],
                    source="folder",
                )
                projects.append(project)

                if cfg.archive_processed:
                    archive = folder / "processed"
                    archive.mkdir(exist_ok=True)
                    item.rename(archive / item.name)

            elif item.is_dir():
                # Directory with multiple PDFs
                pdfs = list(item.glob("*.pdf")) + list(item.glob("*.PDF"))
                if pdfs:
                    project_dir = self.output_dir / item.name
                    project_dir.mkdir(parents=True, exist_ok=True)
                    pdf_paths = []
                    for pdf in pdfs:
                        dest = project_dir / pdf.name
                        shutil.copy2(pdf, dest)
                        pdf_paths.append(str(dest))

                    project = self._extract_project_info(
                        subject=item.name,
                        body="",
                        sender="",
                        pdf_paths=pdf_paths,
                        source="folder",
                    )
                    projects.append(project)

                    if cfg.archive_processed:
                        archive = folder / "processed"
                        archive.mkdir(exist_ok=True)
                        shutil.move(str(item), str(archive / item.name))

        return projects

    # ------------------------------------------------------------------
    # API / webhook intake
    # ------------------------------------------------------------------

    def process_api_submission(
        self,
        project_name: str,
        pdf_paths: list[str],
        metadata: Optional[dict] = None,
    ) -> ProjectInfo:
        """Process an ITB submitted via API/webhook."""
        return self._extract_project_info(
            subject=project_name,
            body=json.dumps(metadata) if metadata else "",
            sender="",
            pdf_paths=pdf_paths,
            source="api",
        )

    # ------------------------------------------------------------------
    # AI-powered metadata extraction
    # ------------------------------------------------------------------

    def _extract_project_info(
        self,
        subject: str,
        body: str,
        sender: str,
        pdf_paths: list[str],
        source: str,
    ) -> ProjectInfo:
        """Use Claude to extract structured project info from ITB text."""
        prompt = f"""You are a construction estimating assistant. Extract project
metadata from this Invitation to Bid (ITB).

Subject: {subject}
From: {sender}
Body:
{body[:4000]}

PDF files received: {', '.join(os.path.basename(p) for p in pdf_paths)}

Extract and return a JSON object with these fields (use empty string if unknown):
{{
  "project_name": "",
  "general_contractor": "",
  "gc_contact_name": "",
  "gc_contact_email": "",
  "gc_contact_phone": "",
  "bid_due_date": "",
  "bid_due_time": "",
  "project_address": "",
  "project_city": "",
  "project_state": "",
  "project_type": "",
  "building_count": 0,
  "unit_count": 0,
  "story_count": 0,
  "requested_trades": [],
  "scope_notes": "",
  "addenda": []
}}

Focus on identifying which envelope trades are requested:
siding, roofing, gutters, downspouts, coping, windows, decking,
exterior doors, railing, framing, painting, drywall.

Return ONLY the JSON object, no other text."""

        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_fast,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()

            # Parse JSON from response
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = {}

        except Exception as e:
            logger.error(f"Failed to extract project info: {e}")
            data = {"project_name": subject}

        project = ProjectInfo(
            project_id=_generate_project_id(),
            project_name=data.get("project_name", subject),
            general_contractor=data.get("general_contractor", ""),
            gc_contact_name=data.get("gc_contact_name", ""),
            gc_contact_email=data.get("gc_contact_email", sender),
            gc_contact_phone=data.get("gc_contact_phone", ""),
            bid_due_date=data.get("bid_due_date"),
            bid_due_time=data.get("bid_due_time"),
            project_address=data.get("project_address", ""),
            project_city=data.get("project_city", ""),
            project_state=data.get("project_state", ""),
            project_type=data.get("project_type", ""),
            building_count=data.get("building_count", 0),
            unit_count=data.get("unit_count", 0),
            story_count=data.get("story_count", 0),
            requested_trades=data.get("requested_trades", []),
            scope_notes=data.get("scope_notes", ""),
            addenda=data.get("addenda", []),
            source=source,
            source_details=subject,
            received_at=datetime.now().isoformat(),
            pdf_paths=pdf_paths,
            raw_text=body[:8000],
        )

        # Save project info to disk
        project_file = self.output_dir / f"{project.project_id}.json"
        project_file.write_text(json.dumps(_project_to_dict(project), indent=2))
        logger.info(
            f"Project registered: {project.project_name} "
            f"(ID: {project.project_id}, {len(pdf_paths)} PDFs)"
        )

        return project


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_project_id() -> str:
    return f"PRJ-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _safe_dirname(name: str) -> str:
    return re.sub(r"[^\w\s-]", "", name).strip()[:60]


def _project_to_dict(p: ProjectInfo) -> dict:
    return {
        "project_id": p.project_id,
        "project_name": p.project_name,
        "general_contractor": p.general_contractor,
        "gc_contact_name": p.gc_contact_name,
        "gc_contact_email": p.gc_contact_email,
        "gc_contact_phone": p.gc_contact_phone,
        "bid_due_date": p.bid_due_date,
        "bid_due_time": p.bid_due_time,
        "project_address": p.project_address,
        "project_city": p.project_city,
        "project_state": p.project_state,
        "project_type": p.project_type,
        "building_count": p.building_count,
        "unit_count": p.unit_count,
        "story_count": p.story_count,
        "requested_trades": p.requested_trades,
        "scope_notes": p.scope_notes,
        "addenda": p.addenda,
        "source": p.source,
        "source_details": p.source_details,
        "received_at": p.received_at,
        "pdf_paths": p.pdf_paths,
    }
