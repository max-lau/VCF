# ParaIQ — Legal Intelligence Platform

AI-powered legal SaaS platform built for boutique law firms. Combines document intelligence,
case management, voice commands, and fine-tuned ML models into a secure multi-tenant system.

**Live:** [https://app.para-iq.com](https://app.para-iq.com) · **API:** [https://nlp.para-iq.com](https://nlp.para-iq.com)

---

## Modules (28 pages)

| Module | Description |
|--------|-------------|
| **Home** | Landing dashboard with morning brief and system status |
| **Analyzer** | Sentiment analysis, named entity recognition, keyword extraction |
| **Batch** | Bulk document analysis with CSV export |
| **Timeline** | Chronological event extraction from legal documents |
| **Dashboard** | Live KPIs — active cases, AI work products, audit events |
| **Cases** | Case management — create, track, link documents and events |
| **Intelligence** | Per-case AI brief, contradiction scan, deadline radar |
| **Insights** | Aggregate analytics across all stored analyses |
| **Scorer** | NLP scoring across multiple dimensions |
| **Risk** | Multi-category risk scoring with signal breakdown |
| **Citations** | US Code, Federal Reporter citation extraction + CourtListener resolution |
| **Compare** | Document similarity — cosine, Jaccard, entity overlap, citation diff |
| **Discovery** | Guarded discovery agent with privilege screening and Bates numbering |
| **Interrogation** | Deposition transcript analysis — diarization, contradiction detection |
| **Credibility** | Witness credibility scoring across 5 dimensions with radar chart |
| **Deposition** | Deposition summary generation |
| **Intake** | OCR from photo/scan → text extraction + NLP analysis |
| **Redaction** | PII and sensitive entity redaction via Presidio |
| **Redaction Review** | Review and approve redacted documents |
| **Privilege Review** | Attorney-client privilege log and enclave review |
| **Media** | Audio/video transcription via Whisper + NLP analysis |
| **Multilingual** | NLP analysis in 13 languages |
| **Review** | Document review workflow with approval queue |
| **Model** | Fine-tuned model management — train, status, predict, LoRA |
| **Audit** | Full audit trail of all API activity, immutable via DB trigger |
| **Admin** | User management, role assignments, firm settings |
| **Login** | JWT authentication with rate limiting and token blocklist |

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Uvicorn (port 5003)
- **Database:** Supabase Postgres with Row-Level Security; multi-tenancy via `firm_id` + `TenantMiddleware`
- **NLP / AI:** Anthropic Claude API (`claude-haiku-4-5-20251001`, `claude-sonnet-4-6`); DistilBERT fine-tuning
- **Vector Store:** ChromaDB (persistent) with `all-MiniLM-L6-v2` embeddings; Pinecone-switchable via `VECTOR_BACKEND` env var
- **MLOps:** MLflow 3.14 — experiment tracking, model registry, drift monitoring; raw PyTorch training loop; LoRA/PEFT fine-tuning (~0.5% of params trained)
- **Observability:** Langfuse 4.9 tracing on all Claude calls; Prometheus + Grafana dashboards; Slack 5xx alerts
- **Voice:** OpenAI Whisper STT + Telegram bot (Hermes Agent); user-defined voice shortcuts stored per-user in Supabase
- **Auth:** JWT (PyJWT) + bcrypt; token blocklist in Postgres; IP-based login rate limiting; daily blocklist cleanup cron
- **PDF Export:** ReportLab with structured KV tables, risk charts, and case summaries
- **OCR:** Claude Vision
- **CI/CD:** GitHub Actions (14 tests — 11 tenant isolation + 3 AI smoke tests)
- **Infrastructure:** Hetzner VPS, Cloudflare Tunnel, PM2, Nginx reverse proxy

---

## Project Structure

```
nlp-portfolio/
├── backend/
│   └── demo1/
│       ├── main.py                    # FastAPI app — all routers mounted here
│       ├── pg.py                      # Postgres pool + RLS connection helper
│       ├── auth.py                    # JWT auth, token blocklist, rate limiting
│       ├── audit_trail.py             # Audit middleware + immutable log table
│       ├── intelligence.py            # Case brief, contradiction scan, deadline radar
│       ├── case_management.py         # Case + document CRUD
│       ├── discovery_intake.py        # Discovery agent with privilege screening
│       ├── discovery_agent_guard.py   # Guarded discovery — cost + privilege rails
│       ├── fine_tune.py               # DistilBERT legal classifier (HF Trainer)
│       ├── risk_scorer.py             # Multi-category risk scoring
│       ├── citation_resolver.py       # Legal citation extraction + CourtListener
│       ├── document_comparison.py     # Document similarity router
│       ├── redaction.py               # PII redaction via Presidio
│       ├── voice_router.py            # Whisper STT + intent routing
│       ├── voice_shortcuts_router.py  # User-defined voice shortcuts
│       ├── risk_watcher.py            # APScheduler — risk, brief, notifications, cron
│       ├── rate_limit.py              # Per-firm rate limiting on Claude calls
│       ├── mlops/
│       │   ├── tracker.py             # MLflow inference logging (wired into claude_with_retry)
│       │   ├── registry.py            # MLflow model registry
│       │   ├── drift_monitor.py       # Hourly latency/cost/token drift checks
│       │   ├── pytorch_trainer.py     # Raw PyTorch training loop (Module 2)
│       │   └── lora_trainer.py        # LoRA/PEFT fine-tuning (Module 3)
│       ├── retrieval/
│       │   ├── base.py                # VectorStoreBase ABC
│       │   ├── chroma_store.py        # ChromaDB persistent backend
│       │   ├── pinecone_store.py      # Pinecone backend (switchable)
│       │   └── factory.py             # get_vector_store() factory
│       ├── ab_testing/
│       │   ├── variants.py            # Deterministic hash-based variant assignment
│       │   └── logger.py              # JSONL experiment logger
│       ├── eval/
│       │   ├── dataset.py             # 15 legal Q&A ground-truth pairs
│       │   └── rag_evaluator.py       # RAGAS eval pipeline
│       └── routers/
│           ├── billing_router.py      # Matter billing and time tracking
│           ├── morning_brief_router.py # Daily AI brief — dynamic firm discovery
│           ├── monitor_router.py      # System health + PM2 status
│           ├── approval_router.py     # Document approval workflow
│           └── ...                    # calendar, contacts, reports, docketing, etc.
├── frontend/
│   └── demo1/                         # 28 HTML pages, Vanilla JS
│       ├── paraiq-sidebar.css/js      # Shared sidebar navigation
│       ├── paraiq-persist.js          # Analysis result persistence
│       ├── paraiq-export.js           # PDF export utility
│       └── *.html                     # One page per module
├── tests/
│   ├── conftest.py                    # Supabase fixtures, auth helpers
│   ├── test_tenant_isolation.py       # 11 cross-firm data leakage tests
│   ├── test_ai_smoke.py               # 3 live Claude API smoke tests
│   ├── test_auth.py                   # Login, permissions, JWT blocklist (4 tests)
│   └── test_monitor.py                # Health endpoint tests
├── scripts/
│   ├── seed_vector_store.py           # Seed ChromaDB from Supabase analyses
│   ├── ab_test_synthetic.py           # Fill A/B log to n=20 per variant
│   ├── ab_test_report.py              # A/B experiment report
│   └── eval_report.py                 # RAG evaluation runner
├── docs/
│   ├── mlops_versioning.md            # Model promotion criteria + registry strategy
│   ├── mlops_pytorch_lora.md          # Module 2+3 findings + interview talking points
│   ├── ab_test_findings.md            # A/B test results (Variant A: -19% latency, -21% cost)
│   ├── rag_eval_findings.md           # RAGAS eval across 3 runs
│   └── vector_db_comparison.md        # FAISS vs ChromaDB benchmark
├── .github/workflows/ci.yml           # GitHub Actions CI (14 tests, ~3.5 min)
├── requirements.txt                   # Full VPS dependencies
├── requirements-ci.txt                # Lean CI dependencies (35 packages)
└── .env                               # API keys (not committed)
```

---

## API Endpoints

### Core Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/analyze` | Sentiment, NER, keywords — saved to Postgres |
| POST | `/analyze/batch` | Bulk document analysis |
| POST | `/analyze/batch/csv` | Batch analysis with CSV export |
| POST | `/timeline` | Chronological event extraction |
| GET | `/history` | Stored analysis history |
| GET | `/dashboard/stats` | Live KPIs from Supabase |
| GET | `/dashboard/deadlines` | Upcoming case deadlines |

### Case Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/cases` | List / create cases |
| GET | `/cases/{id}/wall` | Case wall — documents, events, notes |
| GET | `/cases/{id}/intelligence` | AI-generated case brief + contradiction scan |
| GET/POST | `/cases/{id}/documents` | Case documents |

### Legal Modules
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/risk/score` | Multi-category risk scoring |
| POST | `/documents/compare` | Document similarity analysis |
| POST | `/documents/lease-diff` | Lease clause comparison (AI) |
| POST | `/citations/extract` | Legal citation extraction |
| POST | `/interrogate` | Deposition transcript analysis |
| POST | `/credibility/score` | Witness credibility scoring |
| POST | `/deposition/summarize` | Deposition summary generation |
| POST | `/entities/legal` | Legal entity extraction |
| POST | `/redact` | PII redaction |
| POST | `/intake` | OCR → NLP pipeline |
| POST | `/discovery/run-guarded` | Guarded discovery with privilege screening |
| POST | `/pacer/search` | PACER court record integration |
| POST | `/draft` | AI-assisted legal drafting |
| GET | `/brief/today` | Morning brief for authenticated firm |

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get JWT token + permission snapshot |
| POST | `/auth/logout` | Invalidate token (blocklist) |
| GET | `/auth/me` | Current user info |
| GET | `/auth/me/permissions` | Role + module permissions |
| POST | `/auth/refresh` | Refresh token |
| PUT | `/auth/password` | Change password |
| GET | `/auth/users` | List users (admin only) |

### PDF Export
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/export/analysis` | Analysis result PDF |
| POST | `/export/risk` | Risk report PDF |
| POST | `/export/intake` | Intake report PDF |
| POST | `/export/module` | Generic module PDF |
| GET | `/export/case/{id}` | Case summary PDF |
| GET | `/export/brief/{id}` | Morning brief PDF |

### MLOps / Model
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/model/train` | Fine-tune DistilBERT (HF Trainer) |
| GET | `/model/status` | Training status + progress |
| POST | `/model/predict` | Legal sentence classification |
| POST | `/model/pytorch-train` | Raw PyTorch training loop (MLflow tracked) |
| POST | `/model/lora-train` | LoRA/PEFT fine-tuning (~0.5% params) |

All endpoints require `X-API-Key` header. Authenticated endpoints also require `Authorization: Bearer <token>`.

---

## Security

- **Multi-tenancy:** `firm_id` threaded through all DB calls; Postgres RLS enforced via session variable set per-request by `TenantMiddleware`
- **Auth:** JWT with `jti` claim; logout invalidates token via `token_blocklist` table; daily cleanup cron at 03:00 UTC
- **Rate limiting:** IP-based login rate limiting (5 failures / 15 min); per-firm Claude API rate limiting
- **Audit:** Immutable audit log with DB-level insert trigger; all requests logged with `firm_id`, endpoint, method, status
- **Error handling:** All exceptions log server-side; generic messages returned to clients (no `str(e)` leaks)
- **CI:** 14 automated tests including 11 tenant isolation checks that assert cross-firm data is never accessible

---

## MLOps

- **Experiment tracking:** MLflow 3.14 — every Claude inference logged (tokens, latency, cost, firm_id)
- **Model registry:** `paraiq-legal-classifier v1` registered; promotion criteria: accuracy > 75%, F1 > 0.70, n ≥ 200 samples
- **Drift monitoring:** Hourly checks — latency, cost, token, error rate; alerts logged to MLflow
- **Training options:**
  - HF `Trainer` (existing, fast iteration)
  - Raw PyTorch loop (full control, per-step MLflow logging)
  - LoRA/PEFT (300K / 67M params trained; per-firm adapters at ~5MB each)
- **A/B testing:** Deterministic hash-based variant assignment; Variant A (chain-of-thought framing) confirmed -19% latency, -21% cost at n=20
- **RAG evaluation:** RAGAS 0.1.21 across 3 runs; context precision 0.973 (Run 3); faithfulness optimisation ongoing

---

## Quick Start

### 1. Clone and set up environment

```bash
git clone https://github.com/max-lau/nlp-portfolio.git
cd nlp-portfolio
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Required keys:
# ANTHROPIC_API_KEY=...
# PARAIQ_API_KEY=...
# DATABASE_URL=postgresql://...   (Supabase session pooler)
# JWT_SECRET_KEY=...
```

### 3. Run the API

```bash
uvicorn backend.demo1.main:app --host 0.0.0.0 --port 5003
```

### 4. Serve the frontend

```bash
cd frontend/demo1
python3 -m http.server 8080
# Open http://localhost:8080/home.html
```

---

## Frontend Features

- **Sidebar navigation** — fixed 220px sidebar across all 28 pages, grouped by module category, mobile-responsive with hamburger toggle
- **Morning brief** — AI-generated daily summary per firm, delivered at 08:00 UTC via APScheduler
- **Voice commands** — Whisper STT via Telegram bot; user-definable phrase → action shortcuts stored in Supabase
- **Analysis persistence** — results auto-saved to localStorage, restore banner on return visit
- **PDF export** — floating export button on all modules, structured ReportLab output
- **Approval workflow** — document review queue with approve/reject and audit logging
- **Kanban board** — matter task tracking with drag-and-drop, synced via Hermes Agent

---

## Author

Maxwell L. — [GitHub](https://github.com/max-lau)
