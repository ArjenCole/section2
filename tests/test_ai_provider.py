"""AI 客户端请求头单测（opencode Go 的 x-opencode-session / 客户端 UA）。"""

from __future__ import annotations

import httpx

from app.services.ai import ai_provider


class _FakeResponse:
    status_code = 200

    def iter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"hi"}}]}'
        yield "data: [DONE]"

    def read(self) -> bytes:
        return b""


class _FakeStream:
    def __init__(self, captured: dict, **kwargs) -> None:
        captured.update(kwargs)

    def __enter__(self):
        return _FakeResponse()

    def __exit__(self, *args):
        return False


def _capture(monkeypatch) -> dict:
    captured: dict = {}
    monkeypatch.setattr(
        httpx,
        "stream",
        lambda method, url, **kwargs: _FakeStream(captured, **kwargs),
    )
    return captured


def _chat(base_url: str, **kwargs) -> None:
    ai_provider.stream_chat(
        ai_provider.ProviderConfig(name="p", base_url=base_url, default_model="m"),
        "sk-test",
        [ai_provider.ChatMessage(role="user", content="hi")],
        **kwargs,
    )


def test_opencode_session_header_is_stable(monkeypatch) -> None:
    captured = _capture(monkeypatch)
    _chat("https://opencode.ai/inference/go/v1", session_id="stable-123")
    headers = captured["headers"]
    assert headers["x-opencode-session"] == "stable-123"
    assert headers["User-Agent"].startswith("section2/")
    assert headers["Authorization"] == "Bearer sk-test"


def test_opencode_session_header_generated_when_missing(monkeypatch) -> None:
    captured = _capture(monkeypatch)
    _chat("https://opencode.ai/inference/go/v1")
    assert captured["headers"]["x-opencode-session"]


def test_other_providers_do_not_get_opencode_header(monkeypatch) -> None:
    captured = _capture(monkeypatch)
    _chat("https://api.deepseek.com/v1", session_id="stable-123")
    assert "x-opencode-session" not in captured["headers"]
