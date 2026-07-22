-- 016_communications_created_by.sql
-- Safety net: ensure communications table has created_by column.
-- The column is referenced by backend/demo1/communications.py REST endpoint.

ALTER TABLE communications ADD COLUMN IF NOT EXISTS created_by TEXT;
