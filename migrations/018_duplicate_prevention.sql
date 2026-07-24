-- 018_duplicate_prevention.sql
-- Phase 2 follow-up: detect duplicate uploads by content hash.

ALTER TABLE intake_scans
    ADD COLUMN IF NOT EXISTS content_hash TEXT;

ALTER TABLE case_documents
    ADD COLUMN IF NOT EXISTS content_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_intake_scans_content_hash ON intake_scans(firm_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_case_documents_content_hash ON case_documents(firm_id, content_hash);

COMMENT ON COLUMN intake_scans.content_hash IS 'SHA-256 of uploaded file bytes; used for duplicate detection';
COMMENT ON COLUMN case_documents.content_hash IS 'SHA-256 of uploaded file bytes; mirrors intake_scans for duplicate detection';
