"""工程量明细表：单位工程节点的工程量计算表（主面板顶级 tab）。

表格内容与「导出 Excel」的工程数量表一致（分单位工程口径，去掉表达式 /
算式两列）：行前带“单位工程”列，定额工程量 / 清单工程量两张子表对应
xlsx 的两张 sheet，列见 :data:`_HEADERS`（单位工程 / 类别 / 名称 / 单位 /
数量），清单项目行按导出规则整行浅蓝底色。页面只读，随构件改动自动刷新。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QStyledItemDelegate,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.event_bus import bus, connect_weak
from app.resources.qss.theme import ThemeManager
from app.services import project_io
from app.viewmodels.unit_vm import compute_unit
from app.views.widgets.table_width import fixed_width_behavior

# 与导出 Excel 同源：行生成器与清单行底色（导出同款浅蓝）
from app.services.summary import (
    _LISTING_FILL,
    _QUANTITY_HEADERS,
    _QUOTA_WIDTHS,
    _UNIT_COL_WIDTH,
    _listing_rows,
    _quota_rows,
)

#: 页面表格列：单位工程 + 类别/名称/单位/数量（导出 Excel 去掉表达式、算式两列）
_HEADERS = ["单位工程", *_QUANTITY_HEADERS[:4]]
_WIDTHS = (_UNIT_COL_WIDTH * 8, *(width * 8 for width in _QUOTA_WIDTHS[:4]))

#: 清单项目行标识（存首列条目，委托据此整行画浅蓝底）
_LISTING_ROLE = Qt.ItemDataRole.UserRole + 4

#: 数据变更后的延迟重算（构件增删改时避免逐次全量重算拖慢录入）
_RELOAD_DELAY_MS = 300


class _ListingRowDelegate(QStyledItemDelegate):
    """清单项目行整行浅蓝底（导出 Excel 同款）。

    全局 QSS 的 ``QTableWidget::item { background-color: transparent; }``
    会盖掉逐条目 ``setBackground`` 设置的底色，必须由委托在默认绘制前自绘。
    """

    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self._table = table

    def paint(self, painter, option, index) -> None:
        item = self._table.item(index.row(), 0)
        if item is not None and item.data(_LISTING_ROLE):
            painter.save()
            painter.fillRect(option.rect, QColor(f"#{_LISTING_FILL}"))
            painter.restore()
        super().paint(painter, option, index)


class QuantityDetailPanel(QWidget):
    """工程量明细表页：定额工程量 / 清单工程量两张子表（对应 xlsx 两张 sheet）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._node = None
        self._loading = False  # 程序化填装表格时屏蔽信号
        self._dirty = False  # 页面不可见期间数据变了，显示时补一次重载
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(_RELOAD_DELAY_MS)
        self._reload_timer.timeout.connect(self._on_reload_timer)
        self._build_ui()
        connect_weak(bus().unit_changed, self, "_on_data_changed")
        connect_weak(bus().principle_changed, self, "_on_data_changed")
        connect_weak(bus().project_closed, self, "set_node", None)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        tabs = QTabWidget()
        from app.views.widgets.mac_window import is_mac

        if not is_mac():
            tabs.setDocumentMode(True)
        tabs.tabBar().setDrawBase(False)
        self._quota_table = self._make_table(_HEADERS)
        self._listing_table = self._make_table(_HEADERS)
        tabs.addTab(self._quota_table, "定额工程量")
        tabs.addTab(self._listing_table, "清单工程量")
        layout.addWidget(tabs, 1)

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(False)  # 单元格同色，不按行间隔变色
        # 固定列宽（可拖动调整）：表格不随父控件拉伸（全项目约定）
        fixed_width_behavior(table)
        table.horizontalHeader().setHighlightSections(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.setWordWrap(False)
        # 列宽沿用导出 Excel 的字符宽（×8 ≈ px）
        for index, width in enumerate(_WIDTHS):
            table.setColumnWidth(index, width)
        # 清单项目行浅蓝底：QSS 盖掉 item 底色，须委托自绘
        table.setItemDelegate(_ListingRowDelegate(table))
        return table

    # ------------------------------------------------------------------ 数据刷新
    def set_node(self, node) -> None:
        """项目树选中变化：单位工程节点装填本页，None 清空。"""
        self._node = node
        if node is None:
            self._dirty = False
            self._quota_table.setRowCount(0)
            self._listing_table.setRowCount(0)
            return
        if self.isVisible():
            self._reload()
        else:
            self._dirty = True

    def maybe_reload(self) -> None:
        """主面板 tab 切换后调用：页面脏且当前可见时补一次重载。"""
        if self._dirty and self.isVisible():
            self._dirty = False
            self._reload()

    def _on_data_changed(self, *_args) -> None:
        if self._node is None:
            return
        if not self.isVisible():
            self._dirty = True
            return
        self._reload_timer.start()

    def _on_reload_timer(self) -> None:
        if not self.isVisible():
            self._dirty = True
            return
        self._reload()

    def _reload(self) -> None:
        self._loading = True
        try:
            node = self._node
            if node is None or not project_io.is_open():
                self._quota_table.setRowCount(0)
                self._listing_table.setRowCount(0)
                return
            # 与导出 Excel（分单位工程口径）同源：compute_unit → 行生成器。
            # 本页不显示算式两列，with_expression=False 跳过主算式解析
            # （该解析极重，是切换节点卡顿的元凶）
            summary, detail = compute_unit(node.id)
            unit_name = node.name
            quota_rows = [
                ([unit_name, *row], False)
                for row in _quota_rows(summary, with_expression=False)
            ]
            listing_rows = [
                ([unit_name, *row], is_listing)
                for row, is_listing in _listing_rows(detail, with_expression=False)
            ]
            self._fill_table(self._quota_table, quota_rows)
            self._fill_table(self._listing_table, listing_rows)
        finally:
            self._loading = False

    def _fill_table(self, table: QTableWidget, rows: list[tuple[list, bool]]) -> None:
        """把 (值, 是否清单项目行) 行列表写进表格：清单项目行整行浅蓝（委托自绘）。"""
        table.setRowCount(len(rows))
        for row_index, (values, is_listing) in enumerate(rows):
            for column, text in enumerate(values[: len(_HEADERS)]):
                if column == 4:  # “数量”列：float 按 0.#### 规则显示
                    display = f"{float(text):.4f}".rstrip("0").rstrip(".")
                else:
                    display = str(text)
                item = QTableWidgetItem(display)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 0:
                    item.setForeground(QBrush(self._secondary_color()))
                    if is_listing:
                        item.setData(_LISTING_ROLE, True)
                table.setItem(row_index, column, item)

    @staticmethod
    def _secondary_color() -> QColor:
        return QColor(ThemeManager.instance().current().text_secondary)
