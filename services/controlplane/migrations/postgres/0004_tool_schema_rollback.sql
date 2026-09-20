-- Re-activating an earlier contract is a new change event, not a new fingerprint.
ALTER TABLE tool_schema_versions
    DROP CONSTRAINT IF EXISTS tool_schema_versions_project_id_tool_name_fingerprint_key;
CREATE INDEX IF NOT EXISTS tool_schema_versions_current_idx
    ON tool_schema_versions (project_id, tool_name, created_at DESC);
