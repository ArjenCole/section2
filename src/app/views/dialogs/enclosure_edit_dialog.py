"""围护原则编辑对话框（复刻旧版 FmPcp/FormPE）。

布局与交互照抄 FormPE / FormPE.Designer：

* 顶部「原则名称」；右侧竖排「确认修改 / 取消修改」；v10 起围护原则仅管围护
  做法：原「挖填类型」板块移到挖填降水原则、原「管道基础」板块移到地基原则；
* 主表格 7 列：埋深 / 范围 / 围护类型 / 围护形式描述 / 止水类型 / 止水形式描述 /
  按钮列（「+」在按钮列表头格，每行行尾「-」删该行，见 RowButtonColumn），
  首行埋深恒 0 且只读，Insert 插入做法（埋深取值规则与旧版一致），
  Delete 删除（全删时提示“至少需要一种围护做法。”）；
* 双击“围护形式描述”：多级围护 → 做法编辑（FormEcls），单构件 → 构件公式编辑
  （FormCpntEdit）；双击“止水形式描述” → 构件公式编辑；
* 「确认修改」才落库（原版“编辑副本、确认生效”）：做法表与子编辑器的编辑
  只写共享会话、不 commit；「取消修改」回滚会话，本次编辑（含子编辑器）整体丢弃。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.event_bus import bus
from app.core.models import base as orm
from app.core.models.models import MULTI_LEVEL_TEXT, EnclosureWork, PcpEnclosure
from app.services import project_io
from app.services.project_io import new_enclosure_work
from app.views.dialogs.principle_dialogs import (
    ComponentEditDialog,
    EnclosureWorkDialog,
    describe_component,
)
from app.views.widgets.cell_fill_table import CellFillTable
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox
from app.views.widgets.row_button_column import RowButtonColumn
from app.views.widgets.table_width import fixed_width_behavior

_COL_DEPTH, _COL_RANGE, _COL_ECLS_CAT, _COL_ECLS_DIS, _COL_WS_CAT, _COL_WS_DIS = range(6)
#: 止水形式描述列的下限：可视区减其余列不足这么多时钳回来（宁出横向滚动条）
_DESC_MIN_WIDTH = 80


class EnclosureEditDialog(FramelessDialog):
    """围护原则编辑（FormPE，无边框自绘标题栏）。"""

    def __init__(self, enclosure_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, "围护原则编辑")
        self.resize(660, 470)
        self._enclosure_id = enclosure_id
        self._loading = False
        self._build_ui()
        self._reload()
        self._fill()

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        root = self.bodyLayout()
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("原则名称:"))
        self._name = QLineEdit()
        name_row.addWidget(self._name, 1)
        root.addLayout(name_row)

        # v10 起围护原则仅管围护做法：挖填类型 → 挖填降水原则、管道基础 → 地基原则，
        # 因此这里只剩确认 / 取消按钮（右侧竖排，与做法表同排）
        detail_row = QHBoxLayout()
        detail_row.addStretch(1)
        detail_row.addWidget(self._build_confirm_buttons())
        root.addLayout(detail_row)

        table_row = QHBoxLayout()
        self._work_table = _WorkTable()
        self._work_table.insert_requested.connect(lambda: self._insert_work())
        self._work_table.delete_requested.connect(self._delete_selected_works)
        self._work_table.cellChanged.connect(self._on_cell_changed)
        self._work_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table_row.addWidget(self._work_table, 1)
        # 「+ / -」按钮列（管材面板同款）：+ 在按钮列表头格，每行行尾「-」
        # 删该行（只剩一条做法时删除被禁 → 行尾不装「-」，见 _fill）
        self._work_buttons = RowButtonColumn(
            self._work_table,
            add_tooltip="添加围护做法（Insert）",
            delete_tooltip="删除该围护做法",
        )
        self._work_buttons.add_clicked.connect(lambda: self._insert_work())
        self._work_buttons.delete_clicked.connect(
            lambda row: self._delete_work_rows([row])
        )
        self._work_buttons.attach()
        root.addLayout(table_row, 1)

    def _build_confirm_buttons(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        # 原版按钮文字分两行：确认/修改、取消/修改
        btn_yes = QPushButton("确认\n修改")
        btn_yes.setFixedSize(76, 52)
        btn_yes.setProperty("primary", "true")
        btn_yes.clicked.connect(self._confirm)
        btn_cancel = QPushButton("取消\n修改")
        btn_cancel.setFixedSize(76, 52)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_yes)
        layout.addWidget(btn_cancel)
        layout.addStretch(1)
        return column

    # ------------------------------------------------------------------ 数据
    def _enclosure(self) -> PcpEnclosure | None:
        return orm.session().get(PcpEnclosure, self._enclosure_id)

    def _fresh(self) -> PcpEnclosure | None:
        """重载原则（丢弃已加载的 works/cushions 集合缓存）。

        编辑过程不再即改即存，未提交修改是常态；expire 后的重载路径不做
        autoflush，未 flush 的修改会被静默刷掉，因此先 flush 进事务（flush
        不提交，「取消修改」的回滚仍然整体丢弃）。
        """
        orm.session().flush()
        enclosure = self._enclosure()
        if enclosure is not None:
            orm.session().expire(enclosure)
        return enclosure

    def _reload(self) -> None:
        """填顶部原则名称（v10 起围护原则不再有挖填 / 基础参数）。"""
        enclosure = self._enclosure()
        if enclosure is None:
            return
        self._name.setText(enclosure.name)

    def _fill(self) -> None:
        """FlashdGVPE：重建做法表格。"""
        self._loading = True
        try:
            enclosure = self._fresh()
            works = enclosure.works_sorted() if enclosure else []
            library = project_io.component_library()
            table = self._work_table
            self._work_buttons.clear_row_buttons()
            table.clearContents()
            table.setRowCount(len(works))
            for row_index, work in enumerate(works):
                level = work.levels[0] if work.levels else None
                component = level.components[0] if level and level.components else None
                waterstop = work.waterstops[0] if work.waterstops else None

                depth_item = QTableWidgetItem(f"{work.min_depth:g}")
                depth_item.setData(Qt.ItemDataRole.UserRole, work.id)
                if row_index == 0:
                    depth_item.setFlags(depth_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row_index, _COL_DEPTH, depth_item)

                range_item = QTableWidgetItem(
                    "+∞" if row_index + 1 >= len(works) else f"{works[row_index + 1].min_depth:g}"
                )
                range_item.setFlags(range_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row_index, _COL_RANGE, range_item)

                table.setItem(row_index, _COL_ECLS_DIS, self._readonly_item(self._ecls_discribe(work)))
                table.setItem(row_index, _COL_WS_DIS, self._readonly_item(describe_component(waterstop)))

                cat_combo = QComboBox()
                cat_combo.addItems(list(library.names("Ei")) + [MULTI_LEVEL_TEXT])
                cat_combo.setCurrentText(work.cpnt_cat or (level.name if level else ""))
                cat_combo.currentTextChanged.connect(
                    lambda text, w=work: self._on_work_category(w, text)
                )
                table.setCellWidget(row_index, _COL_ECLS_CAT, cat_combo)

                ws_combo = QComboBox()
                ws_combo.addItems(list(library.names("WSi")))
                ws_combo.setCurrentText(waterstop.name if waterstop else "无")
                ws_combo.currentTextChanged.connect(
                    lambda text, w=work: self._on_waterstop_changed(w, text)
                )
                table.setCellWidget(row_index, _COL_WS_CAT, ws_combo)

                # 行尾「-」删行按钮：至少保留一种做法，只剩一行时不装
                # （空格子设为只读，防误编辑）
                if len(works) > 1:
                    self._work_buttons.add_row_button(row_index)
                else:
                    self._work_buttons.set_row_undeletable(row_index)
        finally:
            self._loading = False
        # 内嵌下拉框就位后重算内容列宽：setRowCount 触发的自动重算发生在控件
        # 创建之前，会把下拉列压窄、表头文字整体移位，视觉上字体忽粗忽细
        for column in (_COL_DEPTH, _COL_RANGE, _COL_ECLS_CAT, _COL_WS_CAT):
            table.resizeColumnToContents(column)
        # 围护形式描述固定宽（可拖动调整）；止水形式描述初始同宽，窗体可见时
        # 再按可视区收窄（_fit_desc_column），总宽刚好不出横向滚动条
        for column in (_COL_ECLS_DIS, _COL_WS_DIS):
            table.setColumnWidth(column, 150)
        if self.isVisible():
            self._fit_desc_column()

    def _fit_desc_column(self) -> None:
        """止水形式描述列收窄到总宽刚好塞满表格可视区：不出横向滚动条。

        其余列各有定宽（内容列按内容、围护形式描述 150、按钮列 40），可视区
        减去它们就是该列的宽；可视区过窄时钳到最小可读宽度（_DESC_MIN_WIDTH），
        那时宁可出横向滚动条也不把文字压没。
        """
        table = self._work_table
        others = sum(
            table.columnWidth(column)
            for column in range(table.columnCount())
            if column != _COL_WS_DIS
        )
        remaining = table.viewport().width() - others
        table.setColumnWidth(_COL_WS_DIS, max(_DESC_MIN_WIDTH, remaining))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # 布局落地后再量可视区：showEvent 时子控件几何还没定
        QTimer.singleShot(0, self._fit_desc_column)

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setToolTip("双击编辑")
        return item

    @staticmethod
    def _ecls_discribe(work: EnclosureWork) -> str:
        """旧版 mcEnclosure.EclsDis：多级围护显示类别名，否则显示构件描述。"""
        if work.cpnt_cat == MULTI_LEVEL_TEXT:
            return MULTI_LEVEL_TEXT
        level = work.levels[0] if work.levels else None
        return describe_component(level.components[0] if level and level.components else None)

    # ------------------------------------------------------------------ 表格交互
    def _on_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column != _COL_DEPTH or row <= 0:
            return
        work = self._work_at(row)
        item = self._work_table.item(row, _COL_DEPTH)
        if work is None or item is None:
            return
        try:
            work.min_depth = float(item.text())
        except ValueError:
            pass
        self._fill()

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        if self._loading or row < 0:
            return
        work = self._work_at(row)
        if work is None:
            return
        if column == _COL_ECLS_DIS:
            if work.cpnt_cat == MULTI_LEVEL_TEXT:
                dialog = EnclosureWorkDialog(work, self)
                if dialog.exec() and dialog.saved:
                    self._fill()
            else:
                level = work.levels[0] if work.levels else None
                component = level.components[0] if level and level.components else None
                if component is None:
                    return
                dialog = ComponentEditDialog(component, self)
                if dialog.exec() and dialog.saved:
                    self._fill()
        elif column == _COL_WS_DIS:
            component = work.waterstops[0] if work.waterstops else None
            if component is None:
                return
            dialog = ComponentEditDialog(component, self)
            if dialog.exec() and dialog.saved:
                self._fill()

    def _on_work_category(self, work: EnclosureWork, text: str) -> None:
        """CellEndEdit ColEclsCat：切换围护类型（旧版 setECpnt，按模板重建级构件）。"""
        if self._loading or work.cpnt_cat == text or not text:
            return
        project_io.set_work_category(orm.session(), work, project_io.component_library(), text)
        self._fill()

    def _on_waterstop_changed(self, work: EnclosureWork, text: str) -> None:
        """CellEndEdit ColWSCat：切换止水构件（从库模板重建）。"""
        if self._loading:
            return
        old = work.waterstops[0] if work.waterstops else None
        if old is not None and old.name == text:
            return
        if old is not None:
            orm.session().delete(old)
        project_io.component_from_template(
            orm.session(), project_io.component_library(), "WSi", text,
            enclosure_work_id=work.id,
        )
        orm.session().expire(work)  # expire_on_commit=False：让 waterstops 集合重载
        self._fill()

    def _work_at(self, row: int) -> EnclosureWork | None:
        item = self._work_table.item(row, _COL_DEPTH)
        work_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return orm.session().get(EnclosureWork, work_id) if work_id else None

    # ------------------------------------------------------------------ 做法 Insert/Delete（InsertEcls / KeyUp Delete）
    def _insert_work(self, position: int | None = None) -> None:
        enclosure = self._enclosure()
        if enclosure is None:
            return
        works = enclosure.works_sorted()
        if position is None or position < 0 or position > len(works):
            position = len(works)  # 默认加在最后
        # 新行插到 position 之前：后续行 order_no 先整体后移（原版 mList.Insert）
        for item in works[position:]:
            item.order_no += 1
        min_depth = 0.0
        if position == len(works) and works:
            min_depth = works[-1].min_depth + 3.5
        elif 0 < position < len(works):
            min_depth = (works[position - 1].min_depth + works[position].min_depth) / 2.0
        new_enclosure_work(
            orm.session(), enclosure, project_io.component_library(),
            min_depth=min_depth, order_no=position,
        )
        enclosure = self._fresh()  # 让 works 集合包含新行
        if position == 0 and works:
            # 加在最前：原第一行的埋深改为 3.5（仅两行时）或原第二行的一半
            shifted = enclosure.works_sorted()
            if len(shifted) >= 2:
                shifted[1].min_depth = 3.5 if len(shifted) == 2 else shifted[2].min_depth / 2.0
        for index, work in enumerate(enclosure.works_sorted()):
            work.order_no = index
        self._fill()

    def _delete_selected_works(self) -> None:
        rows = sorted({index.row() for index in self._work_table.selectedIndexes()}, reverse=True)
        self._delete_work_rows(rows)

    def _delete_work_rows(self, rows: list[int]) -> None:
        """删指定行（行尾「-」单行 / Delete 键多行共用）；全删时提示保底一条。"""
        enclosure = self._enclosure()
        if enclosure is None or not rows:
            return
        works = enclosure.works_sorted()
        if len(rows) >= len(works):
            FramelessMessageBox.information(self, "提示", "至少需要一种围护做法。")
            return
        for row in rows:
            work = self._work_at(row)
            if work is not None:
                orm.session().delete(work)
        orm.session().flush()
        enclosure = self._fresh()
        remaining = enclosure.works_sorted()
        if remaining:
            remaining[0].min_depth = 0.0  # 删除后第一行埋深归 0（原版）
        for index, work in enumerate(remaining):
            work.order_no = index
        self._fill()

    # ------------------------------------------------------------------ 确认 / 取消
    def reject(self) -> None:  # noqa: N802 - Qt 命名
        """取消修改：回滚会话，丢弃做法表与子编辑器的全部未落库修改。

        编辑过程只写共享会话不 commit（按钮、标题栏 X、Esc 关闭都汇到这里，
        Esc 已被 keyPressEvent 屏蔽），因此一次回滚即可整体复原。
        """
        orm.session().rollback()
        super().reject()

    def _confirm(self) -> None:
        """BTNyes：改名 + 提交（确认修改才写回）。

        编辑过程中（做法表、子编辑器）不广播，点击确认修改后统一刷新
        工程量与断面图；改名时再广播 tree_structure_changed 同步原则横条与引用名。
        """
        enclosure = self._enclosure()
        if enclosure is None:
            self.accept()
            return
        name = self._name.text().strip()
        if not name:
            FramelessMessageBox.warning(self, "提示", "原则名称不得为空。")
            return
        renamed = name != enclosure.name
        if renamed:
            project_io.rename_enclosure(enclosure.id, name)
        # 本次编辑（做法表、子编辑器）随这次提交统一落库
        project_io.commit()
        if renamed:
            bus().tree_structure_changed.emit()
        bus().principle_changed.emit()
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # 原版 FormPE 注释掉了 Esc 取消，此处保持一致
        if event.key() == Qt.Key.Key_Escape:
            return
        super().keyPressEvent(event)


class _WorkTable(CellFillTable):
    """做法表格：Insert 插入行 / Delete 删除选中行（原版 dGVPE_KeyUp）。"""

    insert_requested = Signal()
    delete_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels(
            ["埋深 m", "范围", "围护类型", "围护形式描述", "止水类型", "止水形式描述", ""]
        )
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.verticalHeader().setVisible(False)
        # 行高与主表格一致（32px）；单元格内下拉框的纵向内边距已由 QSS 压小
        self.verticalHeader().setDefaultSectionSize(32)
        # 固定列宽（可拖动）：埋深、范围、两个下拉列初始按内容自适应（_fill 里
        # 每次装填后重算），围护形式描述固定宽、止水形式描述按可视区收窄
        # （_fit_desc_column），总宽刚好不出横向滚动条
        fixed_width_behavior(self)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Insert:
            self.insert_requested.emit()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)
