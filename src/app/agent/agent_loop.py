"""function calling 循环（M8 + 二期治理）。

与界面同一路径：工具执行走统一 ToolRegistry → unit_vm / project_io 纯函数。
写操作先经确认通道（内置面板 = builtin 通道），用户拒绝返回
``{"cancelled": true}`` 并立即终止本轮循环（防反复弹窗）。

治理（对齐 Quotor 已验证配置，见 app.agent.governance）：
预算软着陆、停滞检测、提前收尾抢救、空 content 重试、超长结果截断、
429/5xx 退避、硬保险丝。
"""

from __future__ import annotations

import json
import threading

from PySide6.QtCore import QObject, Signal

from app.agent import governance, tool_registry
from app.agent.confirm_policy import ask_confirm, make_preview
from app.services.ai.ai_provider import AiProviderError, ChatMessage, ProviderConfig, stream_chat


class AgentLoop(QObject):
    """一轮 AI 对话（可能包含多次工具调用）。"""

    content = Signal(str)
    reasoning = Signal(str)
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        context: dict | None = None,
        parent: QObject | None = None,
        session_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._context = context or {}
        self._session_id = session_id
        self._cancelled = threading.Event()
        self._registry = tool_registry.default_registry()

    # ------------------------------------------------------------------ 界面
    def cancel(self) -> None:
        self._cancelled.set()

    # ------------------------------------------------------------------ 执行
    def run(
        self,
        messages: list[ChatMessage],
        config: ProviderConfig,
        api_key: str,
        model: str | None,
    ) -> None:
        thread = threading.Thread(
            target=self._run, args=(messages, config, api_key, model), daemon=True
        )
        thread.start()

    def _run(
        self,
        messages: list[ChatMessage],
        config: ProviderConfig,
        api_key: str,
        model: str | None,
    ) -> None:
        conversation = list(messages)
        budget = governance.Budget()
        stagnation = governance.StagnationDetector()
        empty_retries = 0
        premature_nudges = 0
        try:
            for _iteration in range(governance.MAX_ITERATIONS):
                if self._cancelled.is_set():
                    self.finished.emit("（已停止）")
                    return
                budget.next_round()
                if budget.force_stop():
                    self.finished.emit("（本轮对话已达到预算上限，已停止。）")
                    return
                if budget.should_wrap_up():
                    conversation.append(ChatMessage(role="user", content=governance.WRAP_UP_PROMPT))

                text, reasoning_text, tool_buffers = self._round(
                    conversation, config, api_key, model
                )
                budget.consume(text)
                budget.consume(reasoning_text)
                if not tool_buffers:
                    fallback = (
                        governance.extract_tool_call(reasoning_text)
                        if not text.strip()
                        else None
                    )
                    if fallback is not None:
                        tool_buffers = {
                            0: {
                                "id": "call_fallback",
                                "name": fallback["name"],
                                "arguments": json.dumps(fallback["arguments"], ensure_ascii=False),
                            }
                        }
                    elif not text.strip() and empty_retries < governance.EMPTY_RETRY_LIMIT:
                        empty_retries += 1
                        conversation.append(
                            ChatMessage(role="user", content=governance.EMPTY_RETRY_PROMPT)
                        )
                        continue
                    elif (
                        governance.looks_premature_final(text)
                        and premature_nudges < governance.PREMATURE_MAX_NUDGES
                    ):
                        premature_nudges += 1
                        conversation.append(
                            ChatMessage(role="user", content=governance.PREMATURE_NUDGE_PROMPT)
                        )
                        continue
                    else:
                        self.finished.emit(text)
                        return

                tool_calls = [
                    {
                        "id": buffer["id"] or f"call_{index}",
                        "type": "function",
                        "function": {
                            "name": buffer["name"],
                            "arguments": buffer["arguments"] or "{}",
                        },
                    }
                    for index, buffer in sorted(tool_buffers.items())
                ]
                conversation.append(
                    ChatMessage(role="assistant", content=text or "", tool_calls=tool_calls)
                )
                nudge = False
                for index, buffer in sorted(tool_buffers.items()):
                    if self._cancelled.is_set():
                        self.finished.emit("（已停止）")
                        return
                    call_id = buffer["id"] or f"call_{index}"
                    name = buffer["name"]
                    arguments = buffer["arguments"] or "{}"
                    self.status.emit(f"调用工具 {name}…")
                    if self._registry.is_write(name):
                        approved = ask_confirm(self._preview(name, arguments))
                        if not approved:
                            conversation.append(
                                ChatMessage(
                                    role="tool",
                                    tool_call_id=call_id,
                                    content=json.dumps(
                                        {"cancelled": True, "message": "用户取消了操作"},
                                        ensure_ascii=False,
                                    ),
                                )
                            )
                            self.finished.emit("（用户取消了操作，已停止。）")
                            return
                    result = self._registry.execute(name, arguments)
                    if isinstance(result, dict) and result.get("cancelled"):
                        conversation.append(
                            ChatMessage(
                                role="tool",
                                tool_call_id=call_id,
                                content=json.dumps(result, ensure_ascii=False, default=str),
                            )
                        )
                        self.finished.emit("（用户取消了操作，已停止。）")
                        return
                    payload = json.dumps(result, ensure_ascii=False, default=str)
                    conversation.append(
                        ChatMessage(
                            role="tool",
                            tool_call_id=call_id,
                            content=governance.truncate_tool_result(payload),
                        )
                    )
                    if stagnation.observe(name, arguments):
                        nudge = True
                if nudge:
                    conversation.append(
                        ChatMessage(role="user", content=governance.REPEAT_NUDGE_PROMPT)
                    )
                empty_retries = 0
            self.finished.emit("（工具调用轮次达到上限，已停止。）")
        except AiProviderError as error:
            self.failed.emit(str(error))
        except Exception as error:  # 后台线程兜底
            self.failed.emit(f"{type(error).__name__}: {error}")

    # ------------------------------------------------------------------ 单轮流式
    def _round(
        self,
        conversation: list[ChatMessage],
        config: ProviderConfig,
        api_key: str,
        model: str | None,
    ) -> tuple[str, str, dict[int, dict]]:
        attempt = 0
        while True:
            content_chunks: list[str] = []
            reasoning_chunks: list[str] = []
            tool_buffers: dict[int, dict] = {}

            def on_content(text: str) -> None:
                content_chunks.append(text)
                self.content.emit(text)

            def on_reasoning(text: str) -> None:
                reasoning_chunks.append(text)
                self.reasoning.emit(text)

            def on_tool_call(index: int, tool_id: str, name: str, arguments: str) -> None:
                buffer = tool_buffers.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if tool_id:
                    buffer["id"] = tool_id
                if name:
                    buffer["name"] = name
                buffer["arguments"] += arguments

            try:
                stream_chat(
                    config,
                    api_key,
                    conversation,
                    model=model,
                    tools=self._registry.to_openai_tools(),
                    on_content=on_content,
                    on_reasoning=on_reasoning,
                    on_tool_call=on_tool_call,
                    session_id=self._session_id,
                )
                return "".join(content_chunks), "".join(reasoning_chunks), tool_buffers
            except AiProviderError as error:
                delay = governance.retry_delay(attempt, str(error))
                if delay is None:
                    raise
                self.status.emit(f"模型请求失败：{error}；{delay:g}s 后重试…")
                if self._cancelled.wait(delay):
                    raise
                attempt += 1

    # ------------------------------------------------------------------ 确认卡
    def _preview(self, name: str, arguments: str) -> dict:
        tool = self._registry.get(name)
        description = tool.description if tool is not None else name
        try:
            payload = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            payload = {}
        details: list[str] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(value, (dict, list)):
                    text = json.dumps(value, ensure_ascii=False)
                else:
                    text = str(value)
                details.append(f"{key} = {text}")
        return make_preview(
            action=description,
            target=name,
            summary="AI 请求执行写操作",
            details=details,
        )
