"""Shared authenticated API dependencies without route-module coupling."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from .auth import browser_user, csrf_token, project_for_api_key
from .settings import Settings, load_settings
from .storage import clickhouse, postgres


def advisory_lock_key(namespace: str, *values: object) -> int:
    """Return a stable signed bigint suitable for PostgreSQL advisory locks."""
    payload = ":".join((namespace, *(str(value) for value in values)))
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big", signed=True)


def settings_dependency() -> Settings:
    return load_settings()


def actor(
    request: Request, settings: Annotated[Settings, Depends(settings_dependency)]
) -> tuple[str, str]:
    token = request.cookies.get("cs_session")
    authorization = request.headers.get("authorization", "")
    with postgres(settings) as connection:
        if authorization.lower().startswith("bearer "):
            project_id = project_for_api_key(connection, authorization[7:].strip())
            if project_id:
                return "key", project_id
            raise HTTPException(401, "Authentication required")
        user_id = browser_user(connection, token)
        if user_id and token:
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                provided = request.headers.get("x-csrf-token", "")
                if not provided or not hmac.compare_digest(provided, csrf_token(token)):
                    raise HTTPException(403, "Invalid CSRF token")
            return "user", user_id
    raise HTTPException(401, "Authentication required")


def authorized_project(
    project_id: uuid.UUID,
    authenticated_actor: Annotated[tuple[str, str], Depends(actor)],
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> str:
    if authenticated_actor[0] == "key":
        if authenticated_actor[1] != str(project_id):
            raise HTTPException(404, "Project not found")
        return str(project_id)
    with postgres(settings) as connection:
        row = connection.execute(
            "SELECT 1 FROM projects WHERE id = %s AND owner_id = %s",
            (project_id, authenticated_actor[1]),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return str(project_id)


def query_clickhouse(
    settings: Settings, sql: str, parameters: dict[str, Any]
) -> list[dict[str, Any]]:
    client = clickhouse(settings)
    try:
        result = client.query(sql, parameters=parameters)
        return [dict(zip(result.column_names, row, strict=True)) for row in result.result_rows]
    finally:
        client.close()
