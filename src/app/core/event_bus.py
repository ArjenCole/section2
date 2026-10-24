"""全局事件总线：跨面板解耦。

面板之间不互相持有引用，只通过 EventBus 的 Signal 广播。
载荷若为自定义对象统一用 Signal(object)，避免 Shiboken 转换失败导致槽函数不触发。

**连接一律用 :func:`connect_weak`（或接收者签名刚好对得上的绑定方法）**：

* ``signal.connect(self._on_xxx)`` —— 绑定方法：PySide6 只对**接收者**持弱引用，
  接收者销毁后连接自动摘除，安全；
* ``signal.connect(lambda: self.xxx())`` —— **不要这么写**：lambda 是一个闭包对象，
  PySide 只能整体强引用它，闭包里抓着的 self 因此永远释放不掉。窗体会一直活着
  （``close()`` 只是隐藏），并且会继续接收后续信号——见 2026-10-22 的崩溃排查：
  一个"已关闭"的面宽原则窗体收到延迟补发的 ``currentChanged`` 后重入 ``commit()``，
  把 SQLAlchemy 的提交状态机打断，随后在毫不相关的代码里随机原生崩溃。
* 需要夹带常量参数（或忽略信号自带的参数）时用 :func:`connect_weak`，
  它持有接收者的弱引用，效果等价于绑定方法。
"""

from __future__ import annotations

import weakref

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
    #: 新增构件获得焦点（单位工程 id, 构件 id）：面板选中新行，撤销/重做恢复的
    #: 选中也随之落在每一步新增的条目上
    element_focused = Signal(int, int)
    principle_changed = Signal()  # 围护/地基原则内容变更：工程量与断面图需重算
    #: AI 上下文变化（当前选中单位工程/构件）；载荷 dict，见 app.agent.context
    ai_context_changed = Signal(object)

    # --- 界面 ---
    status_message = Signal(str, int)  # 文本, 毫秒（0 = 常驻）

    @classmethod
    def instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def bus() -> EventBus:
    return EventBus.instance()


def connect_weak(signal, receiver, method_name: str, *args, **kwargs):
    """把信号接到 ``receiver.method_name`` 上，且**只持有 receiver 的弱引用**。

    用来替代 ``signal.connect(lambda ...: receiver.method(...))``：后者会被
    PySide 整体强引用，receiver 永远释放不掉（见模块文档）。语义与
    ``signal.connect(receiver.method)`` 相同——receiver 被回收或底层 C++ 对象
    已销毁后，回调静默跳过——区别是可以夹带常量参数。

    :param signal: 任意 PySide 信号（例如 ``bus().project_opened``）
    :param receiver: 接收者对象（QWidget / ViewModel / 普通 Python 对象均可）
    :param method_name: 接收者上的方法名
    :param args: 调用该方法时额外传入的位置参数（信号自带的参数忽略）
    :param kwargs: 调用该方法时额外传入的关键字参数
    :return: 实际连上去的槽（需要手动 disconnect 时可用）
    """
    reference = weakref.ref(receiver)

    def _slot(*_signal_args) -> None:
        target = reference()
        if target is None or not _is_alive(target):
            return
        method = getattr(target, method_name, None)
        if method is None:  # 对接方改名/删方法时不炸，只跳过
            return
        method(*args, **kwargs)

    signal.connect(_slot)
    return _slot


def _is_alive(obj) -> bool:
    """底层 C++ 对象是否仍然有效（普通 Python 对象直接返回 True）。"""
    try:
        import shiboken6

        return shiboken6.isValid(obj)
    except Exception:  # noqa: BLE001 - 非 PySide 对象、或 shiboken 不可用
        return True
