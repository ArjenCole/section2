"""Windows 无边框窗体的自绘圆角与外阴影（不依赖 Win11 DWM，Win10/11 外观一致）。

圆角：窗体开 ``WA_TranslucentBackground`` 且自身不画背景，圆角轮廓由贴角的
子控件用 QSS ``border-radius`` 自绘（见 theme.py：标题栏上两角、对话框 body
与内嵌 QWizard 的下两角、主窗体状态栏下两角）。QSS 背景走 QPainter 抗锯齿
填充，边缘平滑；四条直边与窗体矩形重合，天然无锯齿。曾经用过的 ``setMask``
方案是 1-bit 系统级裁剪，边缘锯齿明显，已移除。置顶的 overlay 子控件沿同一
条轮廓用抗锯齿画 1px 描边圈，充当窗体描边（对应 Win11 DWM 在系统圆角下附带
的 1px 轮廓）。最大化时通过窗体级样式表把贴角子控件的圆角压平（与系统行为
一致），还原时自动恢复。

外阴影：一个透明的 Tool 影子窗口（:class:`_ShadowWindow`）贴在宿主窗体正
后方，随宿主显示/移动/缩放同步，沿圆角路径画多圈渐隐的黑色描边模拟投影。
不改动宿主内容几何，主窗体与弹窗通用；宿主最大化/最小化/隐藏时影子同步
隐藏。影子窗口开启输入穿透，不挡鼠标也不抢焦点。

顶层窗体命中的全局 QSS 背景（``QWidget/QMainWindow/QDialog`` 规则）会把
整个矩形填成实心、露出方角，助手用窗体级样式表 + ID 选择器精确关掉。
macOS 走原生红绿灯窗口（见 mac_window.py），不要装这个助手。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QMainWindow, QMenu, QWidget

#: 圆角半径（逻辑像素），与 theme.py 里贴角子控件的 border-radius 一致
_RADIUS = 8

#: 阴影向外扩散的距离（逻辑像素）
_SHADOW_MARGIN = 20

#: 阴影最深处（贴着窗体边缘）的不透明度
_SHADOW_ALPHA = 60

#: 最大化时压平贴角子控件圆角的窗体级样式表片段（widget 级样式表优先于
#: 全局 QSS，同选择器下直接覆盖）
_SQUARE_CORNERS_SHEET = (
    "QFrame#FramelessTitleBar, QDialog #FramelessDialogBody, QWizard, QStatusBar "
    "{ border-radius: 0px; }"
)

_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010


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


class _ShadowWindow(QWidget):
    """影子窗口：贴在宿主正后方的透明 Tool 窗口，只画一圈渐隐投影。

    - 输入穿透（WA_TransparentForMouseEvents），不挡鼠标、不抢焦点；
    - 阴影按尺寸缓存成位图，仅在尺寸/分辨率变化时重绘；
    - macOS 之外的平台用 SetWindowPos 把自己插到宿主 HWND 正后方，
      避免宿主被其他窗口抬起后影子浮到上面去。
    """

    def __init__(self, host: QWidget) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._host = host
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._cache_key: tuple[int, int, float] | None = None
        self._cache: QPixmap | None = None

    # ------------------------------------------------------------- 几何同步
    def sync(self) -> None:
        host = self._host
        if not host.isVisible() or host.isMinimized() or host.isMaximized():
            if self.isVisible():
                self.hide()
            return
        m = _SHADOW_MARGIN
        target = host.frameGeometry().adjusted(-m, -m, m, m)
        if self.geometry() != target:
            self.setGeometry(target)
        if not self.isVisible():
            self.show()

    def restack(self) -> None:
        """把自己插到宿主 HWND 正后方（仅 Windows）。"""
        if sys.platform != "win32" or not self.isVisible():
            return
        try:
            import ctypes

            ctypes.windll.user32.SetWindowPos(
                int(self.winId()), int(self._host.winId()), 0, 0, 0, 0,
                _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE,
            )
        except Exception:  # noqa: BLE001 - 离屏/无句柄时静默跳过
            pass

    # ------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr)
        if self._cache_key != key or self._cache is None:
            self._render(dpr)
            self._cache_key = key
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)

    def _render(self, dpr: float) -> None:
        w, h, m = self.width(), self.height(), _SHADOW_MARGIN
        # 影子窗口本身就是宿主 + 四周各 m 的留白，画布即窗口大小；
        # 宿主轮廓在本窗口坐标系里是四周缩进 m 的圆角矩形
        pixmap = QPixmap(max(1, round(w * dpr)), max(1, round(h * dpr)))
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(dpr)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 从宿主轮廓开始一圈圈向外描，透明度按距离二次衰减，叠加成
        # “贴边最深、向外渐隐”的外阴影；半径随外扩同步变大（圆角矩形
        # 外偏的几何性质）。描边圈的内半幅压在宿主底下，不可见也无害。
        host = QRectF(m, m, w - 2.0 * m, h - 2.0 * m)
        for i in range(m):
            t = i / m
            alpha = int(_SHADOW_ALPHA * (1.0 - t) ** 2)
            if alpha <= 0:
                continue
            painter.setPen(QPen(QColor(0, 0, 0, alpha), 1.5))
            painter.drawPath(
                _rounded_path(host.adjusted(-i - 0.5, -i - 0.5, i + 0.5, i + 0.5),
                              _RADIUS + i)
            )
        painter.end()
        self._cache = pixmap


class _MenuRounding(QObject):
    """QMenu 圆角修整：Win10 的弹出菜单是不透明矩形窗口，QSS 画的圆角外面
    会露出调色板底色的方角，左下角再叠上系统菜单阴影最扎眼。在菜单首次
    polish（尚无原生窗口）时开透明背景 + 无边框，并关掉系统方角阴影，
    让 QSS 的 border-radius 成为真实的窗口轮廓。"""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt 命名
        if (
            isinstance(obj, QMenu)
            and event.type() == QEvent.Type.Polish
            and not obj.isVisible()
        ):
            apply_menu_rounding(obj)
        return False


def apply_menu_rounding(menu: QMenu) -> None:
    menu.setWindowFlags(
        menu.windowFlags()
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.NoDropShadowWindowHint
    )
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def install_menu_rounding(app) -> None:
    """给整个应用的所有 QMenu（菜单栏下拉、各级子菜单、右键菜单）套圆角修整。"""
    app.installEventFilter(_MenuRounding(app))


class RoundedWindowHelper(QObject):
    """给无边框顶层窗体装上自绘圆角与外阴影，随窗体销毁自动清理。"""

    @classmethod
    def install(cls, window: QWidget) -> "RoundedWindowHelper":
        return cls(window)

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._ring = _RingWidget(window)
        self._shadow = _ShadowWindow(window)
        # 影子窗口是独立顶层窗口（不能设 widget 父对象），挂在助手销毁信号上随宿主清理
        self.destroyed.connect(self._shadow.deleteLater)
        self._squared = False

        window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if not window.objectName():
            window.setObjectName("RoundedWindowRoot")
        base = "QMainWindow" if isinstance(window, QMainWindow) else "QDialog"
        self._base_sheet = f"{base}#{window.objectName()} {{ background: transparent; }}"
        window.setStyleSheet(self._base_sheet)

        window.installEventFilter(self)
        from app.resources.qss.theme import ThemeManager

        # 主题切换时边框圈跟着换色（receiver 绑定 ring，窗体销毁自动断开）
        ThemeManager.instance().theme_changed.connect(self._ring.update)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt 命名
        if obj is not self._window:
            return False
        etype = event.type()
        if etype in (QEvent.Type.Show, QEvent.Type.Resize, QEvent.Type.Move):
            self._apply()
            self._shadow.sync()
            if etype == QEvent.Type.Show:
                self._shadow.restack()
        elif etype == QEvent.Type.WindowStateChange:
            self._apply()
            self._shadow.sync()
            self._shadow.restack()
        elif etype in (QEvent.Type.Hide, QEvent.Type.Close):
            self._shadow.hide()
        elif etype in (QEvent.Type.ActivationChange, QEvent.Type.ZOrderChange):
            # 宿主被抬起后，把影子重新插回宿主正下方
            self._shadow.restack()
        return False

    def _apply(self) -> None:
        window = self._window
        ring = self._ring
        squared = window.isMaximized()
        if squared != self._squared:
            # 最大化时压平贴角子控件的圆角（与系统行为一致），还原时恢复
            self._squared = squared
            window.setStyleSheet(
                self._base_sheet + _SQUARE_CORNERS_SHEET if squared else self._base_sheet
            )
        if squared:
            ring.hide()
            return
        ring.setGeometry(window.rect())
        ring.show()
        ring.raise_()
        ring.update()
