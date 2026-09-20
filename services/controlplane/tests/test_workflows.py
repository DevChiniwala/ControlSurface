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
        "trace_detail",
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
