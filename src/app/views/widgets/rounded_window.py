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
后方，随宿主显示/移动/缩放同步，用“核心填充 + 向外指数渐隐的环带”模拟投影。
深度/范围按原生 Win11 默认阴影标定（侧面贴边约 11%，下缘约 22%）。不改动
宿主内容几何，主窗体与弹窗通用；宿主最大化/最小化/隐藏时影子同步隐藏。
影子窗口开启输入穿透，不挡鼠标也不抢焦点。

顶层窗体命中的全局 QSS 背景（``QWidget/QMainWindow/QDialog`` 规则）会把
整个矩形填成实心、露出方角，助手用窗体级样式表 + ID 选择器精确关掉。
macOS 走原生红绿灯窗口（见 mac_window.py），不要装这个助手。
"""

from __future__ import annotations

import math
import sys

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QComboBox, QMainWindow, QMenu, QWidget

from app.core import window_diag

#: 圆角半径（逻辑像素），与 theme.py 里贴角子控件的 border-radius 一致
_RADIUS = 8

#: 阴影向外扩散的最大距离（逻辑像素）。纵向阴影比横向长，取两个方向的最大值。
_SHADOW_MARGIN = 48

#: 阴影整体向下偏移（逻辑像素），模拟光源在上方；原生 Win11 阴影下缘明显比上缘深。
_SHADOW_OFFSET = 8

#: 贴边处阴影核心的不透明度（0-255）。本机实测 Win11 默认阴影侧面贴边约 11%，
#: 这里取 28（≈11%），与系统默认一致；旧值 60 叠加 1.5px 描边后实际约 29%，明显偏深。
_SHADOW_ALPHA = 28

#: 横向/纵向阴影的可见衰减范围（逻辑像素）。原生阴影侧面约 35px、下缘约 55px。
_SHADOW_RANGE_X = 36
_SHADOW_RANGE_Y = 40

#: 渐隐环带数量；环带越密，透明度阶梯越细，肉眼看起来越平滑。
_SHADOW_LAYERS = 40

#: 圈层透明度按 exp(-_SHADOW_DECAY * t) 衰减，t 为 0（贴边）到 1（最外圈）
_SHADOW_DECAY = 3.1

#: 下缘增强：本机实测 Win11 默认阴影下缘贴边约 22%，而侧面约 11%。从窗体高度
#: 的 _SHADOW_BOTTOM_RAMP 处开始线性增强，到窗底达到 _SHADOW_BOTTOM_BOOST 倍。
_SHADOW_BOTTOM_RAMP = 0.75
_SHADOW_BOTTOM_BOOST = 2.0

#: 最大化时压平贴角子控件圆角的窗体级样式表片段（widget 级样式表优先于
#: 全局 QSS，同选择器下直接覆盖）。选择器必须用 QMainWindow > 直接子选择器
#: 限定：窗体级样式表会沿对象树作用于全部后代，裸的 QFrame#FramelessTitleBar
#: 等会把主窗体最大化的压平规则泄漏到其子弹窗上（弹窗圆角变直角，实测）。
#: 无状态栏后，底部两角由左右两栏自己倒圆（theme.py 里按 objectName 命中），
#: 最大化时同样要压平，否则最大化窗口的底角会留两个透明缺口。
#: AI 展开/收起竖条不在此列：它自绘底色，最大化时自己按方角铺满。
_SQUARE_CORNERS_SHEET = (
    "QMainWindow > QFrame#FramelessTitleBar, "
    "QMainWindow QSplitter#MainSplitter, "
    "QMainWindow QWidget#TreePanelColumn, "
    "QMainWindow QWidget#AiPanelColumn, "
    "QMainWindow QWidget#AiColumnContainer "
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
        # 最大化压平/藏影只针对主窗体：QDialog 作为最大化的 QMainWindow 的
        # owned 窗口时 isMaximized() 会偶发误报 True（实测），把弹窗的影子
        # 错误藏掉且不再恢复；弹窗本就不可最大化，这里仅对 QMainWindow 判定
        suppress_maximized = host.isMaximized() and isinstance(host, QMainWindow)
        if not host.isVisible() or host.isMinimized() or suppress_maximized:
            if self.isVisible():
                self.hide()
            return
        m = _SHADOW_MARGIN
        target = host.frameGeometry().adjusted(-m, -m, m, m)
        if self.geometry() != target:
            self.setGeometry(target)
        if not self.isVisible():
            # 影子与宿主同 Owner（transientParent）：点击被模态禁用的主窗体时，
            # Windows 会把主窗体 z 序抬到弹窗之下、影子之上（弹窗作为 owned 窗口
            # 被 Windows 强制保持在 owner 上方，无主的影子却被压到主窗体下面
            # 盖住，表现为“阴影丢失”且宿主无任何事件可触发 restack）。让影子
            # 继承宿主的 transientParent 后，owned-above-owner 规则保证主窗体
            # 永远压不到影子（见 docs/window_chrome.md §4）
            host_handle = host.windowHandle()
            if host_handle is not None:
                handle = self.windowHandle()
                if handle is None:
                    self.winId()  # 先建原生窗口才能设置 owner
                    handle = self.windowHandle()
                if handle is not None and handle.transientParent() is not host_handle.transientParent():
                    if window_diag.enabled():
                        window_diag.record(
                            "rounded.set_transient_parent",
                            f"host={type(host).__name__} host_hwnd={int(host.winId())} "
                            f"shadow_hwnd={int(self.winId())} "
                            f"owner_now={handle.transientParent()}",
                            stack=3,
                        )
                    handle.setTransientParent(host_handle.transientParent())
            self.show()

    def restack(self) -> None:
        """把自己插到宿主 HWND 正后方（仅 Windows）。"""
        if sys.platform != "win32" or not self.isVisible():
            return
        try:
            import ctypes

            shadow_hwnd = int(self.winId())
            host_hwnd = int(self._host.winId())
            ctypes.windll.user32.SetWindowPos(
                shadow_hwnd, host_hwnd, 0, 0, 0, 0,
                _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE,
            )
            if window_diag.enabled():
                window_diag.record(
                    "rounded.restack",
                    f"shadow_hwnd={shadow_hwnd} after_host_hwnd={host_hwnd} "
                    f"host={type(self._host).__name__}",
                    stack=3,
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
        # 影子窗口本身就是宿主 + 四周留白，画布即窗口大小；
        # 宿主轮廓在本窗口坐标系里是四周缩进 m 的圆角矩形
        pixmap = QPixmap(max(1, round(w * dpr)), max(1, round(h * dpr)))
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(dpr)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 阴影轮廓整体下移，形成“光从上方来”的下重上轻；核心先整体填一层，
        # 保证下缘偏移出的那条带、以及圆角缺口处都有底色。
        host = QRectF(m, m, w - 2.0 * m, h - 2.0 * m)
        base = host.translated(0, _SHADOW_OFFSET)

        def shadow_brush(alpha: int) -> QBrush:
            """同一条纵向渐变：窗体上部保持 alpha，向下缘逐渐加强。"""
            gradient = QLinearGradient(base.topLeft(), base.bottomLeft())
            top = QColor(0, 0, 0, alpha)
            bottom = QColor(
                0, 0, 0, min(255, round(alpha * _SHADOW_BOTTOM_BOOST))
            )
            gradient.setColorAt(0.0, top)
            gradient.setColorAt(_SHADOW_BOTTOM_RAMP, top)
            gradient.setColorAt(1.0, bottom)
            return QBrush(gradient)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(_rounded_path(base, _RADIUS), shadow_brush(_SHADOW_ALPHA))

        # 向外逐条环带填充：每条环带只覆盖 [e_{i-1}, e_i] 这一圈，用 OddEven
        # 挖掉内圈，避免旧实现“1.5px 笔宽 + 1px 步进”相邻圈互相叠加导致贴边
        # 实际不透明度翻倍。环带边缘共享同一条曲线，抗锯齿覆盖互补，既不会
        # 出现亮缝，也不会越描越深。
        # 透明度按 t 指数衰减，横向/纵向用不同扩展距离（下缘更长）。
        decay = _SHADOW_DECAY
        norm = 1.0 - math.exp(-decay)
        for i in range(1, _SHADOW_LAYERS + 1):
            t0 = (i - 1) / _SHADOW_LAYERS
            t1 = i / _SHADOW_LAYERS
            alpha = round(
                _SHADOW_ALPHA
                * (math.exp(-decay * (t0 + t1) * 0.5) - math.exp(-decay))
                / norm
            )
            if alpha <= 0:
                continue
            ex0, ey0 = _SHADOW_RANGE_X * t0, _SHADOW_RANGE_Y * t0
            ex1, ey1 = _SHADOW_RANGE_X * t1, _SHADOW_RANGE_Y * t1
            band = QPainterPath()
            band.setFillRule(Qt.FillRule.OddEvenFill)
            band.addRoundedRect(
                base.adjusted(-ex1, -ey1, ex1, ey1),
                _RADIUS + max(ex1, ey1),
                _RADIUS + max(ex1, ey1),
            )
            band.addRoundedRect(
                base.adjusted(-ex0, -ey0, ex0, ey0),
                _RADIUS + max(ex0, ey0),
                _RADIUS + max(ex0, ey0),
            )
            painter.fillPath(band, shadow_brush(alpha))
        painter.end()
        self._cache = pixmap


class _PopupRounding(QObject):
    """弹出层圆角修整：Win10 的 QMenu 与 QComboBox 弹出列表都是不透明矩形
    窗口，QSS 画的圆角外面会露出容器自身底色的方角（主窗体里是调色板底色、
    QDialog 里 `QDialog QWidget { background: transparent }` 命中容器后直接
    露出未初始化的黑底），左下角再叠上系统阴影最扎眼。在首次 polish（尚无
    原生窗口）时开透明背景 + 无边框，并关掉系统方角阴影，让 QSS 的
    border-radius 成为真实的窗口轮廓。"""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt 命名
        if event.type() != QEvent.Type.Polish or obj.isVisible():
            return False
        if isinstance(obj, QMenu):
            apply_menu_rounding(obj)
        elif isinstance(obj, QComboBox):
            apply_combo_popup_rounding(obj)
        return False


def apply_menu_rounding(menu: QMenu) -> None:
    menu.setWindowFlags(
        menu.windowFlags()
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.NoDropShadowWindowHint
    )
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def apply_combo_popup_rounding(combo: QComboBox) -> None:
    """下拉框弹出列表（QComboBoxPrivateContainer 容器）与菜单同款修整。

    容器必须一并透明化：应用级 QSS 的 QWidget 背景规则会把它画成不透明底色，
    圆角外的方角照样露出来；容器自身透明后，QListView 的圆角卡片
    （QComboBox QAbstractItemView 规则）才是真实轮廓。选择器用类名只命中
    容器，避免无选择器规则把内部列表也打透明。
    """
    container = combo.view().window()
    apply_menu_rounding(container)
    container.setStyleSheet("QComboBoxPrivateContainer { background: transparent; }")


def install_menu_rounding(app) -> None:
    """给整个应用的弹出层（QMenu 菜单栏下拉、各级子菜单、右键菜单，以及
    所有 QComboBox 的下拉列表）套圆角修整。"""
    app.installEventFilter(_PopupRounding(app))


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

        # 系统原生阴影一律关掉：外阴影全部由 _ShadowWindow 自绘，避免 Win11
        # 在自绘阴影外再叠一层 DWM 阴影（Win10/Win11 观感不一致）
        window.setWindowFlags(
            window.windowFlags() | Qt.WindowType.NoDropShadowWindowHint
        )
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
        # 析构中的宿主还可能派发残余事件，此刻 Python 侧属性已被 shiboken 清掉
        window = getattr(self, "_window", None)
        if obj is not window:
            return False
        etype = event.type()
        # 诊断：这一层是运行时唯一"在窗口可见期间动原生窗口"的代码，
        # 只记真正会走到原生窗口的事件（Resize/Move 太吵，跳过）
        if window_diag.enabled() and etype in (
            QEvent.Type.Show,
            QEvent.Type.Hide,
            QEvent.Type.Close,
            QEvent.Type.WindowStateChange,
            QEvent.Type.ActivationChange,
            QEvent.Type.ZOrderChange,
        ):
            window_diag.record(
                "rounded.host_event",
                f"{etype.name} host={type(window).__name__} hwnd={int(window.winId())} "
                f"title={window.windowTitle()!r} visible={window.isVisible()}",
                stack=3,
            )
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
            # 宿主被抬起后，把影子重新插回宿主正下方；顺带 sync 自愈——
            # 若影子曾被误藏（见 _ShadowWindow.sync），激活变化时拉回来
            self._shadow.sync()
            self._shadow.restack()
        return False

    def _apply(self) -> None:
        window = self._window
        ring = self._ring
        # 最大化退化只针对主窗体（QDialog 上 isMaximized() 会误报，见 _ShadowWindow.sync）
        squared = window.isMaximized() and isinstance(window, QMainWindow)
        if squared != self._squared:
            # 最大化时压平贴角子控件的圆角（与系统行为一致），还原时恢复
            self._squared = squared
            if window_diag.enabled():
                window_diag.record(
                    "rounded.set_stylesheet",
                    f"squared={squared} host={type(window).__name__} hwnd={int(window.winId())}",
                    stack=3,
                )
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
