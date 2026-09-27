"""Single-owner control plane with project-scoped operational APIs."""

from __future__ import annotations

import hmac
import json
import os
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, Field

from .auth import (
    LoginRateLimiter,
    create_api_key,
    create_browser_session,
    create_owner,
    csrf_token,
    verify_password,
)
from .dependencies import actor as _actor
from .dependencies import advisory_lock_key
from .dependencies import authorized_project as _authorized_project
from .dependencies import query_clickhouse as _query
from .dependencies import settings_dependency as _settings
from .domain.changes import compare_contracts, fingerprint
from .domain.slo import SloMetrics, SloPolicy, evaluate_slo_metrics
from .settings import Settings
from .storage import postgres

_cors_origins = [
    origin.strip()
    for origin in os.getenv("CS_CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
if not _cors_origins or "*" in _cors_origins:
    raise RuntimeError("CS_CORS_ORIGINS must contain explicit browser origins")

app = FastAPI(title="ControlSurface API", version="0.1.0")
_login_attempts = LoginRateLimiter()
_MAX_CONTROL_REQUEST_BYTES = 2 * 1024 * 1024
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Bootstrap-Token", "X-CSRF-Token"],
)


@app.middleware("http")
async def limit_control_request_body(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Bound JSON control-plane requests even without a reverse proxy."""
    if request.method in {"POST", "PUT", "PATCH"}:
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                if int(raw_length) > _MAX_CONTROL_REQUEST_BYTES:
                    return JSONResponse({"detail": "Request body too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        body = await request.body()
        if len(body) > _MAX_CONTROL_REQUEST_BYTES:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
    return await call_next(request)


class SetupInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)
    project_name: str = Field(min_length=1, max_length=120)


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,62}$")


class KeyInput(BaseModel):
    label: str = Field(min_length=1, max_length=100)


class ChangeInput(BaseModel):
    change_type: str = Field(min_length=1, max_length=64)
    subject_type: str = Field(min_length=1, max_length=64)
    subject_name: str = Field(min_length=1, max_length=200)
    before_version: str | None = Field(default=None, max_length=200)
    after_version: str | None = Field(default=None, max_length=200)
    before_hash: str | None = Field(default=None, max_length=256)
    after_hash: str | None = Field(default=None, max_length=256)
    deployment_id: str | None = Field(default=None, max_length=200)
    environment: str = Field(default="production", min_length=1, max_length=100)
    effective_at: AwareDatetime
    details: dict[str, Any] = Field(default_factory=dict)


class ToolSchemaInput(BaseModel):
    tool_name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    schema_data: dict[str, Any] = Field(alias="schema_json")
    environment: str = Field(default="production", min_length=1, max_length=100)


class SloInput(BaseModel):
    agent_name: str = Field(min_length=1, max_length=200)
    policy: SloPolicy


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready(settings: Settings = Depends(_settings)) -> dict[str, str]:
    try:
        with postgres(settings) as connection:
            connection.execute("SELECT 1")
        _query(settings, "SELECT 1", {})
    except Exception as error:
        raise HTTPException(503, "Storage unavailable") from error
    return {"status": "ok"}


@app.get("/api/setup/status")
def setup_status(settings: Settings = Depends(_settings)) -> dict[str, bool]:
    with postgres(settings) as connection:
        exists = connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
    return {"configured": exists}


@app.post("/api/setup", status_code=201)
def setup(
    data: SetupInput,
    response: Response,
    x_bootstrap_token: str | None = Header(default=None),
    settings: Settings = Depends(_settings),
) -> dict[str, str]:
    if not x_bootstrap_token or not hmac.compare_digest(
        x_bootstrap_token, settings.bootstrap_token
    ):
        raise HTTPException(403, "Invalid bootstrap token")
    with postgres(settings) as connection:
        try:
            user_id, project_id = create_owner(
                connection, data.email, data.password, data.project_name
            )
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        token = create_browser_session(connection, user_id)
    response.set_cookie(
        "cs_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=7 * 86400,
    )
    return {"project_id": project_id}


@app.post("/api/login")
def login(
    data: LoginInput,
    request: Request,
    response: Response,
    settings: Settings = Depends(_settings),
) -> dict[str, str]:
    retry_after = _login_attempts.acquire(request.client.host if request.client else "unknown")
    if retry_after:
        raise HTTPException(
            429, "Too many login attempts", headers={"Retry-After": str(retry_after)}
        )
    with postgres(settings) as connection:
        user_id = verify_password(connection, data.email, data.password)
        if not user_id:
            raise HTTPException(401, "Invalid credentials")
        token = create_browser_session(connection, user_id)
    response.set_cookie(
        "cs_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=7 * 86400,
    )
    return {"status": "ok"}


@app.post("/api/logout")
def logout(
    request: Request,
    response: Response,
    actor: tuple[str, str] = Depends(_actor),
    settings: Settings = Depends(_settings),
) -> dict[str, str]:
    if actor[0] != "user":
        raise HTTPException(403, "Owner session required")
    token = request.cookies.get("cs_session")
    if token:
        import hashlib

        with postgres(settings) as connection:
            connection.execute(
                "DELETE FROM browser_sessions WHERE token_hash = %s",
                (hashlib.sha256(token.encode()).digest(),),
            )
    response.delete_cookie("cs_session")
    return {"status": "ok"}


@app.get("/api/session/csrf")
def session_csrf(
    request: Request,
    response: Response,
    actor: tuple[str, str] = Depends(_actor),
) -> dict[str, str]:
    if actor[0] != "user":
        raise HTTPException(403, "Owner session required")
    response.headers["Cache-Control"] = "no-store"
    return {"token": csrf_token(request.cookies["cs_session"])}


@app.get("/api/projects")
def projects(
    actor: tuple[str, str] = Depends(_actor), settings: Settings = Depends(_settings)
) -> list[dict[str, Any]]:
    with postgres(settings) as connection:
        if actor[0] == "key":
            rows = connection.execute(
                "SELECT id, name, slug, created_at FROM projects WHERE id = %s",
                (actor[1],),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT id, name, slug, created_at FROM projects WHERE owner_id = %s "
                "ORDER BY created_at",
                (actor[1],),
            ).fetchall()
    return jsonable_encoder(rows)


@app.post("/api/projects", status_code=201)
def create_project(
    data: ProjectInput,
    actor: tuple[str, str] = Depends(_actor),
    settings: Settings = Depends(_settings),
) -> dict[str, str]:
    if actor[0] != "user":
        raise HTTPException(403, "Owner session required")
    project_id = uuid.uuid4()
    with postgres(settings) as connection:
        try:
            connection.execute(
                "INSERT INTO projects(id, name, slug, owner_id) VALUES (%s, %s, %s, %s)",
                (project_id, data.name, data.slug, actor[1]),
            )
        except psycopg.errors.UniqueViolation as error:
            raise HTTPException(409, "Project slug unavailable") from error
    return {"id": str(project_id)}


@app.get("/api/projects/{project_id}/keys")
def list_keys(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> list[dict[str, Any]]:
    with postgres(settings) as connection:
        rows = connection.execute(
            "SELECT id, prefix, label, created_at, revoked_at FROM api_keys "
            "WHERE project_id = %s ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return jsonable_encoder(rows)


@app.post("/api/projects/{project_id}/keys", status_code=201)
def new_key(
    project_id: uuid.UUID,
    data: KeyInput,
    actor: tuple[str, str] = Depends(_actor),
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> dict[str, str]:
    if actor[0] != "user":
        raise HTTPException(403, "Owner session required")
    with postgres(settings) as connection:
        key_id, raw = create_api_key(connection, str(project_id), data.label)
    return {"id": key_id, "key": raw}


@app.delete("/api/projects/{project_id}/keys/{key_id}")
def revoke_key(
    project_id: uuid.UUID,
    key_id: uuid.UUID,
    actor: tuple[str, str] = Depends(_actor),
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> dict[str, str]:
    if actor[0] != "user":
        raise HTTPException(403, "Owner session required")
    with postgres(settings) as connection:
        row = connection.execute(
            "UPDATE api_keys SET revoked_at = now() WHERE id = %s AND project_id = %s "
            "AND revoked_at IS NULL RETURNING id",
            (key_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "API key not found")
    return {"status": "revoked"}


@app.get("/api/projects/{project_id}/traces")
def traces(
    project_id: uuid.UUID,
    agent: str | None = None,
    session: str | None = Query(default=None, max_length=512),
    status: str | None = None,
    limit: int = 50,
    before: datetime | None = None,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 200)
    rows = _query(
        settings,
        "SELECT trace_id, session_id, agent_name, agent_version, root_name, "
        "start_time, duration_ms, span_count, error_count, "
        "nullIf(input_tokens, 0) AS input_tokens, "
        "nullIf(output_tokens, 0) AS output_tokens, "
        "nullIf(cost_nano_usd, 0) AS cost_nano_usd, status "
        "FROM trace_summaries FINAL "
        "WHERE project_id = {project_id:UUID} "
        "AND ({agent:String} = '' OR agent_name = {agent:String}) "
        "AND ({filter_session:UInt8} = 0 OR session_id = {session:String}) "
        "AND ({status:String} = '' OR status = {status:String}) "
        "AND start_time < {before:DateTime64(9)} "
        "ORDER BY start_time DESC LIMIT {limit:UInt32}",
        {
            "project_id": str(project_id),
            "agent": agent or "",
            "session": session or "",
            "filter_session": int(session is not None),
            "status": status or "",
            "before": before or datetime.now(UTC) + timedelta(days=1),
            "limit": limit,
        },
    )
    return jsonable_encoder(rows)


@app.get("/api/projects/{project_id}/traces/{trace_id}")
def trace_detail(
    project_id: uuid.UUID,
    trace_id: str,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> dict[str, Any]:
    if len(trace_id) != 32 or not all(char in "0123456789abcdef" for char in trace_id):
        raise HTTPException(404, "Trace not found")
    spans = _query(
        settings,
        "SELECT span_id, parent_span_id, name, start_ns, end_ns, status, operation, "
        "session_id, agent_name, agent_version, tool_name, model_name, "
        "nullIf(input_tokens, 0) AS input_tokens, "
        "nullIf(output_tokens, 0) AS output_tokens, "
        "nullIf(cost_nano_usd, 0) AS cost_nano_usd, "
        "resource_json, scope_json, attributes_json, "
        "events_json, links_json, count() OVER () AS total_span_count FROM spans FINAL "
        "WHERE project_id = {project_id:UUID} AND trace_id = {trace_id:String} "
        "ORDER BY start_ns LIMIT 10000",
        {"project_id": str(project_id), "trace_id": trace_id},
    )
    if not spans:
        raise HTTPException(404, "Trace not found")
    total_span_count = int(spans[0].pop("total_span_count"))
    for span in spans:
        span.pop("total_span_count", None)
        for field in (
            "resource_json",
            "scope_json",
            "attributes_json",
            "events_json",
            "links_json",
        ):
            span[field.removesuffix("_json")] = json.loads(span.pop(field))
    graph = _query(
        settings,
        "SELECT graph_json, features_json, outcome FROM agent_run_graphs FINAL "
        "WHERE project_id = {project_id:UUID} AND trace_id = {trace_id:String} LIMIT 1",
        {"project_id": str(project_id), "trace_id": trace_id},
    )
    return jsonable_encoder(
        {
            "trace_id": trace_id,
            "spans": spans,
            "total_span_count": total_span_count,
            "truncated": total_span_count > len(spans),
            "graph": json.loads(graph[0]["graph_json"]) if graph else None,
            "features": json.loads(graph[0]["features_json"]) if graph else None,
        }
    )


@app.get("/api/projects/{project_id}/sessions")
def sessions(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> list[dict[str, Any]]:
    return jsonable_encoder(
        _query(
            settings,
            "SELECT session_id, count() AS trace_count, max(start_time) AS last_seen, "
            "sum(error_count) AS errors, nullIf(sum(cost_nano_usd), 0) AS cost_nano_usd, "
            "nullIf(sum(duration_ms), 0) AS duration_ms, "
            "nullIf(sum(input_tokens), 0) AS input_tokens, "
            "nullIf(sum(output_tokens), 0) AS output_tokens "
            "FROM trace_summaries FINAL WHERE project_id = {project_id:UUID} "
            "GROUP BY session_id ORDER BY last_seen DESC LIMIT 100",
            {"project_id": str(project_id)},
        )
    )


@app.get("/api/projects/{project_id}/sessions/{session_id:path}")
def session_detail(
    project_id: uuid.UUID,
    session_id: str,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> dict[str, Any]:
    if not session_id or len(session_id) > 512:
        raise HTTPException(404, "Session not found")
    rows = _query(
        settings,
        "SELECT session_id, count() AS trace_count, max(start_time) AS last_seen, "
        "sum(error_count) AS errors, nullIf(sum(cost_nano_usd), 0) AS cost_nano_usd, "
        "nullIf(sum(duration_ms), 0) AS duration_ms, "
        "nullIf(sum(input_tokens), 0) AS input_tokens, "
        "nullIf(sum(output_tokens), 0) AS output_tokens "
        "FROM trace_summaries FINAL WHERE project_id = {project_id:UUID} "
        "AND session_id = {session_id:String} GROUP BY session_id LIMIT 1",
        {"project_id": str(project_id), "session_id": session_id},
    )
    if not rows:
        raise HTTPException(404, "Session not found")
    return jsonable_encoder(rows[0])


@app.get("/api/projects/{project_id}/health")
def production_health(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> dict[str, Any]:
    rows = _query(
        settings,
        "SELECT agent_name, count() AS runs, countIf(status = 'success') AS completed_runs, "
        "countIf(status != 'success') AS failed_runs, "
        "quantileExact(0.95)(duration_ms) AS p95_latency_ms, "
        "sum(cost_nano_usd) AS cost_nano_usd, max(span_count) AS maximum_steps, "
        "max(start_time) AS last_seen "
        "FROM trace_summaries FINAL WHERE project_id = {project_id:UUID} "
        "AND start_time >= now() - interval 1 day GROUP BY agent_name ORDER BY failed_runs DESC",
        {"project_id": str(project_id)},
    )
    tool_rows = _query(
        settings,
        "SELECT run.agent_name AS agent_name, count() AS tool_calls, "
        "countIf(tool.status = 'ok') AS successful_tool_calls "
        "FROM (SELECT trace_id, status FROM spans FINAL "
        "WHERE project_id = {project_id:UUID} AND operation = 'tool' "
        "AND start_time >= now() - interval 1 day) AS tool ANY INNER JOIN "
        "(SELECT trace_id, agent_name FROM trace_summaries FINAL "
        "WHERE project_id = {project_id:UUID} "
        "AND start_time >= now() - interval 1 day) AS run "
        "ON tool.trace_id = run.trace_id GROUP BY run.agent_name",
        {"project_id": str(project_id)},
    )
    summary_rows = _query(
        settings,
        "SELECT count() AS observed_run_count, "
        "countIf(status != 'success') AS failed_run_count, "
        "if(count() = 0, NULL, countIf(status = 'success') / count()) AS completion_rate, "
        "quantileExactOrNull(0.95)(duration_ms) AS p95_latency_ms, "
        "sum(cost_nano_usd) AS recorded_cost_nano_usd "
        "FROM trace_summaries FINAL WHERE project_id = {project_id:UUID} "
        "AND start_time >= now() - interval 1 day",
        {"project_id": str(project_id)},
    )
    with postgres(settings) as connection:
        policies = cast(
            list[dict[str, Any]],
            connection.execute(
                "SELECT agent_name, policy_json FROM slo_policies WHERE project_id = %s",
                (project_id,),
            ).fetchall(),
        )
        incident_rows = cast(
            list[dict[str, Any]],
            connection.execute(
                "SELECT agent_name, count(*) AS count FROM incidents "
                "WHERE project_id = %s AND status = 'open' GROUP BY agent_name",
                (project_id,),
            ).fetchall(),
        )
    policy_by_agent = {row["agent_name"]: row["policy_json"] for row in policies}
    tool_by_agent = {row["agent_name"]: row for row in tool_rows}
    incidents_by_agent = {row["agent_name"]: int(row["count"]) for row in incident_rows}
    for row in rows:
        policy_data = policy_by_agent.get(row["agent_name"])
        tool = tool_by_agent.get(row["agent_name"], {})
        tool_calls = int(tool.get("tool_calls", 0))
        successful_tools = int(tool.get("successful_tool_calls", 0))
        runs = int(row["runs"])
        completed = int(row["completed_runs"])
        open_for_agent = incidents_by_agent.get(row["agent_name"], 0)
        row["tool_calls"] = tool_calls
        row["failed_tool_calls"] = tool_calls - successful_tools
        row["completion_rate"] = completed / runs
        row["tool_success_rate"] = successful_tools / tool_calls if tool_calls else None
        total_cost = int(row["cost_nano_usd"])
        row["average_cost_nano_usd"] = round(total_cost / runs) if total_cost else None
        row["open_incidents"] = open_for_agent
        if policy_data:
            metrics = SloMetrics(
                samples=runs,
                completed_runs=completed,
                tool_calls=tool_calls,
                successful_tool_calls=successful_tools,
                p95_latency_ms=int(row["p95_latency_ms"]),
                total_cost_nano_usd=int(row["cost_nano_usd"]),
                maximum_steps=int(row["maximum_steps"]),
            )
            result = evaluate_slo_metrics(
                metrics, SloPolicy(**policy_data), incident_open=open_for_agent > 0
            )
            row["health"] = result.health.value
            row["breaches"] = result.breaches
        else:
            row["health"] = "incident" if open_for_agent else "no_policy"
            row["breaches"] = ()
    summary = summary_rows[0] if summary_rows else {}
    healthy_agents = sum(row["health"] == "healthy" for row in rows)
    return jsonable_encoder(
        {
            "window_hours": 24,
            "agents": rows,
            "open_incidents": sum(incidents_by_agent.values()),
            "summary": {
                "agent_count": len(rows),
                "healthy_agent_count": healthy_agents,
                "observed_run_count": int(summary.get("observed_run_count") or 0),
                "failed_run_count": int(summary.get("failed_run_count") or 0),
                "completion_rate": summary.get("completion_rate"),
                "p95_latency_ms": summary.get("p95_latency_ms"),
                "recorded_cost_nano_usd": (
                    int(summary["recorded_cost_nano_usd"])
                    if summary.get("recorded_cost_nano_usd")
                    else None
                ),
            },
        }
    )


@app.post("/api/projects/{project_id}/slos", status_code=201)
def upsert_slo(
    project_id: uuid.UUID,
    data: SloInput,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> dict[str, str]:
    with postgres(settings) as connection:
        connection.execute(
            "INSERT INTO slo_policies(id, project_id, agent_name, policy_json) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (project_id, agent_name) "
            "DO UPDATE SET policy_json = EXCLUDED.policy_json",
            (uuid.uuid4(), project_id, data.agent_name, json.dumps(asdict(data.policy))),
        )
    return {"status": "saved"}


@app.get("/api/projects/{project_id}/slos")
def slos(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> list[dict[str, Any]]:
    with postgres(settings) as connection:
        rows = connection.execute(
            "SELECT agent_name, policy_json FROM slo_policies "
            "WHERE project_id = %s ORDER BY agent_name",
            (project_id,),
        ).fetchall()
    return jsonable_encoder(rows)


@app.get("/api/projects/{project_id}/changes")
def changes(
    project_id: uuid.UUID,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> list[dict[str, Any]]:
    with postgres(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM change_events WHERE project_id = %s "
            "ORDER BY effective_at DESC LIMIT 200",
            (project_id,),
        ).fetchall()
    return jsonable_encoder(rows)


@app.post("/api/projects/{project_id}/changes", status_code=201)
def record_change(
    project_id: uuid.UUID,
    data: ChangeInput,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> dict[str, str]:
    event_id = uuid.uuid4()
    with postgres(settings) as connection:
        connection.execute(
            "INSERT INTO change_events(id, project_id, change_type, subject_type, subject_name, "
            "before_version, after_version, before_hash, after_hash, deployment_id, "
            "environment, effective_at, details) VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                event_id,
                project_id,
                data.change_type,
                data.subject_type,
                data.subject_name,
                data.before_version,
                data.after_version,
                data.before_hash,
                data.after_hash,
                data.deployment_id,
                data.environment,
                data.effective_at,
                json.dumps(data.details),
            ),
        )
    return {"id": str(event_id)}


@app.post("/api/projects/{project_id}/tool-schemas", status_code=201)
def record_tool_schema(
    project_id: uuid.UUID,
    data: ToolSchemaInput,
    _: str = Depends(_authorized_project),
    settings: Settings = Depends(_settings),
) -> dict[str, Any]:
    new_fingerprint = fingerprint(data.schema_data)
    with postgres(settings) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (advisory_lock_key("tool-schema", project_id, data.tool_name),),
        )
        previous = cast(
            dict[str, Any] | None,
            connection.execute(
                "SELECT version, fingerprint, schema_json FROM tool_schema_versions "
                "WHERE project_id = %s AND tool_name = %s ORDER BY created_at DESC LIMIT 1",
                (project_id, data.tool_name),
            ).fetchone(),
        )
        if previous and previous["fingerprint"] == new_fingerprint:
            return {"fingerprint": new_fingerprint, "change": "unchanged"}
        schema_id = uuid.uuid4()
        event_id = uuid.uuid4()
        difference = (
            compare_contracts(previous["schema_json"], data.schema_data) if previous else None
        )
        with connection.transaction():
            connection.execute(
                "INSERT INTO tool_schema_versions(id, project_id, tool_name, version, fingerprint, "
                "schema_json) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    schema_id,
                    project_id,
                    data.tool_name,
                    data.version,
                    new_fingerprint,
                    json.dumps(data.schema_data),
                ),
            )
            connection.execute(
                "INSERT INTO change_events(id, project_id, change_type, subject_type, "
                "subject_name, before_version, after_version, before_hash, after_hash, "
                "environment, effective_at, details) VALUES "
                "(%s, %s, 'tool_schema', 'tool', %s, %s, %s, %s, %s, %s, now(), %s)",
                (
                    event_id,
                    project_id,
                    data.tool_name,
                    previous["version"] if previous else None,
                    data.version,
                    previous["fingerprint"] if previous else None,
                    new_fingerprint,
                    data.environment,
                    json.dumps(asdict(difference)) if difference else "{}",
                ),
            )
    return jsonable_encoder(
        {"fingerprint": new_fingerprint, "change": asdict(difference) if difference else "initial"}
    )


from .workflows import router as workflow_router  # noqa: E402

app.include_router(workflow_router)
