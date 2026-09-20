# Roadmap

## V1 acceptance gate

The release is not ready until one repeatable local run demonstrates: instrument → authenticated OTLP ingest → ClickHouse and agent-run graph → Production Health/SLO → breaking tool schema and clustered failure → incident with inspectable change evidence → reviewed representative regression case → fixed candidate evaluation → reproducible release gate. This path needs integration and end-to-end tests, not only a narrated demo.

The current pre-release build has the services, SDK, web surfaces, deterministic CLI evaluator, and release-evidence API. The full deterministic refund-agent path passed on a fresh disposable Docker stack on 2026-09-20, including production-derived regression export and blocked/fixed release gates. One Chromium journey also covers investigation, dataset and release detail, logout, and real sign-in through the redesigned auth screen. This validates one path, not every interaction, security hardening, or production-scale performance. Individual passing checks do not imply public release readiness.

## Near-term work

1. Extend browser interaction tests beyond the current happy path to empty, loading, error, and retry states across the visible navigation.
2. Expand integration/contract tests across PostgreSQL, ClickHouse, OTLP/HTTP and gRPC, SDK, project isolation, and migration replay.
3. Complete the operational-page visual redesign after the auth/theme phase, then verify keyboard access, responsive layout, trace detail, and every visible action in a browser.
4. Measure ingest acknowledgement, worker throughput, end-to-end projection latency, trace/query latency, storage growth, and SDK overhead under controlled workloads. Publish only measured results with hardware and configuration context.
5. Strengthen SLO computation, change-exposure cohorts, incident timeline, regression deduplication, and tool contract coverage.
6. Complete platform-specific dependency/image license and secret scans, document operator backup/retention procedures, and review default security controls before public release.

## After V1

Broader SDK/framework integrations, managed multi-user deployment, advanced drift analysis, coding-agent telemetry, external alert delivery, durable large-scale ingestion options, and long-term retention policies are deferred until the core closed loop is proven.
