"""OpenAI 兼容客户端：SSE 流式对话。

支持任意 OpenAI 兼容端点（DeepSeek / OpenAI / Ollama / vLLM / 通义…），
使用 httpx 直连 chat/completions，``stream=true`` 时逐块回调：

* ``on_content(text)`` —— 正文增量；
* ``on_reasoning(text)`` —— 思考过程增量（DeepSeek reasoning_content，其它端点通常没有）；
* ``on_tool_call(tool_index, tool_id, name, arguments_delta)`` —— 工具调用增量（M8）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import httpx


class AiProviderError(RuntimeError):
    """AI 端点错误（网络 / 鉴权 / 参数）。"""


@dataclass
class ChatMessage:
    role: str
    content: str = ""
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    default_model: str
    temperature: float = 0.2


def stream_chat(
    config: ProviderConfig,
    api_key: str,
    messages: list[ChatMessage],
    *,
    model: str | None = None,
    tools: list[dict] | None = None,
    on_content: Callable[[str], None] | None = None,
    on_reasoning: Callable[[str], None] | None = None,
    on_tool_call: Callable[[int, str, str, str], None] | None = None,
    timeout: float = 120.0,
) -> None:
    """发起一次流式对话；出错抛 AiProviderError。"""
    url = config.base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = url + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict = {
        "model": model or config.default_model,
        "messages": [_encode(message) for message in messages],
        "stream": True,
        "temperature": config.temperature,
    }
    if tools:
        payload["tools"] = tools

    try:
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=timeout) as response:
            if response.status_code != 200:
                body = response.read().decode("utf-8", "replace")
                raise AiProviderError(f"端点返回 {response.status_code}：{body[:400]}")
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    return
                _dispatch(data, on_content, on_reasoning, on_tool_call)
    except httpx.HTTPError as error:
        raise AiProviderError(f"无法连接 AI 端点：{error}") from error


def _encode(message: ChatMessage) -> dict:
    body: dict = {"role": message.role}
    if message.content:
        body["content"] = message.content
    if message.tool_calls:
        body["tool_calls"] = message.tool_calls
    if message.tool_call_id:
        body["tool_call_id"] = message.tool_call_id
    if message.role == "tool" and not message.content:
        body["content"] = ""
    return body


def _dispatch(data: str, on_content, on_reasoning, on_tool_call) -> None:
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return
    for choice in chunk.get("choices", []):
        delta = choice.get("delta") or {}
        reasoning = delta.get("reasoning_content")
        if reasoning and on_reasoning:
            on_reasoning(reasoning)
        content = delta.get("content")
        if content and on_content:
            on_content(content)
        for tool_call in delta.get("tool_calls") or []:
            index = tool_call.get("index", 0)
            identity = tool_call.get("id", "") or ""
            function = tool_call.get("function") or {}
            if on_tool_call:
                on_tool_call(index, identity, function.get("name", ""), function.get("arguments", ""))
