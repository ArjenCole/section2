"""撤销 / 重做 —— 快照式实现（原则与 brackets2 相同）。

工程数据的每次修改都汇聚到 :func:`app.services.project_io.commit`（提交即落盘），
这里在每次提交后保存一份**整工程快照**：``stn_codec.dump_database`` 的 JSON
数据体 + 界面状态；撤销 / 重做就是用快照重建临时工作库（见
``project_io.restore_snapshot``），而不是逐条反演操作。

原则（与 brackets2 services/undo.py 一致）：

* 每个快照保存整份工程 JSON + 界面状态（树选中位置、主表格焦点等，由视图
  经 :func:`set_ui_provider` 注入的回调提供；未注入或捕获失败时为空）；
* 上限双控：最多 25 步撤销，且快照总字节数不超过 10 MB，任一先到即淘汰最旧，
  当前快照始终保留；
* 内容未变的重复提交只更新快照的界面状态，不占用撤销步数（界面浏览不占步数）；
* 写入前先用当前界面状态刷新"变更前"快照：撤销回到上一步时恢复的是用户
  操作时刻的选中 / 焦点，界面状态不单独占步数；
* section2 特有：commit 时刻界面还没按新数据刷新（EventBus 广播 → QTimer
  延后重装表格），栈顶快照的界面状态由视图刷新完成后经 :meth:`UndoStack.patch_top_ui`
  回填——否则重做到栈顶时快照里的选中行指向已删除/已移位的行，恢复即错乱；
* 新变更清除重做分支；
* 时间窗合并（200ms）：一次用户操作内部可能连续提交多次（如候选参数改一格
  会连着落盘两次），窗口内的提交合并为一步，Ctrl+Z 一次回到操作前。

与 brackets2 的偏差：brackets2 记录"已保存点"并据此判 is_dirty；本工程
提交即落盘、不存在"未保存修改"状态，恢复后由 project_io 重写文件即可，
因此没有保存点机制。快照序列化时会剔除 ``saved_at``——它是每次提交都变的
meta，留着会让"内容未变"的判定永远不成立。

本模块刻意不依赖 Qt 与工程数据库：快照内容全部由调用方传入 / 返回，
方便直接跑测试。
"""

from __future__ import annotations

import json
import time
import weakref
from dataclasses import dataclass

__all__ = [
    "UndoStack",
    "can_redo",
    "can_undo",
    "clear",
    "last_focus",
    "patch_top_ui",
    "record",
    "redo",
    "reset",
    "set_listener",
    "set_ui_provider",
    "undo",
]

_MAX_UNDO_STEPS = 25  # 最多可撤销步数
_MAX_BYTES = 10 * 1024 * 1024  # 全部快照总字节上限
_COALESCE_SECONDS = 0.2  # 时间窗：窗口内的连续提交合并为一步


@dataclass
class _Snapshot:
    text: str  # 工程 JSON 数据体（不含 saved_at）
    ui: dict | None = None  # 界面状态（由视图提供，可为空）
    size: int = 0  # UTF-8 字节数


def _serialize(data: dict) -> tuple[str, int]:
    payload = {key: value for key, value in data.items() if key != "saved_at"}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text, len(text.encode("utf-8", errors="replace"))


def _weak_callback(callback):
    """把回调转成弱引用调用；普通函数原样返回。

    主窗体注入的 provider / listener 是窗口的绑定方法，强引用会把整个窗体
    钉住永不释放（见 app.core.event_bus 模块文档的排查记录），与
    :func:`app.core.event_bus.connect_weak` 同款处理：只持接收者的弱引用，
    接收者销毁（含底层 C++ 对象已删除）后静默跳过。
    """
    if callback is None:
        return None
    try:
        receiver = weakref.WeakMethod(callback)
    except TypeError:
        return callback  # 普通函数 / lambda：生命周期由调用方管理

    def _call(*args, **kwargs):
        method = receiver()
        if method is None:
            return None
        try:
            import shiboken6

            if not shiboken6.isValid(method.__self__):
                return None
        except Exception:  # noqa: BLE001 - 非 PySide 对象直接放行
            pass
        return method(*args, **kwargs)

    return _call


def _diff_focus(previous: dict, target: dict) -> tuple[tuple[int, int], int | None] | None:
    """对比相邻两份快照的构件清单，定位该步修改的条目。

    返回 ``((标段序号, 单位工程序号), 行号或 None)``——行号是目标快照里被
    修改条目的位置（删除方向没有该行，收敛到原位置的相邻行；单位工程被
    清空时为 None）。构件清单无差异（原则 / 单价 / 工程结构变化）或多个
    单位工程同时变化（如原则保存触发的批量重匹配）时返回 None，选中交给
    快照携带的界面状态兜底。

    撤销 / 重做按这条规则恢复选中：每一步只落在该步实际修改的那一条上，
    不受操作间浏览（视图选中与步骤脱节）影响。
    """
    prev_segs = previous.get("segments") or []
    target_segs = target.get("segments") or []
    if len(prev_segs) != len(target_segs):
        return None  # 标段级变化：位置语义不稳
    focus: tuple[tuple[int, int], int | None] | None = None
    for seg_index, (prev_seg, target_seg) in enumerate(zip(prev_segs, target_segs)):
        if prev_seg.get("name") != target_seg.get("name"):
            return None
        prev_units = prev_seg.get("units") or []
        target_units = target_seg.get("units") or []
        if len(prev_units) != len(target_units):
            return None
        for unit_index, (prev_unit, target_unit) in enumerate(zip(prev_units, target_units)):
            if prev_unit.get("name") != target_unit.get("name"):
                return None
            prev_elements = prev_unit.get("elements") or []
            target_elements = target_unit.get("elements") or []
            if prev_elements == target_elements:
                continue
            if focus is not None:
                return None  # 多个单位工程同时变化：不猜测，交给界面状态
            prefix = 0
            while (
                prefix < len(prev_elements)
                and prefix < len(target_elements)
                and prev_elements[prefix] == target_elements[prefix]
            ):
                prefix += 1
            if len(prev_elements) == len(target_elements):
                if prefix >= len(prev_elements):
                    continue  # 内容相同（不应发生），跳过
                row: int | None = prefix  # 同长：改值 → 第一个差异行
            elif len(prev_elements) < len(target_elements):
                row = prefix if prefix < len(target_elements) else None  # 新增位置
            else:
                row = min(prefix, len(target_elements) - 1) if target_elements else None
            focus = ((seg_index, unit_index), row)
    return focus


class UndoStack:
    def __init__(self) -> None:
        self._snaps: list[_Snapshot] = []
        self._pos: int = -1  # 当前快照下标
        self._last_push: float | None = None  # 最近一次记录时刻，时间窗合并用
        self._last_focus: tuple[tuple[int, int], int | None] | None = None
        self._ui_provider = None  # 由视图注入：捕获界面状态的回调
        self._listener = None  # 由视图注入：栈变化后刷新撤销/重做按钮

    # ------------------------------------------------------------ 视图注入
    def set_ui_provider(self, provider) -> None:
        """注入界面状态捕获回调（撤销快照携带选中/焦点用），主窗体调用。"""
        self._ui_provider = _weak_callback(provider)

    def set_listener(self, listener) -> None:
        """注入栈变化监听（record/undo/redo/reset/clear 后回调），主窗体调用。"""
        self._listener = _weak_callback(listener)

    def _capture_ui(self) -> dict | None:
        if self._ui_provider is None:
            return None
        try:
            return self._ui_provider()
        except Exception:  # 界面状态不应阻断撤销流程
            return None

    def _notify(self) -> None:
        if self._listener is None:
            return
        try:
            self._listener()
        except Exception:  # pragma: no cover - 界面刷新不应阻断数据流程
            pass

    # ------------------------------------------------------------ 状态
    @property
    def can_undo(self) -> bool:
        return self._pos > 0

    @property
    def can_redo(self) -> bool:
        return 0 <= self._pos < len(self._snaps) - 1

    @property
    def last_focus(self) -> tuple[tuple[int, int], int | None] | None:
        """最近一次 undo()/redo() 对比相邻快照得出的焦点（(单位位置), 行号）。

        撤销 / 重做恢复选中用：每一步只落在该步实际修改的那一条上；None =
        步骤没有构件级差异（原则 / 单价 / 结构变化），选中由快照界面状态兜底。
        """
        return self._last_focus

    # ------------------------------------------------------------ 生命周期
    def clear(self) -> None:
        """清空栈（关闭工程）。"""
        self._snaps = []
        self._pos = -1
        self._last_focus = None
        self._notify()

    def reset(self, data: dict) -> None:
        """初始化栈（新建 / 打开工程后）：当前内容是不可撤销的基线快照。"""
        text, size = _serialize(data)
        self._snaps = [_Snapshot(text, None, size)]
        self._pos = 0
        self._last_push = None
        self._last_focus = None
        self._notify()

    def record(self, data: dict) -> None:
        """工程内容变更（commit）后调用；内容未变时只更新界面状态，不新增一步。

        写入前先用当前界面状态刷新"变更前"快照，保证撤销回到上一步时
        恢复的是用户操作时刻看到的选中/焦点（界面浏览不单独占步数）。
        此刻的界面还没按新数据刷新（unit_changed → QTimer 延后重装表格），
        栈顶快照的界面状态由 :meth:`patch_top_ui` 在刷新完成后回填。
        """
        text, size = _serialize(data)
        ui = self._capture_ui()
        if self._pos >= 0:
            self._snaps[self._pos].ui = ui
            if self._snaps[self._pos].text == text:
                return
        now = time.monotonic()
        del self._snaps[self._pos + 1 :]  # 新变更清除重做分支
        if self._pos >= 1 and (
            self._last_push is not None and now - self._last_push <= _COALESCE_SECONDS
        ):
            # 时间窗合并：替换（而不是追加）栈顶，一步撤销回到整次操作前
            merged = self._snaps[self._pos]
            merged.text, merged.size, merged.ui = text, size, ui
        else:
            self._snaps.append(_Snapshot(text, ui, size))
            self._pos = len(self._snaps) - 1
        self._last_push = now
        self._last_focus = None
        self._trim()
        self._notify()

    def patch_top_ui(self, ui: dict | None) -> None:
        """界面按最新数据装填完成后，回填栈顶快照的界面状态。

        record() 发生在界面刷新之前，捕获的选中/焦点是"变更前"的视图——
        撤销用它正好，重做到栈顶却会指向已删除/已移位的行，选中恢复就会
        错乱。视图刷新完成后（EventBus 广播 → QTimer 延后重装表格之后）
        回填一次，栈顶快照携带的即是用户实际看到的选中/焦点。
        """
        if 0 <= self._pos < len(self._snaps):
            self._snaps[self._pos].ui = ui

    def undo(self) -> tuple[dict, dict | None] | None:
        """回退一步，返回 (工程 JSON 数据体, 界面状态)；无可撤销返回 None。

        同时把相邻快照对比得出的焦点（该步修改的条目位置）存入
        :attr:`last_focus`，供视图恢复选中。
        """
        if not self.can_undo:
            return None
        self._pos -= 1
        self._last_push = None  # 撤销后的新变更不与撤销前的提交合并
        snap = self._snaps[self._pos]
        self._last_focus = _diff_focus(
            json.loads(self._snaps[self._pos + 1].text), json.loads(snap.text)
        )
        self._notify()
        return json.loads(snap.text), snap.ui

    def redo(self) -> tuple[dict, dict | None] | None:
        """前进一步，返回 (工程 JSON 数据体, 界面状态)；无可重做返回 None。

        焦点语义同 :meth:`undo`。
        """
        if not self.can_redo:
            return None
        self._pos += 1
        self._last_push = None
        snap = self._snaps[self._pos]
        self._last_focus = _diff_focus(
            json.loads(self._snaps[self._pos - 1].text), json.loads(snap.text)
        )
        self._notify()
        return json.loads(snap.text), snap.ui

    # ------------------------------------------------------------ 内部
    def _trim(self) -> None:
        """按步数与总字节双上限淘汰最旧快照；当前快照始终保留。"""
        while self._pos > 0 and (
            self._pos > _MAX_UNDO_STEPS
            or sum(snap.size for snap in self._snaps) > _MAX_BYTES
        ):
            self._snaps.pop(0)
            self._pos -= 1


# --------------------------------------------------------------------------- #
# 模块级单例（project_io 是所有修改的漏斗，撤销栈同样用模块级门面）
# --------------------------------------------------------------------------- #
_stack = UndoStack()


def set_ui_provider(provider) -> None:
    _stack.set_ui_provider(provider)


def set_listener(listener) -> None:
    _stack.set_listener(listener)


def can_undo() -> bool:
    return _stack.can_undo


def can_redo() -> bool:
    return _stack.can_redo


def reset(data: dict) -> None:
    _stack.reset(data)


def record(data: dict) -> None:
    _stack.record(data)


def patch_top_ui(ui: dict | None) -> None:
    _stack.patch_top_ui(ui)


def undo() -> tuple[dict, dict | None] | None:
    return _stack.undo()


def redo() -> tuple[dict, dict | None] | None:
    return _stack.redo()


def last_focus() -> tuple[tuple[int, int], int | None] | None:
    return _stack.last_focus


def clear() -> None:
    _stack.clear()
