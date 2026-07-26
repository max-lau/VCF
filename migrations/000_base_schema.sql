-- 000_base_schema.sql
-- Provisional base schema for VCFClaimsIQ (a VCF-focused fork of ParaIQ).
--
-- WARNING: This schema was inferred from backend/demo1/* source files and
-- migrations 001-025. It is intended to bootstrap a fresh Postgres database
-- idempotently so the migration chain can run on a clean install. Before using
-- in production, validate it against the live Supabase schema (e.g. via
-- pg_dump --schema-only or Supabase Studio) and adjust types/constraints as
-- needed. Litigation-only tables are included with minimal columns only when
-- referenced by later migrations.
--
-- Idempotency: every statement uses IF NOT EXISTS / IF NOT EXISTS variants so
-- running this on an existing database is safe.

-- Enable commonly used extensions safely.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ========================================================================
-- 1. FIRMS & AUTH
-- ========================================================================

CREATE TABLE IF NOT EXISTS firms (
    id         TEXT PRIMARY KEY,
    name       TEXT,
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    username      TEXT NOT NULL,
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS token_blocklist (
    jti        TEXT PRIMARY KEY,
    firm_id    TEXT NOT NULL DEFAULT 'default',
    user_id    INTEGER,
    blocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- ========================================================================
-- 2. ROLES & PERMISSIONS (referenced by auth.py / migration 014)
-- ========================================================================

CREATE TABLE IF NOT EXISTS roles (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    tier         INTEGER NOT NULL DEFAULT 3,
    default_open BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS role_assignments (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    role_id     INTEGER NOT NULL,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, firm_id)
);

CREATE TABLE IF NOT EXISTS module_permissions (
    id         SERIAL PRIMARY KEY,
    role_id    INTEGER NOT NULL,
    module     TEXT NOT NULL,
    can_read   BOOLEAN NOT NULL DEFAULT FALSE,
    can_write  BOOLEAN NOT NULL DEFAULT FALSE,
    can_delete BOOLEAN NOT NULL DEFAULT FALSE,
    can_export BOOLEAN NOT NULL DEFAULT FALSE,
    can_admin  BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (role_id, module)
);

-- ========================================================================
-- 3. CASES & CASE-RELATED DOCUMENTS
-- ========================================================================

CREATE TABLE IF NOT EXISTS cases (
    id                    SERIAL PRIMARY KEY,
    firm_id               TEXT NOT NULL DEFAULT 'default',
    case_number           TEXT,
    client_name           TEXT NOT NULL,
    client_email          TEXT,
    matter_number         TEXT,
    status                TEXT NOT NULL DEFAULT 'open',
    claim_stage           TEXT NOT NULL DEFAULT 'intake',
    vcf_status            TEXT NOT NULL DEFAULT 'pending',
    presence_proof_status TEXT NOT NULL DEFAULT 'not_started',
    date_of_birth         DATE,
    ssn_last4             TEXT,
    preferred_language    TEXT,
    exposure_location     TEXT,
    presence_dates        TEXT,
    wtc_health_program    BOOLEAN NOT NULL DEFAULT FALSE,
    award_amount          NUMERIC(12,2),
    description           TEXT,
    vcf_email             TEXT,
    vcf_account_created   BOOLEAN NOT NULL DEFAULT FALSE,
    vcf_claim_submitted   BOOLEAN NOT NULL DEFAULT FALSE,
    court                 TEXT,
    filing_date           DATE,
    risk_level            TEXT,
    deleted               BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS case_documents (
    id                SERIAL PRIMARY KEY,
    firm_id           TEXT NOT NULL DEFAULT 'default',
    case_id           INTEGER,
    scan_id           INTEGER,
    document_name     TEXT,
    source            TEXT,
    source_type       TEXT,
    source_ref        TEXT,
    source_url        TEXT,
    doc_text          TEXT,
    summary           TEXT,
    doc_type          TEXT NOT NULL DEFAULT 'other',
    file_url          TEXT,
    identity_signals  JSONB DEFAULT '{}',
    match_status      TEXT NOT NULL DEFAULT 'matched',
    entities_json     JSONB,
    events_json       JSONB,
    sentiment         TEXT,
    risk_score        REAL,
    language          TEXT DEFAULT 'en',
    upload_date       TIMESTAMPTZ,
    content_hash      TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS case_notes (
    id         SERIAL PRIMARY KEY,
    firm_id    TEXT NOT NULL DEFAULT 'default',
    case_id    INTEGER NOT NULL,
    author     TEXT,
    note       TEXT NOT NULL,
    pinned     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS case_tags (
    id         SERIAL PRIMARY KEY,
    firm_id    TEXT NOT NULL DEFAULT 'default',
    case_id    INTEGER NOT NULL,
    tag        TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firm_id, case_id, tag)
);

CREATE TABLE IF NOT EXISTS case_briefs (
    id           SERIAL PRIMARY KEY,
    firm_id      TEXT NOT NULL DEFAULT 'default',
    case_id      INTEGER NOT NULL,
    brief_json   JSONB,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 4. INTAKE & OCR
-- ========================================================================

CREATE TABLE IF NOT EXISTS intake_scans (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    case_id       INTEGER,
    filename      TEXT,
    raw_text      TEXT,
    word_count    INTEGER,
    confidence    REAL,
    ocr_engine    TEXT,
    risk_score    REAL,
    risk_level    TEXT,
    entities_json JSONB,
    form_fields   JSONB,
    file_url      TEXT,
    content_hash  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 5. VCF-SPECIFIC TABLES
-- ========================================================================

CREATE TABLE IF NOT EXISTS vcf_account_prep (
    id           SERIAL PRIMARY KEY,
    firm_id      TEXT NOT NULL DEFAULT 'default',
    case_id      INTEGER,
    client_name  TEXT,
    status       TEXT NOT NULL DEFAULT 'draft',
    demo_mode    BOOLEAN NOT NULL DEFAULT FALSE,
    encrypted    BOOLEAN NOT NULL DEFAULT FALSE,
    prep_blob    TEXT NOT NULL,
    vcf_username TEXT,
    created_by   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vcf_deadlines (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    case_id       INTEGER NOT NULL,
    deadline_type TEXT NOT NULL,
    due_date      DATE NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    description   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vcf_disbursements (
    id                  SERIAL PRIMARY KEY,
    firm_id             TEXT NOT NULL DEFAULT 'default',
    case_id             INTEGER NOT NULL UNIQUE,
    gross_award         NUMERIC(12,2) NOT NULL DEFAULT 0,
    attorney_fee_pct    NUMERIC(5,2)  NOT NULL DEFAULT 10.0,
    attorney_fee_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    medicare_lien       NUMERIC(12,2) NOT NULL DEFAULT 0,
    medicaid_lien       NUMERIC(12,2) NOT NULL DEFAULT 0,
    workers_comp_lien   NUMERIC(12,2) NOT NULL DEFAULT 0,
    other_lien          NUMERIC(12,2) NOT NULL DEFAULT 0,
    other_lien_desc     TEXT,
    net_to_claimant     NUMERIC(12,2) NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'pending',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS claim_stage_history (
    id         SERIAL PRIMARY KEY,
    firm_id    TEXT NOT NULL DEFAULT 'default',
    case_id    INTEGER NOT NULL,
    from_stage TEXT,
    to_stage   TEXT NOT NULL,
    changed_by TEXT,
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS claim_checklists (
    id         SERIAL PRIMARY KEY,
    firm_id    TEXT NOT NULL DEFAULT 'default',
    case_id    INTEGER NOT NULL,
    stage      TEXT NOT NULL,
    item_key   TEXT NOT NULL,
    label      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firm_id, case_id, stage, item_key)
);

-- ========================================================================
-- 6. COMMUNICATIONS
-- ========================================================================

CREATE TABLE IF NOT EXISTS communications (
    id          BIGSERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     BIGINT,
    direction   TEXT NOT NULL,
    channel     TEXT NOT NULL,
    comm_type   TEXT NOT NULL DEFAULT 'other',
    party_type  TEXT NOT NULL,
    party_name  TEXT,
    sender      TEXT,
    recipient   TEXT,
    subject     TEXT,
    body        TEXT,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 7. EMAIL INTAKE
-- ========================================================================

CREATE TABLE IF NOT EXISTS attorney_email_accounts (
    id            SERIAL PRIMARY KEY,
    attorney_id   INTEGER NOT NULL,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    provider      TEXT NOT NULL CHECK (provider IN ('gmail', 'outlook')),
    email_address TEXT NOT NULL,
    access_token  TEXT,
    refresh_token TEXT,
    token_expiry  TIMESTAMPTZ,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_intakes (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id          INTEGER NOT NULL,
    attorney_id         INTEGER NOT NULL,
    firm_id             TEXT NOT NULL DEFAULT 'default',
    case_id             INTEGER,
    provider            TEXT NOT NULL,
    provider_message_id TEXT NOT NULL,
    from_address        TEXT,
    to_addresses        TEXT[],
    cc_addresses        TEXT[],
    subject             TEXT,
    body_text           TEXT,
    body_html           TEXT,
    received_at         TIMESTAMPTZ NOT NULL,
    extracted_entities  JSONB,
    action_items        JSONB,
    deadline_dates      JSONB,
    priority            TEXT,
    has_attachments     BOOLEAN NOT NULL DEFAULT FALSE,
    attachment_names    TEXT[],
    sentiment           TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replied_at          TIMESTAMPTZ,
    reply_content       TEXT,
    reply_sent_by       TEXT
);

CREATE TABLE IF NOT EXISTS email_processing_log (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id          INTEGER NOT NULL,
    attorney_id         INTEGER NOT NULL,
    firm_id             TEXT NOT NULL DEFAULT 'default',
    provider            TEXT NOT NULL,
    provider_message_id TEXT NOT NULL,
    from_address        TEXT,
    subject             TEXT,
    received_at         TIMESTAMPTZ,
    processed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stage1_domain_score REAL,
    stage2_nlp_score    REAL,
    stage3_spam_penalty REAL,
    stage4_final_score  REAL,
    case_id_matched     INTEGER,
    routing_decision    TEXT,
    discard_reason      TEXT,
    intake_id           UUID,
    reprocessed         BOOLEAN NOT NULL DEFAULT FALSE,
    reprocessed_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS firm_email_settings (
    firm_id              TEXT PRIMARY KEY,
    quiet_hour_start     INTEGER NOT NULL DEFAULT 21,
    quiet_hour_end       INTEGER NOT NULL DEFAULT 7,
    poll_interval_active INTEGER NOT NULL DEFAULT 300,
    poll_interval_quiet  INTEGER NOT NULL DEFAULT 1800,
    timezone             TEXT NOT NULL DEFAULT 'America/New_York',
    trusted_domains      TEXT[],
    vcf_keywords         TEXT[],
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS parsed_messages (
    id           SERIAL PRIMARY KEY,
    firm_id      TEXT NOT NULL DEFAULT 'default',
    source_file  TEXT,
    format       TEXT,
    case_number  TEXT,
    thread_count INTEGER,
    msg_count    INTEGER,
    parsed_json  JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 8. CLIENT PORTAL
-- ========================================================================

CREATE TABLE IF NOT EXISTS client_portal_access (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    matter_id     INTEGER NOT NULL,
    client_name   TEXT,
    client_email  TEXT,
    access_token  TEXT,
    permissions   TEXT,
    expires_at    TIMESTAMPTZ,
    last_accessed TIMESTAMPTZ,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS client_messages (
    id              SERIAL PRIMARY KEY,
    firm_id         TEXT NOT NULL DEFAULT 'default',
    case_id         INTEGER NOT NULL,
    matter_id       INTEGER,
    portal_access_id INTEGER,
    client_name     TEXT,
    client_email    TEXT,
    subject         TEXT,
    message         TEXT NOT NULL,
    sender          TEXT,
    recipient       TEXT,
    direction       TEXT NOT NULL DEFAULT 'inbound',
    read            BOOLEAN NOT NULL DEFAULT FALSE,
    read_by_firm    BOOLEAN NOT NULL DEFAULT FALSE,
    read_by_client  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 9. ANALYSES & FEEDBACK
-- ========================================================================

CREATE TABLE IF NOT EXISTS analyses (
    id         SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    text       TEXT,
    word_count INTEGER,
    sentiment  TEXT,
    score      REAL,
    tone       JSONB,
    entities   JSONB,
    keywords   JSONB,
    summary    TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analysis_id     INTEGER,
    text            TEXT,
    predicted       TEXT,
    predicted_score REAL,
    corrected       TEXT,
    feedback_type   TEXT,
    reviewed        BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT
);

-- ========================================================================
-- 10. NOTIFICATIONS / SLACK / TEAMS
-- ========================================================================

CREATE TABLE IF NOT EXISTS notify_config (
    id         SERIAL PRIMARY KEY,
    platform   TEXT,
    label      TEXT,
    webhook_url TEXT,
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used  TIMESTAMPTZ,
    send_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notify_log (
    id          SERIAL PRIMARY KEY,
    platform    TEXT,
    event_type  TEXT,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status_code INTEGER,
    success     BOOLEAN,
    error       TEXT,
    preview     TEXT
);

-- ========================================================================
-- 11. ML / MODEL RUNS
-- ========================================================================

CREATE TABLE IF NOT EXISTS model_runs (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    status        TEXT,
    accuracy      REAL,
    f1_score      REAL,
    train_size    INTEGER,
    epochs        INTEGER,
    model_path    TEXT,
    notes         TEXT
);

-- ========================================================================
-- 12. AUDIT, GUARD & VALIDATION LOGS
-- ========================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id               SERIAL PRIMARY KEY,
    timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    firm_id          TEXT NOT NULL DEFAULT 'default',
    method           TEXT,
    endpoint         TEXT,
    status_code      INTEGER,
    response_time_ms REAL,
    client_ip        TEXT,
    body_size_bytes  INTEGER,
    error            TEXT,
    user_id          INTEGER
);

CREATE TABLE IF NOT EXISTS prompt_guard_log (
    id                SERIAL PRIMARY KEY,
    firm_id           TEXT NOT NULL DEFAULT 'default',
    endpoint          TEXT,
    risk_score        INTEGER NOT NULL DEFAULT 0,
    blocked           BOOLEAN NOT NULL DEFAULT FALSE,
    threat_count      INTEGER NOT NULL DEFAULT 0,
    threats_json      JSONB,
    original_preview  TEXT,
    sanitized_preview TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_output_validation_log (
    id              BIGSERIAL PRIMARY KEY,
    firm_id         TEXT NOT NULL DEFAULT 'default',
    passed          BOOLEAN NOT NULL,
    pii_detected    JSONB,
    harmful_detected JSONB,
    json_valid      BOOLEAN,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 13. AI ISOLATION & CONFIG
-- ========================================================================

CREATE TABLE IF NOT EXISTS tenant_ai_config (
    firm_id                   TEXT PRIMARY KEY,
    default_model             TEXT,
    strong_model              TEXT,
    max_tokens_per_day        INTEGER NOT NULL DEFAULT 500000,
    max_tokens_per_request    INTEGER NOT NULL DEFAULT 4096,
    system_prompt_override    TEXT NOT NULL DEFAULT '',
    enable_prompt_guard       BOOLEAN NOT NULL DEFAULT TRUE,
    enable_output_validation  BOOLEAN NOT NULL DEFAULT TRUE,
    enable_safety_scoring     BOOLEAN NOT NULL DEFAULT TRUE,
    custom_rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
    allowed_models            JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_token_usage (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    date          DATE NOT NULL,
    tokens_used   INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (firm_id, date)
);

CREATE TABLE IF NOT EXISTS ai_work_product (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    case_id       INTEGER,
    user_id       INTEGER,
    endpoint      TEXT NOT NULL,
    input_preview TEXT,
    result_json   JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 14. CRM, REDACTION, TRANSCRIPTION
-- ========================================================================

CREATE TABLE IF NOT EXISTS leads (
    id              BIGSERIAL PRIMARY KEY,
    firm_id         TEXT NOT NULL DEFAULT 'default',
    first_name      TEXT,
    last_name       TEXT,
    email           TEXT,
    phone           TEXT,
    case_description TEXT,
    status          TEXT NOT NULL DEFAULT 'New',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS redactions (
    id                TEXT PRIMARY KEY,
    firm_id           TEXT NOT NULL DEFAULT 'default',
    filename          TEXT,
    original_filename TEXT,
    size_kb           REAL,
    style             TEXT,
    total_redactions  INTEGER,
    confidence_score  REAL,
    file_path         TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transcriptions (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    filename    TEXT,
    file_type   TEXT,
    duration_s  REAL,
    case_number TEXT,
    language    TEXT,
    transcript  TEXT,
    segments    JSONB,
    word_count  INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 15. KANBAN
-- ========================================================================

CREATE TABLE IF NOT EXISTS kanban_boards (
    id         SERIAL PRIMARY KEY,
    firm_id    TEXT NOT NULL DEFAULT 'default',
    case_id    INTEGER,
    name       TEXT,
    columns    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kanban_cards (
    id              SERIAL PRIMARY KEY,
    case_id         INTEGER NOT NULL,
    firm_id         TEXT NOT NULL DEFAULT 'default',
    title           TEXT,
    card_type       TEXT,
    column_id       TEXT,
    due_date        DATE,
    assignee_id     INTEGER,
    notes           TEXT,
    position        INTEGER NOT NULL DEFAULT 0,
    moved_by_hermes BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kanban_card_logs (
    id              SERIAL PRIMARY KEY,
    card_id         INTEGER NOT NULL,
    case_id         INTEGER NOT NULL,
    firm_id         TEXT NOT NULL DEFAULT 'default',
    from_column     TEXT,
    to_column       TEXT,
    moved_by_hermes BOOLEAN NOT NULL DEFAULT FALSE,
    hermes_reason   TEXT,
    moved_by_user_id INTEGER,
    moved_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 16. WEBHOOKS
-- ========================================================================

CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id          SERIAL PRIMARY KEY,
    event       TEXT,
    url         TEXT,
    label       TEXT,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_fired  TIMESTAMPTZ,
    fire_count  INTEGER NOT NULL DEFAULT 0,
    last_status INTEGER
);

CREATE TABLE IF NOT EXISTS webhook_log (
    id               SERIAL PRIMARY KEY,
    subscription_id  INTEGER,
    event            TEXT,
    fired_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status_code      INTEGER,
    success          BOOLEAN,
    error            TEXT,
    payload_preview  TEXT
);

-- ========================================================================
-- 17. CUSTOM ENTITIES
-- ========================================================================

CREATE TABLE IF NOT EXISTS custom_entity_types (
    id         SERIAL PRIMARY KEY,
    type       TEXT,
    label      TEXT,
    pattern    TEXT,
    examples   JSONB,
    builtin    BOOLEAN NOT NULL DEFAULT FALSE,
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 18. E-SIGNATURE
-- ========================================================================

CREATE TABLE IF NOT EXISTS esign_requests (
    id                   SERIAL PRIMARY KEY,
    firm_id              TEXT NOT NULL DEFAULT 'default',
    case_id              INTEGER,
    document_name        TEXT NOT NULL,
    document_id          INTEGER,
    document_text        TEXT,
    subject              TEXT,
    message              TEXT,
    provider             TEXT NOT NULL DEFAULT 'email',
    status               TEXT NOT NULL DEFAULT 'pending',
    docusign_envelope_id TEXT,
    expires_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at         TIMESTAMPTZ,
    metadata             JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS esign_signers (
    id              SERIAL PRIMARY KEY,
    request_id      INTEGER NOT NULL,
    firm_id         TEXT NOT NULL DEFAULT 'default',
    name            TEXT NOT NULL,
    email           TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'signer',
    status          TEXT NOT NULL DEFAULT 'pending',
    sign_token      TEXT UNIQUE,
    signed_at       TIMESTAMPTZ,
    signature_text  TEXT,
    signature_image TEXT,
    ip_address      TEXT,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 19. LITIGATION-ONLY / LEGACY TABLES REQUIRED BY LATER MIGRATIONS
--    Included with minimal columns so migrations 001+ can ALTER them.
-- ========================================================================

CREATE TABLE IF NOT EXISTS attorney_review_gates (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    doc_id      INTEGER NOT NULL,
    attorney_id TEXT NOT NULL,
    reviewed    BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firm_id, doc_id)
);

CREATE TABLE IF NOT EXISTS user_security_keys (
    id         SERIAL PRIMARY KEY,
    firm_id    TEXT NOT NULL DEFAULT 'default',
    user_id    INTEGER,
    key_data   JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflows (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    name        TEXT,
    config      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_config (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    provider    TEXT,
    config      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_drafts (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER,
    doc_type    TEXT,
    doc_label   TEXT,
    content     TEXT,
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS approval_queue (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    item_type   TEXT,
    item_id     INTEGER,
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bates_configs (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    prefix      TEXT,
    start_num   INTEGER,
    config      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bates_log (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    doc_id      INTEGER,
    bates_num   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS billing_rates (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    user_id     INTEGER,
    rate        NUMERIC(10,2),
    currency    TEXT DEFAULT 'USD',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    matter_id   INTEGER,
    title       TEXT,
    event_date  DATE,
    event_type  TEXT,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS case_contradictions (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER NOT NULL,
    contradiction JSONB,
    reviewed    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS client_enclaves (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    client_id   INTEGER,
    enclave_id  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contacts (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    name        TEXT,
    email       TEXT,
    phone       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contact_matters (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    contact_id  INTEGER NOT NULL,
    matter_id   INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contracts (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    title       TEXT,
    content     TEXT,
    status      TEXT DEFAULT 'draft',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS correspondence (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    matter_id   INTEGER,
    subject     TEXT,
    date        TIMESTAMPTZ,
    direction   TEXT,
    from_party  TEXT,
    to_party    TEXT,
    body        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS depositions (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER,
    deponent    TEXT,
    date        DATE,
    transcript  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS discovery_files (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    case_id       INTEGER,
    case_number   TEXT,
    filename      TEXT,
    original_name TEXT,
    status        TEXT DEFAULT 'pending',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS discovery_runs (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    name        TEXT,
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS docketing_chains (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER,
    chain_name  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS docketing_confirmations (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    event_id    INTEGER,
    confirmed   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS docketing_events (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    chain_id    INTEGER,
    event_date  DATE,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invoices (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER,
    amount      NUMERIC(12,2),
    status      TEXT DEFAULT 'draft',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    invoice_id  INTEGER,
    description TEXT,
    quantity    NUMERIC(10,2),
    rate        NUMERIC(10,2),
    amount      NUMERIC(12,2),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS legal_bert_analyses (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER,
    result      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS morning_briefs (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    content     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS motions (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER,
    title       TEXT,
    content     TEXT,
    status      TEXT DEFAULT 'draft',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notifications (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    user_id     INTEGER,
    message     TEXT,
    read        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    invoice_id  INTEGER,
    amount      NUMERIC(12,2),
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS privilege_log (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER,
    doc_id      INTEGER,
    privilege   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS privilege_verdicts (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    log_id      INTEGER,
    verdict     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reports (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    report_type TEXT,
    report_data JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS research_notes (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    matter_id   INTEGER,
    title       TEXT,
    summary     TEXT,
    source_url  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS risk_assessments (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER,
    score       REAL,
    factors     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS time_entries (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    case_id     INTEGER,
    user_id     INTEGER,
    duration_min INTEGER,
    description TEXT,
    billable    BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS time_heartbeats (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    session_id  INTEGER,
    beat_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS time_sessions (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    user_id     INTEGER,
    case_id     INTEGER,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS voice_audit_log (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    user_id     INTEGER,
    command     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS voice_shortcuts (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    user_id     INTEGER,
    phrase      TEXT,
    action      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========================================================================
-- 20. IDEMPOTENT COLUMN BACKFILLS
--    Ensures the schema matches what later migrations assume is present.
-- ========================================================================

ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS firm_id               TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS claim_stage           TEXT DEFAULT 'intake',
    ADD COLUMN IF NOT EXISTS vcf_status            TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS presence_proof_status TEXT DEFAULT 'not_started',
    ADD COLUMN IF NOT EXISTS award_amount          NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS vcf_account_created   BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS vcf_claim_submitted   BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS date_of_birth         DATE,
    ADD COLUMN IF NOT EXISTS ssn_last4             TEXT,
    ADD COLUMN IF NOT EXISTS preferred_language    TEXT,
    ADD COLUMN IF NOT EXISTS exposure_location     TEXT,
    ADD COLUMN IF NOT EXISTS presence_dates        TEXT,
    ADD COLUMN IF NOT EXISTS wtc_health_program    BOOLEAN,
    ADD COLUMN IF NOT EXISTS client_email          TEXT,
    ADD COLUMN IF NOT EXISTS vcf_email             TEXT;

ALTER TABLE case_documents
    ADD COLUMN IF NOT EXISTS firm_id          TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS source           TEXT,
    ADD COLUMN IF NOT EXISTS case_id          INTEGER,
    ADD COLUMN IF NOT EXISTS scan_id          INTEGER,
    ADD COLUMN IF NOT EXISTS file_url         TEXT,
    ADD COLUMN IF NOT EXISTS doc_type         TEXT DEFAULT 'other',
    ADD COLUMN IF NOT EXISTS identity_signals JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS match_status     TEXT DEFAULT 'matched',
    ADD COLUMN IF NOT EXISTS content_hash     TEXT;

ALTER TABLE intake_scans
    ADD COLUMN IF NOT EXISTS firm_id       TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS case_id       INTEGER,
    ADD COLUMN IF NOT EXISTS created_at    TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS content_hash  TEXT;

ALTER TABLE communications
    ADD COLUMN IF NOT EXISTS firm_id     TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS case_id     BIGINT,
    ADD COLUMN IF NOT EXISTS comm_type   TEXT DEFAULT 'other',
    ADD COLUMN IF NOT EXISTS party_type  TEXT DEFAULT 'client',
    ADD COLUMN IF NOT EXISTS created_by  TEXT;

ALTER TABLE firm_email_settings
    ADD COLUMN IF NOT EXISTS trusted_domains TEXT[],
    ADD COLUMN IF NOT EXISTS vcf_keywords    TEXT[];

-- ========================================================================
-- 21. INDEXES
--    Core indexes for VCFClaimsIQ operation; safe to re-run.
-- ========================================================================

CREATE INDEX IF NOT EXISTS idx_cases_firm_status    ON cases(firm_id, status);
CREATE INDEX IF NOT EXISTS idx_cases_firm_stage     ON cases(firm_id, claim_stage);
CREATE INDEX IF NOT EXISTS idx_cases_created_at     ON cases(firm_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cases_client_name_trgm ON cases USING gin (client_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_cases_vcf_email      ON cases(vcf_email) WHERE vcf_email IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_case_documents_case  ON case_documents(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_case_documents_source ON case_documents(firm_id, source);
CREATE INDEX IF NOT EXISTS idx_case_documents_type  ON case_documents(firm_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_case_documents_match ON case_documents(firm_id, match_status);
CREATE INDEX IF NOT EXISTS idx_case_documents_scan  ON case_documents(firm_id, scan_id);
CREATE INDEX IF NOT EXISTS idx_case_documents_case_type ON case_documents(firm_id, case_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_case_documents_content_hash ON case_documents(firm_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_case_notes_case      ON case_notes(case_id, pinned DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_case_tags_case       ON case_tags(case_id);

CREATE INDEX IF NOT EXISTS idx_intake_scans_case    ON intake_scans(firm_id, case_id);
CREATE INDEX IF NOT EXISTS idx_intake_scans_firm_created ON intake_scans(firm_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_intake_scans_content_hash ON intake_scans(firm_id, content_hash);

CREATE INDEX IF NOT EXISTS idx_vcf_prep_case        ON vcf_account_prep(case_id);
CREATE INDEX IF NOT EXISTS idx_vcf_prep_status      ON vcf_account_prep(firm_id, status);

CREATE INDEX IF NOT EXISTS idx_vcf_deadlines_case   ON vcf_deadlines(case_id);
CREATE INDEX IF NOT EXISTS idx_vcf_deadlines_due_date ON vcf_deadlines(firm_id, due_date);
CREATE INDEX IF NOT EXISTS idx_vcf_deadlines_status ON vcf_deadlines(firm_id, status);
CREATE INDEX IF NOT EXISTS idx_vcf_deadlines_due_status ON vcf_deadlines(firm_id, due_date, status);

CREATE INDEX IF NOT EXISTS idx_vcf_disbursements_case ON vcf_disbursements(case_id);

CREATE INDEX IF NOT EXISTS idx_claim_stage_history_case ON claim_stage_history(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_claim_checklists_case    ON claim_checklists(case_id, stage);

CREATE INDEX IF NOT EXISTS idx_communications_case      ON communications(case_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_communications_party     ON communications(firm_id, party_type, sent_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_intakes_attorney ON email_intakes(attorney_id);
CREATE INDEX IF NOT EXISTS idx_email_intakes_case     ON email_intakes(case_id);
CREATE INDEX IF NOT EXISTS idx_email_intakes_received ON email_intakes(firm_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_intakes_priority ON email_intakes(firm_id, priority, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_log_attorney ON email_processing_log(attorney_id);
CREATE INDEX IF NOT EXISTS idx_email_log_received ON email_processing_log(firm_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_log_decision ON email_processing_log(firm_id, routing_decision, processed_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_log_intake   ON email_processing_log(intake_id);

CREATE INDEX IF NOT EXISTS idx_attorney_email_account_unique ON attorney_email_accounts(attorney_id, provider, email_address);
CREATE INDEX IF NOT EXISTS idx_attorney_email_account_active ON attorney_email_accounts(firm_id, provider, is_active);

CREATE INDEX IF NOT EXISTS idx_client_portal_access_firm ON client_portal_access(firm_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_client_messages_case      ON client_messages(firm_id, case_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_audit_log_firm_time ON audit_log(firm_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_firm_endpoint ON audit_log(firm_id, endpoint);

CREATE INDEX IF NOT EXISTS idx_pgl_firm_created ON prompt_guard_log (firm_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pgl_blocked      ON prompt_guard_log (firm_id, blocked) WHERE blocked = TRUE;

CREATE INDEX IF NOT EXISTS idx_ai_token_firm_date ON ai_token_usage (firm_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_leads_firm         ON leads(firm_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_redactions_firm    ON redactions(firm_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transcriptions_firm_case ON transcriptions(firm_id, case_number, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_kanban_cards_case  ON kanban_cards(case_id, column_id, position);
CREATE INDEX IF NOT EXISTS idx_kanban_card_logs_card ON kanban_card_logs(card_id, moved_at DESC);

CREATE INDEX IF NOT EXISTS idx_webhook_subscriptions_event ON webhook_subscriptions(event, active);
CREATE INDEX IF NOT EXISTS idx_webhook_log_subscription    ON webhook_log(subscription_id);

CREATE INDEX IF NOT EXISTS idx_esign_requests_firm  ON esign_requests(firm_id);
CREATE INDEX IF NOT EXISTS idx_esign_signers_request ON esign_signers(request_id);
CREATE INDEX IF NOT EXISTS idx_esign_signers_token   ON esign_signers(sign_token);

CREATE INDEX IF NOT EXISTS idx_role_assignments_user_firm ON role_assignments(user_id, firm_id);
CREATE INDEX IF NOT EXISTS idx_role_assignments_firm      ON role_assignments(firm_id);
CREATE INDEX IF NOT EXISTS idx_module_permissions_role    ON module_permissions(role_id);

CREATE INDEX IF NOT EXISTS idx_ai_work_product_firm_endpoint ON ai_work_product(firm_id, endpoint);
CREATE INDEX IF NOT EXISTS idx_ai_work_product_case          ON ai_work_product(case_id);
CREATE INDEX IF NOT EXISTS idx_ai_work_product_created_at    ON ai_work_product(created_at DESC);

-- ========================================================================
-- 22. SEQUENCES
-- ========================================================================

CREATE SEQUENCE IF NOT EXISTS vcf_email_seq START 1;
