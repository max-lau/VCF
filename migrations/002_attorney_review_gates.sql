-- Run this in Supabase SQL Editor
CREATE TABLE IF NOT EXISTS attorney_review_gates (
    id SERIAL PRIMARY KEY,
    firm_id TEXT NOT NULL,
    doc_id INTEGER NOT NULL,
    attorney_id TEXT NOT NULL,
    reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_at TIMESTAMPTZ,
    UNIQUE(firm_id, doc_id)
);

ALTER TABLE attorney_review_gates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Firm isolation for review gates" 
ON attorney_review_gates FOR ALL 
USING (firm_id = current_setting('app.current_firm', true));
