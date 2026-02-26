# Claude Code Instructions for DDC CWICR

> This file provides Claude Code with specific instructions for working with the DDC CWICR construction cost database.

## Repository Overview

**DDC CWICR** is an open-source construction cost database with:
- 55,719 work items (строительные работы)
- 27,672 resources (materials, labor, equipment)
- 9 languages with regional pricing
- Pre-computed OpenAI embeddings (3072d) for semantic search
- Qdrant vector database integration

## Data Access Patterns

### 1. Load Parquet Data (Recommended)
```python
import pandas as pd

# Load the database
df = pd.read_parquet("DDC_CWICR_EN.parquet")

# Explore structure
print(f"Rows: {len(df)}, Columns: {len(df.columns)}")
print(df.columns.tolist())
```

### 2. Semantic Search with Qdrant
```python
from qdrant_client import QdrantClient
import openai

# Create embedding for search query
def get_embedding(text):
    response = openai.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return response.data[0].embedding

# Search for similar work items
client = QdrantClient("localhost", port=6333)
results = client.search(
    collection_name="ddc_cwicr_en",  # or ddc_cwicr_de, ddc_cwicr_ru, etc.
    query_vector=get_embedding("brick masonry wall"),
    limit=10
)

for result in results:
    print(f"{result.payload['rate_code']}: {result.payload['rate_original_name']}")
    print(f"  Cost: {result.payload['total_cost_per_position']}")
```

### 3. Filter by Category
```python
# Find all concrete work
concrete = df[df['rate_original_name'].str.contains('concrete|бетон', case=False, na=False)]

# Find by category code
category_01 = df[df['rate_code'].str.startswith('01-')]
```

## Key Columns Reference

### Identification
| Column | Description |
|--------|-------------|
| `rate_code` | Unique work item code |
| `rate_original_name` | Full description |
| `rate_unit_of_measure` | Unit (m², m³, kg, pcs) |

### Cost Breakdown
| Column | Description |
|--------|-------------|
| `total_cost_per_position` | Total cost per unit |
| `total_material_cost` | Materials subtotal |
| `total_labor_cost` | Labor subtotal |
| `total_machinery_cost` | Equipment subtotal |

### Classification
| Column | Description |
|--------|-------------|
| `category_name` | Main category |
| `department_name` | Department |
| `section_name` | Section |

## Common Tasks

### Task: Find Work Item by Description
```python
query = "reinforced concrete foundation"
matches = df[df['rate_original_name'].str.contains(query, case=False, na=False)]
print(matches[['rate_code', 'rate_original_name', 'total_cost_per_position', 'rate_unit_of_measure']])
```

### Task: Calculate Project Cost
```python
# Given quantities from BIM
quantities = {
    "01-01-001": 150,  # m³ of concrete
    "01-02-003": 2000, # kg of rebar
    "05-01-010": 500,  # m² of brick wall
}

total = 0
for code, qty in quantities.items():
    row = df[df['rate_code'] == code].iloc[0]
    cost = row['total_cost_per_position'] * qty
    total += cost
    print(f"{code}: {qty} × {row['total_cost_per_position']} = {cost}")

print(f"Total: {total}")
```

### Task: Export Cost Breakdown
```python
# Get detailed breakdown for a work item
code = "01-01-001"
item = df[df['rate_code'] == code].iloc[0]

print(f"Work Item: {item['rate_original_name']}")
print(f"Unit: {item['rate_unit_of_measure']}")
print(f"\nCost Breakdown:")
print(f"  Materials: {item['total_material_cost']}")
print(f"  Labor: {item['total_labor_cost']}")
print(f"  Equipment: {item['total_machinery_cost']}")
print(f"  TOTAL: {item['total_cost_per_position']}")
```

## Qdrant Collections

| Collection | Language | Region | Currency |
|------------|----------|--------|----------|
| `ddc_cwicr_ar` | Arabic | Dubai | AED |
| `ddc_cwicr_zh` | Chinese | Shanghai | CNY |
| `ddc_cwicr_de` | German | Berlin | EUR |
| `ddc_cwicr_en` | English | Toronto | CAD |
| `ddc_cwicr_es` | Spanish | Barcelona | EUR |
| `ddc_cwicr_fr` | French | Paris | EUR |
| `ddc_cwicr_hi` | Hindi | Mumbai | INR |
| `ddc_cwicr_pt` | Portuguese | São Paulo | BRL |
| `ddc_cwicr_ru` | Russian | St. Petersburg | RUB |

## n8n Workflows

The repository includes ready-to-use n8n workflows:

| # | Workflow | Purpose |
|---|----------|---------|
| 1 | Text Estimator Bot | Telegram bot for text descriptions |
| 2 | Photo Analyzer | GPT-4 Vision for construction photos |
| 3 | Universal Bot | Combined text/photo/PDF input |
| 4 | CAD/BIM Pipeline | Revit/IFC/DWG → 4D/5D estimates |

> **Note**: These n8n workflows are **examples and templates** demonstrating the cost estimation logic. They can be used fully or partially for any business case. Analyze these workflows to understand how cost calculations work: database queries, work item matching, pricing logic, and report generation. This understanding can be applied to build custom solutions on any platform.

## Example Prompts for Claude Code

| Task | Prompt |
|------|--------|
| Find items | "Search for all work items related to waterproofing" |
| Calculate cost | "Calculate total cost for 100m³ of concrete foundation" |
| Compare prices | "Compare labor costs for brick vs concrete walls" |
| Export data | "Export all electrical work items to Excel" |
| Build pipeline | "Create a Python script that takes quantities CSV and outputs cost estimate" |
| Semantic search | "Set up Qdrant and search for 'exterior wall insulation'" |

## Best Practices

1. **Use Parquet** - Much faster than CSV or Excel for large datasets
2. **Cache embeddings** - Don't recompute for repeated queries
3. **Match units** - Always verify `rate_unit_of_measure` matches your quantities
4. **Check language** - Use appropriate collection for target region
5. **Validate codes** - Work item codes may differ between languages

## Related Resources

- **Live Demo**: [openconstructionestimate.com](https://openconstructionestimate.com)
- **CAD/BIM Tools**: [cad2data Repository](https://github.com/datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN-pipeline-with-conversion-validation-qto)
- **Data Files**: See [Releases](https://github.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR/releases)
