-- 020_vcf_email_filter_boost.sql
-- Improve VCF email routing: capture client emails and per-firm trusted domains/keywords.

-- Capture the client's email on a case so emails coming directly from the client
-- are recognised as trusted sender domains.
ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS client_email TEXT;

-- Per-firm configuration for the email filter.
ALTER TABLE firm_email_settings
    ADD COLUMN IF NOT EXISTS trusted_domains TEXT[],
    ADD COLUMN IF NOT EXISTS vcf_keywords    TEXT[];

-- Make sure the single-tenant settings row uses the same firm_id as the cases.
-- (The WAW VCF tenant uses 'waw_vcf'; legacy seeding used '1'.)
DO $$
DECLARE
    target_firm_id TEXT;
BEGIN
    SELECT firm_id INTO target_firm_id FROM cases WHERE firm_id IS NOT NULL LIMIT 1;
    IF target_firm_id IS NULL THEN
        target_firm_id := 'waw_vcf';
    END IF;

    UPDATE firm_email_settings
       SET firm_id = target_firm_id
     WHERE firm_id = '1';

    INSERT INTO firm_email_settings (firm_id, trusted_domains, vcf_keywords)
    VALUES (target_firm_id, ARRAY[
        'vcf.gov',
        'wtchealthprogram.org',
        'cdc.gov',
        'cms.gov',
        'medicare.gov',
        'medicaid.gov',
        'health.ny.gov',
        'nyc.gov',
        'downtownmedical.org',
        'riversidecancer.org',
        'nyulangone.org',
        'mountsinai.org',
        'nyp.org',
        'columbiadoctors.org',
        'weillcornell.org'
    ], ARRAY[
        'victim compensation fund', 'vcf', 'wtc health program', 'wtc',
        'medicare', 'medicaid', 'social security', 'ssa',
        'medical records', 'lab results', 'pathology', 'radiology',
        'biopsy', 'oncology', 'treatment records', 'disability',
        'claim', 'claim number', 'claimant', 'exposure zone',
        'certified condition', 'presence proof', 'award determination'
    ])
    ON CONFLICT (firm_id) DO UPDATE SET
        trusted_domains = EXCLUDED.trusted_domains,
        vcf_keywords    = EXCLUDED.vcf_keywords;
END $$;
