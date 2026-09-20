"""Generate a real telemetry/change/incident/regression lifecycle with synthetic data."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agent import (
    SCHEMA_V1,
    SCHEMA_V2,
    FixtureModel,
    OpenAIModel,
    PaymentTool,
    RefundAgent,
)
from controlsurface import ControlSurface


def api(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    project = os.environ["CONTROLSURFACE_PROJECT_ID"]
    url = os.getenv("CONTROLSURFACE_API_URL", "http://localhost:8000").rstrip("/")
    request = urllib.request.Request(
        f"{url}/api/projects/{project}/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['CONTROLSURFACE_API_KEY']}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def wait_for_failure_cluster(timeout_seconds: int = 45) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        clusters = api("clusters")
        match = next(
            (
                item
                for item in clusters
                if item["features"].get("failed_tool") == "payments.refund"
            ),
            None,
        )
        if match and match["count"] >= 3:
            return match
        time.sleep(1)
    raise RuntimeError("Failure cluster did not appear before timeout")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-model", action="store_true", help="Opt in to a paid API call per run"
    )
    parser.add_argument("--runs", type=int, default=25)
    args = parser.parse_args()
    if args.runs < 3 or args.runs > 200:
        raise ValueError("--runs must be between 3 and 200")
    if args.live_model and not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required for --live-model")
    model = OpenAIModel() if args.live_model else FixtureModel()
    client = ControlSurface.init(
        endpoint=os.getenv("CONTROLSURFACE_OTLP_URL", "http://localhost:4318"),
        agent_name="refund-agent",
        agent_version="v1",
        service_name="refund-demo",
    )
    scenarios = json.loads(
        (Path(__file__).parent / "suite.json").read_text(encoding="utf-8")
    )
    messages = [item["input"]["message"] for item in scenarios["cases"][:2]]
    api(
        "slos",
        "POST",
        {
            "agent_name": "refund-agent",
            "policy": {
                "minimum_samples": 20,
                "completion_rate_min": 0.98,
                "tool_success_rate_min": 0.99,
                "p95_latency_ms_max": 8000,
                "average_cost_nano_usd_max": 80000000,
                "maximum_steps_max": 12,
            },
        },
    )
    api(
        "tool-schemas",
        "POST",
        {"tool_name": "payments.refund", "version": "1.8.4", "schema_json": SCHEMA_V1},
    )
    healthy = RefundAgent(model, PaymentTool(1), client, agent_version=1)
    for index in range(args.runs):
        with client.session(f"healthy-{index}"):
            healthy.run(messages[index % len(messages)])
    client.provider.force_flush()
    print(f"Emitted {args.runs} healthy runs")

    change = api(
        "tool-schemas",
        "POST",
        {"tool_name": "payments.refund", "version": "1.9.0", "schema_json": SCHEMA_V2},
    )
    print(f"Registered tool schema change: {change['change']['compatibility']}")
    broken = RefundAgent(model, PaymentTool(2), client, agent_version=1)
    for index in range(args.runs):
        with client.session(f"broken-{index}"):
            broken.run(messages[index % len(messages)])
    client.provider.force_flush()
    print(f"Emitted {args.runs} schema-incompatible runs")

    cluster = wait_for_failure_cluster()
    print(f"Failure cluster {cluster['signature']}: {cluster['count']} runs")
    incident = api(
        "incidents/analyze",
        "POST",
        {
            "cluster_signature": cluster["signature"],
            "severity": "high",
        },
    )
    print(f"Incident {incident['id']} records inspectable change candidates")
    representative = cluster["representatives"][0]["trace_id"]
    try:
        regression = api(
            "regressions",
            "POST",
            {
                "name": "refund-tool-schema-production-failure",
                "source_trace_id": representative,
                "cluster_signature": cluster["signature"],
                "input": {"message": messages[0]},
                "expect": {
                    "completion": True,
                    "required_tools": [
                        "lookup_transactions",
                        "verify_duplicate",
                        "payments.refund",
                    ],
                    "forbidden_tools": ["create_payment"],
                    "maximum_steps": 6,
                },
            },
        )
        print(f"Synthetic demo regression case {regression['id']} created")
    except urllib.error.HTTPError as error:
        if error.code != 409:
            raise
        print("Regression already exists for representative trace")
    fixed = RefundAgent(model, PaymentTool(2), client, agent_version=2)
    for index in range(5):
        with client.session(f"candidate-{index}"):
            fixed.run(messages[index % len(messages)])
    client.shutdown()
    print("Emitted fixed candidate runs. Run the local eval and release gate next.")


if __name__ == "__main__":
    main()
