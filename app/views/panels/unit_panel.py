"""中部工作区：单位工程（计划 §7.1、§7.2）。

上半区：工程量表（定额工程量 / 清单工程量）——“计算表达式”列在“工程量”列之前，
        计算结果由 M4 的计算引擎填充，这里先把表结构与空状态做好。
下半区：构件录入表 + 选中构件的明细（管材 / 构件参数）。

埋深、数量两列允许写算式（如 2.5+0.3）：单元格 tooltip 显示求值结果，
算式不合法时用警示色标出并给出原因，不静默按 0 处理。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
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

_ELEMENT_ROLE = Qt.ItemDataRole.UserRole + 1
_COL_NAME, _COL_CATEGORY, _COL_DEPTH, _COL_UNIT, _COL_AMOUNT, _COL_PE, _COL_PF = range(7)
_ELEMENT_HEADERS = ["名称", "类型", "埋深", "单位", "数量", "沟槽围护原则", "地基处理原则"]
#: 中部宽度有限，列宽按 7 列约 700px 排布（最后一列自适应剩余空间）
_ELEMENT_WIDTHS = [170, 100, 80, 50, 80, 110, 110]

_QUANTITY_HEADERS = ["编号", "类别", "项目", "单位", "计算表达式", "工程量"]

_PIPE_ROLE = Qt.ItemDataRole.UserRole + 1
_PIPE_HEADERS = ["管材", "管径(mm)", "含量"]
_PARAM_ROLE = Qt.ItemDataRole.UserRole + 1
_PARAM_HEADERS = ["参数名", "参数值"]


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

        header = QHBoxLayout()
        self._title = QLabel("单位工程")
        self._title.setProperty("role", "panel-title")
        header.addWidget(self._title)
        header.addStretch(1)
        self._btn_add = self._make_button("＋构件", "新增构件条目", self._add_element)
        self._btn_delete = self._make_button("✕", "删除选中构件条目", self._delete_element)
        self._btn_up = self._make_button("↑", "上移", lambda: self._move_element(-1))
        self._btn_down = self._make_button("↓", "下移", lambda: self._move_element(1))
        for button in (self._btn_add, self._btn_delete, self._btn_up, self._btn_down):
            header.addWidget(button)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_quantity_area())
        splitter.addWidget(self._build_entry_area())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([180, 580])
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

    def _build_quantity_area(self) -> QWidget:
        tabs = QTabWidget()
        self._quantity_tables: dict[str, QTableWidget] = {}
        for name in ("定额工程量", "清单工程量"):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(6, 6, 6, 6)
            page_layout.setSpacing(4)
            hint = QLabel("计算引擎将在 M4 实现：届时按构件列出工程量，并在“工程量”列前给出计算表达式。")
            hint.setProperty("role", "hint")
            hint.setWordWrap(True)
            page_layout.addWidget(hint)
            table = self._make_table(_QUANTITY_HEADERS)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self._quantity_tables[name] = table
            page_layout.addWidget(table, 1)
            tabs.addTab(page, name)
        self._quantity_tabs = tabs
        return tabs

    def _build_entry_area(self) -> QWidget:
        """录入表在上、选中构件的明细（管材 / 构件参数）在下，两者都用满中部宽度。"""
        splitter = QSplitter(Qt.Orientation.Vertical)

        self._element_table = self._make_table(_ELEMENT_HEADERS)
        for index, width in enumerate(_ELEMENT_WIDTHS[:-1]):
            self._element_table.setColumnWidth(index, width)
        self._element_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._element_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._element_table.setSortingEnabled(False)
        splitter.addWidget(self._element_table)

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
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([330, 250])
        return splitter

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.verticalHeader().setDefaultSectionSize(26)
        table.setWordWrap(False)
        return table

    def _connect(self) -> None:
        self._vm.unit_loaded.connect(self._on_unit_loaded)
        self._vm.detail_loaded.connect(self._on_detail_loaded)
        self._vm.error_occurred.connect(lambda message: bus().status_message.emit(message, 4000))
        self._element_table.itemChanged.connect(self._on_element_item_changed)
        self._element_table.currentCellChanged.connect(self._on_current_element_changed)
        self._pipe_table.itemChanged.connect(self._on_pipe_item_changed)
        self._param_table.itemChanged.connect(self._on_param_item_changed)
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
        self._title.setText(name or "单位工程")
        has_unit = unit_id is not None
        self._placeholder.setVisible(not has_unit)
        self._work_area.setVisible(has_unit)
        self._btn_add.setEnabled(has_unit)
        if not has_unit:
            self._vm.load_unit(None)
            self._element_table.setRowCount(0)
            self._pipe_table.setRowCount(0)
            self._param_table.setRowCount(0)
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

        depth_item = QTableWidgetItem(row.depth)
        self._element_table.setItem(index, _COL_DEPTH, depth_item)
        _apply_expression_hint(depth_item, row.depth, row.depth_error)

        unit_item = QTableWidgetItem(row.unit)
        unit_item.setFlags(unit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        unit_item.setForeground(QBrush(_secondary_color()))
        self._element_table.setItem(index, _COL_UNIT, unit_item)

        amount_item = QTableWidgetItem(row.amount)
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
        self._vm.load_detail(self._element_id_at(row))

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
        answer = QMessageBox.question(
            self,
            "删除确认",
            "确定删除该构件条目及其管材、参数？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._vm.remove_element(element_id)

    def _move_element(self, delta: int) -> None:
        element_id = self._current_element_id()
        if element_id is not None:
            self._vm.move_element(element_id, delta)

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
