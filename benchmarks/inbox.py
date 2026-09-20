"""Compare durable compressed-batch acknowledgement for SQLite WAL and PostgreSQL.

Run inside the backend container with CS_DATABASE_URL set. This benchmark creates a
uniquely named PostgreSQL schema and drops only that schema when finished.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
import uuid
import zlib
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg_pool import ConnectionPool


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[
        min(len(ordered) - 1, max(0, int(len(ordered) * fraction + 0.999) - 1))
    ]


def batches(count: int) -> list[bytes]:
    return [
        zlib.compress(uuid.uuid4().bytes + os.urandom(2048), level=3)
        for _ in range(count)
    ]


def sqlite_case(payloads: list[bytes], path: Path) -> dict[str, float]:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        "CREATE TABLE inbox(id TEXT PRIMARY KEY, project_id TEXT, payload BLOB)"
    )
    latencies = []
    start = time.perf_counter()
    for payload in payloads:
        mark = time.perf_counter()
        with connection:
            connection.execute(
                "INSERT INTO inbox(id, project_id, payload) VALUES (?, ?, ?)",
                (str(uuid.uuid4()), "project-one", payload),
            )
        latencies.append((time.perf_counter() - mark) * 1000)
    elapsed = time.perf_counter() - start
    replay = connection.execute(
        "SELECT payload FROM inbox WHERE project_id = ?", ("project-one",)
    )
    received = [row[0] for row in replay]
    connection.close()
    assert [hashlib.sha256(item).digest() for item in received] == [
        hashlib.sha256(item).digest() for item in payloads
    ]
    return {
        "throughput_batches_per_s": round(len(payloads) / elapsed, 1),
        "p50_ack_ms": round(percentile(latencies, 0.5), 3),
        "p95_ack_ms": round(percentile(latencies, 0.95), 3),
        "replayed": len(received),
    }


def postgres_case(
    payloads: list[bytes], database_url: str, pooled: bool = False
) -> dict[str, float]:
    schema = "bench_" + uuid.uuid4().hex[:12]
    with psycopg.connect(database_url) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(
            sql.SQL(
                "CREATE TABLE {}.inbox "
                "(id UUID PRIMARY KEY, project_id TEXT, payload BYTEA, processed_at TIMESTAMPTZ)"
            ).format(sql.Identifier(schema))
        )
    latencies = []
    pool: ConnectionPool | None = None
    try:
        pool = (
            ConnectionPool(database_url, min_size=1, max_size=4, open=True)
            if pooled
            else None
        )
        if pool:
            pool.wait()
        start = time.perf_counter()
        for payload in payloads:
            mark = time.perf_counter()
            source = pool.connection() if pool else psycopg.connect(database_url)
            with source as connection, connection.transaction():
                connection.execute("SELECT pg_advisory_xact_lock(4178165)")
                connection.execute(
                    sql.SQL(
                        "SELECT sum(octet_length(payload)) FROM {}.inbox "
                        "WHERE processed_at IS NULL"
                    ).format(sql.Identifier(schema))
                ).fetchone()
                connection.execute(
                    sql.SQL(
                        "INSERT INTO {}.inbox "
                        "(id, project_id, payload) VALUES (%s, %s, %s)"
                    ).format(sql.Identifier(schema)),
                    (uuid.uuid4(), "project-one", payload),
                )
            latencies.append((time.perf_counter() - mark) * 1000)
        elapsed = time.perf_counter() - start
        with psycopg.connect(database_url) as connection:
            received = [
                row[0]
                for row in connection.execute(
                    sql.SQL(
                        "SELECT payload FROM {}.inbox WHERE project_id = %s ORDER BY id"
                    ).format(sql.Identifier(schema)),
                    ("project-one",),
                )
            ]
        assert len(received) == len(payloads)
        assert {hashlib.sha256(item).digest() for item in received} == {
            hashlib.sha256(item).digest() for item in payloads
        }
        return {
            "throughput_batches_per_s": round(len(payloads) / elapsed, 1),
            "p50_ack_ms": round(percentile(latencies, 0.5), 3),
            "p95_ack_ms": round(percentile(latencies, 0.95), 3),
            "replayed": len(received),
        }
    finally:
        if pool:
            pool.close()
        with psycopg.connect(database_url) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


def main() -> None:
    count = int(os.getenv("CS_BENCH_BATCHES", "200"))
    if count < 1 or count > 10_000:
        raise ValueError("CS_BENCH_BATCHES must be between 1 and 10000")
    payloads = batches(count)
    with tempfile.TemporaryDirectory(prefix="cs_inbox_bench_") as folder:
        sqlite_result = sqlite_case(payloads, Path(folder) / "spool.db")
    postgres_result = postgres_case(payloads, os.environ["CS_DATABASE_URL"])
    postgres_pooled = postgres_case(
        payloads, os.environ["CS_DATABASE_URL"], pooled=True
    )
    print(
        json.dumps(
            {
                "batch_count": count,
                "compressed_bytes_per_batch": len(payloads[0]),
                "sqlite_wal": sqlite_result,
                "postgres_inbox": postgres_result,
                "postgres_pooled": postgres_pooled,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
