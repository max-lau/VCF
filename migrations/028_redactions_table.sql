-- migrations/028_redactions_table.sql
-- Ensure the redactions table exists for the Redaction module.
-- This table stores outputs of text and PDF redactions.

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

CREATE INDEX IF NOT EXISTS idx_redactions_firm ON redactions(firm_id, created_at DESC);
