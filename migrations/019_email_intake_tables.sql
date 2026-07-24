-- 019_email_intake_tables.sql
-- Fix Email Intake schema for VCFClaimsIQ.
-- The legacy attorney_email_accounts table had firm_id as integer and no
-- attorney_id, which breaks the email router/poller. Since it is empty in this
-- tenant, drop and recreate it with the columns the backend expects.
-- Also creates email_intakes, email_processing_log, and firm_email_settings.

BEGIN;

-- ── Drop legacy mis-typed table (empty in production; CASCADE removes RLS policies) ──
DROP TABLE IF EXISTS attorney_email_accounts CASCADE;

CREATE TABLE attorney_email_accounts (
    id            SERIAL PRIMARY KEY,
    attorney_id   INTEGER NOT NULL,
    firm_id       TEXT NOT NULL,
    provider      TEXT NOT NULL CHECK (provider IN ('gmail','outlook')),
    email_address TEXT NOT NULL,
    access_token  TEXT,
    refresh_token TEXT,
    token_expiry  TIMESTAMPTZ,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_attorney_email_account_unique
    ON attorney_email_accounts(attorney_id, provider, email_address);
CREATE INDEX idx_attorney_email_account_active
    ON attorney_email_accounts(firm_id, provider, is_active);

ALTER TABLE attorney_email_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE attorney_email_accounts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON attorney_email_accounts FOR ALL
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── Email intakes (AI-routed messages worth a human review) ──
CREATE TABLE email_intakes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id          INTEGER NOT NULL REFERENCES attorney_email_accounts(id) ON DELETE CASCADE,
    attorney_id         INTEGER NOT NULL,
    firm_id             TEXT NOT NULL,
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
    reply_sent_by       TEXT,
    CONSTRAINT email_intakes_unique_message UNIQUE (provider, provider_message_id, attorney_id)
);

CREATE INDEX idx_email_intakes_attorney ON email_intakes(attorney_id);
CREATE INDEX idx_email_intakes_case ON email_intakes(case_id);
CREATE INDEX idx_email_intakes_received ON email_intakes(firm_id, received_at DESC);
CREATE INDEX idx_email_intakes_priority ON email_intakes(firm_id, priority, received_at DESC);

ALTER TABLE email_intakes ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_intakes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON email_intakes FOR ALL
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── Email processing log (every polled message, including discarded/spam) ──
CREATE TABLE email_processing_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id          INTEGER NOT NULL,
    attorney_id         INTEGER NOT NULL,
    firm_id             TEXT NOT NULL,
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

CREATE INDEX idx_email_log_attorney ON email_processing_log(attorney_id);
CREATE INDEX idx_email_log_received ON email_processing_log(firm_id, received_at DESC);
CREATE INDEX idx_email_log_decision ON email_processing_log(firm_id, routing_decision, processed_at DESC);
CREATE INDEX idx_email_log_intake ON email_processing_log(intake_id);

ALTER TABLE email_processing_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_processing_log FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON email_processing_log FOR ALL
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── Per-firm email polling settings ──
CREATE TABLE firm_email_settings (
    firm_id              TEXT PRIMARY KEY,
    quiet_hour_start     INTEGER NOT NULL DEFAULT 21,
    quiet_hour_end       INTEGER NOT NULL DEFAULT 7,
    poll_interval_active INTEGER NOT NULL DEFAULT 300,
    poll_interval_quiet  INTEGER NOT NULL DEFAULT 1800,
    timezone             TEXT NOT NULL DEFAULT 'America/New_York',
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE firm_email_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE firm_email_settings FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON firm_email_settings FOR ALL
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- Seed default settings for the WAW firm if it exists
INSERT INTO firm_email_settings (firm_id)
SELECT id FROM firms WHERE id = '1'
ON CONFLICT (firm_id) DO NOTHING;

COMMIT;
