"""全局事件总线：跨面板解耦。

面板之间不互相持有引用，只通过 EventBus 的 Signal 广播。
载荷若为自定义对象统一用 Signal(object)，避免 Shiboken 转换失败导致槽函数不触发。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    _instance: "EventBus | None" = None

    # --- 工程生命周期 ---
    project_opened = Signal(str)  # 工程文件路径
    project_closed = Signal()
    project_saved = Signal(str)  # 工程文件路径

    # --- 数据结构 ---
    tree_structure_changed = Signal()  # 标段/单位工程增删改
    node_selected = Signal(object)  # viewmodels.project_vm.TreeNode | None
    unit_changed = Signal(int)  # 单位工程 id：构件/管道/参数变更
    principle_changed = Signal()  # 围护/地基原则内容变更：工程量与断面图需重算

    # --- 界面 ---
    status_message = Signal(str, int)  # 文本, 毫秒（0 = 常驻）

    @classmethod
    def instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def bus() -> EventBus:
    return EventBus.instance()
