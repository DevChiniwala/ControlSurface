"""Validated process configuration; secrets are never logged."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    clickhouse_host: str
    clickhouse_port: int
    clickhouse_user: str
    clickhouse_password: str
    clickhouse_database: str
    bootstrap_token: str
    cookie_secure: bool
    max_request_bytes: int
    max_uncompressed_bytes: int
    max_pending_bytes: int
    trace_retention_days: int | None


def _bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    if raw.lower() not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw.lower() == "true"


def load_settings() -> Settings:
    required = ("CS_DATABASE_URL", "CS_CH_PASSWORD", "CS_BOOTSTRAP_TOKEN")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing required environment settings: {', '.join(missing)}")
    retention_value = os.getenv("CS_TRACE_RETENTION_DAYS")
    retention_days = (
        _bounded_int("CS_TRACE_RETENTION_DAYS", 30, minimum=1, maximum=3650)
        if retention_value
        else None
    )
    return Settings(
        database_url=os.environ["CS_DATABASE_URL"],
        clickhouse_host=os.getenv("CS_CH_HOST", "clickhouse"),
        clickhouse_port=_bounded_int("CS_CH_PORT", 8123, minimum=1, maximum=65535),
        clickhouse_user=os.getenv("CS_CH_USER", "controlsurface"),
        clickhouse_password=os.environ["CS_CH_PASSWORD"],
        clickhouse_database=os.getenv("CS_CH_DATABASE", "controlsurface"),
        bootstrap_token=os.environ["CS_BOOTSTRAP_TOKEN"],
        cookie_secure=_boolean("CS_COOKIE_SECURE", False),
        max_request_bytes=_bounded_int(
            "CS_MAX_REQUEST_BYTES", 8 * 1024 * 1024, minimum=1024, maximum=64 * 1024 * 1024
        ),
        max_uncompressed_bytes=_bounded_int(
            "CS_MAX_UNCOMPRESSED_BYTES",
            16 * 1024 * 1024,
            minimum=1024,
            maximum=128 * 1024 * 1024,
        ),
        max_pending_bytes=_bounded_int(
            "CS_MAX_PENDING_BYTES",
            512 * 1024 * 1024,
            minimum=1024 * 1024,
            maximum=1024 * 1024 * 1024 * 1024,
        ),
        trace_retention_days=retention_days,
    )
