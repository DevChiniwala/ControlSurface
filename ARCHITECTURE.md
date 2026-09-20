# Architecture

ControlSurface is a local self-hosted modular control plane: Python API, separate OTLP receiver and projection worker, Next.js application, Python SDK/CLI, PostgreSQL, and ClickHouse. Docker Compose runs the stack and a one-shot migration process. There is no Redis, queue broker, Kubernetes operator, or Rust service in V1.

## Data path

```text
SDK / OTLP client
  → authenticated OTLP/HTTP or gRPC receiver
  → validate, redact, bound, compress
  → PostgreSQL telemetry_inbox (durable acknowledgement)
  → asynchronous worker
  → ClickHouse source spans, summaries, AgentRunGraph projections
  → project-scoped API → Production Health and investigation UI
```

Project identity comes from a hashed bearer key, not a client-supplied field. The receiver bounds request and expanded payload size, span count, and pending inbox bytes. A full inbox returns retryable 503. Acknowledgement follows the PostgreSQL write. The worker retries processing and quarantines repeatedly failing batches; completed/dead batches have bounded retention. A ClickHouse outage pauses projection; a PostgreSQL outage prevents acceptance.

PostgreSQL owns owner sessions, projects, key hashes, SLO policies, change events, tool schemas, datasets, incidents, regression cases, and release evidence. ClickHouse owns source span facts, summaries, and graph projections. Resource, scope, span attributes, events, and links remain separate from derived labels. Versioned replacement supports late-span reprojection.

The local benchmark compares a SQLite WAL spool with the compressed PostgreSQL inbox. PostgreSQL is selected for now because spool crash-replay, isolation, and outage behavior have not passed validation. No benchmark result is a production capacity claim.

## Agent run graph and investigation

The worker normalizes spans into `AgentRunGraph` version 1. Nodes classify agent, model, retrieval, memory, tool, retry, sub-agent, approval, workflow, or unknown operations. Edges capture parent/child, sequence, retry-of, and delegation where the source permits. Every node links to source trace/span IDs. Explicit run/session IDs are used when supplied; otherwise a trace-scoped identity is generated.

Graph features include tool sequence, retry count, repeated tools, step count, outcome, and termination reason. Deterministic failure signatures drive bounded recent-failure clustering. Incident analysis ranks nearby change events by timing and matching tool identity. Its `evidence_score` is an inspectable heuristic association, not causal proof or a probability.

The local CLI runs paired baseline/candidate cases in subprocesses. The API gate checks paired IDs and a manifest of versions, revisions, hashes, model configuration, sampling, pricing version, environment, and policy. It stores a content-hashed evidence bundle and returns pass/block status. API-level append-only records are not tamper-proof against a database administrator.

## Boundaries

This is an original ControlSurface UI and single-owner, multi-project local deployment. Evaluation execution is currently local CLI/CI work, not a distributed job service. Incident creation is initiated from a cluster rather than an always-on alert pipeline. Contract classification is structural and may miss semantic incompatibility. Drift, automatic rollback, external notifications, and general retention management are deferred.
