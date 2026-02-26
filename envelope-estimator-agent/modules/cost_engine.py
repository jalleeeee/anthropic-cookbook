"""
Cost Estimation Engine

Prices takeoff quantities using the DDC-CWICR database via Qdrant vector search.

Flow:
1. For each takeoff line item, search DDC-CWICR for matching work items
2. AI reranks results for best match
3. Apply unit price × quantity
4. Add overhead, profit, bond, tax
5. Generate cost breakdown by trade
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from config.settings import Settings
from config.trades import Trade
from modules.pdf_takeoff import TakeoffLineItem, TakeoffResult

logger = logging.getLogger(__name__)


@dataclass
class CostLineItem:
    """A priced line item."""
    trade_code: str
    trade_name: str
    component_name: str
    quantity: float
    unit: str
    unit_price: float
    extended_price: float           # quantity × unit_price
    material_cost: float = 0.0
    labor_cost: float = 0.0
    equipment_cost: float = 0.0
    ddc_rate_code: str = ""         # matched DDC-CWICR rate code
    ddc_rate_name: str = ""         # matched DDC-CWICR rate description
    match_confidence: float = 0.0
    notes: str = ""


@dataclass
class TradeCostSummary:
    """Cost summary for a single trade."""
    trade_code: str
    trade_name: str
    line_items: list[CostLineItem]
    subtotal_material: float = 0.0
    subtotal_labor: float = 0.0
    subtotal_equipment: float = 0.0
    subtotal_direct: float = 0.0
    overhead: float = 0.0
    profit: float = 0.0
    trade_total: float = 0.0


@dataclass
class EstimateResult:
    """Complete project cost estimate."""
    project_id: str
    trade_summaries: list[TradeCostSummary]
    total_material: float = 0.0
    total_labor: float = 0.0
    total_equipment: float = 0.0
    total_direct: float = 0.0
    total_overhead: float = 0.0
    total_profit: float = 0.0
    subtotal: float = 0.0
    bond_cost: float = 0.0
    tax: float = 0.0
    grand_total: float = 0.0
    cost_per_sf: float = 0.0        # $/SF of building footprint
    currency: str = "USD"
    warnings: list[str] = field(default_factory=list)


class CostEngine:
    """Prices takeoff quantities using DDC-CWICR database."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic.api_key)
        self._qdrant_client = None
        self._openai_client = None

    @property
    def qdrant(self):
        if self._qdrant_client is None:
            try:
                from qdrant_client import QdrantClient
                self._qdrant_client = QdrantClient(
                    host=self.settings.qdrant.host,
                    port=self.settings.qdrant.port,
                )
            except ImportError:
                logger.warning(
                    "qdrant-client not installed. "
                    "Install with: pip install qdrant-client"
                )
            except Exception as e:
                logger.warning(f"Cannot connect to Qdrant: {e}")
        return self._qdrant_client

    @property
    def openai(self):
        if self._openai_client is None:
            try:
                import openai
                self._openai_client = openai.OpenAI(
                    api_key=self.settings.openai.api_key
                )
            except ImportError:
                logger.warning(
                    "openai not installed. "
                    "Install with: pip install openai"
                )
        return self._openai_client

    def estimate(
        self,
        takeoff: TakeoffResult,
        trades: list[Trade],
    ) -> EstimateResult:
        """Price all takeoff line items and produce a complete estimate."""

        result = EstimateResult(
            project_id=takeoff.project_id,
            trade_summaries=[],
            currency=self.settings.currency,
        )

        # Group takeoff line items by trade
        items_by_trade: dict[str, list[TakeoffLineItem]] = {}
        for item in takeoff.line_items:
            items_by_trade.setdefault(item.trade_code, []).append(item)

        # Price each trade
        for trade in trades:
            trade_items = items_by_trade.get(trade.code, [])
            if not trade_items:
                continue

            cost_items = []
            for takeoff_item in trade_items:
                cost_item = self._price_line_item(takeoff_item, trade)
                cost_items.append(cost_item)

            # Compute trade summary
            summary = self._compute_trade_summary(trade, cost_items)
            result.trade_summaries.append(summary)

        # Compute project totals
        self._compute_project_totals(result, takeoff)

        logger.info(
            f"Estimate complete: {result.grand_total:,.2f} {result.currency} "
            f"({len(result.trade_summaries)} trades)"
        )

        return result

    # ------------------------------------------------------------------
    # Line item pricing
    # ------------------------------------------------------------------

    def _price_line_item(
        self, takeoff_item: TakeoffLineItem, trade: Trade
    ) -> CostLineItem:
        """Price a single takeoff line item using DDC-CWICR."""

        search_query = f"{trade.name} {takeoff_item.component_name}"

        # Find matching component for search terms
        comp = None
        for c in trade.components:
            if c.name == takeoff_item.component_name:
                comp = c
                break

        search_terms = comp.search_terms if comp else [search_query]

        # Try Qdrant vector search first
        ddc_match = self._search_ddc_cwicr(search_terms, search_query)

        if ddc_match:
            unit_price = ddc_match.get("total_cost_per_position", 0)
            material_cost = ddc_match.get("total_material_cost", 0)
            labor_cost = ddc_match.get("total_labor_cost", 0)
            equipment_cost = ddc_match.get("total_machinery_cost", 0)
            rate_code = ddc_match.get("rate_code", "")
            rate_name = ddc_match.get("rate_original_name", "")
            confidence = ddc_match.get("_match_score", 0.5)

            # If DDC price is per different unit, use AI to convert
            ddc_unit = ddc_match.get("rate_unit", "")
            if ddc_unit and ddc_unit != takeoff_item.unit:
                unit_price = self._convert_unit_price(
                    unit_price, ddc_unit, takeoff_item.unit, search_query
                )
        else:
            # Fallback: use Claude to estimate pricing
            pricing = self._ai_estimate_pricing(
                trade.name, takeoff_item.component_name, takeoff_item.unit
            )
            unit_price = pricing.get("unit_price", 0)
            material_cost = pricing.get("material_per_unit", 0)
            labor_cost = pricing.get("labor_per_unit", 0)
            equipment_cost = pricing.get("equipment_per_unit", 0)
            rate_code = "AI-EST"
            rate_name = pricing.get("description", search_query)
            confidence = 0.4

        extended = round(takeoff_item.adjusted_quantity * unit_price, 2)

        return CostLineItem(
            trade_code=takeoff_item.trade_code,
            trade_name=takeoff_item.trade_name,
            component_name=takeoff_item.component_name,
            quantity=takeoff_item.adjusted_quantity,
            unit=takeoff_item.unit,
            unit_price=round(unit_price, 2),
            extended_price=extended,
            material_cost=round(
                takeoff_item.adjusted_quantity * material_cost, 2
            ),
            labor_cost=round(
                takeoff_item.adjusted_quantity * labor_cost, 2
            ),
            equipment_cost=round(
                takeoff_item.adjusted_quantity * equipment_cost, 2
            ),
            ddc_rate_code=rate_code,
            ddc_rate_name=rate_name,
            match_confidence=confidence,
        )

    # ------------------------------------------------------------------
    # DDC-CWICR vector search
    # ------------------------------------------------------------------

    def _search_ddc_cwicr(
        self, search_terms: list[str], fallback_query: str
    ) -> Optional[dict]:
        """Search DDC-CWICR via Qdrant for best matching work item."""

        if not self.qdrant or not self.openai:
            logger.debug("Qdrant/OpenAI not available, using AI estimation")
            return None

        collection = self.settings.qdrant.collection
        best_match = None
        best_score = 0.0

        for term in search_terms[:3]:  # try top 3 search terms
            try:
                # Generate embedding
                embedding_response = self.openai.embeddings.create(
                    model=self.settings.openai.embedding_model,
                    input=term,
                )
                vector = embedding_response.data[0].embedding

                # Search Qdrant
                results = self.qdrant.search(
                    collection_name=collection,
                    query_vector=vector,
                    limit=self.settings.qdrant.top_k,
                )

                for hit in results:
                    if hit.score > best_score:
                        best_score = hit.score
                        payload = hit.payload or {}
                        payload["_match_score"] = hit.score
                        best_match = payload

            except Exception as e:
                logger.debug(f"Qdrant search failed for '{term}': {e}")
                continue

        if best_match and best_score > 0.5:
            # AI rerank: verify this is actually a good match
            reranked = self._ai_rerank(fallback_query, best_match)
            if reranked:
                return best_match

        return best_match if best_match and best_score > 0.7 else None

    def _ai_rerank(self, query: str, match: dict) -> bool:
        """Use Claude to verify a DDC-CWICR match is appropriate."""
        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_fast,
                max_tokens=100,
                messages=[{
                    "role": "user",
                    "content": f"""Is this DDC-CWICR database entry a good match
for pricing "{query}"?

Database entry:
- Code: {match.get('rate_code', '')}
- Name: {match.get('rate_original_name', '')}
- Unit: {match.get('rate_unit', '')}
- Cost: {match.get('total_cost_per_position', '')}

Answer YES or NO only.""",
                }],
            )
            return "yes" in response.content[0].text.strip().lower()
        except Exception:
            return True  # assume match is OK if rerank fails

    # ------------------------------------------------------------------
    # AI fallback pricing
    # ------------------------------------------------------------------

    def _ai_estimate_pricing(
        self, trade_name: str, component_name: str, unit: str
    ) -> dict:
        """Use Claude to estimate pricing when DDC-CWICR has no match."""
        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_fast,
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": f"""You are a construction cost estimator.
Provide a reasonable US market price estimate for:

Trade: {trade_name}
Component: {component_name}
Unit: per {unit}

Return JSON:
{{
  "unit_price": 0.00,
  "material_per_unit": 0.00,
  "labor_per_unit": 0.00,
  "equipment_per_unit": 0.00,
  "description": "",
  "source": "AI estimate - current US market average"
}}

Use current US commercial construction pricing.
Return ONLY the JSON object.""",
                }],
            )
            text = response.content[0].text.strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"AI pricing failed: {e}")

        return {"unit_price": 0, "description": f"{trade_name} - {component_name}"}

    # ------------------------------------------------------------------
    # Unit conversion
    # ------------------------------------------------------------------

    def _convert_unit_price(
        self,
        price: float,
        from_unit: str,
        to_unit: str,
        context: str,
    ) -> float:
        """Convert unit price between different units of measure."""
        # Common conversions
        conversions = {
            ("m²", "SF"): 0.0929,     # 1 SF = 0.0929 m²
            ("m", "LF"): 0.3048,       # 1 LF = 0.3048 m
            ("m³", "CF"): 0.0283,      # 1 CF = 0.0283 m³
        }

        key = (from_unit, to_unit)
        if key in conversions:
            return price * conversions[key]

        # Reverse
        reverse_key = (to_unit, from_unit)
        if reverse_key in conversions:
            return price / conversions[reverse_key]

        # AI fallback for complex conversions
        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_fast,
                max_tokens=100,
                messages=[{
                    "role": "user",
                    "content": f"""Convert construction pricing:
Price: {price} per {from_unit}
Convert to: per {to_unit}
Context: {context}
Return ONLY the numeric value.""",
                }],
            )
            text = response.content[0].text.strip()
            numbers = re.findall(r"[\d.]+", text)
            if numbers:
                return float(numbers[0])
        except Exception:
            pass

        return price  # return unconverted if all else fails

    # ------------------------------------------------------------------
    # Trade and project totals
    # ------------------------------------------------------------------

    def _compute_trade_summary(
        self, trade: Trade, cost_items: list[CostLineItem]
    ) -> TradeCostSummary:
        """Sum up costs for a trade and apply overhead/profit."""
        company = self.settings.company

        subtotal_material = sum(i.material_cost for i in cost_items)
        subtotal_labor = sum(i.labor_cost for i in cost_items)
        subtotal_equipment = sum(i.equipment_cost for i in cost_items)
        subtotal_direct = sum(i.extended_price for i in cost_items)

        overhead = subtotal_direct * company.overhead_percent
        profit = (subtotal_direct + overhead) * company.profit_percent

        return TradeCostSummary(
            trade_code=trade.code,
            trade_name=trade.name,
            line_items=cost_items,
            subtotal_material=round(subtotal_material, 2),
            subtotal_labor=round(subtotal_labor, 2),
            subtotal_equipment=round(subtotal_equipment, 2),
            subtotal_direct=round(subtotal_direct, 2),
            overhead=round(overhead, 2),
            profit=round(profit, 2),
            trade_total=round(subtotal_direct + overhead + profit, 2),
        )

    def _compute_project_totals(
        self, result: EstimateResult, takeoff: TakeoffResult
    ):
        """Compute project-level totals."""
        company = self.settings.company

        result.total_material = sum(
            s.subtotal_material for s in result.trade_summaries
        )
        result.total_labor = sum(
            s.subtotal_labor for s in result.trade_summaries
        )
        result.total_equipment = sum(
            s.subtotal_equipment for s in result.trade_summaries
        )
        result.total_direct = sum(
            s.subtotal_direct for s in result.trade_summaries
        )
        result.total_overhead = sum(
            s.overhead for s in result.trade_summaries
        )
        result.total_profit = sum(
            s.profit for s in result.trade_summaries
        )
        result.subtotal = sum(
            s.trade_total for s in result.trade_summaries
        )

        # Bond
        result.bond_cost = round(
            result.subtotal * company.bond_percent, 2
        )

        # Tax on materials
        result.tax = round(
            result.total_material * company.tax_rate, 2
        )

        result.grand_total = round(
            result.subtotal + result.bond_cost + result.tax, 2
        )

        # Cost per SF
        if takeoff.building_footprint_sf > 0:
            result.cost_per_sf = round(
                result.grand_total / takeoff.building_footprint_sf, 2
            )
