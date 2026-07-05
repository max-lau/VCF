-- 006_model_runs_tenant_scope.sql
-- Tenant-scope the ML pipeline's run log: model_runs had no firm_id, so training
-- history/metrics were globally visible and un-attributable. Existing rows are
-- demo-era artifacts -> backfilled to 'default'.

BEGIN;

ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS firm_id TEXT NOT NULL DEFAULT 'default';

CREATE INDEX IF NOT EXISTS idx_model_runs_firm ON model_runs(firm_id);

CREATE POLICY tenant_isolation ON model_runs FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

ALTER TABLE model_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_runs FORCE ROW LEVEL SECURITY;

COMMIT;