"""Owner-session CSRF tokens and local login admission control."""

from controlsurface_server.auth import LoginRateLimiter, csrf_token


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
