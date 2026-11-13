"""汇总页：工程根 / 标段节点的费用汇总与综合单价汇总（主面板两个顶级 tab）。

主面板是按左侧选中节点性质切换的 tab 组：选中非子节点（工程根或标段）时
显示本控制器提供的「费用汇总表」与「综合单价汇总表」两个页面（见
:attr:`SummaryPanel.cost_page` / :attr:`SummaryPanel.price_page`）；
单位工程则显示构件列表 / 工程量明细表。右侧 AI 面板不受影响。

* 费用汇总表 —— 项目结构每个节点一行（合槽构件同款树状表格：序号列左侧
  +/- 展开方框、子行缩进竖线、父行浅色底），合价 = 该节点下所有工程量项
  合价的合计（叶子节点取自身，父节点取子节点合计）；
* 综合单价汇总表 —— 选中节点及其下属节点所有条目的工程量按键合并
  （相同条目累加），列：编号 / 类别 / 项目 / 单位 / 工程量 / 单价 / 合价；
  仅单价可编辑，合价 = 工程量 × 单价自动刷新；单价按“类别 + 项目”联动
  （改一处，同类别同项目的其他条目同步，见 ``summary.set_price_propagate``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.calc.tracer import QDict, fmt, sorted_items
from app.core.event_bus import bus, connect_weak
from app.resources.qss.theme import ThemeManager
from app.services import project_io
from app.services import summary as summary_service
from app.viewmodels.project_vm import KIND_PROJECT, KIND_SEGMENT, KIND_UNIT, TreeNode
from app.viewmodels.unit_vm import compute_unit
from app.views.widgets.table_width import fixed_width_behavior

# 合槽构件同款的树形列委托与角色（见 unit_panel）
from app.views.panels.unit_panel import (
    _FOCUS_OWNER_ATTR,
    _TREE_ROLE,
    _ElementNameDelegate,
)

_COST_HEADERS = ["序号", "名称", "合价"]
_COST_COL_SEQ, _COST_COL_NAME, _COST_COL_TOTAL = range(3)
#: 序号列兼作树形列：左侧留给 +/- 方框与缩进槽位，最深层级（单位工程）的
#: 编号（如 1.1.1）仍要整段显示。这里只是默认宽度，装填时按实际字宽兜底加宽
_COST_WIDTHS = [110, 340, 140]

_PRICE_HEADERS = ["编号", "类别", "项目", "单位", "工程量", "单价", "合价"]
_PCOL_NO, _PCOL_CAT, _PCOL_ITEM, _PCOL_UNIT, _PCOL_AMOUNT, _PCOL_PRICE, _PCOL_TOTAL = range(7)
_PRICE_WIDTHS = [64, 110, 220, 64, 130, 110, 140]

#: 费用表名称条目上的节点标识（(kind, id)；工程根 id 为 None）
_NODE_KEY_ROLE = Qt.ItemDataRole.UserRole + 3

#: 数据变更后的延迟重算（构件增删改时避免逐次全量重算拖慢录入）
_RELOAD_DELAY_MS = 300


@dataclass
class _CostNode:
    """费用汇总表的一棵节点行：序号（层级编号）+ 合价 + 子节点。"""

    seq: str
    name: str
    key: tuple  # (kind, id)：展开 / 收起状态标识
    indent: int
    total: float = 0.0
    children: list["_CostNode"] = field(default_factory=list)

    @property
    def has_children(self) -> bool:
        return bool(self.children)


class SummaryPanel(QObject):
    """汇总页控制器：费用汇总表页 + 综合单价汇总表页（主面板顶级 tab）。

    两个页面由主窗体加进主面板 tab 组；页面不可见（非当前 tab 或 tab 被
    隐藏）期间数据变化只标脏，切回时 :meth:`maybe_reload` 补一次重载。
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._node: TreeNode | None = None
        self._loading = False  # 程序化填装表格时屏蔽 itemChanged
        self._dirty = False  # 页面不可见期间数据变了，显示时补一次重载
        #: 收起节点的 (kind, id) 集合（仅视图状态，不入库）
        self._collapsed_keys: set[tuple] = set()
        #: 最近一次装缓的单位工程汇总（key → QDict）：改单价只重乘，不重算
        self._unit_summaries: dict[int, QDict] = {}
        #: 综合单价表行缓存（key / 类别 / 项目 / 单位 / 工程量）
        self._price_rows: list[dict] = []
        #: 单价索引（summary.price_maps 的快照，改单价后局部刷新）
        self._by_key: dict[str, float] = {}
        self._by_scope: dict[tuple[str, str], float] = {}
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(_RELOAD_DELAY_MS)
        self._reload_timer.timeout.connect(self._on_reload_timer)
        self.cost_page = self._build_cost_page()
        self.price_page = self._build_price_page()
        self._connect()

    # ------------------------------------------------------------------ 界面
    def _build_cost_page(self) -> QWidget:
        """费用汇总表页：项目结构每个节点一行（合槽构件同款树状表格）。"""
        page = QWidget()
        page.setProperty("role", "panel")
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(6, 6, 6, 6)
        page_layout.setSpacing(4)

        self._cost_table = self._make_table(_COST_HEADERS)
        for index, width in enumerate(_COST_WIDTHS):
            self._cost_table.setColumnWidth(index, width)
        # 序号列树形委托：父行 +/- 展开方框（点击切换），子行缩进竖线。
        # 表格开着交替行底色，委托自绘的序号列要跟着铺条纹色
        self._cost_table.setItemDelegateForColumn(
            _COST_COL_SEQ,
            _ElementNameDelegate(
                self._cost_table, self._on_node_toggle_requested, alt_rows=True
            ),
        )
        page_layout.addWidget(self._cost_table, 1)
        return page

    def _build_price_page(self) -> QWidget:
        """综合单价汇总表页：工程量合并行，仅单价列可编辑。"""
        page = QWidget()
        page.setProperty("role", "panel")
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(6, 6, 6, 6)
        page_layout.setSpacing(4)

        self._price_table = self._make_table(_PRICE_HEADERS)
        for index, width in enumerate(_PRICE_WIDTHS):
            self._price_table.setColumnWidth(index, width)
        # 单价列无边框编辑器（与主表格一致的编辑态）
        from app.views.widgets.table_edit_delegate import TableEditDelegate

        self._price_table.setItemDelegateForColumn(_PCOL_PRICE, TableEditDelegate(self._price_table))
        self._price_table.itemChanged.connect(self._on_price_item_changed)
        page_layout.addWidget(self._price_table, 1)
        return page

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        # 固定列宽（可拖动调整）：表格不随父控件拉伸（全项目约定）
        fixed_width_behavior(table)
        table.horizontalHeader().setHighlightSections(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.setWordWrap(False)
        setattr(table, _FOCUS_OWNER_ATTR, False)
        return table

    # ------------------------------------------------------------------ 数据刷新
    def set_node(self, node: TreeNode | None) -> None:
        """项目树选中变化：非子节点（工程根 / 标段）装填本页，None 清空。"""
        self._node = node
        if node is None:
            self._dirty = False
            self._price_table.setRowCount(0)
            self._cost_table.setRowCount(0)
            self._unit_summaries = {}
            self._price_rows = []
            return
        if self._any_page_visible():
            self._reload()
        else:
            self._dirty = True

    def maybe_reload(self) -> None:
        """主面板 tab 切换后调用：页面脏且当前可见时补一次重载。"""
        if self._dirty and self._any_page_visible():
            self._dirty = False
            self._reload()

    def _any_page_visible(self) -> bool:
        return self.cost_page.isVisible() or self.price_page.isVisible()

    def _connect(self) -> None:
        """数据变化联动：可见时延后重算，不可见时标脏（显示时补载）。"""
        connect_weak(bus().unit_changed, self, "_on_data_changed")
        connect_weak(bus().principle_changed, self, "_on_data_changed")
        bus().tree_structure_changed.connect(self._on_structure_changed)
        connect_weak(bus().project_closed, self, "set_node", None)

    def _on_data_changed(self, *_args) -> None:
        self._schedule_reload()

    def _on_structure_changed(self) -> None:
        # 树结构 / 节点名变化：立即按当前节点重载（标段单位增删、重命名）
        self._schedule_reload(immediate=True)

    def _schedule_reload(self, *, immediate: bool = False) -> None:
        if self._node is None:
            return
        if not self._any_page_visible():
            self._dirty = True
            return
        if immediate:
            self._reload_timer.stop()
            self._reload()
        else:
            self._reload_timer.start()

    def _on_reload_timer(self) -> None:
        if not self._any_page_visible():
            self._dirty = True
            return
        self._reload()

    def _reload(self) -> None:
        self._loading = True
        try:
            self._load_price_rows()
            self._fill_price_table()
            self._fill_cost_table()
        finally:
            self._loading = False

    def _scope_units(self) -> list[tuple[int, str]]:
        """当前节点范围内的单位工程 [(id, 名称)]：标段 → 下属单位工程；工程根 → 全部。"""
        node = self._node
        if node is None or not project_io.is_open():
            return []
        if node.is_segment:
            return [(unit.id, unit.name) for unit in project_io.units(node.id)]
        return [
            (unit.id, unit.name)
            for segment in project_io.segments()
            for unit in project_io.units(segment.id)
        ]

    def _load_price_rows(self) -> None:
        """全量装填：范围内单位工程逐个计算，QDict 合并（相同条目累加）。"""
        self._unit_summaries = {}
        merged = QDict()
        for unit_id, _name in self._scope_units():
            summary, _detail = compute_unit(unit_id)
            self._unit_summaries[unit_id] = summary
            merged.extend(summary)
        self._price_rows = []
        for quantity in sorted_items(merged):
            parts = quantity.key.split("|")
            self._price_rows.append(
                {
                    "key": quantity.key,
                    "category": parts[0] if parts else "",
                    "item": parts[1] if len(parts) > 1 else "",
                    "unit": parts[2] if len(parts) > 2 else "",
                    "amount": quantity.value,
                }
            )
        self._by_key, self._by_scope = summary_service.price_maps()

    # ------------------------------------------------------------------ 单价
    def _resolve_price(self, key: str) -> float:
        """单价解析：key 显式记录优先，否则回落同（类别, 项目）单价。"""
        return summary_service.resolve_price(key, self._by_key, self._by_scope)

    def _fill_price_table(self) -> None:
        table = self._price_table
        table.setRowCount(len(self._price_rows))
        for row_index, row in enumerate(self._price_rows):
            price = self._resolve_price(row["key"])
            cells = {
                _PCOL_NO: (str(row_index + 1), Qt.AlignmentFlag.AlignCenter),
                _PCOL_CAT: (row["category"], Qt.AlignmentFlag.AlignLeft),
                _PCOL_ITEM: (row["item"], Qt.AlignmentFlag.AlignLeft),
                _PCOL_UNIT: (row["unit"], Qt.AlignmentFlag.AlignCenter),
                _PCOL_AMOUNT: (fmt(row["amount"]), Qt.AlignmentFlag.AlignCenter),
                _PCOL_PRICE: (fmt(price), Qt.AlignmentFlag.AlignCenter),
                _PCOL_TOTAL: (fmt(row["amount"] * price), Qt.AlignmentFlag.AlignCenter),
            }
            for column, (text, alignment) in cells.items():
                item = QTableWidgetItem(text)
                item.setTextAlignment(alignment)
                if column != _PCOL_PRICE:  # 仅单价可编辑
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setForeground(QBrush(self._secondary_color()))
                table.setItem(row_index, column, item)

    def _on_price_item_changed(self, item: QTableWidgetItem) -> None:
        """单价编辑落定：按“类别 + 项目”联动写库，全表单价 / 合价与费用表合计同步刷新。"""
        if self._loading or item.column() != _PCOL_PRICE:
            return
        row_index = item.row()
        if row_index >= len(self._price_rows):
            return
        row = self._price_rows[row_index]
        text = item.text().strip()
        try:
            value = float(text)
        except ValueError:
            bus().status_message.emit(f"单价“{text}”不是有效数字。", 4000)
            self._loading = True
            try:
                item.setText(fmt(self._resolve_price(row["key"])))
            finally:
                self._loading = False
            return
        summary_service.set_price_propagate(row["key"], value)
        # 单价按类别 + 项目联动后重建索引，两块表格一起刷（只重乘，不重算工程量）
        self._loading = True
        try:
            self._by_key, self._by_scope = summary_service.price_maps()
            for index, entry in enumerate(self._price_rows):
                price = self._resolve_price(entry["key"])
                self._price_table.item(index, _PCOL_PRICE).setText(fmt(price))
                self._price_table.item(index, _PCOL_TOTAL).setText(
                    fmt(entry["amount"] * price)
                )
            self._fill_cost_table()
        finally:
            self._loading = False

    # ------------------------------------------------------------------ 费用汇总
    def _unit_total(self, unit_id: int) -> float:
        """单位工程合价：Σ(工程量 × 单价)，用缓存的汇总（改单价不重算）。"""
        summary = self._unit_summaries.get(unit_id)
        if summary is None:
            return 0.0
        return sum(
            quantity.value * self._resolve_price(quantity.key)
            for quantity in summary.items()
        )

    def _build_cost_nodes(self) -> list[_CostNode]:
        """项目结构 → 费用树：工程根（或选中标段）为根，合价自下而上合计。"""
        node = self._node
        if node is None or not project_io.is_open():
            return []
        if node.is_segment:
            segment = next((s for s in project_io.segments() if s.id == node.id), None)
            if segment is None:
                return []
            return [self._make_segment_node(segment, "1", 0)]
        root = _CostNode(
            seq="1",
            name=project_io.project_name() or "未命名工程",
            key=(KIND_PROJECT, None),
            indent=0,
        )
        for index, segment in enumerate(project_io.segments(), start=1):
            root.children.append(self._make_segment_node(segment, f"1.{index}", 1))
        root.total = sum(child.total for child in root.children)
        return [root]

    def _make_segment_node(self, segment, seq: str, indent: int) -> _CostNode:
        node = _CostNode(seq=seq, name=segment.name, key=(KIND_SEGMENT, segment.id), indent=indent)
        for index, unit in enumerate(project_io.units(segment.id), start=1):
            child = _CostNode(
                seq=f"{seq}.{index}",
                name=unit.name,
                key=(KIND_UNIT, unit.id),
                indent=indent + 1,
            )
            child.total = self._unit_total(unit.id)
            node.children.append(child)
        node.total = sum(child.total for child in node.children)
        return node

    def _fill_cost_table(self) -> None:
        nodes = self._build_cost_nodes()
        flat: list[_CostNode] = []

        def walk(node: _CostNode) -> None:
            flat.append(node)
            if node.has_children and node.key not in self._collapsed_keys:
                for child in node.children:
                    walk(child)

        for node in nodes:
            walk(node)

        table = self._cost_table
        table.setRowCount(len(flat))
        highlight = QBrush(QColor(ThemeManager.instance().current().primary_soft))
        for row_index, node in enumerate(flat):
            seq_item = QTableWidgetItem(node.seq)
            seq_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            seq_item.setFlags(seq_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            seq_item.setForeground(QBrush(self._secondary_color()))
            # 序号列是树形列：+/- 方框画在编号左侧，子行按层级缩进（委托自绘）
            seq_item.setData(
                _TREE_ROLE,
                {
                    "indent": node.indent,
                    "has_children": node.has_children,
                    "expanded": node.key not in self._collapsed_keys,
                },
            )
            seq_item.setData(_NODE_KEY_ROLE, node.key)
            if node.has_children:
                seq_item.setToolTip("点击 +/- 展开或收起下级节点。")

            name_item = QTableWidgetItem(node.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            total_item = QTableWidgetItem(fmt(node.total))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if node.has_children:
                # 父行浅色底（合槽父行同款；序号列底色由委托自绘）
                for item in (seq_item, name_item, total_item):
                    item.setBackground(highlight)
            table.setItem(row_index, _COST_COL_SEQ, seq_item)
            table.setItem(row_index, _COST_COL_NAME, name_item)
            table.setItem(row_index, _COST_COL_TOTAL, total_item)
        self._fit_cost_seq_column(flat)

    def _fit_cost_seq_column(self, flat: list[_CostNode]) -> None:
        """序号列兼树形列：按最深层级编号的实际字宽兜底加宽，避免缩进后裁字。

        只加宽不缩窄——用户手动拖宽的列宽保持不动。
        """
        delegate_cls = _ElementNameDelegate
        self._cost_table.ensurePolished()  # 先刷上 QSS 的 13px 字体再量字宽
        metrics = self._cost_table.fontMetrics()
        needed = max(
            (
                delegate_cls.LEFT_PADDING
                + delegate_cls.INDENT_UNIT * node.indent
                + delegate_cls.ICON_SIZE
                + delegate_cls.TEXT_MARGIN
                + metrics.horizontalAdvance(node.seq)
                + delegate_cls.LEFT_PADDING
                for node in flat
            ),
            default=0,
        )
        if needed > self._cost_table.columnWidth(_COST_COL_SEQ):
            self._cost_table.setColumnWidth(_COST_COL_SEQ, needed)

    def _on_node_toggle_requested(self, row_index: int) -> None:
        """点击父行 +/- 方框：切换展开 / 收起并重排费用表。"""
        item = self._cost_table.item(row_index, _COST_COL_SEQ)
        if item is None:
            return
        meta = item.data(_TREE_ROLE)
        key = item.data(_NODE_KEY_ROLE)
        if not (meta and meta.get("has_children")) or key is None:
            return
        if key in self._collapsed_keys:
            self._collapsed_keys.discard(key)
        else:
            self._collapsed_keys.add(key)
        self._fill_cost_table()

    # ------------------------------------------------------------------ 辅助
    @staticmethod
    def _secondary_color() -> QColor:
        return QColor(ThemeManager.instance().current().text_secondary)
