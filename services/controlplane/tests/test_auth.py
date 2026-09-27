"""Owner-session CSRF tokens and local login admission control."""

from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argon2 import PasswordHasher

from controlsurface_server.auth import LoginRateLimiter, csrf_token, reset_owner_password


class RecoveryConnection:
    def __init__(self, email: str) -> None:
        self.owner_id = uuid4()
        self.email = email
        self.password_hash = PasswordHasher().hash("old-password-123")
        self.sessions = ["session-one", "session-two"]

    def transaction(self) -> nullcontext[None]:
        return nullcontext()

    def execute(self, query: str, params: tuple[object, ...] = ()) -> SimpleNamespace:
        if query.startswith("SELECT pg_advisory"):
            return SimpleNamespace()
        if query.startswith("SELECT id, email"):
            return SimpleNamespace(fetchall=lambda: [{"id": self.owner_id, "email": self.email}])
        if query.startswith("UPDATE users"):
            self.password_hash = str(params[0])
            assert params[1] == self.owner_id
            return SimpleNamespace()
        if query.startswith("DELETE FROM browser_sessions"):
            assert params == (self.owner_id,)
            self.sessions.clear()
            return SimpleNamespace()
        raise AssertionError(query)


def test_owner_recovery_changes_hash_and_revokes_sessions() -> None:
    connection = RecoveryConnection("owner@example.test")
    previous_hash = connection.password_hash
    reset_owner_password(connection, " OWNER@example.test ", "new-password-12345")  # type: ignore[arg-type]
    assert connection.password_hash != previous_hash
    assert PasswordHasher().verify(connection.password_hash, "new-password-12345")
    assert connection.sessions == []


def test_owner_recovery_refuses_wrong_email_or_weak_password() -> None:
    connection = RecoveryConnection("owner@example.test")
    previous_hash = connection.password_hash
    with pytest.raises(ValueError, match="configured owner"):
        reset_owner_password(connection, "wrong@example.test", "new-password-12345")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="12 characters"):
        reset_owner_password(connection, "owner@example.test", "short")  # type: ignore[arg-type]
    assert connection.password_hash == previous_hash
    assert len(connection.sessions) == 2


def test_csrf_token_is_deterministic_and_session_bound() -> None:
    first = csrf_token("opaque-session-secret-one")
    assert first == csrf_token("opaque-session-secret-one")
    assert first != csrf_token("opaque-session-secret-two")
    assert first != "opaque-session-secret-one"
    assert len(first) == 64


def test_login_limiter_is_per_client_and_recovers_after_window() -> None:
    current = [100.0]
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=5, clock=lambda: current[0])
    assert limiter.acquire("first") == 0
    assert limiter.acquire("first") == 0
    assert limiter.acquire("first") == 5
    assert limiter.acquire("second") == 0
    current[0] = 103.4
    assert limiter.acquire("first") == 2
    current[0] = 105.0
    assert limiter.acquire("first") == 0


def test_login_limiter_bounds_client_storage() -> None:
    current = [100.0]
    limiter = LoginRateLimiter(
        max_attempts=1, window_seconds=5, max_clients=1, clock=lambda: current[0]
    )
    assert limiter.acquire("first") == 0
    assert limiter.acquire("second") == 5
    current[0] = 105.0
    assert limiter.acquire("second") == 0
