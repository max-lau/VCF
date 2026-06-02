# ParaIQ — Legal Intelligence Platform

AI-powered legal NLP SaaS platform built with FastAPI, Vue 3, and Claude AI.

Live: https://app.para-iq.com
VPS: root@5.161.83.6 — project root: /root/nlp-portfolio

---

## Infrastructure

### pm2 Processes
- ID 9: paraiq-api (FastAPI backend, port 5003)
- ID 6: paraiq-frontend (Vue 3, dist-vue)
- ID 5: paraiq-tunnel (Cloudflare)
- ID 11: paraiq-voice-bot (Telegram)
- ID 3: whale-scanner
- Start all: /root/start-paraiq.sh

### Tech Stack
- Backend: Python 3.12, FastAPI, Uvicorn
- AI/NLP: Claude API (claude-haiku-4-5-20251001, claude-sonnet-4-6), Claude Vision
- Database: Supabase Postgres (primary), SQLite (backup)
- Frontend: Vue 3, Vite, IBM Plex Mono
- Infra: Hetzner VPS, Cloudflare Tunnel, pm2, nginx

### Database
- Connection: backend/demo1/pg.py — synchronous psycopg2 pool
- Pattern: with get_conn(firm_id) as conn: rows = conn.execute(sql, params).fetchall()
- RLS enabled on sensitive tables
- RealDictCursor: use dict(row) not dict(zip(cols, row))

### Auth
- JWT (PyJWT), bcrypt passwords
- Super user: maxwell / paraiq2026, role paraiq_super, firm_id default
- Login: POST /auth/login — response field is token (not access_token)
- Frontend stores token in localStorage as paraiq_token

---

## Modules
Analyzer, Batch, Timeline, Dashboard, Insights, Scorer, Risk, Citations,
Compare, Model, Audit, OCR Intake, Redaction, Interrogation, Credibility,
Multilingual, Review, Discovery, Privilege Log, Correspondence, Email Intake

---

## Voice System (COMPLETE)
- 31 voice commands across 3 channels:
  - Telegram bot (paraiq_voice_bot.py)
  - Dashboard mic (VoiceCommand.vue in TopBar)
  - /voice/run FastAPI endpoint (backend/demo1/voice_router.py)
- Compound commands: get_workload_today, get_case_intelligence
- Telegram locked to ID 541424804, password paraiq2026
- Auth uses username field (not email) at /auth/login

---

## Email Intake Module (June 1-2, 2026)

### Files
- backend/demo1/email_filter.py — 5-stage filter engine
- backend/demo1/email_poller.py — Gmail adaptive poller
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

### Outlook
- OAuth2 via MSAL, scopes: Mail.Read, User.Read, email
- Do NOT pass offline_access/openid/profile — MSAL adds them automatically
- Credentials: OUTLOOK_CLIENT_ID, OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_SECRET
- Redirect: https://app.para-iq.com/auth/outlook/callback
- Azure app supports personal + org Microsoft accounts

### 5-Stage Filter Pipeline
- Stage 1 Domain Trust: +40 trusted domains, -50 bulk headers, -100 SYSTEM_DOMAINS
- Stage 2 NLP Case Match: +35 case match, +20 legal keywords (>=3), +5 dates
- Stage 3 Spam Filter: -40 promo subject, -35 unsubscribe link, -20 image-heavy
- Stage 4 Relevance Score: >=70 intake, 30-69 review, <30 discard
- Stage 5 Priority Tag: urgent/high/normal
- Formula: final = max(0, min(100, s1 + s2 + s3 + 50))

### Deduplication
- DB-based: fetch all processed IDs before each poll cycle
- Inbox never modified (read-only scope)
- UNIQUE constraint on (provider_message_id, attorney_id)

### Quiet Hours
- Default: 9pm-7am America/New_York
- Active: 300s poll, Quiet: 1800s poll
- Configurable per firm in firm_email_settings

### API Endpoints
- GET /email/accounts — list connected accounts
- POST /email/accounts/gmail/connect — start Gmail OAuth
- GET /auth/gmail/callback — Gmail OAuth callback
- POST /email/accounts/outlook/connect — start Outlook OAuth
- GET /auth/outlook/callback — Outlook OAuth callback
- DELETE /email/accounts/{id} — disconnect account
- GET /email/intake — paginated intake feed
- GET /email/intake/{id} — detail (JOINs log for scores)
- GET /email/log — full processing log
- POST /email/log/{id}/reprocess — flag for reprocess

### Key Learnings
- DB dedup safer than modifying inbox (attorney inbox integrity)
- RLS blocks background workers — query with attorney_id directly
- MSAL reserved scopes: do not pass manually
- gmail.readonly is superset of gmail.metadata
- HTML entity decode: html.unescape() after stripping tags
- email_intakes lacks score columns — JOIN with log for detail view
- selectItem on intake tab: use item.id not item.intake_id

---

## nginx Routes
auth, email, outlook, analyze, cases, discovery, depositions, motions,
contracts, correspondence, privilege, audit, intake, redaction, risk,
feedback, summary, credibility, interrogate, coreference, disambiguate,
contradictions, citations, documents, media, messages, model, multilingual,
entities, bates, bundle, pacer, timeline, export, exports, reports,
calendar, contacts, research, legal-bert, client-portal, ai-config,
enclave, notify, webhook, health, stats

---

## Environment Variables (.env)
ANTHROPIC_API_KEY, PARAIQ_API_KEY,
GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET,
GMAIL_REDIRECT_URI=https://app.para-iq.com/auth/gmail/callback,
OUTLOOK_CLIENT_ID, OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_SECRET,
OUTLOOK_REDIRECT_URI=https://app.para-iq.com/auth/outlook/callback,
EMAIL_POLL_INTERVAL_ACTIVE=300, EMAIL_POLL_INTERVAL_QUIET=1800,
EMAIL_QUIET_HOUR_START=21, EMAIL_QUIET_HOUR_END=7

---

## Upcoming
- User-defined voice shortcuts (Option B)
- Multi-tenant RLS hardening (prerequisite for real firm onboarding)
- Outlook Graph webhooks (replace polling with push)
- Email intake case link UI (click case badge to open matter)
