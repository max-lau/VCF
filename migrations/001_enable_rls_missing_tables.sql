-- Migration: Enable RLS on tables missing tenant isolation
-- Tables: ai_token_usage, client_messages, prompt_guard_log, tenant_ai_config
-- Flagged by Supabase Advisor as CRITICAL (RLS Disabled in Public)
-- Pattern: matches existing tenant_isolation policies via app.current_firm_id
--          (set per-request by TenantMiddleware, requires is_local=false)
--
-- IMPORTANT: rename this file to match your migrations folder sequence
-- before applying, e.g. 018_enable_rls_missing_tables.sql

BEGIN;

-- ai_token_usage --------------------------------------------------------
ALTER TABLE public.ai_token_usage ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_ai_token_usage ON public.ai_token_usage;
CREATE POLICY tenant_isolation_ai_token_usage ON public.ai_token_usage
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- client_messages --------------------------------------------------------
ALTER TABLE public.client_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_client_messages ON public.client_messages;
CREATE POLICY tenant_isolation_client_messages ON public.client_messages
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- prompt_guard_log --------------------------------------------------------
ALTER TABLE public.prompt_guard_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_prompt_guard_log ON public.prompt_guard_log;
CREATE POLICY tenant_isolation_prompt_guard_log ON public.prompt_guard_log
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- tenant_ai_config --------------------------------------------------------
ALTER TABLE public.tenant_ai_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_tenant_ai_config ON public.tenant_ai_config;
CREATE POLICY tenant_isolation_tenant_ai_config ON public.tenant_ai_config
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

COMMIT;

-- Verification ------------------------------------------------------------
-- Run after applying to confirm RLS is on and policies exist:
--
-- SELECT tablename, rowsecurity
-- FROM pg_tables
-- WHERE schemaname = 'public'
--   AND tablename IN ('ai_token_usage', 'client_messages', 'prompt_guard_log', 'tenant_ai_config');
--
-- SELECT tablename, policyname, cmd
-- FROM pg_policies
-- WHERE schemaname = 'public'
--   AND tablename IN ('ai_token_usage', 'client_messages', 'prompt_guard_log', 'tenant_ai_config');
