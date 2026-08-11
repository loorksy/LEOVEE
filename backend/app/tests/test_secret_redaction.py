from __future__ import annotations

from app.core.logging import redact_secrets


def test_redact_secrets_masks_token_shaped_strings() -> None:
    fake = "x" * 48
    payload = {
        "msg": f"OANDA_API_TOKEN={fake}",
        "auth": f"Bearer {fake}",
        "nested": {"key": f"sk-{'a' * 24}"},
    }
    out = redact_secrets(payload)
    assert fake not in str(out)
    assert "sk-" not in str(out) or "[REDACTED]" in str(out)
    assert out["msg"] == "[REDACTED]" or "[REDACTED]" in out["msg"]
    assert "[REDACTED]" in out["auth"]
    assert out["nested"]["key"] == "[REDACTED]"
