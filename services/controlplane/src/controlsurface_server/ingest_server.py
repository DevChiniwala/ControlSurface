"""Run OTLP HTTP and gRPC listeners against the same authenticated inbox."""

from __future__ import annotations

import asyncio
import zlib

import grpc
import psycopg
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from google.protobuf import json_format
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc
from psycopg_pool import PoolTimeout

from .auth import project_for_api_key
from .ingest import BatchRejected, accept_batch, parse_http_body
from .settings import Settings, load_settings
from .storage import postgres

app = FastAPI(title="ControlSurface OTLP ingest", docs_url=None, redoc_url=None)


def _bearer(header: str | None) -> str | None:
    if not header or not header.lower().startswith("bearer "):
        return None
    return header[7:].strip()


def _project(settings: Settings, header: str | None) -> str:
    token = _bearer(header)
    if not token:
        raise BatchRejected("Invalid API key", 401)
    with postgres(settings) as connection:
        project_id = project_for_api_key(connection, token)
    if not project_id:
        raise BatchRejected("Invalid API key", 401)
    return project_id


async def _limited_body(request: Request, settings: Settings) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > settings.max_request_bytes:
            raise BatchRejected("Trace request exceeds compressed limit", 413)
        chunks.append(chunk)
    raw = b"".join(chunks)
    encoding = request.headers.get("content-encoding", "").lower()
    if encoding == "gzip":
        try:
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            body = decoder.decompress(raw, settings.max_uncompressed_bytes + 1)
        except zlib.error as error:
            raise BatchRejected("Invalid gzip payload") from error
        if (
            decoder.unconsumed_tail
            or len(body) > settings.max_uncompressed_bytes
            or not decoder.eof
        ):
            raise BatchRejected("Trace request exceeds uncompressed limit", 413)
        return body
    if encoding not in {"", "identity"}:
        raise BatchRejected("Unsupported content encoding", 415)
    return raw


@app.post("/v1/traces")
async def receive_traces(request: Request) -> Response:
    settings = load_settings()
    try:
        project_id = await asyncio.to_thread(
            _project, settings, request.headers.get("authorization")
        )
        body = await _limited_body(request, settings)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        message = parse_http_body(body, content_type)
        await asyncio.to_thread(accept_batch, settings, project_id, message)
    except (psycopg.Error, PoolTimeout) as error:
        raise HTTPException(
            503, "Telemetry storage unavailable", headers={"Retry-After": "2"}
        ) from error
    except BatchRejected as error:
        headers = {"Retry-After": "2"} if error.status == 503 else None
        raise HTTPException(error.status, str(error), headers=headers) from error
    answer = trace_service_pb2.ExportTraceServiceResponse()
    if content_type == "application/json":
        return Response(
            json_format.MessageToJson(answer), status_code=200, media_type="application/json"
        )
    return Response(
        answer.SerializeToString(), status_code=200, media_type="application/x-protobuf"
    )


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


class TraceService(trace_service_pb2_grpc.TraceServiceServicer):
    async def Export(self, request, context):  # type: ignore[no-untyped-def]
        settings = load_settings()
        metadata = dict(context.invocation_metadata())
        try:
            project_id = await asyncio.to_thread(_project, settings, metadata.get("authorization"))
            await asyncio.to_thread(accept_batch, settings, project_id, request)
        except (psycopg.Error, PoolTimeout) as error:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Telemetry storage unavailable")
            raise RuntimeError("gRPC abort returned unexpectedly") from error
        except BatchRejected as error:
            code = (
                grpc.StatusCode.UNAUTHENTICATED
                if error.status == 401
                else grpc.StatusCode.RESOURCE_EXHAUSTED
                if error.status in {413, 503}
                else grpc.StatusCode.INVALID_ARGUMENT
            )
            await context.abort(code, str(error))
        return trace_service_pb2.ExportTraceServiceResponse()


async def main() -> None:
    settings = load_settings()
    grpc_server = grpc.aio.server(
        options=[("grpc.max_receive_message_length", settings.max_request_bytes)]
    )
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(TraceService(), grpc_server)
    grpc_server.add_insecure_port("0.0.0.0:4317")
    await grpc_server.start()
    http_server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=4318, log_level="info"))
    try:
        await http_server.serve()
    finally:
        await grpc_server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(main())
