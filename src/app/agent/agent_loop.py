"""function calling 循环（计划 §3 agent/agent_loop.py，M8）。

在后台线程里跑 OpenAI 兼容的流式对话；模型请求工具调用时：
写操作先经 ConfirmBridge 弹确认（界面线程），执行结果回填后继续下一轮，
直到模型给出最终回答或达到轮次上限。
"""

from __future__ import annotations

import json
import threading

from PySide6.QtCore import QObject, Qt, Signal

from app.agent import tool_registry
from app.agent.confirm_policy import ConfirmBridge
from app.agent.tools.element_crud import ToolContext
from app.services.ai.ai_provider import AiProviderError, ChatMessage, ProviderConfig, stream_chat

MAX_TOOL_ROUNDS = 8


class AgentLoop(QObject):
    """一轮 AI 对话（可能包含多次工具调用）。"""

    content = Signal(str)  # 正文增量
    reasoning = Signal(str)  # 思考过程增量
    status = Signal(str)  # 状态行（调用工具 xx…）
    finished = Signal(str)  # 最终回答
    failed = Signal(str)
    confirm_requested = Signal(str)  # 写操作确认（转发到界面线程弹窗）

    def __init__(self, context: ToolContext, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._context = context
        self._cancelled = threading.Event()
        self._bridge = ConfirmBridge(self)
        self._bridge.request.connect(self.confirm_requested)

    # ------------------------------------------------------------------ 界面
    def cancel(self) -> None:
        self._cancelled.set()

    def answer_confirm(self, approved: bool) -> None:
        self._bridge.answer(approved)

    # ------------------------------------------------------------------ 执行
    def run(self, messages: list[ChatMessage], config: ProviderConfig, api_key: str,
            model: str | None) -> None:
        thread = threading.Thread(
            target=self._run, args=(messages, config, api_key, model), daemon=True
        )
        thread.start()

    def _run(self, messages: list[ChatMessage], config: ProviderConfig, api_key: str,
             model: str | None) -> None:
        conversation = list(messages)
        try:
            for _round in range(MAX_TOOL_ROUNDS):
                if self._cancelled.is_set():
                    self.finished.emit("（已停止）")
                    return
                content_chunks: list[str] = []
                tool_buffers: dict[int, dict] = {}

                def on_content(text: str) -> None:
                    content_chunks.append(text)
                    self.content.emit(text)

                def on_tool_call(index: int, tool_id: str, name: str, arguments: str) -> None:
                    buffer = tool_buffers.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    if tool_id:
                        buffer["id"] = tool_id
                    if name:
                        buffer["name"] = name
                    buffer["arguments"] += arguments

                stream_chat(
                    config, api_key, conversation,
                    model=model,
                    tools=tool_registry.openai_tools(),
                    on_content=on_content,
                    on_reasoning=self.reasoning.emit,
                    on_tool_call=on_tool_call,
                )
                text = "".join(content_chunks)
                if not tool_buffers:
                    self.finished.emit(text)
                    return

                tool_calls = [
                    {
                        "id": buffer["id"] or f"call_{index}",
                        "type": "function",
                        "function": {"name": buffer["name"], "arguments": buffer["arguments"] or "{}"},
                    }
                    for index, buffer in sorted(tool_buffers.items())
                ]
                conversation.append(
                    ChatMessage(role="assistant", content=text or "", tool_calls=tool_calls)
                )
                for index, buffer in sorted(tool_buffers.items()):
                    call_id = buffer["id"] or f"call_{index}"
                    name = buffer["name"]
                    arguments = buffer["arguments"] or "{}"
                    self.status.emit(f"调用工具 {name}…")
                    if tool_registry.is_write(name):
                        if not self._bridge.ask(self._describe(name, arguments)):
                            conversation.append(
                                ChatMessage(role="tool", tool_call_id=call_id,
                                            content="用户拒绝执行该操作。")
                            )
                            continue
                    result = tool_registry.execute(name, arguments, self._context)
                    conversation.append(
                        ChatMessage(role="tool", tool_call_id=call_id, content=result)
                    )
            self.finished.emit("（工具调用轮次达到上限，已停止。）")
        except AiProviderError as error:
            self.failed.emit(str(error))
        except Exception as error:  # 后台线程兜底
            self.failed.emit(f"{type(error).__name__}: {error}")

    @staticmethod
    def _describe(name: str, arguments: str) -> str:
        try:
            payload = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            payload = {}
        actions = {
            "add_element": "新增构件条目",
            "update_element": "修改构件条目",
            "delete_element": "删除构件条目",
        }
        action = actions.get(name, name)
        details = "，".join(f"{key}={value}" for key, value in payload.items() if value not in (None, ""))
        return f"AI 请求{action}\n{details}\n\n允许执行吗？"
