"""铺满单元格的表格：弹窗里内嵌下拉框等单元格控件的兜底。

QDialog 上下文里 QMacStyle 会在 updateEditorGeometries 时把 setCellWidget
放进去的下拉框等控件缩小并垂直居中（实测：单元格 29pt 时控件只剩 19pt，
主窗体 QMainWindow 不触发），表现为"下拉框没撑满单元格"。这里覆写
updateEditorGeometries：每轮视图布局结束后强制把单元格控件铺满整个
单元格，使弹窗内表格与主窗体表格观感一致。
"""

from __future__ import annotations

from PySide6.QtWidgets import QTableWidget


class CellFillTable(QTableWidget):
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
