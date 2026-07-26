-- 027_dedupe_scans.sql
-- Remove existing duplicate intake scans / case documents and enforce
-- uniqueness on (firm_id, content_hash) so future duplicate uploads are
-- rejected or deduplicated automatically.

-- 1. Clean duplicate intake_scans rows, keeping the oldest id per firm+hash.
DELETE FROM intake_scans
WHERE id NOT IN (
    SELECT MIN(id)
    FROM intake_scans
    WHERE firm_id IS NOT NULL
      AND content_hash IS NOT NULL
      AND content_hash <> ''
    GROUP BY firm_id, content_hash
);

-- 2. Clean duplicate case_documents rows, keeping the oldest id per firm+hash.
DELETE FROM case_documents
WHERE id NOT IN (
    SELECT MIN(id)
    FROM case_documents
    WHERE firm_id IS NOT NULL
      AND content_hash IS NOT NULL
      AND content_hash <> ''
    GROUP BY firm_id, content_hash
);

-- 3. Add unique constraints so ON CONFLICT can dedupe future inserts.
-- PostgreSQL does not support ADD CONSTRAINT IF NOT EXISTS, so we guard
-- with an explicit existence check.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'intake_scans'
          AND constraint_name = 'unique_intake_scans_firm_hash'
    ) THEN
        ALTER TABLE intake_scans
            ADD CONSTRAINT unique_intake_scans_firm_hash
            UNIQUE (firm_id, content_hash);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'case_documents'
          AND constraint_name = 'unique_case_documents_firm_hash'
    ) THEN
        ALTER TABLE case_documents
            ADD CONSTRAINT unique_case_documents_firm_hash
            UNIQUE (firm_id, content_hash);
    END IF;
END $$;
