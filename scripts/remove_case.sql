-- remove_case.sql
-- Remove a case from dashboards and counts by soft-deleting it.
-- This preserves related records (documents, history) for audit purposes.
-- Run in Supabase SQL Editor.

BEGIN;

SELECT set_config('app.current_firm_id', 'waw_vcf', false);

UPDATE cases
SET deleted = TRUE, updated_at = NOW()
WHERE case_number = 'VCF-2026-0001';

COMMIT;
