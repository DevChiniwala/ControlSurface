"""Run idempotent metadata and telemetry migrations after storage is ready."""

from __future__ import annotations

import time
from collections.abc import Callable

from clickhouse_connect.driver.exceptions import ClickHouseError

from .settings import Settings, load_settings
from .storage import apply_migrations, clickhouse


def wait_for_clickhouse(
    settings: Settings,
    *,
    attempts: int = 60,
    interval_seconds: float = 2,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait for the configured user and database, not only the HTTP listener."""
    if attempts < 1 or interval_seconds < 0:
        raise ValueError("Invalid ClickHouse readiness retry policy")
    for attempt in range(attempts):
        client = None
        try:
            client = clickhouse(settings)
            client.command("SELECT 1")
            return
        except (ClickHouseError, OSError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise RuntimeError(
                    "ClickHouse database was not ready before the migration deadline"
                ) from exc
            sleep(interval_seconds)
        finally:
            if client is not None:
                client.close()


def main() -> None:
    settings = load_settings()
    wait_for_clickhouse(settings)
    apply_migrations(settings)
    print("ControlSurface migrations are current")


if __name__ == "__main__":
    main()
