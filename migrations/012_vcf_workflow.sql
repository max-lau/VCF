-- 012_vcf_workflow.sql
-- Claim lifecycle stage history, checklist, and communications log.

-- ── Claim stage history ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS claim_stage_history (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL,
    case_id     INTEGER NOT NULL,
    from_stage  TEXT,
    to_stage    TEXT NOT NULL,
    changed_by  TEXT,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE claim_stage_history
    ADD COLUMN IF NOT EXISTS firm_id     TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS case_id     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS from_stage  TEXT,
    ADD COLUMN IF NOT EXISTS to_stage    TEXT NOT NULL DEFAULT 'intake',
    ADD COLUMN IF NOT EXISTS changed_by  TEXT,
    ADD COLUMN IF NOT EXISTS note        TEXT,
    ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_claim_stage_history_case ON claim_stage_history(case_id, created_at DESC);

ALTER TABLE claim_stage_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_stage_history FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS claim_stage_history_tenant_isolation ON claim_stage_history;
CREATE POLICY claim_stage_history_tenant_isolation ON claim_stage_history
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── Claim checklist ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS claim_checklists (
    id          SERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL,
    case_id     INTEGER NOT NULL,
    stage       TEXT NOT NULL,
    item_key    TEXT NOT NULL,
    label       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firm_id, case_id, stage, item_key)
);
ALTER TABLE claim_checklists
    ADD COLUMN IF NOT EXISTS firm_id     TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS case_id     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS stage       TEXT NOT NULL DEFAULT 'intake',
    ADD COLUMN IF NOT EXISTS item_key    TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS label       TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS status      TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS note        TEXT,
    ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_claim_checklists_case ON claim_checklists(case_id, stage);

ALTER TABLE claim_checklists ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_checklists FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS claim_checklists_tenant_isolation ON claim_checklists;
CREATE POLICY claim_checklists_tenant_isolation ON claim_checklists
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── Communications log (expanded from Phase 2 init) ───────────────────────────
-- Drop and recreate only if the old narrow schema exists; new installs already
-- have the table from communications.py init, so this is idempotent.
CREATE TABLE IF NOT EXISTS communications (
    id          BIGSERIAL PRIMARY KEY,
    firm_id     TEXT NOT NULL,
    case_id     BIGINT,
    direction   TEXT NOT NULL,
    channel     TEXT NOT NULL,
    party_type  TEXT NOT NULL,
    party_name  TEXT,
    sender      TEXT,
    recipient   TEXT,
    subject     TEXT,
    body        TEXT,
    sent_at     TIMESTAMPTZ DEFAULT NOW(),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    created_by  TEXT
);
ALTER TABLE communications
    ADD COLUMN IF NOT EXISTS firm_id     TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS case_id     BIGINT,
    ADD COLUMN IF NOT EXISTS direction   TEXT NOT NULL DEFAULT 'inbound',
    ADD COLUMN IF NOT EXISTS channel     TEXT NOT NULL DEFAULT 'email',
    ADD COLUMN IF NOT EXISTS party_type  TEXT NOT NULL DEFAULT 'client',
    ADD COLUMN IF NOT EXISTS party_name  TEXT,
    ADD COLUMN IF NOT EXISTS sender      TEXT,
    ADD COLUMN IF NOT EXISTS recipient   TEXT,
    ADD COLUMN IF NOT EXISTS subject     TEXT,
    ADD COLUMN IF NOT EXISTS body        TEXT,
    ADD COLUMN IF NOT EXISTS sent_at     TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS created_by  TEXT;

CREATE INDEX IF NOT EXISTS idx_communications_case      ON communications(case_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_communications_party     ON communications(firm_id, party_type, sent_at DESC);

ALTER TABLE communications ENABLE ROW LEVEL SECURITY;
ALTER TABLE communications FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS communications_tenant_isolation ON communications;
CREATE POLICY communications_tenant_isolation ON communications
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── Grants ────────────────────────────────────────────────────────────────────
-- Uncomment and adjust role name to match migration 007_app_role.sql:
-- GRANT SELECT, INSERT, UPDATE ON claim_stage_history  TO app_role;
-- GRANT SELECT, INSERT, UPDATE ON claim_checklists      TO app_role;
-- GRANT SELECT, INSERT, UPDATE ON communications        TO app_role;
-- GRANT USAGE, SELECT ON SEQUENCE claim_stage_history_id_seq  TO app_role;
-- GRANT USAGE, SELECT ON SEQUENCE claim_checklists_id_seq      TO app_role;
