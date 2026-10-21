"""界面主线程执行器与线程归属守卫。

数据层只有一个长驻 SQLAlchemy ``Session``（见 :mod:`app.core.models.base`），
而 ``Session`` 不是线程安全的：一个线程在 ``commit()``（内部会把事务状态
临时置为 ``PREPARED``）时，另一个线程再发 SQL 就会抛
``This session is in 'prepared' state``，甚至把事务状态弄坏。

因此本模块提供两件事：

* :func:`execute_on_main` —— 把工具执行器投递到 Qt 主线程同步执行，
  worker 线程只负责网络 I/O。没有 ``QApplication``（headless CLI / 测试）
  或已经在主线程时直接执行；
* :func:`ensure_main_thread` —— 工程数据库/生命周期操作的主线程守卫。
  ``app.main`` 启动时标记主线程，之后任何 worker 线程直接碰 Session
  都会得到明确的错误，而不是偶发的 ``prepared`` 竞态。

投递使用“信号 + Event”而不是 ``QMetaObject.invokeMethod``：可以把任意
Python 可调用对象和参数原样传过去，并用 :mod:`contextvars` 复制当前上下文
（MCP 通道标记等 ContextVar 不会跨 Qt 信号丢失）。
"""

from __future__ import annotations

import contextvars
import logging
import threading
from typing import Any, Callable

_logger = logging.getLogger(__name__)

#: worker 等待主线程执行的最长时间；超时按工具失败返回，避免线程永久挂住
_MAIN_THREAD_TIMEOUT = 600.0

_lock = threading.Lock()
_main_thread_id: int | None = None
_invoker: Any = None
_invoker_thread_id: int | None = None
_invoker_class: type | None = None


class _Call:
    """一次跨线程调用：可调用对象 + 参数 + 复制后的 ContextVar 上下文。"""

    __slots__ = ("function", "args", "kwargs", "context", "event", "result", "error")

    def __init__(
        self, function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.context = contextvars.copy_context()
        self.event = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


def mark_main_thread() -> None:
    """记录界面主线程（``app.main`` 在 QApplication 创建后调用）。"""
    global _main_thread_id
    _main_thread_id = threading.get_ident()


def is_main_thread() -> bool:
    """当前线程是否可执行工程数据库操作。

    尚未标记主线程（headless CLI / 测试 / 嵌入脚本）时返回 True：这些场景
    没有 GUI 线程与工具线程并发访问同一个 Session，保持旧行为即可。
    """
    return _main_thread_id is None or threading.get_ident() == _main_thread_id


def ensure_main_thread(operation: str) -> None:
    """工程数据库/生命周期操作的守卫；在 worker 线程调用时直接报错。"""
    if not is_main_thread():
        raise RuntimeError(
            f"{operation} 只能在界面主线程执行；"
            "AI/MCP 工具必须经 execute_on_main() 投递，不能在 worker 线程直接访问工程数据。"
        )


def _invoker_type() -> type:
    """惰性导入 Qt 并缓存中继类（headless 进程不创建任何 QObject）。"""
    global _invoker_class
    if _invoker_class is None:
        from PySide6.QtCore import QObject, Qt, Signal, Slot

        class _MainThreadInvoker(QObject):
            invoke = Signal(object)

            def __init__(self) -> None:
                super().__init__()
                # 显式 QueuedConnection：worker emit 后由主线程事件循环执行
                self.invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

            @Slot(object)
            def _run(self, call: _Call) -> None:
                try:
                    call.result = call.context.run(
                        call.function, *call.args, **call.kwargs
                    )
                except BaseException as error:  # noqa: BLE001 - 原样回传给调用线程
                    call.error = error
                finally:
                    call.event.set()

        _invoker_class = _MainThreadInvoker
    return _invoker_class


def install_main_thread_executor() -> None:
    """在 Qt 主线程创建中继对象；``app.main`` 在 QApplication 之后调用一次。"""
    from PySide6.QtCore import QCoreApplication, QThread

    app = QCoreApplication.instance()
    if app is None:
        raise RuntimeError(
            "install_main_thread_executor() 需要在 QApplication 创建后调用。"
        )
    if QThread.currentThread() != app.thread():
        raise RuntimeError("install_main_thread_executor() 必须在 Qt 主线程调用。")

    if _main_thread_id is None:
        mark_main_thread()
    elif threading.get_ident() != _main_thread_id:
        raise RuntimeError("install_main_thread_executor() 必须在 Qt 主线程调用。")

    global _invoker, _invoker_thread_id
    with _lock:
        if _invoker is not None and _invoker_thread_id == threading.get_ident():
            return
        _invoker = _invoker_type()()
        _invoker_thread_id = threading.get_ident()


def execute_on_main(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """在 Qt 主线程同步执行 ``function``，并返回结果（异常原样抛回调用线程）。

    * 没有 QApplication（headless CLI / 纯数据层测试）：直接执行；
    * 已在主线程：直接执行；
    * 已安装主线程执行器的 worker 线程：投递并阻塞等待；
    * 有 QApplication 但未标记/安装（测试或嵌入场景）：退回直接执行，
      保持兼容；生产入口 ``app.main`` 一定会先安装。
    """
    try:
        from PySide6.QtCore import QCoreApplication
    except ImportError:  # headless 环境没有 Qt：直接执行
        return function(*args, **kwargs)

    if QCoreApplication.instance() is None:
        return function(*args, **kwargs)
    if is_main_thread():
        return function(*args, **kwargs)

    invoker = _invoker
    if invoker is None:
        if _main_thread_id is not None:
            raise RuntimeError(
                "界面主线程执行器未安装：请在 QApplication 创建后调用 "
                "install_main_thread_executor()。"
            )
        # 测试 / 嵌入场景：没有标记主线程，也没有并发 GUI 访问，保持旧行为
        return function(*args, **kwargs)

    call = _Call(function, args, kwargs)
    invoker.invoke.emit(call)
    if not call.event.wait(_MAIN_THREAD_TIMEOUT):
        _logger.warning(
            "等待界面主线程执行 %r 超时（%ss）", function, _MAIN_THREAD_TIMEOUT
        )
        raise TimeoutError(
            f"等待界面主线程执行超时（{_MAIN_THREAD_TIMEOUT:g}s）。"
        )
    if call.error is not None:
        raise call.error
    return call.result
