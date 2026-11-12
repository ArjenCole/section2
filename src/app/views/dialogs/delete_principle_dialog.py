"""删除原则确认对话框（主页面原则横条右键「删除原则」的确认弹窗）。

两件事：

* 说明这条原则删除后，引用它的构件条目会改引用哪条原则；
* 给出一个下拉框，让用户**当场改选**替代原则（默认取库中其余原则的最后一条，
  与 ``project_io.merge_target_*`` 的既有语义一致）。

正文用 ``QLabel`` 富文本渲染（与 :class:`FramelessMessageBox` 同款），所以
动态拼进去的原则名必须 ``html.escape``：原则名里的 ``<`` / ``&`` 不转义会被
当成未知 HTML 标签吞掉，用户看到的就是“该原则的引用将被 替代”（X 不显示）。
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from app.views.widgets.frameless_dialog import FramelessDialog, load_icon
from app.views.widgets.platform_buttons import (
    CANCEL_TEXT,
    OK_TEXT,
    DialogButtonSpec,
    add_dialog_buttons,
)


class DeletePrincipleDialog(FramelessDialog):
    """删除原则确认：正文说明引用去向，下拉框可选替代原则。"""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        principle_name: str,
        candidates: list[str],
        target: str,
    ) -> None:
        super().__init__(parent, "删除原则")
        self._principle_name = principle_name
        self.setMinimumWidth(460)
        self._build(list(candidates), target)

    # ------------------------------------------------------------------ 对外
    def replacement(self) -> str:
        """用户选定的替代原则名（``exec()`` 返回 Accepted 后读取）。"""
        return self._combo.currentText()

    # ------------------------------------------------------------------ 界面
    def _build(self, candidates: list[str], target: str) -> None:
        layout = self.bodyLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 正文行：问号图标 + 说明（与 FramelessMessageBox 的消息框同款排布）
        content = QHBoxLayout()
        content.setSpacing(12)
        icon = QLabel()
        icon.setFixedSize(24, 24)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        icon.setPixmap(load_icon("help-circle", "#3B82F6", 24).pixmap(24, 24))
        self._text = QLabel()
        self._text.setTextFormat(Qt.TextFormat.RichText)
        self._text.setWordWrap(True)
        self._text.setMinimumWidth(360)
        content.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        content.addWidget(self._text, 1)
        layout.addLayout(content)

        # 替代原则下拉：只列同类原则里**除被删这条之外**的项
        picker = QHBoxLayout()
        picker.setSpacing(8)
        picker.addWidget(QLabel("替代原则："))
        self._combo = QComboBox()
        self._combo.addItems(candidates)
        if target in candidates:
            self._combo.setCurrentText(target)
        self._combo.currentTextChanged.connect(self._refresh_text)
        picker.addWidget(self._combo, 1)
        layout.addLayout(picker)

        hint = QLabel(
            "该原则会从原则库删除；引用它的构件条目（含左右分设 / 合槽组员）"
            "改为引用上面选中的原则。"
        )
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 标准按钮行：顺序 / 默认按钮 / 对齐按平台规范（见 platform_buttons）
        button_row = QHBoxLayout()
        self._btn_ok = QPushButton(OK_TEXT)
        add_dialog_buttons(
            button_row,
            [
                DialogButtonSpec(OK_TEXT, "accept", on_click=self.accept, button=self._btn_ok),
                DialogButtonSpec(CANCEL_TEXT, "reject", on_click=self.reject),
            ],
        )
        layout.addLayout(button_row)
        # 焦点给「确定」：Enter 直接确认（焦点落在下拉框上时 Enter 会展开列表，
        # 用户按习惯回车反而看不到确认效果）；要改选按 Tab 或点下拉框
        self._btn_ok.setFocus()

        self._refresh_text()

    def _refresh_text(self) -> None:
        """按当前下拉选择重写正文（选谁就显示谁，避免“说一套做一套”）。"""
        name = escape(self._principle_name)
        target = escape(self._combo.currentText())
        self._text.setText(
            f"删除后原则“{name}”的引用将被“<b>{target}</b>”替代，确认删除？"
        )
