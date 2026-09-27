"""主题与全局样式表（计划 §7.4）。

思路照搬 Quotor：一套 ThemeColors 调色板 + 由调色板生成整份 QSS + ThemeManager 单例，
切换主题时重新生成并 setStyleSheet，同时发出 theme_changed 供自绘控件重绘。

QSS 用 string.Template（$token）而不是 f-string：样式表里 {} 太多，
f-string 需要把每个大括号都转义成 {{}}，极易出错。
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Template

from PySide6.QtCore import QObject, Signal

from app.core.paths import ensure_app_data_dir


@dataclass(frozen=True)
class ThemeColors:
    name: str
    primary: str
    primary_hover: str
    primary_pressed: str
    primary_soft: str
    bg_window: str
    bg_card: str
    bg_input: str
    bg_hover: str
    bg_pressed: str
    bg_dialog: str
    item_hover: str
    text_primary: str
    text_secondary: str
    text_disabled: str
    text_inverse: str
    border: str
    border_strong: str
    border_focus: str
    success: str
    warning: str
    danger: str
    danger_hover: str
    table_alt_row: str
    table_grid: str
    table_selected_bg: str
    scrollbar_handle: str
    scrollbar_handle_hover: str
    font_family: str
    font_family_mono: str


_CJK_FONTS = '"Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif'
_MONO_FONTS = '"JetBrains Mono", "Cascadia Mono", Consolas, monospace'

LIGHT = ThemeColors(
    name="light",
    primary="#3B82F6",
    primary_hover="#2563EB",
    primary_pressed="#1D4ED8",
    primary_soft="#EFF6FF",
    bg_window="#F7F8FA",
    bg_card="#FFFFFF",
    bg_input="#FFFFFF",
    bg_hover="#F1F5F9",
    bg_pressed="#E2E8F0",
    bg_dialog="#FFFFFF",
    item_hover="#DCE8FB",
    text_primary="#0F172A",
    text_secondary="#64748B",
    text_disabled="#94A3B8",
    text_inverse="#FFFFFF",
    border="#E5E7EB",
    border_strong="#D1D5DB",
    border_focus="#3B82F6",
    success="#10B981",
    warning="#F59E0B",
    danger="#EF4444",
    danger_hover="#DC2626",
    table_alt_row="#F2F4F7",
    table_grid="#D1D5DB",
    table_selected_bg="#B4D6FF",
    scrollbar_handle="#CBD5E1",
    scrollbar_handle_hover="#94A3B8",
    font_family=_CJK_FONTS,
    font_family_mono=_MONO_FONTS,
)

DARK = ThemeColors(
    name="dark",
    primary="#60A5FA",
    primary_hover="#93C5FD",
    primary_pressed="#3B82F6",
    primary_soft="#2F3B4D",
    bg_window="#383838",
    bg_card="#3D3D3D",
    bg_input="#424242",
    bg_hover="#454545",
    bg_pressed="#4D4D4D",
    bg_dialog="#3D3D3D",
    item_hover="#2D5A8A",
    text_primary="#F0F0F0",
    text_secondary="#C0C0C0",
    text_disabled="#7A7A7A",
    text_inverse="#0F172A",
    border="#4A4A4A",
    border_strong="#5A5A5A",
    border_focus="#60A5FA",
    success="#34D399",
    warning="#FBBF24",
    danger="#F87171",
    danger_hover="#EF4444",
    table_alt_row="#383838",
    table_grid="#4A4A4A",
    table_selected_bg="#345E8C",
    scrollbar_handle="#5A5A5A",
    scrollbar_handle_hover="#6A6A6A",
    font_family=_CJK_FONTS,
    font_family_mono=_MONO_FONTS,
)


def _write_svg(name: str, color: str, body: str) -> str:
    """把随主题变色的极简 SVG 写到用户数据目录并返回 QSS 可用的路径。

    组合框箭头、复选框对勾用 QSS 的 border 画在高分屏上会变成小圆点，
    所以照 Quotor 的做法落成 svg 文件。
    """
    path = ensure_app_data_dir() / f"section2-{name}-{color.lstrip('#')}.svg"
    if not path.exists():
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
            'fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" '
            'stroke-linejoin="round">{body}</svg>'.format(color=color, body=body),
            encoding="utf-8",
        )
    return path.as_posix()


_QSS = Template(
    """
/* ===================== 全局 ===================== */
* {
    font-family: $font_family;
    font-size: 13px;
    color: $text_primary;
    outline: none;
}
QWidget { background-color: $bg_window; }
QMainWindow, QDialog { background-color: $bg_window; }
QWidget[role="panel"] { background-color: $bg_card; }
QWidget[role="card"], QFrame[role="card"] {
    background-color: $bg_card;
    border: 1px solid $border;
    border-radius: 8px;
}
QWidget[role="toolbar-strip"] {
    background-color: $bg_card;
    border-bottom: 1px solid $border;
}
QLabel { background: transparent; }
QLabel[role="panel-title"] { font-size: 13px; font-weight: 600; color: $text_primary; }
QLabel[role="title"] { font-size: 15px; font-weight: 600; }
QLabel[role="hint"] { color: $text_secondary; }
QLabel[role="error"] { color: $danger; }
QLabel[role="mono"] { font-family: $font_family_mono; }
QLabel[role="placeholder"] { color: $text_disabled; font-size: 14px; }
QLabel[role="badge"] {
    background-color: $primary_soft;
    color: $primary;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 12px;
}

/* ===================== 菜单栏 / 菜单 ===================== */
QMenuBar {
    background-color: $bg_card;
    border-bottom: 1px solid $border;
    padding: 2px 4px;
}
QMenuBar#TitleBarMenuBar { background: transparent; border: none; padding: 0; }
QMenuBar#TitleBarMenuBar::item { padding: 5px 10px; background: transparent; border-radius: 6px; }
QFrame#FramelessTitleBar {
    background-color: $bg_card;
    border-bottom: 1px solid $border;
}
QLabel#TitleBarIcon { color: $primary; font-weight: 700; font-size: 15px; background: transparent; }
QToolButton#WindowBtn {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
}
QToolButton#WindowBtn:hover { background-color: $bg_hover; }
QToolButton#WindowBtn:pressed { background-color: $bg_pressed; }
QToolButton#WindowBtn[kind="close"]:hover { background-color: $danger; }
QMenuBar::item { padding: 5px 10px; background: transparent; border-radius: 6px; }
QMenuBar::item:selected { background-color: $bg_hover; }
QMenuBar::item:pressed { background-color: $bg_pressed; }
QMenu {
    background-color: $bg_card;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item { padding: 6px 28px 6px 16px; border-radius: 6px; }
QMenu::item:selected { background-color: $item_hover; }
QMenu::item:disabled { color: $text_disabled; }
QMenu::separator { height: 1px; background-color: $border; margin: 4px 8px; }

/* ===================== 工具栏 ===================== */
QToolBar {
    background-color: $bg_card;
    border-bottom: 1px solid $border;
    padding: 4px 6px;
    spacing: 4px;
}
QToolBar::separator { width: 1px; background-color: $border; margin: 4px 6px; }
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 10px;
    color: $text_primary;
}
QToolButton:hover { background-color: $bg_hover; }
QToolButton:pressed { background-color: $bg_pressed; }
QToolButton:disabled { color: $text_disabled; }
QToolButton[role="icon-btn"] { padding: 4px 6px; }
QToolButton[role="toggle-bar"] {
    background-color: $bg_window;
    border: 1px solid $border;
    border-radius: 4px;
    padding: 0;
}
QToolButton[role="toggle-bar"]:hover { background-color: $primary_soft; }

/* ===================== 状态栏 ===================== */
QStatusBar {
    background-color: $bg_card;
    border-top: 1px solid $border;
    color: $text_secondary;
}
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $text_secondary; }

/* ===================== 分隔条 ===================== */
QSplitter::handle { background-color: $border; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
QSplitter::handle:hover { background-color: $border_focus; }

/* ===================== 输入控件 ===================== */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit, QPlainTextEdit, QTextEdit, QTextBrowser {
    background-color: $bg_input;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: $primary;
    selection-color: $text_inverse;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover, QPlainTextEdit:hover, QTextEdit:hover {
    border-color: $border_strong;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QDateEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border-color: $border_focus;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled,
QPlainTextEdit:disabled, QTextEdit:disabled {
    background-color: $bg_hover;
    color: $text_disabled;
}
QLineEdit[invalid="true"], QComboBox[invalid="true"] { border-color: $warning; }
QComboBox::drop-down { width: 22px; border: none; background: transparent; }
QComboBox::down-arrow { image: url($combo_arrow); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background-color: $bg_card;
    border: 1px solid $border;
    border-radius: 6px;
    selection-background-color: $item_hover;
    selection-color: $text_primary;
    padding: 4px;
}

/* ===================== 按钮 ===================== */
QPushButton {
    background-color: $bg_card;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 5px 14px;
    color: $text_primary;
}
QPushButton:hover { background-color: $bg_hover; }
QPushButton:pressed { background-color: $bg_pressed; }
QPushButton:disabled { color: $text_disabled; border-color: $border; background-color: $bg_hover; }
QPushButton[primary="true"] {
    background-color: $primary;
    border-color: $primary;
    color: $text_inverse;
    font-weight: 600;
}
QPushButton[primary="true"]:hover { background-color: $primary_hover; border-color: $primary_hover; }
QPushButton[primary="true"]:pressed { background-color: $primary_pressed; border-color: $primary_pressed; }
QPushButton[danger="true"] { color: $danger; border-color: $danger; background-color: transparent; }
QPushButton[danger="true"]:hover { background-color: $danger; color: $text_inverse; }
QPushButton[flat="true"] { border-color: transparent; background: transparent; }
QPushButton[flat="true"]:hover { background-color: $bg_hover; }

/* ===================== 勾选 ===================== */
QCheckBox, QRadioButton { background: transparent; spacing: 6px; }
QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px; }
QCheckBox::indicator {
    background-color: $bg_input;
    border: 1px solid $border_strong;
    border-radius: 4px;
}
QCheckBox::indicator:checked {
    background-color: $primary;
    border-color: $primary;
    image: url($check_mark);
}
QCheckBox::indicator:disabled { background-color: $bg_hover; border-color: $border; }
QRadioButton::indicator { border: 1px solid $border_strong; border-radius: 8px; background-color: $bg_input; }
QRadioButton::indicator:checked { background-color: $primary; border-color: $primary; }

/* ===================== 分组框 ===================== */
QGroupBox {
    background-color: transparent;
    border: 1px solid $border;
    border-radius: 8px;
    margin-top: 10px;
    padding: 10px 10px 8px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: $text_secondary;
    font-weight: 600;
}

/* ===================== 标签页 ===================== */
QTabWidget::pane {
    background-color: $bg_card;
    border: 1px solid $border;
    border-radius: 8px;
    top: -1px;
}
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent;
    border: 1px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 14px;
    margin-right: 2px;
    color: $text_secondary;
}
QTabBar::tab:hover { background-color: $bg_hover; color: $text_primary; }
QTabBar::tab:selected {
    background-color: $bg_card;
    border-color: $border;
    border-bottom-color: $bg_card;
    color: $primary;
    font-weight: 600;
}

/* ===================== 树 ===================== */
QTreeWidget, QTreeView {
    background-color: $bg_card;
    border: none;
    show-decoration-selected: 1;
}
QTreeView::item { padding: 5px 4px; border-radius: 4px; color: $text_primary; }
QTreeView::item:hover { background-color: $item_hover; }
QTreeView::item:selected { background-color: $table_selected_bg; color: $text_primary; }
QTreeView::item:selected:active { background-color: $table_selected_bg; }
QTreeView::item:disabled { color: $text_disabled; }

/* ===================== 表格 ===================== */
QTableWidget, QTableView {
    background-color: $bg_card;
    alternate-background-color: $table_alt_row;
    border: none;
    gridline-color: $table_grid;
    selection-background-color: $table_selected_bg;
    selection-color: $text_primary;
}
QTableWidget::item, QTableView::item { padding: 3px 6px; }
QTableWidget::item:selected, QTableView::item:selected {
    background-color: $table_selected_bg;
    color: $text_primary;
}
QHeaderView { background-color: $bg_card; }
QHeaderView::section {
    background-color: $bg_card;
    color: $text_secondary;
    font-weight: 600;
    border: none;
    border-right: 1px solid $border;
    border-bottom: 1px solid $border;
    padding: 6px 6px;
}
QHeaderView::section:last { border-right: none; }
QHeaderView::section:hover { background-color: $bg_hover; }
QTableCornerButton::section { background-color: $bg_card; border: none; }

/* ===================== 列表 ===================== */
QListView {
    background-color: $bg_card;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px;
}
QListView::item { padding: 5px 6px; border-radius: 4px; }
QListView::item:hover { background-color: $item_hover; }
QListView::item:selected { background-color: $table_selected_bg; color: $text_primary; }

/* ===================== 滚动条 ===================== */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical {
    background-color: $scrollbar_handle;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background-color: $scrollbar_handle_hover; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background-color: $scrollbar_handle;
    border-radius: 4px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover { background-color: $scrollbar_handle_hover; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; background: none; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

/* ===================== 提示 / 分隔线 ===================== */
QToolTip {
    background-color: $bg_card;
    color: $text_primary;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 5px 8px;
}
QFrame[role="hline"] { background-color: $border; max-height: 1px; border: none; }
QMessageBox { background-color: $bg_dialog; }
QMessageBox QLabel { color: $text_primary; }
QDialog QWidget { background-color: transparent; }
QDialog QMenu { background-color: $bg_card; }
QDialog QComboBox QAbstractItemView { background-color: $bg_card; }
"""
)


def build_stylesheet(colors: ThemeColors) -> str:
    """由调色板生成整份 QSS。"""
    combo_arrow = _write_svg(
        "combo-arrow", colors.text_secondary, '<path d="m6 9 6 6 6-6" />'
    )
    check_mark = _write_svg(
        "check-mark", colors.text_inverse, '<path d="m5 12 5 5 9-10" />'
    )
    return _QSS.substitute(
        **{field: getattr(colors, field) for field in colors.__dataclass_fields__},
        combo_arrow=combo_arrow,
        check_mark=check_mark,
    )


class ThemeManager(QObject):
    """全局主题单例：apply / toggle 后所有窗口立即换肤。"""

    _instance: "ThemeManager | None" = None

    theme_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._colors: ThemeColors = LIGHT
        self._applied = False

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def current(self) -> ThemeColors:
        return self._colors

    def is_dark(self) -> bool:
        return self._colors.name == "dark"

    def apply(self, app, theme_name: str) -> None:
        colors = DARK if theme_name == "dark" else LIGHT
        if colors is self._colors and self._applied:
            return
        self._colors = colors
        app.setStyleSheet(build_stylesheet(colors))
        self._applied = True
        self.theme_changed.emit(colors.name)

    def toggle(self, app) -> str:
        name = "dark" if self._colors.name == "light" else "light"
        self.apply(app, name)
        return name


def apply_initial_theme(app) -> None:
    """启动时按 config.toml 里的 ui.theme 上色。"""
    from app.core.config import get_config

    ThemeManager.instance().apply(app, get_config().ui_theme)
