-- 005_force_rls.sql
-- Makes RLS real: the app connects as 'postgres' (table owner), which BYPASSES RLS
-- unless FORCE ROW LEVEL SECURITY is set. As of 2026-07-04, 0/80 tables were forced.
--
-- GROUP 1: Tenant tables with existing policies -> FORCE only.
-- GROUP 2: client_messages: policy exists but RLS never enabled -> ENABLE + FORCE.
-- GROUP 3: Tenant tables with ZERO policies -> add policy, then FORCE.
-- GROUP 4: AUTH-CRITICAL (users, token_blocklist): policy added, NOT forced --
--   these are read during login before any JWT/firm context exists.
--   Owner bypass (postgres) keeps auth working; non-owner roles are constrained.

BEGIN;

-- ===== GROUP 1: FORCE only =====
ALTER TABLE ai_config                FORCE ROW LEVEL SECURITY;
ALTER TABLE ai_drafts                FORCE ROW LEVEL SECURITY;
ALTER TABLE ai_token_usage           FORCE ROW LEVEL SECURITY;
ALTER TABLE ai_work_product          FORCE ROW LEVEL SECURITY;
ALTER TABLE approval_queue           FORCE ROW LEVEL SECURITY;
ALTER TABLE attorney_review_gates    FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_log                FORCE ROW LEVEL SECURITY;
ALTER TABLE bates_configs            FORCE ROW LEVEL SECURITY;
ALTER TABLE bates_log                FORCE ROW LEVEL SECURITY;
ALTER TABLE billing_rates            FORCE ROW LEVEL SECURITY;
ALTER TABLE calendar_events          FORCE ROW LEVEL SECURITY;
ALTER TABLE case_briefs              FORCE ROW LEVEL SECURITY;
ALTER TABLE case_contradictions      FORCE ROW LEVEL SECURITY;
ALTER TABLE case_documents           FORCE ROW LEVEL SECURITY;
ALTER TABLE case_notes               FORCE ROW LEVEL SECURITY;
ALTER TABLE case_tags                FORCE ROW LEVEL SECURITY;
ALTER TABLE cases                    FORCE ROW LEVEL SECURITY;
ALTER TABLE client_enclaves          FORCE ROW LEVEL SECURITY;
ALTER TABLE client_portal_access     FORCE ROW LEVEL SECURITY;
ALTER TABLE contact_matters          FORCE ROW LEVEL SECURITY;
ALTER TABLE contacts                 FORCE ROW LEVEL SECURITY;
ALTER TABLE contracts                FORCE ROW LEVEL SECURITY;
ALTER TABLE correspondence           FORCE ROW LEVEL SECURITY;
ALTER TABLE depositions              FORCE ROW LEVEL SECURITY;
ALTER TABLE discovery_files          FORCE ROW LEVEL SECURITY;
ALTER TABLE discovery_runs           FORCE ROW LEVEL SECURITY;
ALTER TABLE docketing_chains         FORCE ROW LEVEL SECURITY;
ALTER TABLE docketing_confirmations  FORCE ROW LEVEL SECURITY;
ALTER TABLE docketing_events         FORCE ROW LEVEL SECURITY;
ALTER TABLE intake_scans             FORCE ROW LEVEL SECURITY;
ALTER TABLE invoice_items            FORCE ROW LEVEL SECURITY;
ALTER TABLE invoices                 FORCE ROW LEVEL SECURITY;
ALTER TABLE kanban_card_logs         FORCE ROW LEVEL SECURITY;
ALTER TABLE kanban_cards             FORCE ROW LEVEL SECURITY;
ALTER TABLE legal_bert_analyses      FORCE ROW LEVEL SECURITY;
ALTER TABLE morning_briefs           FORCE ROW LEVEL SECURITY;
ALTER TABLE motions                  FORCE ROW LEVEL SECURITY;
ALTER TABLE notifications            FORCE ROW LEVEL SECURITY;
ALTER TABLE parsed_messages          FORCE ROW LEVEL SECURITY;
ALTER TABLE payments                 FORCE ROW LEVEL SECURITY;
ALTER TABLE privilege_log            FORCE ROW LEVEL SECURITY;
ALTER TABLE privilege_verdicts       FORCE ROW LEVEL SECURITY;
ALTER TABLE prompt_guard_log         FORCE ROW LEVEL SECURITY;
ALTER TABLE redactions               FORCE ROW LEVEL SECURITY;
ALTER TABLE reports                  FORCE ROW LEVEL SECURITY;
ALTER TABLE research_notes           FORCE ROW LEVEL SECURITY;
ALTER TABLE tenant_ai_config         FORCE ROW LEVEL SECURITY;
ALTER TABLE time_entries             FORCE ROW LEVEL SECURITY;
ALTER TABLE time_heartbeats          FORCE ROW LEVEL SECURITY;
ALTER TABLE time_sessions            FORCE ROW LEVEL SECURITY;
ALTER TABLE transcriptions           FORCE ROW LEVEL SECURITY;
ALTER TABLE user_security_keys       FORCE ROW LEVEL SECURITY;
ALTER TABLE voice_audit_log          FORCE ROW LEVEL SECURITY;
ALTER TABLE voice_shortcuts          FORCE ROW LEVEL SECURITY;
ALTER TABLE workflows                FORCE ROW LEVEL SECURITY;

-- ===== GROUP 2: client_messages (policy exists, RLS never enabled) =====
ALTER TABLE client_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE client_messages FORCE  ROW LEVEL SECURITY;

-- ===== GROUP 3: add missing policies, then FORCE =====
CREATE POLICY tenant_isolation ON ai_output_validation_log FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE ai_output_validation_log FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON attorney_email_accounts FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE attorney_email_accounts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON communications FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE communications FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON email_intakes FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE email_intakes FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON email_processing_log FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE email_processing_log FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON esign_requests FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE esign_requests FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON esign_signers FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE esign_signers FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON firm_email_settings FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE firm_email_settings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON leads FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE leads FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON role_assignments FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
ALTER TABLE role_assignments FORCE ROW LEVEL SECURITY;

-- ===== GROUP 4: AUTH-CRITICAL -- policy added, DELIBERATELY NOT FORCED =====
-- users + token_blocklist are read during login/JWT validation, BEFORE any
-- firm context exists. Forcing them would break all logins. The postgres owner
-- bypass keeps auth working; any future non-owner app role is still constrained.
CREATE POLICY tenant_isolation ON users FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

CREATE POLICY tenant_isolation ON token_blocklist FOR ALL
  USING (firm_id = current_setting('app.current_firm_id', true))
  WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

COMMIT;

-- Not touched (no firm_id, legacy/global): analyses, custom_entity_types,
-- feedback, firms, model_runs, module_permissions, notify_config, notify_log,
-- risk_assessments, roles, webhook_log, webhook_subscriptions
-- DEBT: 'analyses' stores raw document text with no tenant scoping -- trace writers.