# Envelope Estimator Agent

An AI-powered construction estimating platform with five integrated workflows:

1. **Commercial Estimating** — PDF blueprint takeoff → cost estimation → proposal
2. **Satellite Roof Reports** — Address-only EagleView-style measurement reports
3. **Property Loss Estimates** — Photo-based Xactimate-style insurance claim reports
4. **Self-Service Scan → 5D Estimate** — Customer self-scan → instant 5D estimate (no salesman)
5. **AI Learning Engine** — Continuous learning from every estimate, auto-calibrating accuracy

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
│  WORKFLOW 4: Self-Service Scan → 5D Estimate (No Salesman Needed)        │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │ INTAKE FORM  │→│ SCAN PORTAL   │→│ AI ANALYSIS │→│ 5D ESTIMATE    │ │
│  │ Customer form│  │ Magic link    │  │ Claude Vis. │  │ 3D scope       │ │
│  │ Project type │  │ Guided photos │  │ Satellite   │  │ + schedule     │ │
│  │ Contact info │  │ Measurements  │  │ cross-ref   │  │ + cost         │ │
│  └─────────────┘  └──────────────┘  └────────────┘  └────────────────┘ │
│                                                                          │
│  WORKFLOW 5: AI Learning Engine (Every Estimate Feeds Back)              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │ RECORD       │→│ CALIBRATE     │→│ BENCHMARK   │→│ INSIGHTS       │ │
│  │ Every est.   │  │ EMA pricing   │  │ By cluster  │  │ Claude analysis│ │
│  │ + feedback   │  │ By trade/rgn  │  │ Comparables │  │ Trends + recs  │ │
│  │ + win/loss   │  │ Auto-adjust   │  │ Win rates   │  │ Dashboard      │ │
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

# Workflow 4: Self-service scan → 5D estimate
python agent.py --self-service --customer-name "Jane Doe" \
  --customer-email "jane@example.com" --address "123 Main St" --project-type residential_roof
python agent.py --process-scan --session-id SS-20260224-ABC123 --scan-photos front.jpg back.jpg

# Workflow 5: AI learning engine
python agent.py --learning-dashboard
python agent.py --record-feedback --estimate-id EST-SS-... --actual-cost 45000
python agent.py --record-feedback --estimate-id EST-SS-... --won
python agent.py --generate-insights

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
| `agent.py` | Main orchestrator - routes to all five workflows |
| `modules/itb_intake.py` | Monitors email/folders for new ITBs and drawings |
| `modules/pdf_takeoff.py` | Extracts measurements from PDF blueprints via Claude Vision |
| `modules/cost_engine.py` | Prices takeoff quantities using DDC-CWICR database |
| `modules/proposal_gen.py` | Generates professional bid proposals |
| `modules/roof_report.py` | Satellite roof measurement reports (EagleView-style) |
| `modules/property_loss.py` | Property loss / insurance estimates (Xactimate-style) |
| `modules/self_service_scan.py` | Self-service scan portal → 5D estimate (no site visit) |
| `modules/ai_learning_engine.py` | Continuous AI learning, calibration, benchmarks, insights |
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

### 4. Self-Service Scan → 5D Estimate
- Customer fills out intake form (name, email, address, project type)
- System generates a secure magic link with 72-hour expiry
- Customer receives link via email/SMS with guided photo instructions
- Scan portal tells them exactly what photos to take per project type
- Customer submits photos + basic measurements through the portal
- Claude Vision analyzes all photos (materials, dimensions, condition, damage)
- System cross-references with satellite data (Google Solar API)
- Generates full 5D estimate: 3D scope + schedule (4D) + cost (5D)
- Professional HTML report delivered instantly — no salesman required

### 5. AI Learning Engine
- **Every estimate** across all workflows is recorded into the learning database
- **Feedback loops**: actual costs, win/loss, adjuster corrections, client ratings
- **Auto-calibration**: EMA-based pricing adjustments per trade, region, and project cluster
- **Benchmarking**: "Projects like this typically cost $X/SF" with percentiles
- **Comparable estimates**: Find similar past projects for sanity checking
- **Pricing trends**: Track material/labor cost drift over time
- **AI insights**: Claude periodically analyzes all data and generates actionable recommendations
- **Dashboard**: Overall platform accuracy, win rate, top adjustments at a glance

## Data Sources

- **takeoff-reader-ai**: Blueprint reading methodology
- **OpenConstructionEstimate-DDC-CWICR**: 55,719 work items, cost database
- **RoofReport-v2**: Satellite measurement pipeline (Google Solar API + GeoTIFF)
- **SureSight**: AI damage detection patterns (Google Cloud Vision)
- **Xactimate**: Industry-standard pricing codes and categories
