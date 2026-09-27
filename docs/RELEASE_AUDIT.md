# v0.1.0-rc.1 release audit

Audit date: 2026-09-27

Scope: local source tree and locally built Linux/amd64 Compose artifacts

Status: **local release-candidate checks pass; remote CI and binary-publication review remain**

This record reports executed checks. It is not a promise that defects cannot exist, a security certification, or legal advice.

## Source and policy

- Fresh Git history belongs to ControlSurface and uses Dev Chiniwala's configured identity.
- Repository-wide case-insensitive naming-policy scan: **0 matches**.
- High-confidence key/private-key/token regex scan outside ignored build environments: **0 matches**.
- Gitleaks v8.24.2 repository-history scan: **10 commits, approximately 761 KB, no leaks found**.
- `.env`, virtual environments, caches, dependencies, build outputs, browser artifacts, and generated evidence are ignored by Git; `.env` and dependency caches are excluded from Docker contexts.
- `git diff --check`: clean at the audited worktree stage. Repeat after final staging/commit.

## Build and automated tests

| Check | Result |
| --- | --- |
| Ruff lint and format (server, SDK, example, tests, benchmarks, scripts) | Pass |
| mypy (server, SDK, recovery operator) | Pass, 23 source files |
| Backend and SDK unit tests | Pass, 57 tests |
| TypeScript type check | Pass |
| ESLint | Pass |
| Prettier | Pass |
| Next.js standalone production build | Pass |
| Python dependency consistency (`pip check`) | Pass |
| Full Python hero workflow | Pass, 107.84 s on fresh stack |
| Authenticated Chromium product workflow | Pass, 6.8 s |
| Real-service login throttle | Pass, limit and `Retry-After` verified |

The Chromium workflow covers Production Health, incident evidence, incident-to-regression review, representative trace transcript/timeline, datasets, release evidence, responsive health/auth states, sign-out/sign-in, deep-linked operational routes, command palette, and API-key modal focus behavior.

Three warnings in the Python suite originate from current dependency deprecations (`array` type code, Starlette TestClient/httpx transition, and AnyIO alias). No first-party warning remains after endpoint-test cleanup.

## Clean installation and migrations

- Two independent new Compose project/volume sets reached healthy on their first `docker compose up --build -d --wait` invocation.
- The ClickHouse health check authenticates as the configured application user and queries the configured database.
- The migration process retries authenticated ClickHouse readiness for a bounded period.
- API, receiver, and worker depend on successful one-shot migration completion.
- A second migration invocation reported `ControlSurface migrations are current` and exited 0.
- No traceback, panic, fatal, or unhandled error appeared in API, receiver, worker, web, or migration logs during the hero workflow.

## Recovery rehearsal

A seeded stack was backed up and restored to a new project and new volumes on isolated ports.

- PostgreSQL custom dump and ClickHouse native archive hashes matched the SHA-256 manifest.
- Restore rejected reuse by design and targeted a previously nonexistent Compose project.
- Source and restored PostgreSQL counts matched: 2 projects, 1 incident, 1 regression case, 4 release-evidence records.
- Source and restored ClickHouse counts matched: 270 spans, 45 trace summaries, 45 run graphs.
- Restored API and web readiness returned HTTP 200.
- Owner-password reset removed all 6 restored browser sessions; the previous password returned 401 and the replacement returned 200.

Outage probes on the restored synthetic stack:

- **Worker stopped:** one OTLP batch remained pending; restart drained the backlog.
- **ClickHouse stopped:** API readiness failed, ingest retained one pending batch, and restart restored API 200 and drained the backlog.
- **API stopped:** the separate receiver accepted telemetry; API restart returned 200.
- All 3 synthetic outage traces appeared in ClickHouse after recovery.

Backups are not encrypted by ControlSurface. The rehearsal used synthetic data in a private workbench; operators must provide encrypted durable storage and their own schedule.

## Performance evidence

The reproducible benchmark used Python 3.13.15, Linux 6.6.87.2 under WSL2, single-node Docker Compose, loopback, 10,000 throughput spans in 100-span batches at concurrency 4, plus dedicated 1K- and 10K-span traces.

| Measurement | p50 | p95 |
| --- | ---: | ---: |
| SDK manual span scope, no exporter | 0.029 ms | 0.093 ms |
| OTLP HTTP acknowledgement | 48.730 ms | 105.534 ms |
| Send to ClickHouse projection | 3,370.651 ms | 5,857.643 ms |
| Trace-list API, 50 rows | 25.173 ms | 32.520 ms |
| Trace detail, 1K spans / 1.12 MB | 145.438 ms | 156.202 ms |
| Trace detail, 10K spans / 11.21 MB | 1,122.591 ms | 1,257.100 ms |
| Browser render, 1K tree rows | 422.881 ms | 462.987 ms |
| Browser render, 10K source / bounded 2K tree rows | 1,555.740 ms | 1,877.091 ms |
| Clustering, 2K failed runs / 20 clusters | 5.646 ms | 5.769 ms |

- Measured throughput: **1,245.94 spans/second**.
- Dedicated projection: **779.735 ms** for 1K spans; **1,290.130 ms** for 10K spans.
- Measured storage delta: **714,056 bytes for 21,000 spans**; sample-normalized estimate **34,002,667 bytes per million spans**.

These measurements are not production sizing claims. They do not establish sustained load, HA behavior, WAN latency, or noisy-neighbor isolation.

## Dependency and artifact review

- `npm audit --omit=dev`: **0 known vulnerabilities**.
- Full npm high-severity audit: **0 known vulnerabilities**.
- `pip-audit` against the exact pinned runtime manifest with dependency resolution disabled: **no known vulnerabilities**.
- The Python manifest is fully version-pinned but not hash-pinned; pip-audit reports this supply-chain limitation.
- Backend and web runtime images use pinned base-image digests and non-root users.
- Backend runtime image: approximately 84.8 MB; `/app` contains installed packages and migrations, not source/build/wheel directories.
- Standalone web runtime image: approximately 76.3 MB; contains only standalone server/runtime dependencies and static output, not Playwright or the build toolchain.
- Docker Scout found **0 critical/high APK vulnerabilities** in both final runtime images and **0 critical/high npm vulnerabilities** in the standalone web image.
- Exact runtime inventories were reconciled against installed Python metadata, web `package.json` metadata, and Alpine package licenses. Copyleft/native components are identified in `THIRD_PARTY_NOTICES.md`.
- Runtime `pip`, `npm`, `npx`, Corepack, Yarn, and pnpm tooling is absent from the corresponding final images.
- **Do not publish binary/container artifacts until the distribution bundle includes the required base-image/native license texts and corresponding-source/relinking compliance materials.** This does not block the source repository release.

## Security posture

Verified controls include Argon2 password hashing, hashed project keys, project isolation, session-bound CSRF, process-local login throttling, strict input/body/decompression limits, common secret redaction, safe SQL binding, explicit CORS, security headers, loopback bindings, non-root containers, and fail-safe asynchronous instrumentation.

Known limits remain: trusted-host/single-owner model, best-effort free-text redaction, no evaluator sandbox, no distributed/proxy-aware limiter, no built-in TLS, no enterprise SSO/RBAC, and no defense from a privileged host/database operator. See `SECURITY.md`.

## Release decision

Ready for a **public source release candidate** after these final actions:

1. Stage the exact intended files and repeat staged Gitleaks plus naming scans.
2. Commit with Dev Chiniwala's configured identity and push.
3. Require the remote `quality` and `hero-e2e` jobs to pass on that exact commit.
4. Record a short real-product hero demo.
5. Tag `v0.1.0-rc.1` only after the remote pipeline is green.

Not approved by this audit: public Python package publication, public container publication, production HA claims, or hosted multi-tenant operation.
