# ParaIQ — Legal Intelligence Platform

AI-powered legal NLP SaaS platform built with FastAPI, Vue 3, and Claude AI.

Live: https://app.para-iq.com
VPS: root@5.161.83.6 — project root: /root/nlp-portfolio

---

## Infrastructure

### pm2 Processes
- ID 4: paraiq-api (FastAPI backend, port 5003)
- ID 2: paraiq-frontend (Vue 3, dist-vue)
- ID 1: paraiq-tunnel (Cloudflare)
- ID 5: prometheus (port 9090, scrapes /metrics every 15s)
- ID 11: paraiq-voice-bot (Telegram)
- Start all: /root/start-paraiq.sh

### Tech Stack
- Backend: Python 3.12, FastAPI, Uvicorn
- AI/NLP: Claude API (claude-haiku-4-5-20251001, claude-sonnet-4-6), Claude Vision
- Database: Supabase Postgres (primary), SQLite (backup)
- Frontend: Vue 3, Vite, IBM Plex Mono
- Infra: Hetzner VPS, Cloudflare Tunnel, pm2, nginx
- Observability: Prometheus + Grafana 11.1.0 (https://grafana.para-iq.com)

### Database
- Connection: backend/demo1/pg.py — synchronous psycopg2 pool
- Pattern: with get_conn(firm_id) as conn: rows = conn.execute(sql, params).fetchall()
- RLS enabled on sensitive tables
- RealDictCursor: use dict(row) not dict(zip(cols, row))

### Auth
- JWT (PyJWT), bcrypt passwords
- Every token includes jti (uuid4) for blocklist support
- Super user: maxwell / paraiq2026, role paraiq_super, firm_id default
- Login: POST /auth/login — response field is token (not access_token)
- Logout: POST /auth/logout — blocks jti in token_blocklist table
- Frontend stores token in localStorage as paraiq_token

---

## Modules
Analyzer, Batch, Timeline, Dashboard, Insights, Scorer, Risk, Citations,
Compare, Model, Audit, OCR Intake, Redaction, Interrogation, Credibility,
Multilingual, Review, Discovery, Privilege Log, Correspondence, Email Intake,
Billing, Voice Shortcuts, Morning Brief

---

## Observability Stack (June 2026)

### Prometheus
- Binary: /opt/prometheus/prometheus
- Config: /opt/prometheus/prometheus.yml
- Scrapes: http://localhost:5003/metrics every 15s (job: paraiq-api)
- Data: /opt/prometheus/data
- PM2 process: prometheus (id:5), listens on 127.0.0.1:9090

### Grafana
- Version: 11.1.0, installed via .deb
- Config: /etc/grafana/grafana.ini
- Public URL: https://grafana.para-iq.com (Cloudflare tunnel route)
- Data source: Prometheus at http://localhost:9090
- Dashboard: FastAPI Observability (ID 18739)
- Alert: ParaIQ 5xx Spike — fires to Slack ParaIQ Monitor when 5xx > 0.01 req/s over 5m

### FastAPI Instrumentation
- Package: prometheus-fastapi-instrumentator==8.0.2
- Wired in main.py: Instrumentator().instrument(app).expose(app, endpoint="/metrics")
- Metrics endpoint: http://localhost:5003/metrics (not exposed publicly)

---

## Voice System (COMPLETE)
- 31 voice commands across 3 channels:
  - Telegram bot (paraiq_voice_bot.py)
  - Dashboard mic (VoiceCommand.vue in TopBar)
  - /voice/run FastAPI endpoint (backend/demo1/voice_router.py)
- Compound commands: get_workload_today, get_case_intelligence
- Telegram locked to ID 541424804, password paraiq2026
- Auth uses username field (not email) at /auth/login
- User-defined shortcuts: voice_shortcuts_router.py, stored in voice_shortcuts table
  - CRUD: GET/POST/PUT/DELETE /voice/shortcuts
  - Injected into Claude prompt at runtime per user/firm

---

## Email Intake Module (June 1-2, 2026)

### Files
- backend/demo1/email_filter.py — 5-stage filter engine
- backend/demo1/email_poller.py — Gmail adaptive poller (token refresh persisted to DB)
- backend/demo1/outlook_poller.py — Outlook/Graph API poller
- backend/demo1/email_router.py — 10 FastAPI endpoints
- frontend/paraiq-vue/src/views/email/EmailInboxView.vue — Inbox UI

### DB Tables
- attorney_email_accounts — OAuth tokens per attorney/provider
- email_intakes — filtered-in emails (body_text attorney-only)
- email_processing_log — every email scored (UNIQUE: provider_message_id + attorney_id)
- firm_email_settings — quiet hours and poll intervals per firm

### Gmail
- OAuth2 via google-auth-oauthlib, scope: gmail.readonly
- Credentials: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET
- Redirect: https://app.para-iq.com/auth/gmail/callback
- Token refresh: _send_gmail_reply() refreshes and persists new token to DB

### Outlook
- OAuth2 via MSAL, scopes: Mail.Read, User.Read, email
- Do NOT pass offline_access/openid/profile — MSAL adds them automatically
- Credentials: OUTLOOK_CLIENT_ID, OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_SECRET
- Redirect: https://app.para-iq.com/auth/outlook/callback

### 5-Stage Filter Pipeline
- Stage 1 Domain Trust: +40 trusted domains, -50 bulk headers, -100 SYSTEM_DOMAINS
- Stage 2 NLP Case Match: +35 case match, +20 legal keywords (>=3), +5 dates
- Stage 3 Spam Filter: -40 promo subject, -35 unsubscribe link, -20 image-heavy
- Stage 4 Relevance Score: >=70 intake, 30-69 review, <30 discard
- Stage 5 Priority Tag: urgent/high/normal
- Formula: final = max(0, min(100, s1 + s2 + s3 + 50))

### Key Learnings
- DB dedup safer than modifying inbox (attorney inbox integrity)
- RLS blocks background workers — query with attorney_id directly
- MSAL reserved scopes: do not pass manually
- gmail.readonly is superset of gmail.metadata
- HTML entity decode: html.unescape() after stripping tags

---

## Billing Module

### Files
- backend/demo1/routers/billing_router.py (703 lines)
- frontend/paraiq-vue/src/views/admin/BillingView.vue

### Endpoints
- POST /billing/invoices — create invoice, pulls certified time entries
- GET /billing/invoices — list invoices with filter
- GET /billing/invoices/{id} — invoice detail
- POST /billing/invoices/{id}/items — add line item
- PATCH /billing/invoices/{id}/status — advance status (with void guard)
- POST /billing/invoices/{id}/payments — record payment, auto-advances to paid/partially_paid
- GET /billing/invoices/{id}/pdf — ReportLab PDF download
- GET /billing/dashboard — summary stats + billing rates
- POST /billing/rates — set attorney billing rate
- GET /billing/matter/{matter_id}/ledger — matter ledger

### Status Flow
draft -> pending_certification -> certified -> sent -> viewed -> partially_paid -> paid
Voiding: blocked if status is paid or partially_paid (frontend + backend guard)

### Key Fixes (June 2026)
- matter_id type mismatch fixed (v-model.number removed from select)
- Empty matters warning shown in New Invoice modal
- Void warning mentions time entry release; paid invoices cannot be voided

---

## Morning Brief (COMPLETE)

### Files
- backend/demo1/routers/morning_brief_router.py
- Scheduler: backend/demo1/risk_watcher.py (APScheduler, cron hour=8 minute=0)

### Behavior
- Runs at 8am daily via APScheduler inside FastAPI process
- get_active_firms() queries live users table — auto-includes new firms on onboarding
- GET /brief/today — returns today brief, generates on demand if not yet created
- GET /brief/today/voice — voice-optimized brief format
- Stored in morning_briefs table (firm_id, brief_date, brief_json, summary_text)

---

## JWT Token Blocklist (June 2026)

### Implementation
- Every JWT now includes jti (uuid4) in payload
- decode_token() checks token_blocklist table on every request
- POST /auth/logout — inserts jti + expires_at into blocklist
- token_blocklist table: jti (PK), firm_id, user_id, blocked_at, expires_at
- Index on expires_at for cleanup queries

---

## nginx Routes
auth, email, outlook, analyze, cases, discovery, depositions, motions,
contracts, correspondence, privilege, audit, intake, redaction, risk,
feedback, summary, credibility, interrogate, coreference, disambiguate,
contradictions, citations, documents, media, messages, model, multilingual,
entities, bates, bundle, pacer, timeline, export, exports, reports,
calendar, contacts, research, legal-bert, client-portal, ai-config,
enclave, notify, webhook, health, stats, kanban, draft, notifications,
brief, approvals, voice, docketing, time, billing, dashboard

---

## Environment Variables (.env)
ANTHROPIC_API_KEY, PARAIQ_API_KEY,
GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET,
GMAIL_REDIRECT_URI=https://app.para-iq.com/auth/gmail/callback,
OUTLOOK_CLIENT_ID, OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_SECRET,
OUTLOOK_REDIRECT_URI=https://app.para-iq.com/auth/outlook/callback,
EMAIL_POLL_INTERVAL_ACTIVE=300, EMAIL_POLL_INTERVAL_QUIET=1800,
EMAIL_QUIET_HOUR_START=21, EMAIL_QUIET_HOUR_END=7,
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com,
LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

---

## CI/CD (GitHub Actions)

### Workflow
- File: .github/workflows/ci.yml
- Triggers: every push to main, every pull request to main
- Runtime: ~3-4 minutes on ubuntu-latest
- Steps: Checkout -> Python 3.12 -> Install deps -> spacy model download -> Compile check -> Start server -> Health check -> pytest -> Stop server

### Secrets
- DATABASE_URL, JWT_SECRET_KEY, PARAIQ_API_KEY, ANTHROPIC_API_KEY
- LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL

### Dependencies
- requirements-ci.txt — lean subset (excludes torch, transformers, MLflow)
- Full venv: requirements.txt (273 packages, VPS only)
- spacy model: en_core_web_sm downloaded as workflow step

---

## Security Hardening (v4 Audit — June 2026)

### What was fixed (score 5/10 -> 8/10)
- §2.1 Audit write path now firm-scoped
- §2.2 /audit/discovery/chain + /export require auth + firm scoping
- §2.3 rate_limit.py wired into all 8 claude_with_retry call sites
- §2.4 Langfuse trace_claude_call() wired into claude_with_retry
- §2.5 /discovery/run-guarded endpoint with auth + firm scoping
- §2.6 redaction.py migrated from SQLite to Supabase
- §2.7 /audit/logs/clear now per-firm only
- §2.8 case_wall + case_intelligence converted to sync def
- §2.9 All hardcoded /root/nlp-portfolio/ paths replaced
- §2.10 get_connection() deprecated; all callers use get_conn(firm_id)
- JWT blocklist — logout invalidation via token_blocklist table
- Gmail OAuth — refresh token persisted back to DB after refresh

### Tenant isolation test suite
```bash
cd /root/nlp-portfolio
.venv/bin/python3 -m pytest tests/test_tenant_isolation.py -v
```

---

## Pending
- Anthropic BAA — submit at anthropic.com/contact before onboarding real firm data
- Outlook Graph webhooks (replace polling with push)
- JWT blocklist cleanup cron (delete expired rows from token_blocklist)
- Broader test coverage (currently ~3%, target 20%+)
- Course 2 MLOps: MLflow -> PyTorch -> LoRA/PEFT (deps installed, CPU-only on VPS)
