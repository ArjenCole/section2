"""AI 模型设置对话框（复刻 Quotor views/dialogs/ai_settings_dialog.py）。

管理多个 AI Provider profile：
- 增删改 provider（显示名 / base_url / 默认模型 / 温度）
- 从预设模板新建（DeepSeek / OpenAI / 通义 / Claude / Ollama / vLLM / LM Studio）
- 测试连接（QThread 异步调 GET /models 验证可达，成功后模型列表回填下拉框）
- 设为当前启用的 provider（即时落盘）

API key 通过 services/ai_keychain.py 存系统 keychain，config.toml 只存元数据。
与 Quotor 的差异仅两处：section2 的 provider 多一个 temperature 字段（表单保留
"温度"行）；暂不支持自定义附加请求头。
"""

from __future__ import annotations

from typing import Any

import httpx
from PySide6.QtCore import QRect, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from app.core.config import get_config, update_config
from app.services.ai import ai_keychain
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox

# Provider 预设模板: display_name / base_url / default_model（Quotor 同款）
PROVIDER_PRESETS: list[dict[str, str]] = [
    {
        "display_name": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    {
        "display_name": "OpenAI 官方",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    {
        "display_name": "通义千问 (DashScope)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    {
        "display_name": "Claude (Anthropic)",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-sonnet-20241022",
    },
    {
        "display_name": "本地 Ollama",
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5:7b",
    },
    {
        "display_name": "局域网 vLLM",
        "base_url": "http://192.168.1.50:8000/v1",
        "default_model": "",
    },
    {
        "display_name": "LM Studio",
        "base_url": "http://localhost:1234/v1",
        "default_model": "",
    },
    {
        "display_name": "自定义 (OpenAI 兼容)",
        "base_url": "",
        "default_model": "",
    },
]


class _TestConnectionWorker(QThread):
    """后台测试连接 worker：GET {base_url}/models 验证可达并列出模型。"""

    finished_with_result = Signal(bool, str, object)

    def __init__(
        self,
        base_url: str,
        api_key: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._api_key = api_key

    def run(self) -> None:  # noqa: N802 - Qt 命名
        url = self._base_url.rstrip("/")
        if not url.endswith("/models"):
            url = url + "/models"
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = httpx.get(url, headers=headers, timeout=10.0)
        except httpx.HTTPError as error:
            self.finished_with_result.emit(False, f"无法连接端点：{error}", [])
            return
        if response.status_code != 200:
            body = response.text[:200].replace("\n", " ")
            self.finished_with_result.emit(
                False, f"端点返回 {response.status_code}：{body}", []
            )
            return
        try:
            data = response.json().get("data", [])
            models = [
                item.get("id", "") for item in data if isinstance(item, dict) and item.get("id")
            ]
        except ValueError:
            models = []
        self.finished_with_result.emit(True, f"连接成功，发现 {len(models)} 个模型", models)


class _ProviderListDelegate(QStyledItemDelegate):
    """列表项绘制委托（Quotor 同款）。

    鼠标点选条目 -> 蓝色背景色块；当前启用条目 -> 文字左侧蓝色加粗竖线。
    """

    NAME_ROLE = Qt.ItemDataRole.UserRole  # 存放 provider name，用于判断启用态

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.active_name: str = ""

    def _primary(self) -> QColor:
        from app.resources.qss.theme import ThemeManager

        return QColor(ThemeManager.instance().current().primary)

    def paint(  # noqa: N802 - Qt 命名
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: object,
    ) -> None:
        painter.save()
        rect = QRect(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        active = bool(self.active_name) and index.data(self.NAME_ROLE) == self.active_name

        if selected:  # 选中态: 蓝色背景块
            background = self._primary()
            background.setAlpha(70)
            painter.fillRect(rect, background)

        bar_w = 0
        if active:  # 启用态: 文字左侧蓝色加粗竖线
            bar_w = 4
            bar_h = min(14, rect.height())
            bar = QRect(
                rect.left() + 6,
                rect.top() + (rect.height() - bar_h) // 2,
                3,
                bar_h,
            )
            painter.fillRect(bar, self._primary())

        padding = bar_w + 8 if bar_w else 8
        text_rect = QRect(rect).adjusted(padding, 0, -4, 0)
        painter.setPen(QColor(option.palette.color(option.palette.ColorRole.Text)))
        painter.setFont(option.font)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            str(index.data(Qt.ItemDataRole.DisplayRole)),
        )
        painter.restore()


class AiSettingsDialog(FramelessDialog):
    """AI 模型设置对话框（Quotor 同款交互）。

    关闭（确定）时把改动保存到 config.toml + keychain；
    「设为当前启用」校验通过后即时落盘。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, "AI 模型设置")
        self.setModal(True)
        self.setMinimumWidth(720)
        self.setMinimumHeight(480)

        # 内存中的 provider 列表（深拷贝当前配置，避免取消时污染）
        self._providers: list[dict[str, Any]] = [dict(p) for p in get_config().ai_providers]
        self._active_provider: str = get_config().ai_active_provider
        self._selected_index: int = -1
        self._test_worker: _TestConnectionWorker | None = None

        self._setup_ui()
        self._populate_list()
        if self._providers:
            # 默认选中「当前启用」的条目而不是列表第一项
            active_row = next(
                (i for i, p in enumerate(self._providers) if p.get("name") == self._active_provider),
                0,
            )
            self._list.setCurrentRow(active_row)
        else:
            self._clear_form()
            self._set_form_enabled(False)

    # --- 界面 ---
    def _setup_ui(self) -> None:
        layout = self.bodyLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        hint = QLabel(
            "配置 AI 模型来源。可添加多个 Provider（本地局域网模型或公共云模型），"
            "并选择当前启用的一个。API Key 通过系统 keychain 安全存储。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        main_layout = QHBoxLayout()
        main_layout.setSpacing(12)

        # 左侧: provider 列表 + 新增/删除 + 设为当前启用
        left = QVBoxLayout()
        left.setSpacing(8)
        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        self._delegate = _ProviderListDelegate(self._list)
        self._delegate.active_name = self._active_provider
        self._list.setItemDelegate(self._delegate)
        self._list.currentRowChanged.connect(self._on_select_row)
        left.addWidget(self._list, stretch=1)

        list_btn_row = QHBoxLayout()
        self._add_btn = QPushButton("新增...")
        self._add_btn.setProperty("secondary", "true")
        self._add_btn.clicked.connect(self._on_add)
        list_btn_row.addWidget(self._add_btn)
        self._del_btn = QPushButton("删除")
        self._del_btn.setProperty("secondary", "true")
        self._del_btn.clicked.connect(self._on_delete)
        list_btn_row.addWidget(self._del_btn)
        left.addLayout(list_btn_row)

        self._activate_btn = QPushButton("设为当前启用")
        self._activate_btn.clicked.connect(self._on_activate)
        left.addWidget(self._activate_btn)

        main_layout.addLayout(left)

        # 右侧: 表单
        right = QVBoxLayout()
        right.setSpacing(8)
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._display_name_edit = QLineEdit()
        self._display_name_edit.textEdited.connect(self._on_field_edited)
        form.addRow("显示名:", self._display_name_edit)

        self._base_url_edit = QLineEdit()
        self._base_url_edit.setPlaceholderText("https://api.example.com/v1")
        self._base_url_edit.textEdited.connect(self._on_field_edited)
        form.addRow("Base URL:", self._base_url_edit)

        self._default_model_edit = QComboBox()
        self._default_model_edit.setEditable(True)
        self._default_model_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._default_model_edit.lineEdit().setPlaceholderText(
            "deepseek-chat / gpt-4o-mini / qwen2.5:7b ... (测试连接后可下拉选择)"
        )
        self._default_model_edit.currentTextChanged.connect(self._on_field_edited)
        form.addRow("默认模型:", self._default_model_edit)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("留空表示不修改已保存的 key")
        form.addRow("API Key:", self._api_key_edit)

        self._temperature_edit = QLineEdit()
        self._temperature_edit.textEdited.connect(self._on_field_edited)
        form.addRow("温度:", self._temperature_edit)

        right.addLayout(form)

        # 测试连接按钮 + 结果标签
        test_row = QHBoxLayout()
        self._test_btn = QPushButton("测试连接")
        self._test_btn.clicked.connect(self._on_test_connection)
        test_row.addWidget(self._test_btn)
        self._test_result = QLabel("")
        self._test_result.setWordWrap(True)
        test_row.addWidget(self._test_result, stretch=1)
        right.addLayout(test_row)

        right.addStretch(1)
        main_layout.addLayout(right, stretch=1)

        layout.addLayout(main_layout, stretch=1)

        # 全局行为: AI 写操作人工确认开关（Quotor 同款，即改即存）
        self._require_confirm_check = QCheckBox(
            "AI 助手执行操作前需人工确认（取消后内置 AI 助手执行写操作不再弹确认窗）"
        )
        self._require_confirm_check.setChecked(get_config().ai_require_confirmation)
        self._require_confirm_check.toggled.connect(self._on_confirm_toggled)
        layout.addWidget(self._require_confirm_check)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._ok_btn = QPushButton("确定")
        self._ok_btn.setProperty("primary", "true")
        self._ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(self._ok_btn)
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

    # --- 列表填充 ---
    def _refresh_item(self, item: QListWidgetItem, p: dict[str, Any]) -> None:
        """更新列表项文字与启用标记（选中/启用样式由 delegate 统一绘制）。"""
        item.setText(p.get("display_name") or p.get("name", "(未命名)"))
        item.setData(self._delegate.NAME_ROLE, p.get("name", ""))
        self._list.viewport().update()

    def _populate_list(self) -> None:
        # clear() 会触发 currentRowChanged(-1) 并清空表单；恢复选中行走 setCurrentRow
        # 重新载表单（此时 _selected_index 仍为 -1，_commit_current_form 跳过，无误写回）
        row = self._selected_index
        self._list.clear()
        self._delegate.active_name = self._active_provider
        for p in self._providers:
            item = QListWidgetItem()
            self._refresh_item(item, p)
            self._list.addItem(item)
        if row >= len(self._providers):
            row = max(0, len(self._providers) - 1)
        if row >= 0:
            self._list.setCurrentRow(row)

    def _on_select_row(self, row: int) -> None:
        # 切换前先保存当前编辑到内存
        self._commit_current_form()
        self._selected_index = row
        if 0 <= row < len(self._providers):
            self._load_form(self._providers[row])
            self._set_form_enabled(True)
            self._update_activate_btn()
        else:
            self._clear_form()
            self._set_form_enabled(False)

    def _load_form(self, profile: dict[str, Any]) -> None:
        self._display_name_edit.setText(profile.get("display_name", ""))
        self._base_url_edit.setText(profile.get("base_url", ""))
        self._default_model_edit.blockSignals(True)
        current = profile.get("default_model", "")
        idx = self._default_model_edit.findText(current)
        if idx >= 0:
            self._default_model_edit.setCurrentIndex(idx)
        else:
            self._default_model_edit.setCurrentIndex(-1)
            self._default_model_edit.lineEdit().setText(current)
        self._default_model_edit.blockSignals(False)
        # API key 不回显，留空表示不修改
        self._api_key_edit.setText("")
        self._api_key_edit.setPlaceholderText("留空表示不修改已保存的 key")
        self._temperature_edit.setText(f"{profile.get('temperature', 0.2):g}")
        self._test_result.setText("")

    def _clear_form(self) -> None:
        self._display_name_edit.clear()
        self._base_url_edit.clear()
        self._default_model_edit.blockSignals(True)
        self._default_model_edit.clear()
        self._default_model_edit.blockSignals(False)
        self._api_key_edit.clear()
        self._temperature_edit.clear()
        self._test_result.setText("")

    def _set_form_enabled(self, enabled: bool) -> None:
        for widget in (
            self._display_name_edit,
            self._base_url_edit,
            self._default_model_edit,
            self._api_key_edit,
            self._temperature_edit,
            self._test_btn,
        ):
            widget.setEnabled(enabled)
        self._activate_btn.setEnabled(enabled and self._can_activate())

    def _can_activate(self) -> bool:
        if not (0 <= self._selected_index < len(self._providers)):
            return False
        p = self._providers[self._selected_index]
        return bool(p.get("display_name")) and bool(p.get("base_url"))

    def _update_activate_btn(self) -> None:
        p = (
            self._providers[self._selected_index]
            if 0 <= self._selected_index < len(self._providers)
            else None
        )
        if p and p.get("name") == self._active_provider:
            self._activate_btn.setText("当前已启用")
            self._activate_btn.setEnabled(False)
        else:
            self._activate_btn.setText("设为当前启用")
            self._activate_btn.setEnabled(self._can_activate())

    # --- 字段编辑 ---
    def _on_confirm_toggled(self, checked: bool) -> None:
        """人工确认开关即改即存（确认判定每次实时读配置）。"""
        update_config({"ai": {"require_confirmation": checked}})

    def _on_field_edited(self, *_args) -> None:
        """字段被编辑时实时同步到内存 + 列表标签。"""
        if not (0 <= self._selected_index < len(self._providers)):
            return
        self._commit_current_form()
        p = self._providers[self._selected_index]
        item = self._list.item(self._selected_index)
        if item is not None:
            self._refresh_item(item, p)
        self._update_activate_btn()

    def _commit_current_form(self) -> None:
        """把当前表单值提交到内存中的 provider dict。"""
        if not (0 <= self._selected_index < len(self._providers)):
            return
        p = self._providers[self._selected_index]
        p["display_name"] = self._display_name_edit.text().strip()
        p["base_url"] = self._base_url_edit.text().strip()
        p["default_model"] = self._default_model_edit.currentText().strip()
        try:
            p["temperature"] = float(self._temperature_edit.text().strip() or 0.2)
        except ValueError:
            p["temperature"] = 0.2
        # api_key 单独处理（只在非空时写入 keychain）
        new_key = self._api_key_edit.text()
        if new_key:
            p["_pending_api_key"] = new_key

    # --- 新增 / 删除 ---
    def _on_add(self) -> None:
        """弹出预设模板菜单，选择后创建新 provider（Quotor 同款）。"""
        menu = QMenu(self)
        for preset in PROVIDER_PRESETS:
            action = menu.addAction(preset["display_name"])
            action.triggered.connect(lambda _checked=False, pr=preset: self._add_from_preset(pr))
        btn_pos = self._add_btn.mapToGlobal(self._add_btn.rect().bottomLeft())
        menu.exec(btn_pos)

    def _add_from_preset(self, preset: dict[str, str]) -> None:
        base = preset["display_name"]
        existing_names = {p.get("name", "") for p in self._providers}
        existing_displays = {p.get("display_name", "") for p in self._providers}
        display_name = base
        suffix = 2
        while display_name in existing_displays:
            display_name = f"{base} {suffix}"
            suffix += 1
        name = display_name
        while name in existing_names:
            name = f"{display_name}_{suffix}"
            suffix += 1

        self._providers.append(
            {
                "name": name,
                "display_name": display_name,
                "base_url": preset["base_url"],
                "default_model": preset["default_model"],
            }
        )
        self._populate_list()
        self._list.setCurrentRow(len(self._providers) - 1)

    def _on_delete(self) -> None:
        if not (0 <= self._selected_index < len(self._providers)):
            return
        p = self._providers[self._selected_index]
        name = p.get("name", "")
        reply = FramelessMessageBox.question(
            self,
            "确认删除",
            f"确定删除 provider「{p.get('display_name', name)}」吗？\n"
            f"系统 keychain 中对应的 API Key 也会一并删除。",
            FramelessMessageBox.Yes | FramelessMessageBox.No,
            FramelessMessageBox.No,
        )
        if reply != FramelessMessageBox.Yes:
            return
        if name:
            ai_keychain.delete_api_key(name)
        if self._active_provider == name:
            self._active_provider = ""
        self._providers.pop(self._selected_index)
        self._populate_list()
        if self._providers:
            new_row = min(self._selected_index, len(self._providers) - 1)
            self._list.setCurrentRow(new_row)
        else:
            self._selected_index = -1
            self._clear_form()
            self._set_form_enabled(False)

    def _on_activate(self) -> None:
        if not (0 <= self._selected_index < len(self._providers)):
            return
        p = self._providers[self._selected_index]
        if not p.get("display_name") or not p.get("base_url"):
            return
        self._active_provider = p.get("name", "")
        self._populate_list()
        self._update_activate_btn()
        # 即时持久化：「设为当前启用」是明确的提交动作，立即写盘
        if self._validate_providers(silent=True):
            self._persist()

    # --- 测试连接 ---
    def _on_test_connection(self) -> None:
        if not (0 <= self._selected_index < len(self._providers)):
            return
        self._commit_current_form()
        p = self._providers[self._selected_index]
        base_url = p.get("base_url", "")
        if not base_url:
            self._test_result.setText("请先填写 Base URL")
            return
        # api_key: 优先用表单输入的（即使未保存），其次 keychain 中已存的
        api_key = p.get("_pending_api_key") or ai_keychain.get_api_key(p.get("name", ""))
        self._test_btn.setEnabled(False)
        self._test_result.setText("测试中...")

        self._test_worker = _TestConnectionWorker(base_url, api_key, self)
        self._test_worker.finished_with_result.connect(self._on_test_finished)
        self._test_worker.start()

    def _on_test_finished(self, ok: bool, msg: str, models: object) -> None:
        from app.resources.qss.theme import ThemeManager

        colors = ThemeManager.instance().current()
        color = colors.success if ok else colors.danger
        self._test_result.setText(f'<span style="color:{color};">{msg}</span>')
        self._test_btn.setEnabled(True)
        self._test_worker = None

        # 成功且有模型列表时，回填到下拉框供用户直接选择
        if ok and models:
            model_ids = [m for m in models if isinstance(m, str) and m]
            if not model_ids:
                return
            current = self._default_model_edit.currentText().strip()
            self._default_model_edit.blockSignals(True)
            self._default_model_edit.clear()
            self._default_model_edit.addItems(model_ids)
            if current and current in model_ids:
                self._default_model_edit.setCurrentText(current)
            elif current:
                self._default_model_edit.setCurrentIndex(-1)
                self._default_model_edit.lineEdit().setText(current)
            else:
                self._default_model_edit.setCurrentIndex(0)
            self._default_model_edit.blockSignals(False)
            self._commit_current_form()

    # --- 确定保存 ---
    def _validate_providers(self, *, silent: bool = False) -> bool:
        """校验所有 provider 的必填字段；silent 时不弹窗（用于启用即存路径）。"""
        for p in self._providers:
            if not p.get("display_name"):
                if not silent:
                    FramelessMessageBox.warning(
                        self, "校验失败",
                        f"provider「{p.get('name')}」缺少显示名，请补全或删除该条目。",
                    )
                return False
            if not p.get("base_url"):
                if not silent:
                    FramelessMessageBox.warning(
                        self, "校验失败",
                        f"provider「{p.get('display_name')}」缺少 Base URL，请补全或删除该条目。",
                    )
                return False
        return True

    def _persist(self) -> None:
        """把内存中的 providers + 启用状态写入 config.toml 并同步 keychain。"""
        providers_clean: list[dict[str, Any]] = []
        for p in self._providers:
            clean = {
                "name": p["name"],
                "display_name": p["display_name"],
                "base_url": p["base_url"],
                "default_model": p.get("default_model", ""),
            }
            if "temperature" in p:
                clean["temperature"] = p.get("temperature", 0.2)
            providers_clean.append(clean)
            if "_pending_api_key" in p:
                ai_keychain.set_api_key(p["name"], p.pop("_pending_api_key"))
        # 清掉已删除 provider 的 key
        old_names = {provider.get("name") for provider in get_config().ai_providers}
        for name in old_names - {p["name"] for p in providers_clean}:
            ai_keychain.delete_api_key(name)
        update_config(
            {
                "ai": {
                    "providers": providers_clean,
                    "active_provider": self._active_provider,
                }
            }
        )

    def _on_ok(self) -> None:
        self._commit_current_form()
        if not self._validate_providers():
            return
        self._persist()
        self.accept()
