# Security

ControlSurface telemetry can contain prompts, user data, tool arguments, credentials, and proprietary context. Treat the local deployment, volumes, and backups as sensitive. Do not send real customer traffic to this pre-release build without your own security review.

## Current controls

- Project bearer keys are high-entropy, shown once, and stored as hashes. Ingestion and API queries derive project scope from a verified key or owner session.
- The initial owner password is Argon2-hashed. Browser sessions are HttpOnly and SameSite=Lax. Mutating owner-session API requests require a session-bound `X-CSRF-Token`, obtained from the authenticated, non-cacheable `GET /api/session/csrf` endpoint. Project bearer keys authenticate independently and do not require CSRF tokens. Local Compose sets `CS_COOKIE_SECURE=false` only because it serves plain HTTP on loopback; use secure cookies behind HTTPS off-host.
- Owner login permits at most 20 requests per client address in a rolling five-minute window and returns HTTP 429 with `Retry-After` when full. The limiter is bounded and process-local; it is not a distributed or proxy-aware abuse-control system.
- The receiver bounds request size, expanded payload size, spans per batch, and pending inbox bytes. It redacts attributes with sensitive key names and bearer-looking text before durable storage. The SDK also masks sensitive attribute keys and does not capture input/output content automatically.
- API queries use bound parameters. Local Compose ports bind to `127.0.0.1`. Browser CORS defaults to `http://localhost:3000` and can be configured with `CS_CORS_ORIGINS`.
- Candidate code and optional custom Python evaluators run as local CLI subprocesses, not uploaded server code. This is not a sandbox for hostile evaluators.

## Operator responsibilities and limitations

Use independent random values for `CS_DB_PASSWORD`, `CS_CH_PASSWORD`, and `CS_BOOTSTRAP_TOKEN` in `.env`; never commit that file, keys, or generated evidence containing sensitive cases. Protect database volumes/backups and put TLS and network controls in front of any remotely reachable service.

Redaction cannot reliably find secrets embedded in prose, encoded content, unfamiliar key names, URLs, or files. Explicit `run(input=...)` capture can contain sensitive information. Restrict capture at the source and test redaction on your own attributes. Trace/evaluation retention is not yet generally operator-configurable; do not assume all stored telemetry is automatically deleted.

The deployment has no enterprise SSO, fine-grained RBAC, hardened remote profile, distributed rate limiting, or external security audit. Session-bound CSRF tokens protect owner-session mutations, but do not prevent XSS and are not a substitute for a full remote-deployment review. The local login limiter resets on process restart and may treat clients behind a shared proxy as one address. Release evidence is hashed and API-level append-only, but a privileged database operator can rewrite it. Root-cause scores express association, not causal certainty. Optional live model calls in the synthetic example send its prompt and policy text to the configured provider and may incur charges.

Report vulnerabilities through a private GitHub security advisory for the repository. Do not put sensitive traces or exploit details in public issues.
