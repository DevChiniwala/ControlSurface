"""SLO and production-health contract tests."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from controlsurface_server import api
from controlsurface_server.domain.slo import (
    Health,
    SloMetrics,
    SloPolicy,
    evaluate_slo_metrics,
)


def test_control_plane_rejects_oversized_request_before_routing() -> None:
    response = TestClient(api.app).post(
        "/api/not-a-route",
        content=b"x" * (2 * 1024 * 1024 + 1),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


def test_slo_aggregate_tool_and_cost_breaches() -> None:
    policy = SloPolicy(minimum_samples=2, average_cost_nano_usd_max=10)
    metrics = SloMetrics(2, 2, 4, 3, 100, 22, 4)
    result = evaluate_slo_metrics(metrics, policy)
    assert result.health is Health.DEGRADED
    assert result.completion_rate == 1
    assert result.tool_success_rate == 0.75
    assert result.average_cost_nano_usd == 11
    assert result.breaches == ("tool_success_rate", "average_cost_nano_usd")


def test_slo_no_data_and_incident_override() -> None:
    policy = SloPolicy(minimum_samples=20)
    metrics = SloMetrics(1, 1, 0, 0, 100, 0, 1)
    assert evaluate_slo_metrics(metrics, policy).health is Health.NO_DATA
    assert evaluate_slo_metrics(metrics, policy, incident_open=True).health is Health.INCIDENT


@pytest.mark.parametrize(
    "field,value",
    [
        ("minimum_samples", 0),
        ("completion_rate_min", 1.1),
        ("tool_success_rate_min", -0.1),
        ("p95_latency_ms_max", -1),
    ],
)
def test_invalid_slo_policy(field: str, value: int | float) -> None:
    with pytest.raises(ValueError):
        SloPolicy(**{field: value})


def test_health_route_uses_real_tool_spans_and_open_incidents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_query(_settings: object, sql: str, _parameters: dict[str, object]) -> list[dict]:
        seen.append(sql)
        if "FROM spans FINAL" in sql:
            return [{"agent_name": "refund", "tool_calls": 10, "successful_tool_calls": 8}]
        return [
            {
                "agent_name": "refund",
                "runs": 20,
                "completed_runs": 20,
                "failed_runs": 0,
                "p95_latency_ms": 100,
                "cost_nano_usd": 200,
                "maximum_steps": 4,
                "last_seen": datetime.now(UTC),
            }
        ]

    class FakeConnection:
        def execute(self, sql: str, _args: tuple) -> FakeConnection:
            if "slo_policies" in sql:
                self.rows = [{"agent_name": "refund", "policy_json": asdict(SloPolicy())}]
            else:
                self.rows = [{"agent_name": "refund", "count": 1}]
            return self

        def fetchall(self) -> list[dict]:
            return self.rows

    @contextmanager
    def fake_postgres(_settings: object):
        yield FakeConnection()

    monkeypatch.setattr(api, "_query", fake_query)
    monkeypatch.setattr(api, "postgres", fake_postgres)
    result = api.production_health(uuid4(), "owner", object())
    agent = result["agents"][0]
    assert agent["health"] == "incident"
    assert agent["tool_success_rate"] == 0.8
    assert agent["failed_tool_calls"] == 2
    assert agent["breaches"] == ["tool_success_rate"]
    assert result["open_incidents"] == 1
    assert len(seen) == 2
    assert "trace_summaries FINAL" in seen[1]
