"""原则横条（复刻旧版 FormMdi 的 panelPrincple，位于主表格上方）。

布局照抄原版：左侧竖排「沟槽围护 / 地基处理」单选（原版 RBmPE / RBmPF 上下排列）+
原则名标签横排（围护底色 #448AFF、地基底色 #455A64、白字居中），「+」按钮紧贴
最右侧原则块（原版 BTNaddPCP 与标签同处一个滚动区）。

交互照抄原版：

* 双击标签 → 打开对应原则编辑窗体（FormPE / FormPF 复刻对话框）；
* 右键标签 → 菜单：编辑原则 / 导入原则 / 导出原则 / 删除原则 /
  添加沟槽围护原则 / 添加地基处理原则（导入导出为 *.spcp）；
* 「+」→ 按当前单选直接新建（默认名重名自动加后缀，不弹输入框）；
* 删除 → 只剩一条时提示「至少需要一种…」；否则确认后引用并入另一条原则。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.event_bus import bus
from app.services import project_io
from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog
from app.views.dialogs.foundation_edit_dialog import FoundationEditDialog
from app.views.widgets.frameless_dialog import FramelessMessageBox

_KIND_ENCLOSURE = "enclosure"
_KIND_FOUNDATION = "foundation"

#: 原版 NewPrincpleLab 的标签样式
_LABEL_SIZE = (200, 40)
_ENCLOSURE_COLOR = "#448AFF"
_FOUNDATION_COLOR = "#455A64"


class PrincipleBar(QWidget):
    """主表格上方的原则横条。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._menu_name = ""  # 右键时记住的原则名（原版 CMSpcp.Text）
        self._build_ui()
        bus().project_opened.connect(lambda _path: self.reload())
        bus().project_closed.connect(self._on_project_closed)
        bus().tree_structure_changed.connect(self.reload)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # 单选竖排（原版 RBmPE 上、RBmPF 下）
        radio_column = QVBoxLayout()
        radio_column.setSpacing(2)
        self._radio_enclosure = QRadioButton("沟槽围护")
        self._radio_enclosure.setChecked(True)
        self._radio_enclosure.toggled.connect(self._reload_labels)
        self._radio_foundation = QRadioButton("地基处理")
        radio_column.addWidget(self._radio_enclosure)
        radio_column.addWidget(self._radio_foundation)
        layout.addLayout(radio_column)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setProperty("role", "hline")
        layout.addWidget(line)

        # 标签 + 「+」按钮同处一个滚动区，「+」始终紧贴最右侧原则块
        self._label_host = QWidget()
        self._label_layout = QHBoxLayout(self._label_host)
        self._label_layout.setContentsMargins(0, 0, 0, 0)
        self._label_layout.setSpacing(4)
        self._btn_add = QPushButton("+")
        self._btn_add.setProperty("role", "icon-btn")
        self._btn_add.setFixedSize(32, 41)
        self._btn_add.clicked.connect(self._add_principle)
        self._label_layout.addWidget(self._btn_add)
        self._label_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(self._label_host)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(_LABEL_SIZE[1] + 8)
        layout.addWidget(scroll, 1)

    # ------------------------------------------------------------------ 刷新
    def reload(self) -> None:
        """FlashPrincpleTab：按当前工程重建标签。"""
        visible = project_io.is_open()
        self.setVisible(visible)
        if not visible:
            return
        self._reload_labels()

    def _on_project_closed(self) -> None:
        self.setVisible(False)

    def _reload_labels(self) -> None:
        while self._label_layout.count():
            item = self._label_layout.takeAt(0)
            widget = item.widget()
            # 「+」按钮是常驻控件，重建标签时保留
            if widget is not None and widget is not self._btn_add:
                widget.deleteLater()
        if self._radio_enclosure.isChecked():
            for enclosure in project_io.enclosures():
                self._label_layout.addWidget(
                    self._make_label(_KIND_ENCLOSURE, enclosure.name, _ENCLOSURE_COLOR)
                )
        else:
            for foundation in project_io.foundations():
                self._label_layout.addWidget(
                    self._make_label(_KIND_FOUNDATION, foundation.name, _FOUNDATION_COLOR)
                )
        self._label_layout.addWidget(self._btn_add)
        self._label_layout.addStretch(1)

    def _make_label(self, kind: str, name: str, color: str) -> QLabel:
        label = _PrincipleLabel(kind, name)
        label.setFixedSize(*_LABEL_SIZE)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"background-color: {color}; color: #FFFFFF;"
            "font-family: 'Microsoft YaHei'; font-size: 13pt; border-radius: 3px;"
        )
        label.double_clicked.connect(self._open_editor)
        label.right_clicked.connect(self._show_context_menu)
        return label

    # ------------------------------------------------------------------ 新建
    def _add_principle(self) -> None:
        """BTNaddPCP：按当前单选直接新建，不弹输入框。"""
        if not project_io.is_open():
            return
        if self._radio_enclosure.isChecked():
            created = project_io.create_enclosure()
            self._radio_enclosure.setChecked(True)
        else:
            created = project_io.create_foundation()
            self._radio_foundation.setChecked(True)
        if created is not None:
            bus().tree_structure_changed.emit()
            bus().status_message.emit(f"已添加原则“{created.name}”", 3000)

    def add_enclosure(self) -> None:
        """菜单「添加沟槽围护原则」入口。"""
        self._radio_enclosure.setChecked(True)
        self._add_principle()

    def add_foundation(self) -> None:
        """菜单「添加地基处理原则」入口。"""
        self._radio_foundation.setChecked(True)
        self._add_principle()

    # ------------------------------------------------------------------ 编辑 / 右键菜单
    def _open_editor(self, kind: str, name: str) -> None:
        """ShowPEPF：双击标签打开 FormPE / FormPF 复刻对话框。"""
        if kind == _KIND_ENCLOSURE:
            enclosure = next((e for e in project_io.enclosures() if e.name == name), None)
            if enclosure is not None:
                EnclosureEditDialog(enclosure.id, self).exec()
        else:
            foundation = next((f for f in project_io.foundations() if f.name == name), None)
            if foundation is not None:
                FoundationEditDialog(foundation.id, self).exec()

    def show_editor(self, kind: str, name: str) -> None:
        """外部入口（项目菜单/树）：打开原则编辑器。"""
        if kind == _KIND_FOUNDATION:
            self._radio_foundation.setChecked(True)
        else:
            self._radio_enclosure.setChecked(True)
        self._open_editor(kind, name)

    def _show_context_menu(self, kind: str, name: str, global_pos) -> None:
        """PrincpleLab_MouseUp：右键菜单（编辑/导入/导出/删除/添加）。"""
        self._menu_name = name
        menu = QMenu(self)
        menu.addAction("编辑原则", lambda: self._open_editor(kind, name))
        menu.addAction("导入原则", self._import_principle)
        menu.addAction("导出原则", lambda: self._export_principle(kind, name))
        menu.addAction("删除原则", lambda: self._delete_principle(kind, name))
        menu.addSeparator()
        menu.addAction("添加沟槽围护原则", self.add_enclosure)
        menu.addAction("添加地基处理原则", self.add_foundation)
        menu.exec(global_pos)

    def _delete_principle(self, kind: str, name: str) -> None:
        if kind == _KIND_ENCLOSURE:
            target = project_io.merge_target_enclosure(name)
            enclosure = next((e for e in project_io.enclosures() if e.name == name), None)
            if enclosure is None:
                return
            if target is None:
                FramelessMessageBox.information(self, "提示", "至少需要一种沟槽围护原则。")
                return
            answer = FramelessMessageBox.question(
                self, "提示",
                f"删除后该原则的引用将被<{target}>替代,确认删除?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            error = project_io.delete_enclosure(enclosure.id, target)
            if error:
                FramelessMessageBox.information(self, "提示", error)
        else:
            target = project_io.merge_target_foundation(name)
            foundation = next((f for f in project_io.foundations() if f.name == name), None)
            if foundation is None:
                return
            if target is None:
                FramelessMessageBox.information(self, "提示", "至少需要一种地基处理原则。")
                return
            answer = FramelessMessageBox.question(
                self, "提示",
                f"删除后该原则的引用将被<{target}>替代,确认删除?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            error = project_io.delete_foundation(foundation.id, target)
            if error:
                FramelessMessageBox.information(self, "提示", error)
        bus().tree_structure_changed.emit()

    def _export_principle(self, kind: str, name: str) -> None:
        """导出原则 → *.spcp（原版 mscXML.SaveXml）。"""
        default = f"{name}.spcp"
        path, _filter = QFileDialog.getSaveFileName(self, "导出原则", default, "原则文件 (*.spcp)")
        if not path:
            return
        try:
            if kind == _KIND_ENCLOSURE:
                enclosure = next((e for e in project_io.enclosures() if e.name == name), None)
                if enclosure is not None:
                    project_io.export_enclosure_spcp(enclosure.id, path)
            else:
                foundation = next((f for f in project_io.foundations() if f.name == name), None)
                if foundation is not None:
                    project_io.export_foundation_spcp(foundation.id, path)
        except Exception as error:
            FramelessMessageBox.warning(self, "导出失败", str(error))
            return
        bus().status_message.emit(f"原则已导出：{path}", 3000)

    def _import_principle(self) -> None:
        """导入 *.spcp（原版按根元素分派类型，导入后切到对应单选）。"""
        path, _filter = QFileDialog.getOpenFileName(self, "导入原则", "", "原则文件 (*.spcp)")
        if not path:
            return
        try:
            kind, name = project_io.import_spcp(path)
        except Exception as error:
            FramelessMessageBox.warning(self, "导入失败", str(error))
            return
        if kind == _KIND_ENCLOSURE:
            self._radio_enclosure.setChecked(True)
        else:
            self._radio_foundation.setChecked(True)
        bus().tree_structure_changed.emit()
        bus().status_message.emit(f"已导入原则“{name}”", 3000)


class _PrincipleLabel(QLabel):
    """原则标签：双击打开编辑，右键弹菜单（原版无单击选中态）。"""

    double_clicked = Signal(str, str)
    right_clicked = Signal(str, str, object)

    def __init__(self, kind: str, name: str) -> None:
        super().__init__(name)
        self._kind = kind
        self._name = name

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._kind, self._name)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self._kind, self._name, event.globalPosition().toPoint())
        super().mousePressEvent(event)
