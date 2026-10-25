"""表格行尾「+ / -」按钮列（管材面板同款，见 unit_panel 管材页）。

「+」钉在按钮列的表头格里（随列宽/显隐/横向滚动重摆），每行行尾一个
「-」负责删除该行——两个按钮同一列。整列可整体显隐：类别 / 状态不允许
增删时直接不显示（不做禁用态）。列附着在“当前最后一列”：列数动态变化
的表格（如参数表的候选列）在重建表头后重新 :meth:`attach` 即可。

调用方负责在表头末尾留一个空表头项（按钮列的表头格）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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
        header = table.horizontalHeader()
        # 按钮列固定宽度（表格本体遵循固定列宽约定，见 table_width 模块）
        if header.stretchLastSection():
            header.setStretchLastSection(False)
        self.add_button = QPushButton("+", header)
        self.add_button.setProperty("role", "icon-btn")
        self.add_button.setToolTip(add_tooltip)
        self.add_button.hide()
        self.add_button.clicked.connect(self.add_clicked.emit)
        header.geometriesChanged.connect(self.place)
        # 单列宽度变化（setColumnWidth / 拖动列边界）不重发 geometriesChanged，
        # 只发 sectionResized——不跟的话「+」会停在旧坐标、悬到表格外
        # （围护窗体做法表按可视区收窄止水描述列后，按钮就丢在收窄前的位置）
        header.sectionResized.connect(self.place)
        table.horizontalScrollBar().valueChanged.connect(self.place)

    # ------------------------------------------------------------------ 列
    @property
    def column(self) -> int:
        """按钮列的列号（attach 前为 -1）。"""
        return self._col

    def attach(self) -> None:
        """按钮列 = 当前最后一列：钉成固定宽度，其余列宽不动。"""
        header = self._table.horizontalHeader()
        new_col = self._table.columnCount() - 1
        if 0 <= self._col < new_col:
            # 按钮列挪位后旧列必须恢复可见：整列显隐是这里唯一的隐藏来源，
            # 不恢复的话，接管旧列的新数据会被上一次 set_visible(False) 的
            # 隐藏吞掉（参数表候选列接管旧按钮列时，砼90° 列整个消失）
            self._table.setColumnHidden(self._col, False)
        self._col = new_col
        # 钉成固定宽度：整表 ResizeToContents 的表格（如围护窗体做法表）里
        # setColumnWidth 会被内容宽度覆盖，按钮列必须显式 Interactive，
        # 否则按钮列宽随内容漂移、按钮被压扁
        header.setSectionResizeMode(new_col, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(self._col, self._width)
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
        self._set_readonly_cell(row)
        self._table.setCellWidget(row, self._col, holder)

    def set_row_undeletable(self, row: int) -> None:
        """该行不可删（没有行尾「-」）：按钮列空格设为只读，防止误编辑出杂散内容。"""
        self._set_readonly_cell(row)

    def _set_readonly_cell(self, row: int) -> None:
        """按钮列该行格子里放一个只读空 item（有「-」的行由按钮盖住，看不见）。"""
        item = self._table.item(row, self._col)
        if item is None:
            item = QTableWidgetItem("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, self._col, item)

    def clear_row_buttons(self) -> None:
        """显式销毁所有行尾「-」（整表重建前调用，防旧控件残留叠加）。"""
        if self._col < 0:
            return
        for row in range(self._table.rowCount()):
            old = self._table.cellWidget(row, self._col)
            if old is not None:
                self._table.removeCellWidget(row, self._col)
                old.deleteLater()
