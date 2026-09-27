"""First-boot migration readiness contracts."""

from types import SimpleNamespace

import pytest
from clickhouse_connect.driver.exceptions import OperationalError

from controlsurface_server import migrate


class FakeClient:
    def __init__(self, *, ready: bool) -> None:
        self.ready = ready
        self.closed = False

    def command(self, query: str) -> int:
        assert query == "SELECT 1"
        if not self.ready:
            raise OperationalError("database is initializing")
        return 1

    def close(self) -> None:
        self.closed = True


def test_wait_for_clickhouse_retries_until_database_is_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients = [FakeClient(ready=False), FakeClient(ready=False), FakeClient(ready=True)]
    delays: list[float] = []
    monkeypatch.setattr(migrate, "clickhouse", lambda _settings: clients.pop(0))

    migrate.wait_for_clickhouse(
        SimpleNamespace(), attempts=3, interval_seconds=0.5, sleep=delays.append
    )

    assert delays == [0.5, 0.5]
    assert clients == []


def test_wait_for_clickhouse_fails_after_bounded_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    clients = [FakeClient(ready=False) for _ in range(3)]
    issued: list[FakeClient] = []

    def connect(_settings: object) -> FakeClient:
        client = clients.pop(0)
        issued.append(client)
        return client

    monkeypatch.setattr(migrate, "clickhouse", connect)

    with pytest.raises(RuntimeError, match="migration deadline"):
        migrate.wait_for_clickhouse(
            SimpleNamespace(), attempts=3, interval_seconds=0, sleep=lambda _: None
        )

    assert len(issued) == 3
    assert all(client.closed for client in issued)


def test_wait_for_clickhouse_validates_retry_policy() -> None:
    with pytest.raises(ValueError, match="retry policy"):
        migrate.wait_for_clickhouse(SimpleNamespace(), attempts=0)
