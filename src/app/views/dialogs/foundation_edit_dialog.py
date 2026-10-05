"""地基处理原则编辑对话框（复刻旧版 FmPcp/FormPF，301×400）。

布局与交互照抄 FormPF / FormPF.Designer：

* 顶部「原则名称」；换填层表（换填材质 / 厚度 mm）+「+」按钮，
  Insert 插入默认换填行（碎石，200）、Delete 删除选中行（无最少条数限制）；
* 底部「特殊地基」区：构件下拉（Fi 库）+「编辑」按钮 + 描述 Label
  （双击同样打开构件公式编辑；描述文案与旧版 FlashCpnt 一致）；
* 底部「确认修改 / 取消修改」，原则名称在确认时写回（重命名同步构件引用）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
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

_COL_MATERIAL, _COL_THICKNESS = 0, 1


class FoundationEditDialog(FramelessDialog):
    """地基处理原则编辑（FormPF，无边框自绘标题栏）。"""

    def __init__(self, foundation_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, "地基处理原则编辑")
        self.resize(460, 400)
        self._foundation_id = foundation_id
        self._loading = False
        self._build_ui()
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

        replace_box = QGroupBox("换填层")
        replace_layout = QVBoxLayout(replace_box)
        table_row = QHBoxLayout()
        self._replace_table = _ReplaceTable()
        self._replace_table.insert_requested.connect(self._insert_replacement)
        self._replace_table.delete_requested.connect(self._delete_selected_replacements)
        self._replace_table.cellChanged.connect(self._on_cell_changed)
        self._replace_table.horizontalHeader().setStretchLastSection(True)
        table_row.addWidget(self._replace_table, 1)
        self._btn_add = QPushButton("+")
        self._btn_add.setProperty("role", "icon-btn")
        self._btn_add.setFixedSize(28, 28)
        self._btn_add.clicked.connect(lambda: self._insert_replacement())
        table_row.addWidget(self._btn_add)
        replace_layout.addLayout(table_row)
        root.addWidget(replace_box, 1)

        component_box = QGroupBox("特殊地基")
        component_form = QFormLayout(component_box)
        self._component_picker = QComboBox()
        self._component_picker.addItems(project_io.component_library().names("Fi"))
        self._component_picker.currentTextChanged.connect(self._on_component_pick)
        self._describe = QLabel("")
        self._describe.setProperty("role", "hint")
        self._describe.setWordWrap(True)
        self._describe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        component_form.addRow(QLabel("构件类型"), self._component_picker)
        component_form.addRow(QLabel("描述"), self._describe)
        btn_edit = QPushButton("编辑")
        btn_edit.clicked.connect(self._edit_component)
        component_form.addRow("", btn_edit)
        root.addWidget(component_box)
        # 描述 Label 双击 → 编辑构件（原版 LBLcpnt_DoubleClick）
        self._describe.mouseDoubleClickEvent = lambda _event: self._edit_component()  # type: ignore[method-assign]

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        btn_yes = QPushButton("确认修改")
        btn_yes.setFixedWidth(76)
        btn_yes.setProperty("primary", "true")
        btn_yes.clicked.connect(self._confirm)
        btn_cancel = QPushButton("取消修改")
        btn_cancel.setFixedWidth(76)
        btn_cancel.clicked.connect(self.reject)
        button_row.addWidget(btn_yes)
        button_row.addWidget(btn_cancel)
        root.addLayout(button_row)

    # ------------------------------------------------------------------ 数据
    def _foundation(self) -> PcpFoundation | None:
        foundation = orm.session().get(PcpFoundation, self._foundation_id)
        if foundation is not None:
            # 提交/直改后已加载的 replacements/components 集合不会自动刷新，取用时强制重载
            orm.session().expire(foundation)
        return foundation

    def _fill(self) -> None:
        self._loading = True
        try:
            foundation = self._foundation()
            if foundation is None:
                return
            orm.session().expire(foundation)  # 提交后强制重载 replacements/components
            self._name.setText(foundation.name)
            replacements = list(foundation.replacements)
            self._replace_table.setRowCount(len(replacements))
            for row_index, replacement in enumerate(replacements):
                name_item = QTableWidgetItem(replacement.name)
                name_item.setData(Qt.ItemDataRole.UserRole, replacement.id)
                self._replace_table.setItem(row_index, _COL_MATERIAL, name_item)
                self._replace_table.setItem(row_index, _COL_THICKNESS, QTableWidgetItem(f"{replacement.h:g}"))
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
        project_io.commit()
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
        project_io.commit()
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
            project_io.commit()
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
        project_io.commit()
        self._fill()

    def _delete_selected_replacements(self) -> None:
        foundation = self._foundation()
        if foundation is None:
            return
        rows = sorted({index.row() for index in self._replace_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            if row < len(foundation.replacements):
                orm.session().delete(foundation.replacements[row])
        orm.session().flush()
        orm.session().expire(foundation)  # 集合里还留着已删对象，强制重载
        for index, item in enumerate(foundation.replacements):
            item.order_no = index
        project_io.commit()
        self._fill()

    # ------------------------------------------------------------------ 确认 / 取消
    def _confirm(self) -> None:
        """BTNyes：名称写回（mscCtrl.Set 同步引用）。

        编辑过程中（换填层、特殊地基构件）不广播，点击确认修改后统一刷新
        工程量与断面图；改名时再广播 tree_structure_changed 同步引用名。
        """
        foundation = self._foundation()
        if foundation is None:
            self.accept()
            return
        name = self._name.text().strip()
        if not name:
            FramelessMessageBox.warning(self, "提示", "原则名称不得为空。")
            return
        if name != foundation.name:
            project_io.rename_foundation(foundation.id, name)
            bus().tree_structure_changed.emit()
        project_io.commit()
        bus().principle_changed.emit()
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        super().keyPressEvent(event)  # Esc = 取消（与原版一致）


class _ReplaceTable(CellFillTable):
    """换填层表：Insert 插入 / Delete 删除选中行（原版 dGVR_KeyUp）。"""

    insert_requested = Signal(int)
    delete_requested = Signal()

    def __init__(self) -> None:
        super().__init__(0, 2)
        self.setHorizontalHeaderLabels(["换填材质", "厚度 mm"])
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.verticalHeader().setVisible(False)
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
