CREATE TABLE IF NOT EXISTS trace_summaries (
    project_id UUID,
    trace_id FixedString(32),
    session_id String,
    agent_name String,
    agent_version String,
    root_name String,
    start_time DateTime64(9, 'UTC'),
    end_time DateTime64(9, 'UTC'),
    duration_ms UInt64,
    span_count UInt32,
    error_count UInt32,
    input_tokens UInt64,
    output_tokens UInt64,
    cost_nano_usd UInt64,
    status LowCardinality(String),
    updated_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (project_id, trace_id)
SETTINGS index_granularity = 8192
