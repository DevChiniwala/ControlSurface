"""Bounded OpenTelemetry instrumentation that never blocks application success."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span

_log = logging.getLogger(__name__)
_session: contextvars.ContextVar[str | None] = contextvars.ContextVar("cs_session", default=None)
_run: contextvars.ContextVar[str | None] = contextvars.ContextVar("cs_run", default=None)
_SECRET_MARKERS = ("token", "password", "secret", "authorization", "api_key", "credential")


def _safe_attributes(attributes: dict[str, Any]) -> dict[str, str | int | float | bool]:
    result: dict[str, str | int | float | bool] = {}
    for key, value in attributes.items():
        if any(marker in key.lower() for marker in _SECRET_MARKERS):
            result[key] = "[REDACTED]"
        elif isinstance(value, bool | int | float):
            result[key] = value
        elif value is not None:
            result[key] = str(value)[:8192]
    return result


@dataclass
class ControlSurface:
    """Application-owned tracer provider; no global OTel provider mutation."""

    provider: TracerProvider
    tracer: trace.Tracer
    endpoint: str

    @classmethod
    def init(
        cls,
        endpoint: str = "http://localhost:4318",
        api_key: str | None = None,
        service_name: str = "agent",
        agent_name: str | None = None,
        agent_version: str | None = None,
        environment: str = "development",
    ) -> ControlSurface:
        key = api_key or os.getenv("CONTROLSURFACE_API_KEY")
        if not key:
            raise ValueError("ControlSurface API key is required")
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("ControlSurface endpoint must be an HTTP(S) URL")
        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment.name": environment,
                "controlsurface.agent.name": agent_name or service_name,
                "controlsurface.agent.version": agent_version or "",
            }
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=endpoint.rstrip("/") + "/v1/traces",
            headers={"Authorization": f"Bearer {key}"},
            timeout=2,
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_queue_size=2048,
                max_export_batch_size=256,
                schedule_delay_millis=2000,
                export_timeout_millis=3000,
            )
        )
        return cls(provider, provider.get_tracer("controlsurface", "0.1.0"), endpoint)

    @contextlib.contextmanager
    def session(self, session_id: str | None = None) -> Iterator[str]:
        value = session_id or str(uuid.uuid4())
        token = _session.set(value)
        try:
            yield value
        finally:
            _session.reset(token)

    @contextlib.contextmanager
    def run(
        self, name: str, input: str | None = None, attributes: dict[str, Any] | None = None
    ) -> Iterator[Span]:
        run_id = str(uuid.uuid4())
        token = _run.set(run_id)
        attrs: dict[str, Any] = {"controlsurface.kind": "agent", "controlsurface.run.id": run_id}
        if input is not None:
            attrs["controlsurface.input"] = input[:8192]
        attrs.update(attributes or {})
        try:
            with self.span(name, "agent", attrs) as span:
                yield span
        finally:
            _run.reset(token)

    @contextlib.contextmanager
    def span(
        self, name: str, kind: str = "workflow", attributes: dict[str, Any] | None = None
    ) -> Iterator[Span]:
        attrs: dict[str, Any] = {"controlsurface.kind": kind}
        if _session.get():
            attrs["controlsurface.session.id"] = _session.get()
        if _run.get():
            attrs["controlsurface.run.id"] = _run.get()
        attrs.update(attributes or {})
        with self.tracer.start_as_current_span(
            name,
            attributes=_safe_attributes(attrs),
            record_exception=True,
            set_status_on_exception=True,
        ) as span:
            yield span

    def shutdown(self, timeout_millis: int = 3000) -> None:
        try:
            self.provider.force_flush(timeout_millis=timeout_millis)
            self.provider.shutdown()
        except Exception:
            _log.warning("ControlSurface telemetry shutdown failed", exc_info=False)
