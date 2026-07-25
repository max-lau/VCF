-- 021_vcf_dedicated_emails.sql
-- Each claimant gets a unique law-firm email address used ONLY for VCF.gov
-- account creation and VCF correspondence. This is separate from the client's
-- personal email (cases.client_email).

ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS vcf_email TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_vcf_email_unique
    ON cases(vcf_email) WHERE vcf_email IS NOT NULL;

CREATE SEQUENCE IF NOT EXISTS vcf_email_seq START 1;
