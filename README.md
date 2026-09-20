# ControlSurface

The production engineering platform for AI agents.

Observe · Evaluate · Monitor · Diagnose · Ship

ControlSurface connects production telemetry to agent run graphs, reliability monitoring, incidents, production-derived regression tests, and reproducible release decisions.

> Pre-release V1: this is a local self-hosted development build. The deterministic refund-agent lifecycle and one authenticated Chromium workflow passed on a fresh disposable stack on 2026-09-20. Broader security, accessibility, performance, and binary-license reviews remain before public release. Do not use it as the sole release control for production.

## Run locally

Requirements: Docker Desktop with Compose, Python 3.11+, and available ports 3000, 8000, 4317, 4318, 55432, and 58123.

1. Copy `.env.example` to `.env`, replacing all three placeholder values with independent random secrets.
2. Run `docker compose up --build`. The migration service must complete. Open `http://localhost:3000`.
3. On first launch, create the owner and project using the `CS_BOOTSTRAP_TOKEN` in your private `.env`. In Settings → API keys, create a project key and copy it immediately.
4. Install the local SDK/CLI: `python -m pip install -e sdk/python`. Set `CONTROLSURFACE_API_KEY` to your key. Get the project ID from `GET http://localhost:8000/api/projects` with `Authorization: Bearer <key>`, set `CONTROLSURFACE_PROJECT_ID`, and run `controlsurface doctor`.

OTLP/HTTP is at `http://localhost:4318/v1/traces`; OTLP/gRPC is at `localhost:4317`. The API is at `http://localhost:8000`.

If you change the browser-facing API origin, set `CS_PUBLIC_API_URL` and the matching `CS_CORS_ORIGINS` in `.env`, then rebuild the web image. `NEXT_PUBLIC_CONTROL_API` is embedded in the browser bundle at build time; changing only a container runtime variable will not retarget an existing image.

```python
from controlsurface import ControlSurface

cs = ControlSurface.init(endpoint="http://localhost:4318", agent_name="support-agent")
with cs.session():
    with cs.run("support-request"):
        with cs.span("lookup-customer", kind="tool"):
            pass  # Call the application tool here.
cs.shutdown()
```

The SDK exports asynchronously through a bounded queue. An unavailable endpoint should not fail application work, but unexported spans may be lost. Content is not captured automatically; explicit `input` or attributes are sent to your deployment.

See [the synthetic refund-agent demo](examples/refund_agent/README.md), [architecture](ARCHITECTURE.md), [security limitations](SECURITY.md), [dependency notices](THIRD_PARTY_NOTICES.md), [roadmap](ROADMAP.md), and [contributing checks](CONTRIBUTING.md). Deterministic demo/evaluation mode requires no paid model API.

Created and maintained by Dev Chiniwala. Licensed under Apache License 2.0. No public package or repository release has been made from this local build.
