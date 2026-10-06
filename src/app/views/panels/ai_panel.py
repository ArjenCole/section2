"""右侧：AI 助手面板（复刻 Quotor views/panels/ai_panel.py，M7 对话 + M8 工具调用）。

结构与交互照抄 Quotor：

* 消息区 = QScrollArea + 容器布局，每条消息一个独立控件：
  - :class:`_MessageBubble` —— 角色标签（用户=主色 / AI 助手=success / 错误=danger）
    + :class:`_MarkdownView`（高度随文档自适应；AI 用 Markdown，用户/错误转义 <pre>）；
  - :class:`_ThinkingBlock` —— 可折叠思考块，"思考中…" 400ms 动画，工具调用与
    流式正文就地刷新；
* 输入区 = QPlainTextEdit#aiInputEdit（圆角、右下角 overlay 发送按钮 #aiSendBtn），
  Enter 发送、Shift/Ctrl+Enter 换行；
* 顶部：标题 + 「清空」（兼停止，运行中点击即中断）+ 齿轮「设置」。

agent 层沿用本项目的 AgentLoop（content/reasoning/status/finished/failed/confirm 信号）。
"""

from __future__ import annotations

import html

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.agent.agent_loop import AgentLoop
from app.agent.tools.element_crud import ToolContext
from app.core.config import get_config
from app.core.event_bus import bus
from app.resources.qss.theme import ThemeManager
from app.services.ai import ai_keychain
from app.services.ai.ai_provider import ChatMessage, ProviderConfig
from app.views.widgets.frameless_dialog import FramelessMessageBox, load_icon

_SYSTEM_PROMPT = (
    "你是 section2（市政管道等线性工程工程量计算软件）的助手。"
    "当前工程数据可以通过工具 list_elements / add_element / update_element / delete_element 操作，"
    "涉及新增/修改/删除时必须先向用户复述将要做的改动。"
    "回答用简体中文，简明扼要；涉及工程量计算时引用界面上的计算表达式。"
)


def _c():
    return ThemeManager.instance().current()


class _MarkdownView(QTextBrowser):
    """高度随文档内容自动撑开的 Markdown 视图（Quotor 同款技巧）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        # 必须控件级清零：主题 QSS 对输入类控件设了 padding，否则视口比文档矮 → 内容截断
        self.setStyleSheet(
            "QTextBrowser { background: transparent; border: none; padding: 0px; margin: 0px; }"
        )
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.document().documentLayout().documentSizeChanged.connect(self._apply_height)

    def _apply_height(self, size) -> None:
        height = int(size.height()) + 4  # 余量防下伸部被裁
        if self.minimumHeight() != height or self.maximumHeight() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        # 宽度变化 → 延迟一拍重算换行高度
        QTimer.singleShot(0, lambda: self._apply_height(self.document().size()))


class _MessageBubble(QWidget):
    """一条消息：角色标签 + 内容（AI 用 Markdown，用户/错误转义纯文本）。"""

    def __init__(self, role: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._role = role
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 4)
        layout.setSpacing(4)

        self._role_label = QLabel()
        self._role_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._role_label)

        self._content_view = _MarkdownView()
        layout.addWidget(self._content_view)

        self._raw_text = ""
        self._refresh_role_label()
        self.set_text(text)

    def _refresh_role_label(self) -> None:
        colors = _c()
        if self._role == "user":
            label, color = "用户", colors.primary
        elif self._role == "error":
            label, color = "错误", colors.danger
        else:
            label, color = "AI 助手", colors.success
        self._role_label.setText(
            f'<span style="color:{color};font-weight:600;">{label}</span>'
        )

    def set_text(self, text: str) -> None:
        self._raw_text = text
        if self._role == "ai":
            self._content_view.setMarkdown(text)
        else:
            self._content_view.setHtml(
                '<pre style="margin:0;font-family:inherit;white-space:pre-wrap;">'
                f"{html.escape(text)}</pre>"
            )

    def refresh_theme(self) -> None:
        self._refresh_role_label()


class _ThinkingBlock(QWidget):
    """可折叠思考块：同一轮对话的思考/工具调用/流式正文累积在同一块里。"""

    def __init__(self, title: str = "思考过程", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stream_label: QLabel | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        colors = _c()
        self._toggle = QToolButton()
        self._toggle.setText(title)
        self._toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setStyleSheet(
            "QToolButton { border: none; background: transparent; text-align: left;"
            f" color: {colors.text_secondary}; font-weight: 600; padding: 2px; }}\n"
            "QToolButton:hover { background: transparent; }"
        )
        self._toggle.toggled.connect(self._on_toggle)
        layout.addWidget(self._toggle)

        self._content = QFrame()
        self._content.setStyleSheet(
            f"QFrame {{ border: none; border-left: 2px solid {colors.border};"
            " margin-left: 8px; }"
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 0, 0, 0)
        self._content_layout.setSpacing(2)
        self._content.setVisible(False)
        layout.addWidget(self._content)

        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(400)
        self._thinking_timer.timeout.connect(self._on_thinking_tick)
        self._thinking_dots = 0
        self._status_label: QLabel | None = None

    def _on_toggle(self, checked: bool) -> None:
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self._content.setVisible(checked)

    def _ensure_status_label(self) -> QLabel:
        if self._status_label is None:
            self._status_label = QLabel()
            self._status_label.setWordWrap(True)
            self._status_label.setTextFormat(Qt.TextFormat.RichText)
            self._content_layout.addWidget(self._status_label)
        return self._status_label

    def start_thinking(self) -> None:
        self._thinking_dots = 0
        self._thinking_timer.start()
        self._ensure_status_label().setText(self._thinking_text())

    def stop_thinking(self) -> None:
        self._thinking_timer.stop()
        if self._status_label is not None:
            self._status_label.setText(
                f'<span style="color:{_c().text_secondary};font-weight:600;">思考完成</span>'
            )

    def _thinking_text(self) -> str:
        dots = "." * (self._thinking_dots + 1)
        return f'<span style="color:{_c().text_secondary};">思考中{dots}</span>'

    def _on_thinking_tick(self) -> None:
        self._thinking_dots = (self._thinking_dots + 1) % 3
        if self._status_label is not None:
            self._status_label.setText(self._thinking_text())

    def set_stream_text(self, text: str) -> None:
        """流式正文就地刷新（Quotor 同款：反复 setText 同一个 QLabel）。"""
        if self._stream_label is None:
            self._stream_label = QLabel()
            self._stream_label.setWordWrap(True)
            self._stream_label.setTextFormat(Qt.TextFormat.PlainText)
            self._stream_label.setStyleSheet(f"color: {_c().text_primary};")
            self._content_layout.addWidget(self._stream_label)
        self._stream_label.setText(text)

    def rotate_stream_label(self) -> None:
        """换轮/重试时丢弃旧流式标签，下次 set_stream_text 重建。"""
        self._stream_label = None

    def append_html(self, rich_text: str) -> None:
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setText(rich_text)
        self._content_layout.addWidget(label)


class _InputEdit(QPlainTextEdit):
    """输入框：Enter 发送，Shift/Ctrl+Enter 换行（Quotor 同款）。"""

    submitted = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
                self.insertPlainText("\n")
                return
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class AiPanel(QWidget):
    """AI 助手面板。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTip("AI 助手（Ctrl+L 折叠/展开）")
        self._history: list[ChatMessage] = []
        self._loop: AgentLoop | None = None
        self._thinking_block: _ThinkingBlock | None = None
        self._bubbles: list[_MessageBubble] = []
        self.unit_id: int | None = None  # 当前单位工程（AI 工具的作用范围）
        self.unit_name: str = ""
        self._stream_text = ""  # 当前流式正文累计
        self._build()
        self._connect()
        self._refresh_hint()

    # ------------------------------------------------------------------ 界面
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(2)
        title = QLabel("AI 助手")
        title.setProperty("role", "title")
        header.addWidget(title)
        header.addStretch(1)
        self._btn_clear = QPushButton("清空")
        self._btn_clear.setProperty("secondary", "true")
        self._btn_clear.clicked.connect(self._clear)
        header.addWidget(self._btn_clear)
        self._btn_settings = QPushButton()
        self._btn_settings.setIcon(
            load_icon("settings", color=_c().text_primary, size=16)
        )
        self._btn_settings.setFixedSize(32, 32)
        self._btn_settings.clicked.connect(self._open_settings)
        header.addWidget(self._btn_settings)
        layout.addLayout(header)

        # 对话历史：每条消息一个独立控件，从顶部堆叠
        self._history_scroll = QScrollArea()
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._history_container = QWidget()
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(4, 4, 4, 4)
        self._history_layout.setSpacing(2)
        self._history_layout.addStretch(1)  # stretch 固定在末尾
        self._history_scroll.setWidget(self._history_container)
        layout.addWidget(self._history_scroll, 1)

        # 输入区：圆角输入框 + 右下角 overlay 发送按钮
        self._input = _InputEdit()
        self._input.setObjectName("aiInputEdit")
        self._input.setPlaceholderText("输入问题... (Enter 发送, Shift+Enter 换行)")
        self._input.setMaximumHeight(108)
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.setViewportMargins(0, 0, 40, 0)  # 右侧留给发送按钮
        self._input.submitted.connect(self._send_message)
        layout.addWidget(self._input)

        self._send_btn = QPushButton()
        self._send_btn.setObjectName("aiSendBtn")
        self._send_btn.setProperty("primary", True)
        self._send_btn.setIcon(self._make_send_arrow_icon())
        self._send_btn.setFixedSize(30, 30)
        self._send_btn.setParent(self._input)
        self._send_btn.raise_()
        self._send_btn.clicked.connect(self._send_message)
        self._input.installEventFilter(self)

    def _connect(self) -> None:
        bus().project_opened.connect(lambda _path: self._refresh_hint())
        bus().project_closed.connect(self._refresh_hint)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ 事件
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        if obj is self._input and event.type() == QEvent.Type.Resize:
            self._reposition_send_btn()
        return super().eventFilter(obj, event)

    def _reposition_send_btn(self) -> None:
        rect = self._input.rect()
        margin = 6
        self._send_btn.move(
            rect.right() - self._send_btn.width() - margin,
            rect.bottom() - self._send_btn.height() - margin,
        )
        self._send_btn.raise_()

    @staticmethod
    def _make_send_arrow_icon():
        """发送箭头：白色圆头上箭头（Quotor _make_send_arrow_icon 同款）。"""
        size = 32
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("white"), 2.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(9, 19, 16, 11)
        painter.drawLine(16, 11, 23, 19)
        painter.drawLine(16, 12, 16, 23)
        painter.end()
        from PySide6.QtGui import QIcon

        return QIcon(pixmap)

    # ------------------------------------------------------------------ 状态
    def refresh_theme(self) -> None:
        self._on_theme_changed()

    def _on_theme_changed(self) -> None:
        self._btn_settings.setIcon(load_icon("settings", color=_c().text_primary, size=16))
        for bubble in self._bubbles:
            bubble.refresh_theme()

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
        self._input.setEnabled(provider is not None)
        self._send_btn.setEnabled(provider is not None)
        if provider is None:
            self._input.setPlaceholderText("尚未配置 AI 模型，请点击右上角齿轮进行配置。")

    def _open_settings(self) -> None:
        from app.views.dialogs.ai_settings_dialog import AiSettingsDialog

        dialog = AiSettingsDialog(self)
        if dialog.exec():
            self._refresh_hint()

    def set_current_unit(self, unit_id: int | None, name: str = "") -> None:
        """主窗体在树选择变化时调用，让 AI 工具作用于当前单位工程。"""
        self.unit_id = unit_id
        self.unit_name = name

    # ------------------------------------------------------------------ 消息区
    def _insert_widget(self, widget: QWidget) -> None:
        self._history_layout.insertWidget(self._history_layout.count() - 1, widget)
        self._scroll_to_bottom()

    def _append_message(self, role: str, text: str) -> None:
        bubble = _MessageBubble(role, text)
        self._bubbles.append(bubble)
        self._insert_widget(bubble)

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, self._do_scroll)

    def _do_scroll(self) -> None:
        bar = self._history_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _clear(self) -> None:
        if self._loop is not None:
            self._loop.cancel()
        while self._history_layout.count() > 1:  # 保留末尾 stretch
            item = self._history_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._history.clear()
        self._bubbles.clear()
        self._thinking_block = None
        self._send_btn.setEnabled(self._provider() is not None)

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
        self._append_message("user", text)

        context = ToolContext(unit_id=self.unit_id, unit_name=self.unit_name)
        self._loop = AgentLoop(context)
        self._loop.content.connect(self._on_content)
        self._loop.reasoning.connect(self._on_reasoning)
        self._loop.status.connect(self._on_status)
        self._loop.finished.connect(self._on_finished)
        self._loop.failed.connect(self._on_failed)
        self._loop.confirm_requested.connect(self._on_confirm)
        self._send_btn.setEnabled(False)

        # 预创建思考块并立即启动"思考中"动画（Quotor 同款，消除启动空白期）
        self._thinking_block = _ThinkingBlock("思考过程")
        self._insert_widget(self._thinking_block)
        self._thinking_block.start_thinking()

        self._loop.run([system, *self._history], provider, api_key, None)

    # ------------------------------------------------------------------ 流式回调
    def _on_content(self, text: str) -> None:
        """流式正文：在思考块里就地刷新（Quotor stream 同款）。"""
        if self._thinking_block is not None:
            self._stream_text += text
            self._thinking_block.set_stream_text(self._stream_text)
            self._scroll_to_bottom()

    def _on_reasoning(self, text: str) -> None:
        if self._thinking_block is not None:
            self._thinking_block.set_stream_text("（思考）" + text[-400:])
            self._scroll_to_bottom()

    def _on_status(self, text: str) -> None:
        """工具调用：🔧 行 + 换轮时重置流式标签。"""
        if self._thinking_block is None:
            return
        self._stream_text = ""
        self._thinking_block.rotate_stream_label()
        self._thinking_block.append_html(
            f'<p style="color:{_c().warning};font-weight:600;margin:0;">'
            f"🔧 {html.escape(text)}</p>"
        )
        self._scroll_to_bottom()

    def _on_finished(self, text: str) -> None:
        if self._thinking_block is not None:
            self._thinking_block.stop_thinking()
        answer = text or self._stream_text
        self._stream_text = ""
        self._append_message("ai", answer)
        self._history.append(ChatMessage(role="assistant", content=answer))
        self._thinking_block = None
        self._send_btn.setEnabled(self._provider() is not None)
        self._loop = None
        self._scroll_to_bottom()

    def _on_failed(self, message: str) -> None:
        if self._thinking_block is not None:
            self._thinking_block.stop_thinking()
            self._thinking_block.append_html(
                f'<p style="color:{_c().danger};font-weight:600;">'
                f"[错误] {html.escape(str(message))}</p>"
            )
        self._stream_text = ""
        self._append_message("error", str(message))
        self._thinking_block = None
        self._send_btn.setEnabled(self._provider() is not None)
        self._loop = None
        self._scroll_to_bottom()
        if isinstance(message, str) and "401" in message:
            FramelessMessageBox.warning(self, "AI 端点", "鉴权失败，请检查 API key。")

    def _on_confirm(self, description: str) -> None:
        # 「AI 执行操作前需人工确认」关闭时自动放行（AI 设置里即改即存）
        if not get_config().ai_require_confirmation:
            bus().status_message.emit("AI 写操作已自动执行（已关闭人工确认）", 3000)
            if self._loop is not None:
                self._loop.answer_confirm(True)
            return
        approved = (
            FramelessMessageBox.question(
                self,
                "AI 写操作确认",
                description,
                FramelessMessageBox.StandardButton.Yes | FramelessMessageBox.StandardButton.No,
                FramelessMessageBox.StandardButton.No,
                button_texts={
                    FramelessMessageBox.StandardButton.Yes: "允许执行",
                    FramelessMessageBox.StandardButton.No: "拒绝",
                },
            )
            == FramelessMessageBox.StandardButton.Yes
        )
        if self._loop is not None:
            self._loop.answer_confirm(approved)
            if approved:
                bus().status_message.emit("AI 正在执行写操作…", 3000)
