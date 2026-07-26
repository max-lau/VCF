-- 017_case_documents_routing.sql
-- Phase 2: support universal document-to-case routing.

ALTER TABLE case_documents
    ADD COLUMN IF NOT EXISTS file_url          TEXT,
    ADD COLUMN IF NOT EXISTS doc_type          TEXT DEFAULT 'other',
    ADD COLUMN IF NOT EXISTS identity_signals  JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS match_status      TEXT DEFAULT 'matched',
    ADD COLUMN IF NOT EXISTS scan_id           INTEGER;

-- Allow unmatched documents to sit in the inbox queue before assignment.
ALTER TABLE case_documents ALTER COLUMN case_id DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_case_documents_type      ON case_documents(firm_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_case_documents_match     ON case_documents(firm_id, match_status);
CREATE INDEX IF NOT EXISTS idx_case_documents_scan      ON case_documents(firm_id, scan_id);
CREATE INDEX IF NOT EXISTS idx_case_documents_case_type ON case_documents(firm_id, case_id, doc_type);

-- Foreign-key defense: a case_document may optionally point back to the raw intake scan.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'case_documents'
          AND constraint_name = 'fk_case_documents_scan'
    ) THEN
        ALTER TABLE case_documents
            ADD CONSTRAINT fk_case_documents_scan
            FOREIGN KEY (scan_id) REFERENCES intake_scans(id)
            ON DELETE SET NULL;
    END IF;
END $$;

COMMENT ON COLUMN case_documents.match_status IS
    'matched | auto_created | ambiguous | unmatched | manual';
