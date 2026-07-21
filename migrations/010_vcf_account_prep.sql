-- 010_vcf_account_prep.sql
-- VCF account-creation prep sheets (credentials + security Q&A → sensitive).
-- Follows the project's RLS pattern (see 001/005/007). Run this in Supabase,
-- then init_vcf_account_table() in vcf_account.py becomes a no-op safety net.

CREATE TABLE IF NOT EXISTS vcf_account_prep (
    id           SERIAL PRIMARY KEY,
    firm_id      TEXT NOT NULL,
    case_id      INTEGER,
    client_name  TEXT,
    status       TEXT NOT NULL DEFAULT 'draft',
    -- draft → ready → account_created → verified | abandoned
    demo_mode    BOOLEAN NOT NULL DEFAULT FALSE,
    encrypted    BOOLEAN NOT NULL DEFAULT FALSE,
    prep_blob    TEXT NOT NULL,
    vcf_username TEXT,
    created_by   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vcf_prep_case   ON vcf_account_prep(case_id);
CREATE INDEX IF NOT EXISTS idx_vcf_prep_status ON vcf_account_prep(firm_id, status);

-- RLS: same tenant-scoping convention as the other tables.
ALTER TABLE vcf_account_prep ENABLE ROW LEVEL SECURITY;
ALTER TABLE vcf_account_prep FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS vcf_prep_tenant_isolation ON vcf_account_prep;
CREATE POLICY vcf_prep_tenant_isolation ON vcf_account_prep
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- Grants: match whatever role migration 007_app_role.sql established.
-- Uncomment and adjust the role name to your app role:
-- GRANT SELECT, INSERT, UPDATE ON vcf_account_prep TO app_role;
-- GRANT USAGE, SELECT ON SEQUENCE vcf_account_prep_id_seq TO app_role;
