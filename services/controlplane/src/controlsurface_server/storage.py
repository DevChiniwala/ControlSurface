"""Database connections and migrations with explicit ownership."""

from __future__ import annotations

import atexit
import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

import clickhouse_connect
import psycopg
from clickhouse_connect.driver.client import Client
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .settings import Settings

DbConnection = psycopg.Connection[dict[str, Any]]


@contextmanager
def postgres(settings: Settings) -> Iterator[DbConnection]:
    with _pool(settings.database_url).connection() as connection:
        yield connection


@lru_cache(maxsize=2)
def _pool(database_url: str) -> ConnectionPool[DbConnection]:
    pool = ConnectionPool[DbConnection](
        conninfo=database_url,
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=8,
        timeout=5,
        open=True,
    )
    atexit.register(pool.close)
    return pool


def clickhouse(settings: Settings) -> Client:
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )


def apply_migrations(settings: Settings) -> None:
    root = (
        Path(os.environ["CS_MIGRATIONS_DIR"])
        if os.getenv("CS_MIGRATIONS_DIR")
        else Path(__file__).resolve().parents[2] / "migrations"
    )
    if not (root / "postgres").is_dir() or not (root / "clickhouse").is_dir():
        raise RuntimeError(f"Migration directories unavailable: {root}")
    with postgres(settings) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        for path in sorted((root / "postgres").glob("*.sql")):
            version = f"pg:{path.stem}"
            if connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s", (version,)
            ).fetchone():
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))
        connection.commit()

    client = clickhouse(settings)
    try:
        for path in sorted((root / "clickhouse").glob("*.sql")):
            version = f"ch:{path.stem}"
            with postgres(settings) as connection:
                if connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s", (version,)
                ).fetchone():
                    continue
                client.command(path.read_text(encoding="utf-8"))
                connection.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))
                connection.commit()
    finally:
        client.close()
