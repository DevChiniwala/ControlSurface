"""Browser mutation tokens are scoped to the current owner session."""

from controlsurface_server.auth import csrf_token


def test_csrf_token_is_deterministic_and_session_bound() -> None:
    first = csrf_token("opaque-session-secret-one")
    assert first == csrf_token("opaque-session-secret-one")
    assert first != csrf_token("opaque-session-secret-two")
    assert first != "opaque-session-secret-one"
    assert len(first) == 64
