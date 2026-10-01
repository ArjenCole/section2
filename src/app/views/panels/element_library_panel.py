"""构件库面板（复刻旧版 FormMdi 左栏下半段：CBOEleIvt + TVEleIvt）。

数据来自 app/resources/inventory/EleInventory.stn（旧版元素库，直接复用）：
顶部类别下拉（直埋混凝土管 / 直埋塑料管 / 直埋金属类管道 / 混凝土结构 / 非开挖管道），
下方两级树（单元 → 元素，元素文本 = 名称或规格）。
双击元素条目 → 发 insert_requested，由主窗口插入当前单位工程主表格。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.event_bus import bus
from app.services.element_library import element_library

_ROLE_TEMPLATE = Qt.ItemDataRole.UserRole + 1


class ElementLibraryPanel(QWidget):
    """构件库（元素模板库）。"""

    #: 双击元素模板（ElementTemplate）
    insert_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEnabled(False)  # 未打开工程前禁用（原版 FlashControlsEnable）
        self._build_ui()
        self._connect()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("构件库")
        title.setProperty("role", "panel-title")
        layout.addWidget(title)

        self._combo = QComboBox()
        self._combo.currentTextChanged.connect(lambda _text: self._reload_tree())
        layout.addWidget(self._combo)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.itemDoubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self._tree, 1)

    def _connect(self) -> None:
        # 复刻原版 FlashControlsEnable：未打开工程时构件库禁用
        bus().project_opened.connect(lambda _path: self.setEnabled(True))
        bus().project_closed.connect(lambda: self.setEnabled(False))

    def reload(self) -> None:
        library = element_library()
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(list(library.categories))
        self._combo.blockSignals(False)
        self._reload_tree()

    def _reload_tree(self) -> None:
        """FlashTVEleIvt：两层树（单位节点 → 元素节点）。"""
        self._tree.clear()
        for unit in element_library().units_of(self._combo.currentText()):
            unit_item = QTreeWidgetItem([unit.name])
            for template in unit.elements:
                element_item = QTreeWidgetItem([template.label])
                element_item.setToolTip(0, template.label)
                element_item.setData(0, _ROLE_TEMPLATE, template)
                unit_item.addChild(element_item)
            self._tree.addTopLevelItem(unit_item)

    def _on_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        template = item.data(0, _ROLE_TEMPLATE)
        if template is not None:
            self.insert_requested.emit(template)
