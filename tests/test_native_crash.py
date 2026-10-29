"""原生崩溃黑匣子（app/core/native_crash.py）的安装与文本报告。

真正触发崩溃没法在单测里做（会把 pytest 进程带走），这里只锁住：
- install/uninstall 幂等、不抛；
- 文本报告内容包含异常码 / 故障模块 / Python 栈段；
- 故障模块解析对非法地址不抛。
"""

from __future__ import annotations

from app.core import native_crash


def test_install_is_idempotent_and_does_not_raise() -> None:
    try:
        first = native_crash.install()
        second = native_crash.install()
        assert isinstance(first, bool)
        assert first == second
    finally:
        native_crash.uninstall()
        native_crash.uninstall()


def test_text_report_contains_crash_fields(tmp_path) -> None:
    path = tmp_path / "crash.txt"
    native_crash._write_text_report(
        path,
        {
            "time": "2026-10-29T09:35:33",
            "pid": 1234,
            "tid": 5678,
            "code": 0xC0000409,
            "flags": 0,
            "address": 0x1C8D8,
            "params": [7],
            "module": r"F:\...\PySide6\Qt6Core.dll (+0x1C8D8)",
            "env": {"python": "3.12.4", "qt": "6.11.2"},
        },
    )
    text = path.read_text(encoding="utf-8")
    assert "原生崩溃报告" in text
    assert "0xC0000409" in text
    assert "Qt6Core.dll (+0x1C8D8)" in text
    assert "原生调用栈" in text
    assert "Python 线程栈" in text
    assert "qt: 6.11.2" in text


def test_text_report_writes_native_stack_before_python_stack(tmp_path) -> None:
    """栈溢出时 minidump 写不出来，原生栈必须已落进文本报告。"""
    path = tmp_path / "crash.txt"
    native_crash._write_text_report(
        path,
        {
            "time": "2026-10-29T12:56:44",
            "pid": 1,
            "tid": 2,
            "code": 0xC00000FD,
            "flags": 0,
            "address": 0x7FF835219304,
            "params": [1, 0xF050003FC8],
            "module": r"d:\anaconda3\python312.dll (+0x289304)",
            "native_stack": [
                "#00 0x7FF835219304  python312.dll (+0x289304)",
                "#01 0x7FF800001234  Qt6Widgets.dll (+0x1234)",
            ],
            "env": {},
        },
    )
    text = path.read_text(encoding="utf-8")
    assert "0xC00000FD" in text
    native_at = text.index("Qt6Widgets.dll (+0x1234)")
    python_at = text.index("Python 线程栈")
    assert native_at < python_at


def test_capture_native_stack_never_raises() -> None:
    frames = native_crash._capture_native_stack(8)
    assert isinstance(frames, list)
    assert all(isinstance(frame, int) for frame in frames)
    formatted = native_crash._format_native_stack(frames)
    assert len(formatted) == len(frames)


def test_stack_guarantee_is_idempotent() -> None:
    try:
        native_crash.install()  # 初始化 Win32 绑定并设置预留
        first = native_crash._set_stack_guarantee()
        second = native_crash._set_stack_guarantee()
        assert isinstance(first, bool)
        assert first == second
    finally:
        native_crash._GUARANTEE_SET = False
        native_crash.uninstall()


def test_faulting_module_handles_bad_address() -> None:
    assert native_crash._faulting_module(0) == ""
    assert isinstance(native_crash._faulting_module(0x1234), str)
