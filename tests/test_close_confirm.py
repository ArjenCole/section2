"""主窗体「未保存工程」关闭确认的三条分支。

用户报告回归（2026-11）：新建项目（临时工程）后关闭窗体，保存 / 不保存 /
取消三个按钮按哪个都没有效果。根因是 FramelessMessageBox 的按钮回调把
clicked(bool) 的 checked 位置参数当成了 StandardButton（_result 恒为
False），主窗体三条分支全部落空。消息框点击语义的单元级防护见
tests/test_platform_buttons.py，这里锁主窗体层面的流程结果。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from app.services import project_io
from app.services.project_io import NewProjectSpec
from app.views.widgets import frameless_dialog as fd


@pytest.fixture()
def transient_window(qapp):
    """新建临时工程（未保存过）并挂一个主窗体。"""
    from app.views.main_window import MainWindow

    project_io.new_project(NewProjectSpec(path=None, unit_names=["雨水工程"]))
    assert project_io.is_transient()
    window = MainWindow()
    window.show()
    qapp.processEvents()
    yield window
    project_io.close_project()
    window.close()
    qapp.processEvents()


def _prompt_with(monkeypatch, reply: QMessageBox.StandardButton):
    """把确认框固定返回 reply，返回「是否允许继续」的结果。"""

    def fake_question(parent, title, text, buttons=None, default=None, **kwargs):
        assert buttons & QMessageBox.StandardButton.Save
        assert buttons & QMessageBox.StandardButton.Discard
        assert buttons & QMessageBox.StandardButton.Cancel
        return reply

    monkeypatch.setattr(fd.FramelessMessageBox, "question", staticmethod(fake_question))


def test_discard_continues_close(transient_window, monkeypatch) -> None:
    """不保存 → 允许继续关闭。"""
    _prompt_with(monkeypatch, QMessageBox.StandardButton.Discard)
    assert transient_window._prompt_save_if_unsaved("关闭") is True


def test_cancel_aborts_close(transient_window, monkeypatch) -> None:
    """取消 → 中止关闭。"""
    _prompt_with(monkeypatch, QMessageBox.StandardButton.Cancel)
    assert transient_window._prompt_save_if_unsaved("关闭") is False


def test_save_goes_to_save_as(transient_window, monkeypatch) -> None:
    """保存 → 走另存为；用户取消选路径时中止关闭。"""
    _prompt_with(monkeypatch, QMessageBox.StandardButton.Save)
    monkeypatch.setattr(transient_window, "_prompt_save_as_path", lambda caption: None)
    assert transient_window._prompt_save_if_unsaved("关闭") is False


def test_save_as_writes_file(transient_window, monkeypatch, tmp_path) -> None:
    """保存 → 另存为成功写出 .stn 后允许继续。"""
    _prompt_with(monkeypatch, QMessageBox.StandardButton.Save)
    target = tmp_path / "另存工程.stn"
    monkeypatch.setattr(
        transient_window, "_prompt_save_as_path", lambda caption: target
    )
    assert transient_window._prompt_save_if_unsaved("关闭") is True
    assert target.exists()


def test_saved_project_skips_prompt(qapp, project, monkeypatch) -> None:
    """已保存到文件的工程不再弹确认（直接允许）。"""
    from app.views.main_window import MainWindow

    called: list[str] = []
    monkeypatch.setattr(
        fd.FramelessMessageBox,
        "question",
        staticmethod(lambda *a, **k: called.append("asked")),
    )
    window = MainWindow(project_path=project)
    try:
        assert window._prompt_save_if_unsaved("关闭") is True
        assert called == []
    finally:
        window.deleteLater()
        qapp.processEvents()
