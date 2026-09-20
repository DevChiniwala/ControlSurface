# ControlSurface engineering report

Status: **local pre-release candidate, not public-release sign-off** · 2026-09-20. No GitHub push or package publication has occurred. This report distinguishes verified behavior from remaining release gates.

## Project status

The deterministic closed loop passed on a fresh disposable Docker stack: Python SDK → authenticated OTLP → durable inbox → ClickHouse traces and agent-run graph → Production Health → breaking payment-tool schema → failure cluster → incident with ranked change evidence → reviewed production-derived regression → broken candidate BLOCK → fixed candidate PASS → content-hashed release evidence. The latest clean-stack end-to-end test completed in 94.85 seconds and also verified captured model output and payment-tool arguments in the stored trace. The test-only stack and its volumes were removed afterward; the development volumes were retained.

This proves a representative local path, not production readiness. Browser interaction, large-scale performance, remote deployment security, and binary redistribution reviews remain open.

## Architecture and repository structure

ControlSurface is an original modular Python control plane, separate OTLP receiver and projection worker, Next.js/TypeScript application, Python SDK/CLI, PostgreSQL, and ClickHouse. Docker Compose runs these plus one-shot migrations. No Redis, Rust service, Kubernetes operator, or paid model service is required. See [ARCHITECTURE.md](ARCHITECTURE.md).

| Path | Purpose |
| --- | --- |
| `apps/web` | Production Health application and investigation workflows |
| `services/controlplane` | API, auth, OTLP receiver, worker, domain services, migrations, tests |
| `sdk/python` | Fail-safe instrumentation SDK, deterministic evaluator, CLI |
| `examples/refund_agent` | Synthetic healthy/broken/fixed agent lifecycle; optional live model adapter |
| `tests/e2e` | Disposable full-stack hero acceptance test |
| `benchmarks` | Local durable-inbox comparison harness |
| `compose.yaml` | Loopback-bound development deployment |

## UI foundation, adapted components, and original UI work

The application and shell are independently authored. **No UI source, components, styles, assets, or text were adapted from private research material.** Production Health is the landing page; traces are supporting evidence. Functional surfaces include traces/sessions, clusters/incidents, Change Ledger, regression review, datasets and items, release-evidence inspection, SLO policies, and API keys. Trace detail shows the execution tree and contextual tabs for captured input/output, model settings, tokens/cost, tool arguments/results, retrieval, errors, events, and metadata. The dataset item and evidence-detail panels have passing APIs, TypeScript checks, and production build, but their full browser interactions have not yet been automated. A browser screenshot exposed and led to a corrected auth-brand layout; the authenticated application has not had complete visual QA.

## Backend and databases

PostgreSQL owns the single owner account, multiple projects, hashed/revocable API keys, compressed batch inbox, SLO policies, Change Ledger, tool-schema versions, datasets, incidents, regression cases, and release evidence. ClickHouse stores source span facts, trace summaries, and versioned graph projections. Migrations run on startup and were re-run against the clean stack. The receiver acknowledges only after a bounded PostgreSQL write; the worker retries projection and quarantines repeatedly failing batches. There is no production HA or cross-region durability claim.

## Telemetry and SDK

The receiver accepts authenticated OTLP/HTTP and OTLP/gRPC trace exports, validates/bounds/redacts them, and stores source and derived projections separately. The Python SDK provides explicit session, agent-run, and typed spans for model, retrieval, tool, memory, retry, sub-agent, and other operations. Its OpenTelemetry batch exporter fails safely when the endpoint is unavailable, at the cost of possible telemetry loss. General framework auto-instrumentation, metrics/logs ingestion, and a TypeScript SDK are deferred. The SDK package is installed locally; it has not been published.

## Evaluation

The CLI evaluates local trusted candidates in subprocesses. Built-in checks cover expected output, JSON Schema, completion, step limits, required/forbidden tools, and optional trusted Python evaluators. Paired result files support deterministic baseline/candidate comparison. Server-side asynchronous evaluation jobs, hostile-code sandboxing, and operational LLM-judge execution are not complete.

## SLO and reliability monitoring

Production Health aggregates observed runs in a 24-hour window and applies minimum-sample SLO policies for completion, tool success, and p95 latency. It can surface an incident state. Tool-schema fingerprints and structural compatibility classification feed the Change Ledger. Persistent error-budget accounting, drift analysis, and a general signal/alert runtime are deferred.

## Failure clustering, incidents, and root cause

The worker normalizes raw spans into a framework-independent AgentRunGraph linked to source IDs. Deterministic features include tool sequence, retry/repetition, steps, outcome, and termination. Recent failed runs are grouped by bounded signatures with representative traces. Incident analysis ranks explicit nearby changes, matching tool identity, and time proximity. Every candidate exposes its supporting facts. An evidence score is an association heuristic, **not a causal probability or proof**. Affected/unaffected cohort analysis and a richer incident timeline remain open.

## Regression system

Representative failures yield editable, review-required regression candidates. Accepted cases retain source trace and cluster identities and are deduplicated in a revisioned suite export. The clean-stack test exported the production suite, evaluated healthy/broken/fixed candidates against it, and obtained BLOCK/PASS decisions. Human review is required because a failed output is not automatically a correct expected assertion.

## Release gate and CLI

The gate validates paired case IDs, rejects duplicates, applies versioned thresholds and critical-case checks, and freezes versions, suite/dataset revisions, evaluator versions, prompt/tool hashes, model configuration, sampling, pricing, environment, policy, individual results, and decision in a SHA-256-addressed bundle. The API is append-only and idempotent by project/hash; it is not tamper-proof against a database administrator. The CLI implements `doctor`, `eval run`, `gate`, `incidents list`, `regression create`, and `regression export`. Broken candidates return nonzero status; fixed candidates return zero status.

## Test results

- Python unit/SDK suite: **22 passed**, with the opt-in end-to-end test skipped in the ordinary run; one Python 3.16 deprecation warning from a dependency.
- Disposable Docker full-stack hero test: **1 passed in 94.85 seconds** on the latest run. It exercised project isolation, dataset API, OTLP ingest, captured model/tool context, Health, graph/cluster/incident/change evidence, regression suite export, paired evaluations, BLOCK/PASS gates, manifest hashes, and evidence verification.
- Ruff lint/format, full backend/SDK mypy (20 source files), web TypeScript typecheck, Prettier check, and Next.js production build pass locally.
- GitHub Actions defines quality and disposable full-stack jobs, but it has not yet run on the eventual public repository. Full authenticated browser E2E and accessibility tests are not present.

## Benchmarks

A single local run of `benchmarks/inbox.py` used 200 synthetic compressed batches of approximately 2,075 bytes each. Measured throughput / p95 acknowledgement: SQLite WAL 218.3 batches/s / 6.378 ms; PostgreSQL fresh-connection 47.9 batches/s / 25.624 ms; PostgreSQL pooled 364.5 batches/s / 3.736 ms. These tiny measurements are **not** production capacity claims. Worker throughput, end-to-end projection latency, ClickHouse insert/query latency, storage growth, SDK overhead, and evaluation throughput still need controlled workloads. The PostgreSQL inbox remains because a local disk spool has not passed crash replay, isolation, or outage validation.

## Security, provenance, and license status

Current controls include Argon2 owner-password hashes, hashed project keys, project-scoped APIs, bound SQL parameters, ingress limits, redaction foundations, loopback-bound Compose ports, HttpOnly/SameSite browser sessions, and configured CORS. Limitations include no explicit CSRF token or request rate limit, incomplete remote-deployment hardening and retention controls, potentially sensitive telemetry, and trusted local evaluator execution. See [SECURITY.md](SECURITY.md).

The private research archives, audits, and provenance ledger are outside this repository. No source was copied or adapted from them. The project declares Apache-2.0 for original code. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) records important runtime licenses, including LGPL components in database and image-processing dependencies. An artifact-specific transitive/container license and notice review is still required before publishing binary images. No secret, prohibited-reference-brand, or dependency-audit claim is final until repeated on the exact commit proposed for release.

## Known limitations and deferred features

This is a self-hosted single-owner/multiple-project local V1, not a hardened multi-user hosted service. Online evaluation jobs, general LLM judges, advanced drift, persistent error budgets, broad framework auto-instrumentation, coding-agent integrations, comprehensive alert delivery, managed retention, backup/restore automation, and distributed ingestion are deferred. The UI has no fully automated authenticated browser suite. There is no published Python package or container image.

## Local run and demo

Follow [README.md](README.md): set independent `.env` secrets, run `docker compose up --build`, create the owner/project, install `sdk/python` locally, create a key, then run `controlsurface doctor`. Follow [the refund-agent example](examples/refund_agent/README.md) for healthy traffic, controlled schema break, incident/regression review, and production-suite release gates. Synthetic mode uses no paid API. Its optional live-model mode transmits text to a provider and can incur charges.

## GitHub readiness

**Not ready to push.** The scripted closed loop is verified, but authenticated browser interaction, dependency/container licensing, secret scanning of a proposed commit, remote-deployment security, operator recovery procedures, and broader performance validation remain open. Do not treat this report as a public-release approval.

## Top 20 next issues

1. Automate authenticated browser paths for Health → incident → representative run → regression → evidence.
2. Verify dataset item creation and release-evidence detail in the browser at desktop and narrow widths.
3. Add keyboard/focus and accessibility tests across overlays, forms, trace tree, and navigation.
4. Add explicit CSRF protection and request rate limiting before any remote deployment.
5. Threat-model telemetry capture, redaction, and secrets embedded in free text or URLs.
6. Publish operator backup, restore, and retention procedures; test restore from real volumes.
7. Complete transitive Python/npm and base-image license/NOTICE review for each binary artifact.
8. Add reproducible dependency locks and security update policy for Python packages.
9. Measure OTLP acknowledgement and end-to-end projection latency under controlled load.
10. Benchmark ClickHouse insert, trace-list/detail query latency, and storage per million spans.
11. Measure SDK overhead and loss behavior during endpoint or process failure.
12. Stress-test inbox backpressure, worker retry/quarantine, and ClickHouse outages.
13. Add OTLP/gRPC and SDK contract fixtures for malformed, duplicate, and late spans.
14. Expand graph normalization fixtures across agent frameworks and branching/retry semantics.
15. Add incident affected/unaffected cohort comparison to strengthen change rankings.
16. Add a durable incident timeline and explicit resolution workflow.
17. Persist error-budget burn and build a bounded signal evaluation loop.
18. Build asynchronous server-side evaluation jobs with isolation and reproducible artifacts.
19. Add a release-evidence verification command and optional external witness/signature.
20. Re-run the clean-stack test, CI, provenance, secret, and licensing reviews on the exact release commit before publishing.
