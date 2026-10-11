"""自绘圆角助手（rounded_window）：安装、mask、最大化退化、主题换色。"""

import pytest
from PySide6.QtCore import Qt

from app.views.widgets.frameless_dialog import FramelessMessageBox
from app.views.widgets.rounded_window import _RingWidget


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


def test_dialog_mask_is_rounded_and_restores(message_box):
    """show 后有圆角 mask；最大化清空 mask，还原后恢复。"""
    message_box.show()
    assert not message_box.mask().isEmpty()
    assert message_box.mask().boundingRect().size() == message_box.size()

    message_box.showMaximized()
    assert message_box.mask().isEmpty()

    message_box.showNormal()
    assert not message_box.mask().isEmpty()


def test_ring_follows_theme(message_box):
    """主题切换后描边圈重绘（不抛异常即为连通）。"""
    from app.resources.qss.theme import ThemeManager

    message_box.show()
    ring = message_box.findChild(_RingWidget)
    ThemeManager.instance().theme_changed.emit("light")
    ThemeManager.instance().theme_changed.emit("dark")
    assert ring.isVisible()
