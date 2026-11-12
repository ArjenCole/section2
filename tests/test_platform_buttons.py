"""平台标准按钮行（widgets/platform_buttons.py）的行为锁定。

Windows（Win32 对话框惯例）：肯定按钮在**左**、取消/关闭在右，同排等宽
（≥75px），肯定按钮是默认按钮（Enter 触发、原生样式强调）；macOS
（Apple HIG）：取消在左、肯定（默认）按钮在**最右**，自然宽度。两平台
按钮行都右对齐。

is_mac 是静态平台判断：monkeypatch platform_buttons.is_mac 即可在同一台
机器上覆盖两个分支。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QPushButton

from app.views.widgets import platform_buttons
from app.views.widgets.frameless_dialog import FramelessInputDialog, FramelessMessageBox
from app.views.widgets.platform_buttons import (
    CANCEL_TEXT,
    CLOSE_TEXT,
    DISCARD_TEXT,
    OK_TEXT,
    SAVE_TEXT,
    DialogButtonSpec,
    add_dialog_buttons,
    ordered,
)

# 所有用例都创建 QWidget：先备好会话级离屏 QApplication
pytestmark = pytest.mark.usefixtures("qapp")


def _make_row(*specs: DialogButtonSpec) -> tuple[QDialog, list[QPushButton]]:
    dialog = QDialog()
    row = QHBoxLayout(dialog)
    buttons = add_dialog_buttons(row, list(specs))
    return dialog, buttons


def test_windows_order_default_and_widths(monkeypatch) -> None:
    """Windows：确定在左、取消在右；确定是默认按钮；同排等宽 ≥75px。"""
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: False)
    dialog, buttons = _make_row(
        DialogButtonSpec(CANCEL_TEXT, "reject"),
        DialogButtonSpec(OK_TEXT, "accept"),
    )
    try:
        assert [b.text() for b in buttons] == [OK_TEXT, CANCEL_TEXT]
        assert buttons[0].isDefault()
        assert not buttons[1].isDefault()
        widths = {b.minimumWidth() for b in buttons}
        assert len(widths) == 1, "Windows 同排按钮应等宽"
        assert widths.pop() >= platform_buttons.WIN_MIN_BUTTON_WIDTH
    finally:
        dialog.deleteLater()


def test_windows_right_aligned(monkeypatch) -> None:
    """Windows：按钮行右对齐（行首是 stretch 占位）。"""
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: False)
    dialog = QDialog()
    row = QHBoxLayout(dialog)
    add_dialog_buttons(
        row,
        [
            DialogButtonSpec(CANCEL_TEXT, "reject"),
            DialogButtonSpec(OK_TEXT, "accept"),
        ],
    )
    try:
        dialog.show()
        first = row.itemAt(0)
        assert first.spacerItem() is not None, "按钮行应以 stretch 开头（右对齐）"
    finally:
        dialog.deleteLater()


def test_mac_order_and_natural_width(monkeypatch) -> None:
    """macOS：取消在左、确定（默认按钮）在最右；不强制等宽。"""
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: True)
    dialog, buttons = _make_row(
        DialogButtonSpec(CANCEL_TEXT, "reject"),
        DialogButtonSpec(OK_TEXT, "accept"),
    )
    try:
        assert [b.text() for b in buttons] == [CANCEL_TEXT, OK_TEXT]
        assert buttons[1].isDefault()
        assert buttons[0].minimumWidth() < platform_buttons.WIN_MIN_BUTTON_WIDTH
    finally:
        dialog.deleteLater()


def test_default_explicit_overrides_role(monkeypatch) -> None:
    """显式 default=True 的按钮优先于 accept 角色承担默认。"""
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: False)
    dialog, buttons = _make_row(
        DialogButtonSpec("是", "accept"),
        DialogButtonSpec("否", "other", default=True),
    )
    try:
        assert buttons[0].text() == "是" and not buttons[0].isDefault()
        assert buttons[1].isDefault()
    finally:
        dialog.deleteLater()


def test_reject_only_row_defaults_to_dismiss(monkeypatch) -> None:
    """整排只有取消/关闭时，dismiss 按钮承担默认（Enter 也要有去处）。"""
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: False)
    dialog, buttons = _make_row(DialogButtonSpec(CLOSE_TEXT, "reject"))
    try:
        assert len(buttons) == 1 and buttons[0].isDefault()
    finally:
        dialog.deleteLater()


def test_ordered_save_discard_cancel(monkeypatch) -> None:
    """保存/不保存/取消 的平台顺序：Windows 保存最左、macOS 保存最右。"""
    specs = [
        DialogButtonSpec(SAVE_TEXT, "accept"),
        DialogButtonSpec(DISCARD_TEXT, "other"),
        DialogButtonSpec(CANCEL_TEXT, "reject"),
    ]
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: False)
    assert [s.text for s in ordered(specs)] == [SAVE_TEXT, DISCARD_TEXT, CANCEL_TEXT]
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: True)
    assert [s.text for s in ordered(specs)] == [DISCARD_TEXT, CANCEL_TEXT, SAVE_TEXT]


def test_messagebox_buttons_platform_order(qapp, monkeypatch) -> None:
    """消息框按钮行随平台排序：Windows 保存|不保存|取消、macOS 反序。"""
    save = QMessageBox.StandardButton.Save
    discard = QMessageBox.StandardButton.Discard
    cancel = QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(platform_buttons, "is_mac", lambda: False)
    box = FramelessMessageBox(None)
    box._add_buttons(save | discard | cancel, save)
    try:
        buttons = [box._button_row.itemAt(i).widget() for i in range(1, box._button_row.count())]
        assert [b.text() for b in buttons] == [SAVE_TEXT, DISCARD_TEXT, CANCEL_TEXT]
        assert buttons[0].isDefault()
        widths = {b.minimumWidth() for b in buttons}
        assert len(widths) == 1
    finally:
        box.deleteLater()

    monkeypatch.setattr(platform_buttons, "is_mac", lambda: True)
    box = FramelessMessageBox(None)
    box._add_buttons(save | discard | cancel, save)
    try:
        buttons = [box._button_row.itemAt(i).widget() for i in range(1, box._button_row.count())]
        assert [b.text() for b in buttons] == [DISCARD_TEXT, CANCEL_TEXT, SAVE_TEXT]
        assert buttons[-1].isDefault()
    finally:
        box.deleteLater()


def _row_buttons(box) -> dict[str, QPushButton]:
    """消息框按钮行 文字 → 按钮（跳过行首 stretch）。"""
    result = {}
    for i in range(box._button_row.count()):
        widget = box._button_row.itemAt(i).widget()
        if isinstance(widget, QPushButton):
            result[widget.text()] = widget
    return result


def test_messagebox_click_returns_standard_button(qapp) -> None:
    """真实点击消息框按钮，_result 必须是对应的 StandardButton。

    回归：_add_buttons 的回调曾写成 ``lambda value=...: ...``——clicked(bool)
    把 checked 位置传入覆盖了默认值，_result 恒为 False，主窗体关闭时的
    保存/不保存确认按哪个按钮都"没有效果"。
    """
    save = QMessageBox.StandardButton.Save
    discard = QMessageBox.StandardButton.Discard
    cancel = QMessageBox.StandardButton.Cancel

    for expected, text in (
        (save, SAVE_TEXT),
        (discard, DISCARD_TEXT),
        (cancel, CANCEL_TEXT),
    ):
        box = FramelessMessageBox(None)
        box._add_buttons(save | discard | cancel, save)
        try:
            _row_buttons(box)[text].click()
            assert box._result == expected
        finally:
            box.deleteLater()


def test_messagebox_esc_maps_to_cancel(qapp) -> None:
    """Esc / X 关闭消息框：有取消按钮时归为取消。"""
    save = QMessageBox.StandardButton.Save
    discard = QMessageBox.StandardButton.Discard
    cancel = QMessageBox.StandardButton.Cancel

    box = FramelessMessageBox(None)
    box._add_buttons(save | discard | cancel, save)
    try:
        box.reject()
        assert box._result == cancel
    finally:
        box.deleteLater()


def test_messagebox_custom_texts_click(qapp) -> None:
    """自定义文案（AI 写操作确认 是/否 → 允许执行/拒绝）点击语义正确。"""
    yes = QMessageBox.StandardButton.Yes
    no = QMessageBox.StandardButton.No

    box = FramelessMessageBox(None)
    box._add_buttons(yes | no, no, button_texts={yes: "允许执行", no: "拒绝"})
    try:
        buttons = _row_buttons(box)
        assert set(buttons) == {"允许执行", "拒绝"}
        buttons["拒绝"].click()
        assert box._result == no
    finally:
        box.deleteLater()


def test_add_dialog_buttons_zero_arg_callbacks(qapp, monkeypatch) -> None:
    """helper 的 on_click 零参回调被 clicked(bool) 调用时按零参处理。"""
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: False)
    clicked: list[str] = []
    dialog = QDialog()
    row = QHBoxLayout(dialog)
    add_dialog_buttons(
        row,
        [
            DialogButtonSpec(OK_TEXT, "accept", on_click=lambda: clicked.append("ok")),
            DialogButtonSpec(CANCEL_TEXT, "reject", on_click=lambda: clicked.append("cancel")),
        ],
    )
    try:
        for button in dialog.findChildren(QPushButton):
            button.click()
        assert clicked == ["ok", "cancel"]
    finally:
        dialog.deleteLater()


def test_input_dialog_buttons(qapp, monkeypatch) -> None:
    """输入对话框：平台顺序 + 确定为默认按钮，无自定义 QSS 属性。"""
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: False)
    dialog = FramelessInputDialog(None, "重命名", "新名称", "旧名")
    try:
        buttons = [b for b in dialog.findChildren(QPushButton) if b.text() in (OK_TEXT, CANCEL_TEXT)]
        assert [b.text() for b in buttons] == [OK_TEXT, CANCEL_TEXT]
        assert buttons[0].isDefault()
        assert buttons[0].property("primary") is None
    finally:
        dialog.deleteLater()


def test_prebuilt_button_is_adopted(monkeypatch) -> None:
    """传入预建按钮时 helper 收编该实例（对话框保留引用可用）。"""
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: False)
    prebuilt = QPushButton(CLOSE_TEXT)
    dialog = QDialog()
    row = QHBoxLayout(dialog)
    buttons = add_dialog_buttons(row, [DialogButtonSpec(CLOSE_TEXT, "reject", button=prebuilt)])
    try:
        assert buttons[0] is prebuilt
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("is_mac", [False, True])
def test_role_priority_full_order(monkeypatch, is_mac: bool) -> None:
    """三角色齐全时的完整顺序：Windows accept|other|reject，macOS 反序。"""
    monkeypatch.setattr(platform_buttons, "is_mac", lambda: is_mac)
    specs = [
        DialogButtonSpec("是", "accept"),
        DialogButtonSpec("否", "other"),
        DialogButtonSpec(CANCEL_TEXT, "reject"),
    ]
    texts = [s.text for s in ordered(specs)]
    if is_mac:
        assert texts == ["否", CANCEL_TEXT, "是"]
    else:
        assert texts == ["是", "否", CANCEL_TEXT]
