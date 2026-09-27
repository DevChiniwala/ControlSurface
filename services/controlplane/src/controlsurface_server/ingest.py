"""OTLP trace parsing, redaction, and durable batch acceptance."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import zlib
from typing import Any

from google.protobuf import json_format
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from .settings import Settings
from .storage import postgres

_SENSITIVE_KEY = re.compile(
    r"(?:^|[._-])(authorization|password|passwd|secret|token|api[_-]?key|credential|"
    r"cookie|set[_-]?cookie)(?:$|[._-])",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_URL_SECRET = re.compile(
    r"([?&](?:access[_-]?token|api[_-]?key|token|password|secret)=)[^&#\s]+",
    re.IGNORECASE,
)
_MAX_STRING = 64 * 1024
_MAX_ATTRIBUTE_DEPTH = 32
MAX_SPANS_PER_BATCH = 2_000


class BatchRejected(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def span_count(message: ExportTraceServiceRequest) -> int:
    return sum(
        len(scope.spans) for resource in message.resource_spans for scope in resource.scope_spans
    )


def _redact_tree(value: Any, depth: int = 0) -> Any:
    if depth > _MAX_ATTRIBUTE_DEPTH:
        return "[TRUNCATED: nesting limit]"
    if isinstance(value, list):
        return [_redact_tree(item, depth + 1) for item in value]
    if isinstance(value, dict):
        key = value.get("key")
        if isinstance(key, str) and _SENSITIVE_KEY.search(key):
            return {**value, "value": {"string_value": "[REDACTED]"}}
        return {name: _redact_tree(item, depth + 1) for name, item in value.items()}
    if isinstance(value, str):
        clipped = value[:_MAX_STRING]
        return _URL_SECRET.sub(r"\1[REDACTED]", _BEARER.sub("Bearer [REDACTED]", clipped))
    return value


def sanitized_payload(message: ExportTraceServiceRequest) -> bytes:
    count = span_count(message)
    if count > MAX_SPANS_PER_BATCH:
        raise BatchRejected("Too many spans in one request", 413)
    for resource in message.resource_spans:
        for scope in resource.scope_spans:
            for span in scope.spans:
                if len(span.trace_id) != 16 or len(span.span_id) != 8:
                    raise BatchRejected("Span contains an invalid trace or span identifier")
                if span.parent_span_id and len(span.parent_span_id) != 8:
                    raise BatchRejected("Span contains an invalid parent span identifier")
                if span.end_time_unix_nano and span.end_time_unix_nano < span.start_time_unix_nano:
                    raise BatchRejected("Span end time precedes its start time")
    body = json_format.MessageToDict(message, preserving_proto_field_name=True)
    return json.dumps(_redact_tree(body), separators=(",", ":"), sort_keys=True).encode("utf-8")


def parse_http_body(body: bytes, content_type: str) -> ExportTraceServiceRequest:
    message = ExportTraceServiceRequest()
    try:
        if content_type == "application/x-protobuf":
            message.ParseFromString(body)
        elif content_type == "application/json":
            json_format.Parse(body.decode("utf-8"), message)
        else:
            raise BatchRejected("Unsupported OTLP content type", 415)
    except (UnicodeDecodeError, json_format.ParseError, DecodeError, ValueError) as error:
        if isinstance(error, BatchRejected):
            raise
        raise BatchRejected("Invalid OTLP trace request") from error
    return message


def accept_batch(settings: Settings, project_id: str, message: ExportTraceServiceRequest) -> str:
    payload = sanitized_payload(message)
    if len(payload) > settings.max_uncompressed_bytes:
        raise BatchRejected("Trace payload exceeds uncompressed limit", 413)
    compressed = zlib.compress(payload, level=3)
    digest = hashlib.sha256(payload).digest()
    batch_id = str(uuid.uuid4())
    with postgres(settings) as connection:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(4178164)")
            pending_row = connection.execute(
                "SELECT COALESCE(sum(octet_length(payload_zlib)), 0) AS bytes "
                "FROM telemetry_inbox WHERE processed_at IS NULL AND dead_letter_at IS NULL"
            ).fetchone()
            if pending_row is None:
                raise RuntimeError("Telemetry inbox aggregate returned no row")
            pending = pending_row["bytes"]
            if pending + len(compressed) > settings.max_pending_bytes:
                raise BatchRejected("Telemetry backlog is full; retry later", 503)
            connection.execute(
                "INSERT INTO telemetry_inbox "
                "(id, project_id, payload_hash, payload_zlib, content_type) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (project_id, payload_hash) DO NOTHING",
                (batch_id, project_id, digest, compressed, "application/json"),
            )
    return batch_id
