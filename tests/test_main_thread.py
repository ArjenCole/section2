"""主线程执行器与数据层线程守卫回归测试。"""

from __future__ import annotations

import threading
import time

from app.agent.tool_registry import Tool, ToolRegistry
from app.core import main_thread
from app.core.models import base as orm
from app.services import project_io


def _save_state() -> tuple:
    return (
        main_thread._main_thread_id,
        main_thread._invoker,
        main_thread._invoker_thread_id,
    )


def _restore_state(state: tuple) -> None:
    (
        main_thread._main_thread_id,
        main_thread._invoker,
        main_thread._invoker_thread_id,
    ) = state


def _drain_until(qapp, thread: threading.Thread, timeout: float = 5.0) -> None:
    """主线程持续处理 Qt 事件，直到 worker 完成（模拟 GUI 事件循环）。"""
    deadline = time.monotonic() + timeout
    while thread.is_alive() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.002)


def test_tool_registry_marshals_executor_to_main_thread(qapp) -> None:
    state = _save_state()
    main_thread.install_main_thread_executor()
    try:
        seen: list[int] = []
        registry = ToolRegistry()

        def executor(_arguments: dict) -> dict:
            seen.append(threading.get_ident())
            return {"ok": True}

        registry.register(
            Tool("fake_read", "测试工具", {"type": "object", "properties": {}}, executor)
        )
        holder: dict = {}

        def worker() -> None:
            holder["result"] = registry.execute("fake_read", {})

        thread = threading.Thread(target=worker)
        thread.start()
        _drain_until(qapp, thread)
        thread.join(timeout=1)

        assert not thread.is_alive()
        assert holder["result"] == {"ok": True}
        assert seen == [threading.get_ident()]  # 执行器跑在主线程
    finally:
        _restore_state(state)


def test_execute_on_main_keeps_contextvars(qapp) -> None:
    """MCP 通道标记等 ContextVar 必须随调用复制到主线程（check_write_path 依赖）。"""
    from app.agent.confirm_policy import CHANNEL_MCP, channel, current_channel

    state = _save_state()
    main_thread.install_main_thread_executor()
    try:
        holder: dict = {}

        def worker() -> None:
            with channel(CHANNEL_MCP):
                holder["channel"] = main_thread.execute_on_main(current_channel)

        thread = threading.Thread(target=worker)
        thread.start()
        _drain_until(qapp, thread)
        thread.join(timeout=1)

        assert holder.get("channel") == CHANNEL_MCP
    finally:
        _restore_state(state)


def test_database_operations_rejected_from_worker_thread() -> None:
    state = _save_state()
    main_thread._main_thread_id = -1  # 模拟“已标记主线程”，与当前测试线程不同
    try:
        errors: list[BaseException] = []

        def worker() -> None:
            operations = (
                ("session", orm.session, ()),
                ("commit", project_io.commit, ()),
                ("open", project_io.open_project, ("not-there.stn2",)),
            )
            for _name, operation, arguments in operations:
                try:
                    operation(*arguments)
                except BaseException as error:  # noqa: BLE001
                    errors.append(error)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=2)

        assert not thread.is_alive()
        assert len(errors) == 3
        assert all(isinstance(error, RuntimeError) for error in errors)
        assert all("界面主线程" in str(error) for error in errors)
    finally:
        _restore_state(state)
