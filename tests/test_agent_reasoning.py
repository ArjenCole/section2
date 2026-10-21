"""思考模式工具调用：assistant 的 reasoning_content 必须随下一轮请求回传。"""

from __future__ import annotations

import json

from app.agent import agent_loop as agent_loop_module
from app.agent.agent_loop import AgentLoop
from app.services.ai.ai_provider import ChatMessage, ProviderConfig


def test_agent_loop_passes_reasoning_content_back(monkeypatch) -> None:
    calls: list[list[ChatMessage]] = []

    def fake_stream(_config, _api_key, messages, **kwargs) -> None:
        calls.append(list(messages))
        if len(calls) == 1:
            kwargs["on_reasoning"]("先查一下表达式")
            kwargs["on_tool_call"](
                0,
                "call_1",
                "evaluate_expression",
                json.dumps({"expression": "1+2"}),
            )
        else:
            kwargs["on_content"]("计算结果是 3。")

    monkeypatch.setattr(agent_loop_module, "stream_chat", fake_stream)

    loop = AgentLoop()
    finished: list[str] = []
    loop.finished.connect(finished.append)
    loop._run(
        [ChatMessage(role="user", content="帮我算 1+2")],
        ProviderConfig(name="p", base_url="https://example.com/v1", default_model="m"),
        "",
        None,
    )

    assert finished == ["计算结果是 3。"]
    assert len(calls) == 2

    # 第二次请求：user → assistant(tool_calls) → tool
    assistant = calls[1][1]
    assert assistant.role == "assistant"
    assert assistant.reasoning_content == "先查一下表达式"
    assert assistant.tool_calls[0]["function"]["name"] == "evaluate_expression"
