-- 013_performance_indexes.sql
-- Performance indexes for high-volume VCFClaimsIQ operations (10k+ claims).
-- Self-healing: ensures required columns exist on legacy tables before indexing.

-- Ensure required columns exist on legacy tables (idempotent)
ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS firm_id      TEXT NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS claim_stage  TEXT DEFAULT 'intake',
    ADD COLUMN IF NOT EXISTS status       TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS created_at   TIMESTAMPTZ DEFAULT NOW();
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'case_documents'
    ) THEN
        ALTER TABLE case_documents
            ADD COLUMN IF NOT EXISTS firm_id TEXT NOT NULL DEFAULT 'default',
            ADD COLUMN IF NOT EXISTS source  TEXT,
            ADD COLUMN IF NOT EXISTS case_id INTEGER;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'intake_scans'
    ) THEN
        ALTER TABLE intake_scans
            ADD COLUMN IF NOT EXISTS firm_id    TEXT NOT NULL DEFAULT 'default',
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- Claim lookup / filtering (conditional on columns actually existing)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cases' AND column_name='firm_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cases' AND column_name='status') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cases_firm_status ON cases(firm_id, status)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cases' AND column_name='firm_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cases' AND column_name='claim_stage') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cases_firm_stage ON cases(firm_id, claim_stage)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cases' AND column_name='firm_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cases' AND column_name='created_at') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(firm_id, created_at DESC)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='case_documents' AND column_name='case_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='case_documents' AND column_name='created_at') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_case_documents_case ON case_documents(case_id, created_at DESC)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='case_documents' AND column_name='firm_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='case_documents' AND column_name='source') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_case_documents_source ON case_documents(firm_id, source)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='intake_scans' AND column_name='firm_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='intake_scans' AND column_name='created_at') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_intake_scans_firm_created ON intake_scans(firm_id, created_at DESC)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='communications' AND column_name='case_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='communications' AND column_name='sent_at') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_communications_case_sent ON communications(case_id, sent_at DESC)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='vcf_deadlines' AND column_name='firm_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='vcf_deadlines' AND column_name='due_date')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='vcf_deadlines' AND column_name='status') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_vcf_deadlines_due_status ON vcf_deadlines(firm_id, due_date, status)';
    END IF;
END $$;

-- Trigram search on client name (run 011 first, which creates the GIN index)
-- If pg_trgm is not enabled, enable it:
CREATE EXTENSION IF NOT EXISTS pg_trgm;
