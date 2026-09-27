import json

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from controlsurface_server.ingest import (
    BatchRejected,
    parse_http_body,
    sanitized_payload,
    span_count,
)
from controlsurface_server.worker import _span_rows


def sample_request() -> ExportTraceServiceRequest:
    request = ExportTraceServiceRequest()
    resource = request.resource_spans.add()
    agent = resource.resource.attributes.add()
    agent.key = "controlsurface.agent.name"
    agent.value.string_value = "refund-agent"
    scope = resource.scope_spans.add()
    span = scope.spans.add()
    span.trace_id = bytes.fromhex("a" * 32)
    span.span_id = bytes.fromhex("b" * 16)
    span.name = "refund-request"
    span.start_time_unix_nano = 1_700_000_000_000_000_000
    span.end_time_unix_nano = span.start_time_unix_nano + 2_000_000
    attr = span.attributes.add()
    attr.key = "authorization"
    attr.value.string_value = "Bearer sensitive-value"
    token = span.attributes.add()
    token.key = "gen_ai.usage.input_tokens"
    token.value.int_value = 42
    return request


def test_otlp_protobuf_contract_and_redaction():
    request = sample_request()
    decoded = parse_http_body(request.SerializeToString(), "application/x-protobuf")
    assert span_count(decoded) == 1
    body = json.loads(sanitized_payload(decoded))
    attributes = body["resource_spans"][0]["scope_spans"][0]["spans"][0]["attributes"]
    assert attributes[0]["value"]["string_value"] == "[REDACTED]"


def test_redacts_cookie_attributes_and_url_query_secrets():
    request = sample_request()
    span = request.resource_spans[0].scope_spans[0].spans[0]
    cookie = span.attributes.add()
    cookie.key = "http.request.header.cookie"
    cookie.value.string_value = "session=private"
    url = span.attributes.add()
    url.key = "url.full"
    url.value.string_value = "https://example.invalid/callback?token=private&mode=safe"
    payload = sanitized_payload(request).decode()
    assert "session=private" not in payload
    assert "token=private" not in payload
    assert "token=[REDACTED]" in payload


def test_otlp_rejects_malformed_protobuf():
    with pytest.raises(BatchRejected):
        parse_http_body(b"\xff\x80\xff", "application/x-protobuf")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("trace_id", b"short", "invalid trace or span identifier"),
        ("span_id", b"short", "invalid trace or span identifier"),
        ("parent_span_id", b"short", "invalid parent span identifier"),
    ],
)
def test_otlp_rejects_invalid_identifiers(field: str, value: bytes, message: str):
    request = sample_request()
    setattr(request.resource_spans[0].scope_spans[0].spans[0], field, value)
    with pytest.raises(BatchRejected, match=message):
        sanitized_payload(request)


def test_otlp_rejects_negative_duration():
    request = sample_request()
    span = request.resource_spans[0].scope_spans[0].spans[0]
    span.end_time_unix_nano = span.start_time_unix_nano - 1
    with pytest.raises(BatchRejected, match="end time"):
        sanitized_payload(request)


def test_flattened_span_preserves_resource_and_usage():
    rows, traces = _span_rows("00000000-0000-0000-0000-000000000001", sample_request())
    assert traces == {"a" * 32}
    assert rows[0][11] == "refund-agent"
    assert rows[0][15] == 42
