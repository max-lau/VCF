-- Migration 008: Rebuild esign tables to match application schema
-- Date: 2026-07-07
-- Root cause: esign_requests / esign_signers were created by an earlier
--   DocuSign-era DDL (uuid PKs, no subject/message/provider/sign_token cols).
--   The current code's CREATE TABLE IF NOT EXISTS in esignature.py is a no-op
--   against the existing tables, so the live schema never caught up.
--   GET /esign/requests 500s with: column r.subject does not exist.
-- Safety: both tables verified empty (0 rows) on 2026-07-07 before drop.

BEGIN;

DROP TABLE IF EXISTS esign_signers CASCADE;
DROP TABLE IF EXISTS esign_requests CASCADE;

-- Recreated to exactly match init_esign_tables() in backend/demo1/esignature.py
CREATE TABLE esign_requests (
    id SERIAL PRIMARY KEY,
    firm_id TEXT NOT NULL,
    case_id INT,
    document_name TEXT NOT NULL,
    document_id INT,
    document_text TEXT,
    subject TEXT,
    message TEXT,
    provider TEXT NOT NULL DEFAULT 'email',
    status TEXT NOT NULL DEFAULT 'pending',
    docusign_envelope_id TEXT,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE esign_signers (
    id SERIAL PRIMARY KEY,
    request_id INT NOT NULL REFERENCES esign_requests(id) ON DELETE CASCADE,
    firm_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'signer',
    status TEXT NOT NULL DEFAULT 'pending',
    sign_token TEXT UNIQUE,
    signed_at TIMESTAMPTZ,
    signature_text TEXT,
    signature_image TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_esign_requests_firm ON esign_requests (firm_id);
CREATE INDEX idx_esign_signers_firm ON esign_signers (firm_id);
CREATE INDEX idx_esign_signers_request ON esign_signers (request_id);

-- Ownership + RLS: match migration 005/007 posture
ALTER TABLE esign_requests OWNER TO paraiq_app;
ALTER TABLE esign_signers OWNER TO paraiq_app;
ALTER SEQUENCE esign_requests_id_seq OWNER TO paraiq_app;
ALTER SEQUENCE esign_signers_id_seq OWNER TO paraiq_app;

ALTER TABLE esign_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE esign_requests FORCE ROW LEVEL SECURITY;
ALTER TABLE esign_signers ENABLE ROW LEVEL SECURITY;
ALTER TABLE esign_signers FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON esign_requests
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

CREATE POLICY tenant_isolation ON esign_signers
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

COMMIT;
