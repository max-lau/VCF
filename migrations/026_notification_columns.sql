-- 026_notification_columns.sql
-- Phase 2: extend notifications table with structured notification fields.
-- The notifications_router already expects type/title/body/link; this migration
-- adds them safely to existing tables that only had message/user_id/read.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'type'
    ) THEN
        ALTER TABLE notifications ADD COLUMN type TEXT NOT NULL DEFAULT 'general';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'title'
    ) THEN
        ALTER TABLE notifications ADD COLUMN title TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'body'
    ) THEN
        ALTER TABLE notifications ADD COLUMN body TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'link'
    ) THEN
        ALTER TABLE notifications ADD COLUMN link TEXT;
    END IF;
END $$;

-- Backfill legacy rows so the router can still render them.
UPDATE notifications SET title = COALESCE(title, message), body = COALESCE(body, message) WHERE title IS NULL OR body IS NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(firm_id, type, created_at DESC);
