"""MCP 服务设置对话框。

- 开关（应用启动时是否自动启动）、端口、Bearer token（生成/复制）
- allow_actions（关闭 = 只暴露只读工具）、require_confirmation（MCP 通道写操作确认）
- 启动/停止服务与状态显示
- 一键复制 Claude Desktop / Cursor / Codex 客户端配置片段
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.core.config import get_config, update_config
from app.mcp_server.auth import generate_token
from app.mcp_server.controller import McpServerController
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox


def _snippets(url: str, token: str) -> str:
    return (
        "// Claude Desktop（claude_desktop_config.json）/ Cursor / Cline / VS Code\n"
        '{\n'
        '  "mcpServers": {\n'
        '    "section2": {\n'
        f'      "url": "{url}",\n'
        f'      "headers": {{ "Authorization": "Bearer {token}" }}\n'
        "    }\n"
        "  }\n"
        "}\n\n"
        "# Codex CLI（~/.codex/config.toml）\n"
        "[mcp_servers.section2]\n"
        'type = "http"\n'
        f'url = "{url}"\n'
        f'headers = {{ Authorization = "Bearer {token}" }}\n\n'
        "# 只支持 stdio 的客户端：用 stdio 桥接\n"
        "# command = section2-mcp\n"
        f'# args = ["--connect", "{url}", "--token", "{token}"]\n'
    )


class McpSettingsDialog(FramelessDialog):
    """MCP 服务设置。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, "MCP 服务设置")
        self.setModal(True)
        self.setMinimumWidth(680)
        self._build_ui()
        self._load()

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        layout = self.bodyLayout()
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        hint = QLabel(
            "把 Section 2.0 的全部工具暴露给外部 AI 客户端（Claude Desktop / Cursor / "
            "Codex / Cline / WorkBuddy…）。服务仅监听 127.0.0.1（本机回环），"
            "访问需要 Bearer token；工程仍由桌面应用持有，界面会实时刷新。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)

        self._enabled = QCheckBox("应用启动时自动启动 MCP 服务")
        form.addRow("", self._enabled)

        self._port = QSpinBox()
        self._port.setRange(1024, 65535)
        form.addRow("端口:", self._port)

        token_row = QHBoxLayout()
        self._token = QLineEdit()
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        token_row.addWidget(self._token, 1)
        btn_generate = QPushButton("生成")
        btn_generate.setProperty("secondary", "true")
        btn_generate.clicked.connect(self._generate)
        token_row.addWidget(btn_generate)
        btn_show = QPushButton("显示")
        btn_show.setProperty("secondary", "true")
        btn_show.setCheckable(True)
        btn_show.toggled.connect(
            lambda checked: self._token.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        token_row.addWidget(btn_show)
        form.addRow("Bearer token:", token_row)

        self._allow_actions = QCheckBox("允许外部客户端执行写操作（关闭 = 只读模式）")
        form.addRow("", self._allow_actions)

        self._require_confirm = QCheckBox("外部客户端写操作时在界面弹出确认卡")
        form.addRow("", self._require_confirm)

        layout.addLayout(form)

        # 运行状态
        status_row = QHBoxLayout()
        self._status = QLabel("")
        self._status.setWordWrap(True)
        status_row.addWidget(self._status, 1)
        self._btn_start = QPushButton("启动服务")
        self._btn_start.setProperty("primary", "true")
        self._btn_start.clicked.connect(self._start)
        status_row.addWidget(self._btn_start)
        self._btn_stop = QPushButton("停止服务")
        self._btn_stop.clicked.connect(self._stop)
        status_row.addWidget(self._btn_stop)
        layout.addLayout(status_row)

        # 客户端配置片段
        config_label = QLabel("客户端配置（复制后粘贴到对应配置文件）：")
        layout.addWidget(config_label)
        self._snippet = QPlainTextEdit()
        self._snippet.setReadOnly(True)
        self._snippet.setMaximumHeight(190)
        layout.addWidget(self._snippet)
        copy_row = QHBoxLayout()
        copy_row.addStretch(1)
        btn_copy = QPushButton("复制配置")
        btn_copy.setProperty("secondary", "true")
        btn_copy.clicked.connect(self._copy_snippet)
        copy_row.addWidget(btn_copy)
        layout.addLayout(copy_row)

        # 底部
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        btn_ok = QPushButton("保存")
        btn_ok.setProperty("primary", "true")
        btn_ok.clicked.connect(self._save)
        buttons.addWidget(btn_ok)
        btn_cancel = QPushButton("关闭")
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        layout.addLayout(buttons)

    # ------------------------------------------------------------------ 数据
    def _load(self) -> None:
        config = get_config()
        self._enabled.setChecked(config.mcp_enabled)
        self._port.setValue(config.mcp_port)
        self._token.setText(config.mcp_token)
        self._allow_actions.setChecked(config.mcp_allow_actions)
        self._require_confirm.setChecked(config.mcp_require_confirmation)
        self._refresh_status()

    def _persist(self) -> None:
        update_config(
            {
                "mcp": {
                    "enabled": self._enabled.isChecked(),
                    "port": self._port.value(),
                    "token": self._token.text().strip(),
                    "allow_actions": self._allow_actions.isChecked(),
                    "require_confirmation": self._require_confirm.isChecked(),
                }
            }
        )

    def _generate(self) -> None:
        self._token.setText(generate_token())

    def _start(self) -> None:
        self._persist()
        ok, message = McpServerController.instance().start()
        self._refresh_status()
        if not ok:
            FramelessMessageBox.warning(self, "MCP 服务", message)

    def _stop(self) -> None:
        McpServerController.instance().stop()
        self._refresh_status()

    def _refresh_status(self) -> None:
        status = McpServerController.instance().status()
        if status["running"]:
            self._status.setText(f"● 运行中：{status['url']}")
            self._status.setStyleSheet("color: #2e7d32;")
        else:
            self._status.setText(f"○ 已停止{('：' + status['error']) if status['error'] else ''}")
            self._status.setStyleSheet("")
        self._snippet.setPlainText(
            _snippets(status["url"], self._token.text().strip() or status["token"] or "<token>")
        )

    def _copy_snippet(self) -> None:
        QApplication.clipboard().setText(self._snippet.toPlainText())
        self._status.setText("客户端配置已复制到剪贴板。")

    def _save(self) -> None:
        if not self._token.text().strip():
            self._token.setText(generate_token())
        self._persist()
        controller = McpServerController.instance()
        if self._enabled.isChecked() and not controller.running():
            controller.start()
        elif not self._enabled.isChecked() and controller.running():
            controller.stop()
        self.accept()
