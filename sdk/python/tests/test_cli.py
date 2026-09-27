import argparse
import json
from pathlib import Path

import pytest

from controlsurface.cli import _api_base, _evaluate_case, eval_run


@pytest.mark.parametrize(
    "value",
    [
        "file:///tmp/controlsurface",
        "http://",
        "http://user:password@localhost:8000",
        "http://localhost:8000?token=secret",
        "http://localhost:invalid",
    ],
)
def test_api_base_rejects_non_http_or_secret_bearing_urls(monkeypatch, value):
    monkeypatch.setenv("CONTROLSURFACE_API_URL", value)
    with pytest.raises(ValueError, match=r"HTTP\(S\) URL"):
        _api_base()


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


@pytest.mark.parametrize(
    "case",
    [
        {},
        {"id": "", "input": {}, "expected": {}},
        {"id": "case", "input": "not-an-object", "expected": {}},
        {"id": "case", "input": {}, "expected": []},
    ],
)
def test_local_runner_rejects_malformed_suite_cases(tmp_path, case):
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"cases": [case]}), encoding="utf-8")
    args = argparse.Namespace(
        suite=str(suite),
        candidate="fixture_candidate:refund_candidate",
        evaluator=None,
        timeout=5,
        out=str(tmp_path / "results.json"),
    )
    with pytest.raises(ValueError, match="Suite case"):
        eval_run(args)
