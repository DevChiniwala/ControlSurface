"""Local evaluation runner and API-backed release gate CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import jsonschema

# Candidate isolation uses this interpreter with a fixed module argv and JSON stdin.


def _json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: str, value: Any) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _api_base() -> str:
    value = os.getenv("CONTROLSURFACE_API_URL", "http://localhost:8000").rstrip("/")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("CONTROLSURFACE_API_URL must be an HTTP(S) URL without credentials")
    return value


def _request(path: str, method: str = "GET", body: Any = None, auth: bool = True) -> Any:
    base = _api_base()
    headers: dict[str, str] = {}
    if auth:
        token = os.getenv("CONTROLSURFACE_API_KEY")
        if not token:
            raise ValueError("CONTROLSURFACE_API_KEY is required")
        headers["Authorization"] = f"Bearer {token}"
    encoded = json.dumps(body).encode() if body is not None else None
    if encoded is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, encoded, headers, method=method)
    try:
        # The base is parsed and restricted to HTTP(S) above.
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(2048).decode("utf-8", "replace")
        raise ValueError(f"API rejected request ({error.code}): {detail}") from error


def _project() -> str:
    value = os.getenv("CONTROLSURFACE_PROJECT_ID")
    if not value:
        raise ValueError("CONTROLSURFACE_PROJECT_ID is required")
    return value


def _evaluate_case(
    item: dict[str, Any], actual: dict[str, Any], custom: Any, latency: int
) -> dict[str, Any]:
    expected = item.get("expected", {})
    checks: list[bool] = []
    if "exact_output" in expected:
        checks.append(actual.get("output") == expected["exact_output"])
    if "schema" in expected:
        try:
            jsonschema.validate(actual.get("output"), expected["schema"])
            checks.append(True)
        except (jsonschema.ValidationError, jsonschema.SchemaError):
            checks.append(False)
    if "completion" in expected:
        checks.append(actual.get("complete") is expected["completion"])
    if "maximum_steps" in expected:
        checks.append(int(actual.get("steps", 0)) <= int(expected["maximum_steps"]))
    tools = actual.get("tools", [])
    if not isinstance(tools, list):
        raise ValueError("Candidate tools must be a list")
    required = set(expected.get("required_tools", []))
    forbidden = set(expected.get("forbidden_tools", []))
    tool_correct = required.issubset(set(tools)) and not forbidden.intersection(tools)
    checks.append(tool_correct)
    if custom is not None:
        checks.append(bool(custom))
    passed = all(checks)
    quality = float(actual.get("quality_score", 1.0 if passed else 0.0))
    if not 0 <= quality <= 1:
        raise ValueError("quality_score must be in [0, 1]")
    return {
        "case_id": item["id"],
        "passed": passed,
        "quality_score": quality,
        "tool_correct": tool_correct,
        "latency_ms": latency,
        "cost_nano_usd": max(0, int(actual.get("cost_nano_usd", 0))),
    }


def eval_run(args: argparse.Namespace) -> int:
    suite = _json(args.suite)
    if not isinstance(suite, dict):
        raise ValueError("Suite must be a JSON object")
    items = suite.get("cases")
    if not isinstance(items, list) or not items:
        raise ValueError("Suite must contain a nonempty cases array")
    if len(items) > 5000:
        raise ValueError("Suite may contain at most 5000 cases")
    if not 1 <= args.timeout <= 3600:
        raise ValueError("Evaluation timeout must be between 1 and 3600 seconds")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Suite case {index} must be an object")
        case_id = item.get("id")
        if not isinstance(case_id, str) or not case_id.strip() or len(case_id) > 200:
            raise ValueError(f"Suite case {index} requires a nonempty ID up to 200 characters")
        if not isinstance(item.get("input"), dict):
            raise ValueError(f"Suite case {case_id} input must be an object")
        if not isinstance(item.get("expected", {}), dict):
            raise ValueError(f"Suite case {case_id} expected value must be an object")
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Suite case IDs must be unique")
    results = []
    for item in items:
        start = time.perf_counter_ns()
        try:
            process = subprocess.run(  # nosec B603
                [sys.executable, "-m", "controlsurface.case_worker"],
                input=json.dumps(
                    {
                        "candidate": args.candidate,
                        "evaluator": args.evaluator,
                        "input": item["input"],
                        "expected": item.get("expected", {}),
                    }
                ),
                text=True,
                capture_output=True,
                timeout=args.timeout,
                check=False,
            )
            if process.returncode:
                raise ValueError(process.stderr[-1000:] or "Candidate process failed")
            output = json.loads(process.stdout)
            latency = round((time.perf_counter_ns() - start) / 1_000_000)
            results.append(_evaluate_case(item, output["actual"], output["custom"], latency))
        except (
            subprocess.TimeoutExpired,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            latency = round((time.perf_counter_ns() - start) / 1_000_000)
            results.append(
                {
                    "case_id": item["id"],
                    "passed": False,
                    "quality_score": 0,
                    "tool_correct": False,
                    "latency_ms": latency,
                    "cost_nano_usd": 0,
                    "error": str(error)[-1000:],
                }
            )
    payload = {
        "format_version": 1,
        "suite_revision": suite.get("revision"),
        "candidate": args.candidate,
        "results": results,
    }
    _write(args.out, payload)
    passed = sum(item["passed"] for item in results)
    print(
        f"Evaluated {len(results)} cases: {passed} passed, "
        f"{len(results) - passed} failed. {args.out}"
    )
    return 0 if passed == len(results) else 2


def gate(args: argparse.Namespace) -> int:
    baseline = _json(args.baseline)
    candidate = _json(args.candidate)
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise ValueError("Baseline and candidate result files must be JSON objects")
    if not isinstance(baseline.get("results"), list) or not isinstance(
        candidate.get("results"), list
    ):
        raise ValueError("Baseline and candidate files must contain results arrays")
    submission = {
        "baseline": baseline["results"],
        "candidate": candidate["results"],
        "manifest": _json(args.manifest),
        "policy": _json(args.policy),
    }
    result = _request(f"/api/projects/{_project()}/release-evidence", "POST", submission)
    if args.out:
        bundle = _request(f"/api/projects/{_project()}/release-evidence/{result['id']}")
        _write(args.out, bundle)
    decision = result["decision"]
    print(f"Release gate: {'PASS' if decision['passed'] else 'BLOCK'}")
    print(f"Evidence SHA-256: {result['sha256']}")
    for reason in decision["reasons"]:
        print(f"  - {reason}")
    return 0 if decision["passed"] else 2


def doctor(args: argparse.Namespace) -> int:
    checks = [
        ("API and databases", lambda: _request("/health/ready", auth=False)),
        ("Project API key", lambda: _request("/api/projects")),
    ]
    failures = 0
    for name, check in checks:
        try:
            check()
            print(f"PASS {name}")
        except Exception as error:
            failures += 1
            print(f"FAIL {name}: {error}")
    return 0 if not failures else 1


def incidents_list(args: argparse.Namespace) -> int:
    for incident in _request(f"/api/projects/{_project()}/incidents"):
        print(
            f"{incident['id']}  {incident['severity']}  {incident['status']}  {incident['title']}"
        )
    return 0


def regression_create(args: argparse.Namespace) -> int:
    item = _json(args.case)
    result = _request(f"/api/projects/{_project()}/regressions", "POST", item)
    print(f"Created regression {result['id']} revision {result['revision']}")
    return 0


def regression_export(args: argparse.Namespace) -> int:
    suite = _request(f"/api/projects/{_project()}/regressions/suite")
    _write(args.out, suite)
    print(f"Exported {len(suite['cases'])} cases at {suite['revision']} to {args.out}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="controlsurface")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor_parser = commands.add_parser("doctor", help="Check local API and project access")
    doctor_parser.set_defaults(func=doctor)
    eval_parser = commands.add_parser("eval", help="Run local evaluation cases")
    eval_commands = eval_parser.add_subparsers(dest="eval_command", required=True)
    run_parser = eval_commands.add_parser("run")
    run_parser.add_argument("--suite", required=True)
    run_parser.add_argument("--candidate", required=True, help="module:function")
    run_parser.add_argument("--evaluator", help="Optional module:function")
    run_parser.add_argument("--timeout", type=int, default=30)
    run_parser.add_argument("--out", required=True)
    run_parser.set_defaults(func=eval_run)
    gate_parser = commands.add_parser("gate", help="Create immutable API-backed release evidence")
    gate_parser.add_argument("--baseline", required=True)
    gate_parser.add_argument("--candidate", required=True)
    gate_parser.add_argument("--manifest", required=True)
    gate_parser.add_argument("--policy", required=True)
    gate_parser.add_argument("--out")
    gate_parser.set_defaults(func=gate)
    incidents_parser = commands.add_parser("incidents")
    incidents_commands = incidents_parser.add_subparsers(dest="incidents_command", required=True)
    list_parser = incidents_commands.add_parser("list")
    list_parser.set_defaults(func=incidents_list)
    regression_parser = commands.add_parser("regression")
    regression_commands = regression_parser.add_subparsers(dest="regression_command", required=True)
    create_parser = regression_commands.add_parser("create")
    create_parser.add_argument("--case", required=True)
    create_parser.set_defaults(func=regression_create)
    export_parser = regression_commands.add_parser("export")
    export_parser.add_argument("--out", required=True)
    export_parser.set_defaults(func=regression_export)
    args = parser.parse_args()
    try:
        raise SystemExit(args.func(args))
    except (
        KeyError,
        OSError,
        TypeError,
        ValueError,
        urllib.error.URLError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
