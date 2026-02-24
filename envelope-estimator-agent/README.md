# Envelope Estimator Agent

An AI-powered commercial estimating agent for building envelope trades.
Combines PDF blueprint takeoff (via Claude Vision) with resource-based cost
estimation (via DDC-CWICR) to automate the full workflow from ITB intake
to proposal generation.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    ENVELOPE ESTIMATOR AGENT                       │
│                      (main orchestrator)                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────┐ │
│  │ ITB INTAKE   │→│ PDF TAKEOFF   │→│ COST ENGINE │→│PROPOSAL│ │
│  │              │  │              │  │             │  │ GEN    │ │
│  │ - Email/IMAP │  │ - Claude     │  │ - DDC-CWICR │  │ - HTML │ │
│  │ - Watched    │  │   Vision     │  │ - Qdrant    │  │ - PDF  │ │
│  │   folders    │  │ - Scale      │  │ - Regional  │  │ - Excel│ │
│  │ - API hooks  │  │   detection  │  │   pricing   │  │        │ │
│  │              │  │ - 4-way      │  │ - Markup &  │  │        │ │
│  │              │  │   validation │  │   overhead  │  │        │ │
│  └─────────────┘  └──────────────┘  └────────────┘  └────────┘ │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  Phase 1 Trades: Siding, Roofing, Gutters, Downspouts,          │
│                  Coping, Windows                                 │
│  Phase 2 Trades: Decking, Exterior Doors, Railing, Framing,     │
│                  Painting, Drywall                               │
└──────────────────────────────────────────────────────────────────┘
```

## Setup

1. Copy `.env.example` to `.env` and fill in your API keys
2. Install dependencies: `pip install -r requirements.txt`
3. Set up Qdrant with DDC-CWICR data (see config/qdrant_setup.md)
4. Run: `python agent.py`

## Modules

| Module | Purpose |
|--------|---------|
| `agent.py` | Main orchestrator - coordinates all modules |
| `modules/itb_intake.py` | Monitors email/folders for new ITBs and drawings |
| `modules/pdf_takeoff.py` | Extracts measurements from PDF blueprints via Claude Vision |
| `modules/cost_engine.py` | Prices takeoff quantities using DDC-CWICR database |
| `modules/proposal_gen.py` | Generates professional bid proposals |
| `config/trades.py` | Trade definitions, waste factors, and measurement rules |
| `config/settings.py` | Environment and runtime configuration |
| `prompts/` | Claude prompt templates for each pipeline stage |
| `templates/` | HTML/proposal templates |

## Data Sources

- **takeoff-reader-ai**: Blueprint reading methodology, validation system
- **OpenConstructionEstimate-DDC-CWICR**: 55,719 work items, cost database, Qdrant vectors
