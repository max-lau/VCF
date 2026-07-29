-- delete_specific_file.sql
-- Remove a specific intake/document record by filename and case number.
-- Run in Supabase SQL Editor.

BEGIN;

-- Set tenant context for RLS (defense in depth).
SELECT set_config('app.current_firm_id', 'waw_vcf', false);

-- Find the case ID.
DO $$
DECLARE
    target_case_id integer;
    deleted_scans integer := 0;
    deleted_docs integer := 0;
BEGIN
    SELECT id INTO target_case_id
    FROM cases
    WHERE case_number = 'VCF-2026-0001';

    IF target_case_id IS NULL THEN
        RAISE NOTICE 'Case VCF-2026-0001 not found.';
        RETURN;
    END IF;

    RAISE NOTICE 'Found case_id: %', target_case_id;

    -- Delete from intake_scans (this is what the Intake history table shows).
    DELETE FROM intake_scans
    WHERE case_id = target_case_id
      AND filename = 'chen_weiming_intake_questionnaire_zh.png';
    GET DIAGNOSTICS deleted_scans = ROW_COUNT;
    RAISE NOTICE 'Deleted % intake_scan row(s).', deleted_scans;

    -- Delete from case_documents (the case binder / document vault).
    DELETE FROM case_documents
    WHERE case_id = target_case_id
      AND document_name = 'chen_weiming_intake_questionnaire_zh.png';
    GET DIAGNOSTICS deleted_docs = ROW_COUNT;
    RAISE NOTICE 'Deleted % case_document row(s).', deleted_docs;

    IF deleted_scans = 0 AND deleted_docs = 0 THEN
        RAISE NOTICE 'No matching rows found for filename %.', 'chen_weiming_intake_questionnaire_zh.png';
    END IF;
END $$;

COMMIT;
