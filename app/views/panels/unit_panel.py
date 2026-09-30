"""中部工作区：单位工程（计划 §7.1、§7.2）。

上部：构件录入表（复刻旧版 dGVmain）。
下部横向三栏（旧版 FormUnit 的 spltCtnerR 布局）：
  左  选中构件的明细（管材 / 构件参数）；
  中  工程量表（定额工程量 / 清单工程量）——“计算表达式”列在“工程量”列之前；
  右  断面示意图（旧版 mcPictureBox，随选中构件联动重绘）。

埋深、数量两列允许写算式（如 2.5+0.3）：单元格 tooltip 显示求值结果，
算式不合法时用警示色标出并给出原因，不静默按 0 处理。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStyledItemDelegate,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.evaluator import EvalError, evaluate, format_number
from app.core.event_bus import bus
from app.orm.models import CATEGORY_CHOICES, CATEGORY_NAMES, category_name
from app.resources.qss.theme import ThemeManager
from app.services import project_io
from app.viewmodels.project_vm import TreeNode
from app.viewmodels.unit_vm import ElementRow, ParamRow, PipeRow, UnitViewModel
from app.views.widgets.frameless_dialog import FramelessMessageBox

_ELEMENT_ROLE = Qt.ItemDataRole.UserRole + 1
_COL_NAME, _COL_CATEGORY, _COL_SPEC, _COL_DEPTH, _COL_UNIT, _COL_AMOUNT, _COL_PE, _COL_PF, _COL_SOURCE = range(9)
_ELEMENT_HEADERS = ["名称", "类型", "规格", "埋深", "单位", "数量", "沟槽围护原则", "地基处理原则", "来源"]
#: 复刻旧版 dGVmain 列结构（规格 / 来源列只读）
#: 类型与沟槽围护原则列同宽；围护/地基原则列须完整显示下拉框里 6 个字；
#: 规格列取两倍宽；埋深/单位/数量三列文字在填充时居中
_ELEMENT_WIDTHS = [130, 110, 280, 60, 40, 70, 130, 130, 80]

_QUANTITY_HEADERS = ["编号", "类别", "项目", "单位", "计算表达式", "工程量"]
_QCOL_EXPRESSION = 4
_QCOL_AMOUNT = 5

_PIPE_ROLE = Qt.ItemDataRole.UserRole + 1
_PIPE_HEADERS = ["管材", "管径(mm)", "含量"]
_PARAM_ROLE = Qt.ItemDataRole.UserRole + 1
_PARAM_HEADERS = ["参数名", "参数值"]

#: 共享单元格焦点的归属标记（挂在 QTableWidget 实例属性上，Quotor _GLOBAL_LATEST 同款）
_FOCUS_OWNER_ATTR = "_unit_panel_focus_owner"


class _FocusCellDelegate(QStyledItemDelegate):
    """当前单元格用加粗边框表示（Quotor FullCellDelegate 同款）。

    主表格与下方面板（管材/构件参数/定额工程量/清单工程量）共享唯一焦点：
    只有"最新点选"的那张表（``_FOCUS_OWNER_ATTR`` 为 True）绘制当前单元格
    边框，其余表的选中行保持普通高亮，不画边框。
    """

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802 - Qt 命名
        view = self.parent()
        is_focus_cell = (
            isinstance(view, QTableWidget)
            and getattr(view, _FOCUS_OWNER_ATTR, False)
            and view.currentIndex() == index
        )
        # 去掉默认的虚线焦点框，统一用边框表示
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)
        if not is_focus_cell:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor(ThemeManager.instance().current().table_selected_border), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRect(option.rect).adjusted(1, 1, -2, -2))
        painter.restore()


class UnitPanel(QWidget):
    """单位工程工作台。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self._vm = UnitViewModel()
        self._unit_id: int | None = None
        self._loading = False
        self._build_ui()
        self._connect()
        self._show_unit(None)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_element_table())
        splitter.addWidget(self._build_bottom_area())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([240, 560])
        self._work_area = splitter
        layout.addWidget(splitter, 1)

        self._placeholder = QLabel("请先在左侧选择单位工程。")
        self._placeholder.setProperty("role", "placeholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._placeholder, 1)
        self._placeholder.setVisible(False)

    def _make_button(self, text: str, tooltip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setProperty("role", "icon-btn")
        button.clicked.connect(slot)
        return button

    def _build_element_table(self) -> QTableWidget:
        self._element_table = self._make_table(_ELEMENT_HEADERS)
        for index, width in enumerate(_ELEMENT_WIDTHS[:-1]):
            self._element_table.setColumnWidth(index, width)
        self._element_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._element_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._element_table.setSortingEnabled(False)
        self._element_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._element_table.customContextMenuRequested.connect(self._on_element_context_menu)
        self._element_table.installEventFilter(self)
        return self._element_table

    def _build_bottom_area(self) -> QWidget:
        """横向三栏：构件明细（管材/构件参数）｜工程量表（定额/清单）｜断面示意图。"""
        bottom = QSplitter(Qt.Orientation.Horizontal)

        # 左：选中构件的明细
        detail = QTabWidget()
        self._pipe_table = self._make_table(_PIPE_HEADERS)
        self._param_table = self._make_table(_PARAM_HEADERS)

        pipe_page = QWidget()
        pipe_layout = QVBoxLayout(pipe_page)
        pipe_layout.setContentsMargins(6, 6, 6, 6)
        pipe_layout.setSpacing(4)
        pipe_bar = QHBoxLayout()
        pipe_bar.addWidget(self._make_button("＋管材", "为选中构件新增一行管材", self._add_pipe))
        pipe_bar.addWidget(self._make_button("✕", "删除选中管材", self._delete_pipe))
        pipe_bar.addStretch(1)
        pipe_layout.addLayout(pipe_bar)
        pipe_layout.addWidget(self._pipe_table, 1)

        param_page = QWidget()
        param_layout = QVBoxLayout(param_page)
        param_layout.setContentsMargins(6, 6, 6, 6)
        param_layout.setSpacing(4)
        param_bar = QHBoxLayout()
        param_bar.addWidget(self._make_button("＋参数", "为选中构件新增一行参数", self._add_param))
        param_bar.addWidget(self._make_button("✕", "删除选中参数", self._delete_param))
        param_bar.addStretch(1)
        param_layout.addLayout(param_bar)
        param_layout.addWidget(self._param_table, 1)

        detail.addTab(pipe_page, "管材")
        detail.addTab(param_page, "构件参数")
        self._detail_tabs = detail
        bottom.addWidget(detail)

        # 中：工程量表（定额工程量 / 清单工程量）
        bottom.addWidget(self._build_quantity_area())

        # 右：断面示意图（旧版 FormUnit 右侧 spltCtnerR.Panel2）
        section_page = QWidget()
        section_layout = QVBoxLayout(section_page)
        section_layout.setContentsMargins(6, 6, 6, 6)
        section_layout.setSpacing(4)
        section_title = QLabel("断 面 示 意 图")
        section_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        section_layout.addWidget(section_title)
        from app.views.panels.section_view import SectionView

        self._section_view = SectionView()
        section_layout.addWidget(self._section_view, 1)
        bottom.addWidget(section_page)

        bottom.setStretchFactor(0, 2)
        bottom.setStretchFactor(1, 3)
        bottom.setStretchFactor(2, 2)
        bottom.setSizes([300, 440, 300])
        return bottom

    def _build_quantity_area(self) -> QWidget:
        tabs = QTabWidget()
        self._quantity_tables: dict[str, QTableWidget] = {}
        for name in ("定额工程量", "清单工程量"):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(6, 6, 6, 6)
            page_layout.setSpacing(4)
            table = self._make_table(_QUANTITY_HEADERS)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setWordWrap(False)
            table.itemDoubleClicked.connect(self._show_expression_detail)
            self._quantity_tables[name] = table
            page_layout.addWidget(table, 1)
            tabs.addTab(page, name)
        self._quantity_tabs = tabs
        return tabs

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # 行高与 Quotor 计价主表一致（32px）：表格内嵌下拉框的纵向内边距
        # 已在 QSS 里压到 2px，32px 行高足以完整显示文字
        table.verticalHeader().setDefaultSectionSize(32)
        table.setWordWrap(False)
        table.setItemDelegate(_FocusCellDelegate(table))
        setattr(table, _FOCUS_OWNER_ATTR, False)
        return table

    def _focus_tables(self) -> list[QTableWidget]:
        """共享单元格焦点的五张表：主表格 + 管材/构件参数/定额/清单。"""
        return [
            self._element_table,
            self._pipe_table,
            self._param_table,
            *self._quantity_tables.values(),
        ]

    def _mark_focus_table(self, table: QTableWidget) -> None:
        """把共享焦点转移到 table：只有它绘制当前单元格边框。"""
        for other in self._focus_tables():
            is_owner = other is table
            if getattr(other, _FOCUS_OWNER_ATTR, False) != is_owner:
                setattr(other, _FOCUS_OWNER_ATTR, is_owner)
                other.viewport().update()

    def _connect(self) -> None:
        self._vm.unit_loaded.connect(self._on_unit_loaded)
        self._vm.detail_loaded.connect(self._on_detail_loaded)
        self._vm.error_occurred.connect(lambda message: bus().status_message.emit(message, 4000))
        self._element_table.itemChanged.connect(self._on_element_item_changed)
        self._element_table.currentCellChanged.connect(self._on_current_element_changed)
        self._pipe_table.itemChanged.connect(self._on_pipe_item_changed)
        self._param_table.itemChanged.connect(self._on_param_item_changed)
        # 共享单元格焦点：任一表被点选/键盘导航即成为焦点归属表
        for table in self._focus_tables():
            table.cellClicked.connect(lambda _row, _col, t=table: self._mark_focus_table(t))
            table.currentCellChanged.connect(
                lambda _r, _c, _pr, _pc, t=table: self._mark_focus_table(t)
            )
        setattr(self._element_table, _FOCUS_OWNER_ATTR, True)  # 初始焦点在主表格
        bus().node_selected.connect(self._on_node_selected)
        bus().project_closed.connect(lambda: self._show_unit(None))
        bus().project_opened.connect(lambda _path: self._show_unit(None))

    # ------------------------------------------------------------------ 选中
    def _on_node_selected(self, node: TreeNode | None) -> None:
        if node is not None and node.is_unit:
            self._show_unit(node.id, node.name)
        # 选中其它节点时保留当前内容，切回来不用重新加载

    def _show_unit(self, unit_id: int | None, name: str = "") -> None:
        self._unit_id = unit_id
        has_unit = unit_id is not None
        self._placeholder.setVisible(not has_unit)
        self._work_area.setVisible(has_unit)
        if not has_unit:
            self._vm.load_unit(None)
            self._element_table.setRowCount(0)
            self._pipe_table.setRowCount(0)
            self._param_table.setRowCount(0)
            self._section_view.set_element(None)
            return
        self._vm.load_unit(unit_id)

    # ------------------------------------------------------------------ 构件表
    def _on_unit_loaded(self, unit_id: int, rows: list[ElementRow]) -> None:
        if unit_id != self._unit_id:
            return
        keep_element = self._current_element_id()
        keep_column = self._element_table.currentColumn()
        self._loading = True
        try:
            self._element_table.setRowCount(len(rows))
            enclosure_names = _combo_names(project_io.enclosure_names(), rows, "pe_name")
            foundation_names = _combo_names(project_io.foundation_names(), rows, "pf_name")
            for index, row in enumerate(rows):
                self._fill_element_row(index, row, enclosure_names, foundation_names)
        finally:
            self._loading = False
        self._restore_current_element(keep_element, keep_column)
        self._fill_quantities()
        self._section_view.set_element(self._current_element_id())

    def _fill_quantities(self) -> None:
        """计算并填充工程量表（定额汇总 / 清单逐构件，含计算表达式列）。"""
        from app.services.calc.tracer import fmt as calc_fmt
        from app.services.calc.tracer import sorted_items
        from app.viewmodels.unit_vm import compute_unit

        if self._unit_id is None:
            for table in self._quantity_tables.values():
                table.setRowCount(0)
            return
        summary, detail = compute_unit(self._unit_id)

        digests = self._quantity_tables["定额工程量"]
        digests.setRowCount(0)
        quantities = sorted_items(summary)
        digests.setRowCount(len(quantities))
        for row_index, quantity in enumerate(quantities):
            parts = quantity.key.split("|")
            category = parts[0] if parts else ""
            item_name = parts[1] if len(parts) > 1 else ""
            unit_name = parts[2] if len(parts) > 2 else ""
            for column, text in enumerate(("", category, item_name, unit_name)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                digests.setItem(row_index, column, item)
            expression = QTableWidgetItem(quantity.expression)
            expression.setFlags(expression.flags() & ~Qt.ItemFlag.ItemIsEditable)
            expression.setData(Qt.ItemDataRole.UserRole, quantity.expression)
            expression.setToolTip(quantity.expression)
            if quantity.details:
                expression.setToolTip(quantity.expression + "\n\n" + "\n".join(quantity.details))
            digests.setItem(row_index, _QCOL_EXPRESSION, expression)
            amount = QTableWidgetItem(calc_fmt(quantity.value))
            amount.setFlags(amount.flags() & ~Qt.ItemFlag.ItemIsEditable)
            digests.setItem(row_index, _QCOL_AMOUNT, amount)

        listing = self._quantity_tables["清单工程量"]
        listing.setRowCount(0)
        row_index = 0
        from app.orm.models import category_name

        for element_row, dq in detail:
            listing.setRowCount(row_index + 1 + len(dq.items()))
            header = QTableWidgetItem("清单项目")
            header.setFlags(header.flags() & ~Qt.ItemFlag.ItemIsEditable)
            listing.setItem(row_index, 0, header)
            values = (category_name(element_row.category), element_row.spec or element_row.name,
                      element_row.unit, calc_fmt(element_row.amount_value))
            for offset, text in enumerate(values, start=1):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                listing.setItem(row_index, offset, item)
            from app.resources.qss.theme import ThemeManager

            highlight = QBrush(QColor(ThemeManager.instance().current().primary_soft))
            for column in range(len(_QUANTITY_HEADERS)):
                cell = listing.item(row_index, column)
                if cell is None:
                    cell = QTableWidgetItem("")
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    listing.setItem(row_index, column, cell)
                cell.setBackground(highlight)
            row_index += 1

            for quantity in sorted_items(dq):
                parts = quantity.key.split("|")
                cells = (
                    "",
                    parts[0] if parts else "",
                    parts[1] if len(parts) > 1 else "",
                    parts[2] if len(parts) > 2 else "",
                    quantity.expression,
                    calc_fmt(quantity.value),
                )
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if column == _QCOL_EXPRESSION:
                        item.setData(Qt.ItemDataRole.UserRole, quantity.expression)
                        tooltip = quantity.expression
                        if quantity.details:
                            tooltip += "\n\n" + "\n".join(quantity.details)
                        item.setToolTip(tooltip)
                    listing.setItem(row_index, column, item)
                row_index += 1

    def _show_expression_detail(self, item: QTableWidgetItem) -> None:
        """双击“计算表达式”列：弹窗展示完整算式与中间步骤。"""
        expression = item.data(Qt.ItemDataRole.UserRole)
        if not expression:
            return
        details = item.toolTip()
        informative = details if details and "\n\n" in details else ""
        html = (
            f"<pre style='white-space:pre-wrap'>{expression}</pre>"
            + (f"<br><br>中间步骤：<br>{informative.split(chr(10)+chr(10))[-1]}" if informative else "")
        )
        FramelessMessageBox.information(self, "计算表达式", html)

    def _fill_element_row(
        self,
        index: int,
        row: ElementRow,
        enclosure_names: list[str],
        foundation_names: list[str],
    ) -> None:
        name_item = QTableWidgetItem(row.name)
        name_item.setData(_ELEMENT_ROLE, row.id)
        self._element_table.setItem(index, _COL_NAME, name_item)

        category = QComboBox()
        category.addItems([CATEGORY_NAMES[value] for value in CATEGORY_CHOICES])
        category.setCurrentIndex(_category_index(row.category))
        category.currentIndexChanged.connect(
            lambda position, element_id=row.id: self._on_category_changed(element_id, position)
        )
        self._element_table.setCellWidget(index, _COL_CATEGORY, category)

        spec_item = QTableWidgetItem(row.spec)
        spec_item.setFlags(spec_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        spec_item.setForeground(QBrush(_secondary_color()))
        self._element_table.setItem(index, _COL_SPEC, spec_item)

        depth_item = QTableWidgetItem(row.depth)
        depth_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._element_table.setItem(index, _COL_DEPTH, depth_item)
        _apply_expression_hint(depth_item, row.depth, row.depth_error)

        unit_item = QTableWidgetItem(row.unit)
        unit_item.setFlags(unit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        unit_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        unit_item.setForeground(QBrush(_secondary_color()))
        self._element_table.setItem(index, _COL_UNIT, unit_item)

        amount_item = QTableWidgetItem(row.amount)
        amount_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._element_table.setItem(index, _COL_AMOUNT, amount_item)
        _apply_expression_hint(amount_item, row.amount, row.amount_error)

        pe_combo = QComboBox()
        pe_combo.addItems(enclosure_names)
        pe_combo.setCurrentText(row.pe_name)
        pe_combo.currentTextChanged.connect(
            lambda text, element_id=row.id: self._vm.set_element_field(element_id, "pe_name", text)
        )
        self._element_table.setCellWidget(index, _COL_PE, pe_combo)

        pf_combo = QComboBox()
        pf_combo.addItems(foundation_names)
        pf_combo.setCurrentText(row.pf_name)
        pf_combo.currentTextChanged.connect(
            lambda text, element_id=row.id: self._vm.set_element_field(element_id, "pf_name", text)
        )
        self._element_table.setCellWidget(index, _COL_PF, pf_combo)

        source_item = QTableWidgetItem(row.source)
        source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        source_item.setForeground(QBrush(_secondary_color()))
        self._element_table.setItem(index, _COL_SOURCE, source_item)

    def _on_element_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        element_id = self._element_id_at(item.row())
        if element_id is None:
            return
        field = {_COL_NAME: "name", _COL_DEPTH: "depth", _COL_AMOUNT: "amount"}.get(item.column())
        if field is None:
            return
        text = item.text()
        if field == "name":
            self._vm.set_element_field(element_id, field, text)
            return
        _apply_expression_hint(item, text, "")
        self._vm.set_element_field(element_id, field, text)
        label = "埋深" if field == "depth" else "数量"
        try:
            value = evaluate(text)
        except EvalError as error:
            bus().status_message.emit(f"{label}算式错误：{error}", 6000)
        else:
            bus().status_message.emit(f"{label} {text} = {format_number(value)}", 4000)

    def _on_category_changed(self, element_id: int, position: int) -> None:
        if self._loading or position < 0 or position >= len(CATEGORY_CHOICES):
            return
        self._vm.set_element_field(element_id, "category", CATEGORY_CHOICES[position])

    def _on_current_element_changed(self, row: int, _column: int, _previous_row: int, _previous_column: int) -> None:
        if self._loading:
            return
        element_id = self._element_id_at(row)
        self._vm.load_detail(element_id)
        self._section_view.set_element(element_id)

    def _current_element_id(self) -> int | None:
        return self._element_id_at(self._element_table.currentRow())

    def _element_id_at(self, row: int) -> int | None:
        item = self._element_table.item(row, _COL_NAME) if row >= 0 else None
        return item.data(_ELEMENT_ROLE) if item is not None else None

    def _restore_current_element(self, element_id: int | None, column: int) -> None:
        """重建表格后恢复选中行；本来没有选中就选第一行，让明细区直接可用。"""
        if self._element_table.rowCount() == 0:
            return
        if element_id is None:
            self._element_table.setCurrentCell(0, max(0, column))
            return
        for row in range(self._element_table.rowCount()):
            if self._element_id_at(row) == element_id:
                self._element_table.setCurrentCell(row, max(0, column))
                return
        self._element_table.setCurrentCell(0, max(0, column))

    def _add_element(self) -> None:
        self._vm.add_element()

    def add_element(self) -> None:
        """主窗体“新增构件条目”入口。"""
        self._vm.add_element()

    def refresh(self) -> None:
        """重新加载当前单位工程（主题切换、手动刷新时用）。"""
        if self._unit_id is not None:
            self._vm.load_unit(self._unit_id)

    def _delete_element(self) -> None:
        element_id = self._current_element_id()
        if element_id is None:
            return
        answer = FramelessMessageBox.question(
            self,
            "删除确认",
            "确定删除该构件条目及其管材、参数？",
            FramelessMessageBox.StandardButton.Yes | FramelessMessageBox.StandardButton.No,
            FramelessMessageBox.StandardButton.No,
        )
        if answer == FramelessMessageBox.StandardButton.Yes:
            self._vm.remove_element(element_id)

    def _move_element(self, delta: int) -> None:
        element_id = self._current_element_id()
        if element_id is not None:
            self._vm.move_element(element_id, delta)

    # ------------------------------------------------------------------ 主表格快捷键 / 右键菜单（复刻旧版 dGVmain_KeyUp / CMSmain）
    def eventFilter(self, source, event) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        if source is self._element_table and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() == Qt.Key.Key_Insert:
                self._insert_blank_before_current()
                return True
            if event.key() == Qt.Key.Key_Delete:
                self._delete_selected_elements()
                return True
        return super().eventFilter(source, event)

    def _selected_element_ids(self) -> list[int]:
        """选中行对应的构件 id（多选，按行号升序）。"""
        rows = sorted({index.row() for index in self._element_table.selectedIndexes()})
        return [element_id for element_id in (self._element_id_at(row) for row in rows) if element_id]

    def _insert_blank_before_current(self) -> None:
        if self._unit_id is None:
            return
        from app.viewmodels.unit_vm import insert_blank_element

        insert_blank_element(self._unit_id, self._current_element_id())

    def _delete_selected_elements(self) -> None:
        """Delete 键：直接删除选中行（与原版一致，不经确认）。"""
        for element_id in self._selected_element_ids():
            self._vm.remove_element(element_id)

    def _on_element_context_menu(self, position) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction("添加构件", self._add_element)
        menu.addAction("删除选中构件", self._delete_selected_elements)
        menu.addSeparator()
        menu.addAction("复制", self._copy_elements)
        menu.addAction("剪切", self._cut_elements)
        paste = menu.addAction("粘贴", self._paste_elements)
        paste.setEnabled(self._clipboard is not None)
        menu.addSeparator()
        principle_menu = menu.addMenu("选择沟槽围护原则")
        for name in project_io.enclosure_names():
            principle_menu.addAction(name, lambda name=name: self._apply_to_selected("pe_name", name))
        foundation_menu = menu.addMenu("选择地基处理原则")
        for name in project_io.foundation_names():
            foundation_menu.addAction(name, lambda name=name: self._apply_to_selected("pf_name", name))
        menu.addSeparator()
        menu.addAction("复制原则", self._copy_principles)
        apply_menu = menu.addMenu("应用原则")
        apply_menu.addAction("应用沟槽及地基原则", lambda: self._paste_principles(True, True))
        apply_menu.addAction("应用沟槽围护原则", lambda: self._paste_principles(True, False))
        apply_menu.addAction("应用地基处理原则", lambda: self._paste_principles(False, True))
        menu.exec(self._element_table.viewport().mapToGlobal(position))

    #: 行剪贴板 / 原则剪贴板（原版 mClipboard / mClipboard_PCP 的内存版）
    _clipboard: list[dict] | None = None
    _principle_clipboard: tuple[str, str] | None = None

    def _copy_elements(self, *, cut: bool = False) -> None:
        ids = self._selected_element_ids()
        if not ids:
            return
        from app.viewmodels.unit_vm import element_snapshot

        self._clipboard = [element_snapshot(element_id) for element_id in ids]
        if cut:
            for element_id in ids:
                self._vm.remove_element(element_id)

    def _cut_elements(self) -> None:
        self._copy_elements(cut=True)

    def _paste_elements(self) -> None:
        if not self._clipboard or self._unit_id is None:
            return
        from app.viewmodels.unit_vm import insert_element_data

        anchor = self._current_element_id()
        for data in self._clipboard:
            element = insert_element_data(self._unit_id, data, anchor)
            anchor = element.id if element is not None else anchor

    def _copy_principles(self) -> None:
        element_id = self._current_element_id()
        if element_id is None:
            return
        from app.viewmodels.unit_vm import element_snapshot

        data = element_snapshot(element_id)
        if data is not None:
            self._principle_clipboard = (data["pe_name"], data["pf_name"])

    def _apply_to_selected(self, field: str, value: str) -> None:
        for element_id in self._selected_element_ids():
            self._vm.set_element_field(element_id, field, value)

    def _paste_principles(self, use_pe: bool, use_pf: bool) -> None:
        """CopyPCP/PastePCP：把记住的原则批量应用到选中行。"""
        if self._principle_clipboard is None:
            return
        pe_name, pf_name = self._principle_clipboard
        for element_id in self._selected_element_ids():
            if use_pe:
                self._vm.set_element_field(element_id, "pe_name", pe_name)
            if use_pf:
                self._vm.set_element_field(element_id, "pf_name", pf_name)

    # ------------------------------------------------------------------ 构件库插入（原版 FormMdi 构件库双击）
    def insert_template(self, template) -> None:
        """把构件库模板插入当前单位工程主表格（选中行之前）。"""
        if self._unit_id is None:
            bus().status_message.emit("请先选中单位工程，再从构件库插入。", 4000)
            return
        from app.viewmodels.unit_vm import insert_element_template

        insert_element_template(self._unit_id, template, self._current_element_id())

    # ------------------------------------------------------------------ 明细
    def _on_detail_loaded(self, element_id: int, pipes: list[PipeRow], params: list[ParamRow]) -> None:
        self._loading = True
        try:
            self._pipe_table.setRowCount(len(pipes))
            for index, pipe in enumerate(pipes):
                mat_item = QTableWidgetItem(pipe.mat)
                mat_item.setData(_PIPE_ROLE, pipe.id)
                self._pipe_table.setItem(index, 0, mat_item)
                self._pipe_table.setItem(index, 1, QTableWidgetItem(str(pipe.dn)))
                self._pipe_table.setItem(index, 2, QTableWidgetItem(pipe.content))

            self._param_table.setRowCount(len(params))
            for index, param in enumerate(params):
                key_item = QTableWidgetItem(param.key)
                key_item.setData(_PARAM_ROLE, param.id)
                self._param_table.setItem(index, 0, key_item)
                self._param_table.setItem(index, 1, QTableWidgetItem(param.value))
        finally:
            self._loading = False
        # 管径/参数（包封宽高、壁厚、内壁道数…）都影响断面几何，明细变化后重绘
        if element_id:
            self._section_view.set_element(element_id)
        else:
            self._section_view.set_element(None)

    def _on_pipe_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        pipe_id = self._pipe_id_at(item.row())
        if pipe_id is None:
            return
        field = {0: "mat", 1: "dn", 2: "content"}.get(item.column())
        if field is None:
            return
        if field == "dn":
            try:
                value = int(float(item.text().strip() or 0))
            except ValueError:
                bus().status_message.emit("管径需为数字（mm）。", 5000)
                return
            self._vm.set_pipe_field(pipe_id, field, value)
            return
        self._vm.set_pipe_field(pipe_id, field, item.text())

    def _on_param_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        param_id = self._param_id_at(item.row())
        if param_id is None:
            return
        field = {0: "key", 1: "value"}.get(item.column())
        if field is not None:
            self._vm.set_param_field(param_id, field, item.text())

    def _pipe_id_at(self, row: int) -> int | None:
        item = self._pipe_table.item(row, 0) if row >= 0 else None
        return item.data(_PIPE_ROLE) if item is not None else None

    def _param_id_at(self, row: int) -> int | None:
        item = self._param_table.item(row, 0) if row >= 0 else None
        return item.data(_PARAM_ROLE) if item is not None else None

    def _add_pipe(self) -> None:
        self._vm.add_pipe()

    def _delete_pipe(self) -> None:
        pipe_id = self._pipe_id_at(self._pipe_table.currentRow())
        if pipe_id is not None:
            self._vm.remove_pipe(pipe_id)

    def _add_param(self) -> None:
        self._vm.add_param()

    def _delete_param(self) -> None:
        param_id = self._param_id_at(self._param_table.currentRow())
        if param_id is not None:
            self._vm.remove_param(param_id)


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _category_index(category: int) -> int:
    try:
        return CATEGORY_CHOICES.index(category)
    except ValueError:
        return 0


def _combo_names(names: list[str], rows: list[ElementRow], field: str) -> list[str]:
    """下拉项 = 库中原则名；若某构件引用的名字已不在库里也保留，避免显示为空。"""
    result = list(names)
    for row in rows:
        value = getattr(row, field)
        if value and value not in result:
            result.append(value)
    if not result:
        result = [""]
    return result


def _apply_expression_hint(item: QTableWidgetItem, text: str, error: str) -> None:
    """把算式求值结果显示在 tooltip；不合法时用警示色标出。"""
    if not text.strip():
        item.setToolTip("")
        item.setForeground(QBrush(_primary_color()))
        return
    if error:
        item.setToolTip(f"算式错误：{error}")
        item.setForeground(QBrush(_warning_color()))
        return
    try:
        value = evaluate(text)
    except EvalError as exc:
        item.setToolTip(f"算式错误：{exc}")
        item.setForeground(QBrush(_warning_color()))
        return
    item.setToolTip(f"{text} = {format_number(value)}")
    item.setForeground(QBrush(_primary_color()))


def _primary_color() -> QColor:
    return QColor(ThemeManager.instance().current().text_primary)


def _secondary_color() -> QColor:
    return QColor(ThemeManager.instance().current().text_secondary)


def _warning_color() -> QColor:
    return QColor(ThemeManager.instance().current().warning)
