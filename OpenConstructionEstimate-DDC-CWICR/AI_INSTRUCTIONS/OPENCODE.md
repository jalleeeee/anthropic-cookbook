# Opencode Instructions for DDC CWICR

> Instructions for using DDC CWICR construction cost database with Opencode AI assistant.

## What is DDC CWICR?

Open-source construction cost database:
- **55,719 work items** with detailed cost breakdowns
- **27,672 resources** (materials, labor, equipment)
- **9 languages** with regional pricing
- **Pre-computed embeddings** for semantic search
- **Qdrant ready** vector database snapshots

## Quick Start

```python
import pandas as pd

# Load database
df = pd.read_parquet("DDC_CWICR_EN.parquet")

# Search by name
results = df[df['rate_original_name'].str.contains('concrete', case=False)]
print(results[['rate_code', 'rate_original_name', 'total_cost_per_position']])
```

## Data Formats

| Format | Size | Use Case |
|--------|------|----------|
| **Parquet** | 55 MB | Python, fast queries |
| **Excel** | 150-400 MB | Manual analysis |
| **CSV** | 1.3 GB | Database import |
| **Qdrant** | 1 GB | Semantic search |

## Key Columns

| Column | Description |
|--------|-------------|
| `rate_code` | Unique ID |
| `rate_original_name` | Work item description |
| `rate_unit_of_measure` | Unit (m², m³, kg) |
| `total_cost_per_position` | Total cost |
| `total_material_cost` | Materials cost |
| `total_labor_cost` | Labor cost |
| `total_machinery_cost` | Equipment cost |

## Languages

| Code | Language | Collection |
|------|----------|------------|
| EN | English | `ddc_cwicr_en` |
| DE | German | `ddc_cwicr_de` |
| FR | French | `ddc_cwicr_fr` |
| ES | Spanish | `ddc_cwicr_es` |
| RU | Russian | `ddc_cwicr_ru` |
| ZH | Chinese | `ddc_cwicr_zh` |
| AR | Arabic | `ddc_cwicr_ar` |
| PT | Portuguese | `ddc_cwicr_pt` |
| HI | Hindi | `ddc_cwicr_hi` |

## Semantic Search

```python
from qdrant_client import QdrantClient
import openai

# Get embedding
embedding = openai.embeddings.create(
    model="text-embedding-3-large",
    input="brick wall construction"
).data[0].embedding

# Search
client = QdrantClient("localhost", port=6333)
results = client.search(
    collection_name="ddc_cwicr_en",
    query_vector=embedding,
    limit=5
)
```

## Cost Calculation

```python
# Calculate project cost
quantities = {"01-01-001": 100}  # 100 m³

for code, qty in quantities.items():
    item = df[df['rate_code'] == code].iloc[0]
    cost = item['total_cost_per_position'] * qty
    print(f"{item['rate_original_name']}: {cost}")
```

## n8n Workflows

1. **Text Estimator** - Telegram bot
2. **Photo Analyzer** - GPT-4 Vision
3. **Universal Bot** - Multi-input
4. **CAD/BIM Pipeline** - BIM → Cost

> **Note**: These workflows are **examples and templates** for cost estimation logic. Use fully or partially for any business case. Study them to understand the calculation methodology.

## Links

- Demo: [openconstructionestimate.com](https://openconstructionestimate.com)
- Releases: [GitHub Releases](https://github.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR/releases)
