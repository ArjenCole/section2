"""地基处理原则编辑对话框（复刻旧版 FmPcp/FormPF，460×400）。

布局与交互照抄 FormPF / FormPF.Designer：

* 顶部「原则名称」；v10 起「管道基础」板块（基础类型 / 基础角度 / 垫层材质 /
  厚度 mm，原在围护原则窗体里）并入本窗体，放在换填层板块上方；
* 换填层表（换填材质 / 厚度 mm / 行尾「-」删行按钮列，
  「+」在按钮列表头格，见 RowButtonColumn），板块高度至少容得下 3 行，
  4 行起出纵向滚动条；Insert 插入默认换填行（碎石，200）、Delete 删除选中行
  （无最少条数限制）；
* 底部「特殊地基」区：构件下拉 +「编辑」按钮（下拉与按钮宽度 2:1，同一行）；
* 描述 Label 在特殊地基框下方，作为整个窗体当前选择的总体描述（双击同样打开
  构件公式编辑；描述文案与旧版 FlashCpnt 一致）；
* 底部「取消 / 确认」按钮（Apple HIG：取消在左、确认在右），原则名称在确认时
  写回（重命名同步构件引用）；换填层与特殊地基构件的编辑只写共享会话、
  确认时统一落库，「取消」回滚会话整体丢弃。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
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
from app.core.models.models import FoundationReplacement, PcpFoundation
from app.services import project_io
from app.views.dialogs.principle_dialogs import ComponentEditDialog, describe_component
from app.views.widgets.cell_fill_table import CellFillTable
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox
from app.views.widgets.row_button_column import RowButtonColumn
from app.views.widgets.table_width import fixed_width_behavior

_COL_MATERIAL, _COL_THICKNESS = 0, 1

#: 「管道基础」板块选项（原围护原则窗体同款；v10 起并入地基原则）
_CONFOUND_CHOICES = ("采用混凝土基础", "不采用混凝土基础")
_ANGLE_CHOICES = ("90", "120", "150", "180")

#: 换填层板块最少要完整显示的行数（4 行起出纵向滚动条）
_MIN_VISIBLE_ROWS = 3
_ROW_HEIGHT = 32


class FoundationEditDialog(FramelessDialog):
    """地基处理原则编辑（FormPF，无边框自绘标题栏）。"""

    def __init__(self, foundation_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, "地基处理原则编辑")
        self.resize(460, 510)
        self._foundation_id = foundation_id
        self._loading = False
        self._build_ui()
        self._fill()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        # 布局落定后再按真实表头高度定板块高度（首帧 header 高度未定）
        QTimer.singleShot(0, self, self._fit_replace_height)

    def _fit_replace_height(self) -> None:
        """换填层板块恰好容得下表头 + 3 行（4 行起出纵向滚动条）。"""
        table = self._replace_table
        table.setFixedHeight(table.horizontalHeader().height() + _MIN_VISIBLE_ROWS * _ROW_HEIGHT)

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

        # 「管道基础」（原属围护原则窗体，v10 起并入地基原则），放在换填层上方；
        # 四个参数两行两列：基础类型 / 基础角度第一行，垫层材质 / 厚度第二行
        pipe_box = QGroupBox("管道基础")
        pipe_grid = QGridLayout(pipe_box)
        self._con_found = QComboBox()
        self._con_found.addItems(_CONFOUND_CHOICES)
        self._angle = QComboBox()
        self._angle.addItems(_ANGLE_CHOICES)
        self._cushion_name = QLineEdit()
        self._cushion_h = QLineEdit()
        pipe_grid.addWidget(QLabel("基础类型"), 0, 0)
        pipe_grid.addWidget(self._con_found, 0, 1)
        pipe_grid.addWidget(QLabel("基础角度"), 0, 2)
        pipe_grid.addWidget(self._angle, 0, 3)
        pipe_grid.addWidget(QLabel("垫层材质"), 1, 0)
        pipe_grid.addWidget(self._cushion_name, 1, 1)
        pipe_grid.addWidget(QLabel("厚度mm"), 1, 2)
        pipe_grid.addWidget(self._cushion_h, 1, 3)
        root.addWidget(pipe_box)

        replace_box = QGroupBox("换填层")
        replace_layout = QVBoxLayout(replace_box)
        self._replace_table = _ReplaceTable()
        self._replace_table.insert_requested.connect(self._insert_replacement)
        self._replace_table.delete_requested.connect(self._delete_selected_replacements)
        self._replace_table.cellChanged.connect(self._on_cell_changed)
        replace_layout.addWidget(self._replace_table, 1)
        # 「+ / -」按钮列（管材面板同款）：+ 在按钮列表头格，每行行尾「-」删该行
        self._replace_buttons = RowButtonColumn(
            self._replace_table,
            add_tooltip="添加换填层（Insert）",
            delete_tooltip="删除该换填层",
        )
        self._replace_buttons.add_clicked.connect(lambda: self._insert_replacement())
        self._replace_buttons.delete_clicked.connect(self._delete_replacement_row)
        self._replace_buttons.attach()
        root.addWidget(replace_box, 1)

        component_box = QGroupBox("特殊地基")
        component_form = QFormLayout(component_box)
        self._component_picker = QComboBox()
        self._component_picker.addItems(project_io.component_library().names("Fi"))
        self._component_picker.currentTextChanged.connect(self._on_component_pick)
        btn_edit = QPushButton("编辑")
        btn_edit.clicked.connect(self._edit_component)
        picker_row = QWidget()
        picker_layout = QHBoxLayout(picker_row)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        picker_layout.setSpacing(6)
        picker_layout.addWidget(self._component_picker, 2)
        picker_layout.addWidget(btn_edit, 1)
        component_form.addRow(QLabel("构件类型"), picker_row)
        root.addWidget(component_box)

        # 描述在特殊地基框下方，作为整个窗体当前选择的总体描述
        self._describe = QLabel("")
        self._describe.setProperty("role", "hint")
        self._describe.setWordWrap(True)
        self._describe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._describe)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        # Apple HIG：取消在左，确认（默认按钮）在右
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedWidth(76)
        btn_cancel.clicked.connect(self.reject)
        btn_yes = QPushButton("确认")
        btn_yes.setFixedWidth(76)
        btn_yes.setProperty("primary", "true")
        btn_yes.setDefault(True)
        btn_yes.clicked.connect(self._confirm)
        button_row.addWidget(btn_cancel)
        button_row.addWidget(btn_yes)
        root.addLayout(button_row)

    # ------------------------------------------------------------------ 数据
    def _foundation(self) -> PcpFoundation | None:
        # 提交/直改后已加载的 replacements/components 集合不会自动刷新，取用时
        # 强制重载；expire 后的重载路径不做 autoflush，先把未 flush 的编辑写进
        # 事务（flush 不提交，「取消」的回滚仍然整体丢弃）
        orm.session().flush()
        foundation = orm.session().get(PcpFoundation, self._foundation_id)
        if foundation is not None:
            orm.session().expire(foundation)
        return foundation

    def _fill(self) -> None:
        self._loading = True
        try:
            foundation = self._foundation()
            if foundation is None:
                return
            self._name.setText(foundation.name)
            self._con_found.setCurrentIndex(0 if foundation.con_found else 1)
            self._angle.setCurrentText(str(foundation.found_angle))
            cushion = foundation.cushions[0] if foundation.cushions else None
            self._cushion_name.setText(cushion.name if cushion else "")
            self._cushion_h.setText(f"{cushion.h:g}" if cushion else "0")
            replacements = list(foundation.replacements)
            self._replace_buttons.clear_row_buttons()
            self._replace_table.setRowCount(len(replacements))
            for row_index, replacement in enumerate(replacements):
                name_item = QTableWidgetItem(replacement.name)
                name_item.setData(Qt.ItemDataRole.UserRole, replacement.id)
                self._replace_table.setItem(row_index, _COL_MATERIAL, name_item)
                self._replace_table.setItem(row_index, _COL_THICKNESS, QTableWidgetItem(f"{replacement.h:g}"))
                # 行尾「-」删行按钮：一行一个（无行即无按钮，删除无最少条数限制）
                self._replace_buttons.add_row_button(row_index)
            component = foundation.components[0] if foundation.components else None
            self._component_picker.blockSignals(True)
            if component is not None:
                self._component_picker.setCurrentText(component.name)
            self._component_picker.blockSignals(False)
            self._refresh_describe()
        finally:
            self._loading = False

    def _refresh_describe(self) -> None:
        """FlashCpnt：描述 = 换填层数说明 + 构件描述 + 句号。"""
        foundation = self._foundation()
        if foundation is None:
            return
        component = foundation.components[0] if foundation.components else None
        head = f"本原则采用{len(foundation.replacements)}层换填；" if foundation.replacements else "不采用换填；"
        self._describe.setText(head + describe_component(component) + "。")

    # ------------------------------------------------------------------ 表格交互
    def _on_cell_changed(self, row: int, column: int) -> None:
        if self._loading:
            return
        foundation = self._foundation()
        if foundation is None or row >= len(foundation.replacements):
            return
        replacement = foundation.replacements[row]
        item = self._replace_table.item(row, column)
        if item is None:
            return
        if column == _COL_MATERIAL:
            replacement.name = item.text()
        else:
            try:
                replacement.h = float(item.text() or 0)
            except ValueError:
                pass
        self._refresh_describe()

    def _on_component_pick(self, text: str) -> None:
        """CBOcpnt_DropDownClosed：切换特殊地基构件（从库模板重建）。"""
        if self._loading or not text:
            return
        foundation = self._foundation()
        if foundation is None:
            return
        old = foundation.components[0] if foundation.components else None
        if old is not None and old.name == text:
            return
        if old is not None:
            orm.session().delete(old)
        project_io.attach_foundation_component(
            orm.session(), foundation, project_io.component_library(), name=text
        )
        self._refresh_describe()

    def _edit_component(self) -> None:
        foundation = self._foundation()
        if foundation is None:
            return
        component = foundation.components[0] if foundation.components else None
        if component is None:
            return
        dialog = ComponentEditDialog(component, self)
        if dialog.exec() and dialog.saved:
            self._refresh_describe()

    # ------------------------------------------------------------------ 换填层 Insert/Delete
    def _insert_replacement(self, position: int | None = None) -> None:
        foundation = self._foundation()
        if foundation is None:
            return
        replacements = list(foundation.replacements)
        if position is None or position < 0 or position > len(replacements):
            position = len(replacements)
        for item in replacements[position:]:
            item.order_no += 1
        foundation.replacements.append(
            FoundationReplacement(foundation_id=foundation.id, name="碎石", h=200.0, order_no=position)
        )
        for index, item in enumerate(sorted(foundation.replacements, key=lambda r: (r.order_no, r.id))):
            item.order_no = index
        self._fill()

    def _delete_selected_replacements(self) -> None:
        rows = sorted({index.row() for index in self._replace_table.selectedIndexes()}, reverse=True)
        self._delete_replacements(rows)

    def _delete_replacement_row(self, row: int) -> None:
        """行尾「-」：删该行换填层（无最少条数限制，删空即不换填）。"""
        self._delete_replacements([row])

    def _delete_replacements(self, rows: list[int]) -> None:
        foundation = self._foundation()
        if foundation is None or not rows:
            return
        replacements = list(foundation.replacements)
        for row in rows:
            if row < len(replacements):
                orm.session().delete(replacements[row])
        orm.session().flush()
        orm.session().expire(foundation)  # 集合里还留着已删对象，强制重载
        for index, item in enumerate(foundation.replacements):
            item.order_no = index
        self._fill()

    # ------------------------------------------------------------------ 确认 / 取消
    def reject(self) -> None:  # noqa: N802 - Qt 命名
        """取消：回滚会话，丢弃换填层与特殊地基构件的全部未落库修改。

        编辑过程只写共享会话不 commit（按钮、标题栏 X、Esc 关闭都汇到这里），
        因此一次回滚即可整体复原。
        """
        orm.session().rollback()
        super().reject()

    def _confirm(self) -> None:
        """BTNyes：名称 + 管道基础写回（mscCtrl.Set 同步引用）。

        编辑过程中（换填层、特殊地基构件）不广播，点击确认修改后统一刷新
        工程量与断面图；改名时再广播 tree_structure_changed 同步引用名。
        管道基础的砼基础开关 / 角度变化经 apply_foundation 触发候选组重选。
        """
        foundation = self._foundation()
        if foundation is None:
            self.accept()
            return
        name = self._name.text().strip()
        if not name:
            FramelessMessageBox.warning(self, "提示", "原则名称不得为空。")
            return
        cushion_name = self._cushion_name.text().strip()
        if not cushion_name:
            FramelessMessageBox.warning(self, "提示", "垫层材质不能为空。")
            return
        try:
            cushion_h = float(self._cushion_h.text() or 0)
        except ValueError:
            FramelessMessageBox.warning(self, "提示", "垫层厚度需为数字（mm）。")
            return
        if name != foundation.name:
            project_io.rename_foundation(foundation.id, name)
            bus().tree_structure_changed.emit()
        # 管道基础字段 / 垫层走 principle_edit.apply_foundation：砼基础开关 /
        # 基础角度变化时它会对引用该原则的直埋构件自动重选候选组
        from app.services.principle_edit import apply_foundation

        fields: dict = {"con_found": "不" not in self._con_found.currentText()}
        try:
            fields["found_angle"] = int(self._angle.currentText())
        except ValueError:
            pass
        apply_foundation(
            foundation.id,
            fields=fields,
            cushions=[{"name": cushion_name, "h": cushion_h}],
        )
        # 本次编辑（换填层、特殊地基构件）随这次提交统一落库
        project_io.commit()
        bus().principle_changed.emit()
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        super().keyPressEvent(event)  # Esc = 取消（与原版一致）


class _ReplaceTable(CellFillTable):
    """换填层表：Insert 插入 / Delete 删除选中行（原版 dGVR_KeyUp）；末列空表头 = 按钮列。"""

    insert_requested = Signal(int)
    delete_requested = Signal()

    def __init__(self) -> None:
        super().__init__(0, 3)
        self.setHorizontalHeaderLabels(["换填材质", "厚度 mm", ""])
        # 固定列宽（可拖动）：表格不随窗体拉伸，右侧留白 / 窄时出横向滚动条
        fixed_width_behavior(self)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        self.setColumnWidth(0, 130)
        self.setColumnWidth(1, 120)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Insert:
            self.insert_requested.emit(self.currentRow())
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)
