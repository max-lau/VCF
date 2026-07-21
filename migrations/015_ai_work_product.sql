-- 015_ai_work_product.sql
-- Creates the ai_work_product table referenced by backend/demo1/main.py.
-- Migration 005_force_rls.sql already adds RLS policy/force directives for it,
-- but the CREATE TABLE was missing from the migration chain.

CREATE TABLE IF NOT EXISTS ai_work_product (
    id            SERIAL PRIMARY KEY,
    firm_id       TEXT NOT NULL DEFAULT 'default',
    case_id       INTEGER,
    user_id       INTEGER,
    endpoint      TEXT NOT NULL,
    input_preview TEXT,
    result_json   JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_work_product_firm_endpoint
    ON ai_work_product(firm_id, endpoint);
CREATE INDEX IF NOT EXISTS idx_ai_work_product_case
    ON ai_work_product(case_id);
CREATE INDEX IF NOT EXISTS idx_ai_work_product_created_at
    ON ai_work_product(created_at DESC);

ALTER TABLE ai_work_product ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_work_product FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON ai_work_product;
CREATE POLICY tenant_isolation ON ai_work_product FOR ALL
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── Grants (uncomment and adjust role name to match migration 007_app_role.sql) ─
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ai_work_product TO app_role;
-- GRANT USAGE, SELECT ON SEQUENCE ai_work_product_id_seq TO app_role;
