"""项目树视图模型（计划 §7.1）。

数据来源：project_io 读库 → 组装 TreeNode 树 → 交给树面板渲染。
增删改后统一 commit 落盘并广播 tree_structure_changed。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from app.core.event_bus import bus
from app.core.models.models import Segment, Unit
from app.services import project_io

KIND_PROJECT = "project"
KIND_SEGMENT = "segment"
KIND_UNIT = "unit"
KIND_ENCLOSURE_GROUP = "enclosure_group"
KIND_ENCLOSURE = "enclosure"
KIND_FOUNDATION_GROUP = "foundation_group"
KIND_FOUNDATION = "foundation"


@dataclass
class TreeNode:
    """树节点。id 为 None 表示工程根 / 分组（虚拟节点）。"""

    kind: str
    name: str
    id: int | None = None
    order_no: int = 0
    parent_id: int | None = None
    children: list["TreeNode"] = field(default_factory=list)

    @property
    def is_project(self) -> bool:
        return self.kind == KIND_PROJECT

    @property
    def is_segment(self) -> bool:
        return self.kind == KIND_SEGMENT

    @property
    def is_unit(self) -> bool:
        return self.kind == KIND_UNIT

    @property
    def is_enclosure(self) -> bool:
        return self.kind == KIND_ENCLOSURE

    @property
    def is_foundation(self) -> bool:
        return self.kind == KIND_FOUNDATION

    @property
    def is_group(self) -> bool:
        return self.kind in (KIND_ENCLOSURE_GROUP, KIND_FOUNDATION_GROUP)


def build_tree() -> TreeNode | None:
    """读库组装整棵树；未打开工程时返回 None。"""
    if not project_io.is_open():
        return None
    root = TreeNode(
        kind=KIND_PROJECT,
        name=project_io.project_name() or "未命名工程",
        id=None,
    )
    for segment in project_io.segments():
        segment_node = TreeNode(
            kind=KIND_SEGMENT,
            name=segment.name,
            id=segment.id,
            order_no=segment.order_no,
        )
        for unit in project_io.units(segment.id):
            segment_node.children.append(
                TreeNode(
                    kind=KIND_UNIT,
                    name=unit.name,
                    id=unit.id,
                    order_no=unit.order_no,
                    parent_id=segment.id,
                )
            )
        root.children.append(segment_node)

    # 复刻原版：树只有 项目 → 标段 → 单位工程 三层，原则全部在原则横条上管理
    return root


class ProjectViewModel(QObject):
    tree_loaded = Signal(object)  # TreeNode（根）或 None
    selection_changed = Signal(object)  # TreeNode | None
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._current: TreeNode | None = None

    # --- 加载与选中 ---
    def load(self) -> None:
        self.tree_loaded.emit(build_tree())

    def current(self) -> TreeNode | None:
        return self._current

    def select(self, node: TreeNode | None) -> None:
        self._current = node
        self.selection_changed.emit(node)

    def reselect(self, kind: str, node_id: int | None) -> None:
        """按 kind+id 在树里找回节点（重建树后保持选中）。"""
        root = build_tree()
        found = _find(root, kind, node_id)
        self._current = found
        self.selection_changed.emit(found)

    # --- 结构增删改 ---
    def add_segment(self, name: str = "新建标段") -> TreeNode | None:
        if not project_io.is_open():
            return None
        session = project_io.orm.session()
        segment = Segment(name=name, order_no=project_io.next_order_no(Segment))
        session.add(segment)
        project_io.commit()
        self._after_change()
        return TreeNode(kind=KIND_SEGMENT, name=segment.name, id=segment.id, order_no=segment.order_no)

    def add_unit(self, segment_id: int, name: str = "新建单位工程") -> TreeNode | None:
        if not project_io.is_open():
            return None
        session = project_io.orm.session()
        unit = Unit(
            segment_id=segment_id,
            name=name,
            order_no=project_io.next_order_no(Unit, segment_id=segment_id),
        )
        session.add(unit)
        project_io.commit()
        self._after_change()
        return TreeNode(kind=KIND_UNIT, name=unit.name, id=unit.id, parent_id=segment_id)

    def rename(self, node: TreeNode, name: str) -> None:
        name = name.strip()
        if not name:
            self.error_occurred.emit("名称不可为空。")
            return
        if node.is_enclosure:
            project_io.rename_enclosure(node.id, name)
        elif node.is_foundation:
            project_io.rename_foundation(node.id, name)
        else:
            target = self._entity(node)
            if target is None:
                return
            if target.name == name:
                return
            target.name = name
            project_io.commit()
        self._after_change()

    def delete(self, node: TreeNode) -> None:
        """删除标段/单位工程/原则（级联删除下属数据）。"""
        if node.is_enclosure:
            error = project_io.delete_enclosure(node.id)
        elif node.is_foundation:
            error = project_io.delete_foundation(node.id)
        else:
            target = self._entity(node)
            if target is None:
                return
            orm.session().delete(target)
            error = None
            project_io.commit()
        if error:
            self.error_occurred.emit(error)
            return
        self._current = None
        self.selection_changed.emit(None)
        self._after_change()

    def move_node(self, node: TreeNode, parent_id: int | None, index: int) -> bool:
        """拖拽移动：node 放到 parent_id（None = 项目根）下第 index 个兄弟位置。

        标段只能在项目根下并排重排；单位工程可在标段内排序或跨标段移动。
        移动成功返回 True。
        """
        target = self._entity(node)
        if target is None:
            return False
        if isinstance(target, Unit):
            if parent_id is None:
                return False
            project_io.move_unit(target.id, parent_id, index)
        else:
            if parent_id is not None:
                return False
            project_io.move_segment(target.id, index)
        self._after_change()
        return True

    def move(self, node: TreeNode, delta: int) -> None:
        """上移/下移（delta = -1 / +1）。"""
        target = self._entity(node)
        if target is None:
            return
        siblings = (
            project_io.units(target.segment_id)
            if isinstance(target, Unit)
            else project_io.segments()
        )
        ordered = list(siblings)
        try:
            index = ordered.index(target)
        except ValueError:
            return
        new_index = index + delta
        if new_index < 0 or new_index >= len(ordered):
            return
        ordered[index], ordered[new_index] = ordered[new_index], ordered[index]
        # 历史数据可能有重复 order_no，整列重编号保证顺序确定
        for position, item in enumerate(ordered):
            item.order_no = position
        project_io.commit()
        self._after_change()

    # --- 内部 ---
    def _after_change(self) -> None:
        self.load()
        bus().tree_structure_changed.emit()

    def _entity(self, node: TreeNode | None):
        if node is None or node.id is None or not project_io.is_open():
            return None
        if node.kind == KIND_SEGMENT:
            return project_io.orm.session().get(Segment, node.id)
        if node.kind == KIND_UNIT:
            return project_io.orm.session().get(Unit, node.id)
        return None


def _find(node: TreeNode | None, kind: str, node_id: int | None) -> TreeNode | None:
    if node is None:
        return None
    if node.kind == kind and node.id == node_id:
        return node
    for child in node.children:
        found = _find(child, kind, node_id)
        if found is not None:
            return found
    return None
