-- 028_vcf_calendar.sql
-- Adapt calendar_events for VCFClaimsIQ: link to cases, drop litigation-only
-- concepts, and backfill from the legacy event_date column.

-- Add columns the backend expects, if they don't already exist.
ALTER TABLE calendar_events
    ADD COLUMN IF NOT EXISTS case_id      INTEGER,
    ADD COLUMN IF NOT EXISTS due_date     DATE,
    ADD COLUMN IF NOT EXISTS due_time     TIME,
    ADD COLUMN IF NOT EXISTS location     TEXT,
    ADD COLUMN IF NOT EXISTS status       TEXT DEFAULT 'upcoming',
    ADD COLUMN IF NOT EXISTS reminder_days INTEGER DEFAULT 3,
    ADD COLUMN IF NOT EXISTS attendees    TEXT,
    ADD COLUMN IF NOT EXISTS is_court_date BOOLEAN DEFAULT FALSE;

-- Backfill due_date from the old event_date column (only if event_date exists).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'calendar_events' AND column_name = 'event_date'
    ) THEN
        UPDATE calendar_events SET due_date = event_date WHERE due_date IS NULL;
    END IF;
END $$;

-- Default any remaining NULL due_date rows so the calendar doesn't break.
UPDATE calendar_events SET due_date = CURRENT_DATE WHERE due_date IS NULL;

-- Make matter_id nullable so old rows don't break; new VCF code uses case_id.
ALTER TABLE calendar_events ALTER COLUMN matter_id DROP NOT NULL;

-- Index for case-based lookups.
CREATE INDEX IF NOT EXISTS idx_calendar_events_case ON calendar_events(firm_id, case_id);
CREATE INDEX IF NOT EXISTS idx_calendar_events_due  ON calendar_events(firm_id, due_date);
