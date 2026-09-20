"""Exercise the production-failure-to-release loop against a fresh Compose stack.

Run only with CONTROLSURFACE_E2E=1. The test creates an owner and projects, so it
must target a disposable stack, never an existing installation.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from controlsurface_server.domain.release import verify_evidence

pytestmark = pytest.mark.skipif(
    os.getenv("CONTROLSURFACE_E2E") != "1",
    reason="Set CONTROLSURFACE_E2E=1 for the disposable full-stack test",
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "refund_agent"


def _request(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    opener: Any = None,
) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    response_context = (
        opener.open(request, timeout=20)
        if opener is not None
        else urllib.request.urlopen(request, timeout=20)
    )
    with response_context as response:
        content = response.read()
    return json.loads(content) if content else None


def _wait_ready(url: str, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if _request(url)["status"] == "ok":
                return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(2)
    pytest.fail(f"Service did not become ready: {url}")


def _command(arguments: list[str], *, env: dict[str, str], expected: int = 0) -> str:
    process = subprocess.run(
        [sys.executable, *arguments],
        cwd=EXAMPLE,
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert process.returncode == expected, (
        f"Command exited {process.returncode}, expected {expected}: {arguments}\n"
        f"stdout: {process.stdout[-3000:]}\nstderr: {process.stderr[-3000:]}"
    )
    return process.stdout


def test_failure_to_reproducible_release_decision(tmp_path: Path) -> None:
    base = os.getenv("CONTROLSURFACE_API_URL", "http://localhost:8000").rstrip("/")
    web = os.getenv("CONTROLSURFACE_WEB_URL", "http://localhost:3000").rstrip("/")
    bootstrap = os.environ["CS_BOOTSTRAP_TOKEN"]
    _wait_ready(f"{base}/health/ready")
    assert not _request(f"{base}/api/setup/status")["configured"], (
        "The hero test requires a fresh, disposable stack with no owner account"
    )

    cookies = http.cookiejar.CookieJar()
    owner = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    created = _request(
        f"{base}/api/setup",
        method="POST",
        body={
            "email": "ci-owner@example.invalid",
            "password": "disposable-ci-password-only",
            "project_name": "Refund reliability",
        },
        headers={"X-Bootstrap-Token": bootstrap},
        opener=owner,
    )
    project_id = created["project_id"]
    project_url = f"{base}/api/projects/{project_id}"
    key = _request(
        f"{project_url}/keys",
        method="POST",
        body={"label": "hero test"},
        opener=owner,
    )["key"]
    auth = {"Authorization": f"Bearer {key}"}

    # Project-bound API keys must not read a different project's data.
    other = _request(
        f"{base}/api/projects",
        method="POST",
        body={"name": "Isolated", "slug": "isolated-ci"},
        opener=owner,
    )["id"]
    other_key = _request(
        f"{base}/api/projects/{other}/keys",
        method="POST",
        body={"label": "other project"},
        opener=owner,
    )["key"]
    with pytest.raises(urllib.error.HTTPError) as rejected:
        _request(
            f"{project_url}/traces",
            headers={"Authorization": f"Bearer {other_key}"},
        )
    assert rejected.value.code == 404

    suite = json.loads((EXAMPLE / "suite.json").read_text(encoding="utf-8"))
    dataset_id = _request(
        f"{project_url}/datasets",
        method="POST",
        body={"name": "Refund scenarios"},
        headers=auth,
    )["id"]
    for case in suite["cases"]:
        _request(
            f"{project_url}/datasets/{dataset_id}/items",
            method="POST",
            body={"input": case["input"], "expected": case["expected"]},
            headers=auth,
        )
    assert len(
        _request(f"{project_url}/datasets/{dataset_id}/items", headers=auth)
    ) == len(suite["cases"])

    env = dict(
        os.environ,
        CONTROLSURFACE_API_URL=base,
        CONTROLSURFACE_OTLP_URL=os.getenv(
            "CONTROLSURFACE_OTLP_URL", "http://localhost:4318"
        ),
        CONTROLSURFACE_API_KEY=key,
        CONTROLSURFACE_PROJECT_ID=project_id,
    )
    demo_output = _command([str(EXAMPLE / "demo.py"), "--runs", "20"], env=env)
    assert "Failure cluster" in demo_output
    assert "Incident" in demo_output

    health = _request(f"{project_url}/health", headers=auth)
    refund_health = next(
        item for item in health["agents"] if item["agent_name"] == "refund-agent"
    )
    assert refund_health["runs"] >= 40
    assert refund_health["failed_runs"] >= 20
    assert refund_health["health"] in {"degraded", "incident"}

    changes = _request(f"{project_url}/changes", headers=auth)
    assert any(
        item["change_type"] == "tool_schema"
        and item["subject_name"] == "payments.refund"
        for item in changes
    )
    clusters = _request(f"{project_url}/clusters", headers=auth)
    cluster = next(
        item
        for item in clusters
        if item["features"].get("failed_tool") == "payments.refund"
    )
    assert cluster["count"] >= 3
    assert len(cluster["representatives"]) <= 3
    representative_id = cluster["representatives"][0]["trace_id"]
    detail = _request(f"{project_url}/traces/{representative_id}", headers=auth)
    assert detail["graph"]["outcome"] == "error"
    operations = {node["operation"] for node in detail["graph"]["nodes"]}
    assert {"agent", "model", "retrieval", "tool"}.issubset(operations)
    assert any(span["status"] == "error" for span in detail["spans"])
    assert any(
        span["operation"] == "model" and "controlsurface.output" in span["attributes"]
        for span in detail["spans"]
    )
    assert any(
        span["name"] == "payments.refund"
        and "controlsurface.tool.arguments" in span["attributes"]
        for span in detail["spans"]
    )

    incidents = _request(f"{project_url}/incidents", headers=auth)
    incident = next(
        item for item in incidents if item["cluster_signature"] == cluster["signature"]
    )
    evidence = _request(f"{project_url}/incidents/{incident['id']}", headers=auth)[
        "evidence_json"
    ]
    if isinstance(evidence, str):
        evidence = json.loads(evidence)
    candidates = evidence["root_cause_candidates"]
    assert candidates
    assert candidates[0]["subject"] == "payments.refund"
    assert candidates[0]["failed_tool_matches"] is True
    assert "not causal proof" in candidates[0]["explanation"]

    regressions = _request(f"{project_url}/regressions", headers=auth)
    assert any(
        item["source_trace_id"] == representative_id
        and item["cluster_signature"] == cluster["signature"]
        for item in regressions
    )

    baseline = tmp_path / "healthy-baseline.json"
    broken = tmp_path / "broken-candidate.json"
    candidate = tmp_path / "fixed-candidate.json"
    manifest = tmp_path / "manifest.json"
    blocked_manifest = tmp_path / "blocked-manifest.json"
    blocked_evidence_path = tmp_path / "blocked-evidence.json"
    evidence_path = tmp_path / "release-evidence.json"
    _command(
        [
            "-m",
            "controlsurface.cli",
            "eval",
            "run",
            "--suite",
            "suite.json",
            "--candidate",
            "agent:healthy_candidate",
            "--out",
            str(baseline),
        ],
        env=env,
    )
    _command(
        [
            "-m",
            "controlsurface.cli",
            "eval",
            "run",
            "--suite",
            "suite.json",
            "--candidate",
            "agent:broken_candidate",
            "--out",
            str(broken),
        ],
        env=env,
        expected=2,
    )
    _command(
        [
            "-m",
            "controlsurface.cli",
            "eval",
            "run",
            "--suite",
            "suite.json",
            "--candidate",
            "agent:fixed_candidate",
            "--out",
            str(candidate),
        ],
        env=env,
    )
    _command(
        ["manifest.py", "--candidate", "broken", "--out", str(blocked_manifest)],
        env=env,
    )
    _command(["manifest.py", "--candidate", "fixed", "--out", str(manifest)], env=env)
    recorded_schema_hashes = {
        item["after_hash"]
        for item in changes
        if item["change_type"] == "tool_schema"
        and item["subject_name"] == "payments.refund"
    }
    hashes = json.loads(manifest.read_text(encoding="utf-8"))["tool_schema_hashes"]
    assert {hashes["baseline"], hashes["candidate"]} <= recorded_schema_hashes
    blocked_output = _command(
        [
            "-m",
            "controlsurface.cli",
            "gate",
            "--baseline",
            str(baseline),
            "--candidate",
            str(broken),
            "--manifest",
            str(blocked_manifest),
            "--policy",
            "gate_policy.json",
            "--out",
            str(blocked_evidence_path),
        ],
        env=env,
        expected=2,
    )
    assert "Release gate: BLOCK" in blocked_output
    blocked_bundle = json.loads(blocked_evidence_path.read_text(encoding="utf-8"))
    assert verify_evidence(blocked_bundle)
    assert not blocked_bundle["decision"]["passed"]
    assert "critical_regression" in blocked_bundle["decision"]["reasons"]
    assert "duplicate-charge" in blocked_bundle["decision"]["regressions"]

    gate_output = _command(
        [
            "-m",
            "controlsurface.cli",
            "gate",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--manifest",
            str(manifest),
            "--policy",
            "gate_policy.json",
            "--out",
            str(evidence_path),
        ],
        env=env,
    )
    assert "Release gate: PASS" in gate_output
    bundle = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert verify_evidence(bundle)
    assert bundle["decision"]["passed"]
    assert (
        bundle["manifest"]["tool_schema_hashes"]["baseline"]
        != bundle["manifest"]["tool_schema_hashes"]["candidate"]
    )

    repeated = _request(
        f"{project_url}/release-evidence",
        method="POST",
        headers=auth,
        body={
            "baseline": json.loads(baseline.read_text(encoding="utf-8"))["results"],
            "candidate": json.loads(candidate.read_text(encoding="utf-8"))["results"],
            "manifest": json.loads(manifest.read_text(encoding="utf-8")),
            "policy": json.loads(
                (EXAMPLE / "gate_policy.json").read_text(encoding="utf-8")
            ),
        },
    )
    assert repeated["sha256"] == bundle["sha256"]
    assert len(_request(f"{project_url}/release-evidence", headers=auth)) == 2

    production_suite = tmp_path / "production-suite.json"
    _command(
        [
            "-m",
            "controlsurface.cli",
            "regression",
            "export",
            "--out",
            str(production_suite),
        ],
        env=env,
    )
    mined = json.loads(production_suite.read_text(encoding="utf-8"))
    assert len(mined["cases"]) == 1
    assert mined["cases"][0]["source_trace_id"] == representative_id
    production_results = {}
    for label, target, expected in (
        ("baseline", "healthy_candidate", 0),
        ("broken", "broken_candidate", 2),
        ("fixed", "fixed_candidate", 0),
    ):
        result_path = tmp_path / f"production-{label}.json"
        _command(
            [
                "-m",
                "controlsurface.cli",
                "eval",
                "run",
                "--suite",
                str(production_suite),
                "--candidate",
                f"agent:{target}",
                "--out",
                str(result_path),
            ],
            env=env,
            expected=expected,
        )
        production_results[label] = result_path

    for label, expected in (("broken", 2), ("fixed", 0)):
        manifest_path = tmp_path / f"production-{label}-manifest.json"
        evidence_path = tmp_path / f"production-{label}-evidence.json"
        _command(
            [
                "manifest.py",
                "--candidate",
                label,
                "--suite",
                str(production_suite),
                "--out",
                str(manifest_path),
            ],
            env=env,
        )
        _command(
            [
                "-m",
                "controlsurface.cli",
                "gate",
                "--baseline",
                str(production_results["baseline"]),
                "--candidate",
                str(production_results[label]),
                "--manifest",
                str(manifest_path),
                "--policy",
                "production_gate_policy.json",
                "--out",
                str(evidence_path),
            ],
            env=env,
            expected=expected,
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert verify_evidence(evidence)
        assert evidence["decision"]["passed"] is (label == "fixed")
        assert evidence["manifest"]["suite_revision"].startswith("sha256:")
    assert len(_request(f"{project_url}/release-evidence", headers=auth)) == 4

    with urllib.request.urlopen(web, timeout=30) as response:
        assert response.status == 200
