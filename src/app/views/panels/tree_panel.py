"""左侧面板（复刻旧版 FormMdi 左栏 splitContainerLeft，交互对齐 Quotor 项目结构树）。

上半段：项目结构（工程 → 标段 → 单位工程；复刻原版树右键菜单 + Quotor 拖拽移动）。
下半段：构件库（类别下拉 + 两级模板树，双击元素插入主表格）。

树交互与 Quotor 同款：
* 节点图标 Lucide 单色线条（工程=folder、标段=folder-open、单位工程=file-text），
  18px，text_secondary 着色；
* 拖拽仅 MoveAction：标段可与标段并排重排，单位工程可在标段内排序或跨标段移动；
  根节点不可拖；dropEvent 只记录意图，模态拖拽循环结束后才写库；
* 悬停折叠容器 250ms 自动展开。

选中节点通过 EventBus.node_selected 广播，中部工作区据此切换内容。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.event_bus import bus
from app.resources.qss.theme import ThemeManager
from app.viewmodels.project_vm import (
    KIND_PROJECT,
    KIND_SEGMENT,
    KIND_UNIT,
    ProjectViewModel,
    TreeNode,
)
from app.views.panels.element_library_panel import ElementLibraryPanel
from app.views.widgets.frameless_dialog import FramelessInputDialog, load_icon

_NODE_ROLE = Qt.ItemDataRole.UserRole + 1

#: 节点类型图标（Quotor tree_panel._NODE_ICONS 同款）
_NODE_ICONS = {
    KIND_PROJECT: "folder",  # 根目录: 合上的文件夹
    KIND_SEGMENT: "folder-open",  # 标段: 打开的文件夹
    KIND_UNIT: "file-text",  # 单位工程: 文档
}


def _node_icon(node: TreeNode):
    color = ThemeManager.instance().current().text_secondary
    return load_icon(_NODE_ICONS.get(node.kind, "folder"), color=color, size=18)


class _ProjectTree(QTreeWidget):
    """项目结构树：拖拽移动节点（Quotor _ProjectTree 同款交互）。"""

    #: (source_node, target_parent_id, index)；index 为排除自身后的兄弟位置
    move_node_requested = Signal(object, int, int)
    drop_rejected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)  # 根级不显示展开箭头
        self.setAnimated(True)
        self.setIndentation(16)
        self.setAutoExpandDelay(250)  # 悬停折叠容器片刻后自动展开
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._dragging_item: QTreeWidgetItem | None = None
        self._pending_move: tuple[object, int, int] | None = None

    # --- 拖拽（Quotor 同款：自建 QDrag + 半透明影像；drop 只记录、循环结束后写库） ---
    def startDrag(self, supported_actions) -> None:  # noqa: N802 - Qt 命名
        items = self.selectedItems()
        if not items:
            return
        item = items[0]
        if item.parent() is None:  # 根节点（工程）不可拖
            return
        self._dragging_item = item
        drag = QDrag(self)
        drag.setMimeData(self.model().mimeData([self.indexFromItem(item)]))
        rect = self.visualItemRect(item)
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
        # 只允许移动动作, Ctrl 等修饰键不会切换成复制
        drag.exec(Qt.DropAction.MoveAction, Qt.DropAction.MoveAction)
        self._dragging_item = None
        self._consume_pending_move()

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.source() is not self:  # 只接受树内部拖拽
            event.ignore()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.source() is not self:
            event.ignore()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.source() is not self:
            event.ignore()
            return
        source_item = self._dragging_item
        if source_item is None:
            event.ignore()
            return
        target_item = self.itemAt(event.position().toPoint())
        status, payload = self._resolve_drop(
            self._node_of(source_item), target_item, self.dropIndicatorPosition()
        )
        if status == "ok":
            self._dragging_item = None
            self._pending_move = payload
            event.acceptProposedAction()
            return
        event.ignore()
        if status == "invalid":
            self.drop_rejected.emit(payload)

    def _consume_pending_move(self) -> None:
        pending, self._pending_move = self._pending_move, None
        if pending is not None:
            self.move_node_requested.emit(*pending)

    @staticmethod
    def _node_of(item: QTreeWidgetItem) -> TreeNode:
        return item.data(0, _NODE_ROLE)

    # --- 落点解析：section2 层级为 工程→标段→单位工程 ---
    def _resolve_drop(
        self, source: TreeNode, target_item: QTreeWidgetItem | None, indicator
    ) -> tuple[str, tuple[object, int, int] | str]:
        from app.services import project_io

        target = self._node_of(target_item) if target_item is not None else None
        on_item = indicator == QAbstractItemView.DropIndicatorPosition.OnItem
        above = indicator == QAbstractItemView.DropIndicatorPosition.AboveItem
        below = indicator == QAbstractItemView.DropIndicatorPosition.BelowItem

        if source.kind == KIND_SEGMENT:
            if target is None or target.kind != KIND_SEGMENT or on_item or not (above or below):
                return "invalid", "标段只能拖到其它标段的上方或下方并排。"
            siblings = [item for item in project_io.segments() if item.id != source.id]
            index = next((i for i, item in enumerate(siblings) if item.id == target.id), 0)
            if below:
                index += 1
            return "ok", (source, None, index)

        if source.kind == KIND_UNIT:
            if target is None:
                return "invalid", "单位工程必须放到某个标段内。"
            if target.kind == KIND_SEGMENT:
                if on_item:
                    index = len([u for u in project_io.units(target.id) if u.id != source.id])
                    return "ok", (source, target.id, index)
                return "invalid", "单位工程请拖到标段上（放入）或其它单位工程旁。"
            # target 是单位工程
            siblings = [u for u in project_io.units(target.parent_id or 0) if u.id != source.id]
            index = next((i for i, item in enumerate(siblings) if item.id == target.id), 0)
            if below or on_item:
                index += 1
            return "ok", (source, target.parent_id, index)

        return "invalid", "该节点不能移动。"


class TreePanel(QWidget):
    """左侧面板：上半项目结构 + 下半构件库。"""

    #: 双击构件库元素模板（ElementTemplate）
    insert_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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

        # ---- 上半段：项目结构
        tree_page = QWidget()
        tree_layout = QVBoxLayout(tree_page)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(2)
        title = QLabel("项目结构")
        title.setProperty("role", "title")
        header.addWidget(title)
        header.addStretch(1)
        self._btn_move_up = self._make_icon_button("chevron-up", "上移", lambda: self._move(-1))
        self._btn_move_down = self._make_icon_button("chevron-down", "下移", lambda: self._move(1))
        for button in (self._btn_move_up, self._btn_move_down):
            header.addWidget(button)
        tree_layout.addLayout(header)

        self._stack = QStackedWidget()
        hint = QLabel("尚未打开工程。\n文件 → 新建工程 / 打开工程")
        hint.setProperty("role", "placeholder")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        self._stack.addWidget(hint)

        self._tree = _ProjectTree()
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._stack.addWidget(self._tree)
        tree_layout.addWidget(self._stack, 1)
        splitter.addWidget(tree_page)

        # ---- 下半段：构件库
        self._library = ElementLibraryPanel()
        self._library.insert_requested.connect(self.insert_requested.emit)
        splitter.addWidget(self._library)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        # 项目结构 / 构件库默认高度（取自运行实例实测）
        splitter.setSizes([336, 566])
        layout.addWidget(splitter, 1)

    def _make_icon_button(self, icon_name: str, tooltip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setProperty("role", "icon-btn")
        button.setAutoRaise(True)
        button.setIcon(
            load_icon(icon_name, color=ThemeManager.instance().current().text_secondary, size=16)
        )
        button.clicked.connect(slot)
        return button

    def _connect(self) -> None:
        self._vm.tree_loaded.connect(self._on_tree_loaded)
        self._vm.error_occurred.connect(lambda message: bus().status_message.emit(message, 4000))
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.move_node_requested.connect(self._on_move_node_requested)
        self._tree.drop_rejected.connect(lambda message: bus().status_message.emit(message, 5000))
        bus().project_opened.connect(lambda _path: self._vm.load())
        bus().project_closed.connect(self._on_project_closed)
        ThemeManager.instance().theme_changed.connect(self._refresh_icons)

    # ------------------------------------------------------------------ 拖拽移动
    def _on_move_node_requested(self, node: TreeNode, parent_id: int | None, index: int) -> None:
        self._selected_key = (node.kind, node.id)
        self._vm.move_node(node, parent_id, index)

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
            menu.addAction("添加标段", self._add_segment)
        elif node.is_segment:
            menu.addAction("添加标段", self._add_segment)
            menu.addAction("添加单位工程", self._add_unit)
            menu.addSeparator()
            menu.addAction("删除标段", self._delete)
        elif node.is_unit:
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
                segment_id = self._tree._node_of(root.child(0)).id
        if segment_id is None:
            bus().status_message.emit("请于项目树中选中标段以添加单位工程。", 4000)
            return
        self._vm.add_unit(segment_id)

    def _rename(self) -> None:
        node = self._current_node()
        if node is None or node.is_project:
            return
        text, ok = FramelessInputDialog.getText(self, "重命名", "名称：", text=node.name)
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
        from app.views.widgets.frameless_dialog import FramelessMessageBox

        answer = FramelessMessageBox.question(
            self,
            "删除确认",
            question,
            FramelessMessageBox.StandardButton.Yes | FramelessMessageBox.StandardButton.No,
            FramelessMessageBox.StandardButton.No,
        )
        if answer != FramelessMessageBox.StandardButton.Yes:
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
        """外部入口：移动项目树当前选中节点。"""
        self._move(delta)

    # ------------------------------------------------------------------ 辅助
    def _refresh_icons(self) -> None:
        """主题切换后按新主题色重绘节点与按钮图标。"""
        stack = [self._tree.topLevelItem(index) for index in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            item.setIcon(0, _node_icon(self._tree._node_of(item)))
            stack.extend(item.child(index) for index in range(item.childCount()))
        for name, button in (
            ("chevron-up", self._btn_move_up),
            ("chevron-down", self._btn_move_down),
        ):
            button.setIcon(
                load_icon(name, color=ThemeManager.instance().current().text_secondary, size=16)
            )

    def _current_node(self) -> TreeNode | None:
        item = self._tree.currentItem()
        return self._tree._node_of(item) if item is not None else None

    def _make_item(self, node: TreeNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name])
        item.setData(0, _NODE_ROLE, node)
        item.setIcon(0, _node_icon(node))
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
            node = self._tree._node_of(item)
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
        for button in (self._btn_move_up, self._btn_move_down):
            button.setEnabled(editable)


def _tooltip(node: TreeNode) -> str:
    if node.is_project:
        return f"工程：{node.name}"
    if node.is_segment:
        return f"标段：{node.name}"
    return f"单位工程：{node.name}"
