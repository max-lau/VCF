-- 017_communications_comm_type.sql
-- Safety net: ensure communications table has a comm_type column.
-- Legacy log_communication() uses email/sms; the REST endpoint maps channel into it.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'communications' AND column_name = 'comm_type'
    ) THEN
        ALTER TABLE communications ADD COLUMN comm_type TEXT NOT NULL DEFAULT 'other';
    ELSE
        -- Existing comm_type column may be NOT NULL without a default; make it safe.
        ALTER TABLE communications ALTER COLUMN comm_type SET DEFAULT 'other';
        ALTER TABLE communications ALTER COLUMN comm_type DROP NOT NULL;
    END IF;
END $$;
