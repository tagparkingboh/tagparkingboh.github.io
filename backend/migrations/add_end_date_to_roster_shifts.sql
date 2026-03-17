-- Add end_date column to roster_shifts for overnight shifts
-- Run this migration on the database

ALTER TABLE roster_shifts ADD COLUMN IF NOT EXISTS end_date DATE;

-- Set end_date to date for existing shifts (same-day shifts)
UPDATE roster_shifts SET end_date = date WHERE end_date IS NULL;

-- Create index for end_date
CREATE INDEX IF NOT EXISTS ix_roster_shifts_end_date ON roster_shifts(end_date);
