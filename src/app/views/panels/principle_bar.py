"""原则横条（复刻旧版 FormMdi 的 panelPrincple，位于主表格上方）。

布局：左侧竖排四个单选「沟槽围护 / 地基处理 / 降水原则 / 面宽原则」（原版
RBmPE / RBmPF 上下排列，v4 起降水与面宽独立成原则）+ 原则名标签横排
（围护底色 #448AFF、地基底色 #455A64、降水底色 #26A69A、面宽底色 #7E57C2、
白字居中），「+」按钮紧贴最右侧原则块（原版 BTNaddPCP 与标签同处一个滚动区）。

交互照抄原版：

* 双击标签 → 打开对应原则编辑窗体（FormPE / FormPF 复刻对话框 + 降水/面宽窗体）；
* 右键标签 → 菜单：编辑原则 / 导入原则 / 导出原则 / 删除原则 /
  添加各类原则（导入导出为 *.spcp）；
* 「+」→ 按当前单选直接新建（默认名重名自动加后缀，不弹输入框）；
* 删除 → 只剩一条时提示「至少需要一种…」；否则确认后引用并入另一条原则。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QWidget,
)

from app.core.event_bus import bus
from app.services import project_io
from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog
from app.views.dialogs.foundation_edit_dialog import FoundationEditDialog
from app.views.dialogs.principle_dialogs import PrecipitationEditDialog, WidthEditDialog
from app.views.widgets.frameless_dialog import FramelessMessageBox

_KIND_ENCLOSURE = "enclosure"
_KIND_FOUNDATION = "foundation"
_KIND_PRECIPITATION = "precipitation"
_KIND_WIDTH = "width"

#: 原版 NewPrincpleLab 的标签样式
_LABEL_SIZE = (200, 40)
#: 四类原则的卡片底色：围护蓝 / 地基石板 / 降水青 / 面宽紫
_KIND_COLORS = {
    _KIND_ENCLOSURE: "#448AFF",
    _KIND_FOUNDATION: "#455A64",
    _KIND_PRECIPITATION: "#26A69A",
    _KIND_WIDTH: "#7E57C2",
}
_KIND_RADIO_TEXT = {
    _KIND_ENCLOSURE: "沟槽围护",
    _KIND_FOUNDATION: "地基处理",
    _KIND_PRECIPITATION: "降水原则",
    _KIND_WIDTH: "面宽原则",
}
_KIND_ADD_MENU_TEXT = {
    _KIND_ENCLOSURE: "添加沟槽围护原则",
    _KIND_FOUNDATION: "添加地基处理原则",
    _KIND_PRECIPITATION: "添加降水原则",
    _KIND_WIDTH: "添加面宽原则",
}
_KIND_MIN_TEXT = {
    _KIND_ENCLOSURE: "至少需要一种沟槽围护原则。",
    _KIND_FOUNDATION: "至少需要一种地基处理原则。",
    _KIND_PRECIPITATION: "至少需要一种降水原则。",
    _KIND_WIDTH: "至少需要一种面宽原则。",
}


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

        # 单选竖排（原版 RBmPE / RBmPF，v4 起加降水、面宽两行）
        radio_grid = QGridLayout()
        radio_grid.setContentsMargins(0, 0, 0, 0)
        radio_grid.setHorizontalSpacing(8)
        radio_grid.setVerticalSpacing(2)
        self._radios: dict[str, QRadioButton] = {}
        for order, kind in enumerate((_KIND_ENCLOSURE, _KIND_FOUNDATION, _KIND_PRECIPITATION, _KIND_WIDTH)):
            radio = QRadioButton(_KIND_RADIO_TEXT[kind])
            if order == 0:
                radio.setChecked(True)
            radio.toggled.connect(self._reload_labels)
            radio_grid.addWidget(radio, order % 2, order // 2)
            self._radios[kind] = radio
        layout.addLayout(radio_grid)

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

    def _current_kind(self) -> str:
        for kind, radio in self._radios.items():
            if radio.isChecked():
                return kind
        return _KIND_ENCLOSURE

    def _principle_names(self, kind: str) -> list[str]:
        if kind == _KIND_ENCLOSURE:
            return [item.name for item in project_io.enclosures()]
        if kind == _KIND_FOUNDATION:
            return [item.name for item in project_io.foundations()]
        if kind == _KIND_PRECIPITATION:
            return [item.name for item in project_io.precipitations()]
        return [item.name for item in project_io.width_principles()]

    def _reload_labels(self) -> None:
        while self._label_layout.count():
            item = self._label_layout.takeAt(0)
            widget = item.widget()
            # 「+」按钮是常驻控件，重建标签时保留
            if widget is not None and widget is not self._btn_add:
                widget.deleteLater()
        kind = self._current_kind()
        for name in self._principle_names(kind):
            self._label_layout.addWidget(self._make_label(kind, name, _KIND_COLORS[kind]))
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
        kind = self._current_kind()
        creators = {
            _KIND_ENCLOSURE: project_io.create_enclosure,
            _KIND_FOUNDATION: project_io.create_foundation,
            _KIND_PRECIPITATION: project_io.create_precipitation,
            _KIND_WIDTH: project_io.create_width,
        }
        created = creators[kind]()
        if created is not None:
            bus().tree_structure_changed.emit()
            bus().status_message.emit(f"已添加原则“{created.name}”", 3000)

    def add_enclosure(self) -> None:
        """菜单「添加沟槽围护原则」入口。"""
        self._radios[_KIND_ENCLOSURE].setChecked(True)
        self._add_principle()

    def add_foundation(self) -> None:
        """菜单「添加地基处理原则」入口。"""
        self._radios[_KIND_FOUNDATION].setChecked(True)
        self._add_principle()

    def add_precipitation(self) -> None:
        """菜单「添加降水原则」入口。"""
        self._radios[_KIND_PRECIPITATION].setChecked(True)
        self._add_principle()

    def add_width(self) -> None:
        """菜单「添加面宽原则」入口。"""
        self._radios[_KIND_WIDTH].setChecked(True)
        self._add_principle()

    # ------------------------------------------------------------------ 编辑 / 右键菜单
    def _open_editor(self, kind: str, name: str) -> None:
        """ShowPEPF：双击标签打开对应原则编辑对话框。"""
        if kind == _KIND_ENCLOSURE:
            enclosure = next((e for e in project_io.enclosures() if e.name == name), None)
            if enclosure is not None:
                EnclosureEditDialog(enclosure.id, self).exec()
        elif kind == _KIND_FOUNDATION:
            foundation = next((f for f in project_io.foundations() if f.name == name), None)
            if foundation is not None:
                FoundationEditDialog(foundation.id, self).exec()
        elif kind == _KIND_PRECIPITATION:
            precipitation = next((p for p in project_io.precipitations() if p.name == name), None)
            if precipitation is not None:
                PrecipitationEditDialog(precipitation.id, self).exec()
        else:
            width = next((w for w in project_io.width_principles() if w.name == name), None)
            if width is not None:
                WidthEditDialog(width.id, self).exec()

    def _show_context_menu(self, kind: str, name: str, global_pos) -> None:
        """PrincpleLab_MouseUp：右键菜单（编辑/导入/导出/删除/添加）。"""
        self._menu_name = name
        menu = QMenu(self)
        menu.addAction("编辑原则", lambda: self._open_editor(kind, name))
        menu.addAction("导入原则", self._import_principle)
        menu.addAction("导出原则", lambda: self._export_principle(kind, name))
        menu.addAction("删除原则", lambda: self._delete_principle(kind, name))
        menu.addSeparator()
        for add_kind in (_KIND_ENCLOSURE, _KIND_FOUNDATION, _KIND_PRECIPITATION, _KIND_WIDTH):
            menu.addAction(_KIND_ADD_MENU_TEXT[add_kind], lambda k=add_kind: self._add_kind(k))
        menu.exec(global_pos)

    def _add_kind(self, kind: str) -> None:
        self._radios[kind].setChecked(True)
        self._add_principle()

    def _delete_principle(self, kind: str, name: str) -> None:
        if kind == _KIND_ENCLOSURE:
            target = project_io.merge_target_enclosure(name)
            found = next((e for e in project_io.enclosures() if e.name == name), None)
        elif kind == _KIND_FOUNDATION:
            target = project_io.merge_target_foundation(name)
            found = next((f for f in project_io.foundations() if f.name == name), None)
        elif kind == _KIND_PRECIPITATION:
            target = project_io.merge_target_precipitation(name)
            found = next((p for p in project_io.precipitations() if p.name == name), None)
        else:
            target = project_io.merge_target_width(name)
            found = next((w for w in project_io.width_principles() if w.name == name), None)
        if found is None:
            return
        if target is None:
            FramelessMessageBox.information(self, "提示", _KIND_MIN_TEXT[kind])
            return
        answer = FramelessMessageBox.question(
            self, "提示",
            f"删除后该原则的引用将被<{target}>替代,确认删除?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        deleters = {
            _KIND_ENCLOSURE: lambda: project_io.delete_enclosure(found.id, target),
            _KIND_FOUNDATION: lambda: project_io.delete_foundation(found.id, target),
            _KIND_PRECIPITATION: lambda: project_io.delete_precipitation(found.id, target),
            _KIND_WIDTH: lambda: project_io.delete_width(found.id, target),
        }
        error = deleters[kind]()
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
                found = next((e for e in project_io.enclosures() if e.name == name), None)
                if found is not None:
                    project_io.export_enclosure_spcp(found.id, path)
            elif kind == _KIND_FOUNDATION:
                found = next((f for f in project_io.foundations() if f.name == name), None)
                if found is not None:
                    project_io.export_foundation_spcp(found.id, path)
            elif kind == _KIND_PRECIPITATION:
                found = next((p for p in project_io.precipitations() if p.name == name), None)
                if found is not None:
                    project_io.export_precipitation_spcp(found.id, path)
            else:
                found = next((w for w in project_io.width_principles() if w.name == name), None)
                if found is not None:
                    project_io.export_width_spcp(found.id, path)
        except Exception as error:
            FramelessMessageBox.warning(self, "导出失败", str(error))
            return
        bus().status_message.emit(f"原则已导出：{path}", 3000)

    def _import_principle(self) -> None:
        """导入 *.spcp（按根元素分派类型，导入后切到对应单选）。"""
        path, _filter = QFileDialog.getOpenFileName(self, "导入原则", "", "原则文件 (*.spcp)")
        if not path:
            return
        try:
            kind, name = project_io.import_spcp(path)
        except Exception as error:
            FramelessMessageBox.warning(self, "导入失败", str(error))
            return
        if kind in self._radios:
            self._radios[kind].setChecked(True)
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
