"""Redaction of AI provider 4xx error bodies (finding H2).

Provider error bodies that echo a credential back to the client (e.g. a 401
"Invalid API key: sk-...") must never propagate verbatim to the CDaily client.
"""

from __future__ import annotations

import asyncio
import pytest

from cdaily.services import article_summary as summary_svc


class _FakeResponse:
    def __init__(self, text: str, status_code: int) -> None:
        self.text = text
        self.status_code = status_code


class _FakeClient:
    """AsyncClient stand-in whose post() returns a canned response."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, *args: object, **kwargs: object) -> _FakeResponse:
        return self._response


def test_ai_4xx_body_redacts_secret(monkeypatch):
    """A 401 that echoes the API key in its body must not leak it to the client."""
    secret_body = "Invalid API key: sk-test123"
    fake_client = _FakeClient(_FakeResponse(secret_body, 401))

    # Patch the AsyncClient class itself; the service calls AsyncClient(timeout=...) -> fake_client
    monkeypatch.setattr(summary_svc.httpx, "AsyncClient", lambda *a, **k: fake_client)

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            summary_svc._request_ai_completion(
                "http://localhost:12345/v1/chat/completions",
                {"model": "x", "messages": []},
                {"api_key": "", "auth_type": "none"},
            )
        )

    msg = str(exc.value)
    assert "sk-test123" not in msg, "API key leaked into the surfaced error"
    assert "[REDACTED]" in msg


def test_redact_error_body_masks_key():
    out = summary_svc._redact_error_body("Invalid API key: sk-test123")
    assert "sk-test123" not in out
    assert "[REDACTED]" in out


def test_redact_error_body_truncates_long_body():
    long_body = "x" * 500
    out = summary_svc._redact_error_body(long_body)
    assert len(out) <= summary_svc._ERROR_BODY_MAX_CHARS + len("... [truncated]")
    assert out.endswith("... [truncated]")


def test_redact_error_body_passes_benign_text():
    benign = "Model not found for the given endpoint."
    assert summary_svc._redact_error_body(benign) == benign
