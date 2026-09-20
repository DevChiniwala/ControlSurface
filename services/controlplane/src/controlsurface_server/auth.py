"""Project API keys and owner browser sessions."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher

from .storage import DbConnection

_passwords = PasswordHasher()


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def csrf_token(session_token: str) -> str:
    """Bind a browser mutation token to its unguessable HttpOnly session secret."""
    return hmac.new(
        session_token.encode("utf-8"), b"controlsurface-csrf-v1", hashlib.sha256
    ).hexdigest()


def create_owner(
    connection: DbConnection, email: str, password: str, project_name: str
) -> tuple[str, str]:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(75972419)")
        if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            raise ValueError("Owner is already configured")
        user_id, project_id = uuid.uuid4(), uuid.uuid4()
        slug = "default"
        connection.execute(
            "INSERT INTO users(id, email, password_hash) VALUES (%s, %s, %s)",
            (user_id, email.lower().strip(), _passwords.hash(password)),
        )
        connection.execute(
            "INSERT INTO projects(id, name, slug, owner_id) VALUES (%s, %s, %s, %s)",
            (project_id, project_name.strip(), slug, user_id),
        )
    return str(user_id), str(project_id)


def verify_password(connection: DbConnection, email: str, password: str) -> str | None:
    row = connection.execute(
        "SELECT id, password_hash FROM users WHERE email = %s", (email.lower().strip(),)
    ).fetchone()
    if not row:
        return None
    try:
        _passwords.verify(row["password_hash"], password)
    except Exception:
        return None
    return str(row["id"])


def create_browser_session(connection: DbConnection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO browser_sessions(token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (_digest(token), user_id, datetime.now(UTC) + timedelta(days=7)),
    )
    return token


def browser_user(connection: DbConnection, token: str | None) -> str | None:
    if not token:
        return None
    row = connection.execute(
        "SELECT user_id FROM browser_sessions WHERE token_hash = %s AND expires_at > now()",
        (_digest(token),),
    ).fetchone()
    return str(row["user_id"]) if row else None


def create_api_key(connection: DbConnection, project_id: str, label: str) -> tuple[str, str]:
    key_id = str(uuid.uuid4())
    raw = "cs_live_" + secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO api_keys(id, project_id, prefix, key_hash, label) VALUES (%s, %s, %s, %s, %s)",
        (key_id, project_id, raw[:16], _digest(raw), label.strip()),
    )
    return key_id, raw


def project_for_api_key(connection: DbConnection, raw: str | None) -> str | None:
    if not raw or not raw.startswith("cs_live_"):
        return None
    row = connection.execute(
        "SELECT project_id, key_hash FROM api_keys WHERE key_hash = %s AND revoked_at IS NULL",
        (_digest(raw),),
    ).fetchone()
    if not row or not hmac.compare_digest(row["key_hash"], _digest(raw)):
        return None
    return str(row["project_id"])
