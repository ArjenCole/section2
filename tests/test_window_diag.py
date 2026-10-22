"""窗口诊断黑匣子（app/core/window_diag.py）的开关与空操作语义。

真实落盘需要 Windows 平台插件 + 顶层窗口，那部分由手工自测覆盖；
这里只锁住"默认不启用、失败不抛"这两条底线。
"""

from __future__ import annotations

from app.core import window_diag


def test_disabled_without_env(qapp, monkeypatch) -> None:
    """没有 SECTION2_DIAG 时 install() 返回 None，record() 是空操作。"""
    monkeypatch.delenv(window_diag.ENV_FLAG, raising=False)
    try:
        assert window_diag.install(qapp) is None
        assert window_diag.enabled() is False
        window_diag.record("unit.test", "未启用时不能抛", stack=2)
    finally:
        window_diag.shutdown()


def test_offline_platform_never_installs(qapp, monkeypatch) -> None:
    """离屏（offscreen）平台没有真实 HWND，即使开了开关也不启用。"""
    monkeypatch.setenv(window_diag.ENV_FLAG, "1")
    try:
        assert qapp.platformName() != "windows"
        assert window_diag.install(qapp) is None
        assert window_diag.enabled() is False
    finally:
        window_diag.shutdown()


def test_shutdown_is_idempotent() -> None:
    """重复 shutdown() 不能抛（退出路径会调它）。"""
    window_diag.shutdown()
    window_diag.shutdown()
    assert window_diag.enabled() is False
