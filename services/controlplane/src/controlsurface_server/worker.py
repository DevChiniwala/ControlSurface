"""Replay accepted telemetry batches into raw and derived ClickHouse projections."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
import zlib
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any

from google.protobuf import json_format
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from .domain.failures import FailedRun, failure_signature
from .domain.graph import SpanFact, build_graph, graph_features
from .settings import Settings, load_settings
from .storage import clickhouse, postgres

MAX_PROJECTED_SPANS_PER_TRACE = 10_000

log = logging.getLogger(__name__)
SPAN_COLUMNS = [
    "project_id",
    "trace_id",
    "span_id",
    "parent_span_id",
    "name",
    "start_ns",
    "end_ns",
    "start_time",
    "status",
    "operation",
    "session_id",
    "agent_name",
    "agent_version",
    "tool_name",
    "model_name",
    "input_tokens",
    "output_tokens",
    "cost_nano_usd",
    "resource_json",
    "scope_json",
    "attributes_json",
    "events_json",
    "links_json",
    "ingested_at",
]


def _value(item: Any) -> Any:
    kind = item.WhichOneof("value")
    if kind == "array_value":
        return [_value(value) for value in item.array_value.values]
    if kind == "kvlist_value":
        return {pair.key: _value(pair.value) for pair in item.kvlist_value.values}
    if kind == "bytes_value":
        return item.bytes_value.hex()
    return getattr(item, kind) if kind else None


def _attributes(items: Any) -> dict[str, Any]:
    return {item.key: _value(item.value) for item in items}


def _kind(attributes: dict[str, Any]) -> str:
    explicit = attributes.get("controlsurface.kind")
    if explicit:
        return str(explicit)
    operation = attributes.get("gen_ai.operation.name")
    if operation in {"chat", "generate_content", "text_completion", "embeddings"}:
        return "model"
    if operation in {"execute_tool", "tool"}:
        return "tool"
    return str(operation or "other")


def _num(attributes: dict[str, Any], *names: str) -> int:
    for name in names:
        value = attributes.get(name)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                pass
    return 0


def _span_rows(
    project_id: str, request: ExportTraceServiceRequest
) -> tuple[list[list[Any]], set[str]]:
    rows: list[list[Any]] = []
    traces: set[str] = set()
    received = datetime.now(UTC)
    for resource in request.resource_spans:
        resource_attrs = _attributes(resource.resource.attributes)
        resource_json = json.dumps(resource_attrs, separators=(",", ":"))
        for scope in resource.scope_spans:
            scope_json = json.dumps({"name": scope.scope.name, "version": scope.scope.version})
            for span in scope.spans:
                attrs = {**resource_attrs, **_attributes(span.attributes)}
                trace_id = span.trace_id.hex()
                traces.add(trace_id)
                events = [
                    {
                        "name": event.name,
                        "time_ns": event.time_unix_nano,
                        "attributes": _attributes(event.attributes),
                    }
                    for event in span.events
                ]
                status = "error" if span.status.code == 2 else "ok"
                rows.append(
                    [
                        project_id,
                        trace_id,
                        span.span_id.hex(),
                        span.parent_span_id.hex(),
                        span.name,
                        span.start_time_unix_nano,
                        span.end_time_unix_nano,
                        datetime.fromtimestamp(span.start_time_unix_nano / 1e9, UTC),
                        status,
                        _kind(attrs),
                        str(attrs.get("controlsurface.session.id") or ""),
                        str(attrs.get("controlsurface.agent.name") or ""),
                        str(attrs.get("controlsurface.agent.version") or ""),
                        str(attrs.get("gen_ai.tool.name") or ""),
                        str(
                            attrs.get("gen_ai.response.model")
                            or attrs.get("gen_ai.request.model")
                            or ""
                        ),
                        _num(attrs, "gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens"),
                        _num(attrs, "gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens"),
                        _num(attrs, "controlsurface.cost.nano_usd"),
                        resource_json,
                        scope_json,
                        json.dumps(attrs, separators=(",", ":")),
                        json.dumps(events, separators=(",", ":")),
                        json.dumps(
                            [
                                json_format.MessageToDict(link, preserving_proto_field_name=True)
                                for link in span.links
                            ],
                            separators=(",", ":"),
                        ),
                        received,
                    ]
                )
    return rows, traces


def _refresh_trace(client: Any, project_id: str, trace_id: str) -> None:
    result = client.query(
        "SELECT span_id, parent_span_id, name, start_ns, end_ns, status, session_id, "
        "agent_name, agent_version, input_tokens, output_tokens, cost_nano_usd, "
        "attributes_json, events_json, count() OVER () AS total_span_count, "
        "countIf(status = 'error') OVER () AS total_error_count, "
        "sum(input_tokens) OVER () AS total_input_tokens, "
        "sum(output_tokens) OVER () AS total_output_tokens, "
        "sum(cost_nano_usd) OVER () AS total_cost_nano_usd, "
        "min(start_ns) OVER () AS trace_start_ns, max(end_ns) OVER () AS trace_end_ns "
        "FROM spans FINAL "
        "WHERE project_id = {project_id:UUID} AND trace_id = {trace_id:String} "
        "ORDER BY start_ns, span_id LIMIT {limit:UInt32}",
        parameters={
            "project_id": project_id,
            "trace_id": trace_id,
            "limit": MAX_PROJECTED_SPANS_PER_TRACE,
        },
    )
    if not result.result_rows:
        return
    spans = []
    for row in result.result_rows:
        attrs = json.loads(row[12])
        spans.append(
            SpanFact(
                trace_id,
                row[0].decode("ascii").rstrip("\x00") if isinstance(row[0], bytes) else row[0],
                (row[1].decode("ascii").rstrip("\x00") if isinstance(row[1], bytes) else row[1])
                or None,
                row[2],
                int(row[3]),
                int(row[4]),
                row[5],
                attrs,
                tuple(json.loads(row[13])),
            )
        )
    graph = build_graph(spans)
    total_span_count = int(result.result_rows[0][14])
    total_error_count = int(result.result_rows[0][15])
    total_input_tokens = int(result.result_rows[0][16])
    total_output_tokens = int(result.result_rows[0][17])
    total_cost_nano_usd = int(result.result_rows[0][18])
    trace_start_ns = int(result.result_rows[0][19])
    trace_end_ns = int(result.result_rows[0][20])
    if total_error_count and graph.outcome == "success":
        graph = replace(graph, outcome="error")
    roots = [span for span in spans if not span.parent_span_id]
    root = min(roots or spans, key=lambda item: item.start_ns)
    start_ns = trace_start_ns
    end_ns = trace_end_ns
    session = next((row[6] for row in result.result_rows if row[6]), graph.session_id)
    agent = next((row[7] for row in result.result_rows if row[7]), "")
    version = next((row[8] for row in result.result_rows if row[8]), "")
    now = datetime.now(UTC)
    client.insert(
        "trace_summaries",
        [
            [
                project_id,
                trace_id,
                session,
                agent,
                version,
                root.name,
                datetime.fromtimestamp(start_ns / 1e9, UTC),
                datetime.fromtimestamp(end_ns / 1e9, UTC),
                max(0, (end_ns - start_ns) // 1_000_000),
                total_span_count,
                total_error_count,
                total_input_tokens,
                total_output_tokens,
                total_cost_nano_usd,
                graph.outcome,
                now,
            ]
        ],
        column_names=[
            "project_id",
            "trace_id",
            "session_id",
            "agent_name",
            "agent_version",
            "root_name",
            "start_time",
            "end_time",
            "duration_ms",
            "span_count",
            "error_count",
            "input_tokens",
            "output_tokens",
            "cost_nano_usd",
            "status",
            "updated_at",
        ],
    )
    features = graph_features(graph)
    if total_span_count > len(spans):
        features["projection_truncated"] = True
        features["projected_span_count"] = len(spans)
        features["total_span_count"] = total_span_count
    if graph.outcome != "success":
        error_event = next(
            (event for span in spans for event in span.events if event.get("name") == "exception"),
            {},
        )
        error_type = str(error_event.get("attributes", {}).get("exception.type") or "span_error")
        failed_tool = next(
            (
                str(span.attributes.get("gen_ai.tool.name") or span.name)
                for span in spans
                if span.status == "error" and _kind(span.attributes) == "tool"
            ),
            None,
        )
        input_value = root.attributes.get("controlsurface.input")
        input_hash = hashlib.sha256(str(input_value or trace_id).encode()).hexdigest()
        signature, structural = failure_signature(
            FailedRun(
                graph,
                error_type,
                failed_tool,
                input_hash,
                start_ns,
            )
        )
        features.update(
            {
                "failure_signature": signature,
                "failure_structure": structural,
                "input_fingerprint": input_hash,
            }
        )
    client.insert(
        "agent_run_graphs",
        [
            [
                project_id,
                graph.run_id,
                trace_id,
                session,
                graph.version,
                json.dumps(asdict(graph), separators=(",", ":")),
                json.dumps(features, separators=(",", ":")),
                graph.outcome,
                now,
                datetime.fromtimestamp(start_ns / 1e9, UTC),
            ]
        ],
        column_names=[
            "project_id",
            "run_id",
            "trace_id",
            "session_id",
            "graph_version",
            "graph_json",
            "features_json",
            "outcome",
            "updated_at",
            "occurred_at",
        ],
    )


def process_one(settings: Settings) -> bool:
    owner = uuid.uuid4()
    with postgres(settings) as connection:
        with connection.transaction():
            row = connection.execute(
                "SELECT id, project_id, payload_zlib FROM telemetry_inbox "
                "WHERE processed_at IS NULL AND dead_letter_at IS NULL "
                "AND available_at <= now() "
                "AND (lease_until IS NULL OR lease_until < now()) "
                "ORDER BY received_at LIMIT 1 FOR UPDATE SKIP LOCKED"
            ).fetchone()
            if not row:
                return False
            connection.execute(
                "UPDATE telemetry_inbox SET lease_owner = %s, "
                "lease_until = now() + interval '2 minutes', attempts = attempts + 1 WHERE id = %s",
                (owner, row["id"]),
            )
    try:
        request = json_format.Parse(
            zlib.decompress(row["payload_zlib"]).decode("utf-8"),
            ExportTraceServiceRequest(),
        )
        project_id = str(row["project_id"])
        rows, traces = _span_rows(project_id, request)
        client = clickhouse(settings)
        try:
            if rows:
                client.insert("spans", rows, column_names=SPAN_COLUMNS)
            for trace_id in sorted(traces):
                # Concurrent batches may contain different spans from the same
                # trace. Serialize each derived projection so a late partial
                # summary cannot replace a complete one.
                lock_key = int.from_bytes(
                    hashlib.sha256(f"{project_id}:{trace_id}".encode()).digest()[:8],
                    "big",
                    signed=True,
                )
                with postgres(settings) as connection:
                    with connection.transaction():
                        connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
                        _refresh_trace(client, project_id, trace_id)
        finally:
            client.close()
        with postgres(settings) as connection:
            connection.execute(
                "UPDATE telemetry_inbox SET processed_at = now(), lease_owner = NULL, "
                "lease_until = NULL, last_error = NULL WHERE id = %s AND lease_owner = %s",
                (row["id"], owner),
            )
    except Exception as error:
        log.exception("Telemetry batch processing failed", extra={"batch_id": str(row["id"])})
        with postgres(settings) as connection:
            connection.execute(
                "UPDATE telemetry_inbox SET lease_owner = NULL, lease_until = NULL, "
                "available_at = now() + make_interval(secs => "
                "LEAST(300, power(2, LEAST(attempts, 8))::int)), "
                "dead_letter_at = CASE WHEN attempts >= 10 THEN now() ELSE NULL END, "
                "last_error = %s WHERE id = %s AND lease_owner = %s",
                (type(error).__name__, row["id"], owner),
            )
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    next_cleanup = time.monotonic() + 60
    while True:
        if time.monotonic() >= next_cleanup:
            with postgres(settings) as connection:
                connection.execute(
                    "DELETE FROM telemetry_inbox WHERE id IN "
                    "(SELECT id FROM telemetry_inbox WHERE processed_at < now() - interval '1 day' "
                    "OR dead_letter_at < now() - interval '7 days' LIMIT 1000)"
                )
            next_cleanup = time.monotonic() + 60
        if not process_one(settings):
            time.sleep(0.5)


if __name__ == "__main__":
    main()
