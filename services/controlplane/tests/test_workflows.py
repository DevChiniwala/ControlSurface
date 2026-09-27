"""Production-derived cases must remain inspectable and bounded."""

from datetime import UTC, datetime
from uuid import UUID

from controlsurface_server import workflows

PROJECT = UUID("d54fb3a5-9641-4f62-8c1e-50d3a654a63d")
SIGNATURE = "a" * 24


def test_cluster_deduplicates_representatives_by_input(monkeypatch):
    def rows(_settings, _project):
        return [
            {
                "trace_id": str(index).zfill(32).encode("ascii"),
                "run_id": f"run-{index}",
                "features_json": (
                    '{"failure_signature":"' + SIGNATURE + '",'
                    '"input_fingerprint":"' + fingerprint + '",'
                    '"failure_structure":{"failed_tool":"payments.refund"}}'
                ),
                "graph_json": "{}",
                "updated_at": datetime(2026, 1, index, tzinfo=UTC),
                "occurred_at": datetime(2026, 1, index, tzinfo=UTC),
            }
            for index, fingerprint in enumerate(("one", "one", "two"), start=1)
        ]

    monkeypatch.setattr(workflows, "_failure_rows", rows)
    cluster = workflows._clusters(None, str(PROJECT))[0]
    assert cluster["count"] == 3
    assert len(cluster["representatives"]) == 2
    assert cluster["representatives"][0]["run_id"] == "run-2"
    assert isinstance(cluster["representatives"][0]["trace_id"], str)


def test_regression_candidate_requires_review_and_preserves_source(monkeypatch):
    cluster = {
        "signature": SIGNATURE,
        "count": 428,
        "features": {"failed_tool": "payments.refund"},
        "representatives": [{"trace_id": "f" * 32, "run_id": "run-1"}],
    }
    monkeypatch.setattr(workflows, "_clusters", lambda *_: [cluster])
    monkeypatch.setattr(
        workflows,
        "_trace_detail",
        lambda *_: {
            "spans": [{"attributes": {"controlsurface.input": "I was charged twice"}}],
            "graph": {"outcome": "error"},
        },
    )
    candidates = workflows.regression_candidates(PROJECT, SIGNATURE, str(PROJECT), None)
    assert len(candidates) == 1
    assert candidates[0]["input"] == {"message": "I was charged twice"}
    assert candidates[0]["expect"] == {"completion": True}
    assert candidates[0]["review_required"] is True
    assert candidates[0]["evidence"]["affected_runs"] == 428


def test_incident_list_uses_stable_summary_shape(monkeypatch):
    class Result:
        def fetchall(self):
            return [
                {
                    "id": "incident-1",
                    "title": "Refund failures",
                    "agent_name": "refund-agent",
                    "affected_run_count": 42,
                    "severity": "high",
                    "status": "open",
                    "started_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "top_evidence_type": "tool_schema",
                    "top_evidence_subject": "payments.refund",
                    "top_evidence_score": 0.91,
                }
            ]

    class Connection:
        def execute(self, sql, _args):
            assert "affected_runs AS affected_run_count" in sql
            assert "top_evidence_score" in sql
            return Result()

    class Context:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(workflows, "postgres", lambda _settings: Context())
    rows = workflows.list_incidents(PROJECT, str(PROJECT), None)
    assert rows[0]["affected_run_count"] == 42
    assert rows[0]["top_evidence_subject"] == "payments.refund"


def test_release_list_returns_compact_decision_summaries(monkeypatch):
    class Result:
        def fetchall(self):
            return [
                {
                    "id": "release-1",
                    "decision": "blocked",
                    "candidate_version": "refund-agent@2",
                    "baseline_version": "refund-agent@1",
                    "quality_delta": 0.02,
                    "cost_delta": -1000.0,
                    "latency_delta": -20.0,
                    "tool_accuracy_delta": -0.03,
                    "failed_gate_count": 1,
                    "evidence_hash": "abc",
                    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
                }
            ]

    class Connection:
        def execute(self, sql, _args):
            assert "evidence_sha256 AS evidence_hash" in sql
            assert "failed_gate_count" in sql
            return Result()

    class Context:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(workflows, "postgres", lambda _settings: Context())
    rows = workflows.list_release_evidence(PROJECT, str(PROJECT), None)
    assert rows[0]["decision"] == "blocked"
    assert rows[0]["tool_accuracy_delta"] == -0.03
