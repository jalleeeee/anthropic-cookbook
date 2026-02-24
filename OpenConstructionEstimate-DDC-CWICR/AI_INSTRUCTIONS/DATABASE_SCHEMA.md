# DDC CWICR Database Schema

> Complete reference for the 85-field database structure.

## Overview

The DDC CWICR database contains **55,719 work items** with **85 fields** organized into logical groups.

## Field Groups

### 1. Classification (6 fields)

| Field | Type | Description |
|-------|------|-------------|
| `category_id` | INT | Category ID |
| `category_name` | STRING | Category name |
| `department_id` | INT | Department ID |
| `department_name` | STRING | Department name |
| `section_id` | INT | Section ID |
| `section_name` | STRING | Section name |

### 2. Work Item Identification (8 fields)

| Field | Type | Description |
|-------|------|-------------|
| `rate_id` | INT | Internal rate ID |
| `rate_code` | STRING | **Unique work item code** |
| `rate_original_name` | STRING | **Full description** |
| `rate_unit_of_measure` | STRING | **Unit** (m², m³, kg, pcs, etc.) |
| `rate_scope_repairs` | BOOL | Applicable to repairs |
| `rate_scope_new_construction` | BOOL | Applicable to new construction |
| `rate_scope_reconstruction` | BOOL | Applicable to reconstruction |
| `rate_has_resources` | BOOL | Has detailed resource breakdown |

### 3. Material Resources (12 fields)

| Field | Type | Description |
|-------|------|-------------|
| `material_id` | INT | Material ID |
| `material_code` | STRING | Material code |
| `material_name` | STRING | Material description |
| `material_unit` | STRING | Material unit |
| `material_quantity` | FLOAT | Quantity per work unit |
| `material_unit_cost` | FLOAT | Cost per material unit |
| `material_total_cost` | FLOAT | Total material cost |
| `material_weight_kg` | FLOAT | Weight in kg |
| `material_density` | FLOAT | Material density |
| `material_category` | STRING | Material category |
| `material_class` | STRING | Material class |
| `material_specification` | STRING | Detailed specs |

### 4. Labor Resources (10 fields)

| Field | Type | Description |
|-------|------|-------------|
| `labor_id` | INT | Labor record ID |
| `labor_qualification` | STRING | Worker qualification |
| `labor_worker_count` | INT | Number of workers |
| `labor_hours` | FLOAT | Labor hours per unit |
| `labor_hourly_rate` | FLOAT | Hourly wage rate |
| `labor_total_cost` | FLOAT | Total labor cost |
| `machinist_worker_count` | INT | Machinist count |
| `machinist_hours` | FLOAT | Machinist hours |
| `machinist_hourly_rate` | FLOAT | Machinist rate |
| `machinist_total_cost` | FLOAT | Machinist total |

### 5. Equipment/Machinery (12 fields)

| Field | Type | Description |
|-------|------|-------------|
| `machinery_id` | INT | Equipment ID |
| `machinery_code` | STRING | Equipment code |
| `machinery_name` | STRING | Equipment description |
| `machinery_class` | STRING | Equipment class |
| `machinery_hours` | FLOAT | Machine hours per unit |
| `machinery_hourly_rate` | FLOAT | Hourly equipment rate |
| `machinery_total_cost` | FLOAT | Total equipment cost |
| `machinery_fuel_type` | STRING | Fuel type |
| `machinery_fuel_consumption` | FLOAT | Fuel consumption rate |
| `machinery_electricity_kwh` | FLOAT | Electricity consumption |
| `machinery_operator_required` | BOOL | Requires operator |
| `machinery_operator_wage` | FLOAT | Operator wage |

### 6. Cost Aggregates (8 fields)

| Field | Type | Description |
|-------|------|-------------|
| `total_cost_per_position` | FLOAT | **TOTAL COST** |
| `total_material_cost` | FLOAT | **Materials subtotal** |
| `total_labor_cost` | FLOAT | **Labor subtotal** |
| `total_machinery_cost` | FLOAT | **Equipment subtotal** |
| `overhead_cost` | FLOAT | Overhead |
| `profit_margin` | FLOAT | Profit margin |
| `vat_amount` | FLOAT | VAT/Tax |
| `final_price` | FLOAT | Final price with all additions |

### 7. Price Statistics (6 fields)

| Field | Type | Description |
|-------|------|-------------|
| `price_min` | FLOAT | Minimum observed price |
| `price_max` | FLOAT | Maximum observed price |
| `price_median` | FLOAT | Median price |
| `price_mean` | FLOAT | Average price |
| `price_std_dev` | FLOAT | Standard deviation |
| `price_sample_count` | INT | Number of price samples |

### 8. Physical Properties (8 fields)

| Field | Type | Description |
|-------|------|-------------|
| `mass_total_kg` | FLOAT | Total mass in kg |
| `mass_materials_kg` | FLOAT | Materials mass |
| `volume_m3` | FLOAT | Volume in m³ |
| `area_m2` | FLOAT | Area in m² |
| `length_m` | FLOAT | Length in meters |
| `weight_per_unit` | FLOAT | Weight per unit |
| `density` | FLOAT | Density |
| `thickness_mm` | FLOAT | Thickness in mm |

### 9. Regional & Language (8 fields)

| Field | Type | Description |
|-------|------|-------------|
| `language_code` | STRING | Language (EN, DE, RU, etc.) |
| `region_code` | STRING | Region code |
| `region_name` | STRING | Region name |
| `currency_code` | STRING | Currency (EUR, USD, RUB) |
| `currency_symbol` | STRING | Currency symbol |
| `price_level` | STRING | Price level reference |
| `price_year` | INT | Price reference year |
| `price_index` | FLOAT | Regional price index |

### 10. Metadata (7 fields)

| Field | Type | Description |
|-------|------|-------------|
| `created_at` | DATETIME | Record creation date |
| `updated_at` | DATETIME | Last update date |
| `source_system` | STRING | Data source |
| `source_version` | STRING | Source version |
| `data_quality_score` | FLOAT | Quality score 0-1 |
| `is_active` | BOOL | Active record |
| `notes` | STRING | Additional notes |

## Cost Calculation Formula

```
Total Cost = Materials + Labor + Equipment + Overhead + Profit + VAT

Where:
- Materials = Σ(material_quantity × material_unit_cost)
- Labor = labor_hours × labor_hourly_rate + machinist_hours × machinist_hourly_rate
- Equipment = machinery_hours × machinery_hourly_rate
```

## Resource-Based Methodology

The database separates:
- **Technology Norms** (unchanging): Labor hours, material quantities, equipment time
- **Regional Prices** (volatile): Hourly rates, material costs, fuel prices

This allows:
```
Actual_Cost = Technology_Norm × Regional_Price
```

## Unit Types

| Unit | Description | Examples |
|------|-------------|----------|
| `m²` | Square meters | Flooring, painting, roofing |
| `m³` | Cubic meters | Concrete, excavation, fill |
| `m` | Linear meters | Pipes, cables, beams |
| `kg` | Kilograms | Steel, rebar, nails |
| `t` | Tonnes | Heavy materials |
| `pcs` | Pieces | Fixtures, doors, windows |
| `set` | Sets | Equipment sets |
| `100m` | Per 100 meters | Cables, wiring |
| `1000pcs` | Per 1000 pieces | Bricks, blocks |

## Index Fields (for Performance)

Recommended indexes for queries:
- `rate_code` (unique)
- `category_name`
- `rate_original_name` (full-text)
- `total_cost_per_position`
- `language_code`

## Embedding Field

For Qdrant vector search:
- **Field**: `embedding`
- **Dimensions**: 3072
- **Model**: OpenAI `text-embedding-3-large`
- **Source**: `rate_original_name` + `category_name`
