-- Fixes RLS policies created with wrong session variable name.
-- Both attorney_review_gates and user_security_keys were created using
-- current_setting('app.current_firm', true) instead of the correct
-- 'app.current_firm_id' set by TenantMiddleware, causing these policies
-- to silently return zero rows for all requests.

DROP POLICY IF EXISTS "Firm isolation for review gates" ON attorney_review_gates;
CREATE POLICY "Firm isolation for review gates"
ON attorney_review_gates FOR ALL
USING (firm_id = current_setting('app.current_firm_id', true))
WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

DROP POLICY IF EXISTS "Firm isolation for security keys" ON user_security_keys;
CREATE POLICY "Firm isolation for security keys"
ON user_security_keys FOR ALL
USING (firm_id = current_setting('app.current_firm_id', true))
WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
