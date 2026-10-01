"""多原则引用编辑 Tab（复刻旧版 FormUnit 左下角的 PNLPE / PNLPF 子表）。

旧版交互（FormUnit.cs FlashdGVPE / FlashdGVPF / dGVPE_* 事件）：

* 主表格“沟槽围护原则”列选中“多围护原则”后，左下角出现子表：
  每行 = 原则名称（下拉，仅库中原则）+ 比例（占比系数，可写算式）；
  围护子表另有“主要原则”下拉（cmbBoxMainPE，沟槽回填材质命名、
  管道基础、支撑按主要原则计算）；
* 追加行选择未引用的原则（旧版 AllowUserToAddRows + CellValidating
  拒绝重复：“原则已存在于列表中。”）；Delete 删除选中行，
  全删时提示“至少需要一种围护原则。”；
* 地基子表（dGVPF）同构，仅无主要原则下拉。

新版把两个子表放進「管材 / 构件参数」面板作为额外 Tab；构件未使用
多原则时显示占位说明。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.evaluator import EvalError, evaluate, format_number
from app.core.event_bus import bus
from app.core.models.models import MULTI_PE_TEXT, MULTI_PF_TEXT
from app.services import project_io
from app.viewmodels.unit_vm import (
    _element,
    add_principle_ref,
    principle_ref_rows,
    remove_principle_ref,
    set_main_pe,
    update_principle_ref,
)
from app.views.widgets.frameless_dialog import FramelessMessageBox

_REF_ROLE = Qt.ItemDataRole.UserRole + 1

_KIND_PE = "pe"
_KIND_PF = "pf"

_TITLE = {_KIND_PE: "沟槽围护", _KIND_PF: "地基处理"}
_MULTI_TEXT = {_KIND_PE: MULTI_PE_TEXT, _KIND_PF: MULTI_PF_TEXT}
_SHOW_FIELD = {_KIND_PE: "pe_name", _KIND_PF: "pf_name"}
_SHOW_COLUMN = {_KIND_PE: "沟槽围护原则", _KIND_PF: "地基处理原则"}


class MultiPrincipleTab(QWidget):
    """「多围护原则 / 多地基原则」Tab：按比例引用多条原则。"""

    #: 构件切到多原则模式时发出（旧版 PNLPE/PNLPF 自动出现的等价通知）
    became_active = Signal()

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._element_id: int | None = None
        self._loading = False
        self._last_active = False
        self._build_ui()
        bus().unit_changed.connect(lambda _unit_id: self._defer_reload())
        bus().tree_structure_changed.connect(self._defer_reload)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._title = QLabel(_TITLE[self._kind])
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._main_row = QWidget()
        main_layout = QHBoxLayout(self._main_row)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(QLabel("主要原则:"))
        self._main_combo = QComboBox()
        self._main_combo.currentTextChanged.connect(self._on_main_changed)
        main_layout.addWidget(self._main_combo, 1)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["原则名称", "比例"])
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 130)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.itemChanged.connect(self._on_item_changed)

        self._btn_host = QWidget()
        button_bar = QHBoxLayout(self._btn_host)
        button_bar.setContentsMargins(0, 0, 0, 0)
        button_bar.addWidget(self._make_button("＋原则", "添加一条原则引用", self._add_ref))
        button_bar.addWidget(self._make_button("✕", "删除选中原则引用", self._delete_selected))
        button_bar.addStretch(1)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        content_layout.addWidget(self._title)
        if self._kind == _KIND_PE:
            content_layout.addWidget(self._main_row)  # 地基子表无主要原则（旧版 PNLPF 同）
        content_layout.addWidget(self._table, 1)
        content_layout.addWidget(self._btn_host)
        layout.addWidget(self._content, 1)

        self._placeholder = QLabel(
            f"当前构件未使用{_MULTI_TEXT[self._kind]}。\n"
            f"在主表格“{_SHOW_COLUMN[self._kind]}”列选择“{_MULTI_TEXT[self._kind]}”"
            "后在此按比例引用多条原则。"
        )
        self._placeholder.setProperty("role", "placeholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        layout.addWidget(self._placeholder, 1)

    def _make_button(self, text: str, tooltip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setProperty("role", "icon-btn")
        button.clicked.connect(slot)
        return button

    # ------------------------------------------------------------------ 数据
    def set_element(self, element_id: int | None) -> None:
        """跟随主表格选中行（UnitPanel 在选中变化 / 重载时调用）。"""
        self._element_id = element_id
        self.reload()

    def reload(self) -> None:
        """FlashdGVPE / FlashdGVPF：按当前构件的引用重建表格。"""
        was_active = self._last_active
        self._loading = True
        try:
            active = self._element_active()
            self._content.setVisible(active)
            self._placeholder.setVisible(not active)
            if not active:
                self._table.setRowCount(0)
            else:
                self._fill_rows()
        finally:
            self._loading = False
        self._last_active = active
        if active and not was_active:
            self.became_active.emit()

    def _fill_rows(self) -> None:
        rows = principle_ref_rows(self._element_id, self._kind)
        names = project_io.enclosure_names() if self._kind == _KIND_PE else project_io.foundation_names()
        self._table.setRowCount(len(rows))
        for index, ref in enumerate(rows):
            combo = QComboBox()
            combo.addItems([ref.name] + names if ref.name not in names else names)
            combo.setCurrentText(ref.name)
            combo.currentTextChanged.connect(
                lambda text, ref_id=ref.id: self._on_name_changed(ref_id, text)
            )
            self._table.setCellWidget(index, 0, combo)

            ratio_item = QTableWidgetItem(format_number(ref.ratio))
            ratio_item.setData(_REF_ROLE, ref.id)
            self._table.setItem(index, 1, ratio_item)

        if self._kind == _KIND_PE:
            main_names = [ref.name for ref in rows]
            self._main_combo.blockSignals(True)
            self._main_combo.clear()
            self._main_combo.addItems(main_names)
            main = next((ref.name for ref in rows if ref.is_main), main_names[0] if main_names else "")
            self._main_combo.setCurrentText(main)
            self._main_combo.blockSignals(False)

    def _element_active(self) -> bool:
        """当前选中构件是否处于本 Tab 的多原则模式（旧版 PNLPE.Visible 条件）。"""
        if self._element_id is None or not project_io.is_open():
            return False
        element = _element(self._element_id)
        return element is not None and getattr(element, _SHOW_FIELD[self._kind]) == _MULTI_TEXT[self._kind]

    # ------------------------------------------------------------------ 事件
    def _defer_reload(self, *_args) -> None:
        """延后刷新：本槽可能由表格自身编辑信号触发，立即重建会删掉正编辑的控件。"""
        QTimer.singleShot(0, self.reload)

    def _on_name_changed(self, ref_id: int, text: str) -> None:
        if self._loading:
            return
        if update_principle_ref(ref_id, name=text) is None:
            bus().status_message.emit("原则已存在于列表中。", 4000)
            self._defer_reload()  # 重复原则被拒绝：恢复原显示

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != 1:
            return
        ref_id = item.data(_REF_ROLE)
        if not ref_id:
            return
        try:
            ratio = evaluate(item.text())
        except EvalError as error:
            bus().status_message.emit(f"比例算式错误：{error}", 5000)
            self._defer_reload()
            return
        if update_principle_ref(ref_id, ratio=ratio) is None:
            self._defer_reload()

    def _on_main_changed(self, text: str) -> None:
        if self._loading or not text or self._element_id is None:
            return
        set_main_pe(self._element_id, text)

    def _add_ref(self) -> None:
        if not self._element_active():
            return
        names = project_io.enclosure_names() if self._kind == _KIND_PE else project_io.foundation_names()
        used = {ref.name for ref in principle_ref_rows(self._element_id, self._kind)}
        candidate = next((name for name in names if name not in used), "")
        if not candidate:
            FramelessMessageBox.information(self, "提示", "原则库中的原则已全部引用。")
            return
        if add_principle_ref(self._element_id, self._kind, candidate) is None:
            bus().status_message.emit("原则已存在于列表中。", 4000)
            return
        self.reload()

    def _delete_selected(self) -> None:
        if not self._element_active():
            return
        rows = sorted({index.row() for index in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            item = self._table.item(row, 1)
            ref_id = item.data(_REF_ROLE) if item else None
            if ref_id:
                error = remove_principle_ref(ref_id)
                if error:  # 最后一条：旧版“至少需要一种围护原则。”
                    FramelessMessageBox.information(self, "提示", error)
        if rows:
            self.reload()
