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


def load_settings() -> Settings:
    required = ("CS_DATABASE_URL", "CS_CH_PASSWORD", "CS_BOOTSTRAP_TOKEN")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing required environment settings: {', '.join(missing)}")
    return Settings(
        database_url=os.environ["CS_DATABASE_URL"],
        clickhouse_host=os.getenv("CS_CH_HOST", "clickhouse"),
        clickhouse_port=int(os.getenv("CS_CH_PORT", "8123")),
        clickhouse_user=os.getenv("CS_CH_USER", "controlsurface"),
        clickhouse_password=os.environ["CS_CH_PASSWORD"],
        clickhouse_database=os.getenv("CS_CH_DATABASE", "controlsurface"),
        bootstrap_token=os.environ["CS_BOOTSTRAP_TOKEN"],
        cookie_secure=os.getenv("CS_COOKIE_SECURE", "false").lower() == "true",
        max_request_bytes=int(os.getenv("CS_MAX_REQUEST_BYTES", str(8 * 1024 * 1024))),
        max_uncompressed_bytes=int(os.getenv("CS_MAX_UNCOMPRESSED_BYTES", str(16 * 1024 * 1024))),
        max_pending_bytes=int(os.getenv("CS_MAX_PENDING_BYTES", str(512 * 1024 * 1024))),
    )
