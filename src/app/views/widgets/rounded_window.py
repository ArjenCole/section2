"""Windows 无边框窗体的自绘圆角（不依赖 Win11 DWM，Win10/11 外观一致）。

做法：窗体开 ``WA_TranslucentBackground``，再用 ``setMask`` 把整窗裁成圆角
区域，窗口系统级裁剪对标题栏、内容区等所有子控件生效——不要求每个子控件
自己画圆角。mask 边缘是锯齿的，所以再放一个置顶、鼠标穿透的 overlay 子控
件沿同一条圆角路径用抗锯齿画 1px 边框圈，盖住锯齿、同时充当窗体描边
（对应 Win11 DWM 在系统圆角下附带的 1px 轮廓）。最大化时退化为直角并与
系统行为一致，还原时自动恢复。

顶层窗体命中的全局 QSS 背景（``QWidget/QMainWindow/QDialog`` 规则）会把
整个矩形填成实心、盖掉透明圆角，助手用窗体级样式表 + ID 选择器精确关掉。
macOS 走原生红绿灯窗口（见 mac_window.py），不要装这个助手。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import QMainWindow, QWidget

#: 圆角半径（逻辑像素），与 QSS 卡片的 border-radius: 8px 一致
_RADIUS = 8


def _rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


class _RingWidget(QWidget):
    """置顶 overlay：只画 1px 抗锯齿圆角边框圈，鼠标穿透。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # 全局 QSS 的 QWidget 背景规则会把它填成实心盖住窗口，这里关掉
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        from app.resources.qss.theme import ThemeManager

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(ThemeManager.instance().current().border), 1))
        painter.drawPath(
            _rounded_path(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), _RADIUS)
        )


class RoundedWindowHelper(QObject):
    """给无边框顶层窗体装上自绘圆角，随窗体销毁自动清理。"""

    @classmethod
    def install(cls, window: QWidget) -> "RoundedWindowHelper":
        return cls(window)

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._ring = _RingWidget(window)

        window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if not window.objectName():
            window.setObjectName("RoundedWindowRoot")
        base = "QMainWindow" if isinstance(window, QMainWindow) else "QDialog"
        window.setStyleSheet(f"{base}#{window.objectName()} {{ background: transparent; }}")

        window.installEventFilter(self)
        from app.resources.qss.theme import ThemeManager

        # 主题切换时边框圈跟着换色（receiver 绑定 ring，窗体销毁自动断开）
        ThemeManager.instance().theme_changed.connect(self._ring.update)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt 命名
        if obj is self._window and event.type() in (
            QEvent.Type.Show,
            QEvent.Type.Resize,
            # 最大化/还原即使尺寸不变（离屏平台）也要退直角/恢复圆角
            QEvent.Type.WindowStateChange,
        ):
            self._apply()
        return False

    def _apply(self) -> None:
        window = self._window
        ring = self._ring
        if window.isMaximized():
            window.clearMask()
            ring.hide()
            return
        ring.setGeometry(window.rect())
        ring.show()
        ring.raise_()
        window.setMask(QRegion(_rounded_path(QRectF(window.rect()), _RADIUS)
                               .toFillPolygon().toPolygon()))
        ring.update()
