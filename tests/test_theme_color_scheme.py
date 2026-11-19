"""主题切换时同步原生 color scheme 的回归锁定。

背景：Windows 11 的 windows11 样式绘制标准按钮时读 QStyleHints.colorScheme()
（系统深/浅色），不读应用 QPalette。alpha.3 把按钮改回原生样式后只同步了
QPalette，软件主题与系统主题不一致时按钮会按系统主题上色——最深色的例子是
“深色系统 + 浅色软件”时浅色文字画在浅色原生按钮上，按钮整个看不见。
ThemeManager.apply 必须把 color scheme 一并覆盖成应用主题。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from app.resources.qss import theme

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeHints:
    """只记录 setColorScheme 调用的 QStyleHints 替身。"""

    def __init__(self) -> None:
        self.requested: list[Qt.ColorScheme] = []

    def setColorScheme(self, scheme: Qt.ColorScheme) -> None:  # noqa: N802 - Qt 命名
        self.requested.append(scheme)


class _FakeApp:
    """记录调用顺序的最小 QApplication 替身。"""

    def __init__(self, calls: list[str] | None = None) -> None:
        self.calls = calls if calls is not None else []

    def setPalette(self, palette) -> None:  # noqa: N802 - Qt 命名
        self.calls.append("palette")

    def setStyleSheet(self, sheet: str) -> None:  # noqa: N802 - Qt 命名
        self.calls.append("stylesheet")


def test_sync_color_scheme_requests_app_theme() -> None:
    """深色主题请求 Dark、浅色主题请求 Light。"""
    hints = _FakeHints()
    theme._sync_color_scheme(theme.DARK, hints)
    theme._sync_color_scheme(theme.LIGHT, hints)
    assert hints.requested == [Qt.ColorScheme.Dark, Qt.ColorScheme.Light]


def test_sync_color_scheme_tolerates_qt_without_api() -> None:
    """Qt < 6.8 没有 setColorScheme：静默跳过，不能打断启动。"""

    class _OldHints:
        pass

    theme._sync_color_scheme(theme.DARK, _OldHints())


@pytest.mark.parametrize("theme_colors", [theme.LIGHT, theme.DARK])
def test_stylesheet_has_no_generic_button_rule(theme_colors) -> None:
    """标准按钮由 ButtonStyle 自绘：QSS 里不能有通用 QPushButton 规则。

    一旦写了 ``QPushButton { background... }``，Qt 会改走 QStyleSheetStyle，
    ButtonStyle 的 drawControl 就接管不到（回归会表现为按钮外观退回原生）。
    """
    sheet = theme.build_stylesheet(theme_colors)
    assert "QPushButton {" not in sheet
    assert "QPushButton:default" not in sheet
    # 功能性按钮的专属规则仍然保留（它们本来就是 QSS 自绘）
    assert 'QPushButton[role="icon-btn"]' in sheet
    assert 'QPushButton[role="segment-btn"]' in sheet
    assert "QPushButton#aiSendBtn" in sheet


def test_theme_manager_syncs_color_scheme_before_palette(monkeypatch) -> None:
    """apply 先同步 color scheme、再 apply 调色板与 QSS。"""
    order: list[str] = []
    monkeypatch.setattr(
        theme, "_sync_color_scheme", lambda colors: order.append(f"scheme:{colors.name}")
    )
    app = _FakeApp(order)
    manager = theme.ThemeManager()
    manager.theme_changed.connect(lambda name: order.append(f"signal:{name}"))

    manager.apply(app, "dark")
    assert order[:4] == ["scheme:dark", "palette", "stylesheet", "signal:dark"]
    assert manager.is_dark()

    order.clear()
    manager.apply(app, "light")
    assert order[:4] == ["scheme:light", "palette", "stylesheet", "signal:light"]
    assert not manager.is_dark()
