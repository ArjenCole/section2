"""macOS 原生窗口装饰（Apple HIG）：红绿灯按钮 + 透明标题栏 + 系统圆角。

Windows 上“无边框”由 Qt.FramelessWindowHint + Win11 DWM 圆角实现；macOS 上
FramelessWindowHint 会把系统圆角、阴影、红绿灯一并剥掉且无法找回。因此 mac
改走原生路线：保留系统窗口边框，但用 fullSizeContentView + 透明标题栏，把
系统标题栏“藏”进自绘界面——视觉上无边框，而圆角、阴影、红绿灯、边缘缩放
都由系统提供。标题文字由系统画在红绿灯同一行（titleVisibility 保持可见），
颜色跟随窗口外观，因此每次套 chrome 时会把 NSWindow 外观同步成当前主题
（亮/暗），保证标题文字在自绘背景上可读。

注意：fullSizeContentView 会带来 28pt 的安全区内边距（Qt 6.9+ 安全区机制），
所有窗体内容统一从标题栏下方开始布局——这正是原生 mac 应用的排布。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

#: 主窗体红绿灯（关闭/最小化/缩放三枚）占用的标题栏左侧宽度
TRAFFIC_LIGHT_INSET_ALL = 88


def is_mac() -> bool:
    """当前系统是否 macOS。"""
    return sys.platform == "darwin"


class MacStyleTweaks(QProxyStyle):
    """mac 原生样式的微量调整。

    QMacStyle 会把 QComboBox 弹层按菜单渲染（当前项对齐到按钮、层叠在按钮
    上方、宽度按内容收缩），且把 QTabBar 整体居中。这里覆盖两个样式提示：
    - SH_ComboBox_Popup → False：弹层改为标准下拉列表，紧贴输入框下边线
    - SH_TabBar_Alignment → AlignLeft：页签条左对齐（与 Windows 一致）
    其余全部委托给原生样式。仅 mac 安装，见 app/main.py。
    """

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802 - Qt 命名
        if hint == QStyle.SH_ComboBox_Popup:
            return 0
        if hint == QStyle.SH_TabBar_Alignment:
            return int(Qt.AlignmentFlag.AlignLeft)
        return super().styleHint(hint, option, widget, returnData)


def _sync_window_appearance(ns_window) -> None:
    """让 NSWindow 外观跟随应用主题，系统绘制的标题文字才可读。"""
    try:
        from AppKit import NSAppearance, NSAppearanceNameAqua, NSAppearanceNameDarkAqua

        dark = False
        try:
            from app.resources.qss.theme import ThemeManager

            dark = ThemeManager.instance().is_dark()
        except Exception:  # noqa: BLE001 - 主题未就绪时按亮色处理
            pass
        name = NSAppearanceNameDarkAqua if dark else NSAppearanceNameAqua
        ns_window.setAppearance_(NSAppearance.appearanceNamed_(name))
    except Exception:  # noqa: BLE001 - 外观同步失败不影响功能
        pass


class _MacAppGuard(QObject):
    """mac 应用级兜底修复，两类问题：

    1. 窗口装饰被重置：QMacStyle 会在某些控件（如 QSplitter）polish 时重置
       窗口样式掩码/透明标题栏（实测：单位工程面板显示即触发）。监听
       Polish/Show 事件，凡套过 chrome 的窗口被波及，就延迟补套一次
       chrome（幂等、按窗口合并）。
    2. Qt 6.11 mac 下 QComboBox 弹层定位用了 combo 的窗口局部坐标（弹层
       贴到窗口顶部而不是输入框下边线，纯净 Qt 即可复现）。监听弹层容器
       （QComboBoxPrivateContainer）的 Show，显示后按 combo 的真实全局
       位置重新定位到输入框正下方，宽度对齐输入框。
    """

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._watched: dict[QObject, bool] = {}  # 顶层窗口 → close_only
        self._pending: set[QObject] = set()
        self._popup_pending: set[QObject] = set()
        app.installEventFilter(self)

    def watch(self, widget, close_only: bool) -> None:
        self._watched[widget] = close_only

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QWidget

        et = event.type()
        if et in (QEvent.Type.Polish, QEvent.Type.Show) and isinstance(obj, QWidget):
            top = obj.window()
            if top in self._watched and top not in self._pending:
                self._pending.add(top)
                QTimer.singleShot(0, lambda w=top: self._reapply(w))
        if et == QEvent.Type.Show and obj.metaObject().className() == "QComboBoxPrivateContainer":
            if obj not in self._popup_pending:
                self._popup_pending.add(obj)
                QTimer.singleShot(0, lambda c=obj: self._fix_combo_popup(c))
        return False

    def _reapply(self, widget) -> None:
        self._pending.discard(widget)
        apply_mac_window_chrome(widget, close_only=self._watched.get(widget, False))

    def _fix_combo_popup(self, container) -> None:
        self._popup_pending.discard(container)
        try:
            from PySide6.QtWidgets import QComboBox

            combo = container.parentWidget()
            if not isinstance(combo, QComboBox) or not combo.isVisible():
                return

            def place():
                try:
                    if not container.isVisible():
                        return
                    below = combo.mapToGlobal(combo.rect().bottomLeft())
                    above = combo.mapToGlobal(combo.rect().topLeft())
                    width = max(combo.width(), container.width())
                    screen = combo.screen()
                    y = below.y()
                    if screen is not None:
                        overflow = y + container.height() - screen.availableGeometry().bottom()
                        if overflow > 0:
                            y = max(
                                screen.availableGeometry().top(),
                                above.y() - container.height(),
                            )
                    container.setGeometry(below.x(), y, width, container.height())
                except RuntimeError:  # noqa: BLE001 - 控件已销毁
                    pass

            # Qt 自身定位与本修复存在竞态（弹层偶发被移回错误位置），多轮重申
            place()
            for delay in (60, 150):
                QTimer.singleShot(delay, place)
        except RuntimeError:  # noqa: BLE001 - 控件已销毁
            pass


_GUARD: _MacAppGuard | None = None


def _ensure_guard() -> _MacAppGuard | None:
    global _GUARD
    if _GUARD is None:
        app = QApplication.instance()
        if app is not None:
            _GUARD = _MacAppGuard(app)
    return _GUARD


def apply_mac_window_chrome(widget, close_only: bool = False) -> bool:
    """把顶层窗口变为 mac 无边框外观：透明标题栏 + 红绿灯 + 标题文字。

    fullSizeContentView + titlebarAppearsTransparent 让内容延伸进标题栏区域，
    自绘背景铺满窗口；标题文字仍由系统画在红绿灯同一行。close_only=True
    隐藏最小化/缩放红绿灯（对话框只留关闭）。同时把 NSWindow 外观同步成
    当前应用主题（亮/暗）。需在窗口显示前调用（内部会创建原生句柄），
    显示后 Qt 可能重置窗口装饰，由调用方的 showEvent 再补一次（幂等）。
    非 macOS、非 cocoa 后端或调用失败时返回 False，调用方无需处理。
    """
    if not is_mac():
        return False
    try:
        from PySide6.QtGui import QGuiApplication

        # offscreen 等非 cocoa 后端没有真实 NSWindow，误发 ObjC 消息会崩溃
        if QGuiApplication.platformName() != "cocoa":
            return False

        import objc
        from AppKit import (
            NSWindowMiniaturizeButton,
            NSWindowStyleMaskFullSizeContentView,
            NSWindowZoomButton,
        )

        # winId() 是 NSView*，取它的 NSWindow 再改样式掩码
        ns_view = objc.objc_object(c_void_p=int(widget.winId()))
        ns_window = ns_view.window()
        if ns_window is None:
            return False
        ns_window.setStyleMask_(
            ns_window.styleMask() | NSWindowStyleMaskFullSizeContentView
        )
        ns_window.setTitlebarAppearsTransparent_(True)
        _sync_window_appearance(ns_window)
        if close_only:
            ns_window.standardWindowButton_(NSWindowZoomButton).setHidden_(True)
            ns_window.standardWindowButton_(NSWindowMiniaturizeButton).setHidden_(True)
        guard = _ensure_guard()
        if guard is not None:
            guard.watch(widget, close_only)
        return True
    except Exception:  # noqa: BLE001 - 装饰失败不影响功能，退回自绘全部窗口 chrome
        return False
