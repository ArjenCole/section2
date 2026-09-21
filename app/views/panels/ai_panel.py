"""右侧：AI 助手面板（计划 §7.1、§8.2，宽 360px，可折叠 Ctrl+L）。

对话、SSE 流式、工具调用分别在 M7 / M8 实现；未配置模型时给引导提示而不是报错。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.config import get_config
from app.core.event_bus import bus
from app.resources.qss.theme import ThemeManager


class AiPanel(QWidget):
    """AI 助手面板（M7/M8 填充对话与工具调用）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
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
        layout.addLayout(header)

        self._transcript = QTextBrowser()
        self._transcript.setOpenExternalLinks(True)
        layout.addWidget(self._transcript, 1)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("AI 对话将在 M7 实现…")
        self._input.setFixedHeight(72)
        layout.addWidget(self._input)

        self._send = QPushButton("发送")
        self._send.setProperty("primary", "true")
        layout.addWidget(self._send)

        self._refresh_hint()
        self.setMinimumWidth(240)
        self.setToolTip("AI 助手（Ctrl+L 折叠/展开）")
        bus().project_opened.connect(lambda _path: self._refresh_hint())
        bus().project_closed.connect(self._refresh_hint)

    def refresh_theme(self) -> None:
        """主题切换后重绘引导文案（内联颜色取自调色板）。"""
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        providers = get_config().ai_providers
        self._status.setText(f"{len(providers)} 个模型配置" if providers else "未配置")
        self._input.setEnabled(False)
        self._send.setEnabled(False)
        hint_color = ThemeManager.instance().current().text_secondary
        self._transcript.setHtml(
            f"<p style='color:{hint_color}'>"
            "AI 助手将在 M7（流式对话）与 M8（构件条目增删改查工具）实现。<br><br>"
            "使用前请在 <b>AI → AI 设置…</b> 里配置 OpenAI 兼容端点（DeepSeek / OpenAI / Ollama 等），"
            "API key 只保存在系统钥匙串，不写入配置文件与工程文件。"
            "</p>"
        )
