"""自绘圆角助手（rounded_window）：安装、mask、最大化退化、主题换色、外阴影。"""

import pytest
from PySide6.QtCore import Qt

from app.views.widgets.frameless_dialog import FramelessMessageBox
from app.views.widgets.rounded_window import _RingWidget, _ShadowWindow, _SHADOW_MARGIN


@pytest.fixture()
def message_box(qapp):
    box = FramelessMessageBox()
    box.setWindowTitle("圆角测试")
    box._set_text("内容")
    box._add_buttons(FramelessMessageBox.Ok, FramelessMessageBox.Ok)
    yield box
    box.close()
    box.deleteLater()


def test_dialog_gets_translucent_background_and_ring(message_box):
    """安装助手后：半透明窗口 + 描边圈 overlay 存在且置顶。"""
    message_box.show()
    message_box.activateWindow()
    assert bool(message_box.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
    ring = message_box.findChild(_RingWidget)
    assert ring is not None
    assert ring.parent() is message_box
    # 窗体级样式表按 ID 选择器关掉了顶层 QSS 背景，避免盖住透明圆角
    assert "RoundedWindowRoot" in message_box.styleSheet()


def test_dialog_corners_squared_when_maximized(qapp, message_box):
    """圆角由贴角子控件 QSS 自绘（不再用 1-bit mask）；最大化压平，还原恢复。"""
    box = message_box
    box.show()
    assert box.mask().isEmpty()
    assert "border-radius: 0px" not in box.styleSheet()

    box.showMaximized()
    assert "border-radius: 0px" in box.styleSheet()

    box.showNormal()
    assert "border-radius: 0px" not in box.styleSheet()


def test_ring_follows_theme(message_box):
    """主题切换后描边圈重绘（不抛异常即为连通）。"""
    from app.resources.qss.theme import ThemeManager

    message_box.show()
    ring = message_box.findChild(_RingWidget)
    ThemeManager.instance().theme_changed.emit("light")
    ThemeManager.instance().theme_changed.emit("dark")
    assert ring.isVisible()


def test_menu_rounding_applied(qapp):
    """菜单圆角修整：透明背景 + 无边框 + 关系统阴影，QSS 圆角成为真实轮廓。"""
    from PySide6.QtWidgets import QMenu

    from app.views.widgets.rounded_window import apply_menu_rounding

    menu = QMenu()
    apply_menu_rounding(menu)
    assert menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert bool(menu.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert bool(menu.windowFlags() & Qt.WindowType.NoDropShadowWindowHint)


def _shadow_of(message_box):
    """影子窗口是独立顶层窗口，经由助手访问。"""
    return message_box._rounded._shadow


def test_shadow_follows_host(qapp, message_box):
    """影子窗口随宿主显示/隐藏，几何 = 宿主 frameGeometry 向四周扩阴影边距。"""
    shadow = _shadow_of(message_box)
    assert shadow is not None
    message_box.show()
    qapp.processEvents()
    assert shadow.isVisible()
    expected = message_box.frameGeometry().adjusted(
        -_SHADOW_MARGIN, -_SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN
    )
    assert shadow.geometry() == expected

    message_box.hide()
    qapp.processEvents()
    assert not shadow.isVisible()


def test_shadow_hidden_when_maximized(qapp, message_box):
    """宿主最大化时影子隐藏，还原后恢复。"""
    shadow = _shadow_of(message_box)
    message_box.show()
    message_box.showMaximized()
    qapp.processEvents()
    assert not shadow.isVisible()

    message_box.showNormal()
    qapp.processEvents()
    assert shadow.isVisible()


def test_shadow_gradient_faces_outward_on_all_sides(qapp, message_box):
    """回归防护：画布 = 影子窗口本身；四边都是“贴边深、向外渐隐”。"""
    shadow = _shadow_of(message_box)
    w, h, m = 320, 240, _SHADOW_MARGIN
    shadow.resize(w, h)
    shadow._render(1.0)
    img = shadow._cache.toImage()
    assert (img.width(), img.height()) == (w, h)

    def alpha(x, y):
        return img.pixelColor(x, y).alpha()

    # 宿主轮廓在影子窗口里四周缩进 m；逐边比较贴边与远处的不透明度
    host_l, host_t, host_r, host_b = m, m, w - m, h - m
    sides = (
        ("左", alpha(host_l - 3, h // 2), alpha(host_l - m + 3, h // 2)),
        ("右", alpha(host_r + 2, h // 2), alpha(host_r + m - 3, h // 2)),
        ("上", alpha(w // 2, host_t - 3), alpha(w // 2, host_t - m + 3)),
        ("下", alpha(w // 2, host_b + 2), alpha(w // 2, host_b + m - 3)),
    )
    for name, near, far in sides:
        assert near > far > 0, f"{name}侧阴影方向错误: near={near}, far={far}"
