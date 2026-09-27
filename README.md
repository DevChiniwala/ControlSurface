# ControlSurface

<p align="center">
  <img src="assets/controlsurface-banner.svg" alt="ControlSurface turns production telemetry into agent reliability and release decisions" width="100%" />
</p>

<p align="center">
  <strong>Production engineering for AI agents.</strong><br />
  Observe → Evaluate → Monitor → Diagnose → Improve → Ship
</p>

<p align="center">
  <a href="https://github.com/DevChiniwala/ControlSurface/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/DevChiniwala/ControlSurface/actions/workflows/ci.yml/badge.svg" /></a>
  <a href="LICENSE"><img alt="Apache 2.0" src="https://img.shields.io/badge/license-Apache--2.0-4F6BFF" /></a>
</p>

Production failures become incidents. Incidents become regression tests. Regression tests become release decisions.

ControlSurface connects OpenTelemetry traces, framework-independent agent execution graphs, SLOs, explicit production changes, failure clusters, regression suites, and immutable release evidence. Raw telemetry remains inspectable; every derived diagnosis and gate decision links back to its evidence.

> **Release-candidate status.** The complete synthetic failure-to-fixed-release workflow, clean first boot, browser journey, backup/restore rehearsal, outage recovery, and reproducible benchmarks pass locally. The Python package and container images are not published. This is a single-owner self-hosted release candidate, not a managed or high-availability service.

## Why ControlSurface

Most telemetry systems answer “what happened?” ControlSurface continues the engineering loop:

```text
authenticated production telemetry
              ↓
 framework-independent AgentRunGraph
              ↓
    SLO and failure intelligence
              ↓
 incident + inspectable change evidence
              ↓
 deduplicated production-derived regression
              ↓
     baseline/candidate evaluation
              ↓
 content-addressed release evidence
              ↓
          SHIP or BLOCK
```

Four concepts anchor the product:

- **AgentRunGraph** normalizes model calls, tools, retrieval, memory, retries, sub-agents, approvals, outcomes, and state transitions while preserving the source spans.
- **Change Ledger** records deployments, prompts, models, tool contracts, retrievers, environments, and versions as explicit evidence for incident analysis.
- **Production-derived regressions** mine representative failures from a cluster for human review instead of producing hundreds of duplicate tests.
- **Release evidence** freezes baseline and candidate versions, suite and dataset revisions, evaluator versions, prompt/tool hashes, model configuration, policy, results, and decision under a content hash.

Root-cause rankings are evidence scores, never claims of causal proof.

## What works today

| Area | Release-candidate capability |
| --- | --- |
| Observe | Authenticated OTLP/HTTP and OTLP/gRPC, sessions, raw spans, 10K-span detail API, model/tool/retrieval/agent semantics, latency, errors, tokens, and supplied costs |
| Normalize | Versioned AgentRunGraph projections linked to raw trace/span IDs, with bounded execution-tree rendering |
| Evaluate | Datasets and items, exact/schema/step/tool assertions, trusted local Python evaluators, paired baseline/candidate comparison |
| Monitor | 24-hour agent health, completion/tool-success/latency SLOs, minimum samples, and health states |
| Diagnose | Deterministic failure signatures, clusters, representative traces, incidents, tool-schema classification, and ranked nearby changes |
| Improve | Editable, review-required, source-linked regression candidates and revisioned suite export |
| Ship | Deterministic CLI gate, critical-case policies, machine exit status, SHA-256 evidence bundle, and evidence verification |
| Operate | First-boot-safe migrations, retention TTLs, inbox backpressure, owner reset, coordinated backup/restore, dead-letter inspection/requeue, and outage recovery guidance |

The web application opens on **Production Health**, then drills down through incident → failure cluster → representative agent run → raw trace. URL-addressable routes support deep links for overview, traces, sessions, incidents, datasets, regressions, releases, SLOs, changes, and API keys.

## Quick start

Requirements: Docker with Compose, Python 3.11+ for the SDK/CLI, and free local ports `3000`, `8000`, `4317`, `4318`, `55432`, and `58123`. All Compose ports bind to loopback.

```bash
git clone https://github.com/DevChiniwala/ControlSurface.git
cd ControlSurface
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env`. Replace all three placeholder values in `.env` with independent random secrets, then start the stack:

```bash
docker compose up --build -d --wait
docker compose ps -a
```

The one-shot `migrate` service must exit with code 0. Open [http://localhost:3000](http://localhost:3000), create the owner and first project with the bootstrap token from `.env`, then create a project API key. The plaintext key is shown once.

Endpoints:

| Service | Local endpoint |
| --- | --- |
| Application | `http://localhost:3000` |
| Control API | `http://localhost:8000` |
| OTLP/HTTP traces | `http://localhost:4318/v1/traces` |
| OTLP/gRPC | `localhost:4317` |

The authenticated ClickHouse readiness probe and bounded migration retry remove the previous first-boot race: two independent clean-volume boots passed on the first Compose invocation during the release audit.

## Instrument a Python agent

The package is installed from this checkout until a package artifact is published:

```bash
python -m pip install -e sdk/python
```

Set `CONTROLSURFACE_API_KEY` to the project key. Instrumentation is explicit and fail-safe:

```python
from controlsurface import ControlSurface

cs = ControlSurface.init(
    endpoint="http://localhost:4318",
    api_key="<project-key>",
    agent_name="support-agent",
    agent_version="v19",
    environment="production",
)

try:
    with cs.session():
        with cs.run("support-request", input="I was charged twice"):
            with cs.span("policy-search", kind="retrieval"):
                pass
            with cs.span("lookup-transactions", kind="tool"):
                pass
finally:
    cs.shutdown()
```

Exporter batching happens off the application path. An unavailable endpoint does not fail agent work, but queued telemetry can be lost during process termination or a long outage. Prompt and tool content are not captured automatically; explicitly supplied input and attributes may be sensitive. Read [SECURITY.md](SECURITY.md) before using real data.

Validate connectivity without emitting a trace:

```bash
controlsurface doctor
```

## Run the hero workflow

The [customer-support refund agent](examples/refund_agent/README.md) uses synthetic data and a deterministic model fixture by default. It demonstrates:

```text
healthy traffic
  → breaking payments.refund schema
  → Production Health degradation
  → failure cluster
  → incident + change evidence
  → representative run
  → reviewed regression
  → broken candidate BLOCK
  → fixed candidate PASS
```

Set `CONTROLSURFACE_PROJECT_ID` and `CONTROLSURFACE_API_KEY`, then run:

```bash
python examples/refund_agent/demo.py
```

The opt-in live-model adapter is separately documented and may transmit content or incur provider charges. The default workflow requires no paid API.

## Architecture

```text
Python SDK / authenticated OTLP client
  → OTLP receiver
  → bounded compressed PostgreSQL inbox
  → asynchronous projection worker
  → ClickHouse raw spans + summaries + AgentRunGraph

PostgreSQL
  → identity, projects, keys, SLOs, changes, tool schemas
  → datasets, incidents, regressions, release evidence

project-scoped API
  → Next.js application and CLI
```

PostgreSQL provides durable acknowledgement and operational metadata. ClickHouse owns high-volume telemetry and derived graph projections. Projection failure never makes the instrumented request wait; the worker retries, then quarantines repeatedly failing batches. See [ARCHITECTURE.md](ARCHITECTURE.md) for boundaries, idempotency, backpressure, and graph semantics.

| Path | Purpose |
| --- | --- |
| [`apps/web`](apps/web) | Dark-first Next.js application and Chromium workflow |
| [`services/controlplane`](services/controlplane) | API, OTLP receivers, worker, migrations, domain logic |
| [`sdk/python`](sdk/python) | Instrumentation SDK, deterministic evaluators, CLI |
| [`examples/refund_agent`](examples/refund_agent) | Synthetic healthy/broken/fixed lifecycle |
| [`tests/e2e`](tests/e2e) | Disposable full-stack acceptance path |
| [`benchmarks`](benchmarks) | Reproducible SDK, ingest, query, rendering, clustering, and storage measurements |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Readiness, backup/restore, retention, outage, and migration policy |

## Measured performance

One reproducible local run on 2026-09-27 measured **1,245.94 spans/second**, **48.730 ms p50 OTLP acknowledgement**, **3.371 s p50 send-to-projection**, **145.438 ms p50 1K-span trace detail**, and **1,122.591 ms p50 10K-span trace detail**. Browser route-to-render measured **422.881 ms p50** for 1K rows and **1,555.740 ms p50** for a 10K-source-span trace with a deliberately bounded 2K-row tree.

These are synthetic single-machine measurements, not capacity or production-sizing claims. Hardware, workload, complete p95 results, storage caveats, and reproduction commands are in [benchmarks/README.md](benchmarks/README.md).

## Operations and recovery

- `CS_TRACE_RETENTION_DAYS` configures bounded ClickHouse TTLs for spans, summaries, and run graphs.
- `scripts/recovery.py backup` creates coordinated PostgreSQL and ClickHouse archives with SHA-256 checksums.
- Restore refuses existing projects/volumes and targets a fresh Compose project.
- The offline owner reset revokes every browser session while preserving project API keys.
- `inbox-status` and explicit dead-letter requeue support operator recovery.

The release audit restored a seeded installation into a new project with exact counts, reset the owner password, and recovered telemetry through worker, ClickHouse, and API outages. Follow [docs/OPERATIONS.md](docs/OPERATIONS.md); rehearse with your own encrypted backup system before production use.

## Security and release status

Current controls include Argon2 password hashing, hashed high-entropy project keys, session-bound CSRF protection, project isolation, parameterized SQL, input and decompression limits, telemetry redaction foundations, strict CORS, security headers, process-local login throttling, non-root runtime images, loopback bindings, and pinned release-container dependencies/base-image digests.

The trust model is intentionally narrow: a trusted single owner operates a trusted host. There is no enterprise SSO/RBAC, hostile evaluator sandbox, distributed rate limiter, built-in TLS termination, or protection from a privileged database/host operator. Free-text redaction is not complete. See [SECURITY.md](SECURITY.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and the exact [release audit](docs/RELEASE_AUDIT.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before sending a change. CI runs Python formatting/lint/type/tests, frontend formatting/lint/type/build, a clean Compose boot, migration replay, the complete hero workflow, authenticated Chromium navigation, and login throttling. Do not commit customer telemetry, `.env`, API keys, generated evidence, copied third-party application code, or fabricated benchmark results.

ControlSurface is created and maintained by **Dev Chiniwala**. Original ControlSurface source is licensed under [Apache-2.0](LICENSE); dependencies retain their own licenses.
