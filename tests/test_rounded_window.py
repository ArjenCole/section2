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


def test_dialog_not_squared_when_maximized(qapp, message_box):
    """圆角由贴角子控件 QSS 自绘（不再用 1-bit mask）。

    最大化压平只针对主窗体：QDialog 作为最大化的 QMainWindow 的 owned 窗口时
    isMaximized() 会偶发误报 True（Win 实测），若按旧逻辑压平会把正常弹窗的
    圆角/描边/影子一并丢掉，所以弹窗不再参与最大化退化。
    """
    box = message_box
    box.show()
    assert box.mask().isEmpty()
    assert "border-radius: 0px" not in box.styleSheet()

    box.showMaximized()
    qapp.processEvents()
    assert "border-radius: 0px" not in box.styleSheet()

    box.showNormal()
    assert "border-radius: 0px" not in box.styleSheet()


def test_shadow_hidden_when_maximized(qapp):
    """影子窗口：主窗体最大化时隐藏；弹窗宿主即使被误报最大化也保持影子。"""
    from PySide6.QtWidgets import QDialog, QMainWindow

    from app.views.widgets.rounded_window import _ShadowWindow

    main = QMainWindow()
    main.showMaximized()
    qapp.processEvents()
    main_shadow = _ShadowWindow(main)
    main_shadow.sync()
    assert not main_shadow.isVisible()
    main.close()

    dialog = QDialog()
    dialog.resize(300, 200)
    dialog.show()
    dialog_shadow = _ShadowWindow(dialog)
    dialog_shadow.sync()
    assert dialog_shadow.isVisible()
    dialog.showMaximized()
    qapp.processEvents()
    dialog_shadow.sync()
    assert dialog_shadow.isVisible(), "弹窗被误报最大化时不应隐藏影子"
    dialog.close()


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


def test_item_rule_has_transparent_background(qapp):
    """回归防护：半透明窗体（自绘圆角）上，::indicator 有 QSS 规则而 item 无
    背景规则时，QStyleSheetStyle 画完 QSS 指示器后用 baseStyle 补画单元格并
    裁掉指示器区；Win10 分层窗口上主题绘制回退经典几何、逃出裁剪区，原生
    勾选框与 QSS 勾选框叠画（实测）。item 规则必须带透明背景，让单元格走
    纯 QSS 绘制路径（qstylesheetstyle.cpp CE_ItemViewItem 的 hasDrawable 分支）。"""
    from app.resources.qss.theme import LIGHT, build_stylesheet

    sheet = build_stylesheet(LIGHT)
    assert (
        "QTableWidget::item, QTableView::item"
        " { padding: 5px 8px; background-color: transparent; }"
    ) in sheet


def test_shadow_inherits_host_transient_parent(qapp):
    """影子与宿主同 Owner：点击被模态禁用的主窗体时，Windows 会把主窗体 z 序
    抬到弹窗之下、影子之上（弹窗作为 owned 窗口被强制保持在 owner 上方，无主
    的影子却被压到主窗体下面盖住，表现为“阴影丢失”，且宿主无任何事件可触发
    restack 自愈）。影子继承宿主的 transientParent 后，owned-above-owner 规则
    保证主窗体永远压不到影子。"""
    from PySide6.QtWidgets import QDialog, QWidget

    from app.views.widgets.rounded_window import _ShadowWindow

    owner = QWidget()
    owner.show()
    host = QDialog(owner)
    host.show()
    shadow = _ShadowWindow(host)
    shadow.sync()
    try:
        assert shadow.windowHandle() is not None
        assert (
            shadow.windowHandle().transientParent()
            is host.windowHandle().transientParent()
        )
    finally:
        host.close()
        owner.close()


def test_square_corners_sheet_scoped_to_main_window(qapp):
    """回归防护：最大化压平样式表设在主窗体上，会沿对象树作用于全部后代——
    裸的后代选择器会把压平规则泄漏到子弹窗上（弹窗圆角变直角，实测）。
    必须用 QMainWindow > 直接子选择器限定，且不包含弹窗/向导的后代选择器。"""
    from app.views.widgets.rounded_window import _SQUARE_CORNERS_SHEET

    assert "QMainWindow > QFrame#FramelessTitleBar" in _SQUARE_CORNERS_SHEET
    assert "QMainWindow > QStatusBar" in _SQUARE_CORNERS_SHEET
    assert "QDialog #FramelessDialogBody" not in _SQUARE_CORNERS_SHEET
    assert "QWizard" not in _SQUARE_CORNERS_SHEET


def test_combo_popup_rounding_applied(qapp):
    """下拉框弹出列表与菜单同款修整：容器透明 + 无边框 + 关系统阴影。

    弹出容器（QComboBoxPrivateContainer）是不透明矩形窗口：QListView 的圆角
    卡片画在里面，圆角外露出容器底色（主窗体里是调色板底色，QDialog 里
    `QDialog QWidget { background: transparent }` 命中容器后直接露黑底）。
    修整后容器的圆角卡片成为真实窗口轮廓。"""
    from PySide6.QtWidgets import QComboBox

    from app.views.widgets.rounded_window import apply_combo_popup_rounding

    combo = QComboBox()
    combo.addItems(["甲", "乙"])
    apply_combo_popup_rounding(combo)
    container = combo.view().window()
    assert container is not combo
    assert container.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert bool(container.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert bool(container.windowFlags() & Qt.WindowType.NoDropShadowWindowHint)
    # 容器自身透明化（类名选择器只命中容器，不影响内部列表的 QSS 背景）
    assert "QComboBoxPrivateContainer { background: transparent; }" in container.styleSheet()
