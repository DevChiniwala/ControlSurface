CREATE TABLE IF NOT EXISTS agent_run_graphs (
    project_id UUID,
    run_id String,
    trace_id FixedString(32),
    session_id String,
    graph_version UInt16,
    graph_json String CODEC(ZSTD(3)),
    features_json String CODEC(ZSTD(3)),
    outcome LowCardinality(String),
    updated_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (project_id, run_id)
SETTINGS index_granularity = 8192
