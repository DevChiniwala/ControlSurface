import argparse
import json
from pathlib import Path

from controlsurface.cli import _evaluate_case, eval_run


def test_deterministic_assertions():
    case = {
        "id": "refund",
        "expected": {
            "exact_output": {"refunded": True},
            "required_tools": ["lookup_transactions"],
            "forbidden_tools": ["create_payment"],
            "maximum_steps": 4,
            "schema": {"type": "object", "required": ["refunded"]},
        },
    }
    actual = {"output": {"refunded": True}, "tools": ["lookup_transactions"], "steps": 3}
    result = _evaluate_case(case, actual, True, 12)
    assert result["passed"]
    assert result["tool_correct"]
    actual["tools"].append("create_payment")
    assert not _evaluate_case(case, actual, True, 12)["passed"]


def test_local_runner_isolates_failing_case(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).parent)
    suite = tmp_path / "suite.json"
    output = tmp_path / "results.json"
    suite.write_text(
        json.dumps(
            {
                "revision": "r1",
                "cases": [
                    {
                        "id": "healthy",
                        "input": {"message": "duplicate charge"},
                        "expected": {"completion": True, "required_tools": ["verify_duplicate"]},
                    },
                    {
                        "id": "broken",
                        "input": {"message": "other"},
                        "expected": {"completion": True},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        suite=str(suite),
        candidate="fixture_candidate:refund_candidate",
        evaluator="fixture_candidate:custom_evaluator",
        timeout=5,
        out=str(output),
    )
    assert eval_run(args) == 2
    results = json.loads(output.read_text(encoding="utf-8"))["results"]
    assert results[0]["passed"]
    assert not results[1]["passed"]
    assert "Unknown scenario" in results[1]["error"]
