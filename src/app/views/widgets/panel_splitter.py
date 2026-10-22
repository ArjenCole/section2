"""AI 面板左侧的展开/收起竖条与可悬停高亮的分割手柄（视觉对齐 Quotor）。

两个控件的分工照搬 Quotor：

- ``LineSplitterHandle``：拖拽改宽度的分割手柄。抓取区加宽（由 splitter 的
  handleWidth 决定），但只画居中 1px 竖线；鼠标进入或正在拖拽时，线由
  ``border`` 变成强调色 ``border_focus``。1px 的手柄虽然画得出线，鼠标却
  几乎落不上去，纯 QSS 的 ``::handle:hover`` 高亮实际永远看不到。
- ``DragToggleBar``：14px 竖条，透明底 + 居中 chevron 箭头。悬停时整条铺
  ``bg_hover``、箭头由 ``text_secondary`` 提亮到 ``text_primary``，按下铺
  ``bg_pressed``。全部自绘（QSS 的 color 管不到画笔/图标）。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QPushButton,
    QSizePolicy,
    QSplitter,
    QSplitterHandle,
    QWidget,
)

from app.resources.qss.theme import ThemeManager

#: 展开/收起竖条宽度（与 Quotor DragToggleBar 一致）
TOGGLE_BAR_WIDTH = 14

#: 分割手柄的抓取区宽度（线仍只画 1px，居中）
SPLITTER_HANDLE_WIDTH = 6

#: 与主窗体底部圆角一致（theme.py 的 border-bottom-right-radius）
_CORNER_RADIUS = 8


class LineSplitterHandle(QSplitterHandle):
    """只画 1px 线的分割手柄；悬停/拖拽时线变强调色。"""

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self._hovered = False
        self._dragging = False
        if orientation == Qt.Orientation.Horizontal:
            self.setCursor(Qt.CursorShape.SplitHCursor)
        else:
            self.setCursor(Qt.CursorShape.SplitVCursor)
        # 全局 QSS 的 QSplitter::handle 会把整个抓取区刷成边框色（对 1px 手柄
        # 正好是那条线，加宽到 6px 后就成了 6px 实心条）。这里用控件级样式
        # 让出背景，线只由 paintEvent 画；不依赖某个 objectName 的 QSS 例外规则。
        self.setStyleSheet("background: transparent;")
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ 状态
    def _active(self) -> bool:
        """悬停中，或正在被拖动（拖动时鼠标可能已经移出手柄）。"""
        return self._hovered or self._dragging

    def _on_theme_changed(self, _name: str) -> None:
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._dragging = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._dragging = False
        self.update()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt 命名
        colors = ThemeManager.instance().current()
        color = QColor(colors.border_focus if self._active() else colors.border)
        painter = QPainter(self)
        # 线是 1px 的整数矩形，关抗锯齿才不会糊成 2px 灰带
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self.orientation() == Qt.Orientation.Horizontal:
            x = (self.width() - 1) // 2
            painter.fillRect(x, 0, 1, self.height(), color)
        else:
            y = (self.height() - 1) // 2
            painter.fillRect(0, y, self.width(), 1, color)


class LineSplitter(QSplitter):
    """手柄换成自绘 1px 线的 QSplitter。"""

    def createHandle(self) -> QSplitterHandle:  # noqa: N802 - Qt 命名
        return LineSplitterHandle(self.orientation(), self)


class DragToggleBar(QPushButton):
    """细长条展开/收起按钮（仅点击切换，不支持拖拽）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded = False
        self._hovered = False
        self.setProperty("role", "toggle-bar")
        self.setFixedWidth(TOGGLE_BAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 键盘焦点交给输入框，竖条不参与 Tab
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # 底色由 paintEvent 自绘：控件级透明保证任何主题/任何父容器下都不带
        # QPushButton 的默认底（不依赖全局 QSS 是否已应用）
        self.setStyleSheet("background: transparent;")
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ 状态
    def set_expanded(self, expanded: bool) -> None:
        """刷新箭头方向：展开时 ›（点它收起），收起时 ‹（点它展开）。"""
        self._expanded = expanded
        self.update()

    def _on_theme_changed(self, _name: str) -> None:
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt 命名
        colors = ThemeManager.instance().current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._hovered or self.isDown():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(
                QColor(colors.bg_pressed if self.isDown() else colors.bg_hover)
            )
            painter.drawPath(self._background_path())

        pen = QPen(
            QColor(colors.text_primary if self._hovered else colors.text_secondary),
            1.4,
        )
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._chevron_path())

    def _background_path(self) -> QPainterPath:
        """悬停底色：展开时铺满竖条；收起时竖条贴在窗体右下角，跟着倒圆。"""
        rect = QRectF(self.rect())
        path = QPainterPath()
        window = self.window()
        if self._expanded or (window is not None and window.isMaximized()):
            # 展开时位于中间，最大化时窗体本身没有圆角，都按方角铺满
            path.addRect(rect)
            return path
        r = float(_CORNER_RADIUS)
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.right(), rect.bottom() - r)
        path.quadTo(rect.right(), rect.bottom(), rect.right() - r, rect.bottom())
        path.lineTo(rect.left(), rect.bottom())
        path.closeSubpath()
        return path

    def _chevron_path(self) -> QPainterPath:
        """居中的 chevron 折线（› / ‹），尺寸对齐 Quotor 的 10px 图标。"""
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        half_w = 2.0
        half_h = 4.0
        path = QPainterPath()
        if self._expanded:
            path.moveTo(cx - half_w, cy - half_h)
            path.lineTo(cx + half_w, cy)
            path.lineTo(cx - half_w, cy + half_h)
        else:
            path.moveTo(cx + half_w, cy - half_h)
            path.lineTo(cx - half_w, cy)
            path.lineTo(cx + half_w, cy + half_h)
        return path
