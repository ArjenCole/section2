"""表格编辑器抛光委托（共享）。

32px 行高里，默认的 QLineEdit 编辑器带 1px 边框 + QSS 的 6px 纵向内边距，
文字上下会被裁掉。本委托统一把编辑器去掉边框、清零边距（含 QSS 内边距）
并占满整个单元格。
"""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate


class TableEditDelegate(QStyledItemDelegate):
    """编辑态抛光：QLineEdit 编辑器无边框、无内边距、占满单元格。"""

    def createEditor(self, parent, option, index):  # noqa: N802 - Qt 命名
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setFrame(False)
            editor.setContentsMargins(0, 0, 0, 0)
            editor.setTextMargins(0, 0, 0, 0)
            editor.setMinimumSize(0, 0)
            # 应用级 QSS 给 QLineEdit 的 6px 纵向内边距在 32px 行高里会裁掉
            # 文字上下，用控件级样式覆盖为 0
            editor.setStyleSheet("padding: 0px;")
        return editor

    def updateEditorGeometry(self, editor, option, index):  # noqa: N802 - Qt 命名
        editor.setMinimumSize(0, 0)
        editor.setGeometry(option.rect)
