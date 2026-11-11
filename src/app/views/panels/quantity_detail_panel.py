"""工程量明细表：单位工程节点的工程量计算表（主面板顶级 tab）。

表格内容与「导出 Excel」的工程数量表同源（去掉表达式 / 算式两列）：行前
带“编号”列（内容与构件列表详情面板 定额 / 清单工程量 tab 首列一致：清单
项目行填“清单项目”、定额拆分行留空），列见 :data:`_HEADERS`（编号 / 类别 /
名称 / 单位 / 数量 / 单价 / 合价），清单项目行按导出规则整行浅蓝底色。
单价列参照综合单价汇总表交互：可编辑，按“项目”名全项目联动写库（见
``summary.set_price_propagate``）；合价 = 数量 × 单价自动算出，不可编辑。
清单项目行（清单表）的单价 / 合价为派生值：合价 = 该条目下所有定额工程量
行合价的合计，单价 = 合价 ÷ 数量，不可编辑、随定额行单价联动刷新。
定额 / 清单两张表（对应 xlsx 两张 sheet）用页内分段控件切换（Apple HIG
同款，避免与主面板 tab 连成两行）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.event_bus import bus, connect_weak
from app.core.calc.tracer import fmt
from app.resources.qss.theme import ThemeManager
from app.services import project_io
from app.services import summary as summary_service
from app.viewmodels.unit_vm import compute_unit
from app.views.widgets.table_edit_delegate import TableEditDelegate
from app.views.widgets.table_width import fixed_width_behavior

# 与导出 Excel 同源：行生成器与清单行底色（导出同款浅蓝）
from app.services.summary import (
    _LISTING_FILL,
    _QUOTA_WIDTHS,
    _listing_rows,
    _quota_rows,
)

#: 页面表格列：编号 + 类别/名称/单位/数量 + 单价/合价（编号列内容与构件
#: 列表详情面板定额 / 清单工程量 tab 首列一致，单价列交互同综合单价汇总表）
_HEADERS = ["编号", "类别", "名称", "单位", "数量", "单价", "合价"]
_COL_NO, _COL_CAT, _COL_NAME, _COL_UNIT, _COL_AMOUNT, _COL_PRICE, _COL_TOTAL = range(7)
_WIDTHS = (77, *(width * 8 for width in _QUOTA_WIDTHS[:4]), 110, 140)

#: 清单项目行标识（存首列条目，委托据此整行画浅蓝底）
_LISTING_ROLE = Qt.ItemDataRole.UserRole + 4

#: 单价条目 key（类别|项目|单位，存单价列条目）与数量浮点值（存数量列条目）
_PRICE_KEY_ROLE = Qt.ItemDataRole.UserRole + 5
_AMOUNT_ROLE = Qt.ItemDataRole.UserRole + 6

#: 清单项目行浅蓝底（#D6EAF8）固定配的深色文字：暗色主题下默认亮字在浅蓝底上看不清
_LISTING_TEXT = "#17324F"

#: 数据变更后的延迟重算（构件增删改时避免逐次全量重算拖慢录入）
_RELOAD_DELAY_MS = 300


class _ListingRowDelegate(TableEditDelegate):
    """清单项目行整行浅蓝底（导出 Excel 同款）+ 单价列编辑态抛光。

    全局 QSS 的 ``QTableWidget::item { background-color: transparent; }``
    会盖掉逐条目 ``setBackground`` 设置的底色，必须由委托在默认绘制前自绘。
    继承 :class:`TableEditDelegate` 让可编辑的单价列获得同款无边框编辑器。
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
        #: 单价索引（summary.price_maps 的快照，改单价后局部刷新）
        self._by_key: dict[str, float] = {}
        self._by_item: dict[str, float] = {}
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
        layout.setSpacing(6)

        self._quota_table = self._make_table(_HEADERS)
        self._listing_table = self._make_table(_HEADERS)
        self._quota_table.itemChanged.connect(self._on_price_item_changed)
        self._listing_table.itemChanged.connect(self._on_price_item_changed)
        self._tables = QStackedWidget()
        self._tables.addWidget(self._quota_table)   # 段 0：定额工程量
        self._tables.addWidget(self._listing_table)  # 段 1：清单工程量

        # 页内同层视图切换用分段控件（Apple HIG 同款），避免与主面板 tab 连成两行
        seg_row = QHBoxLayout()
        seg_row.setContentsMargins(0, 0, 0, 0)
        seg_row.addWidget(self._build_segment_control())
        seg_row.addStretch(1)
        layout.addLayout(seg_row)
        layout.addWidget(self._tables, 1)

    def _build_segment_control(self) -> QWidget:
        """灰底圆角轨道 + 两段互斥按钮（定额工程量 / 清单工程量）。"""
        host = QWidget()
        host.setProperty("role", "segment-host")
        host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        seg_layout = QHBoxLayout(host)
        seg_layout.setContentsMargins(2, 2, 2, 2)
        seg_layout.setSpacing(2)
        self._segment_group = QButtonGroup(self)
        self._segment_group.setExclusive(True)
        for index, text in enumerate(("定额工程量", "清单工程量")):
            button = QPushButton(text)
            button.setProperty("role", "segment-btn")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(index == 0)
            self._segment_group.addButton(button, index)
            seg_layout.addWidget(button)
        self._segment_group.idClicked.connect(self._tables.setCurrentIndex)
        return host

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
            quota_rows = [
                (row[:4], False) for row in _quota_rows(summary, with_expression=False)
            ]
            listing_rows = [
                (row[:4], is_listing)
                for row, is_listing in _listing_rows(detail, with_expression=False)
            ]
            self._by_key, self._by_item = summary_service.price_maps()
            self._fill_table(self._quota_table, quota_rows)
            self._fill_table(self._listing_table, listing_rows)
        finally:
            self._loading = False

    def _fill_table(self, table: QTableWidget, rows: list[tuple[list, bool]]) -> None:
        """把 (值, 是否清单项目行) 行列表写进表格。

        值 = (类别, 名称, 单位, 数量)；编号列内容与构件列表详情面板定额 /
        清单工程量 tab 首列一致（清单项目行填“清单项目”，其余留空）。定额行
        单价可编辑（key = 类别|项目|单位），合价 = 数量 × 单价自动算出；清单
        项目行的合价 = 该条目下所有定额工程量行合价的合计、单价 = 合价 ÷
        数量（派生值，不可编辑），随定额行单价联动刷新；清单项目行整行浅蓝
        （委托自绘）。
        """
        table.setRowCount(len(rows))
        for row_index, (values, is_listing) in enumerate(rows):
            category, name, unit, amount = values[:4]
            amount = float(amount)
            price_key: str | None = None
            if is_listing:
                # 清单项目行：合价 = 该条目下所有定额工程量行合价合计，
                # 单价 = 合价 ÷ 数量（不写库，随定额行单价联动）
                total = 0.0
                for child_values, child_is_listing in rows[row_index + 1:]:
                    if child_is_listing:
                        break
                    child_category, child_name, child_unit, child_amount = child_values[:4]
                    child_amount = float(child_amount)
                    child_key = f"{child_category}|{child_name}|{child_unit}"
                    total += child_amount * self._resolve_price(child_key, child_name)
                price = total / amount if amount else 0.0
            else:
                price_key = f"{category}|{name}|{unit}"
                price = self._resolve_price(price_key, name)
                total = amount * price
            texts = (
                "清单项目" if is_listing else "",
                str(category),
                str(name),
                str(unit),
                f"{amount:.4f}".rstrip("0").rstrip("."),
                fmt(price),
                fmt(total),
            )
            for column, text in enumerate(texts):
                item = QTableWidgetItem(text)
                if column == _COL_PRICE and price_key is not None:
                    item.setData(_PRICE_KEY_ROLE, price_key)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if is_listing:
                        # 浅蓝底固定配深色文字（暗色主题下亮字在浅蓝底上看不清）
                        item.setForeground(QBrush(QColor(_LISTING_TEXT)))
                    elif column == _COL_NO:
                        item.setForeground(QBrush(self._secondary_color()))
                if column == _COL_AMOUNT:
                    item.setData(_AMOUNT_ROLE, amount)
                if column == _COL_NO and is_listing:
                    item.setData(_LISTING_ROLE, True)
                table.setItem(row_index, column, item)

    # ------------------------------------------------------------------ 单价
    def _resolve_price(self, key: str, item: str) -> float:
        """key 显式记录优先，无记录回落到同“项目”名单价（按项目名全局联动）。"""
        price = self._by_key.get(key)
        if price is not None:
            return price
        return self._by_item.get(item, 0.0)

    def _on_price_item_changed(self, item: QTableWidgetItem) -> None:
        """单价编辑落定：按“项目”名联动写库，两表单价 / 合价同步重乘刷新。"""
        if self._loading or item.column() != _COL_PRICE:
            return
        price_key = item.data(_PRICE_KEY_ROLE)
        if price_key is None:
            return
        text = item.text().strip()
        try:
            value = float(text)
        except ValueError:
            bus().status_message.emit(f"单价“{text}”不是有效数字。", 4000)
            self._loading = True
            try:
                item.setText(fmt(self._resolve_price(price_key, self._item_of(price_key))))
            finally:
                self._loading = False
            return
        summary_service.set_price_propagate(price_key, value)
        # 单价按项目名联动后重建索引，两表一起刷（只重乘，不重算工程量）
        self._loading = True
        try:
            self._by_key, self._by_item = summary_service.price_maps()
            self._refresh_price_cells()
        finally:
            self._loading = False

    def _refresh_price_cells(self) -> None:
        """按最新单价索引重写两表的单价 / 合价（数量不重算）。

        定额行单价 / 合价重乘；清单项目行合价 = 其下定额行合价合计、
        单价 = 合价 ÷ 数量，随定额行联动重算。
        """
        for table in (self._quota_table, self._listing_table):
            for row in range(table.rowCount()):
                price_item = table.item(row, _COL_PRICE)
                if price_item is None:
                    continue
                price_key = price_item.data(_PRICE_KEY_ROLE)
                if price_key is None:
                    continue
                amount_item = table.item(row, _COL_AMOUNT)
                if amount_item is None:
                    continue
                amount = amount_item.data(_AMOUNT_ROLE)
                if amount is None:
                    continue
                price = self._resolve_price(price_key, self._item_of(price_key))
                price_item.setText(fmt(price))
                total_item = table.item(row, _COL_TOTAL)
                if total_item is not None:
                    total_item.setText(fmt(amount * price))
        self._refresh_listing_derived_cells()

    def _refresh_listing_derived_cells(self) -> None:
        """清单项目行的派生单价 / 合价：合价 = 其下定额行合价合计，单价 = 合价 ÷ 数量。"""
        table = self._listing_table
        for row in range(table.rowCount()):
            no_item = table.item(row, _COL_NO)
            if no_item is None or not no_item.data(_LISTING_ROLE):
                continue
            amount_item = table.item(row, _COL_AMOUNT)
            if amount_item is None:
                continue
            amount = amount_item.data(_AMOUNT_ROLE)
            if amount is None:
                continue
            total = 0.0
            for child in range(row + 1, table.rowCount()):
                child_no = table.item(child, _COL_NO)
                if child_no is not None and child_no.data(_LISTING_ROLE):
                    break
                child_price_item = table.item(child, _COL_PRICE)
                child_amount_item = table.item(child, _COL_AMOUNT)
                if child_price_item is None or child_amount_item is None:
                    continue
                child_key = child_price_item.data(_PRICE_KEY_ROLE)
                child_amount = child_amount_item.data(_AMOUNT_ROLE)
                if child_key is None or child_amount is None:
                    continue
                total += float(child_amount) * self._resolve_price(child_key, self._item_of(child_key))
            price_item = table.item(row, _COL_PRICE)
            if price_item is not None:
                price_item.setText(fmt(total / amount if amount else 0.0))
            total_item = table.item(row, _COL_TOTAL)
            if total_item is not None:
                total_item.setText(fmt(total))

    @staticmethod
    def _item_of(price_key: str) -> str:
        parts = price_key.split("|")
        return parts[1] if len(parts) > 1 else ""

    @staticmethod
    def _secondary_color() -> QColor:
        return QColor(ThemeManager.instance().current().text_secondary)
