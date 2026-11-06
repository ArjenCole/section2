"""铺满单元格的表格：内嵌下拉框 / 文本框 / 编辑器的兜底。

两个场景会让 setCellWidget 放进去的控件不占满单元格、甚至跑到别的行：

* QDialog 上下文里 QMacStyle 会在 updateEditorGeometries 时把控件与双击打开的
  编辑器缩小并垂直居中（实测：单元格 29pt 时控件只剩 19pt，主窗体 QMainWindow
  不触发），表现为"下拉框 / 编辑框没撑满单元格、文字显示不全"；
* setRowCount 之后行列位置还没算出来，setCellWidget 会按重置前的旧位置摆放
  （常落在第 0 行），之后没有布局事件时不会再纠正。

这里：
- 安装与主表格一致的 :class:`TableEditDelegate`（编辑器无边框、无内边距）
- 覆写 updateEditorGeometries：每轮视图布局结束后强制把单元格控件与
  打开中的编辑器铺满整个单元格
- 提供 :meth:`CellFillTable.fit_cell_widgets`：填装完单元格控件后主动调用一次，
  立即（并在下一轮事件循环）把控件铺回各自的单元格。
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTableWidget, QWidget
import shiboken6

from app.views.widgets.table_edit_delegate import TableEditDelegate

#: QWIDGETSIZE_MAX：解除之前锁定的尺寸上限
_MAX_WIDGET_SIZE = 16777215


class CellFillTable(QTableWidget):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # 选中单元格时对应列的列头不再加粗重绘：QSS 的列头规则没有 :selected
        # 背景，highlightSections 的唯一表现是选中列的列头文字走另一条渲染
        # 路径变粗，看起来像“字体忽大忽小”
        self.horizontalHeader().setHighlightSections(False)
        # 编辑态与主表格一致：QLineEdit 编辑器无边框、无内边距、占满单元格
        self.setItemDelegate(TableEditDelegate(self))

    def updateEditorGeometries(self) -> None:  # noqa: N802 - Qt 命名
        super().updateEditorGeometries()
        self._fit_cell_widgets()

    def fit_cell_widgets(self) -> None:
        """立即把单元格控件铺回各自的单元格（填装完单元格控件后调用一次）。

        ``setRowCount`` 之后行列位置可能还是旧的，``setCellWidget`` 会把控件按
        旧位置（常常是第 0 行）摆放；这里跑一遍布局后逐个铺回，下一轮事件循环
        再补一次（布局尚未落地时第一遍可能拿不到正确矩形）。
        """
        self._fit_cell_widgets()
        QTimer.singleShot(0, self, self._fit_cell_widgets)

    def _fit_cell_widgets(self) -> None:
        cell_widgets: set[QWidget] = set()
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                widget = self.cellWidget(row, col)
                if widget is None:
                    continue
                cell_widgets.add(widget)
                rect = self.visualRect(self.model().index(row, col))
                if widget.geometry() != rect:
                    # 常驻控件不能被之前锁定的 min/max 尺寸卡住（编辑器才会锁）
                    widget.setMinimumSize(0, 0)
                    widget.setMaximumSize(_MAX_WIDGET_SIZE, _MAX_WIDGET_SIZE)
                    widget.setGeometry(rect)
        # 编辑中的编辑器同样被缩小居中（QMacStyle 在 delegate 之后按 sizeHint
        # 再缩一次），铺回单元格后还要锁定尺寸，防止后续被改回。
        # 常驻单元格控件不算编辑器：它们只由上面的循环摆位，不锁尺寸。
        viewport = self.viewport()
        for child in viewport.children():
            if not isinstance(child, QWidget) or not child.isVisible():
                continue
            if child in cell_widgets:
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
        editor.setMaximumSize(_MAX_WIDGET_SIZE, _MAX_WIDGET_SIZE)
        editor.setGeometry(rect)
        # 锁死为单元格大小：QMacStyle 事后按 sizeHint 缩小时会被钳在满格
        editor.setMinimumSize(rect.size())
        editor.setMaximumSize(rect.size())

    def _fit_editors_once(self) -> None:
        if not shiboken6.isValid(self):
            return  # 接收者已销毁时兜底（正常情况下挂起回调已随销毁取消）
        cell_widgets = {
            self.cellWidget(row, col)
            for row in range(self.rowCount())
            for col in range(self.columnCount())
        }
        viewport = self.viewport()
        for child in viewport.children():
            if not isinstance(child, QWidget) or not child.isVisible():
                continue
            if child in cell_widgets:
                continue
            index = self.indexAt(child.geometry().center())
            if not index.isValid():
                continue
            rect = self.visualRect(index)
            if child.geometry() != rect:
                self._fit_editor(child, rect)
