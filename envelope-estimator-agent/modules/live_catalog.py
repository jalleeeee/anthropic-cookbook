"""
Live Cost Catalog — Labor + Material Pricing from DDC-CWICR

Provides a live, searchable cost catalog backed by the DDC-CWICR database
(55,719 work items) served via Qdrant vector search.

Two catalogs in one:
1. LABOR CATALOG — Crew compositions, labor hours, wage rates per work item
2. MATERIAL CATALOG — Material unit costs, supplier pricing, quantity breaks

These catalogs feed:
- The Cost Engine (for detailed line-item pricing)
- The ROM Estimator (for quick preliminary estimates)
- The AIA G703 Schedule of Values (unit prices per CSI division)
- The Deductive Engine (to upgrade ratio-derived quantities into priced estimates)

DDC-CWICR fields used:
  Labor:  workers_count, engineers_count, machinists_count, labor_hours,
          labor_cost, personnel_codes, wages
  Material: resource_code, resource_name, resource_unit, resource_quantity,
            resource_price_per_unit_eur_current, resource_cost_eur
  Work item: rate_code, rate_original_name, rate_unit, total_cost_per_position

The catalog supports "live" updates by re-querying Qdrant on each request,
so changes to the underlying vector DB (new pricing, regional adjustments)
are immediately reflected.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from config.settings import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Catalog data structures
# ---------------------------------------------------------------------------

@dataclass
class LaborRate:
    """A single labor rate entry from DDC-CWICR."""
    rate_code: str
    description: str
    unit: str                       # unit of work (e.g., m², LF, SF, EA)
    crew_size: int = 0              # total workers on crew
    workers_count: int = 0          # general laborers
    engineers_count: int = 0        # skilled trades / engineers
    machinists_count: int = 0       # equipment operators
    labor_hours_per_unit: float = 0.0
    labor_cost_per_unit: float = 0.0   # in local currency
    wage_rate_per_hour: float = 0.0
    daily_output: float = 0.0          # units per 8-hour day
    csi_division: str = ""
    notes: str = ""
    source: str = "DDC-CWICR"
    match_score: float = 0.0


@dataclass
class MaterialRate:
    """A single material pricing entry from DDC-CWICR."""
    resource_code: str
    resource_name: str
    unit: str                       # pricing unit (e.g., SF, LF, EA, GAL)
    unit_price: float = 0.0        # price per unit (local currency)
    supplier: str = ""
    manufacturer: str = ""
    specification: str = ""
    min_order_qty: float = 0.0
    quantity_break_price: float = 0.0  # price at volume
    category: str = ""              # e.g., "cladding", "roofing", "sealant"
    csi_division: str = ""
    notes: str = ""
    source: str = "DDC-CWICR"
    match_score: float = 0.0


@dataclass
class CatalogEntry:
    """Combined catalog entry — labor + material for a work item."""
    rate_code: str
    description: str
    csi_division: str
    unit: str
    # Total installed cost
    total_unit_price: float = 0.0
    material_unit_price: float = 0.0
    labor_unit_price: float = 0.0
    equipment_unit_price: float = 0.0
    # Breakdown
    labor: Optional[LaborRate] = None
    materials: list[MaterialRate] = field(default_factory=list)
    # Metadata
    region: str = ""
    currency: str = "USD"
    last_updated: str = ""
    source: str = "DDC-CWICR"
    match_score: float = 0.0


@dataclass
class CatalogSearchResult:
    """Result from a catalog search."""
    query: str
    entries: list[CatalogEntry] = field(default_factory=list)
    total_found: int = 0
    search_type: str = ""       # "vector", "ai_fallback", "cached"


# ---------------------------------------------------------------------------
# Default envelope catalog — static fallback when DDC-CWICR is unavailable
# ---------------------------------------------------------------------------

# These are US national average prices for common envelope work items.
# Used as fallback when Qdrant/DDC is not connected.
# Format: {description: {unit, material, labor, equipment, csi}}
DEFAULT_ENVELOPE_CATALOG = {
    # Division 06 — Sheathing
    "Exterior Sheathing OSB 7/16\"": {
        "unit": "SF", "material": 1.15, "labor": 1.35, "equipment": 0.0,
        "csi": "06 16 00",
    },
    "Exterior Sheathing Plywood 1/2\"": {
        "unit": "SF", "material": 1.55, "labor": 1.35, "equipment": 0.0,
        "csi": "06 16 00",
    },
    # Division 07 — Thermal & Moisture
    "Weather-Resistive Barrier Self-Adhered": {
        "unit": "SF", "material": 0.85, "labor": 1.00, "equipment": 0.0,
        "csi": "07 27 00",
    },
    "Weather-Resistive Barrier Fluid-Applied": {
        "unit": "SF", "material": 1.25, "labor": 0.90, "equipment": 0.15,
        "csi": "07 27 00",
    },
    "Continuous Insulation Polyiso 2\"": {
        "unit": "SF", "material": 1.30, "labor": 0.80, "equipment": 0.0,
        "csi": "07 21 13",
    },
    "Continuous Insulation XPS 2\"": {
        "unit": "SF", "material": 1.10, "labor": 0.80, "equipment": 0.0,
        "csi": "07 21 13",
    },
    "Fiber Cement Lap Siding": {
        "unit": "SF", "material": 3.50, "labor": 4.50, "equipment": 0.50,
        "csi": "07 46 23",
    },
    "Fiber Cement Panel Siding": {
        "unit": "SF", "material": 4.25, "labor": 5.00, "equipment": 0.50,
        "csi": "07 46 00",
    },
    "Vinyl Siding": {
        "unit": "SF", "material": 1.80, "labor": 2.50, "equipment": 0.0,
        "csi": "07 46 33",
    },
    "Metal Panel Siding": {
        "unit": "SF", "material": 6.00, "labor": 5.50, "equipment": 0.75,
        "csi": "07 42 00",
    },
    "Brick Veneer (modular)": {
        "unit": "SF", "material": 6.50, "labor": 12.00, "equipment": 1.50,
        "csi": "04 21 13",
    },
    "Stone Veneer Manufactured": {
        "unit": "SF", "material": 8.00, "labor": 10.00, "equipment": 0.50,
        "csi": "04 43 00",
    },
    "Stucco / EIFS": {
        "unit": "SF", "material": 4.00, "labor": 6.50, "equipment": 0.50,
        "csi": "09 24 00",
    },
    "TPO Roofing 60-mil": {
        "unit": "SQ", "material": 125.00, "labor": 180.00, "equipment": 45.00,
        "csi": "07 54 00",
    },
    "PVC Roofing 60-mil": {
        "unit": "SQ", "material": 140.00, "labor": 180.00, "equipment": 45.00,
        "csi": "07 54 00",
    },
    "EPDM Roofing 60-mil": {
        "unit": "SQ", "material": 105.00, "labor": 170.00, "equipment": 40.00,
        "csi": "07 55 00",
    },
    "Asphalt Shingles Architectural": {
        "unit": "SQ", "material": 95.00, "labor": 125.00, "equipment": 15.00,
        "csi": "07 31 00",
    },
    "Standing Seam Metal Roof": {
        "unit": "SQ", "material": 350.00, "labor": 250.00, "equipment": 50.00,
        "csi": "07 41 00",
    },
    "Roof Insulation Polyiso Tapered": {
        "unit": "SF", "material": 1.80, "labor": 1.00, "equipment": 0.0,
        "csi": "07 21 13",
    },
    "Metal Coping 24 ga.": {
        "unit": "LF", "material": 12.00, "labor": 10.00, "equipment": 0.0,
        "csi": "07 71 00",
    },
    "Aluminum Gutter 6\" K-Style": {
        "unit": "LF", "material": 3.50, "labor": 5.00, "equipment": 0.0,
        "csi": "07 63 00",
    },
    "Aluminum Downspout 3×4\"": {
        "unit": "LF", "material": 2.50, "labor": 3.50, "equipment": 0.0,
        "csi": "07 63 00",
    },
    "Downspout Elbows": {
        "unit": "EA", "material": 4.50, "labor": 6.00, "equipment": 0.0,
        "csi": "07 63 00",
    },
    "Internal Roof Drain": {
        "unit": "EA", "material": 350.00, "labor": 500.00, "equipment": 0.0,
        "csi": "07 63 00",
    },
    "Overflow Scupper": {
        "unit": "EA", "material": 150.00, "labor": 200.00, "equipment": 0.0,
        "csi": "07 63 00",
    },
    "Flashing Step/Counter/Through-Wall": {
        "unit": "LF", "material": 4.50, "labor": 7.50, "equipment": 0.0,
        "csi": "07 62 00",
    },
    "Perimeter Sealant (backer rod + caulk)": {
        "unit": "LF", "material": 1.00, "labor": 2.50, "equipment": 0.0,
        "csi": "07 92 00",
    },
    "Control Joint Sealant": {
        "unit": "LF", "material": 1.50, "labor": 2.50, "equipment": 0.0,
        "csi": "07 92 00",
    },
    "Balcony Deck Waterproofing Fluid-Applied": {
        "unit": "SF", "material": 3.50, "labor": 4.50, "equipment": 0.0,
        "csi": "07 14 00",
    },
    "Foundation Dampproofing": {
        "unit": "SF", "material": 1.00, "labor": 2.00, "equipment": 0.0,
        "csi": "07 11 00",
    },
    "Podium Deck Waterproofing": {
        "unit": "SF", "material": 5.00, "labor": 7.00, "equipment": 0.0,
        "csi": "07 13 00",
    },
    # Division 08 — Openings
    "Vinyl Window Double-Hung (avg size)": {
        "unit": "EA", "material": 250.00, "labor": 200.00, "equipment": 0.0,
        "csi": "08 53 00",
    },
    "Aluminum Window Fixed (avg size)": {
        "unit": "EA", "material": 300.00, "labor": 200.00, "equipment": 0.0,
        "csi": "08 51 00",
    },
    "Sliding Glass Door 6'": {
        "unit": "EA", "material": 650.00, "labor": 350.00, "equipment": 0.0,
        "csi": "08 51 00",
    },
    "Exterior Entry Door HM Frame": {
        "unit": "EA", "material": 450.00, "labor": 300.00, "equipment": 0.0,
        "csi": "08 11 00",
    },
    "Storefront System": {
        "unit": "SF", "material": 25.00, "labor": 20.00, "equipment": 2.00,
        "csi": "08 41 00",
    },
    # Division 05 — Railing
    "Balcony Railing Aluminum": {
        "unit": "LF", "material": 35.00, "labor": 45.00, "equipment": 5.00,
        "csi": "05 73 00",
    },
    "Corridor / Breezeway Railing": {
        "unit": "LF", "material": 30.00, "labor": 40.00, "equipment": 5.00,
        "csi": "05 52 00",
    },
    # Trim
    "Soffit Fiber Cement Vented": {
        "unit": "SF", "material": 2.50, "labor": 3.50, "equipment": 0.0,
        "csi": "07 46 00",
    },
    "Fascia Board Fiber Cement": {
        "unit": "LF", "material": 3.00, "labor": 5.00, "equipment": 0.0,
        "csi": "07 46 00",
    },
    "J-Channel": {
        "unit": "LF", "material": 0.75, "labor": 1.75, "equipment": 0.0,
        "csi": "07 46 00",
    },
    "Corner Trim Inside + Outside": {
        "unit": "LF", "material": 1.50, "labor": 2.50, "equipment": 0.0,
        "csi": "07 46 00",
    },
    "Band Board / Floor Transition": {
        "unit": "LF", "material": 2.50, "labor": 4.00, "equipment": 0.0,
        "csi": "07 46 00",
    },
}


# ---------------------------------------------------------------------------
# Mapping from deductive engine SOV descriptions → catalog keys
# ---------------------------------------------------------------------------

SOV_TO_CATALOG_MAP = {
    "Exterior Sheathing": "Exterior Sheathing OSB 7/16\"",
    "Weather-Resistive Barrier / Air Barrier": "Weather-Resistive Barrier Self-Adhered",
    "Continuous Insulation (rigid)": "Continuous Insulation Polyiso 2\"",
    "Primary Cladding": "Fiber Cement Lap Siding",
    "Accent Cladding": "Fiber Cement Panel Siding",
    "Soffit": "Soffit Fiber Cement Vented",
    "Fascia": "Fascia Board Fiber Cement",
    "J-Channel & Starter": "J-Channel",
    "Corner Trim": "Corner Trim Inside + Outside",
    "Band Board / Floor Line Transition": "Band Board / Floor Transition",
    "Roofing": "TPO Roofing 60-mil",
    "Roof Insulation": "Roof Insulation Polyiso Tapered",
    "Metal Coping": "Metal Coping 24 ga.",
    "Flashing & Sheet Metal": "Flashing Step/Counter/Through-Wall",
    "Gutters": "Aluminum Gutter 6\" K-Style",
    "Downspouts": "Aluminum Downspout 3×4\"",
    "Internal Roof Drains": "Internal Roof Drain",
    "Overflow Scuppers": "Overflow Scupper",
    "Perimeter Sealant (windows/doors)": "Perimeter Sealant (backer rod + caulk)",
    "Control Joint Sealant": "Control Joint Sealant",
    "Balcony Deck Waterproofing": "Balcony Deck Waterproofing Fluid-Applied",
    "Foundation Dampproofing": "Foundation Dampproofing",
    "Podium Deck Waterproofing": "Podium Deck Waterproofing",
    "Windows (supply & install)": "Vinyl Window Double-Hung (avg size)",
    "Sliding Glass Doors": "Sliding Glass Door 6'",
    "Exterior Doors": "Exterior Entry Door HM Frame",
    "Balcony Railing": "Balcony Railing Aluminum",
    "Corridor / Breezeway Railing": "Corridor / Breezeway Railing",
}


# ---------------------------------------------------------------------------
# The Live Catalog
# ---------------------------------------------------------------------------

class LiveCatalog:
    """Unified labor + material catalog backed by DDC-CWICR via Qdrant.

    When Qdrant is available, queries the live database for real-time pricing.
    When offline, falls back to the built-in DEFAULT_ENVELOPE_CATALOG with
    US national average prices.

    Usage:
        catalog = LiveCatalog(settings)

        # Search for specific work items
        result = catalog.search("fiber cement siding installation")

        # Get pricing for a specific component
        entry = catalog.get_installed_price("Fiber Cement Lap Siding", "SF")

        # Get full catalog for a CSI division
        entries = catalog.browse_division("07 46 00")

        # Price a deductive engine SOV
        priced = catalog.price_schedule_of_values(sov_items)
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic.api_key)
        self._qdrant_client = None
        self._openai_client = None
        self._cache: dict[str, CatalogEntry] = {}

    @property
    def qdrant(self):
        if self._qdrant_client is None:
            try:
                from qdrant_client import QdrantClient
                self._qdrant_client = QdrantClient(
                    host=self.settings.qdrant.host,
                    port=self.settings.qdrant.port,
                )
            except (ImportError, Exception) as e:
                logger.debug(f"Qdrant not available: {e}")
        return self._qdrant_client

    @property
    def openai(self):
        if self._openai_client is None:
            try:
                import openai
                self._openai_client = openai.OpenAI(
                    api_key=self.settings.openai.api_key
                )
            except (ImportError, Exception) as e:
                logger.debug(f"OpenAI not available: {e}")
        return self._openai_client

    # ------------------------------------------------------------------
    # Core search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 5,
        csi_filter: str = "",
        catalog_type: str = "all",
    ) -> CatalogSearchResult:
        """Search the live catalog for work items matching a query.

        Args:
            query: Natural language search (e.g., "fiber cement siding install")
            limit: Max results to return
            csi_filter: Optional CSI division filter (e.g., "07 46")
            catalog_type: "labor", "material", or "all"

        Returns:
            CatalogSearchResult with matching entries
        """
        result = CatalogSearchResult(query=query)

        # Try Qdrant first
        if self.qdrant and self.openai:
            entries = self._search_qdrant(query, limit, csi_filter)
            if entries:
                result.entries = entries
                result.total_found = len(entries)
                result.search_type = "vector"
                return result

        # Fallback: search default catalog
        entries = self._search_default_catalog(query, limit, csi_filter)
        result.entries = entries
        result.total_found = len(entries)
        result.search_type = "default_catalog"
        return result

    def get_installed_price(
        self, description: str, unit: str
    ) -> Optional[CatalogEntry]:
        """Get the total installed unit price for a specific component.

        Checks cache first, then Qdrant, then default catalog.
        """
        cache_key = f"{description}|{unit}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Search for it
        result = self.search(description, limit=1)
        if result.entries:
            entry = result.entries[0]
            self._cache[cache_key] = entry
            return entry

        # Try default catalog exact match
        for desc, data in DEFAULT_ENVELOPE_CATALOG.items():
            if desc.lower() in description.lower() or description.lower() in desc.lower():
                entry = self._default_to_entry(desc, data)
                self._cache[cache_key] = entry
                return entry

        return None

    def browse_division(self, csi_division: str) -> list[CatalogEntry]:
        """Get all catalog entries for a CSI division."""
        entries = []
        for desc, data in DEFAULT_ENVELOPE_CATALOG.items():
            if data["csi"].startswith(csi_division[:5]):
                entries.append(self._default_to_entry(desc, data))
        return entries

    def get_labor_rates(self, trade_query: str) -> list[LaborRate]:
        """Get labor rates for a specific trade/work item."""
        result = self.search(trade_query, limit=5, catalog_type="labor")
        return [e.labor for e in result.entries if e.labor]

    def get_material_prices(self, material_query: str) -> list[MaterialRate]:
        """Get material prices for a specific product."""
        result = self.search(material_query, limit=5, catalog_type="material")
        materials = []
        for e in result.entries:
            materials.extend(e.materials)
        return materials

    # ------------------------------------------------------------------
    # Price a Schedule of Values using live catalog
    # ------------------------------------------------------------------

    def price_schedule_of_values(
        self, sov_items: list[dict]
    ) -> list[dict]:
        """Re-price SOV items using the live catalog.

        Takes the deductive engine's SOV output (with default prices) and
        replaces the unit prices with live catalog data.

        Args:
            sov_items: List of SOV item dicts from DeductiveEngine

        Returns:
            Updated SOV items with live pricing and source attribution
        """
        priced = []
        for item in sov_items:
            desc = item.get("description", "")
            qty = item.get("qty", 0)
            unit = item.get("unit", "")

            # Try to find a catalog match
            # Strip building ID prefix ("Building A — ") from description
            clean_desc = re.sub(r'^.*? — ', '', desc)

            # Check SOV-to-catalog mapping first
            catalog_key = None
            for sov_pattern, cat_key in SOV_TO_CATALOG_MAP.items():
                if sov_pattern.lower() in clean_desc.lower():
                    catalog_key = cat_key
                    break

            entry = None
            if catalog_key:
                entry = self.get_installed_price(catalog_key, unit)

            if not entry:
                entry = self.get_installed_price(clean_desc, unit)

            if entry:
                unit_price = entry.total_unit_price
                material_price = entry.material_unit_price
                labor_price = entry.labor_unit_price
                source = entry.source
            else:
                # Keep default pricing
                unit_price = item.get("unit_price", 0)
                material_price = unit_price * 0.45  # typical 45/55 M/L split
                labor_price = unit_price * 0.55
                source = "default"

            priced.append({
                **item,
                "unit_price": round(unit_price, 2),
                "value": round(qty * unit_price, 2),
                "material_cost": round(qty * material_price, 2),
                "labor_cost": round(qty * labor_price, 2),
                "pricing_source": source,
            })

        return priced

    # ------------------------------------------------------------------
    # Qdrant vector search
    # ------------------------------------------------------------------

    def _search_qdrant(
        self, query: str, limit: int, csi_filter: str = ""
    ) -> list[CatalogEntry]:
        """Search DDC-CWICR via Qdrant vector similarity."""
        try:
            embedding_response = self.openai.embeddings.create(
                model=self.settings.openai.embedding_model,
                input=query,
            )
            vector = embedding_response.data[0].embedding

            results = self.qdrant.search(
                collection_name=self.settings.qdrant.collection,
                query_vector=vector,
                limit=limit,
            )

            entries = []
            for hit in results:
                if hit.score < 0.4:
                    continue
                payload = hit.payload or {}

                # Build labor rate
                labor = LaborRate(
                    rate_code=payload.get("rate_code", ""),
                    description=payload.get("rate_original_name", ""),
                    unit=payload.get("rate_unit", ""),
                    workers_count=int(payload.get("workers_count", 0) or 0),
                    engineers_count=int(payload.get("engineers_count", 0) or 0),
                    machinists_count=int(payload.get("machinists_count", 0) or 0),
                    labor_hours_per_unit=float(
                        payload.get("labor_hours", 0) or 0
                    ),
                    labor_cost_per_unit=float(
                        payload.get("total_labor_cost", 0) or 0
                    ),
                    match_score=hit.score,
                )
                labor.crew_size = (
                    labor.workers_count
                    + labor.engineers_count
                    + labor.machinists_count
                )

                # Build material rate
                materials = []
                if payload.get("resource_name"):
                    materials.append(MaterialRate(
                        resource_code=payload.get("resource_code", ""),
                        resource_name=payload.get("resource_name", ""),
                        unit=payload.get("resource_unit", ""),
                        unit_price=float(
                            payload.get("resource_price_per_unit_eur_current", 0) or 0
                        ),
                        match_score=hit.score,
                    ))

                total_cost = float(
                    payload.get("total_cost_per_position", 0) or 0
                )
                material_cost = float(
                    payload.get("total_material_cost", 0) or 0
                )
                labor_cost_total = float(
                    payload.get("total_labor_cost", 0) or 0
                )
                equipment_cost = float(
                    payload.get("total_machinery_cost", 0) or 0
                )

                entry = CatalogEntry(
                    rate_code=payload.get("rate_code", ""),
                    description=payload.get("rate_original_name", ""),
                    csi_division=payload.get("csi_division", ""),
                    unit=payload.get("rate_unit", ""),
                    total_unit_price=total_cost,
                    material_unit_price=material_cost,
                    labor_unit_price=labor_cost_total,
                    equipment_unit_price=equipment_cost,
                    labor=labor,
                    materials=materials,
                    region=self.settings.region,
                    currency=self.settings.currency,
                    source="DDC-CWICR (live)",
                    match_score=hit.score,
                )
                entries.append(entry)

            return entries

        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Default catalog search
    # ------------------------------------------------------------------

    def _search_default_catalog(
        self, query: str, limit: int, csi_filter: str = ""
    ) -> list[CatalogEntry]:
        """Search the built-in default catalog by keyword matching."""
        query_lower = query.lower()
        scored = []

        for desc, data in DEFAULT_ENVELOPE_CATALOG.items():
            if csi_filter and not data["csi"].startswith(csi_filter[:5]):
                continue

            # Simple keyword scoring
            score = 0.0
            desc_lower = desc.lower()
            words = query_lower.split()
            for word in words:
                if word in desc_lower:
                    score += 1.0 / len(words)

            if score > 0:
                scored.append((score, desc, data))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            self._default_to_entry(desc, data)
            for score, desc, data in scored[:limit]
        ]

    def _default_to_entry(self, desc: str, data: dict) -> CatalogEntry:
        """Convert a default catalog row into a CatalogEntry."""
        material = data.get("material", 0)
        labor = data.get("labor", 0)
        equipment = data.get("equipment", 0)
        total = material + labor + equipment

        labor_rate = LaborRate(
            rate_code="DEFAULT",
            description=desc,
            unit=data["unit"],
            labor_cost_per_unit=labor,
            source="US National Average",
        )

        material_rate = MaterialRate(
            resource_code="DEFAULT",
            resource_name=desc,
            unit=data["unit"],
            unit_price=material,
            source="US National Average",
        )

        return CatalogEntry(
            rate_code="DEFAULT",
            description=desc,
            csi_division=data.get("csi", ""),
            unit=data["unit"],
            total_unit_price=total,
            material_unit_price=material,
            labor_unit_price=labor,
            equipment_unit_price=equipment,
            labor=labor_rate,
            materials=[material_rate],
            region="US",
            currency="USD",
            source="US National Average",
            match_score=1.0,
        )

    # ------------------------------------------------------------------
    # AI-assisted catalog enrichment
    # ------------------------------------------------------------------

    def ai_estimate_price(
        self, description: str, unit: str, region: str = "US"
    ) -> CatalogEntry:
        """Use Claude to estimate pricing when no catalog match exists."""
        try:
            response = self.client.messages.create(
                model=self.settings.anthropic.model_fast,
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": f"""You are a construction cost database. Provide current
{region} market pricing for:

Item: {description}
Unit: per {unit}

Return JSON:
{{
  "total_unit_price": 0.00,
  "material_per_unit": 0.00,
  "labor_per_unit": 0.00,
  "equipment_per_unit": 0.00,
  "crew_size": 0,
  "daily_output": 0,
  "notes": ""
}}

Use current commercial construction pricing. Return ONLY JSON.""",
                }],
            )
            text = response.content[0].text.strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return CatalogEntry(
                    rate_code="AI-EST",
                    description=description,
                    csi_division="",
                    unit=unit,
                    total_unit_price=float(data.get("total_unit_price", 0)),
                    material_unit_price=float(data.get("material_per_unit", 0)),
                    labor_unit_price=float(data.get("labor_per_unit", 0)),
                    equipment_unit_price=float(data.get("equipment_per_unit", 0)),
                    source="AI Estimate",
                )
        except Exception as e:
            logger.error(f"AI price estimation failed: {e}")

        return CatalogEntry(
            rate_code="UNKNOWN",
            description=description,
            csi_division="",
            unit=unit,
            source="No data",
        )
