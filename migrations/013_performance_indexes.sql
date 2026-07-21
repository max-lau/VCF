-- 013_performance_indexes.sql
-- Performance indexes for high-volume VCFClaimsIQ operations (10k+ claims).
-- Self-healing: ensures firm_id exists on legacy tables before indexing.

-- Ensure firm_id columns exist on legacy tables (idempotent)
ALTER TABLE cases ADD COLUMN IF NOT EXISTS firm_id TEXT NOT NULL DEFAULT 'default';
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

-- Claim lookup / filtering
CREATE INDEX IF NOT EXISTS idx_cases_firm_status ON cases(firm_id, status);
CREATE INDEX IF NOT EXISTS idx_cases_firm_stage  ON cases(firm_id, claim_stage);
CREATE INDEX IF NOT EXISTS idx_cases_created_at  ON cases(firm_id, created_at DESC);

-- Document lookups
CREATE INDEX IF NOT EXISTS idx_case_documents_case ON case_documents(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_case_documents_source ON case_documents(firm_id, source);

-- Intake scans
CREATE INDEX IF NOT EXISTS idx_intake_scans_firm_created ON intake_scans(firm_id, created_at DESC);

-- Communications
CREATE INDEX IF NOT EXISTS idx_communications_case_sent ON communications(case_id, sent_at DESC);

-- Deadlines
CREATE INDEX IF NOT EXISTS idx_vcf_deadlines_due_status ON vcf_deadlines(firm_id, due_date, status);

-- Trigram search on client name (run 011 first, which creates the GIN index)
-- If pg_trgm is not enabled, enable it:
CREATE EXTENSION IF NOT EXISTS pg_trgm;
