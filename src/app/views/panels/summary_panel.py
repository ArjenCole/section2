"""中部：汇总页（计划 §7.1，M5）。

选中项目树根 / 标段节点时显示：全部单位工程的定额汇总与清单逐构件工程量，
量 × 单价 = 合价；单价可直接在表内编辑（写入单价字典），
并支持 批量载价（价格库） / 清空价格 / 导出 Excel。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.evaluator import format_number
from app.core.event_bus import bus
from app.services import excel_export, project_io
from app.services.atlas import default_price_table
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox

_PRICE_ROLE = Qt.ItemDataRole.UserRole + 1
_HEADERS = ["编号", "类别", "项目", "单位", "计算表达式", "工程量", "单价", "合价"]
_COL_PRICE = 6


class SummaryPanel(QWidget):
    """汇总页：量 × 单价 = 合价。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self._data = None
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        self._title = QLabel("工程汇总")
        self._title.setProperty("role", "panel-title")
        bar.addWidget(self._title)
        bar.addStretch(1)
        self._scope = QComboBox()
        self._scope.setMinimumWidth(200)
        self._scope.currentIndexChanged.connect(lambda _index: self.refresh())
        bar.addWidget(QLabel("汇总范围："))
        bar.addWidget(self._scope)
        self._btn_load_prices = QPushButton("批量载价…")
        self._btn_clear_prices = QPushButton("清空价格")
        self._btn_clear_prices.setProperty("danger", "true")
        self._btn_export = QPushButton("导出 Excel…")
        self._btn_export.setProperty("primary", "true")
        self._btn_load_prices.clicked.connect(self._load_prices)
        self._btn_clear_prices.clicked.connect(self._clear_prices)
        self._btn_export.clicked.connect(self._export)
        bar.addWidget(self._btn_load_prices)
        bar.addWidget(self._btn_clear_prices)
        bar.addWidget(self._btn_export)
        layout.addLayout(bar)

        from PySide6.QtWidgets import QTabWidget

        self._tabs = QTabWidget()
        # documentMode：页签文字统一左对齐（macOS 原生样式默认把页签条整体居中）
        self._tabs.setDocumentMode(True)
        self._tabs.tabBar().setDrawBase(False)
        self._quota_table = self._make_table()
        self._listing_table = self._make_table()
        self._tabs.addTab(self._quota_table, "定额工程量")
        self._tabs.addTab(self._listing_table, "清单工程量")
        layout.addWidget(self._tabs, 1)

        self._total_label = QLabel("")
        self._total_label.setProperty("role", "panel-title")
        layout.addWidget(self._total_label)

        self._quota_table.itemChanged.connect(lambda item: self._on_price_changed(item, "quota"))
        self._listing_table.itemChanged.connect(lambda item: self._on_price_changed(item, "listing"))
        bus().project_opened.connect(lambda _path: self._reload_scope())
        bus().project_closed.connect(lambda: self._reload_scope())
        bus().tree_structure_changed.connect(lambda: self._reload_scope())
        bus().unit_changed.connect(lambda _unit_id: self.refresh())
        self._reload_scope()

    # ------------------------------------------------------------------ 界面
    def _make_table(self) -> QTableWidget:
        table = QTableWidget(0, len(_HEADERS))
        table.setHorizontalHeaderLabels(_HEADERS)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(4, 320)
        table.verticalHeader().setVisible(False)
        table.setWordWrap(False)
        return table

    def _reload_scope(self) -> None:
        self._scope.blockSignals(True)
        self._scope.clear()
        if project_io.is_open():
            self._scope.addItem("全部单位工程", None)
            for segment in project_io.segments():
                for unit in project_io.units(segment.id):
                    self._scope.addItem(f"{segment.name} / {unit.name}", unit.id)
        self._scope.blockSignals(False)
        self.refresh()

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        info = project_io.basic_info()
        if info is None:
            self._title.setText("工程汇总")
            self._total_label.setText("尚未打开工程。")
            self._quota_table.setRowCount(0)
            self._listing_table.setRowCount(0)
            self._data = None
            return
        self._title.setText(f"{info.project_name} · 汇总")
        unit_id = self._scope.currentData()
        unit_ids = [unit_id] if unit_id is not None else None
        self._data = excel_export.collect_summary(unit_ids)
        self._fill(self._quota_table, self._data.quota, self._data.quota_category_totals, self._data.quota_total)
        self._fill(self._listing_table, self._data.listing, self._data.listing_category_totals, self._data.listing_total)
        self._total_label.setText(
            f"定额合计：{format_number(self._data.quota_total)} 元　　清单合计：{format_number(self._data.listing_total)} 元"
            "（单价为空按 0 计）"
        )

    def _fill(self, table: QTableWidget, rows, category_totals: dict, total: float) -> None:
        self._loading = True
        try:
            table.setRowCount(len(rows) + len(category_totals) + 1)
            row_index = 0
            for row in rows:
                values = (
                    row.no,
                    row.category,
                    row.item,
                    row.unit,
                    row.expression,
                    format_number(row.amount) if row.amount else "",
                    format_number(row.price) if row.price else "",
                    format_number(row.total) if row.total else "",
                )
                for column, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    if column == _COL_PRICE and row.editable_price and row.no != "清单项目":
                        item.setData(_PRICE_ROLE, f"{row.category}|{row.item}|{row.unit}")
                        item.setToolTip("双击或直接编辑单价，合价自动重算")
                    else:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if column == 4:
                        item.setToolTip(row.expression)
                    if row.no == "清单项目":
                        item.setBackground(_highlight())
                    table.setItem(row_index, column, item)
                row_index += 1
            footer = [
                ("合计：", "", format_number(total)),
                *[(category, "", format_number(value)) for category, value in category_totals.items()],
            ]
            for label, _category, value in footer:
                no_item = QTableWidgetItem(label)
                no_item.setFlags(no_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row_index, 0, no_item)
                unit_item = QTableWidgetItem("元")
                unit_item.setFlags(unit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row_index, 3, unit_item)
                total_item = QTableWidgetItem(value)
                total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row_index, 7, total_item)
                row_index += 1
        finally:
            self._loading = False

    def _on_price_changed(self, item: QTableWidgetItem, table_name: str) -> None:
        if self._loading or item.column() != _COL_PRICE:
            return
        key = item.data(_PRICE_ROLE)
        if not key:
            return
        try:
            value = float(item.text() or 0)
        except ValueError:
            bus().status_message.emit("单价需为数字。", 4000)
            self.refresh()
            return
        project_io.set_price(key, value)
        self.refresh()

    def _load_prices(self) -> None:
        """批量载价（旧版 FormSum：从价格库 Price.xlsx 载入）。"""
        library = default_price_table()
        if not library:
            FramelessMessageBox.information(self, "批量载价", "价格库文件缺失（app/resources/inventory/Price.xlsx）。")
            return
        names = sorted(library)
        picker = QComboBox(self)
        picker.addItems(names)
        from PySide6.QtWidgets import QDialogButtonBox

        dialog = FramelessDialog(self, "批量载价")
        dialog.setMinimumWidth(360)
        layout = dialog.bodyLayout()
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(QLabel("选择价格库套价："))
        layout.addWidget(picker)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if not dialog.exec():
            return
        name = picker.currentText()
        mapping = library.get(name, {})
        if not mapping:
            FramelessMessageBox.warning(self, "批量载价", f"价格库 {name} 为空。")
            return
        overwrite = self._ask_overwrite()
        if overwrite is None:
            return
        count = 0
        for key, value in mapping.items():
            if overwrite or project_io.get_price(key) == 0.0:
                project_io.set_price(key, float(value))
                count += 1
        bus().status_message.emit(f"已载入 {count} 条单价。", 5000)
        self.refresh()

    def _ask_overwrite(self) -> bool | None:
        result = FramelessMessageBox.question(
            self,
            "批量载价",
            "是否覆盖当前已填写的价格信息？",
            FramelessMessageBox.StandardButton.Yes
            | FramelessMessageBox.StandardButton.No
            | FramelessMessageBox.StandardButton.Cancel,
            FramelessMessageBox.StandardButton.Yes,
            button_texts={
                FramelessMessageBox.StandardButton.Yes: "覆盖",
                FramelessMessageBox.StandardButton.No: "只补空",
            },
        )
        if result == FramelessMessageBox.StandardButton.Yes:
            return True
        if result == FramelessMessageBox.StandardButton.No:
            return False
        return None

    def _clear_prices(self) -> None:
        answer = FramelessMessageBox.question(
            self, "清空价格", "确定清空所有单价？",
            FramelessMessageBox.StandardButton.Yes | FramelessMessageBox.StandardButton.No,
            FramelessMessageBox.StandardButton.No,
        )
        if answer == FramelessMessageBox.StandardButton.Yes:
            project_io.clear_prices()
            self.refresh()

    def _export(self) -> None:
        if self._data is None:
            return
        target, _filter = QFileDialog.getSaveFileName(
            self, "导出 Excel", "工程数量表.xlsx", "Excel 工作簿 (*.xlsx)"
        )
        if not target:
            return
        try:
            excel_export.export_excel(target, self._data)
        except PermissionError:
            FramelessMessageBox.warning(self, "导出错误", "文件可能正在使用，请关闭后重试。")
            return
        bus().status_message.emit(f"已导出：{target}", 5000)


def _highlight():
    from app.resources.qss.theme import ThemeManager

    return QColor(ThemeManager.instance().current().primary_soft)
