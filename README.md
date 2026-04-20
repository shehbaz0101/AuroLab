# AuroLab — Autonomous Physical AI Lab Automation

> Convert natural language lab instructions into validated, cited, robot-executable protocols in under 3 seconds.

[![Tests](https://img.shields.io/badge/tests-337%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)]() 
[![Streamlit](https://img.shields.io/badge/Streamlit-1.55-red)]()

---

## Quick Start

```bash
# 1. Activate environment
Auroenv\Scripts\activate          # Windows
# source Auroenv/bin/activate     # Linux/Mac

# 2. Pre-flight check
python scripts/validate_startup.py

# 3. Backend
uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# 4. Dashboard (new terminal)
streamlit run dashboard/app.py

# 5. Smoke test (no API key needed)
python mock_test.py               # 12/12 should pass

# 6. Full test suite
pytest tests/ -v                  # 307 pass, 26 skip (sandbox); 337 on full install
```

---

## What it does

Takes a plain-English lab instruction like:

> *"Perform a BCA protein assay on 8 samples using a 96-well plate at 562nm"*

And produces in under 3 seconds:
- Fully cited, step-by-step robotic protocol with `[SOURCE_N]` attribution
- Safety classification (safe / caution / warning / hazardous)
- PyBullet physics simulation result
- Itemised cost vs manual execution
- Downloadable Opentrons OT-2 Python script

---

## Architecture

```
Natural Language Instruction
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  Translation Service  (FastAPI · Groq Llama 3.3-70B)   │
│  PDF → chunk → embed → HyDE → Dense → BM25 → RRF       │
│  → CrossEncoder rerank → LLM generate → cite           │
└──────────────────┬──────────────────────────────────────┘
                   │  GeneratedProtocol (Pydantic v2)
         ┌─────────┼──────────────────────┐
         ▼         ▼                      ▼
 Execution      Analytics             RL Service
 (PyBullet)     (Cost/CO₂/ROI)       (Q-learning)
         │
         ▼
 Fleet Orchestration ── Vision Service ── Digital Twin
 (EDF scheduler)       (LLaVA/mock)      (Three.js OT-2)
```

---

## Project Structure

```
AuroLab/
├── main.py                          ← FastAPI entry point (use this)
├── mock_test.py                     ← 12 smoke tests, no API key needed
├── conftest.py                      ← pytest root sys.path config
├── requirements.txt                 ← all dependencies
├── .env.example                     ← copy to .env and fill
│
├── core/                            ← Phase 8+ new modules
│   ├── batch_generator.py           ← N-variant batch generation + ranking
│   ├── eln_exporter.py              ← CSV / Excel / JSON-LD export
│   ├── export_bundle.py             ← ZIP: JSON+HTML+OT2+MD+TXT
│   ├── llm_reflection.py            ← auto-fix failed simulations
│   ├── opentrons_exporter.py        ← OT-2 Python API v2 script
│   ├── param_validator.py           ← cross-validate params vs KB
│   ├── protocol_diff.py             ← side-by-side protocol comparison
│   ├── protocol_notes.py            ← lab notebook: notes/tags/stars/logs
│   ├── protocol_optimizer.py        ← speed/cost/green variants
│   ├── protocol_templates.py        ← 8 validated assay templates
│   ├── rag_engine.py               ← HyDE+BM25+RRF+rerank pipeline
│   ├── reagent_inventory.py         ← SQLite reagent stock management
│   ├── report_generator.py          ← HTML + Markdown report
│   ├── scheduler_jobs.py            ← recurring experiment scheduler
│   └── workflow_engine.py           ← multi-protocol chains
│
├── services/
│   ├── translation_service/         ← RAG + LLM + protocol management
│   ├── execution_service/           ← PyBullet physics simulation
│   ├── analytics_service/           ← cost + CO₂ + ROI
│   ├── vision_service/              ← lab state detection
│   ├── orchestration_service/       ← EDF fleet scheduler
│   └── rl_service/                  ← Q-learning optimisation
│
├── api/
│   └── extensions_router.py         ← 40 Phase 8+ API endpoints
│
├── dashboard/
│   ├── app.py                       ← Home page
│   ├── shared.py                    ← Design system (neon/robotic)
│   └── pages/                       ← 22 Streamlit pages
│       ├── 1_generate.py            ← NL → Protocol (streaming)
│       ├── 2_knowledge.py           ← PDF upload + KB management
│       ├── 3_eval.py                ← RAG evaluation metrics
│       ├── 4_history.py             ← Protocol history + search
│       ├── 5_health.py              ← Live endpoint health monitor
│       ├── 6_vision.py              ← Lab state detection
│       ├── 7_analytics.py           ← Cost + sustainability
│       ├── 8_fleet.py               ← Multi-robot fleet Gantt
│       ├── 9_rl_optimiser.py        ← Q-agent reward trend
│       ├── 10_digital_twin.py       ← Three.js OT-2 3D twin
│       ├── 11_compare.py            ← Protocol diff viewer
│       ├── 12_inventory.py          ← Reagent stock management
│       ├── 13_reflect.py            ← LLM auto-fix on failure
│       ├── 14_workflows.py          ← Multi-protocol chains
│       ├── 15_templates.py          ← 8 validated templates
│       ├── 16_report.py             ← HTML/MD report export
│       ├── 17_optimize.py           ← Speed/cost/green variants
│       ├── 18_batch.py              ← Batch generation + ranking
│       ├── 19_notebook.py           ← Electronic lab notebook
│       ├── 20_search.py             ← Semantic protocol search
│       ├── 21_scheduler.py          ← Experiment scheduler
│       └── 22_eln.py                ← ELN export (CSV/Excel/JSON-LD)
│
├── tests/                           ← 337 tests
│   ├── conftest.py                  ← fixtures + module aliases
│   ├── test_phase8_extensions.py    ← 96 tests, all Phase 8+ modules
│   ├── test_phase3_execution.py     ← execution pipeline
│   ├── test_phase4_vision.py        ← vision detection
│   ├── test_phase5_analytics.py     ← analytics engine
│   ├── test_phase6_orchestration.py ← fleet scheduling
│   ├── test_phase7_rl.py            ← RL engine + telemetry
│   ├── test_phase13.py              ← PDF parsing + chunking + RAG
│   ├── test_phase14_15.py           ← retrieval eval + LLM generation
│   ├── test_pybullet_sim.py         ← physics simulation
│   └── test_e2e_pipeline.py         ← end-to-end pipeline
│
└── scripts/
    ├── validate_startup.py          ← pre-flight check (run first)
    ├── run_eval.py                  ← RAG evaluation harness
    └── launch_dashboard.py          ← dashboard launcher
```

---

## API Reference — 84 Endpoints

### Core Generation
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/generate` | Generate protocol from NL instruction |
| POST | `/api/v1/generate/stream` | SSE streaming with live progress |
| POST | `/api/v1/upload` | Upload PDF to knowledge base |
| GET | `/api/v1/protocols/` | List all protocols |
| GET | `/api/v1/protocols/{id}` | Get protocol |
| DELETE | `/api/v1/protocols/{id}` | Delete protocol |

### Phase 8+ Extensions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/protocols/{id}/export/ot2` | OT-2 Python script |
| GET | `/api/v1/protocols/{id}/report` | HTML or Markdown report |
| GET | `/api/v1/protocols/{id}/bundle` | ZIP with all formats |
| GET | `/api/v1/protocols/{id}/export/csv` | CSV export |
| GET | `/api/v1/protocols/{id}/export/excel` | Excel workbook |
| GET | `/api/v1/protocols/{id}/export/jsonld` | JSON-LD (Bioschemas) |
| POST | `/api/v1/protocols/compare` | Side-by-side diff |
| POST | `/api/v1/protocols/validate-params` | Cross-validate vs KB |
| GET | `/api/v1/optimise/{id}` | Speed/cost/green variants |
| POST | `/api/v1/batch/generate` | N-variant batch + ranking |
| GET | `/api/v1/templates/` | List 8 assay templates |
| GET | `/api/v1/templates/{id}` | Template detail |
| POST | `/api/v1/templates/{id}/build` | Build instruction from template |
| GET | `/api/v1/inventory/` | Reagent inventory |
| POST | `/api/v1/inventory/` | Add reagent |
| POST | `/api/v1/inventory/check` | Check protocol vs stock |
| POST | `/api/v1/reflect` | LLM auto-fix failed sim |
| GET | `/api/v1/workflows/` | List workflows |
| POST | `/api/v1/workflows/` | Create workflow |
| POST | `/api/v1/workflows/{id}/run` | Execute workflow chain |
| GET | `/api/v1/protocols/{id}/annotations` | All annotations |
| PUT | `/api/v1/protocols/{id}/note` | Lab note |
| POST | `/api/v1/protocols/{id}/tags` | Add tag |
| POST | `/api/v1/protocols/{id}/star` | Star protocol |
| POST | `/api/v1/protocols/{id}/execution-log` | Log execution outcome |
| GET | `/api/v1/search` | Semantic search |
| GET | `/api/v1/scheduler/jobs` | List scheduled jobs |
| POST | `/api/v1/scheduler/jobs` | Schedule experiment |
| GET | `/api/v1/extensions/status` | Module availability |

### Other Services
| Prefix | Description |
|--------|-------------|
| `/api/v1/execute/*` | PyBullet simulation |
| `/api/v1/vision/*` | Lab state detection |
| `/api/v1/analytics/*` | Cost + sustainability |
| `/api/v1/fleet/*` | Robot fleet management |
| `/api/v1/rl/*` | RL agent + telemetry |

Full interactive docs: **http://localhost:8080/docs**

---

## Protocol Templates

| Template | Category | Time | Difficulty |
|----------|----------|------|------------|
| BCA Protein Assay | assay | 75 min | easy |
| Bradford Assay | assay | 30 min | easy |
| Sandwich ELISA | assay | 300 min | medium |
| MTT Cell Viability | assay | 360 min | medium |
| Standard PCR | assay | 120 min | easy |
| Western Blot Transfer | analysis | 240 min | hard |
| Agarose Gel Electrophoresis | analysis | 60 min | easy |
| Plasmid DNA Miniprep | prep | 45 min | easy |

---

## RAG Pipeline

```
Query → HyDE expansion → Dense retrieval (ChromaDB)
     → BM25 reranking → RRF fusion → CrossEncoder rerank → top-k
```

Evaluation metrics: MRR@k, NDCG@k, Recall@k, Hit Rate@k

---

## RL Reward Function

```
R = 0.30 × speed_score
  + 0.35 × accuracy_score
  + 0.20 × waste_score
  + 0.15 × safety_score
```

Q-learning converges in ~50 execution runs per protocol.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | required | Groq API key |
| `AUROLAB_SIM_MODE` | `pybullet` | `mock` / `pybullet` / `live` |
| `AUROLAB_VISION_BACKEND` | `mock` | `mock` / `groq` |
| `CHROMA_PERSIST` | `./data/chroma` | ChromaDB path |
| `TELEMETRY_DB` | `./data/telemetry.db` | RL telemetry |
| `AUROLAB_API_KEY` | (empty) | Optional API key auth |
| `PORT` | `8080` | API server port |

---

## Test Coverage

```bash
pytest tests/ -v

# 337 tests total:
tests/test_phase8_extensions.py     96 tests  ← Phase 8+ modules (all new)
tests/test_phase3_execution.py      ~50 tests ← execution pipeline
tests/test_phase4_vision.py         ~30 tests ← vision detection
tests/test_phase5_analytics.py      ~35 tests ← analytics engine
tests/test_phase6_orchestration.py  ~40 tests ← fleet scheduling
tests/test_phase7_rl.py             ~50 tests ← RL engine
tests/test_phase13.py               13 tests  ← PDF/chunker/RAG
tests/test_phase14_15.py            19 tests  ← retrieval eval + LLM
tests/test_pybullet_sim.py          ~15 tests ← physics
tests/test_e2e_pipeline.py          ~10 tests ← end-to-end
```

---

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8 GB | 16 GB |
| CPU | x86-64 | 8+ cores |
| GPU | Not required | NVIDIA RTX (Isaac Sim only) |
| Internet | Required | Required (Groq API) |

Tested on: Dell Latitude 5310 (Intel UHD, 16 GB RAM)

---

*AuroLab v2.0 — Autonomous Physical AI Lab Automation* 
