"""铺满单元格的表格：弹窗里内嵌下拉框与编辑器的兜底。

QDialog 上下文里 QMacStyle 会在 updateEditorGeometries 时把 setCellWidget
放进去的下拉框等控件、以及双击单元格打开的编辑器缩小并垂直居中（实测：
单元格 29pt 时控件只剩 19pt，主窗体 QMainWindow 不触发），表现为"下拉框/
编辑框没撑满单元格、文字显示不全"。这里：
- 安装与主表格一致的 :class:`TableEditDelegate`（编辑器无边框、无内边距）
- 覆写 updateEditorGeometries：每轮视图布局结束后强制把单元格控件与
  打开中的编辑器铺满整个单元格，使弹窗内表格与主窗体表格观感一致。
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTableWidget, QWidget
import shiboken6

from app.views.widgets.table_edit_delegate import TableEditDelegate


class CellFillTable(QTableWidget):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # 编辑态与主表格一致：QLineEdit 编辑器无边框、无内边距、占满单元格
        self.setItemDelegate(TableEditDelegate(self))

    def updateEditorGeometries(self) -> None:  # noqa: N802 - Qt 命名
        super().updateEditorGeometries()
        self._fit_cell_widgets()

    def _fit_cell_widgets(self) -> None:
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                widget = self.cellWidget(row, col)
                if widget is None:
                    continue
                rect = self.visualRect(self.model().index(row, col))
                if widget.geometry() != rect:
                    widget.setGeometry(rect)
        # 编辑中的编辑器同样被缩小居中（QMacStyle 在 delegate 之后按 sizeHint
        # 再缩一次），铺回单元格后还要锁定尺寸，防止后续被改回
        viewport = self.viewport()
        for child in viewport.children():
            if not isinstance(child, QWidget) or not child.isVisible():
                continue
            index = self.indexAt(child.geometry().center())
            if not index.isValid():
                continue
            rect = self.visualRect(index)
            if child.geometry() != rect:
                self._fit_editor(child, rect)
        # 编辑器打开路径里有的几何修正在事件循环才完成，延迟再校一次。
        # 必须绑定接收者上下文（singleShot(ms, receiver, callable)）：表格所属弹窗
        # 关闭后 C++ 对象即被销毁，无上下文的挂起回调不会随之取消，会打到已删除
        # 对象上触发 "libshiboken: Internal C++ object already deleted"（Windows 实测弹窗）。
        QTimer.singleShot(0, self, self._fit_editors_once)

    def _fit_editor(self, editor: QWidget, rect) -> None:
        editor.setMinimumSize(0, 0)
        editor.setMaximumSize(16777215, 16777215)
        editor.setGeometry(rect)
        # 锁死为单元格大小：QMacStyle 事后按 sizeHint 缩小时会被钳在满格
        editor.setMinimumSize(rect.size())
        editor.setMaximumSize(rect.size())

    def _fit_editors_once(self) -> None:
        if not shiboken6.isValid(self):
            return  # 接收者已销毁时兜底（正常情况下挂起回调已随销毁取消）
        viewport = self.viewport()
        for child in viewport.children():
            if not isinstance(child, QWidget) or not child.isVisible():
                continue
            index = self.indexAt(child.geometry().center())
            if not index.isValid():
                continue
            rect = self.visualRect(index)
            if child.geometry() != rect:
                self._fit_editor(child, rect)
