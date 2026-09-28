# Roadmap

ControlSurface is built around one closed loop:

```text
instrument → observe → measure → detect → incident → evidence
           → regression → candidate → reproducible release decision
```

## v0.1 release candidate

Implemented and locally verified:

- clean first boot with authenticated database readiness and migration ordering;
- Python SDK → OTLP → durable inbox → ClickHouse → API → web path;
- raw telemetry plus framework-independent AgentRunGraph;
- Production Health, SLO policy evaluation, failure clustering, incidents, and ranked Change Ledger evidence;
- representative production-derived regression review and revisioned suites;
- paired candidate evaluation and content-addressed release evidence;
- URL-addressable operational routes and authenticated Chromium workflow;
- owner recovery, coordinated PostgreSQL/ClickHouse backup and fresh-project restore, retention policy, and outage recovery;
- reproducible SDK, ingestion, query, large-trace rendering, clustering, and storage measurements;
- exact-manifest dependency, repository-history secret, naming-policy, and runtime-image reviews.

Remaining release work is intentionally narrow:

1. Run GitHub Actions on the exact candidate commit in the remote repository.
2. Review the final staged diff and repeat secret/naming scans after staging.
3. Complete artifact-specific license/SBOM review before publishing Python or container artifacts.
4. Tag `v0.1.0-rc.1` only after the exact remote candidate is green and the final launch review is approved.

## v0.2: always-on reliability automation

The next major product investment is not another dashboard. It is the continuous reliability loop:

```text
production traffic
  → persistent SLO windows and error budgets
  → degradation population
  → bounded failure clustering
  → automatically proposed incident
  → evidence-ranked change candidates
  → engineer review
  → deduplicated regression candidates
```

Planned work:

- durable SLO windows, error-budget accounting, and burn-rate evaluation;
- scheduled bounded clustering over new failed-run populations;
- incident proposal policy, deduplication, acknowledgement, resolution, and durable timeline;
- affected/unaffected cohort comparison for stronger evidence rankings;
- bounded behavioral signals with explicit cost and sampling controls;
- notification adapters after the incident state machine is reliable.

## Subsequent priorities

1. **Tool/MCP contract intelligence** — deeper semantic compatibility, blast radius, affected agents, first failure, and release-gate policy.
2. **GitHub pull-request reporting** — publish sanitized gate results and evidence links with a deterministic exit status.
3. **TypeScript SDK and selected integrations** — only after contract fixtures and ingestion behavior are stable.
4. **Evaluation runtime** — asynchronous jobs, reproducible environments, stronger isolation, and practical judge adapters.
5. **Operational scale** — sustained-load validation, distributed rate limiting, production deployment profile, and larger tenancy model.

## Explicitly deferred

Enterprise SSO/RBAC, billing, a Kubernetes operator, automatic rollback, traffic routing, a marketplace, dozens of SDKs, and a broad marketing site are not near-term priorities. They should not dilute the telemetry-to-release loop.
