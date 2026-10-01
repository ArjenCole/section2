"""无边框对话框基类与统一消息框（照搬 Quotor views/widgets/frameless_dialog.py）。

为所有弹出窗体提供统一风格：
- 去除系统标题栏与边框（Qt.FramelessWindowHint）+ 自定义标题栏（支持拖拽）
- Windows 11 原生圆角（Win10 自动忽略）
- :class:`FramelessMessageBox` 提供与 QMessageBox 一致的静态方法 API，
  图标为 Lucide SVG 着色渲染，按钮文案/顺序统一（肯定在前、取消最后），
  全项目统一用它替换 QMessageBox。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# 消息框按钮文案映射（StandardButton → 中文）
_BUTTON_TEXT = {
    QMessageBox.StandardButton.Ok: "确定",
    QMessageBox.StandardButton.Cancel: "取消",
    QMessageBox.StandardButton.Yes: "是",
    QMessageBox.StandardButton.No: "否",
    QMessageBox.StandardButton.Save: "保存",
    QMessageBox.StandardButton.Discard: "不保存",
    QMessageBox.StandardButton.Close: "关闭",
    QMessageBox.StandardButton.Abort: "中止",
    QMessageBox.StandardButton.Retry: "重试",
    QMessageBox.StandardButton.Ignore: "忽略",
    QMessageBox.StandardButton.Apply: "应用",
    QMessageBox.StandardButton.Reset: "重置",
    QMessageBox.StandardButton.RestoreDefaults: "恢复默认",
    QMessageBox.StandardButton.Help: "帮助",
    QMessageBox.StandardButton.SaveAll: "全部保存",
    QMessageBox.StandardButton.YesAll: "全是",
    QMessageBox.StandardButton.NoAll: "全否",
}

# 图标：Lucide SVG（currentColor 运行时着色），path 与 Quotor resources/icons 一致
_ICON_BODIES = {
    "info": '<circle cx="12" cy="12" r="10" /><path d="M12 16v-4" /><path d="M12 8h.01" />',
    "alert-circle": (
        '<circle cx="12" cy="12" r="10" /><line x1="12" x2="12" y1="8" y2="12" />'
        '<line x1="12" x2="12.01" y1="16" y2="16" />'
    ),
    "help-circle": (
        '<circle cx="12" cy="12" r="10" />'
        '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><path d="M12 17h.01" />'
    ),
    "moon": (
        '<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803'
        'a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401" />'
    ),
    "sun": (
        '<circle cx="12" cy="12" r="4" /><path d="M12 2v2" /><path d="M12 20v2" />'
        '<path d="m4.93 4.93 1.41 1.41" /><path d="m17.66 17.66 1.41 1.41" />'
        '<path d="M2 12h2" /><path d="M20 12h2" /><path d="m6.34 17.66-1.41 1.41" />'
        '<path d="m19.07 4.93-1.41 1.41" />'
    ),
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />',
    "folder-open": (
        '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4'
        'a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2" />'
    ),
    "folder-plus": (
        '<path d="M12 10v6" /><path d="M9 13h6" />'
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4'
        'a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />'
    ),
    "file-text": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12'
        'a2 2 0 0 1-2 2z" /><path d="M14 2v5a1 1 0 0 0 1 1h5" /><path d="M10 9H8" />'
        '<path d="M16 13H8" /><path d="M16 17H8" />'
    ),
    "file-plus": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12'
        'a2 2 0 0 1-2 2z" /><path d="M14 2v5a1 1 0 0 0 1 1h5" /><path d="M9 15h6" /><path d="M12 18v-6" />'
    ),
    "save": (
        '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5'
        'a2 2 0 0 1 2-2z" /><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7" /><path d="M7 3v4a1 1 0 0 0 1 1h7" />'
    ),
    "plus": '<path d="M5 12h14" /><path d="M12 5v14" />',
    "panel-right": (
        '<rect x="4" y="6" width="15" height="13" rx="2" /><path d="M12 6v13" />'
        '<path d="M18 3l1 2 2 1-2 1-1 2-1-2-2-1 2-1z" />'
    ),
    "chevron-up": '<path d="m18 15-6-6-6 6" />',
    "chevron-down": '<path d="m6 9 6 6 6-6" />',
    "chevron-left": '<path d="m15 18-6-6 6-6" />',
    "chevron-right": '<path d="m9 18 6-6-6-6" />',
    "settings": (
        '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08'
        'a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09'
        'a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20'
        'a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73'
        'l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73'
        'l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />'
        '<circle cx="12" cy="12" r="3" />'
    ),
    "refresh-cw": (
        '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />'
        '<path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />'
        '<path d="M8 16H3v5" />'
    ),
}

_ICON_SVG = {
    QMessageBox.Icon.Information: "info",
    QMessageBox.Icon.Warning: "alert-circle",
    QMessageBox.Icon.Critical: "alert-circle",
    QMessageBox.Icon.Question: "help-circle",
}

# 图标颜色亮暗主题同色（与 Quotor 一致）
_ICON_COLOR = {
    QMessageBox.Icon.Information: "#3B82F6",
    QMessageBox.Icon.Warning: "#F59E0B",
    QMessageBox.Icon.Critical: "#EF4444",
    QMessageBox.Icon.Question: "#3B82F6",
}

# 按钮显示顺序：肯定操作在前 → 破坏性居中 → 取消/关闭最后
_ALL_BUTTONS = [
    QMessageBox.StandardButton.Save,
    QMessageBox.StandardButton.SaveAll,
    QMessageBox.StandardButton.Yes,
    QMessageBox.StandardButton.YesAll,
    QMessageBox.StandardButton.Ok,
    QMessageBox.StandardButton.Apply,
    QMessageBox.StandardButton.Retry,
    QMessageBox.StandardButton.Ignore,
    QMessageBox.StandardButton.Discard,
    QMessageBox.StandardButton.No,
    QMessageBox.StandardButton.NoAll,
    QMessageBox.StandardButton.Abort,
    QMessageBox.StandardButton.Reset,
    QMessageBox.StandardButton.RestoreDefaults,
    QMessageBox.StandardButton.Close,
    QMessageBox.StandardButton.Cancel,
    QMessageBox.StandardButton.Help,
]


def load_icon(name: str, color: str, size: int = 24) -> QIcon:
    """把内置 Lucide SVG 按 color 着色渲染成 QIcon（供菜单/工具栏动作复用）。"""
    body = _ICON_BODIES[name]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">{body}</svg>'.format(color=color, body=body)
    )
    renderer = QSvgRenderer(svg.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def _make_close_icon(color: str) -> QIcon:
    """绘制关闭按钮 X 图标。"""
    size = 16
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(color), 1.6))
    painter.drawLine(4, 4, size - 4, size - 4)
    painter.drawLine(size - 4, 4, 4, size - 4)
    painter.end()
    return QIcon(pm)


class _DialogCloseButton(QToolButton):
    """对话框关闭按钮：悬停时切换图标颜色。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WindowBtn")
        self.setProperty("kind", "close")
        self.setFixedSize(46, 36)
        self._normal_color = "#C0C0C0"
        self._hover_color = "#FFFFFF"
        self._hovered = False
        self._refresh()

    def set_colors(self, normal: str, hover: str) -> None:
        self._normal_color = normal
        self._hover_color = hover
        self._refresh()

    def _refresh(self) -> None:
        self.setIcon(_make_close_icon(self._hover_color if self._hovered else self._normal_color))

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._hovered = True
        self._refresh()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._hovered = False
        self._refresh()
        super().leaveEvent(event)


class DialogTitleBar(QFrame):
    """对话框自定义标题栏（标题 + 关闭按钮，支持拖拽移动）。"""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FramelessTitleBar")
        self.setFixedHeight(36)

        self._pressed = False
        self._drag_offset: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)

        self._title_label = QLabel(title)
        self._title_label.setProperty("role", "dialog-title")
        # 透传鼠标事件到标题栏，点标题文字也能拖拽
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._title_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)

        self._btn_close = _DialogCloseButton(self)
        layout.addWidget(self._btn_close)
        self._btn_close.clicked.connect(self._on_close)

        self._apply_theme()

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def _apply_theme(self) -> None:
        from app.resources.qss.theme import ThemeManager

        colors = ThemeManager.instance().current()
        self._btn_close.set_colors(colors.text_primary, colors.text_inverse)

    def refresh_theme(self) -> None:
        self._apply_theme()

    def _on_close(self) -> None:
        window = self.window()
        if window is not None:
            window.close()

    # --- 拖拽移动 ---
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window is not None:
                self._pressed = True
                self._drag_offset = (
                    event.globalPosition().toPoint() - window.frameGeometry().topLeft()
                )
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if not self._pressed or self._drag_offset is None:
            return
        window = self.window()
        if window is not None:
            window.move(event.globalPosition().toPoint() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._pressed = False
        self._drag_offset = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        event.accept()


class FramelessDialog(QDialog):
    """无边框对话框基类：子类向 bodyLayout() 添加内容。"""

    def __init__(self, parent: QWidget | None = None, title: str = "") -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        self._title_bar = DialogTitleBar(title, self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._title_bar)

        self._body = QWidget()
        self._body.setObjectName("FramelessDialogBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._body, stretch=1)

    def bodyLayout(self) -> QVBoxLayout:
        return self._body_layout

    def bodyWidget(self) -> QWidget:
        return self._body

    def setWindowTitle(self, title: str) -> None:  # noqa: N802 - Qt 命名
        super().setWindowTitle(title)
        self._title_bar.set_title(title)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        self._enable_win11_rounded_corners()

    def _enable_win11_rounded_corners(self) -> None:
        """Windows 11 原生圆角（Win10 自动忽略）。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes  # noqa: PLC0415

            hwnd = int(self.winId())
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33; DWMWCP_ROUND = 2
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref)
            )
        except Exception:  # noqa: BLE001
            pass


class FramelessMessageBox(FramelessDialog):
    """无边框消息框：与 QMessageBox 一致的静态方法 API，可直接替换。"""

    # === 重新导出 QMessageBox 常量 ===
    StandardButton = QMessageBox.StandardButton
    ButtonRole = QMessageBox.ButtonRole
    Icon = QMessageBox.Icon

    NoIcon = QMessageBox.Icon.NoIcon
    Information = QMessageBox.Icon.Information
    Warning = QMessageBox.Icon.Warning
    Critical = QMessageBox.Icon.Critical
    Question = QMessageBox.Icon.Question

    NoButton = QMessageBox.StandardButton.NoButton
    Ok = QMessageBox.StandardButton.Ok
    Cancel = QMessageBox.StandardButton.Cancel
    Yes = QMessageBox.StandardButton.Yes
    No = QMessageBox.StandardButton.No
    Save = QMessageBox.StandardButton.Save
    Discard = QMessageBox.StandardButton.Discard
    Close = QMessageBox.StandardButton.Close
    Abort = QMessageBox.StandardButton.Abort
    Retry = QMessageBox.StandardButton.Retry
    Ignore = QMessageBox.StandardButton.Ignore
    Apply = QMessageBox.StandardButton.Apply
    Reset = QMessageBox.StandardButton.Reset
    RestoreDefaults = QMessageBox.StandardButton.RestoreDefaults
    Help = QMessageBox.StandardButton.Help
    SaveAll = QMessageBox.StandardButton.SaveAll
    YesAll = QMessageBox.StandardButton.YesAll
    NoAll = QMessageBox.StandardButton.NoAll

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, "")
        self.setModal(True)
        self._result: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton
        self._buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = self.bodyLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        content = QHBoxLayout()
        content.setSpacing(12)
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(24, 24)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._text_label = QLabel()
        self._text_label.setWordWrap(True)
        self._text_label.setTextFormat(Qt.TextFormat.RichText)
        self._text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._text_label.setMinimumWidth(300)
        content.addWidget(self._icon_label, alignment=Qt.AlignmentFlag.AlignTop)
        content.addWidget(self._text_label, stretch=1)
        layout.addLayout(content)

        self._button_row = QHBoxLayout()
        self._button_row.addStretch(1)
        self._button_container = QHBoxLayout()
        self._button_container.setSpacing(8)
        self._button_row.addLayout(self._button_container)
        self._button_row.addStretch(1)
        layout.addLayout(self._button_row)

    def _set_icon(self, icon_type: QMessageBox.Icon) -> None:
        svg_name = _ICON_SVG.get(icon_type)
        if svg_name:
            color = _ICON_COLOR.get(icon_type, "#3B82F6")
            self._icon_label.setPixmap(load_icon(svg_name, color, 24).pixmap(24, 24))
        else:
            self._icon_label.clear()

    def _set_text(self, text: str) -> None:
        self._text_label.setText(text)
        self.adjustSize()

    def _add_buttons(
        self,
        buttons: QMessageBox.StandardButton,
        default: QMessageBox.StandardButton,
        button_texts: dict | None = None,
    ) -> None:
        self._buttons = buttons
        while self._button_container.count():
            item = self._button_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        has_default = default != QMessageBox.StandardButton.NoButton and (buttons & default)
        for button_value in _ALL_BUTTONS:
            if not (buttons & button_value):
                continue
            text = (button_texts or {}).get(
                button_value, _BUTTON_TEXT.get(button_value, str(button_value))
            )
            button = QPushButton(text)
            if button_value == default or (
                not has_default and button_value == QMessageBox.StandardButton.Ok
            ):
                button.setProperty("primary", True)
            button.setMinimumWidth(72)
            button.clicked.connect(
                lambda checked=False, value=button_value: self._on_button_clicked(value)
            )
            self._button_container.addWidget(button)

    def _on_button_clicked(self, button: QMessageBox.StandardButton) -> None:
        self._result = button
        self.accept()

    def reject(self) -> None:  # noqa: N802 - Qt 命名
        # X / Esc 关闭：有 Cancel 时归为 Cancel
        if self._result == QMessageBox.StandardButton.NoButton:
            if self._buttons & QMessageBox.StandardButton.Cancel:
                self._result = QMessageBox.StandardButton.Cancel
        super().reject()

    # === 静态方法（匹配 QMessageBox API） ===

    @staticmethod
    def information(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        box = FramelessMessageBox(parent)
        box.setWindowTitle(title)
        box._set_icon(QMessageBox.Icon.Information)
        box._set_text(text)
        box._add_buttons(buttons, default)
        box.exec()
        return box._result

    @staticmethod
    def warning(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        box = FramelessMessageBox(parent)
        box.setWindowTitle(title)
        box._set_icon(QMessageBox.Icon.Warning)
        box._set_text(text)
        box._add_buttons(buttons, default)
        box.exec()
        return box._result

    @staticmethod
    def critical(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        box = FramelessMessageBox(parent)
        box.setWindowTitle(title)
        box._set_icon(QMessageBox.Icon.Critical)
        box._set_text(text)
        box._add_buttons(buttons, default)
        box.exec()
        return box._result

    @staticmethod
    def question(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes
        | QMessageBox.StandardButton.No,
        default: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
        button_texts: dict | None = None,
    ) -> QMessageBox.StandardButton:
        box = FramelessMessageBox(parent)
        box.setWindowTitle(title)
        box._set_icon(QMessageBox.Icon.Question)
        box._set_text(text)
        box._add_buttons(buttons, default, button_texts=button_texts)
        box.exec()
        return box._result

    @staticmethod
    def about(parent: QWidget | None, title: str, text: str) -> None:
        box = FramelessMessageBox(parent)
        box.setWindowTitle(title)
        box._set_icon(QMessageBox.Icon.Information)
        box._set_text(text)
        box._add_buttons(QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok)
        box.exec()


class FramelessInputDialog(FramelessDialog):
    """无边框文本输入对话框（QInputDialog.getText 的自绘替代，API 一致）。"""

    def __init__(
        self, parent: QWidget | None, title: str, label: str, text: str = ""
    ) -> None:
        super().__init__(parent, title)
        self.setMinimumWidth(380)
        layout = self.bodyLayout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        self._label = QLabel(label)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)
        self._edit = QLineEdit(text)
        self._edit.selectAll()
        layout.addWidget(self._edit)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        ok = QPushButton("确定")
        ok.setProperty("primary", True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        button_row.addWidget(ok)
        button_row.addWidget(cancel)
        layout.addLayout(button_row)

    def textValue(self) -> str:
        return self._edit.text()

    @staticmethod
    def getText(
        parent: QWidget | None, title: str, label: str, text: str = ""
    ) -> tuple[str, bool]:
        """返回 (文本, 是否确认)，签名与 QInputDialog.getText 一致。"""
        dialog = FramelessInputDialog(parent, title, label, text)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.textValue(), accepted
