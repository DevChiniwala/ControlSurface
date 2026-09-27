# Local operations and recovery

ControlSurface's Compose profile is a single-owner, loopback-only installation. It is not a managed HA deployment. Store `.env` and backups outside the repository, restrict file access, and rehearse restores on a disposable Compose project. Backups contain prompts, tool arguments, traces, dataset content, and owner password hashes. They are **not encrypted by ControlSurface**. Encrypt them in your backup system before off-host transfer.

## First boot and readiness

From the repository root, create `.env` from `.env.example` with independent random values, then run `docker compose up --build -d --wait`. The PostgreSQL probe checks the application database. The ClickHouse probe authenticates as the configured user and queries the configured database; `/ping` alone is insufficient during first boot. The migration process waits a bounded two minutes for authenticated ClickHouse readiness and exits nonzero if unavailable. API, ingest, and worker start only after migrations exit successfully. Verify `docker compose ps -a` shows `migrate` exited 0 and `curl http://localhost:8000/health/ready` returns 200. If it does not, inspect `docker compose logs migrate postgres clickhouse`; never mark a failed migration successful by editing `schema_migrations`.

## Owner-password reset

On the host running the private Compose installation:

```sh
docker compose exec -it api python -m controlsurface_server.operator reset-owner-password --email owner@example.com
```

The password is prompted twice without a command-line argument. It must be at least 12 characters. The supplied email must match the sole configured owner. Successful reset revokes every browser session; existing project API keys remain valid. If an API key may be compromised, revoke it separately after signing back in. This command assumes the operator already controls the host and database; it is intentionally not a public HTTP endpoint. Take a verified backup before planned recovery.

## Coordinated backup

Run from the repository root, choosing a **new** destination directory each time:

```sh
python scripts/recovery.py backup --directory ../controlsurface-backups/2026-09-21
```

The script stops web, API, ingest, and worker to quiesce writes. It creates a PostgreSQL custom-format dump and a ClickHouse native database archive, copies both to the destination, records SHA-256 checksums in `manifest.json`, removes its temporary ClickHouse archive, and restarts the application services. There is intentional ingestion/API downtime; senders must retry. A partial directory without a valid manifest is not a usable backup. Check free disk space before starting. Copy backups to durable encrypted storage under your own retention policy; the bundled script does not schedule backups or encrypt them.

The two stores are snapshotted while application writers are stopped, not through a distributed database transaction. Verify important backup sets by restoring them into a disposable project and checking project counts, traces, API readiness, and the expected UI workflow. `CS_BOOTSTRAP_TOKEN` and database passwords are **not** in the dump manifest; preserve `.env` separately in a secure secret store. The restored project should use the same database credentials configuration for its Compose services; secrets can be rotated later.

## Restore to a fresh project

Never restore over existing project volumes. To test without binding the normal host ports, provide an override file that resets every service's published `ports`, then use a new Compose project name:

```sh
python scripts/recovery.py restore --project controlsurface_rehearsal --override /path/to/no-ports.override.yaml --directory ../controlsurface-backups/2026-09-21
```

Without an override, `restore` targets the normal Compose ports and those must be free. The script verifies archive checksums, rejects any project that already has containers or volumes, starts empty databases, restores ClickHouse and PostgreSQL, then builds and starts the application. Verify `/health/ready`, project ownership, row counts, representative traces, and login before routing users or senders to it. Do not use a different release build/migration set without testing compatibility first. A failed restore may leave partial new volumes; investigate it and use another **new** project name for the next attempt. Do not run `docker compose down -v` against the original installation.

## Trace retention

Telemetry retention is opt-in. Set `CS_TRACE_RETENTION_DAYS=30` (allowed range 1–3650) in `.env`, then rerun `docker compose up --build -d --wait`. Migration configuration applies ClickHouse TTLs to `spans`, `trace_summaries`, and `agent_run_graphs` using their event times. ClickHouse removes expired rows asynchronously; this is not an exact-time deletion guarantee. Values set too low can erase historical trace evidence; back up first. PostgreSQL datasets, incidents, regressions, release evidence, users, and change events are not governed by this trace TTL. Completed inbox batches are pruned after one day and dead letters after seven days by the worker.

Removing `CS_TRACE_RETENTION_DAYS` later does **not** automatically remove an existing ClickHouse TTL. To disable retention, take a backup and explicitly run `ALTER TABLE ... REMOVE TTL` for each of the three tables, then verify `SHOW CREATE TABLE`. Do not assume a lost ClickHouse volume can be fully reconstructed from the inbox: processed inbox batches are deliberately short-lived. A verified ClickHouse backup is required for complete historical trace recovery.

## Outages and backlog

Use `docker compose ps -a`, `docker compose logs --tail=100 SERVICE`, and `docker compose exec -T api python -m controlsurface_server.operator inbox-status`. The inbox command reports queued/dead-letter batch counts and queued compressed bytes, not raw payloads.

| Failure | Expected behavior | Recovery |
| --- | --- | --- |
| Web or API unavailable | Web/login or operational queries fail; ingest has a separate process. | Check database readiness, then `docker compose up -d api web`; verify `/health/ready`. |
| Worker unavailable | Authenticated OTLP batches can continue into the bounded PostgreSQL inbox, until `CS_MAX_PENDING_BYTES` is reached. No new traces appear in ClickHouse. | Restart worker, monitor `inbox-status`, verify pending reaches zero and traces appear. |
| ClickHouse unavailable | API readiness fails; worker retries queued batches with backoff. Ingest can accept while inbox capacity remains. Batches reaching ten failed attempts become dead letters. | Restore ClickHouse service or backup, verify its authenticated health and schema; inspect dead-letter count, then explicitly requeue. |
| PostgreSQL unavailable | Authentication, ingestion durability, and metadata APIs fail. The SDK/exporters must retry or drop according to their own queue policies. | Restore PostgreSQL or its backup; verify migrations/readiness. There is no guarantee that sender-side unsent telemetry survives a long outage. |
| Migration fails | Dependent application services stay stopped. | Inspect migration/database logs and correct the underlying issue. Restore compatible backups if needed; do not edit migration history to force startup. |

After fixing the cause of dead letters, a host operator can run:

```sh
docker compose exec -T api python -m controlsurface_server.operator requeue-dead-letters --limit 1000 --confirm
```

Requeue is explicit because permanently bad payloads will fail again. A retried batch can produce duplicate physical ClickHouse versions; queries use replacing semantics for logical trace reads. Monitor both pending and dead counts after recovery. The inbox is bounded, not an unlimited disaster-recovery log.

## Migration rollback policy

PostgreSQL and ClickHouse migrations are ordered, forward-only, and recorded in PostgreSQL `schema_migrations`. There are no automatic down-migrations. Before a release changing schema, take and verify a coordinated backup and test the new release against a restored copy. Prefer additive/expand-contract changes. If a migration is faulty, stop writers and restore the **matching** PostgreSQL and ClickHouse backup into a fresh project running the previous compatible build; do not downgrade code against a partially upgraded live database. The operator must plan downtime and DNS/port cutover. No point-in-time recovery, cross-host replication, or automatic failover is included in the Compose profile.
