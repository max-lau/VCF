-- reset_demo_data.sql
-- Run this in the Supabase SQL Editor to wipe all client/case/demo data.
-- Keeps users, roles, firm config, and audit logs.
-- Skips any tables that do not exist in this project.
-- WARNING: destructive — make sure you don't need the data.

DO $$
DECLARE
    tbl text;
    tables text[] := ARRAY[
        'case_documents',
        'case_notes',
        'case_tags',
        'case_briefs',
        'case_contradictions',
        'claim_stage_history',
        'claim_checklists',
        'vcf_account_prep',
        'vcf_deadlines',
        'vcf_disbursements',
        'contact_matters',
        'contacts',
        'communications',
        'intake_scans',
        'intake_jobs',
        'redactions',
        'transcriptions',
        'parsed_messages',
        'discovery_files',
        'discovery_runs',
        'bates_log',
        'bates_configs',
        'email_intakes',
        'email_processing_log',
        'client_portal_access',
        'client_messages',
        'client_enclaves',
        'kanban_card_logs',
        'kanban_cards',
        'kanban_boards',
        'esign_signers',
        'esign_requests',
        'leads',
        'analyses',
        'feedback',
        'ai_work_product',
        'ai_drafts',
        'custom_entity_types',
        'correspondence',
        'depositions',
        'docketing_chains',
        'docketing_confirmations',
        'docketing_events',
        'invoices',
        'invoice_items',
        'legal_bert_analyses',
        'morning_briefs',
        'motions',
        'payments',
        'privilege_log',
        'privilege_verdicts',
        'reports',
        'research_notes',
        'risk_assessments',
        'contracts',
        'approval_queue',
        'attorney_review_gates',
        'webhook_subscriptions',
        'webhook_log',
        'time_entries',
        'time_heartbeats',
        'time_sessions',
        'voice_audit_log',
        'voice_shortcuts',
        'notifications',
        'cases',
        'billing_rates'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            -- Temporarily disable RLS if present, truncate, then re-enable.
            IF EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = tbl AND c.relrowsecurity = true
            ) THEN
                EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', tbl);
            END IF;

            EXECUTE format('TRUNCATE TABLE %I CASCADE', tbl);

            IF EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = tbl AND c.relrowsecurity = true
            ) THEN
                EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
            END IF;
        END IF;
    END LOOP;
END $$;

-- Restart serial IDs so the next case starts from 1.
DO $$
DECLARE
    seq text;
    seqs text[] := ARRAY[
        'cases_id_seq',
        'case_documents_id_seq',
        'intake_scans_id_seq',
        'email_intakes_id_seq',
        'communications_id_seq',
        'vcf_deadlines_id_seq',
        'redactions_id_seq'
    ];
BEGIN
    FOREACH seq IN ARRAY seqs
    LOOP
        IF EXISTS (SELECT 1 FROM pg_class WHERE relname = seq AND relkind = 'S') THEN
            EXECUTE format('ALTER SEQUENCE %I RESTART WITH 1', seq);
        END IF;
    END LOOP;
END $$;
