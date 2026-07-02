-- Fixes RLS policy on workflows table created with wrong session variable name.
-- Was using current_setting('app.current_firm', true) instead of the correct
-- 'app.current_firm_id' set by TenantMiddleware, causing the policy to
-- silently return zero rows for all requests. Table is currently orphaned
-- (workflows_router.py was never created/committed) but fixed preemptively
-- so it's not a landmine when the real router is built.

DROP POLICY IF EXISTS "Firm isolation for workflows" ON workflows;
CREATE POLICY "Firm isolation for workflows"
ON workflows FOR ALL
USING (firm_id = current_setting('app.current_firm_id', true))
WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
