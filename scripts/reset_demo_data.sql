-- reset_demo_data.sql
-- Run this in the Supabase SQL Editor to wipe all client/case/demo data.
-- Keeps users, roles, firm config, and audit logs.
-- WARNING: destructive — make sure you don't need the data.

BEGIN;

TRUNCATE TABLE
  case_documents,
  case_notes,
  case_tags,
  case_briefs,
  case_contradictions,
  claim_stage_history,
  claim_checklists,
  vcf_account_prep,
  vcf_deadlines,
  vcf_disbursements,
  contact_matters,
  contacts,
  communications,
  intake_scans,
  intake_jobs,
  redactions,
  transcriptions,
  parsed_messages,
  discovery_files,
  discovery_runs,
  bates_log,
  bates_configs,
  email_intakes,
  email_processing_log,
  client_portal_access,
  client_messages,
  client_enclaves,
  kanban_card_logs,
  kanban_cards,
  kanban_boards,
  esign_signers,
  esign_requests,
  leads,
  analyses,
  feedback,
  ai_work_product,
  ai_drafts,
  custom_entity_types,
  correspondence,
  depositions,
  docketing_chains,
  docketing_confirmations,
  docketing_events,
  invoices,
  invoice_items,
  legal_bert_analyses,
  morning_briefs,
  motions,
  payments,
  privilege_log,
  privilege_verdicts,
  reports,
  research_notes,
  risk_assessments,
  contracts,
  approval_queue,
  attorney_review_gates,
  webhook_subscriptions,
  webhook_log,
  time_entries,
  time_heartbeats,
  time_sessions,
  voice_audit_log,
  voice_shortcuts,
  notifications,
  cases,
  billing_rates
CASCADE;

-- Restart serial IDs so the next case starts from 1.
ALTER SEQUENCE IF EXISTS cases_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS case_documents_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS intake_scans_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS email_intakes_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS communications_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS vcf_deadlines_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS redactions_id_seq RESTART WITH 1;

COMMIT;
