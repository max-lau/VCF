-- 011_vcf_schema.sql
-- VCFClaimsIQ core schema additions: claim lifecycle fields, deadlines, disbursements.
-- Run after 010_vcf_account_prep.sql.

-- ── Ensure tenant column exists on legacy tables first ────────────────────────
-- This must succeed before any tenant-scoped indexes are created.
ALTER TABLE IF EXISTS cases ADD COLUMN IF NOT EXISTS firm_id TEXT NOT NULL DEFAULT 'default';
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'case_documents'
    ) THEN
        ALTER TABLE case_documents ADD COLUMN IF NOT EXISTS firm_id TEXT NOT NULL DEFAULT 'default';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'intake_scans'
    ) THEN
        ALTER TABLE intake_scans ADD COLUMN IF NOT EXISTS firm_id TEXT NOT NULL DEFAULT 'default';
    END IF;
END $$;

-- ── Extend cases table with VCF-specific fields ───────────────────────────────
ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS claim_stage          TEXT DEFAULT 'intake',
    ADD COLUMN IF NOT EXISTS vcf_status           TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS presence_proof_status TEXT DEFAULT 'not_started',
    ADD COLUMN IF NOT EXISTS award_amount         NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS vcf_account_created  BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS vcf_claim_submitted  BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS date_of_birth        DATE,
    ADD COLUMN IF NOT EXISTS ssn_last4            TEXT,
    ADD COLUMN IF NOT EXISTS preferred_language   TEXT,
    ADD COLUMN IF NOT EXISTS exposure_location    TEXT,
    ADD COLUMN IF NOT EXISTS presence_dates       TEXT,
    ADD COLUMN IF NOT EXISTS wtc_health_program   BOOLEAN;

-- ── GIN/trigram indexes (conditional so missing columns don’t abort migration) ─
CREATE EXTENSION IF NOT EXISTS pg_trgm;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'cases' AND column_name = 'firm_id'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'cases' AND column_name = 'claim_stage'
        ) THEN
            EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cases_claim_stage ON cases(firm_id, claim_stage)';
        END IF;
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'cases' AND column_name = 'vcf_status'
        ) THEN
            EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cases_vcf_status ON cases(firm_id, vcf_status)';
        END IF;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'cases' AND column_name = 'client_name'
    ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cases_client_name_trgm ON cases USING gin (client_name gin_trgm_ops)';
    END IF;
END $$;

-- ── VCF deadlines ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vcf_deadlines (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL,
    case_id       INTEGER NOT NULL,
    deadline_type TEXT NOT NULL,
    due_date      DATE NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    description   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE vcf_deadlines
    ADD COLUMN IF NOT EXISTS firm_id       TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS case_id       INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS deadline_type TEXT NOT NULL DEFAULT 'general',
    ADD COLUMN IF NOT EXISTS due_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS status        TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS description   TEXT,
    ADD COLUMN IF NOT EXISTS created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_vcf_deadlines_case      ON vcf_deadlines(case_id);
CREATE INDEX IF NOT EXISTS idx_vcf_deadlines_due_date  ON vcf_deadlines(firm_id, due_date);
CREATE INDEX IF NOT EXISTS idx_vcf_deadlines_status    ON vcf_deadlines(firm_id, status);

ALTER TABLE vcf_deadlines ENABLE ROW LEVEL SECURITY;
ALTER TABLE vcf_deadlines FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS vcf_deadlines_tenant_isolation ON vcf_deadlines;
CREATE POLICY vcf_deadlines_tenant_isolation ON vcf_deadlines
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── VCF disbursements ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vcf_disbursements (
    id                  SERIAL PRIMARY KEY,
    firm_id             TEXT NOT NULL,
    case_id             INTEGER NOT NULL UNIQUE,
    gross_award         NUMERIC(12,2) DEFAULT 0,
    attorney_fee_pct    NUMERIC(5,2)  DEFAULT 10.0,
    attorney_fee_amount NUMERIC(12,2) DEFAULT 0,
    medicare_lien       NUMERIC(12,2) DEFAULT 0,
    medicaid_lien       NUMERIC(12,2) DEFAULT 0,
    workers_comp_lien   NUMERIC(12,2) DEFAULT 0,
    other_lien          NUMERIC(12,2) DEFAULT 0,
    other_lien_desc     TEXT,
    net_to_claimant     NUMERIC(12,2) DEFAULT 0,
    status              TEXT DEFAULT 'pending',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE vcf_disbursements
    ADD COLUMN IF NOT EXISTS firm_id             TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS case_id             INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS gross_award         NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS attorney_fee_pct    NUMERIC(5,2)  DEFAULT 10.0,
    ADD COLUMN IF NOT EXISTS attorney_fee_amount NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS medicare_lien       NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS medicaid_lien       NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS workers_comp_lien   NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS other_lien          NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS other_lien_desc     TEXT,
    ADD COLUMN IF NOT EXISTS net_to_claimant     NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS status              TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_vcf_disbursements_case ON vcf_disbursements(case_id);

ALTER TABLE vcf_disbursements ENABLE ROW LEVEL SECURITY;
ALTER TABLE vcf_disbursements FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS vcf_disbursements_tenant_isolation ON vcf_disbursements;
CREATE POLICY vcf_disbursements_tenant_isolation ON vcf_disbursements
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── Grants (uncomment and adjust role name to match migration 007_app_role.sql) ─
-- GRANT SELECT, INSERT, UPDATE, DELETE ON vcf_deadlines      TO app_role;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON vcf_disbursements  TO app_role;
-- GRANT USAGE, SELECT ON SEQUENCE vcf_deadlines_id_seq      TO app_role;
-- GRANT USAGE, SELECT ON SEQUENCE vcf_disbursements_id_seq  TO app_role;
