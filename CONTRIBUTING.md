# Contributing

ControlSurface is a new, independently implemented project. Keep changes scoped, add tests for domain or protocol behavior, and update documentation when an interface changes. Open an issue describing the engineering problem before a large feature. Do not paste third-party application code, assets, tests, or documentation into first-party files.

From the repository root, run applicable checks before proposing a change:

```powershell
python -m pip install -e 'services/controlplane[dev]' -e 'sdk/python[dev]'
python -m pytest services/controlplane/tests sdk/python/tests
python -m ruff check services/controlplane sdk/python examples/refund_agent tests
python -m ruff format --check services/controlplane sdk/python examples/refund_agent tests
python -m mypy services/controlplane/src sdk/python/src --ignore-missing-imports
cd apps/web
npm ci
npm run format:check
npm run typecheck
npm run build
```

For storage, protocol, or UI changes, also run `docker compose up --build` and the relevant local integration or refund-agent workflow. CI runs the Python hero test, then the Chromium browser test, then the login-limit test against one fresh disposable Compose stack. Do not enable the opt-in `CONTROLSURFACE_E2E` or `CONTROLSURFACE_BROWSER_E2E` tests against an existing installation: they create an owner, write synthetic telemetry, add a dataset item, and intentionally exhaust login attempts. Add migrations for persistent schema changes and test from a clean database. Never commit `.env`, API keys, customer telemetry, generated local evidence files, or benchmark claims without reproducible measurement context. Use conventional commit messages and your own Git identity. Do not add AI co-author trailers.
