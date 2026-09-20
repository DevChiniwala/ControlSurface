# Refund agent lifecycle demonstration

This example uses synthetic payment data and a deterministic decision-model test
double by default. It exercises the real ControlSurface SDK, OTLP receiver,
ClickHouse worker, change ledger, failure clustering, incident analysis and
production-derived regression API. It does not pretend that fixture model calls
are live paid inference or that their cost is a real provider bill.

From the repository root after `docker compose up --build` and UI setup:

1. Create a project API key in the UI.
2. `pip install -e sdk/python`
3. Set `CONTROLSURFACE_API_KEY` and `CONTROLSURFACE_PROJECT_ID` in your local shell.
4. `python examples/refund_agent/demo.py`
5. Open `http://localhost:3000` to inspect Health, failure clusters, the
   incident, the representative run and the regression case.

For the local release gate, run from `examples/refund_agent` so the candidate
module is importable:

```powershell
controlsurface eval run --suite suite.json --candidate agent:healthy_candidate --out baseline.json
controlsurface eval run --suite suite.json --candidate agent:broken_candidate --out candidate.json
python manifest.py --candidate broken --out manifest.json
controlsurface gate --baseline baseline.json --candidate candidate.json --manifest manifest.json --policy gate_policy.json --out blocked-evidence.json
controlsurface eval run --suite suite.json --candidate agent:fixed_candidate --out candidate.json
python manifest.py --candidate fixed --out manifest.json
controlsurface gate --baseline baseline.json --candidate candidate.json --manifest manifest.json --policy gate_policy.json --out evidence.json
```

The broken candidate and blocked gate intentionally exit `2`. The fixed
candidate and second gate should pass. `baseline.json`, `candidate.json`,
`manifest.json`, `blocked-evidence.json` and `evidence.json` are
generated local artifacts and must not be committed. The evidence bundle is also
stored immutably by the control plane.

To gate on the human-reviewed cases mined from production instead of the
checked-in teaching suite, export the project suite and pin that same revision
for every evaluation and manifest. Run these commands from this directory after
reviewing at least one case in the application:

```powershell
controlsurface regression export --out production-suite.json
controlsurface eval run --suite production-suite.json --candidate agent:healthy_candidate --out production-baseline.json
controlsurface eval run --suite production-suite.json --candidate agent:broken_candidate --out production-broken.json
python manifest.py --candidate broken --suite production-suite.json --out production-broken-manifest.json
controlsurface gate --baseline production-baseline.json --candidate production-broken.json --manifest production-broken-manifest.json --policy production_gate_policy.json --out production-blocked-evidence.json
controlsurface eval run --suite production-suite.json --candidate agent:fixed_candidate --out production-fixed.json
python manifest.py --candidate fixed --suite production-suite.json --out production-fixed-manifest.json
controlsurface gate --baseline production-baseline.json --candidate production-fixed.json --manifest production-fixed-manifest.json --policy production_gate_policy.json --out production-passed-evidence.json
```

The broken evaluation and blocked gate intentionally exit `2`; the fixed run
and gate exit `0`. The exported suite carries source trace IDs and a content
revision. Review case expectations before using the result as a release gate.
All generated JSON files above are local evidence artifacts and must not be
committed; keep sensitive cases outside the repository in real deployments.

Optional live LLM decision step: install `requirements-live.txt`, set
`OPENAI_API_KEY` and a model available to your account in `CONTROL_DEMO_MODEL`,
then run `python demo.py --live-model`. This sends each synthetic message and
policy text to the model provider and may incur cost. It is not used by CI or
the deterministic release gate. The [Responses API](https://developers.openai.com/api/docs/guides/text)
is used with `store=False`; token usage is recorded when returned. No provider
pricing is guessed.
