"""AI 写操作确认策略：按调用通道分别控制是否弹人工确认窗。

两条通道（与 Quotor 对齐）：
- ``builtin`` —— 内置 AI 面板，受 ``[ai] require_confirmation`` 控制；
- ``mcp``     —— 外部 MCP 客户端，受 ``[mcp] require_confirmation`` 控制。

跨线程：工具在 worker 线程执行；确认卡通过 Qt 队列信号投递到界面线程。
**判定在 worker 线程完成**（``confirmation_suppressed`` 在 emit 之前读），
因此不需要 Quotor 那样的 contextvar 快照/恢复——contextvar 不跨信号，
这里把“是否抑制”的决策提前到同一线程内完成。

无界面进程（headless CLI）没有安装确认处理器：写操作直接返回“拒绝”，
由适配层的 ``_gui_available`` 守卫先给出更明确的错误。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable

from PySide6.QtCore import QObject, Signal

from app.core.config import get_config

CHANNEL_BUILTIN = "builtin"
CHANNEL_MCP = "mcp"

_CHANNEL: ContextVar[str] = ContextVar("confirm_channel", default=CHANNEL_BUILTIN)


def current_channel() -> str:
    return _CHANNEL.get()


@contextmanager
def channel(name: str):
    """在作用域内把调用通道标记为 name（支持嵌套）。"""
    token = _CHANNEL.set(name)
    try:
        yield
    finally:
        _CHANNEL.reset(token)


def confirmation_suppressed() -> bool:
    """当前通道是否跳过人工确认窗体。"""
    config = get_config()
    if current_channel() == CHANNEL_MCP:
        return not config.mcp_require_confirmation
    return not config.ai_require_confirmation


def make_preview(action: str, target: str = "", summary: str = "", details=None) -> dict:
    """结构化确认卡内容（action / target / summary / details）。"""
    return {
        "action": action,
        "target": target,
        "summary": summary,
        "details": list(details or []),
    }


class _ConfirmRelay(QObject):
    """跨线程确认中继：worker 线程 emit，界面线程弹窗后回填。"""

    request = Signal(object)  # dict：preview


_relay: _ConfirmRelay | None = None
_handler: Callable[[dict], bool] | None = None
_pending_event: threading.Event | None = None
_pending_answer = False
_pending_lock = threading.Lock()


def install_confirm_handler(handler: Callable[[dict], bool]) -> None:
    """界面启动时安装确认处理器（必须在主线程调用）。"""
    global _relay, _handler
    _handler = handler
    if _relay is None:
        _relay = _ConfirmRelay()
        # 默认 AutoConnection：worker 线程 emit → 队列投递到界面线程；
        # 界面线程 emit → 直接调用（不会死等自己）。
        _relay.request.connect(_dispatch)


def uninstall_confirm_handler() -> None:
    """窗口关闭时卸载处理器（避免持有已销毁窗口的绑定方法）。"""
    global _handler
    _handler = None


def has_confirm_handler() -> bool:
    """是否已安装确认处理器（MCP 适配层用于判断写操作是否可行）。"""
    return _handler is not None


def _dispatch(preview: dict) -> None:
    """界面线程：弹确认卡并回填结果。"""
    global _pending_answer
    approved = False
    if _handler is not None:
        try:
            approved = bool(_handler(preview))
        except Exception:
            approved = False
    with _pending_lock:
        _pending_answer = approved
        if _pending_event is not None:
            _pending_event.set()


def ask_confirm(preview: dict, timeout: float = 300.0) -> bool:
    """worker/工具线程调用：请求人工确认，阻塞等待（默认拒绝超时）。"""
    global _pending_event, _pending_answer
    if confirmation_suppressed():
        return True
    if _relay is None or _handler is None:
        # 无界面：不能弹确认卡，按拒绝处理（适配层通常会先行拦截）
        return False
    with _pending_lock:
        event = threading.Event()
        _pending_event = event
        _pending_answer = False
    _relay.request.emit(preview)
    event.wait(timeout=max(1.0, timeout))
    with _pending_lock:
        result = _pending_answer
        _pending_event = None
    return result


# --------------------------------------------------------------------------- #
# 兼容旧接口（agent_loop 早期版本用 ConfirmBridge + answer_confirm）
# --------------------------------------------------------------------------- #
class ConfirmBridge(QObject):
    """保留的兼容桥：把 ask() 转给全局确认通道。

    新的 AgentLoop 直接调 :func:`ask_confirm`；保留此类避免外部脚本/测试
    import 失败。
    """

    request = Signal(str)

    def ask(self, description: str | dict) -> bool:
        preview = (
            description
            if isinstance(description, dict)
            else make_preview("执行操作", summary=str(description))
        )
        return ask_confirm(preview)

    def answer(self, approved: bool) -> None:  # 旧接口：单值覆盖（仅测试用）
        global _pending_answer
        with _pending_lock:
            _pending_answer = bool(approved)
            if _pending_event is not None:
                _pending_event.set()
