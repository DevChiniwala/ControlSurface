# Security

ControlSurface telemetry can contain prompts, user data, tool arguments, credentials, retrieved documents, and proprietary context. Treat the host, databases, backups, exported suites, and release evidence as sensitive.

## V1 trust model

The included Compose profile is a **single trusted owner on a trusted host**, bound to loopback. The owner and host/database administrators are inside the trust boundary. Instrumented applications trust the configured receiver endpoint; the receiver trusts a valid project key only for that key's project.

This profile is not a hardened multi-user or hostile-code service. It does not protect data from a privileged host/database operator, provide enterprise SSO/RBAC, terminate public TLS, isolate mutually hostile tenants, or safely execute untrusted evaluator/candidate code. Put a reviewed TLS reverse proxy, firewall, host hardening, encrypted storage, and independent backups around any remote deployment.

## Implemented controls

- Owner passwords use Argon2. Verification uses a dummy hash for unknown accounts, supports safe rehash, and never stores plaintext passwords.
- Project API keys are high-entropy, shown once, stored as SHA-256 digests, revocable, and resolved to a server-side project scope. A client cannot select another project through telemetry fields.
- Browser sessions are stored as token digests, `HttpOnly`, and `SameSite=Lax`. Owner-session mutations require a token bound to that session through `X-CSRF-Token`. Logout and offline password reset revoke sessions.
- Login admission is limited to 20 attempts per client address in a rolling five-minute window and returns `429` plus `Retry-After`. The table is bounded to prevent attacker-controlled memory growth.
- CORS is an explicit allow-list. The web application sets CSP, frame denial, content-type protection, a strict referrer policy, and a restrictive permissions policy. Framework identification headers are disabled.
- Compose publishes PostgreSQL, ClickHouse, API, web, and OTLP ports only on `127.0.0.1`. Runtime containers use non-root users. Release-candidate base images use pinned digests.
- API queries use bound SQL parameters. Concurrency-sensitive creation paths use PostgreSQL advisory locks. Request models constrain identifier/text lengths and numeric ranges.
- Control-plane JSON bodies are limited to 2 MiB. OTLP receivers bound compressed and expanded size, nesting depth, ID lengths, span count, and total pending-inbox bytes. Malformed gzip and trailing data are rejected.
- The SDK and receiver redact sensitive attribute keys, bearer-looking values, and common secret query parameters. The SDK does not automatically capture prompt/tool input or output.
- PostgreSQL acknowledges compressed telemetry batches durably before the asynchronous worker projects to ClickHouse. Failed projection retries are bounded; repeatedly failing batches become visible dead letters.
- Optional trace retention applies bounded ClickHouse TTLs. Completed and dead-letter inbox records also have bounded retention.
- Release evidence is content-addressed, validated, and append-only through the API. It records versions/hashes/configuration/results needed to reproduce a gate decision.

## Known limitations

- Redaction is best-effort. It cannot reliably discover secrets embedded in prose, unknown key names, encoded blobs, document contents, or every URL form. Prevent sensitive capture at the source and validate your own attribute policy.
- `run(input=...)` and explicit attributes may contain personal or secret data. No field-level encryption or customer-managed encryption key system is included.
- The login limiter is process-local, resets on restart, and is neither distributed nor trusted-proxy aware. A remote deployment needs rate limiting and client-IP policy at the edge.
- Local CLI candidate programs and optional Python evaluators execute as trusted subprocesses with the invoking user's authority. They are not a sandbox. Do not run code from untrusted datasets or contributors.
- HTTPS, certificate rotation, network policy, database encryption at rest, malware scanning, SIEM export, SSO, RBAC, audit-log immutability, and automatic secret rotation are operator responsibilities or deferred work.
- A privileged database or host operator can rewrite source telemetry and release evidence. The content hash detects accidental/inconsistent bundles, not a malicious privileged administrator. External signing/witnessing is not implemented.
- Root-cause evidence scores express observed association, not proof or probability of causation.
- SDK queues can lose telemetry on abrupt process exit or a sustained endpoint outage. Instrumentation must never become a dependency for application correctness.

## Deployment requirements

1. Generate independent random values for `CS_DB_PASSWORD`, `CS_CH_PASSWORD`, and `CS_BOOTSTRAP_TOKEN`; keep `.env` outside source control and restrict its filesystem permissions.
2. Keep the provided loopback bindings unless a reviewed proxy/network layer is in place. Set `CS_COOKIE_SECURE=true` behind HTTPS and configure exact `CS_CORS_ORIGINS` and `CS_PUBLIC_API_URL` values.
3. Configure `CS_TRACE_RETENTION_DAYS` according to data policy. Remember that disabling an existing ClickHouse TTL requires an explicit table change.
4. Store backups in encrypted, access-controlled storage and rehearse restore into a fresh project. Backup archives contain telemetry and owner password hashes; ControlSurface does not encrypt them.
5. Review evaluator and candidate commands before execution. Run them in your own restricted build environment when inputs are not fully trusted.
6. Run dependency, secret, and license scans against the exact commit and artifacts you plan to publish. Do not reuse the release-audit results as a permanent guarantee.

Operational procedures, outage behavior, recovery, and migration policy are documented in [docs/OPERATIONS.md](docs/OPERATIONS.md). The current exact scan/test record is in [docs/RELEASE_AUDIT.md](docs/RELEASE_AUDIT.md).

## Reporting a vulnerability

Use a private GitHub security advisory for the repository. Include affected versions, reproduction steps, impact, and a minimal sanitized example. Do not put credentials, customer telemetry, private prompts, or exploit details in a public issue.
