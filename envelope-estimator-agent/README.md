# Envelope Estimator Agent

An AI-powered construction estimating platform with three integrated workflows:

1. **Commercial Estimating** — PDF blueprint takeoff → cost estimation → proposal
2. **Satellite Roof Reports** — Address-only EagleView-style measurement reports
3. **Property Loss Estimates** — Photo-based Xactimate-style insurance claim reports

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       ENVELOPE ESTIMATOR AGENT                          │
│                         (main orchestrator)                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  WORKFLOW 1: Commercial Estimating (ITB → Takeoff → Estimate → Proposal) │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │ ITB INTAKE   │→│ PDF TAKEOFF   │→│ COST ENGINE │→│ PROPOSAL GEN   │ │
│  │ Email/IMAP   │  │ Claude Vision │  │ DDC-CWICR   │  │ HTML/PDF       │ │
│  │ Watched dirs │  │ Scale detect  │  │ Qdrant      │  │ Trade breakdown│ │
│  │ API hooks    │  │ 4-way valid.  │  │ Markup/O&P  │  │ Bid-ready      │ │
│  └─────────────┘  └──────────────┘  └────────────┘  └────────────────┘ │
│                                                                          │
│  WORKFLOW 2: Satellite Roof Report (Address → 3-Page Report)             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │ GEOCODE      │→│ SOLAR API     │→│ GEOTIFF DSM │→│ MEASUREMENT    │ │
│  │ Address→GPS  │  │ Building     │  │ Elevation   │  │ Area/Pitch     │ │
│  │              │  │ Insights     │  │ Gradient    │  │ Edges/BOM      │ │
│  ├─────────────┤  ├──────────────┤  ├────────────┤  ├────────────────┤ │
│  │ SATELLITE    │→│ CLAUDE VISION │→│ MATERIALS   │→│ 3-PAGE HTML    │ │
│  │ Multi-zoom   │  │ Facet detect  │  │ BOM + cost  │  │ Print-to-PDF   │ │
│  │ imagery      │  │ Penetrations  │  │ estimate    │  │ Professional   │ │
│  └─────────────┘  └──────────────┘  └────────────┘  └────────────────┘ │
│                                                                          │
│  WORKFLOW 3: Property Loss Estimate (Photos → Xactimate-style Claim)     │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │ PHOTO AI     │→│ DAMAGE ASSESS │→│ LINE ITEMS  │→│ CLAIM REPORT   │ │
│  │ Claude Vision│  │ Type/Severity│  │ XactNet     │  │ RCV/ACV/Dep    │ │
│  │ Damage detect│  │ Affected area│  │ pricing     │  │ O&P 10/10      │ │
│  │ Classify     │  │ Components   │  │ Labor+Matl  │  │ Net claim amt  │ │
│  └─────────────┘  └──────────────┘  └────────────┘  └────────────────┘ │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  Phase 1 Trades: Siding, Roofing, Gutters, Downspouts, Coping, Windows  │
│  Phase 2 Trades: Decking, Ext. Doors, Railing, Framing, Painting, Drywall│
└──────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Copy environment config
cp .env.example .env  # fill in API keys

# Workflow 1: Process construction plans
python agent.py --pdf plans.pdf
python agent.py --pdf sheet1.pdf sheet2.pdf --trades SID,ROF
python agent.py --folder ./project_plans/

# Workflow 2: Satellite roof report
python agent.py --roof-report --address "123 Main St, Denver, CO 80202"

# Workflow 3: Property loss / insurance estimate
python agent.py --loss-report --address "123 Main St" --photos dmg1.jpg dmg2.jpg --cause hail
python agent.py --loss-report --address "123 Main St" --photos *.jpg --with-roof \
  --cause wind --homeowner "John Doe" --insurance "State Farm" --deductible 2500

# Continuous monitoring
python agent.py --monitor
```

## Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...         # Claude API (vision + reasoning)

# For Satellite Roof Reports (Workflow 2)
GOOGLE_API_KEY=AIzaSy...             # Google Maps + Solar API

# For DDC-CWICR pricing (Workflow 1)
OPENAI_API_KEY=sk-...                # Embeddings for vector search
QDRANT_HOST=localhost                # Qdrant vector DB
QDRANT_PORT=6333

# For email monitoring
IMAP_SERVER=imap.gmail.com
IMAP_USERNAME=...
IMAP_PASSWORD=...

# Company profile (for proposals)
COMPANY_NAME=...
COMPANY_EMAIL=...
OVERHEAD_PERCENT=0.10
PROFIT_PERCENT=0.10
```

## Modules

| Module | Purpose |
|--------|---------|
| `agent.py` | Main orchestrator - routes to all three workflows |
| `modules/itb_intake.py` | Monitors email/folders for new ITBs and drawings |
| `modules/pdf_takeoff.py` | Extracts measurements from PDF blueprints via Claude Vision |
| `modules/cost_engine.py` | Prices takeoff quantities using DDC-CWICR database |
| `modules/proposal_gen.py` | Generates professional bid proposals |
| `modules/roof_report.py` | Satellite roof measurement reports (EagleView-style) |
| `modules/property_loss.py` | Property loss / insurance estimates (Xactimate-style) |
| `config/trades.py` | Trade definitions, waste factors, and measurement rules |
| `config/settings.py` | Environment and runtime configuration |

## Workflow Details

### 1. Commercial Estimating
- Monitors IMAP email and watched folders for ITBs
- Uses Claude Vision to read PDF blueprints and extract quantities
- Prices items via DDC-CWICR vector search (55,719 work items)
- Generates HTML/PDF bid proposals with trade breakdowns

### 2. Satellite Roof Reports
- Geocodes address → lat/lng via Google Maps API
- Fetches building footprint + roof segments via Google Solar API
- Downloads DSM GeoTIFF for precise slope/pitch analysis
- Multi-zoom satellite imagery (5 zoom levels)
- Claude Vision analyzes roof geometry (facets, edges, penetrations)
- Generates 3-page professional HTML report with materials BOM

### 3. Property Loss Estimates
- Claude Vision analyzes damage photos (hail, wind, water, fire, impact)
- Classifies damage type, severity, affected components
- Generates Xactimate-compatible line items with XactNet pricing
- Computes O&P (10%/10%), depreciation, ACV/RCV
- Optional satellite roof measurement integration
- Produces claim-ready 3-page report with depreciation schedule

## Data Sources

- **takeoff-reader-ai**: Blueprint reading methodology
- **OpenConstructionEstimate-DDC-CWICR**: 55,719 work items, cost database
- **RoofReport-v2**: Satellite measurement pipeline (Google Solar API + GeoTIFF)
- **SureSight**: AI damage detection patterns (Google Cloud Vision)
- **Xactimate**: Industry-standard pricing codes and categories
