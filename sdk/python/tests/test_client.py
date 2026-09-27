import json

import pytest

from controlsurface.client import ControlSurface, _safe_attributes


def test_sdk_redacts_sensitive_keys_bearer_values_and_url_secrets() -> None:
    attributes = _safe_attributes(
        {
            "authorization": "Bearer top-secret",
            "url": "https://example.invalid/callback?token=top-secret&mode=safe",
            "tool.arguments": {
                "account": "safe",
                "password": "top-secret",
                "nested": ["Bearer another-secret"],
            },
        }
    )
    assert attributes["authorization"] == "[REDACTED]"
    assert "top-secret" not in str(attributes)
    assert "another-secret" not in str(attributes)
    assert "token=[REDACTED]" in attributes["url"]
    structured = json.loads(str(attributes["tool.arguments"]))
    assert structured["password"] == "[REDACTED]"
    assert structured["nested"] == ["Bearer [REDACTED]"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "localhost:4318",
        "ftp://localhost:4318",
        "http://",
        "http://user:password@localhost:4318",
        "http://localhost:4318?token=secret",
        "http://localhost:4318/#fragment",
    ],
)
def test_sdk_rejects_malformed_or_secret_bearing_endpoints(endpoint: str) -> None:
    with pytest.raises(ValueError, match=r"HTTP\(S\) URL"):
        ControlSurface.init(endpoint=endpoint, api_key="test-only-key")
