"""Operator-configured trace retention remains explicit and bounded."""

from types import SimpleNamespace

import pytest

from controlsurface_server.settings import load_settings
from controlsurface_server.storage import configure_trace_retention


def test_retention_is_opt_in_and_range_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CS_DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("CS_CH_PASSWORD", "not-a-real-secret")
    monkeypatch.setenv("CS_BOOTSTRAP_TOKEN", "not-a-real-token")
    monkeypatch.delenv("CS_TRACE_RETENTION_DAYS", raising=False)
    assert load_settings().trace_retention_days is None
    monkeypatch.setenv("CS_TRACE_RETENTION_DAYS", "30")
    assert load_settings().trace_retention_days == 30
    monkeypatch.setenv("CS_TRACE_RETENTION_DAYS", "0")
    with pytest.raises(ValueError, match="between 1 and 3650"):
        load_settings()


def test_retention_updates_all_three_telemetry_tables() -> None:
    commands: list[str] = []
    client = SimpleNamespace(command=commands.append)
    configure_trace_retention(client, 30)  # type: ignore[arg-type]
    assert commands == [
        "ALTER TABLE spans MODIFY TTL start_time + INTERVAL 30 DAY DELETE",
        "ALTER TABLE trace_summaries MODIFY TTL start_time + INTERVAL 30 DAY DELETE",
        "ALTER TABLE agent_run_graphs MODIFY TTL occurred_at + INTERVAL 30 DAY DELETE",
    ]
    with pytest.raises(ValueError, match="between 1 and 3650"):
        configure_trace_retention(client, 0)  # type: ignore[arg-type]
