# Full-stack hero test

`test_hero_workflow.py` exercises a disposable ControlSurface installation:
owner setup, project-scoped API keys, dataset creation, SDK telemetry through
OTLP and the worker into ClickHouse, health degradation, change-ledger evidence,
failure clustering, incident analysis, production-derived regression, local
evaluation, an immutable blocked release decision for the broken candidate,
and an immutable passing decision for the fixed candidate. It uses the synthetic
refund example and never calls a paid model API.

The test is opt-in because it creates the first owner account and must not run
against an existing installation. CI builds a fresh Compose stack and runs it.
To run it manually, provide a **fresh disposable stack**, install both Python
packages with their `dev` extras, and set `CONTROLSURFACE_E2E=1` and
`CS_BOOTSTRAP_TOKEN` to the token used by that stack. Then run:

```text
python -m pytest -q tests/e2e -s
```

`CONTROLSURFACE_API_URL`, `CONTROLSURFACE_OTLP_URL`, and
`CONTROLSURFACE_WEB_URL` may override the default localhost endpoints. Do not
point this test at a shared or production installation.
