ALTER TABLE telemetry_inbox ADD COLUMN IF NOT EXISTS dead_letter_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS telemetry_inbox_dead_letter_idx
    ON telemetry_inbox (dead_letter_at) WHERE dead_letter_at IS NOT NULL;
