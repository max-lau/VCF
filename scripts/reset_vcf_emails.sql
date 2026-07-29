-- reset_vcf_emails.sql
-- Clear all assigned VCF emails and restart the sequence at 1.
-- Run in Supabase SQL Editor.

BEGIN;

SELECT set_config('app.current_firm_id', 'waw_vcf', false);

-- Remove all assigned law-firm VCF emails from cases.
UPDATE cases SET vcf_email = NULL;

-- Restart the sequence so the next email is vcfclaim00001@wawvcf.com.
ALTER SEQUENCE IF EXISTS vcf_email_seq RESTART WITH 1;

COMMIT;
