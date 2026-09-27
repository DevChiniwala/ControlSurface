"""Reproducible, disposable-stack SDK/OTLP/query/clustering benchmark.

Run via the Compose benchmark profile, never against a production project.
This creates synthetic trace data and prints measured JSON; it makes no capacity claims.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from controlsurface import ControlSurface
from controlsurface_server import workflows
from controlsurface_server.auth import create_api_key, create_owner
from controlsurface_server.settings import load_settings
from controlsurface_server.storage import clickhouse, postgres
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.trace import TracerProvider


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[max(0, min(len(values) - 1, int(len(values) * fraction) - 1))]


def distribution(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(percentile(values, 0.5), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
    }


def sdk_overhead(iterations: int) -> dict[str, Any]:
    provider = TracerProvider()
    sdk = ControlSurface(provider, provider.get_tracer("benchmark"), "offline")
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        with sdk.span("benchmark-span", "tool", {"benchmark": True}):
            pass
        samples.append((time.perf_counter_ns() - started) / 1e6)
    provider.shutdown()
    return {
        "iterations": iterations,
        **distribution(samples),
        "scope": "in-process, no exporter",
    }


def project_key() -> tuple[str, str, str]:
    settings = load_settings()
    with postgres(settings) as connection:
        owners = connection.execute("SELECT id FROM users LIMIT 2").fetchall()
        if not owners:
            owner_password = os.getenv(
                "CS_BENCH_OWNER_PASSWORD"
            ) or secrets.token_urlsafe(24)
            _, project_id = create_owner(
                connection,
                "benchmark@example.invalid",
                owner_password,
                "Benchmark",
            )
        else:
            projects = connection.execute(
                "SELECT id, name FROM projects LIMIT 2"
            ).fetchall()
            if (
                len(owners) != 1
                or len(projects) != 1
                or projects[0]["name"] != "Benchmark"
            ):
                raise RuntimeError(
                    "Benchmark refuses to run against a non-disposable project"
                )
            project_id = str(projects[0]["id"])
        key_id, key = create_api_key(connection, project_id, "temporary benchmark key")
    return project_id, key_id, key


def request(url: str, key: str, data: bytes | None = None) -> bytes:
    headers = {"Authorization": f"Bearer {key}"}
    if data is not None:
        headers["Content-Type"] = "application/x-protobuf"
    query = urllib.request.Request(url, data=data, headers=headers)
    # Benchmark endpoints are parsed and restricted to HTTP(S) before sampling.
    with urllib.request.urlopen(query, timeout=30) as response:  # nosec B310
        return response.read()


def validated_endpoint(name: str, value: str) -> str:
    value = value.rstrip("/")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be an HTTP(S) URL without credentials")
    return value


def batch(
    agent: str,
    size: int,
    *,
    failed: bool,
    trace_id: str | None = None,
    span_offset: int = 0,
) -> tuple[str, bytes]:
    trace = trace_id or uuid.uuid4().hex
    message = ExportTraceServiceRequest()
    resource = message.resource_spans.add()
    attribute = resource.resource.attributes.add()
    attribute.key = "controlsurface.agent.name"
    attribute.value.string_value = agent
    scope = resource.scope_spans.add()
    now = time.time_ns()
    for index in range(size):
        absolute_index = span_offset + index
        span = scope.spans.add()
        span.trace_id = bytes.fromhex(trace)
        span.span_id = (absolute_index + 1).to_bytes(8, "big")
        span.name = "benchmark-agent" if absolute_index == 0 else "benchmark-tool"
        if absolute_index:
            span.parent_span_id = (1).to_bytes(8, "big")
        span.start_time_unix_nano = now + absolute_index * 1000
        span.end_time_unix_nano = span.start_time_unix_nano + 1000000
        kind = span.attributes.add()
        kind.key = "controlsurface.kind"
        kind.value.string_value = "agent" if absolute_index == 0 else "tool"
        if failed and index == size - 1:
            span.status.code = 2
    return trace, message.SerializeToString()


def storage_bytes(client: Any) -> int:
    return int(
        client.query(
            "SELECT coalesce(sum(bytes_on_disk), 0) FROM system.parts WHERE active = 1 "
            "AND database = 'controlsurface' AND table IN "
            "('spans', 'trace_summaries', 'agent_run_graphs')"
        ).result_rows[0][0]
    )


def cluster_compute(rows: int) -> dict[str, Any]:
    now = datetime.now(UTC)
    fake = [
        {
            "trace_id": f"{index:032x}",
            "run_id": str(index),
            "features_json": json.dumps(
                {
                    "failure_signature": f"signature-{index % 20}",
                    "failure_structure": {"tool": "benchmark-tool"},
                    "input_fingerprint": str(index % 100),
                }
            ),
            "graph_json": "{}",
            "updated_at": now,
            "occurred_at": now,
        }
        for index in range(rows)
    ]
    original = workflows._failure_rows
    workflows._failure_rows = lambda _settings, _project: fake  # type: ignore[assignment]
    try:
        samples = []
        for _ in range(10):
            started = time.perf_counter_ns()
            result = workflows._clusters(None, "benchmark")  # type: ignore[arg-type]
            samples.append((time.perf_counter_ns() - started) / 1e6)
        return {"failed_runs": rows, "clusters": len(result), **distribution(samples)}
    finally:
        workflows._failure_rows = original


def wait_for_trace(
    client: Any, project_id: str, trace_id: str, expected_spans: int, timeout: int = 300
) -> float:
    started = time.perf_counter()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = client.query(
            "SELECT span_count FROM trace_summaries FINAL "
            "WHERE project_id = {project_id:UUID} AND trace_id = {trace_id:String} LIMIT 1",
            parameters={"project_id": project_id, "trace_id": trace_id},
        ).result_rows
        if rows and int(rows[0][0]) == expected_spans:
            return (time.perf_counter() - started) * 1000
        time.sleep(0.25)
    raise RuntimeError(f"Trace {trace_id} did not reach {expected_spans} spans")


def trace_detail_scaling(
    client: Any, project_id: str, key: str, api: str, otlp: str
) -> list[dict[str, Any]]:
    results = []
    for size in (1000, 10_000):
        trace_id = uuid.uuid4().hex
        agent = f"detail-{size}-{uuid.uuid4().hex[:8]}"
        for offset in range(0, size, 2000):
            chunk_size = min(2000, size - offset)
            _, payload = batch(
                agent,
                chunk_size,
                failed=False,
                trace_id=trace_id,
                span_offset=offset,
            )
            request(f"{otlp}/v1/traces", key, payload)
        visible_ms = wait_for_trace(client, project_id, trace_id, size)
        samples = []
        response_bytes = 0
        returned_spans = 0
        total_spans = 0
        for _ in range(10):
            started = time.perf_counter_ns()
            payload = request(f"{api}/api/projects/{project_id}/traces/{trace_id}", key)
            samples.append((time.perf_counter_ns() - started) / 1e6)
            response_bytes = len(payload)
            decoded = json.loads(payload)
            returned_spans = len(decoded["spans"])
            total_spans = int(decoded["total_span_count"])
        if returned_spans != size or total_spans != size:
            raise RuntimeError(
                f"Trace detail returned {returned_spans}/{total_spans} spans for {size}"
            )
        results.append(
            {
                "trace_id": trace_id,
                "source_spans": size,
                "time_to_projection_ms": round(visible_ms, 3),
                "response_bytes": response_bytes,
                "returned_spans": returned_spans,
                **distribution(samples),
            }
        )
    return results


def run(
    spans: int, batch_size: int, concurrency: int, sdk_iterations: int
) -> dict[str, Any]:
    if spans < 1 or spans % batch_size or batch_size > 2000 or concurrency < 1:
        raise ValueError("Use a positive span count divisible by batch size <= 2000")
    settings = load_settings()
    project_id, key_id, key = project_key()
    client = clickhouse(settings)
    api = validated_endpoint(
        "CS_BENCH_API_URL", os.getenv("CS_BENCH_API_URL", "http://api:8000")
    )
    otlp = validated_endpoint(
        "CS_BENCH_OTLP_URL", os.getenv("CS_BENCH_OTLP_URL", "http://ingest:4318")
    )
    agent = "bench-" + uuid.uuid4().hex[:12]
    try:
        before_bytes = storage_bytes(client)
        sdk = sdk_overhead(sdk_iterations)
        batches = [
            batch(agent, batch_size, failed=index % 10 == 0)
            for index in range(spans // batch_size)
        ]
        sent_at: dict[str, float] = {}
        ack_ms: list[float] = []

        def send(item: tuple[str, bytes]) -> None:
            trace_id, payload = item
            started = time.time()
            sent_at[trace_id] = started
            request(f"{otlp}/v1/traces", key, payload)
            ack_ms.append((time.time() - started) * 1000)

        beginning = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(send, batches))
        deadline = time.monotonic() + 300
        summaries: dict[str, float] = {}
        while time.monotonic() < deadline:
            rows = client.query(
                "SELECT trace_id, toUnixTimestamp64Milli(updated_at) "
                "FROM trace_summaries FINAL WHERE project_id = {project_id:UUID} "
                "AND agent_name = {agent:String}",
                parameters={"project_id": project_id, "agent": agent},
            ).result_rows
            summaries = {
                trace.decode("ascii").rstrip("\x00")
                if isinstance(trace, bytes)
                else trace: ms
                for trace, ms in rows
            }
            if len(summaries) == len(batches):
                break
            time.sleep(0.5)
        if len(summaries) != len(batches):
            raise RuntimeError(
                f"Only {len(summaries)}/{len(batches)} traces became visible"
            )
        elapsed = time.perf_counter() - beginning
        visible_ms = [
            max(0.0, summary_ms - sent_at[trace_id] * 1000)
            for trace_id, summary_ms in summaries.items()
        ]
        auth_url = f"{api}/api/projects/{project_id}"
        query_samples = []
        detail_samples = []
        for _ in range(25):
            started = time.perf_counter_ns()
            request(f"{auth_url}/traces?limit=50", key)
            query_samples.append((time.perf_counter_ns() - started) / 1e6)
            started = time.perf_counter_ns()
            request(f"{auth_url}/traces/{batches[0][0]}", key)
            detail_samples.append((time.perf_counter_ns() - started) / 1e6)
        scaling = trace_detail_scaling(client, project_id, key, api, otlp)
        after_bytes = storage_bytes(client)
        measured_storage_spans = spans + sum(item["source_spans"] for item in scaling)
        return {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
            },
            "workload": {
                "spans": spans,
                "batch_size": batch_size,
                "concurrency": concurrency,
            },
            "sdk_overhead": sdk,
            "throughput_spans_per_second_end_to_end": round(spans / elapsed, 2),
            "otlp_ack": distribution(ack_ms),
            "send_to_projection": distribution(visible_ms),
            "trace_list_query": distribution(query_samples),
            "trace_detail_query": distribution(detail_samples),
            "trace_detail_scaling": scaling,
            "failure_clustering_compute": cluster_compute(2000),
            "storage": {
                "measured_spans": measured_storage_spans,
                "bytes_before": before_bytes,
                "bytes_after": after_bytes,
                "delta_bytes": after_bytes - before_bytes,
                "normalized_bytes_per_million_spans_estimate": round(
                    (after_bytes - before_bytes) * 1_000_000 / measured_storage_spans
                ),
                "note": "Estimated from this measured sample, not a million-span run; merges vary.",
            },
            "limitations": [
                "Trace-detail scaling measures API query and JSON serialization, not browser paint time.",
                "Single-node disposable Compose, synthetic spans, no sustained-load or HA claim.",
            ],
        }
    finally:
        client.close()
        with postgres(settings) as connection:
            connection.execute(
                "UPDATE api_keys SET revoked_at = now() WHERE id = %s", (key_id,)
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spans", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--sdk-iterations", type=int, default=10000)
    arguments = parser.parse_args()
    print(
        json.dumps(
            run(
                arguments.spans,
                arguments.batch_size,
                arguments.concurrency,
                arguments.sdk_iterations,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
