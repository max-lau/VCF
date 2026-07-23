-- 016_intake_scans_case_id.sql
-- Link intake scans to cases for VCF document management.

ALTER TABLE intake_scans
    ADD COLUMN IF NOT EXISTS case_id INTEGER;

-- Defense-in-depth foreign key (intake scans may be deleted independently).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'intake_scans'
          AND constraint_name = 'fk_intake_scans_case'
    ) THEN
        ALTER TABLE intake_scans
            ADD CONSTRAINT fk_intake_scans_case
            FOREIGN KEY (case_id) REFERENCES cases(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_intake_scans_case ON intake_scans(firm_id, case_id);

-- Existing rows remain unlinked (case_id NULL) until manually assigned or reprocessed.
