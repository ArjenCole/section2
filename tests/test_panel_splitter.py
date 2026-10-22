"""AI 面板左侧的竖条与分割手柄：宽度、悬停高亮、箭头方向、折叠联动。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from app.resources.qss.theme import ThemeManager
from app.views.widgets.panel_splitter import (
    SPLITTER_HANDLE_WIDTH,
    TOGGLE_BAR_WIDTH,
    DragToggleBar,
    LineSplitter,
    LineSplitterHandle,
)


def _same(color: QColor, hex_value: str) -> bool:
    """比较颜色：ThemeColors 里的十六进制是大写，QColor.name() 返回小写。"""
    return QColor(color).name().lower() == hex_value.lower()


def _painted_columns(handle: LineSplitterHandle) -> list[int]:
    """手柄中部那一行里画了东西的列（背景透明，只有线有像素）。"""
    image = handle.grab().toImage()
    y = handle.height() // 2
    return [
        x for x in range(handle.width()) if image.pixelColor(x, y).alpha() > 0
    ]


def _darkest(image, center: QPoint, radius: int = 2) -> QColor:
    """取中心附近最暗的不透明像素（箭头是细线，直接取单点会落在空隙里）。"""
    best: QColor | None = None
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            color = image.pixelColor(center.x() + dx, center.y() + dy)
            if color.alpha() == 0:  # 平日的透明底不算
                continue
            if best is None or color.lightness() < best.lightness():
                best = color
    return best if best is not None else image.pixelColor(center)


@pytest.fixture()
def splitter(qapp):
    splitter = LineSplitter(Qt.Orientation.Horizontal)
    splitter.setHandleWidth(SPLITTER_HANDLE_WIDTH)
    for _ in range(2):
        splitter.addWidget(QWidget())
    splitter.resize(400, 120)
    splitter.show()
    yield splitter
    splitter.close()
    splitter.deleteLater()


def test_handle_is_custom_and_draws_single_line(splitter):
    """手柄用自绘类，抓取区加宽到 6px，但仍只画 1px 线。"""
    handle = splitter.handle(1)
    assert isinstance(handle, LineSplitterHandle)
    assert handle.width() == SPLITTER_HANDLE_WIDTH

    handle._hovered = False
    handle._dragging = False
    assert _painted_columns(handle) == [(handle.width() - 1) // 2]


def test_handle_line_highlights_on_hover(splitter):
    """鼠标进入手柄：线由边框色变成强调色（拖拽中同样保持高亮）。"""
    handle = splitter.handle(1)
    colors = ThemeManager.instance().current()
    line_x = (handle.width() - 1) // 2
    y = handle.height() // 2

    def line_color() -> str:
        return QColor(handle.grab().toImage().pixelColor(line_x, y)).name()

    handle._hovered = False
    handle._dragging = False
    assert _same(line_color(), colors.border)

    handle._hovered = True
    assert _same(line_color(), colors.border_focus)

    # 拖到一半鼠标可能已经移出手柄，此时仍要保持高亮
    handle._hovered = False
    handle._dragging = True
    assert _same(line_color(), colors.border_focus)


def test_toggle_bar_background_and_arrow_follow_hover(qapp):
    """竖条平时透明（只有箭头），悬停时整条铺 bg_hover、箭头提亮。"""
    bar = DragToggleBar()
    bar.resize(TOGGLE_BAR_WIDTH, 120)
    bar.show()
    try:
        colors = ThemeManager.instance().current()
        edge = QPoint(1, 4)  # 竖条边缘，远离居中箭头
        arrow = QPoint(bar.width() // 2 + 2, bar.height() // 2)  # 展开态箭头顶点

        idle = bar.grab().toImage()
        assert not _same(idle.pixelColor(edge), colors.bg_hover)
        idle_arrow = _darkest(idle, arrow)

        bar._hovered = True
        hovered = bar.grab().toImage()
        assert _same(hovered.pixelColor(edge), colors.bg_hover)
        # 箭头颜色由 text_secondary 提亮到 text_primary：最暗像素更暗
        assert _darkest(hovered, arrow).lightness() < idle_arrow.lightness()
    finally:
        bar.close()
        bar.deleteLater()


def test_toggle_bar_chevron_direction(qapp):
    """展开时箭头 ›（点它收起），收起时箭头 ‹。"""
    bar = DragToggleBar()
    bar.resize(TOGGLE_BAR_WIDTH, 120)

    bar.set_expanded(True)
    expanded_path = bar._chevron_path()
    bar.set_expanded(False)
    collapsed_path = bar._chevron_path()

    cx = bar.width() / 2
    # 展开：起点在中心左侧（向右张开）；收起：起点在中心右侧
    assert expanded_path.elementAt(0).x < cx
    assert collapsed_path.elementAt(0).x > cx


def test_toggle_click_collapses_ai_panel(qapp):
    """点竖条切换 AI 面板：收起后容器只剩竖条宽度，再点恢复原宽度。"""
    from app.views.main_window import MainWindow

    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    try:
        window._apply_ai_visible(True, initial=True)
        qapp.processEvents()
        expanded_width = window._ai_panel.width()
        assert expanded_width > 300

        window._ai_toggle.click()
        qapp.processEvents()
        assert not window._ai_panel.isVisible()
        assert window._splitter.sizes()[2] == TOGGLE_BAR_WIDTH

        window._ai_toggle.click()
        qapp.processEvents()
        assert window._ai_panel.isVisible()
        assert window._ai_panel.width() == expanded_width
    finally:
        window.close()
