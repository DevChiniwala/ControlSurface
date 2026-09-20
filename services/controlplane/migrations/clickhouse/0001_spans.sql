CREATE TABLE IF NOT EXISTS spans (
    project_id UUID,
    trace_id FixedString(32),
    span_id FixedString(16),
    parent_span_id String,
    name String,
    start_ns UInt64,
    end_ns UInt64,
    start_time DateTime64(9, 'UTC'),
    status LowCardinality(String),
    operation LowCardinality(String),
    session_id String,
    agent_name String,
    agent_version String,
    tool_name String,
    model_name String,
    input_tokens UInt64,
    output_tokens UInt64,
    cost_nano_usd UInt64,
    resource_json String CODEC(ZSTD(3)),
    scope_json String CODEC(ZSTD(3)),
    attributes_json String CODEC(ZSTD(3)),
    events_json String CODEC(ZSTD(3)),
    links_json String CODEC(ZSTD(3)),
    ingested_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(start_time)
ORDER BY (project_id, trace_id, span_id)
SETTINGS index_granularity = 8192
