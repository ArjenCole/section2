"""macOS 原生窗口装饰（Apple HIG）：红绿灯按钮 + 透明标题栏 + 系统圆角。

Windows 上“无边框”由 Qt.FramelessWindowHint + Win11 DWM 圆角实现；macOS 上
FramelessWindowHint 会把系统圆角、阴影、红绿灯一并剥掉且无法找回。因此 mac
改走原生路线：保留系统窗口边框，但用 fullSizeContentView + 透明标题栏 +
隐藏标题文字，把系统标题栏“藏”进自绘界面——视觉上同样无边框，而圆角、
窗口阴影、左上角红绿灯、边缘缩放都由系统提供，符合 Apple 人机界面指南。
"""

from __future__ import annotations

import sys

#: 主窗体红绿灯（关闭/最小化/缩放三枚）占用的标题栏左侧宽度
TRAFFIC_LIGHT_INSET_ALL = 88
#: 对话框只有关闭一枚红绿灯时的左侧宽度
TRAFFIC_LIGHT_INSET_CLOSE = 52


def is_mac() -> bool:
    """当前系统是否 macOS。"""
    return sys.platform == "darwin"


def apply_mac_window_chrome(widget, close_only: bool = False) -> bool:
    """把顶层窗口变为 mac 无边框外观：透明标题栏 + 隐藏标题文字。

    需在窗口显示前调用（内部会创建原生句柄）。close_only=True 只保留
    关闭红绿灯（对话框习惯），False 保留关闭/最小化/缩放三枚（主窗体）。
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

        title_hidden = 1  # NSWindowTitleVisibility.NSWindowTitleHidden
        try:
            from AppKit import NSWindowTitleHidden as title_hidden  # noqa: PLC0415
        except ImportError:
            pass

        # winId() 是 NSView*，取它的 NSWindow 再改样式掩码
        ns_view = objc.objc_object(c_void_p=int(widget.winId()))
        ns_window = ns_view.window()
        if ns_window is None:
            return False
        ns_window.setStyleMask_(
            ns_window.styleMask() | NSWindowStyleMaskFullSizeContentView
        )
        ns_window.setTitlebarAppearsTransparent_(True)
        ns_window.setTitleVisibility_(title_hidden)
        if close_only:
            ns_window.standardWindowButton_(NSWindowZoomButton).setHidden_(True)
            ns_window.standardWindowButton_(NSWindowMiniaturizeButton).setHidden_(True)
        return True
    except Exception:  # noqa: BLE001 - 装饰失败不影响功能，退回自绘全部窗口 chrome
        return False
