"""Project API keys and owner browser sessions."""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import uuid
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .storage import DbConnection

_passwords = PasswordHasher()
_DUMMY_PASSWORD_HASH = _passwords.hash("controlsurface-login-timing-placeholder")


class LoginRateLimiter:
    """Bounded, process-local login admission control for the single-owner deployment."""

    def __init__(
        self,
        max_attempts: int = 20,
        window_seconds: float = 300,
        max_clients: int = 2048,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_attempts < 1 or window_seconds <= 0 or max_clients < 1:
            raise ValueError("Login rate limits must be positive")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self.clock = clock
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def acquire(self, client: str) -> int:
        """Record an attempt; return zero or the whole seconds to retry."""
        now = self.clock()
        cutoff = now - self.window_seconds
        with self._lock:
            attempts = self._attempts.get(client)
            if attempts is None:
                if len(self._attempts) >= self.max_clients:
                    for name, previous in list(self._attempts.items()):
                        while previous and previous[0] <= cutoff:
                            previous.popleft()
                        if not previous:
                            del self._attempts[name]
                if len(self._attempts) >= self.max_clients:
                    return math.ceil(self.window_seconds)
                attempts = deque()
                self._attempts[client] = attempts
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.max_attempts:
                return max(1, math.ceil(attempts[0] + self.window_seconds - now))
            attempts.append(now)
            return 0


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
    encoded = row["password_hash"] if row else _DUMMY_PASSWORD_HASH
    try:
        _passwords.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return None
    if not row:
        return None
    if _passwords.check_needs_rehash(encoded):
        connection.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (_passwords.hash(password), row["id"]),
        )
    return str(row["id"])


def reset_owner_password(connection: DbConnection, email: str, new_password: str) -> None:
    """Offline owner recovery; revoke browser sessions, retain project API keys."""
    if len(new_password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    normalized = email.lower().strip()
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(75972419)")
        owners = connection.execute("SELECT id, email FROM users LIMIT 2").fetchall()
        if len(owners) != 1 or owners[0]["email"] != normalized:
            raise ValueError("Exactly one configured owner must match the supplied email")
        owner_id = owners[0]["id"]
        connection.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (_passwords.hash(new_password), owner_id),
        )
        connection.execute("DELETE FROM browser_sessions WHERE user_id = %s", (owner_id,))


def create_browser_session(connection: DbConnection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    connection.execute("DELETE FROM browser_sessions WHERE expires_at <= now()")
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
