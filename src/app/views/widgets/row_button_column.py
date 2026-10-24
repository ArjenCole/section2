"""表格行尾「+ / -」按钮列（管材面板同款，见 unit_panel 管材页）。

「+」钉在按钮列的表头格里（随列宽/显隐/横向滚动重摆），每行行尾一个
「-」负责删除该行——两个按钮同一列。整列可整体显隐：类别 / 状态不允许
增删时直接不显示（不做禁用态）。列附着在“当前最后一列”：列数动态变化
的表格（如参数表的候选列）在重建表头后重新 :meth:`attach` 即可。

调用方负责在表头末尾留一个空表头项（按钮列的表头格）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QWidget,
)


class RowButtonColumn(QObject):
    """「+」表头格 + 每行行尾「-」的按钮列。"""

    add_clicked = Signal()
    delete_clicked = Signal(int)  # 行号

    def __init__(
        self,
        table: QTableWidget,
        *,
        width: int = 40,
        add_tooltip: str = "新增一行",
        delete_tooltip: str = "删除该行",
    ) -> None:
        super().__init__(table)
        self._table = table
        self._col = -1  # attach 前未附着
        self._width = width
        self._delete_tooltip = delete_tooltip
        self._prev_stretch_col: int | None = None
        header = table.horizontalHeader()
        # 按钮列固定宽度：原先「最后一列拉伸」让位给按钮列的前一列（attach 设置）
        if header.stretchLastSection():
            header.setStretchLastSection(False)
        self.add_button = QPushButton("+", header)
        self.add_button.setProperty("role", "icon-btn")
        self.add_button.setToolTip(add_tooltip)
        self.add_button.hide()
        self.add_button.clicked.connect(self.add_clicked.emit)
        header.geometriesChanged.connect(self.place)
        table.horizontalScrollBar().valueChanged.connect(self.place)

    # ------------------------------------------------------------------ 列
    @property
    def column(self) -> int:
        """按钮列的列号（attach 前为 -1）。"""
        return self._col

    def attach(self) -> None:
        """按钮列 = 当前最后一列：固定宽度，前一列改为拉伸（原尾列的拉伸外观）。"""
        header = self._table.horizontalHeader()
        new_col = self._table.columnCount() - 1
        if self._prev_stretch_col is not None and self._prev_stretch_col != new_col - 1:
            if self._prev_stretch_col < self._table.columnCount():
                header.setSectionResizeMode(
                    self._prev_stretch_col, QHeaderView.ResizeMode.Interactive
                )
        self._col = new_col
        self._table.setColumnWidth(self._col, self._width)
        self._prev_stretch_col = new_col - 1 if new_col > 0 else None
        if self._prev_stretch_col is not None:
            header.setSectionResizeMode(self._prev_stretch_col, QHeaderView.ResizeMode.Stretch)
        self.place()

    def set_visible(self, visible: bool) -> None:
        """整列显隐；隐藏时表头「+」一起藏。"""
        if self._col < 0:
            return
        self._table.setColumnHidden(self._col, not visible)
        self.place()

    def place(self) -> None:
        """把「+」钉进按钮列的表头格；列隐藏时连按钮一起藏。"""
        if self._col < 0 or self._table.isColumnHidden(self._col):
            self.add_button.hide()
            return
        header = self._table.horizontalHeader()
        self.add_button.setGeometry(
            header.sectionViewportPosition(self._col) + 3,
            3,
            header.sectionSize(self._col) - 6,
            max(1, header.height() - 6),
        )
        self.add_button.show()

    # ------------------------------------------------------------------ 行
    def add_row_button(self, row: int) -> None:
        """给行尾装「-」删行按钮（点击发 delete_clicked(行号)）。"""
        button = QPushButton("-", self._table)
        button.setProperty("role", "icon-btn")
        button.setToolTip(self._delete_tooltip)
        button.clicked.connect(lambda _checked=False, r=row: self.delete_clicked.emit(r))
        holder = QWidget(self._table)
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(button)
        self._table.setCellWidget(row, self._col, holder)

    def clear_row_buttons(self) -> None:
        """显式销毁所有行尾「-」（整表重建前调用，防旧控件残留叠加）。"""
        if self._col < 0:
            return
        for row in range(self._table.rowCount()):
            old = self._table.cellWidget(row, self._col)
            if old is not None:
                self._table.removeCellWidget(row, self._col)
                old.deleteLater()
