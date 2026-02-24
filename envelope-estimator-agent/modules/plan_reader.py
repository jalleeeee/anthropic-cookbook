"""
AI Plan Reader — Ask questions about blueprints and specs.

Clones BEAM AI's "BeamGPT" feature:
- Upload plans/specs, then ask natural language questions
- "What is the roof pitch?" → reads from the drawings
- "What cladding is specified?" → reads from the specs
- "How many units per building?" → reads from general notes

Also includes Addendum Comparison:
- Upload original + revised drawings
- AI detects what changed (added, removed, modified quantities)
- Generates a variance report showing quantity deltas

Our advantage: BEAM's plan reader just answers questions.
Ours answers questions AND feeds data into the deductive engine
for instant re-estimation when specs change.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from config.settings import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PlanQuestion:
    """A question asked about the plans."""
    question: str
    answer: str = ""
    confidence: str = ""     # high, medium, low
    source_page: str = ""    # Which page/sheet the answer came from
    source_quote: str = ""   # Exact text from the plans


@dataclass
class QuantityChange:
    """A single quantity change between plan versions."""
    item: str
    description: str
    original_qty: float = 0.0
    revised_qty: float = 0.0
    delta: float = 0.0
    delta_pct: float = 0.0
    unit: str = ""
    change_type: str = ""   # added, removed, increased, decreased, unchanged
    sheet: str = ""          # Which sheet the change is on


@dataclass
class AddendumVarianceReport:
    """Variance report between two plan versions — like BEAM's addenda comparison."""
    addendum_number: int = 0
    original_date: str = ""
    revised_date: str = ""
    description: str = ""
    # Changes
    changes: list[QuantityChange] = field(default_factory=list)
    sheets_affected: list[str] = field(default_factory=list)
    # Summary
    total_items_changed: int = 0
    items_added: int = 0
    items_removed: int = 0
    items_increased: int = 0
    items_decreased: int = 0
    net_cost_impact: float = 0.0


# ---------------------------------------------------------------------------
# AI Plan Reader
# ---------------------------------------------------------------------------

class PlanReader:
    """AI-powered plan reader that answers questions about blueprints.

    Workflow:
    1. Plans are uploaded and stored (PDF pages converted to images)
    2. User asks a natural language question
    3. AI reads the relevant pages and extracts the answer
    4. Answer includes source page and confidence level

    Also handles addendum comparison:
    1. Upload original + revised plan pages
    2. AI compares and identifies changes
    3. Generates structured variance report

    Usage:
        reader = PlanReader(settings)

        # Ask a question about plans
        answer = reader.ask(
            question="What is the specified roof type?",
            plan_pages=[page1_base64, page2_base64, ...]
        )

        # Compare addenda
        report = reader.compare_addenda(
            original_pages=[...],
            revised_pages=[...],
            description="Addendum #2 — revised elevations"
        )
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic.api_key,
        )
        self.model = settings.anthropic.model

    def ask(
        self,
        question: str,
        plan_pages: list[str],
        context: str = "",
    ) -> PlanQuestion:
        """Ask a question about the plans.

        Args:
            question: Natural language question about the plans
            plan_pages: List of base64-encoded page images
            context: Additional context (e.g., project description)

        Returns:
            PlanQuestion with answer, confidence, and source
        """
        # Build the message with plan images
        content = []

        # Add plan page images (up to 8 pages for context window)
        for i, page_b64 in enumerate(plan_pages[:8]):
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": page_b64,
                },
            })

        # Add the question
        prompt = f"""You are an expert construction plan reader. You have been given
blueprint/specification pages from a construction project.

Answer the following question by reading the plans carefully:

QUESTION: {question}

{f"Additional context: {context}" if context else ""}

Respond in this exact format:
ANSWER: [your answer]
CONFIDENCE: [high/medium/low]
SOURCE PAGE: [which page number you found this on, or "multiple" if across pages]
SOURCE QUOTE: [exact text or dimension from the plans that supports your answer]

If you cannot find the answer in the provided pages, say so clearly
and suggest which sheet types might contain the information."""

        content.append({"type": "text", "text": prompt})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": content}],
            )

            text = response.content[0].text
            result = PlanQuestion(question=question)

            # Parse structured response
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("ANSWER:"):
                    result.answer = line[7:].strip()
                elif line.startswith("CONFIDENCE:"):
                    result.confidence = line[11:].strip().lower()
                elif line.startswith("SOURCE PAGE:"):
                    result.source_page = line[12:].strip()
                elif line.startswith("SOURCE QUOTE:"):
                    result.source_quote = line[13:].strip()

            # If parsing failed, use the full response as the answer
            if not result.answer:
                result.answer = text
                result.confidence = "medium"

            logger.info(
                f"Plan reader: '{question}' → "
                f"{result.confidence} confidence"
            )
            return result

        except Exception as e:
            logger.error(f"Plan reader error: {e}")
            return PlanQuestion(
                question=question,
                answer=f"Error reading plans: {str(e)}",
                confidence="low",
            )

    def ask_about_specs(
        self,
        question: str,
        spec_text: str,
    ) -> PlanQuestion:
        """Ask a question about specification documents (text-based).

        For when specs are available as text rather than images.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": f"""You are an expert construction specification reader.

Given these project specifications:
---
{spec_text[:15000]}
---

Answer this question:
QUESTION: {question}

Respond in this exact format:
ANSWER: [your answer]
CONFIDENCE: [high/medium/low]
SOURCE: [which spec section you found this in]
QUOTE: [exact text from the spec that supports your answer]""",
                }],
            )

            text = response.content[0].text
            result = PlanQuestion(question=question)

            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("ANSWER:"):
                    result.answer = line[7:].strip()
                elif line.startswith("CONFIDENCE:"):
                    result.confidence = line[11:].strip().lower()
                elif line.startswith("SOURCE:"):
                    result.source_page = line[7:].strip()
                elif line.startswith("QUOTE:"):
                    result.source_quote = line[6:].strip()

            if not result.answer:
                result.answer = text
                result.confidence = "medium"

            return result

        except Exception as e:
            logger.error(f"Spec reader error: {e}")
            return PlanQuestion(
                question=question,
                answer=f"Error reading specs: {str(e)}",
                confidence="low",
            )

    # -----------------------------------------------------------------------
    # Addendum Comparison
    # -----------------------------------------------------------------------

    def compare_addenda(
        self,
        original_pages: list[str],
        revised_pages: list[str],
        description: str = "",
        addendum_number: int = 1,
    ) -> AddendumVarianceReport:
        """Compare original vs revised plan pages and generate variance report.

        This is BEAM AI's addendum comparison feature — detects drawing
        changes and produces a structured variance report.

        Args:
            original_pages: Base64-encoded images of original plan pages
            revised_pages: Base64-encoded images of revised plan pages
            description: Description of the addendum
            addendum_number: Addendum number for tracking

        Returns:
            AddendumVarianceReport with all quantity changes
        """
        content = []

        # Add original pages
        content.append({
            "type": "text",
            "text": "ORIGINAL PLANS (before addendum):",
        })
        for page_b64 in original_pages[:5]:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": page_b64,
                },
            })

        # Add revised pages
        content.append({
            "type": "text",
            "text": "REVISED PLANS (after addendum):",
        })
        for page_b64 in revised_pages[:5]:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": page_b64,
                },
            })

        # Add comparison prompt
        content.append({
            "type": "text",
            "text": f"""You are an expert construction plan reviewer comparing original
plans vs. revised plans (Addendum #{addendum_number}).

{f"Addendum description: {description}" if description else ""}

Compare these two sets of drawings and identify ALL changes.
Focus on changes that affect quantities and costs:
- Dimensions that changed
- Materials that were substituted
- Scope that was added or removed
- Notes or specifications that changed

For each change, provide:
CHANGE: [item description]
ORIGINAL: [original value with unit]
REVISED: [revised value with unit]
SHEET: [which sheet the change is on]
TYPE: [added/removed/increased/decreased]

List every change you can identify, then provide:
SUMMARY: [total items changed], [items added], [items removed],
[items increased], [items decreased]
SHEETS_AFFECTED: [comma-separated list of affected sheets]""",
        })

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )

            text = response.content[0].text
            report = AddendumVarianceReport(
                addendum_number=addendum_number,
                description=description,
            )

            # Parse changes
            current_change = {}
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("CHANGE:"):
                    if current_change.get("item"):
                        report.changes.append(
                            self._parse_change(current_change)
                        )
                    current_change = {"item": line[7:].strip()}
                elif line.startswith("ORIGINAL:"):
                    current_change["original"] = line[9:].strip()
                elif line.startswith("REVISED:"):
                    current_change["revised"] = line[8:].strip()
                elif line.startswith("SHEET:"):
                    current_change["sheet"] = line[6:].strip()
                elif line.startswith("TYPE:"):
                    current_change["type"] = line[5:].strip().lower()
                elif line.startswith("SHEETS_AFFECTED:"):
                    sheets = line[16:].strip()
                    report.sheets_affected = [
                        s.strip() for s in sheets.split(",")
                    ]

            # Append last change
            if current_change.get("item"):
                report.changes.append(self._parse_change(current_change))

            # Compute summary
            report.total_items_changed = len(report.changes)
            report.items_added = len([
                c for c in report.changes if c.change_type == "added"
            ])
            report.items_removed = len([
                c for c in report.changes if c.change_type == "removed"
            ])
            report.items_increased = len([
                c for c in report.changes if c.change_type == "increased"
            ])
            report.items_decreased = len([
                c for c in report.changes if c.change_type == "decreased"
            ])

            logger.info(
                f"Addendum #{addendum_number} comparison: "
                f"{report.total_items_changed} changes detected"
            )
            return report

        except Exception as e:
            logger.error(f"Addendum comparison error: {e}")
            return AddendumVarianceReport(
                addendum_number=addendum_number,
                description=f"Error: {str(e)}",
            )

    def _parse_change(self, data: dict) -> QuantityChange:
        """Parse a raw change dict into a QuantityChange."""
        change = QuantityChange(
            item=data.get("item", ""),
            description=data.get("item", ""),
            sheet=data.get("sheet", ""),
            change_type=data.get("type", "modified"),
        )

        # Try to extract numeric values
        orig = data.get("original", "")
        rev = data.get("revised", "")

        orig_num = self._extract_number(orig)
        rev_num = self._extract_number(rev)

        if orig_num is not None:
            change.original_qty = orig_num
        if rev_num is not None:
            change.revised_qty = rev_num

        if orig_num is not None and rev_num is not None:
            change.delta = rev_num - orig_num
            if orig_num > 0:
                change.delta_pct = round(
                    (change.delta / orig_num) * 100, 1
                )

        return change

    def _extract_number(self, text: str) -> Optional[float]:
        """Try to extract a number from text like '120 SF' or '45.5 LF'."""
        import re
        match = re.search(r"([\d,.]+)", text)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass
        return None

    # -----------------------------------------------------------------------
    # Serialization
    # -----------------------------------------------------------------------

    def question_to_dict(self, q: PlanQuestion) -> dict:
        return {
            "question": q.question,
            "answer": q.answer,
            "confidence": q.confidence,
            "source_page": q.source_page,
            "source_quote": q.source_quote,
        }

    def variance_report_to_dict(self, r: AddendumVarianceReport) -> dict:
        return {
            "addendum_number": r.addendum_number,
            "description": r.description,
            "summary": {
                "total_changes": r.total_items_changed,
                "added": r.items_added,
                "removed": r.items_removed,
                "increased": r.items_increased,
                "decreased": r.items_decreased,
                "net_cost_impact": r.net_cost_impact,
            },
            "sheets_affected": r.sheets_affected,
            "changes": [
                {
                    "item": c.item,
                    "original_qty": c.original_qty,
                    "revised_qty": c.revised_qty,
                    "delta": c.delta,
                    "delta_pct": c.delta_pct,
                    "unit": c.unit,
                    "change_type": c.change_type,
                    "sheet": c.sheet,
                }
                for c in r.changes
            ],
        }
