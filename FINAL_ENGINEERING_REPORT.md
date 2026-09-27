# ControlSurface final engineering report

Report date: 2026-09-27

Owner and maintainer: Dev Chiniwala

Repository: `DevChiniwala/ControlSurface` (`main`, private at audit time)

Status: **locally verified v0.1.0-rc.1 source candidate; remote CI and binary artifact clearance remain**

## Project status

ControlSurface implements and verifies its defining loop:

```text
Python SDK
  → authenticated OTLP ingest
  → durable compressed inbox
  → ClickHouse raw traces + AgentRunGraph
  → Production Health and SLO degradation
  → deterministic failure cluster
  → incident with inspectable change evidence
  → reviewed production-derived regression
  → paired baseline/candidate evaluation
  → reproducible BLOCK/PASS release evidence
```

The full synthetic refund-agent workflow passes on a fresh Compose stack. The first-boot readiness blocker is fixed and passed twice on independent volumes. Browser deep links, recovery, outage behavior, large-trace rendering, dependency audits, and reproducible benchmarks have been exercised. This is a serious self-hosted single-owner release candidate, not a production HA or managed multi-tenant release.

## Implemented features

### Foundation

- Docker Compose with PostgreSQL 17, ClickHouse 25.8, one-shot migrations, API, separate OTLP receiver, projection worker, standalone Next.js web runtime, and opt-in benchmark service.
- Base images pinned by digest; Python runtime dependencies pinned exactly.
- API/ingest/web/database host ports bound to loopback.
- Authenticated readiness and dependency ordering; failed migration keeps dependent services stopped.
- PostgreSQL advisory locks for concurrency-sensitive setup, schema, incident, regression, dataset, and trace-projection paths.

### Observe

- OTLP/HTTP protobuf/JSON and OTLP/gRPC trace ingestion authenticated by project key.
- Sessions, agent runs, model, tool, retrieval, memory, retry, sub-agent, workflow, error, event, token, supplied-cost, provider, and environment attributes.
- Preserved raw spans, trace summaries, session lookup, full-window aggregates, and versioned replacement for late spans.
- Trace list/search and dense three-part trace detail: execution tree, transcript/timeline, contextual inspector.
- Detail API exposes truncation metadata and safely supports 10,000 source spans; the browser tree is bounded to 2,000 rows and transcript to 160 events.

### AgentRunGraph

- Framework-independent normalized graph stored separately from source telemetry.
- Node kinds for agent, model, tool, retrieval, memory, retry, sub-agent, approval, workflow, and unknown operations.
- Parent/child, sequence, delegation, and retry relationships when source evidence permits.
- Derived features for tool sequence, repeated tools, retry count, step count, termination, and outcome.
- Any failing child span correctly propagates a failed graph outcome.

### Evaluate

- Datasets and revisioned dataset items.
- Exact output, JSON Schema, completion, maximum-step, required-tool, and forbidden-tool checks.
- Trusted local Python evaluator hook and deterministic fixtures.
- Paired baseline/candidate files with duplicate/missing-case validation and comparable metrics.
- Evaluation stays outside ingestion; V1 execution is local CLI/CI rather than a server job service.

### Monitor

- 24-hour per-agent health aggregation.
- Completion-rate, tool-success-rate, and p95-latency SLO policies with minimum sample thresholds.
- Healthy/degraded/SLO-burn/incident presentation foundations.
- Operational tool schema/version data and tool-call behavior in traces.
- Configurable ClickHouse trace/summary/graph TTL through `CS_TRACE_RETENTION_DAYS`.

### Diagnose

- Bounded deterministic failure signatures and clusters.
- Representative execution selection instead of one test per duplicate failure.
- First-class incidents, affected-run evidence, dominant cluster, related traces, and chronological evidence.
- Change Ledger for deployments, prompts, models, tools, schemas, retrievers, environment, and version changes.
- Tool schema fingerprinting plus structural breaking-change classification.
- Ranked root-cause candidates with timing/match evidence and explicit scoring. Scores are association evidence, not causal proof.

### Improve

- Incident/cluster/trace to editable regression review.
- Captured source trace, failure signature, input, expected behavior, affected-run evidence, and review requirement.
- Per-project deduplication and revisioned suite export.
- Human review required before a production failure becomes an assertion.

### Ship

- Candidate comparison and gate policy with thresholds and critical-case checks.
- Machine-readable exit status for CI.
- Immutable API-level ReleaseEvidence record with content SHA-256.
- Frozen baseline/candidate versions, dataset and suite revisions, evaluator versions, prompt/tool hashes, model/sampling/pricing/environment configuration, policy, individual results, regressions, and decision.
- Evidence verification function and CLI output suitable for release automation.

### Operator experience

- Owner-password reset with exact-owner validation and browser-session revocation.
- Coordinated PostgreSQL custom dump plus ClickHouse native backup with SHA-256 manifest.
- Restore only into a fresh Compose project with no containers or volumes.
- Inbox status, dead-letter visibility, explicit bounded requeue, forward-only rollback policy, and outage runbook.
- `controlsurface doctor` for API, databases, migrations, and project-key validation.

## Architecture

ControlSurface is an understandable modular monolith with separate processes where failure isolation matters:

```text
SDK / OTLP client
  → receiver
  → compressed PostgreSQL telemetry_inbox
  → worker
  → ClickHouse spans, summaries, agent_run_graphs

PostgreSQL metadata
  ←→ project-scoped FastAPI control plane
  ←→ Next.js web application / Python CLI
```

PostgreSQL owns identity, keys, operational metadata, Change Ledger, tool schemas, SLOs, datasets, incidents, regressions, and evidence. ClickHouse owns high-volume source facts and projections. Redis and a message broker are deliberately absent. The durable inbox stores compressed OTLP batches rather than one row per span; acknowledgement happens after the PostgreSQL commit.

Ingestion and API are separate processes. ClickHouse failure does not immediately stop ingest while bounded inbox capacity remains. Worker retry is bounded and observable. The SDK exporter is asynchronous and fail-safe, accepting that queued telemetry may be lost during abrupt process termination.

## Repository structure

| Path | Responsibility |
| --- | --- |
| `apps/web` | Next.js application, reusable investigation components, browser E2E |
| `services/controlplane` | FastAPI, auth, OTLP receiver, worker, domain logic, migrations, operator CLI |
| `sdk/python` | Instrumentation SDK, evaluator, release gate, user CLI |
| `examples/refund_agent` | Synthetic healthy/broken/fixed demo lifecycle |
| `tests/e2e` | Disposable real-service hero acceptance test |
| `benchmarks` | System, browser, clustering, scale, storage, and inbox harnesses |
| `deploy/clickhouse` | Native backup-disk configuration |
| `scripts/recovery.py` | Coordinated backup and fresh-project restore |
| `docs` | Operations and exact release audit |
| `.github/workflows` | Quality and disposable hero E2E jobs |

## UI foundation chosen

The application UI is independently authored for ControlSurface. No third-party product application shell, component, CSS, text, asset, or implementation file was adapted. Commodity open-source runtime packages are consumed through package managers under their own licenses.

Production Health—not traces—is the landing experience. The information hierarchy is health → incident → failure cluster → representative run → raw trace. The visual system uses deep navy/charcoal surfaces, white and muted blue-gray typography, electric blue/violet brand accents, semantic status colors, compact typography, thin borders, restrained glow, dense tables, and bounded motion.

## UI components adapted

None from the private research material. Generic icons come from Lucide through its public package. All first-party brand, shell, layout, execution, incident, regression, and release components are ControlSurface work.

## Original UI work

- Responsive dark application shell, grouped sidebar, project selector, top breadcrumb/context bar, mobile navigation, command palette, and error/retry state.
- Continuous-canvas authentication with ControlSurface brand mark, blue/violet product visualization, responsive compact health preview, and no template split-screen treatment.
- Production Health metric strip, agent rows, active incident evidence, recent release decision, and recent run table.
- Execution tree, agent-oriented transcript, waterfall timeline, contextual span tabs, session story panel, dataset inspector, incident evidence/timeline, regression review, release evidence, Change Ledger, SLO table, API-key modal/reveal, empty states, skeletons, and errors.
- Deep links for `/overview`, `/traces`, `/traces/[traceId]`, `/sessions/[sessionId]`, `/incidents`, `/incidents/[incidentId]`, `/datasets`, `/regressions`, `/releases/[releaseId]`, `/slos`, `/changes`, `/settings/api-keys`, and `/failure-clusters`.
- Browser history-aware close behavior, global session-expiry handling, focus containment for panels/forms, visible focus, semantic dialogs/tabs, and 390px overflow checks.

The main authenticated orchestrator remains a large client component even after extracting execution, inspector, session, command-palette, auth-visual, and focus modules. Further route-specific component extraction is maintainability work, not a release blocker.

## Backend and databases

The API uses strongly validated request models, project-scoped authentication dependencies, explicit CSRF for owner-session mutations, parameterized SQL, bounded query results, and structured HTTP failures. Large control-plane JSON bodies are rejected above 2 MiB. Login uses a bounded process-local sliding-window limiter.

PostgreSQL migrations are forward-only and idempotent. ClickHouse DDL creates raw spans, replacing trace summaries, and replacing graph projections. Trace updates compute aggregates across the full stored window while graph materialization remains bounded. Per-trace advisory locking prevents concurrent late batches from racing a complete projection.

## Telemetry

The receiver validates trace/span ID lengths, timestamps/durations, decompression expansion, nesting, span count, authorization, and inbox capacity. It rejects trailing gzip data and invalid content types. Attribute redaction covers common secret keys, bearer values, cookies, authorization, and common secret URL query names. Redaction is intentionally documented as best-effort.

Raw resource, scope, span, attributes, events, and links stay available independently of derived ControlSurface semantics. No proprietary transformation replaces the source telemetry.

## Python SDK

`ControlSurface.init()` validates a non-credential-bearing HTTP(S) endpoint and requires a project key. Batch export uses bounded queue/batch/timeouts and does not raise exporter failures into agent code. Explicit `session`, `run`, and typed `span` contexts propagate normalized attributes. Recursive structured-attribute redaction limits depth/size and masks common secret keys and bearer/query values.

The SDK is not yet published to a package index. Automatic framework instrumentation and a TypeScript SDK are deferred.

## Evaluation

Deterministic evaluation is implemented and used by the release workflow. Candidate processes and optional evaluators are trusted local subprocesses; they are not safe for hostile code. Server-side asynchronous jobs, a sandbox, general judge providers, and human-review queues are deferred.

## SLO and reliability

Health and SLO computation is real and backed by ClickHouse trace/graph facts. Current views use a 24-hour window and minimum samples. Persistent rolling windows, error-budget history, burn alerts, and an always-on incident proposal engine are the next major differentiator.

## Failure clustering

Clustering uses deterministic bounded features rather than an LLM call per span. Signatures include outcome, termination, tool sequence, repeated tools, retry behavior, failed operation, and error type/text. Recent failures group into stable populations with bounded representatives. A 2,000-run/20-cluster synthetic benchmark measured 5.222 ms p50 and 6.088 ms p95 on the audited machine.

## Incidents and root cause

Incidents link affected runs, SLO evidence, cluster evidence, representative traces, and explicit change candidates. Tool/schema identity and temporal distance influence the score. Evidence is visible and individually inspectable. Cohort analysis and richer durable incident state/resolution remain for v0.2.

## Regression system

Production failures are mined at the cluster level. Representative candidates are editable and review-required. Accepted cases keep source IDs and enter revisioned suites. Concurrent duplicate creation is serialized. The browser workflow verifies the incident → review → representative trace transition and the CLI verifies suite export/evaluation.

## Release gate

Gate inputs are validated for matching IDs, uniqueness, required manifest fields, supported thresholds, and critical cases. The resulting evidence is content-addressed and reproducible. It is immutable through the API, not tamper-proof from a privileged database administrator. External signing/witnessing is deferred.

## CLI

Working commands include `doctor`, `eval run`, `gate`, `incidents list`, `regression create`, and `regression export`. CLI JSON/suite/result size and structure are bounded. Invalid input produces a clean nonzero result. A blocked gate exits nonzero; a passing gate exits zero.

## Test results

Latest local results:

- Ruff lint and format: pass across server, SDK, example, tests, benchmarks, and scripts.
- mypy: pass across 23 backend/SDK/operator source files.
- Backend/SDK unit suite: **57 passed**; remaining warnings are dependency deprecations.
- TypeScript typecheck, ESLint, Prettier: pass.
- Standalone Next.js production build: pass.
- Fresh-stack migration replay: pass.
- Full hero E2E: **1 passed in 107.84 seconds**.
- Chromium product workflow: **1 passed** after repair of incident-to-regression route state.
- Real-service login throttling: pass at the 20-attempt boundary with positive `Retry-After`.
- First boot: pass twice on independent clean project/volume sets.
- Service logs during hero flow: no matching traceback/error/critical/panic/fatal/unhandled output.

CI defines a `quality` job and a dependent disposable `hero-e2e` job. The remote workflow must pass on the exact final commit before tagging.

## Benchmarks

Audited environment: Python 3.13.15, Linux 6.6.87.2 under WSL2, single-node Docker Compose, loopback, synthetic data.

| Measurement | p50 | p95 |
| --- | ---: | ---: |
| SDK manual span scope | 0.029 ms | 0.093 ms |
| OTLP acknowledgement | 48.730 ms | 105.534 ms |
| Send-to-projection | 3,370.651 ms | 5,857.643 ms |
| Trace list (50) | 25.173 ms | 32.520 ms |
| Trace detail (1K) | 145.438 ms | 156.202 ms |
| Trace detail (10K) | 1,122.591 ms | 1,257.100 ms |
| Browser render (1K) | 422.881 ms | 462.987 ms |
| Browser render (10K source / 2K tree) | 1,555.740 ms | 1,877.091 ms |
| Clustering (2K failures) | 5.646 ms | 5.769 ms |

Measured throughput was 1,245.94 spans/second. Dedicated projection took 779.735 ms for 1K and 1,290.130 ms for 10K spans. The 21K-span storage delta was 714,056 bytes, a sample-normalized estimate of 34,002,667 bytes per million spans. These are not capacity claims.

## Security status

Implemented: Argon2, dummy-hash timing behavior, password rehash, hashed/revocable keys, digested sessions, CSRF, project isolation, strict CORS, security headers, request/ingest bounds, safe SQL, redaction, loopback, non-root images, pinned dependency manifest, and process-local login throttling.

Known limits: trusted single-owner host, no SSO/RBAC, no built-in TLS, no distributed limiter, incomplete free-text secret detection, trusted evaluator subprocesses, and privileged-operator access to data/evidence. `SECURITY.md` defines the exact trust boundary.

## Recovery status

The release audit performed a real coordinated backup and restored it into a new project. Checksums matched; PostgreSQL and ClickHouse counts matched exactly. Owner reset revoked six sessions. Worker, ClickHouse, and API outage probes all recovered, with three synthetic traces visible afterward. Migration rollback is forward-only restore-to-fresh, not automated down migration.

## Provenance status

The private audit/provenance material remains outside this repository. ControlSurface first-party implementation is independent. Repository-wide policy scanning returns zero forbidden reference-project names in first-party public files. No source history was imported.

## License status

Original source uses Apache-2.0. Direct and important transitive dependencies are recorded in `THIRD_PARTY_NOTICES.md`. Exact image SBOMs and installed package-license metadata were reviewed, while npm runtime and pinned Python runtime vulnerability audits report zero known vulnerabilities as of the audit date. Public binary/container publication remains blocked on assembling the required base-image/native license texts and corresponding-source/relinking compliance materials, especially for LGPL/GPL components.

## Known limitations

- Single-owner self-hosted profile; no production HA, failover, or multi-region durability.
- No server-side asynchronous evaluation queue or hostile-code sandbox.
- No persistent error-budget history or always-on incident proposal engine.
- Structural schema compatibility can miss semantic behavior changes.
- Evidence is not externally signed and a privileged operator can rewrite databases.
- Telemetry redaction cannot discover every free-text or encoded secret.
- General framework auto-instrumentation and TypeScript SDK are not implemented.
- The main web orchestrator should be split further as route complexity grows.
- No public Python or container artifact is published.

## Deferred features

Enterprise SSO/RBAC, billing, Kubernetes operator, automatic rollback, traffic router, marketplace, many SDKs, coding-agent specialization, broad alerts, and a marketing site are deferred until the always-on reliability loop is proven.

## Local run instructions

1. Copy `.env.example` to `.env` and replace all three secrets.
2. Run `docker compose up --build -d --wait`.
3. Confirm `migrate` exited 0 and all long-running services are healthy/running.
4. Open `http://localhost:3000`, create the owner/project, and create a project key.
5. Install `sdk/python` locally and run `controlsurface doctor`.
6. Follow `examples/refund_agent/README.md` for the closed-loop demo.

## Demo instructions

Use the deterministic refund-agent mode. Show healthy Production Health, register the deliberate payment schema break, emit failure traffic, inspect the cluster/incident/change evidence, open a representative execution, review the mined regression, evaluate the fixed candidate, and open the passing release evidence. Do not substitute invented UI metrics or paid-provider claims.

## GitHub readiness

The local source candidate is ready to commit and push to the existing private repository once the final staged secret/naming checks pass. After push, require both remote workflows to pass. Making the source repository public and tagging `v0.1.0-rc.1` are appropriate only after that result. Publishing Python/container artifacts is a separate decision and is not approved by this report.

## Top 20 next issues

1. Run and require the remote quality and hero-E2E workflows on the candidate commit.
2. Record the 60–90 second real-product refund lifecycle demo.
3. Generate an exact container/package SBOM and finish binary license/notice clearance.
4. Persist rolling SLO windows, error budgets, and burn rates.
5. Build bounded scheduled failure-population clustering.
6. Add automatic incident proposals with deduplication and review.
7. Add durable incident acknowledgement, resolution, and timeline state.
8. Add affected/unaffected cohort comparison to change evidence.
9. Deepen tool/MCP contract compatibility and blast-radius analysis.
10. Report sanitized release-gate results on pull requests.
11. Split the main authenticated web orchestrator into route-specific feature components.
12. Add automated accessibility checks and keyboard tests for every overlay/form.
13. Expand browser coverage for empty, error, retry, expired-session, and outage states.
14. Add sustained-load and long-running storage/merge benchmarks.
15. Add a hardened remote deployment profile with TLS/proxy guidance and distributed rate limits.
16. Build isolated asynchronous evaluation workers and reproducible evaluator environments.
17. Add external signing/witnessing for release evidence.
18. Add the TypeScript SDK after telemetry contract fixtures stabilize.
19. Add selected high-value framework integrations without changing core semantics.
20. Re-run clean install, restore, outage, benchmark, vulnerability, secret, and license audits for every release candidate.
