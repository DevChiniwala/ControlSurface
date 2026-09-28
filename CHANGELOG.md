# Changelog

All notable changes are recorded here. ControlSurface has not published a package or container release.

## 0.1.0-rc.1 — 2026-09-28

### Added

- Authenticated OTLP/HTTP and OTLP/gRPC ingestion with bounded compressed PostgreSQL batches and asynchronous ClickHouse projection.
- Framework-independent AgentRunGraph linked to immutable source trace/span identifiers.
- Python SDK for sessions, agent runs, models, retrieval, tools, memory, retries, sub-agents, and workflow spans.
- Production Health, SLO policies, deterministic failure clustering, incidents, Change Ledger evidence, and tool-schema compatibility classification.
- Datasets, deterministic evaluators, paired comparison, editable production-derived regressions, revisioned suites, and content-addressed release evidence.
- Dark-first application shell, responsive authentication, execution transcript/timeline, contextual span inspector, command palette, and URL-addressable operational routes.
- Owner-password recovery, session revocation, coordinated PostgreSQL/ClickHouse backup and restore, trace TTLs, inbox status, and dead-letter requeue.
- Reproducible system and browser benchmarks for SDK overhead, ingest/projection, query latency, 1K/10K-span traces, clustering, throughput, and storage growth.
- Security headers, CSRF, login throttling, request/decompression limits, telemetry redaction, and non-root minimal runtime images.

### Changed

- ClickHouse readiness now authenticates against the application database, and migrations use bounded retries before dependent services start.
- Trace summaries use full-window aggregates even when graph projection or UI tree rendering is bounded.
- Trace projection is serialized per trace to prevent late concurrent batches from overwriting a more complete summary.
- API-key creation now uses an accessible in-product modal instead of a browser prompt.
- Runtime dependencies and base images are pinned for the release-candidate build.

### Fixed

- Removed a backend dependency cycle.
- Corrected tool-schema enum compatibility classification and non-finite canonical JSON handling.
- Corrected error outcomes when a child span fails beneath a successful root.
- Preserved incident-to-regression review state across deep-link navigation.
- Prevented recursive execution-tree rendering from overflowing on large or malformed traces.
- Added strict payload, identifier, duration, decompression, CLI input, and release-manifest validation.

### Verified

- Two independent clean-volume Compose boots succeeded on the first invocation.
- The full healthy → broken schema → incident → regression → fixed candidate → passing gate workflow passed.
- Coordinated backup restored exact PostgreSQL and ClickHouse record counts into a new project.
- Owner reset revoked sessions; worker, ClickHouse, and API outage recovery delivered all synthetic probe traces.
- Python lint/format/type/tests, frontend format/lint/type/build, Chromium E2E, dependency audits, and repository-history secret/naming scans pass locally.
