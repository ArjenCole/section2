"""右侧：AI 助手面板（计划 §8.2，M7 对话 + M8 工具调用）。

* SSE 流式输出，正文逐字上屏，思考过程（reasoning_content）单独折叠块；
* 未配置模型时显示引导提示而不是报错；
* 工具调用经 ConfirmBridge 在界面线程弹确认窗，执行后 EventBus 刷新工程量表。
"""

from __future__ import annotations

import html
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.agent.agent_loop import AgentLoop
from app.agent.tools.element_crud import ToolContext
from app.core.config import get_config
from app.core.event_bus import bus
from app.services.ai import ai_keychain
from app.services.ai.ai_provider import AiProviderError, ChatMessage, ProviderConfig

_SYSTEM_PROMPT = (
    "你是 section2（市政管道等线性工程工程量计算软件）的助手。"
    "当前工程数据可以通过工具 list_elements / add_element / update_element / delete_element 操作，"
    "涉及新增/修改/删除时必须先向用户复述将要做的改动。"
    "回答用简体中文，简明扼要；涉及工程量计算时引用界面上的计算表达式。"
)


class _InputEdit(QPlainTextEdit):
    """输入框：Ctrl+Enter 发送。"""

    submitted = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class AiPanel(QWidget):
    """AI 助手面板。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self.setMinimumWidth(240)
        self.setToolTip("AI 助手（Ctrl+L 折叠/展开）")
        self._history: list[ChatMessage] = []
        self._loop: AgentLoop | None = None
        self._blocks: list[dict] = []  # 渲染用的消息块
        self.unit_id: int | None = None  # 当前单位工程（AI 工具的作用范围）
        self.unit_name: str = ""
        self._build()
        self._refresh_hint()
        bus().project_opened.connect(lambda _path: self._refresh_hint())
        bus().project_closed.connect(self._refresh_hint)

    # ------------------------------------------------------------------ 界面
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("AI 助手")
        title.setProperty("role", "panel-title")
        header.addWidget(title)
        header.addStretch(1)
        self._status = QLabel("未配置")
        self._status.setProperty("role", "badge")
        header.addWidget(self._status)
        self._btn_settings = QPushButton("设置")
        self._btn_settings.setFlat(True)
        self._btn_settings.clicked.connect(self._open_settings)
        header.addWidget(self._btn_settings)
        layout.addLayout(header)

        self._transcript = QTextBrowser()
        self._transcript.setOpenExternalLinks(True)
        self._transcript.anchorClicked.connect(self._toggle_reasoning)
        layout.addWidget(self._transcript, 1)

        self._input = _InputEdit()
        self._input.setPlaceholderText("输入问题，Ctrl+Enter 发送（如：把雨水管的埋深改成 2.5m）")
        self._input.setFixedHeight(72)
        self._input.submitted.connect(self._send_message)
        layout.addWidget(self._input)

        row = QHBoxLayout()
        self._btn_stop = QPushButton("停止")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop)
        self._btn_clear = QPushButton("清空对话")
        self._btn_clear.setFlat(True)
        self._btn_clear.clicked.connect(self._clear)
        self._send = QPushButton("发送")
        self._send.setProperty("primary", "true")
        self._send.clicked.connect(self._send_message)
        row.addWidget(self._btn_stop)
        row.addWidget(self._btn_clear)
        row.addStretch(1)
        row.addWidget(self._send)
        layout.addLayout(row)

    # ------------------------------------------------------------------ 状态
    def refresh_theme(self) -> None:
        self._render()

    def _provider(self) -> ProviderConfig | None:
        config = get_config()
        name = config.ai_active_provider
        provider = config.ai_provider(name) if name else None
        if provider is None:
            providers = config.ai_providers
            provider = providers[0] if providers else None
        if provider is None:
            return None
        return ProviderConfig(
            name=provider.get("name", ""),
            base_url=provider.get("base_url", ""),
            default_model=provider.get("default_model", ""),
            temperature=float(provider.get("temperature", 0.2)),
        )

    def _refresh_hint(self) -> None:
        provider = self._provider()
        self._status.setText(provider.name if provider else "未配置")
        self._input.setEnabled(provider is not None)
        self._send.setEnabled(provider is not None)
        if provider is None:
            self._blocks = []
        self._render()

    def _open_settings(self) -> None:
        from app.views.dialogs.ai_settings_dialog import AiSettingsDialog

        dialog = AiSettingsDialog(self)
        if dialog.exec():
            self._refresh_hint()

    def _clear(self) -> None:
        self._history.clear()
        self._blocks = []
        self._render()

    # ------------------------------------------------------------------ 发送
    def _send_message(self) -> None:
        provider = self._provider()
        if provider is None or self._loop is not None:
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        api_key = ai_keychain.get_api_key(provider.name)
        self._input.clear()
        self._history.append(ChatMessage(role="user", content=text))
        system = ChatMessage(role="system", content=_SYSTEM_PROMPT)
        self._blocks.append({"role": "user", "text": text})
        self._blocks.append({"role": "assistant", "text": "", "reasoning": "", "tools": []})
        self._render()

        context = ToolContext(unit_id=self.unit_id, unit_name=self.unit_name)
        self._loop = AgentLoop(context)
        self._loop.content.connect(self._on_content)
        self._loop.reasoning.connect(self._on_reasoning)
        self._loop.status.connect(self._on_status)
        self._loop.finished.connect(self._on_finished)
        self._loop.failed.connect(self._on_failed)
        self._loop.confirm_requested.connect(self._on_confirm)
        self._send.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._loop.run([system, *self._history], provider, api_key, None)

    def _stop(self) -> None:
        if self._loop is not None:
            self._loop.cancel()

    def set_current_unit(self, unit_id: int | None, name: str = "") -> None:
        """主窗体在树选择变化时调用，让 AI 工具作用于当前单位工程。"""
        self.unit_id = unit_id
        self.unit_name = name

    # ------------------------------------------------------------------ 流式回调
    def _on_content(self, text: str) -> None:
        if self._blocks and self._blocks[-1]["role"] == "assistant":
            self._blocks[-1]["text"] += text
            self._render()

    def _on_reasoning(self, text: str) -> None:
        if self._blocks and self._blocks[-1]["role"] == "assistant":
            self._blocks[-1]["reasoning"] += text
            if len(self._blocks[-1]["reasoning"]) % 64 < len(text):
                self._render()

    def _on_status(self, text: str) -> None:
        if self._blocks and self._blocks[-1]["role"] == "assistant":
            self._blocks[-1].setdefault("tools", []).append(text)
            self._render()

    def _on_finished(self, text: str) -> None:
        self._history.append(ChatMessage(role="assistant", content=text))
        if self._blocks and self._blocks[-1]["role"] == "assistant":
            self._blocks[-1]["text"] = self._blocks[-1]["text"] or text
            self._blocks[-1]["done"] = True
        self._render()
        self._send.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._loop = None

    def _on_failed(self, message: str) -> None:
        if self._blocks and self._blocks[-1]["role"] == "assistant":
            self._blocks[-1]["error"] = message
        self._render()
        self._send.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._loop = None
        if isinstance(message, str) and "401" in message:
            QMessageBox.warning(self, "AI 端点", "鉴权失败，请检查 API key。")

    def _on_confirm(self, description: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("AI 写操作确认")
        box.setText(description)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText("允许执行")
        box.button(QMessageBox.StandardButton.No).setText("拒绝")
        box.setDefaultButton(QMessageBox.StandardButton.No)
        approved = box.exec() == QMessageBox.StandardButton.Yes
        if self._loop is not None:
            self._loop.answer_confirm(approved)
            if approved:
                bus().status_message.emit("AI 正在执行写操作…", 3000)

    # ------------------------------------------------------------------ 渲染
    def _toggle_reasoning(self, url) -> None:
        link = url.toString()
        if link.startswith("reason:"):
            index = int(link.split(":", 1)[1])
            if 0 <= index < len(self._blocks):
                self._blocks[index]["show_reasoning"] = not self._blocks[index].get("show_reasoning")
                self._render()

    def _render(self) -> None:
        if not self._blocks:
            hint_color = "#64748B"
            self._transcript.setHtml(
                f"<p style='color:{hint_color}'>"
                "在这里用自然语言维护当前单位工程的构件条目。<br><br>"
                "例如：<i>列出当前构件</i>、<i>把雨水管的埋深改成 2.5m</i>、"
                "<i>新增一条 Dn800 雨水管，长度 120 米</i>。<br><br>"
                "新增/修改/删除都会先弹出确认窗；计算表达式可以在中部工程量表里查看。"
                "</p>"
            )
            return
        parts: list[str] = []
        for index, block in enumerate(self._blocks):
            if block["role"] == "user":
                parts.append(
                    f"<div style='margin:6px 0 2px 0;color:#64748B'>我：</div>"
                    f"<div style='background:#EFF6FF;border-radius:6px;padding:6px 8px;'>"
                    f"{html.escape(block['text']).replace(chr(10), '<br>')}</div>"
                )
                continue
            text = html.escape(block.get("text", "")).replace("\n", "<br>")
            chunks = []
            reasoning = block.get("reasoning", "")
            if reasoning:
                shown = block.get("show_reasoning")
                if shown:
                    chunks.append(
                        f"<a href='reason:{index}'>▾ 收起思考过程</a><br>"
                        f"<div style='color:#94A3B8;border-left:2px solid #E5E7EB;"
                        f"margin:4px 0 4px 4px;padding-left:8px;'>"
                        f"{html.escape(reasoning).replace(chr(10), '<br>')}</div>"
                    )
                else:
                    chunks.append(f"<a href='reason:{index}'>▸ 思考过程（{len(reasoning)} 字）</a>")
            for tool in block.get("tools", []):
                chunks.append(f"<div style='color:#3B82F6'>⚙ {html.escape(tool)}</div>")
            if text:
                chunks.append(text)
            if not block.get("done") and block.get("text") == "" and not chunks:
                chunks.append("<span style='color:#94A3B8'>思考中…</span>")
            if block.get("error"):
                chunks.append(f"<div style='color:#EF4444'>{html.escape(block['error'])}</div>")
            parts.append(
                f"<div style='margin:6px 0 2px 0;color:#64748B'>AI：</div>"
                f"<div>{''.join(chunks)}</div>"
            )
        self._transcript.setHtml("".join(parts) or "")
        self._transcript.verticalScrollBar().setValue(self._transcript.verticalScrollBar().maximum())
