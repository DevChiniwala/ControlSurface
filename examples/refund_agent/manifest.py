"""Create content-pinned evidence input from the checked-in demo artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

from agent import SCHEMA_V1, SCHEMA_V2


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def schema_fingerprint(schema: dict) -> str:
    canonical = json.dumps(
        schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


root = Path(__file__).resolve().parent
suite = (root / "suite.json").read_bytes()
agent = (root / "agent.py").read_bytes()
payload = {
    "baseline_version": "refund-agent@v1-tool-v1:" + digest(agent),
    "candidate_version": "refund-agent@v2-tool-v2:" + digest(agent),
    "dataset_revision": digest(suite),
    "suite_revision": digest(suite),
    "evaluator_versions": {"deterministic": "1"},
    "prompt_hashes": {},
    "tool_schema_hashes": {
        "baseline": schema_fingerprint(SCHEMA_V1),
        "candidate": schema_fingerprint(SCHEMA_V2),
    },
    "model_configuration": {"provider": "fixture", "model": "fixture-decision-model"},
    "pricing_version": "not-applicable-fixture",
    "execution_environment": {
        "python": platform.python_version(),
        "platform": platform.platform(),
    },
    "sampling_parameters": {"temperature": None, "seed": None},
}
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", choices=("broken", "fixed"), required=True)
    parser.add_argument("--suite", type=Path, default=root / "suite.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    suite_revision = digest(args.suite.read_bytes())
    payload["dataset_revision"] = suite_revision
    payload["suite_revision"] = suite_revision
    candidate_agent_version = "v1" if args.candidate == "broken" else "v2"
    payload["candidate_version"] = (
        f"refund-agent@{candidate_agent_version}-tool-v2:" + digest(agent)
    )
    Path(args.out).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote content-pinned manifest to {args.out}")
