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
    assert "Python 线程栈" in text
    assert "qt: 6.11.2" in text


def test_faulting_module_handles_bad_address() -> None:
    assert native_crash._faulting_module(0) == ""
    assert isinstance(native_crash._faulting_module(0x1234), str)
