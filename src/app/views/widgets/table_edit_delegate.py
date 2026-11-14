"""表格编辑器抛光委托（共享）。

32px 行高里，默认的 QLineEdit 编辑器带 1px 边框 + QSS 的 6px 纵向内边距，
文字上下会被裁掉。本委托统一把编辑器去掉边框、清零边距（含 QSS 内边距）、
设不透明主题底色并占满整个单元格——不透明是关键：QDialog 上下文里
QDialog QWidget 透明的全局规则会把编辑器打透明，下层单元格的旧文字会
从编辑框后面透出来形成重影。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QLineEdit,
    QStyledItemDelegate,
    QTableView,
)

#: 挂在视图（QTableView 子类）实例上的属性名：值为列号集合，这些列的编辑器
#: 里按回车 = 提交并把当前格移到下一可见行同一列（Excel 同款）；未挂该属性
#: 的表格保持 Qt 默认行为（提交后焦点留在原格）。挂在视图而不是委托参数上：
#: 委托与表格是多对一关系，行为开关跟着表格走（``_FOCUS_OWNER_ATTR`` 同款）。
ENTER_NEXT_COLUMNS_ATTR = "_table_edit_delegate_enter_next_columns"


class TableEditDelegate(QStyledItemDelegate):
    """编辑态抛光：QLineEdit 编辑器无边框、无内边距、不透明底色、占满单元格。"""

    def createEditor(self, parent, option, index):  # noqa: N802 - Qt 命名
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setFrame(False)
            editor.setContentsMargins(0, 0, 0, 0)
            editor.setTextMargins(0, 0, 0, 0)
            editor.setMinimumSize(0, 0)
            # 应用级 QSS 给 QLineEdit 的 6px 纵向内边距在 32px 行高里会裁掉
            # 文字上下，用控件级样式覆盖为 0；再显式给不透明主题底色——
            # 控件级样式优先级最高，能压过 QDialog QWidget 透明的全局规则
            from app.resources.qss.theme import ThemeManager

            bg = ThemeManager.instance().current().bg_input
            editor.setStyleSheet(f"padding: 0px; background-color: {bg};")
        return editor

    def updateEditorGeometry(self, editor, option, index):  # noqa: N802 - Qt 命名
        editor.setMinimumSize(0, 0)
        editor.setGeometry(option.rect)

    # --- 回车提交并跳下一行（视图挂 ENTER_NEXT_COLUMNS_ATTR 后启用，仅限指定列） ---
    def eventFilter(self, editor, event) -> bool:  # noqa: N802 - Qt 命名
        if event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            # 只接管不带修饰键的回车（小键盘回车的 KeypadModifier 放行）：
            # Ctrl/Alt/Shift 组合仍走 Qt 默认行为
            if (
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and (event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier)
                == Qt.KeyboardModifier.NoModifier
                and self._enter_moves_next_row()
            ):
                self._commit_and_move_next(editor)
                return True
        return super().eventFilter(editor, event)

    def _enter_moves_next_row(self) -> bool:
        view = self.parent()
        if not isinstance(view, QTableView):
            return False
        columns = getattr(view, ENTER_NEXT_COLUMNS_ATTR, None)
        if not columns:
            return False
        index = view.currentIndex()
        return index.isValid() and index.column() in columns

    def _commit_and_move_next(self, editor) -> None:
        view = self.parent()
        assert isinstance(view, QTableView)
        index = view.currentIndex()
        # 提交并关闭编辑器（与 Qt 默认回车处理同款）：commitData 同步写回
        # 模型（itemChanged → 业务保存 → unit_changed → 整表重载排入下一轮
        # 事件循环），因此必须先提交再跳行——重载后的「按构件 id 恢复选中」
        # 会落在新行上，不会把焦点拽回原行
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.SubmitModelCache)
        row = index.row() + 1
        # 跳过隐藏行（收起的合槽成员行）：跳到下一可见行
        while row < view.model().rowCount() and view.isRowHidden(row):
            row += 1
        if row < view.model().rowCount():
            # 只选中、不代开编辑器；选区行为（整行 / 单元格）由视图自己的
            # selectionBehavior 决定，明细面板照常跟随新选中行刷新
            view.setCurrentIndex(view.model().index(row, index.column()))
