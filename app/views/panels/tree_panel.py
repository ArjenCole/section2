"""左侧面板（复刻旧版 FormMdi 左栏 splitContainerLeft）。

上半段：项目数据结构（工程 → 标段 → 单位工程；复刻原版树右键菜单）。
下半段：构件库（类别下拉 + 两级模板树，双击元素插入主表格）。

选中节点通过 EventBus.node_selected 广播，中部工作区据此切换内容。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.event_bus import bus
from app.viewmodels.project_vm import (
    KIND_PROJECT,
    KIND_SEGMENT,
    KIND_UNIT,
    ProjectViewModel,
    TreeNode,
)
from app.views.panels.element_library_panel import ElementLibraryPanel

_NODE_ROLE = Qt.ItemDataRole.UserRole + 1


class TreePanel(QWidget):
    """左侧面板：上半项目树 + 下半构件库。"""

    #: 双击构件库元素模板（ElementTemplate）
    insert_requested = Signal(object)
    #: 右键菜单“项目/标段/单位工程汇总”
    summary_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self.setMinimumWidth(200)
        self._vm = ProjectViewModel()
        self._selected_key: tuple[str, int | None] | None = None
        self._build_ui()
        self._connect()
        self._update_actions()

    @property
    def vm(self) -> ProjectViewModel:
        return self._vm

    @property
    def current_node(self) -> TreeNode | None:
        return self._current_node()

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ---- 上半段：项目数据结构
        tree_page = QWidget()
        tree_layout = QVBoxLayout(tree_page)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(4)
        header = QHBoxLayout()
        title = QLabel("项目数据结构")
        title.setProperty("role", "panel-title")
        header.addWidget(title)
        header.addStretch(1)
        self._btn_move_up = self._make_button("↑", "上移", lambda: self._move(-1))
        self._btn_move_down = self._make_button("↓", "下移", lambda: self._move(1))
        self._btn_delete = self._make_button("✕", "删除选中节点", self._delete)
        for button in (self._btn_move_up, self._btn_move_down, self._btn_delete):
            header.addWidget(button)
        tree_layout.addLayout(header)

        self._stack = QStackedWidget()
        hint = QLabel("尚未打开工程。\n文件 → 新建工程 / 打开工程")
        hint.setProperty("role", "placeholder")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        self._stack.addWidget(hint)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._stack.addWidget(self._tree)
        tree_layout.addWidget(self._stack, 1)
        splitter.addWidget(tree_page)

        # ---- 下半段：构件库
        self._library = ElementLibraryPanel()
        self._library.insert_requested.connect(self.insert_requested.emit)
        splitter.addWidget(self._library)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

    def _make_button(self, text: str, tooltip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setProperty("role", "icon-btn")
        button.clicked.connect(slot)
        return button

    def _connect(self) -> None:
        self._vm.tree_loaded.connect(self._on_tree_loaded)
        self._vm.error_occurred.connect(lambda message: bus().status_message.emit(message, 4000))
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        bus().project_opened.connect(lambda _path: self._vm.load())
        bus().project_closed.connect(self._on_project_closed)

    # ------------------------------------------------------------------ 槽
    def _on_project_closed(self) -> None:
        self._selected_key = None
        self._vm.load()
        self._vm.select(None)

    def _on_tree_loaded(self, root: TreeNode | None) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        if root is None:
            self._stack.setCurrentIndex(0)
            self._tree.blockSignals(False)
            self._update_actions()
            return
        root_item = self._make_item(root)
        self._tree.addTopLevelItem(root_item)
        self._tree.expandAll()
        self._stack.setCurrentIndex(1)
        item = self._find_item(self._selected_key) or root_item
        self._tree.setCurrentItem(item)
        self._tree.blockSignals(False)
        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        node = self._current_node()
        self._selected_key = (node.kind, node.id) if node is not None else None
        self._vm.select(node)
        bus().node_selected.emit(node)
        self._update_actions()

    # ------------------------------------------------------------------ 右键菜单（复刻原版 CMStvDC / CMStvSegment / CMStvUnit）
    def _on_context_menu(self, position) -> None:
        node = self._current_node()
        menu = QMenu(self)
        if node is None or node.is_project:
            menu.addAction("项目汇总", self.summary_requested.emit)
            menu.addSeparator()
            menu.addAction("添加标段", self._add_segment)
        elif node.is_segment:
            menu.addAction("标段汇总", self.summary_requested.emit)
            menu.addSeparator()
            menu.addAction("添加标段", self._add_segment)
            menu.addAction("添加单位工程", self._add_unit)
            menu.addSeparator()
            menu.addAction("删除标段", self._delete)
        elif node.is_unit:
            menu.addAction("单位工程汇总", self.summary_requested.emit)
            menu.addSeparator()
            menu.addAction("添加标段", self._add_segment)
            menu.addAction("添加单位工程", self._add_unit)
            menu.addSeparator()
            menu.addAction("删除单位工程", self._delete)
        else:
            return
        menu.addSeparator()
        # 新版保留：重命名（原版为 F2 行内编辑）、展开/折叠
        if node is not None and not node.is_project:
            menu.addAction("重命名", self._rename)
        menu.addAction("展开全部", self._tree.expandAll)
        menu.addAction("折叠全部", self._tree.collapseAll)
        menu.exec(self._tree.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------ 操作
    def add_segment(self) -> None:
        self._add_segment()

    def add_unit(self) -> None:
        self._add_unit()

    def _add_segment(self) -> None:
        if not self._vm.current() and self._stack.currentIndex() == 0:
            return
        self._vm.add_segment()

    def _add_unit(self) -> None:
        node = self._current_node()
        segment_id: int | None = None
        if node is not None and node.is_unit:
            segment_id = node.parent_id
        elif node is not None and node.is_segment:
            segment_id = node.id
        else:
            root = self._tree.topLevelItem(0)
            if root is not None and root.childCount() > 0:
                segment_id = self._node_of(root.child(0)).id
        if segment_id is None:
            bus().status_message.emit("请于项目树中选中标段以添加单位工程。", 4000)
            return
        self._vm.add_unit(segment_id)

    def _rename(self) -> None:
        node = self._current_node()
        if node is None or node.is_project:
            return
        text, ok = QInputDialog.getText(self, "重命名", "名称：", text=node.name)
        if not ok:
            return
        self._vm.rename(node, text)

    def _delete(self) -> None:
        node = self._current_node()
        if node is None or node.is_project:
            return
        if node.is_segment:
            question = f"确定删除标段“{node.name}”及其下全部单位工程、构件条目？"
        else:
            question = f"确定删除单位工程“{node.name}”及其下全部构件条目？"
        answer = QMessageBox.question(
            self,
            "删除确认",
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        parent = self._parent_key(node)
        self._vm.delete(node)
        if parent is not None:
            self._selected_key = parent

    def _move(self, delta: int) -> None:
        node = self._current_node()
        if node is None or node.is_project:
            return
        self._selected_key = (node.kind, node.id)
        self._vm.move(node, delta)

    def move_selected(self, delta: int) -> None:
        """原则横条 ↑/↓ 入口：移动项目树当前选中节点（原版 btnMoveUp/Down）。"""
        self._move(delta)

    # ------------------------------------------------------------------ 辅助
    def _current_node(self) -> TreeNode | None:
        item = self._tree.currentItem()
        return self._node_of(item) if item is not None else None

    @staticmethod
    def _node_of(item: QTreeWidgetItem) -> TreeNode:
        return item.data(0, _NODE_ROLE)

    def _make_item(self, node: TreeNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name])
        item.setData(0, _NODE_ROLE, node)
        item.setToolTip(0, _tooltip(node))
        if node.is_project:
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
        for child in node.children:
            item.addChild(self._make_item(child))
        return item

    def _find_item(self, key: tuple[str, int | None] | None) -> QTreeWidgetItem | None:
        if key is None:
            return None
        kind, node_id = key
        stack = [self._tree.topLevelItem(index) for index in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            node = self._node_of(item)
            if node.kind == kind and node.id == node_id:
                return item
            stack.extend(item.child(index) for index in range(item.childCount()))
        return None

    def _parent_key(self, node: TreeNode) -> tuple[str, int | None] | None:
        if node.is_unit:
            return (KIND_SEGMENT, node.parent_id)
        return (KIND_PROJECT, None)

    def _update_actions(self) -> None:
        node = self._current_node()
        editable = node is not None and not node.is_project
        for button in (self._btn_move_up, self._btn_move_down, self._btn_delete):
            button.setEnabled(editable)


def _tooltip(node: TreeNode) -> str:
    if node.is_project:
        return f"工程：{node.name}"
    if node.is_segment:
        return f"标段：{node.name}"
    return f"单位工程：{node.name}"
