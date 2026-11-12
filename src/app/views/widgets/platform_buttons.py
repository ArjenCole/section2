"""标准按钮行的平台布局构造器。

同一个应用要同时符合 Windows 与 macOS 的对话框按钮惯例（平台原生规范）：

- Windows（Win32 对话框惯例）：肯定按钮（确定/保存）在**左**、取消在右；
  肯定按钮是默认按钮（Enter 触发，原生样式带强调色描边）；一排按钮等宽
  （最小 75px）；整行右对齐。
- macOS（Apple HIG）：取消在左、肯定（默认）按钮在**最右**；按钮按文字
  自然宽度；整行右对齐。

两平台统一标准中文文案（确定/取消/保存/关闭/是/否…），平台差异只体现在
顺序、默认按钮与宽度策略上。见 docs/button_standards.md。

用法::

    row = QHBoxLayout()
    row.addWidget(aux_button)          # 行内最左侧的辅助按钮（如"恢复图集默认"）
    buttons = add_dialog_buttons(
        row,
        [DialogButtonSpec("确定", "accept", on_click=dialog.accept),
         DialogButtonSpec("取消", "reject", on_click=dialog.reject)],
    )
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtWidgets import QBoxLayout, QPushButton

#: Windows 上标准按钮的最小宽度（Win32 对话框基准 50 DLU ≈ 75px），
#: 同一排按钮再统一等宽到最宽者的自然宽度。
WIN_MIN_BUTTON_WIDTH = 75


def is_mac() -> bool:
    """当前系统是否 macOS（与 mac_window.is_mac 一致，避免循环依赖单列于此）。"""
    return sys.platform == "darwin"


# 标准文案（两平台统一，见模块 docstring）
OK_TEXT = "确定"
CANCEL_TEXT = "取消"
SAVE_TEXT = "保存"
DISCARD_TEXT = "不保存"
CLOSE_TEXT = "关闭"
YES_TEXT = "是"
NO_TEXT = "否"
APPLY_TEXT = "应用"


@dataclass(frozen=True)
class DialogButtonSpec:
    """一个标准按钮：文字、角色与点击回调。

    role 决定平台排序：
    - ``"accept"``：肯定动作（确定/保存/是），默认按钮，Windows 最左 / mac 最右；
    - ``"reject"``：取消/关闭（dismiss），Windows 最右 / mac 肯定按钮左侧；
    - ``"other"``：其余辅助动作（不保存/否/复制报告…），两平台都排在中间偏外。
    """

    text: str
    role: str = "other"
    on_click: Callable[[], None] | None = None
    #: 显式指定默认按钮；不写时由第一个 accept 角色承担
    default: bool = False
    #: 预建按钮（对话框需要保留按钮引用时传入，此时 text 仅为排序占位）
    button: QPushButton | None = None


def ordered(specs: Sequence[DialogButtonSpec]) -> list[DialogButtonSpec]:
    """按平台惯例返回按钮的视觉顺序（左→右）。

    Windows：accept → other → reject；macOS：other → reject → accept。
    同角色保持传入顺序。
    """
    if is_mac():
        priority = {"other": 0, "reject": 1, "accept": 2}
    else:
        priority = {"accept": 0, "other": 1, "reject": 2}
    return sorted(specs, key=lambda spec: priority.get(spec.role, 1))


def add_dialog_buttons(row: QBoxLayout, specs: Sequence[DialogButtonSpec]) -> list[QPushButton]:
    """把一排标准按钮按平台惯例加入 ``row``，返回视觉顺序（左→右）的按钮列表。

    - 整行右对齐（行首 stretch 由本函数负责，调用方如需在最左侧放辅助
      按钮，先加入 ``row`` 再调用本函数）；
    - 默认按钮：显式 ``default=True`` 者优先，否则取第一个 accept 角色；
    - Windows 上同排按钮等宽（≥75px），macOS 保持自然宽度；
    - 不写任何 QSS 属性，外观由原生样式 + 全局 QPalette 决定。
    """
    # 右对齐：占位 stretch 排在按钮之前
    row.addStretch(1)
    ordered_specs = ordered(specs)
    buttons = [
        spec.button if spec.button is not None else QPushButton(spec.text)
        for spec in ordered_specs
    ]
    for spec, button in zip(ordered_specs, buttons, strict=True):
        if spec.on_click is not None:
            button.clicked.connect(spec.on_click)
        row.addWidget(button)

    default_index = next(
        (i for i, spec in enumerate(ordered_specs) if spec.default), -1
    )
    if default_index < 0:
        default_index = next(
            (i for i, spec in enumerate(ordered_specs) if spec.role == "accept"), -1
        )
    if default_index < 0:
        # 整排只有取消/关闭这类 dismiss 按钮时（如纯“关闭”的消息框），
        # Enter 也要有去处：默认最后一个 dismiss 按钮
        default_index = next(
            (i for i, spec in enumerate(ordered_specs) if spec.role == "reject"), -1
        )
    if default_index >= 0:
        buttons[default_index].setDefault(True)

    if not is_mac():
        # Windows：同排等宽，最小 75px（Win32 标准按钮宽度）
        equal_width = max(
            [WIN_MIN_BUTTON_WIDTH, *(button.sizeHint().width() for button in buttons)]
        )
        for button in buttons:
            button.setMinimumWidth(equal_width)
    return buttons
