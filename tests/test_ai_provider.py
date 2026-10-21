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


def test_reasoning_content_passed_back_for_assistant_only(monkeypatch) -> None:
    """思考模式：assistant 的 reasoning_content 必须随消息回传；其它角色不带。"""
    captured = _capture(monkeypatch)
    messages = [
        ai_provider.ChatMessage(role="system", content="system"),
        ai_provider.ChatMessage(role="user", content="user"),
        ai_provider.ChatMessage(
            role="assistant",
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "list_elements", "arguments": "{}"},
                }
            ],
            reasoning_content="先查一下构件列表",
        ),
        ai_provider.ChatMessage(
            role="tool", tool_call_id="call_1", content='{"ok": true}'
        ),
    ]
    ai_provider.stream_chat(
        ai_provider.ProviderConfig(
            name="p", base_url="https://example.com/v1", default_model="m"
        ),
        "sk-test",
        messages,
    )
    encoded = captured["json"]["messages"]
    assert encoded[2]["reasoning_content"] == "先查一下构件列表"
    assert "reasoning_content" not in encoded[0]
    assert "reasoning_content" not in encoded[1]
    assert "reasoning_content" not in encoded[3]


def test_reasoning_content_can_be_disabled_per_provider(monkeypatch) -> None:
    """官方 DeepSeek 等不需要回传的端点可关闭该字段。"""
    captured = _capture(monkeypatch)
    messages = [
        ai_provider.ChatMessage(
            role="assistant", content="ok", reasoning_content="思考内容"
        )
    ]
    ai_provider.stream_chat(
        ai_provider.ProviderConfig(
            name="p",
            base_url="https://api.deepseek.com/v1",
            default_model="m",
            send_reasoning_content=False,
        ),
        "sk-test",
        messages,
    )
    assert "reasoning_content" not in captured["json"]["messages"][0]


def test_default_send_reasoning_content_by_endpoint() -> None:
    assert not ai_provider.default_send_reasoning_content(
        "https://api.deepseek.com/v1"
    )
    assert ai_provider.default_send_reasoning_content(
        "https://opencode.ai/zen/go/v1"
    )
