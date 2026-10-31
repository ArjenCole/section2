"""窗口诊断黑匣子（app/core/window_diag.py）的开关、空操作与异常判定语义。

真实落盘需要 Windows 平台插件 + 顶层窗口，那部分由手工自测覆盖；
这里锁住"默认不启用、失败不抛"以及 2026-10-29 之后新增的判定规则。
"""

from __future__ import annotations

import weakref

from app.core import window_diag


def test_disabled_without_env(qapp, monkeypatch) -> None:
    """没有 SECTION2_DIAG 时 install() 返回 None，record() 是空操作。"""
    monkeypatch.delenv(window_diag.ENV_FLAG, raising=False)
    try:
        assert window_diag.install(qapp) is None
        assert window_diag.enabled() is False
        assert window_diag.record("unit.test", "未启用时不能抛", stack=2) == ""
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


# --------------------------------------------------------------------------- #
# 2026-10-29 现场之后新增的判定规则（不依赖真实窗口，直接测纯逻辑）
# --------------------------------------------------------------------------- #
class _FakeWidget:
    def __init__(self, minimized: bool = False, visible: bool = True) -> None:
        self._minimized = minimized
        self._visible = visible

    def isMinimized(self) -> bool:  # noqa: N802 - 模仿 Qt 命名
        return self._minimized

    def isVisible(self) -> bool:  # noqa: N802
        return self._visible


def _bare_diag(hwnd: int = 100) -> window_diag.WindowDiag:
    """绕过 __init__（需要真实 Windows 窗口），只装判定所需的最小状态。"""
    diag = object.__new__(window_diag.WindowDiag)
    widget = _FakeWidget()
    diag._fake = widget  # 强引用：否则 weakref 立即失效
    diag._important = {hwnd}
    diag._closed = set()
    diag._hidden = set()
    diag._widgets = {hwnd: weakref.ref(widget)}
    diag._main_hwnd = hwnd
    diag._main_closed = False
    return diag


def test_bare_hide_of_main_window_is_anomalous() -> None:
    """主窗体无 Close、非最小化、非 spontaneous 的 Hide 必须判为异常。"""
    diag = _bare_diag()
    widget = _FakeWidget()
    assert diag._is_anomalous_hide(widget, 100, False, "eventFilter <- _populate_full")
    # 最小化（栈里有 _on_minimize）不算异常
    assert not diag._is_anomalous_hide(
        widget, 100, False, "eventFilter <- _on_minimize@main_window.py:216"
    )
    # 系统级隐藏（spontaneous）不算异常
    assert not diag._is_anomalous_hide(widget, 100, True, "eventFilter <- app.exec")
    # 明确 Close 过的 Hide 不算异常
    diag._closed.add(100)
    assert not diag._is_anomalous_hide(widget, 100, False, "eventFilter <- app.exec")


def test_main_window_destroy_requires_close() -> None:
    """主窗体只有明确收到 Close 才算"正常销毁"；仅 Hide 不算。"""
    diag = _bare_diag()
    diag._hidden.add(100)  # 只有 Hide、没有 Close
    assert diag._destroy_expected(100) is False
    diag._closed.add(100)
    assert diag._destroy_expected(100) is True
    # 非主窗体（菜单/弹层）保持宽松口径
    other = object.__new__(window_diag.WindowDiag)
    fake = _FakeWidget(visible=False)
    other._fake = fake
    other._important = set()
    other._hidden = {200}
    other._widgets = {200: weakref.ref(fake)}
    assert other._destroy_expected(200) is True


def test_quit_without_close_flag_survives_forget() -> None:
    """正常 Close 后即使 DESTROY 清理了集合，退出判定仍应知道主窗体已关闭。"""
    diag = _bare_diag()
    assert diag._quit_without_close() is True
    diag._main_closed = True
    assert diag._quit_without_close() is False


# --------------------------------------------------------------------------- #
# 2026-10-31 现场之后新增：closeEvent 弹模态确认框期间不算“关闭被取消”
# （20:32 等五次现场：确认框开着时自检把 _closed 撤了，用户确认后的正常
# Hide 被误判为异常 Hide，产生了五份假 dump）
# --------------------------------------------------------------------------- #
def test_close_was_ignored_false_while_modal_prompt_open(monkeypatch) -> None:
    """主窗体可见但有模态框在弹（确认保存提示）：不算“关闭被取消”。"""
    from PySide6.QtWidgets import QApplication

    sentinel = object()
    monkeypatch.setattr(
        QApplication, "activeModalWidget", staticmethod(lambda: sentinel)
    )
    assert window_diag.WindowDiag._close_was_ignored(_FakeWidget()) is False


def test_close_was_ignored_true_when_visible_and_modal_free(monkeypatch) -> None:
    """Close 之后仍可见、且没有任何模态框：才算“关闭被取消”（点过取消）。"""
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(
        QApplication, "activeModalWidget", staticmethod(lambda: None)
    )
    assert window_diag.WindowDiag._close_was_ignored(_FakeWidget()) is True
    # 已经隐藏（Hide 已发生）：不能判“被取消”
    assert (
        window_diag.WindowDiag._close_was_ignored(_FakeWidget(visible=False))
        is False
    )
