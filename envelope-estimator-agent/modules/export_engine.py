"""
Export Engine — Structured Excel/PDF/CSV output for takeoff results.

Clones BEAM AI's clean Excel output format:
- Trade-organized line items
- Quantity, unit, description columns
- Ready-to-price format (user adds their own rates)
- Bid-ready structure

Our enhancement over BEAM AI:
  BEAM exports quantities only.
  We export quantities + live pricing + schedule of values.

Supported export formats:
  1. Excel (.xlsx) — Structured workbook with multiple sheets
  2. CSV — Simple flat export
  3. JSON — API-ready structured data
  4. PDF — Formatted proposal/report (via proposal_gen)
"""

import csv
import io
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Export data structures
# ---------------------------------------------------------------------------

@dataclass
class ExportLineItem:
    """A single line item for export."""
    item_number: str = ""
    trade: str = ""
    csi_division: str = ""
    description: str = ""
    quantity: float = 0.0
    unit: str = ""
    unit_price: float = 0.0
    material_cost: float = 0.0
    labor_cost: float = 0.0
    equipment_cost: float = 0.0
    extended_price: float = 0.0
    notes: str = ""


@dataclass
class ExportSheet:
    """A single sheet/tab in the export workbook."""
    name: str = ""
    items: list[ExportLineItem] = field(default_factory=list)
    subtotal: float = 0.0


@dataclass
class ExportPackage:
    """Complete export package ready for download."""
    project_name: str = ""
    building_id: str = ""
    export_date: str = ""
    # Sheets
    sheets: list[ExportSheet] = field(default_factory=list)
    # Summary
    total_material: float = 0.0
    total_labor: float = 0.0
    total_equipment: float = 0.0
    subtotal_direct: float = 0.0
    overhead: float = 0.0
    profit: float = 0.0
    tax: float = 0.0
    grand_total: float = 0.0


# ---------------------------------------------------------------------------
# Export Engine
# ---------------------------------------------------------------------------

class ExportEngine:
    """Generates structured exports from takeoff/estimate results.

    Produces BEAM-AI-style clean Excel output with our pricing added.

    Usage:
        engine = ExportEngine()

        # From ROM estimate
        package = engine.from_rom_estimate(rom_estimate)

        # From measurement report
        package = engine.from_measurement_report(report)

        # Export to CSV
        csv_content = engine.to_csv(package)

        # Export to Excel-compatible format
        xlsx_rows = engine.to_xlsx_data(package)
    """

    def from_rom_estimate(self, rom_dict: dict) -> ExportPackage:
        """Build export package from a ROM estimate dict."""
        package = ExportPackage(
            project_name=rom_dict.get("project_name", ""),
        )

        summary = rom_dict.get("summary", {})
        package.total_material = summary.get("total_material", 0)
        package.total_labor = summary.get("total_labor", 0)
        package.total_equipment = summary.get("total_equipment", 0)
        package.grand_total = summary.get("grand_total", 0)

        for bldg in rom_dict.get("buildings", []):
            sheet = ExportSheet(
                name=bldg.get("building_id", "Building"),
            )

            for li in bldg.get("line_items", []):
                sheet.items.append(ExportLineItem(
                    item_number=li.get("item", ""),
                    csi_division=li.get("csi", ""),
                    description=li.get("description", ""),
                    quantity=li.get("qty", 0),
                    unit=li.get("unit", ""),
                    unit_price=li.get("unit_price", 0),
                    material_cost=li.get("material", 0),
                    labor_cost=li.get("labor", 0),
                    equipment_cost=li.get("equipment", 0),
                    extended_price=li.get("extended", 0),
                ))

            totals = bldg.get("totals", {})
            sheet.subtotal = totals.get("grand_total", 0)
            package.sheets.append(sheet)

        return package

    def from_measurement_report(self, report_dict: dict) -> ExportPackage:
        """Build export package from a measurement report dict."""
        package = ExportPackage(
            project_name=report_dict.get("property_name", ""),
            building_id=report_dict.get("building_id", ""),
        )

        # Siding sheet
        siding = report_dict.get("siding_summary", {})
        if siding:
            areas = siding.get("areas", {})
            siding_sheet = ExportSheet(name="Siding Summary")
            siding_sheet.items.append(ExportLineItem(
                description="Facades — Siding",
                quantity=areas.get("facades", {}).get("siding", 0),
                unit="SF",
            ))
            siding_sheet.items.append(ExportLineItem(
                description="Facades — Other",
                quantity=areas.get("facades", {}).get("other", 0),
                unit="SF",
            ))
            siding_sheet.items.append(ExportLineItem(
                description="Openings — Siding",
                quantity=areas.get("openings", {}).get("siding", 0),
                unit="SF",
                notes="Deduction",
            ))
            siding_sheet.items.append(ExportLineItem(
                description="Trims — Siding",
                quantity=areas.get("trims", {}).get("siding", 0),
                unit="SF",
            ))
            package.sheets.append(siding_sheet)

        # Roof sheet
        roof = report_dict.get("roof_summary", {})
        if roof:
            roof_sheet = ExportSheet(name="Roof Summary")
            for item in roof.get("items", []):
                roof_sheet.items.append(ExportLineItem(
                    description=item.get("name", ""),
                    quantity=item.get("area_sf", 0) or item.get("count", 0),
                    unit="SF" if item.get("area_sf") else "EA",
                    notes=item.get("length", ""),
                ))
            package.sheets.append(roof_sheet)

        # Priced estimate sheet
        priced = report_dict.get("priced_estimate", {})
        if priced:
            estimate_sheet = ExportSheet(name="Priced Estimate")
            for li in priced.get("line_items", []):
                estimate_sheet.items.append(ExportLineItem(
                    csi_division=li.get("csi", ""),
                    description=li.get("description", ""),
                    quantity=li.get("qty", 0),
                    unit=li.get("unit", ""),
                    unit_price=li.get("unit_price", 0),
                    material_cost=li.get("material", 0),
                    labor_cost=li.get("labor", 0),
                    equipment_cost=li.get("equipment", 0),
                    extended_price=li.get("extended", 0),
                ))

            totals = priced.get("totals", {})
            estimate_sheet.subtotal = totals.get("grand_total", 0)
            package.total_material = totals.get("material", 0)
            package.total_labor = totals.get("labor", 0)
            package.total_equipment = totals.get("equipment", 0)
            package.grand_total = totals.get("grand_total", 0)
            package.sheets.append(estimate_sheet)

        # Per-elevation sheet
        elevations = report_dict.get("siding_per_elevation", [])
        if elevations:
            elev_sheet = ExportSheet(name="Siding Per Elevation")
            for elev in elevations:
                for sec in elev.get("sections", []):
                    elev_sheet.items.append(ExportLineItem(
                        item_number=sec.get("id", ""),
                        description=f"{elev.get('elevation', '')} — {sec.get('id', '')}",
                        quantity=sec.get("area_sf", 0),
                        unit="SF",
                    ))
            package.sheets.append(elev_sheet)

        return package

    # -----------------------------------------------------------------------
    # Export formats
    # -----------------------------------------------------------------------

    def to_csv(self, package: ExportPackage) -> str:
        """Export to CSV string — BEAM AI style flat output."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Item #", "CSI", "Trade", "Description",
            "Qty", "Unit", "Unit Price",
            "Material", "Labor", "Equipment", "Extended",
            "Notes",
        ])

        for sheet in package.sheets:
            # Sheet header row
            writer.writerow([f"--- {sheet.name} ---"])
            for item in sheet.items:
                writer.writerow([
                    item.item_number,
                    item.csi_division,
                    item.trade,
                    item.description,
                    round(item.quantity, 1),
                    item.unit,
                    round(item.unit_price, 2),
                    round(item.material_cost, 2),
                    round(item.labor_cost, 2),
                    round(item.equipment_cost, 2),
                    round(item.extended_price, 2),
                    item.notes,
                ])
            if sheet.subtotal > 0:
                writer.writerow([
                    "", "", "", f"Subtotal — {sheet.name}",
                    "", "", "", "", "", "", round(sheet.subtotal, 2), "",
                ])

        # Grand total
        writer.writerow([])
        writer.writerow([
            "", "", "", "TOTAL MATERIAL",
            "", "", "", round(package.total_material, 2),
        ])
        writer.writerow([
            "", "", "", "TOTAL LABOR",
            "", "", "", "", round(package.total_labor, 2),
        ])
        writer.writerow([
            "", "", "", "GRAND TOTAL",
            "", "", "", "", "", "", round(package.grand_total, 2),
        ])

        return output.getvalue()

    def to_xlsx_data(self, package: ExportPackage) -> dict:
        """Export to structured dict suitable for Excel generation.

        Returns a dict of sheet_name → list of row dicts.
        Client-side or a library like openpyxl can render this.
        """
        workbook = {}

        for sheet in package.sheets:
            rows = []
            for item in sheet.items:
                rows.append({
                    "Item #": item.item_number,
                    "CSI Division": item.csi_division,
                    "Description": item.description,
                    "Quantity": round(item.quantity, 1),
                    "Unit": item.unit,
                    "Unit Price": round(item.unit_price, 2),
                    "Material": round(item.material_cost, 2),
                    "Labor": round(item.labor_cost, 2),
                    "Equipment": round(item.equipment_cost, 2),
                    "Extended": round(item.extended_price, 2),
                    "Notes": item.notes,
                })

            if sheet.subtotal > 0:
                rows.append({
                    "Description": f"SUBTOTAL — {sheet.name}",
                    "Extended": round(sheet.subtotal, 2),
                })

            workbook[sheet.name] = rows

        # Summary sheet
        workbook["Summary"] = [
            {"Description": "Project", "Value": package.project_name},
            {"Description": "Building", "Value": package.building_id},
            {"Description": "Total Material", "Value": round(package.total_material, 2)},
            {"Description": "Total Labor", "Value": round(package.total_labor, 2)},
            {"Description": "Total Equipment", "Value": round(package.total_equipment, 2)},
            {"Description": "Subtotal Direct", "Value": round(package.subtotal_direct, 2)},
            {"Description": "Overhead", "Value": round(package.overhead, 2)},
            {"Description": "Profit", "Value": round(package.profit, 2)},
            {"Description": "Tax", "Value": round(package.tax, 2)},
            {"Description": "GRAND TOTAL", "Value": round(package.grand_total, 2)},
        ]

        return workbook

    def to_json(self, package: ExportPackage) -> str:
        """Export to JSON string."""
        data = {
            "project_name": package.project_name,
            "building_id": package.building_id,
            "export_date": package.export_date,
            "sheets": [
                {
                    "name": sheet.name,
                    "items": [
                        {
                            "item_number": li.item_number,
                            "csi": li.csi_division,
                            "description": li.description,
                            "qty": li.quantity,
                            "unit": li.unit,
                            "unit_price": li.unit_price,
                            "material": li.material_cost,
                            "labor": li.labor_cost,
                            "equipment": li.equipment_cost,
                            "extended": li.extended_price,
                        }
                        for li in sheet.items
                    ],
                    "subtotal": sheet.subtotal,
                }
                for sheet in package.sheets
            ],
            "totals": {
                "material": package.total_material,
                "labor": package.total_labor,
                "equipment": package.total_equipment,
                "grand_total": package.grand_total,
            },
        }
        return json.dumps(data, indent=2)
