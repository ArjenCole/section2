"""AI 设置对话框（计划 §8.1，M7）。

``[[ai.providers]]``：name / base_url / default_model / temperature；
支持任意 OpenAI 兼容端点。API key 只存 keyring（条目 section2/<provider>），
本对话框不落盘 key，也不回显已有 key（占位符提示“已保存”）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.config import get_config, update_config
from app.services.ai import ai_keychain

_NAME_ROLE = Qt.ItemDataRole.UserRole + 1


class AiSettingsDialog(QDialog):
    """AI 模型配置。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 设置")
        self.resize(640, 420)
        self._loading = False
        self._build()
        self._reload()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(
            "支持任意 OpenAI 兼容端点（DeepSeek / OpenAI / Ollama / vLLM / 通义…）。\n"
            "API key 只保存在系统钥匙串（条目 section2/<名称>），不写入任何文件。"
        )
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["名称", "接口地址 base_url", "默认模型", "温度"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 120)
        self._table.setColumnWidth(2, 200)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        layout.addWidget(self._table, 1)

        buttons = QHBoxLayout()
        add = QPushButton("新增")
        delete = QPushButton("删除")
        delete.setProperty("danger", "true")
        add.clicked.connect(self._add_row)
        delete.clicked.connect(self._delete_row)
        buttons.addWidget(add)
        buttons.addWidget(delete)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        key_form = QFormLayout()
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("留空表示不修改；保存后写入系统钥匙串")
        key_form.addRow("API key", self._api_key)
        layout.addLayout(key_form)

        self._active = QComboBox()
        key_form.addRow("默认使用的模型配置", self._active)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    # ------------------------------------------------------------------ 数据
    def _reload(self) -> None:
        self._loading = True
        try:
            providers = get_config().ai_providers
            self._table.setRowCount(len(providers))
            for row, provider in enumerate(providers):
                has_key = bool(ai_keychain.get_api_key(provider.get("name", "")))
                cells = (
                    provider.get("name", ""),
                    provider.get("base_url", ""),
                    provider.get("default_model", ""),
                    str(provider.get("temperature", 0.2)),
                )
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text + ("　🔑" if has_key and column == 0 else ""))
                    item.setData(_NAME_ROLE, provider.get("name", ""))
                    self._table.setItem(row, column, item)
            self._active.clear()
            for provider in providers:
                self._active.addItem(provider.get("name", ""))
            self._active.setCurrentText(get_config().ai_active_provider)
        finally:
            self._loading = False

    def _on_row_selected(self) -> None:
        self._api_key.setPlaceholderText(
            "留空表示不修改；保存后写入系统钥匙串"
            + ("（该配置已有 key）" if self._has_key() else "")
        )

    def _has_key(self) -> bool:
        name = self._selected_name()
        return bool(name) and bool(ai_keychain.get_api_key(name))

    def _selected_name(self) -> str:
        row = self._table.currentRow()
        if row < 0:
            return ""
        item = self._table.item(row, 0)
        return item.data(_NAME_ROLE) if item else ""

    def _add_row(self) -> None:
        row = self._table.rowCount()
        self._table.setRowCount(row + 1)
        defaults = (
            f"新配置{row + 1}",
            "https://api.deepseek.com/v1",
            "deepseek-chat",
            "0.2",
        )
        for column, text in enumerate(defaults):
            self._table.setItem(row, column, QTableWidgetItem(text))
        self._table.setCurrentCell(row, 0)

    def _delete_row(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).data(_NAME_ROLE)
        if name and self._has_key():
            ai_keychain.delete_api_key(name)
        self._table.removeRow(row)

    def _collect(self) -> list[dict]:
        providers = []
        for row in range(self._table.rowCount()):
            def cell(column: int) -> str:
                item = self._table.item(row, column)
                return item.text().strip() if item else ""
            name = cell(0)
            if not name:
                continue
            try:
                temperature = float(cell(3) or 0.2)
            except ValueError:
                temperature = 0.2
            providers.append(
                {
                    "name": name,
                    "base_url": cell(1),
                    "default_model": cell(2),
                    "temperature": temperature,
                }
            )
        return providers

    def _save(self) -> None:
        providers = self._collect()
        names = [provider["name"] for provider in providers]
        if len(names) != len(set(names)):
            QMessageBox.warning(self, "AI 设置", "配置名称重复，请修改。")
            return
        old_names = {provider.get("name") for provider in get_config().ai_providers}
        for name in old_names - set(names):
            ai_keychain.delete_api_key(name)
        # 保存 key：编辑行填了 key 就写入；改名时把旧 key 迁移过去
        selected = self._selected_name()
        row = self._table.currentRow()
        if row >= 0 and selected:
            new_name = self._table.item(row, 0).text().strip()
            key = self._api_key.text().strip()
            old_key = ai_keychain.get_api_key(selected)
            if key:
                ai_keychain.set_api_key(new_name, key)
            elif old_key and new_name != selected:
                ai_keychain.set_api_key(new_name, old_key)
                ai_keychain.delete_api_key(selected)

        update_config({"ai": {"providers": providers, "active_provider": self._active.currentText()}})
        self.accept()
