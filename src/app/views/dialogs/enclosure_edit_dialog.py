"""围护原则编辑对话框（复刻旧版 FmPcp/FormPE）。

布局与交互照抄 FormPE / FormPE.Designer：

* 顶部「原则名称」；v10 起围护原则仅管围护做法：原「挖填类型」板块移到挖填
  降水原则、原「管道基础」板块移到地基原则；
* 底部「取消 / 确认」按钮（与地基处理原则窗体同款常规按钮，Apple HIG：
  取消在左、确认在右）；
* 主表格 7 列：埋深 / 范围 / 围护类型 / 围护形式描述 / 止水类型 / 止水形式描述 /
  按钮列（「+」在按钮列表头格，每行行尾「-」删该行，见 RowButtonColumn），
  首行埋深恒 0 且只读，Insert /「+」插入做法：有选中行时插到该行下方、埋深取
  上下两行中值，无选中行时追加到最后（埋深 = 末行 + 3.5），
  Delete 删除（全删时提示“至少需要一种围护做法。”）；
* 拖动行调整做法顺序：一次只拖按下的那一行（多选时也一样），落点线画在插入
  位置，松手后按新顺序重排 order_no，并把原有的一组埋深阈值升序贴回去
  （首行恒 0，与只读首行一致；阈值与顺序同向，否则「范围」列倒挂、计算取错）；
* 双击“围护形式描述”：多级围护 → 做法编辑（FormEcls），单构件 → 构件公式编辑
  （FormCpntEdit）；双击“止水形式描述” → 构件公式编辑；
* 「确认修改」才落库（原版“编辑副本、确认生效”）：做法表与子编辑器的编辑
  只写共享会话、不 commit；「取消修改」回滚会话，本次编辑（含子编辑器）整体丢弃。
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QDrag, QKeyEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidgetItem,
    QWidget,
)

from app.core.event_bus import bus
from app.core.models import base as orm
from app.core.models.models import MULTI_LEVEL_TEXT, EnclosureWork, PcpEnclosure
from app.resources.qss.theme import ThemeManager
from app.services import project_io
from app.services.project_io import new_enclosure_work
from app.views.dialogs.principle_dialogs import (
    ComponentEditDialog,
    EnclosureWorkDialog,
    describe_component,
)
from app.views.widgets.cell_fill_table import CellFillTable
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox
from app.views.widgets.platform_buttons import (
    CANCEL_TEXT,
    OK_TEXT,
    DialogButtonSpec,
    add_dialog_buttons,
)
from app.views.widgets.row_button_column import RowButtonColumn
from app.views.widgets.table_width import fixed_width_behavior

_COL_DEPTH, _COL_RANGE, _COL_ECLS_CAT, _COL_ECLS_DIS, _COL_WS_CAT, _COL_WS_DIS = range(6)
#: 止水形式描述列的下限：可视区减其余列不足这么多时钳回来（宁出横向滚动条）
_DESC_MIN_WIDTH = 80
#: 做法行拖拽的 MIME 类型：只认表格内部的拖拽（外部文件 / 文本一律不接）
_WORK_ROW_MIME = "application/x-section2-enclosure-work-row"


class EnclosureEditDialog(FramelessDialog):
    """围护原则编辑（FormPE，无边框自绘标题栏）。"""

    def __init__(self, enclosure_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, "沟槽围护原则编辑")
        self.resize(660, 520)
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

        table_row = QHBoxLayout()
        self._work_table = _WorkTable()
        self._work_table.insert_requested.connect(lambda: self._insert_work())
        self._work_table.delete_requested.connect(self._delete_selected_works)
        self._work_table.row_move_requested.connect(self._move_work_row)
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

        # 底部标准按钮行（确定/取消）：顺序、默认按钮、对齐按平台规范，
        # 见 widgets/platform_buttons.py
        button_row = QHBoxLayout()
        add_dialog_buttons(
            button_row,
            [
                DialogButtonSpec(CANCEL_TEXT, "reject", on_click=self.reject),
                DialogButtonSpec(OK_TEXT, "accept", on_click=self._confirm),
            ],
        )
        root.addLayout(button_row)

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

    def _fill(self, select_row: int | None = None) -> None:
        """FlashdGVPE：重建做法表格。

        ``select_row`` 用于重建后把选中行落回指定行（新增做法后选中新行），
        其余调用方保持“重建后不选中任何行”的原行为。
        """
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
        if select_row is not None and 0 <= select_row < table.rowCount():
            # 只设当前格（整行选择由 SelectRows 行为带出），不触发 cellChanged
            table.setCurrentCell(select_row, _COL_DEPTH)
            table.scrollToItem(table.item(select_row, _COL_DEPTH))

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
    def _selected_row(self) -> int | None:
        """当前选中的最后一行（整行多选时取最下面那行）；无选中返回 None。"""
        rows = {index.row() for index in self._work_table.selectedIndexes()}
        return max(rows) if rows else None

    def _insert_work(self, position: int | None = None) -> None:
        """「+」/Insert：有选中行时插到该行**下方**，无选中行时追加到最后。

        插入行的埋深取上下两行的中值（插到最后一行之后没有下界 → 末行 +3.5，
        沿用原版）；插入后选中新行，便于继续编辑或调序。
        """
        enclosure = self._enclosure()
        if enclosure is None:
            return
        works = enclosure.works_sorted()
        if position is None:
            selected = self._selected_row()
            position = len(works) if selected is None else min(selected + 1, len(works))
        if position < 0 or position > len(works):
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
        self._fill(select_row=position)

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

    # ------------------------------------------------------------------ 拖动调序
    def _move_work_row(self, source_row: int, insert_row: int) -> None:
        """把做法行 ``source_row`` 移到 ``insert_row`` 之前（一次只动一行）。

        行的先后就是做法生效的先后（``order_no``），而埋深阈值决定“多深用哪条”：
        两者必须同向，否则「范围」列倒挂、计算也会取错做法。所以重排后把原有的
        一组埋深阈值**升序**贴回新顺序（首行仍恒 0，与只读首行一致）。
        """
        enclosure = self._enclosure()
        if enclosure is None:
            return
        works = enclosure.works_sorted()
        if not 0 <= source_row < len(works):
            return
        insert_row = max(0, min(insert_row, len(works)))
        if insert_row in (source_row, source_row + 1):
            return  # 原地：不动
        work = works.pop(source_row)
        # 先删后插：插在源行之后时目标下标要减 1（insert_row 是按原列表给的）
        target = insert_row - 1 if insert_row > source_row else insert_row
        works.insert(target, work)
        for index, (item, depth) in enumerate(zip(works, sorted(w.min_depth for w in works))):
            item.order_no = index
            item.min_depth = depth
        self._fill(select_row=target)

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


class _WorkTable(CellFillTable):
    """做法表格：Insert 插入行 / Delete 删除选中行 / 拖动行调序（原版 dGVPE_KeyUp）。"""

    insert_requested = Signal()
    delete_requested = Signal()
    #: (源行, 插入行)：插入行 = 源行要插到该行**之前**（按拖拽前的行号，含末尾）
    row_move_requested = Signal(int, int)

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
        # 拖动行调序：只认本表格内部的拖拽（MoveAction），落点线自绘——Qt 默认
        # 指示器只在行上下 2px 边缘判 Above/Below，行中心是 OnItem（画整行框），
        # 对“插到某行前后”的语义不清楚，见 _resolve_drop / paintEvent
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(False)
        #: 按下时所在行（一次只拖这一行；多选时也不整组拖）
        self._drag_row: int | None = None
        #: 落点线的 y（视口坐标）；None = 不画
        self._drop_line_y: int | None = None
        #: 拖拽循环结束后才落地的移动意图（重建表格不能发生在循环里）
        self._pending_move: tuple[int, int] | None = None

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Insert:
            self.insert_requested.emit()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ 拖动调序
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            # 一次只拖一行：记住按下的那一行，startDrag 只用它
            self._drag_row = index.row() if index.isValid() else None
        super().mousePressEvent(event)

    def startDrag(self, supported_actions) -> None:  # noqa: N802 - Qt 命名
        row = self._drag_row
        if row is None or not 0 <= row < self.rowCount():
            return
        index = self.model().index(row, 0)
        # 拖拽影像只取这一行（整行宽），半透明，鼠标落点跟着按下位置
        rect = QRect(
            0, self.visualRect(index).top(), self.viewport().width(), self.rowHeight(row)
        ).intersected(self.viewport().rect())
        if rect.isEmpty():
            return
        mime = QMimeData()
        mime.setData(_WORK_ROW_MIME, str(row).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        dpr = self.devicePixelRatioF() or 1.0
        pixmap = QPixmap(rect.size() * dpr)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setOpacity(0.8)
        painter.drawPixmap(0, 0, self.viewport().grab(rect))
        painter.end()
        drag.setPixmap(pixmap)
        hotspot = self.viewport().mapFromGlobal(QCursor.pos()) - rect.topLeft()
        hotspot.setX(max(0, min(hotspot.x(), rect.width())))
        hotspot.setY(max(0, min(hotspot.y(), rect.height())))
        drag.setHotSpot(hotspot)
        # 只允许移动动作：Ctrl 等修饰键不会切成复制
        drag.exec(Qt.DropAction.MoveAction, Qt.DropAction.MoveAction)
        self._drag_row = None
        self._set_drop_line(None)
        # 拖拽循环结束后再改数据：循环里重建表格会拆掉正在拖的单元格控件
        self._consume_pending_move()

    def _consume_pending_move(self) -> None:
        """落地拖拽期间记下的移动意图（模态循环结束后才发信号）。"""
        pending, self._pending_move = self._pending_move, None
        if pending is not None:
            self.row_move_requested.emit(*pending)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.source() is not self or self._drag_row is None:
            event.ignore()
            return
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.source() is not self or self._drag_row is None:
            event.ignore()
            self._set_drop_line(None)
            return
        target = self._resolve_drop(event.position().toPoint())
        self._set_drop_line(target[1] if target is not None else None)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._set_drop_line(None)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        source = self._drag_row
        self._set_drop_line(None)
        if event.source() is not self or source is None:
            event.ignore()
            return
        event.acceptProposedAction()
        target = self._resolve_drop(event.position().toPoint())
        if target is not None:
            self._pending_move = (source, target[0])

    def _resolve_drop(self, pos: QPoint) -> tuple[int, int] | None:
        """落点 → ``(插入行, 落点线 y)``；原地不动返回 None。

        插入行 = 拖拽行插到该行之前（``rowCount()`` = 追加到末尾）。行的上下半
        自己判：上半插到该行之前、下半插到之后，落点线画在对应边界上；落在空白
        区（末行下方）按追加处理。
        """
        source = self._drag_row
        if source is None:
            return None
        row = self.rowAt(pos.y())
        if row < 0:
            # 落在末行下方的空白区：追加到末尾，线画在末行底边
            insert_row = self.rowCount()
            last = self.visualRect(self.model().index(self.rowCount() - 1, 0))
            y = 0 if last.isNull() else last.bottom() + 1
        else:
            rect = self.visualRect(self.model().index(row, 0))
            if pos.y() < rect.center().y():
                insert_row, y = row, rect.top()
            else:
                insert_row, y = row + 1, rect.bottom() + 1
        if insert_row in (source, source + 1):
            return None  # 原地（插到自己前面 / 后面）
        return insert_row, max(0, min(y, self.viewport().height() - 1))

    def _set_drop_line(self, y: int | None) -> None:
        if self._drop_line_y == y:
            return
        self._drop_line_y = y
        self.viewport().update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().paintEvent(event)
        y = self._drop_line_y
        if y is None:
            return
        painter = QPainter(self.viewport())
        painter.setPen(QPen(QColor(ThemeManager.instance().current().border_focus), 2))
        painter.drawLine(0, y, self.viewport().width(), y)
