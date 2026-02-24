"""
Proposal Generation Module

Generates professional bid proposals from cost estimates.
Output formats: HTML (primary), with PDF export via browser print.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import anthropic

from config.settings import Settings
from modules.cost_engine import EstimateResult, TradeCostSummary
from modules.itb_intake import ProjectInfo
from modules.pdf_takeoff import TakeoffResult

logger = logging.getLogger(__name__)


class ProposalGenerator:
    """Generates professional bid proposals."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic.api_key)
        self.output_dir = Path(settings.output_dir) / "proposals"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        project: ProjectInfo,
        takeoff: TakeoffResult,
        estimate: EstimateResult,
        include_detail: bool = True,
    ) -> dict:
        """Generate a complete bid proposal.

        Returns dict with paths to generated files.
        """
        company = self.settings.company
        proposal_date = datetime.now()
        valid_until = proposal_date + timedelta(
            days=company.proposal_validity_days
        )

        # Generate scope narrative using AI
        scope_narrative = self._generate_scope_narrative(
            project, takeoff, estimate
        )

        # Generate exclusions and clarifications
        exclusions = self._generate_exclusions(project, takeoff)

        # Build the HTML proposal
        html = self._build_html_proposal(
            project=project,
            takeoff=takeoff,
            estimate=estimate,
            scope_narrative=scope_narrative,
            exclusions=exclusions,
            proposal_date=proposal_date,
            valid_until=valid_until,
            include_detail=include_detail,
        )

        # Save files
        project_slug = re.sub(
            r"[^\w-]", "_", project.project_name or project.project_id
        )[:50]
        date_str = proposal_date.strftime("%Y%m%d")

        html_path = self.output_dir / f"{project_slug}_{date_str}_proposal.html"
        html_path.write_text(html, encoding="utf-8")

        # Save JSON summary
        summary = self._build_json_summary(
            project, takeoff, estimate, proposal_date, valid_until
        )
        json_path = self.output_dir / f"{project_slug}_{date_str}_summary.json"
        json_path.write_text(json.dumps(summary, indent=2))

        logger.info(f"Proposal generated: {html_path}")

        return {
            "html": str(html_path),
            "json": str(json_path),
            "grand_total": estimate.grand_total,
            "currency": estimate.currency,
        }

    # ------------------------------------------------------------------
    # AI-generated scope narrative
    # ------------------------------------------------------------------

    def _generate_scope_narrative(
        self,
        project: ProjectInfo,
        takeoff: TakeoffResult,
        estimate: EstimateResult,
    ) -> str:
        """Use Claude to write a professional scope of work narrative."""
        trade_list = "\n".join(
            f"- {s.trade_name}: {len(s.line_items)} items, "
            f"${s.trade_total:,.2f}"
            for s in estimate.trade_summaries
        )

        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_fast,
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": f"""Write a professional scope of work
narrative for a commercial construction bid proposal.

Project: {project.project_name}
Type: {project.project_type}
Location: {project.project_city}, {project.project_state}
Buildings: {project.building_count}, Units: {project.unit_count}
Stories: {project.story_count or takeoff.story_count}

Building dimensions:
- Footprint: {takeoff.building_footprint_sf:,.0f} SF
- Roof pitch: {takeoff.roof_pitch}
- Net wall area: {takeoff.net_wall_area_sf:,.0f} SF

Trades included:
{trade_list}

Write 2-3 paragraphs describing the scope of work in professional
construction language. Be specific about materials and quantities.
Do not include pricing in the narrative. Write in first person plural
("We will provide..."). Keep it concise and professional.""",
                }],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Scope narrative generation failed: {e}")
            return "Scope of work as described in the attached estimate detail."

    def _generate_exclusions(
        self, project: ProjectInfo, takeoff: TakeoffResult
    ) -> list[str]:
        """Generate standard exclusions and clarifications."""
        exclusions = [
            "Permits and permit fees (by others)",
            "Engineering and design services (by others)",
            "Temporary utilities, dumpsters, and site facilities (by GC)",
            "Scaffolding beyond standard ladder access (by GC unless noted)",
            "Hazardous material testing, abatement, or disposal",
            "Work outside normal business hours unless noted",
            "Structural repairs or modifications to existing conditions",
            "Final cleaning beyond our scope areas",
        ]

        # Add trade-specific exclusions based on what's NOT included
        from config.trades import ALL_TRADES, Phase

        included_codes = {
            s.trade_code for s in
            # We don't have estimate here, derive from takeoff
            []
        }

        # Add general note about what's included
        if takeoff.warnings:
            exclusions.append(
                "Items flagged during takeoff review require field verification"
            )

        return exclusions

    # ------------------------------------------------------------------
    # HTML proposal builder
    # ------------------------------------------------------------------

    def _build_html_proposal(
        self,
        project: ProjectInfo,
        takeoff: TakeoffResult,
        estimate: EstimateResult,
        scope_narrative: str,
        exclusions: list[str],
        proposal_date: datetime,
        valid_until: datetime,
        include_detail: bool,
    ) -> str:
        """Build the full HTML proposal document."""
        company = self.settings.company

        # Trade summary rows
        trade_rows = ""
        for ts in estimate.trade_summaries:
            trade_rows += f"""
            <tr>
                <td>{ts.trade_name}</td>
                <td class="money">${ts.subtotal_material:,.2f}</td>
                <td class="money">${ts.subtotal_labor:,.2f}</td>
                <td class="money">${ts.subtotal_equipment:,.2f}</td>
                <td class="money">${ts.subtotal_direct:,.2f}</td>
                <td class="money">${ts.overhead:,.2f}</td>
                <td class="money">${ts.profit:,.2f}</td>
                <td class="money total">${ts.trade_total:,.2f}</td>
            </tr>"""

        # Detail section per trade
        detail_section = ""
        if include_detail:
            for ts in estimate.trade_summaries:
                detail_rows = ""
                for item in ts.line_items:
                    detail_rows += f"""
                    <tr>
                        <td>{item.component_name}</td>
                        <td class="center">{item.quantity:,.1f}</td>
                        <td class="center">{item.unit}</td>
                        <td class="money">${item.unit_price:,.2f}</td>
                        <td class="money">${item.extended_price:,.2f}</td>
                    </tr>"""

                detail_section += f"""
                <div class="trade-detail">
                    <h3>{ts.trade_name}</h3>
                    <table class="detail-table">
                        <thead>
                            <tr>
                                <th>Component</th>
                                <th>Quantity</th>
                                <th>Unit</th>
                                <th>Unit Price</th>
                                <th>Extended</th>
                            </tr>
                        </thead>
                        <tbody>
                            {detail_rows}
                        </tbody>
                        <tfoot>
                            <tr class="subtotal-row">
                                <td colspan="4"><strong>{ts.trade_name} Subtotal</strong></td>
                                <td class="money total">${ts.trade_total:,.2f}</td>
                            </tr>
                        </tfoot>
                    </table>
                </div>"""

        # Exclusions list
        exclusion_items = "\n".join(
            f"<li>{exc}</li>" for exc in exclusions
        )

        # Warnings / notes
        warning_items = ""
        if takeoff.warnings:
            warning_items = "<h3>Notes &amp; Clarifications</h3><ul>"
            for w in takeoff.warnings:
                warning_items += f"<li>{w}</li>"
            warning_items += "</ul>"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Proposal - {_esc(project.project_name)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #1a1a2e; background: #fff; line-height: 1.5;
            max-width: 1000px; margin: 0 auto; padding: 40px;
        }}
        .header {{
            display: flex; justify-content: space-between;
            align-items: flex-start; border-bottom: 3px solid #16213e;
            padding-bottom: 20px; margin-bottom: 30px;
        }}
        .company-info h1 {{ font-size: 24px; color: #16213e; }}
        .company-info p {{ font-size: 13px; color: #555; }}
        .proposal-meta {{ text-align: right; }}
        .proposal-meta h2 {{ font-size: 20px; color: #0f3460; }}
        .proposal-meta p {{ font-size: 13px; color: #555; }}

        .project-box {{
            background: #f0f4f8; border-radius: 8px;
            padding: 20px; margin-bottom: 25px;
        }}
        .project-box h3 {{ color: #16213e; margin-bottom: 10px; }}
        .project-grid {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
        }}
        .project-grid .label {{ font-weight: 600; color: #333; }}
        .project-grid .value {{ color: #555; }}

        h2 {{ color: #16213e; border-bottom: 1px solid #ddd;
              padding-bottom: 8px; margin: 25px 0 15px; font-size: 18px; }}
        h3 {{ color: #0f3460; margin: 15px 0 10px; font-size: 16px; }}

        .scope {{ margin-bottom: 20px; }}
        .scope p {{ margin-bottom: 10px; }}

        table {{
            width: 100%; border-collapse: collapse; margin-bottom: 20px;
            font-size: 13px;
        }}
        th {{
            background: #16213e; color: #fff; padding: 10px 12px;
            text-align: left; font-weight: 600;
        }}
        td {{ padding: 8px 12px; border-bottom: 1px solid #e0e0e0; }}
        tr:nth-child(even) {{ background: #f8f9fa; }}
        .money {{ text-align: right; font-family: 'Courier New', monospace; }}
        .center {{ text-align: center; }}
        .total {{ font-weight: 700; color: #16213e; }}

        .subtotal-row td {{ background: #e8edf2; font-weight: 600; }}

        .grand-total {{
            background: #16213e; color: #fff; border-radius: 8px;
            padding: 20px; text-align: center; margin: 25px 0;
        }}
        .grand-total .amount {{
            font-size: 32px; font-weight: 700; margin: 5px 0;
        }}
        .grand-total .label {{ font-size: 14px; opacity: 0.8; }}
        .grand-total .per-sf {{ font-size: 14px; opacity: 0.7; }}

        .totals-breakdown {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
            margin-bottom: 20px;
        }}
        .totals-breakdown .item {{
            display: flex; justify-content: space-between;
            padding: 4px 0; border-bottom: 1px dotted #ccc;
        }}

        .exclusions ul {{ padding-left: 20px; }}
        .exclusions li {{ margin-bottom: 5px; color: #555; }}

        .terms {{ margin-top: 25px; }}
        .terms p {{ margin-bottom: 8px; font-size: 13px; color: #555; }}

        .signature {{
            margin-top: 40px; display: grid;
            grid-template-columns: 1fr 1fr; gap: 40px;
        }}
        .sig-block {{ border-top: 1px solid #333; padding-top: 10px; }}
        .sig-block .label {{ font-size: 12px; color: #777; }}

        .trade-detail {{ margin-bottom: 20px; page-break-inside: avoid; }}
        .detail-table th {{ background: #0f3460; }}

        .confidence-bar {{
            display: inline-block; width: 60px; height: 8px;
            background: #e0e0e0; border-radius: 4px; margin-left: 8px;
        }}
        .confidence-fill {{
            height: 100%; border-radius: 4px;
            background: #2ecc71;
        }}

        .footer {{
            margin-top: 40px; padding-top: 15px;
            border-top: 1px solid #ddd; text-align: center;
            font-size: 11px; color: #999;
        }}

        @media print {{
            body {{ padding: 20px; }}
            .grand-total {{ -webkit-print-color-adjust: exact; }}
            th {{ -webkit-print-color-adjust: exact; }}
        }}
    </style>
</head>
<body>

<!-- HEADER -->
<div class="header">
    <div class="company-info">
        <h1>{_esc(company.name) or 'Your Company Name'}</h1>
        <p>{_esc(company.address)}</p>
        <p>{_esc(company.city)}, {_esc(company.state)} {_esc(company.zip_code)}</p>
        <p>{_esc(company.phone)} | {_esc(company.email)}</p>
        {'<p>License: ' + _esc(company.license_number) + '</p>' if company.license_number else ''}
    </div>
    <div class="proposal-meta">
        <h2>PROPOSAL</h2>
        <p><strong>Date:</strong> {proposal_date.strftime('%B %d, %Y')}</p>
        <p><strong>Valid Until:</strong> {valid_until.strftime('%B %d, %Y')}</p>
        <p><strong>Project ID:</strong> {_esc(project.project_id)}</p>
    </div>
</div>

<!-- PROJECT INFO -->
<div class="project-box">
    <h3>{_esc(project.project_name)}</h3>
    <div class="project-grid">
        <div><span class="label">General Contractor:</span></div>
        <div class="value">{_esc(project.general_contractor) or 'TBD'}</div>
        <div><span class="label">Contact:</span></div>
        <div class="value">{_esc(project.gc_contact_name)} - {_esc(project.gc_contact_email)}</div>
        <div><span class="label">Project Location:</span></div>
        <div class="value">{_esc(project.project_address)}, {_esc(project.project_city)}, {_esc(project.project_state)}</div>
        <div><span class="label">Project Type:</span></div>
        <div class="value">{_esc(project.project_type)}</div>
        <div><span class="label">Bid Due:</span></div>
        <div class="value">{_esc(project.bid_due_date or 'TBD')} {_esc(project.bid_due_time or '')}</div>
        <div><span class="label">Building Info:</span></div>
        <div class="value">{takeoff.story_count} stories, {takeoff.building_footprint_sf:,.0f} SF footprint</div>
    </div>
</div>

<!-- SCOPE OF WORK -->
<h2>Scope of Work</h2>
<div class="scope">
    {''.join(f'<p>{_esc(para)}</p>' for para in scope_narrative.split(chr(10)) if para.strip())}
</div>

<!-- COST SUMMARY BY TRADE -->
<h2>Cost Summary by Trade</h2>
<table>
    <thead>
        <tr>
            <th>Trade</th>
            <th>Material</th>
            <th>Labor</th>
            <th>Equipment</th>
            <th>Direct Cost</th>
            <th>Overhead</th>
            <th>Profit</th>
            <th>Total</th>
        </tr>
    </thead>
    <tbody>
        {trade_rows}
    </tbody>
</table>

<!-- TOTALS -->
<div class="totals-breakdown">
    <div>
        <div class="item"><span>Total Direct Cost:</span><span class="money">${estimate.total_direct:,.2f}</span></div>
        <div class="item"><span>Total Overhead ({company.overhead_percent:.0%}):</span><span class="money">${estimate.total_overhead:,.2f}</span></div>
        <div class="item"><span>Total Profit ({company.profit_percent:.0%}):</span><span class="money">${estimate.total_profit:,.2f}</span></div>
    </div>
    <div>
        <div class="item"><span>Subtotal:</span><span class="money">${estimate.subtotal:,.2f}</span></div>
        {'<div class="item"><span>Bond (' + f'{company.bond_percent:.1%}' + '):</span><span class="money">$' + f'{estimate.bond_cost:,.2f}' + '</span></div>' if estimate.bond_cost else ''}
        {'<div class="item"><span>Sales Tax (' + f'{company.tax_rate:.1%}' + '):</span><span class="money">$' + f'{estimate.tax:,.2f}' + '</span></div>' if estimate.tax else ''}
    </div>
</div>

<div class="grand-total">
    <div class="label">TOTAL BID AMOUNT</div>
    <div class="amount">${estimate.grand_total:,.2f}</div>
    {'<div class="per-sf">$' + f'{estimate.cost_per_sf:,.2f}' + ' per SF of building footprint</div>' if estimate.cost_per_sf else ''}
</div>

<!-- DETAIL BREAKDOWN -->
{'<h2>Detailed Breakdown</h2>' + detail_section if include_detail else ''}

<!-- EXCLUSIONS -->
<h2>Exclusions</h2>
<div class="exclusions">
    <ul>
        {exclusion_items}
    </ul>
</div>

{warning_items}

<!-- TERMS -->
<div class="terms">
    <h2>Terms &amp; Conditions</h2>
    <p><strong>Payment Terms:</strong> {_esc(company.default_payment_terms)}</p>
    <p><strong>Proposal Valid:</strong> {company.proposal_validity_days} days from date of proposal</p>
    <p><strong>Warranty:</strong> {company.warranty_years} year(s) workmanship warranty from date of substantial completion</p>
    <p>This proposal is based on the plans and specifications reviewed. Any changes to scope
    will be addressed via change order. Pricing is subject to material availability at time of order.</p>
</div>

<!-- SIGNATURES -->
<div class="signature">
    <div>
        <div class="sig-block">
            <div class="label">Submitted By</div>
            <p><strong>{_esc(company.name)}</strong></p>
        </div>
    </div>
    <div>
        <div class="sig-block">
            <div class="label">Accepted By (Signature / Date)</div>
            <p>&nbsp;</p>
        </div>
    </div>
</div>

<div class="footer">
    <p>Generated by Envelope Estimator Agent |
    Takeoff confidence: {takeoff.confidence_score:.0%} |
    Validation variance: {takeoff.validation_variance_pct:.1f}%</p>
</div>

</body>
</html>"""

        return html

    # ------------------------------------------------------------------
    # JSON summary
    # ------------------------------------------------------------------

    def _build_json_summary(
        self,
        project: ProjectInfo,
        takeoff: TakeoffResult,
        estimate: EstimateResult,
        proposal_date: datetime,
        valid_until: datetime,
    ) -> dict:
        """Build a machine-readable JSON summary of the proposal."""
        return {
            "proposal_date": proposal_date.isoformat(),
            "valid_until": valid_until.isoformat(),
            "project": {
                "id": project.project_id,
                "name": project.project_name,
                "gc": project.general_contractor,
                "location": f"{project.project_city}, {project.project_state}",
                "type": project.project_type,
                "bid_due": project.bid_due_date,
            },
            "building": {
                "footprint_sf": takeoff.building_footprint_sf,
                "stories": takeoff.story_count,
                "roof_pitch": takeoff.roof_pitch,
                "gross_wall_sf": takeoff.gross_wall_area_sf,
                "net_wall_sf": takeoff.net_wall_area_sf,
            },
            "trades": [
                {
                    "name": ts.trade_name,
                    "items": len(ts.line_items),
                    "direct_cost": ts.subtotal_direct,
                    "total": ts.trade_total,
                }
                for ts in estimate.trade_summaries
            ],
            "totals": {
                "direct": estimate.total_direct,
                "overhead": estimate.total_overhead,
                "profit": estimate.total_profit,
                "bond": estimate.bond_cost,
                "tax": estimate.tax,
                "grand_total": estimate.grand_total,
                "cost_per_sf": estimate.cost_per_sf,
                "currency": estimate.currency,
            },
            "quality": {
                "confidence": takeoff.confidence_score,
                "validation_variance_pct": takeoff.validation_variance_pct,
                "warnings": takeoff.warnings,
            },
        }


def _esc(text: str) -> str:
    """HTML-escape a string."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
