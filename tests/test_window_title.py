"""窗口标题（任务栏 / 开始菜单）只显示工程文件名与未保存星号的回归测试。

覆盖：

* 未开工程时标题就是应用名 Section2（任务栏只显示 Section2）；
* 开工程后窗口标题只显示工程文件名，任务栏显示“文件名 - Section2”；
* 临时工程（新建 / 1.0 转译后尚未保存到任何文件）按项目名给建议文件名，
  且从一开始就带 * 星号（无保存点即脏），显式保存后消失；
* 打开的工程距已保存点有修改时标题加 * 前缀，显式保存（界面 / AI 保存同一条
  project_saved 广播）后清掉；
* 撤销回已保存点内容星号自动消失（is_dirty 按内容比较，brackets2 同款）。
"""

from __future__ import annotations

import app  # noqa: F401  # ICU 预加载必须先于 PySide6

from app.core.event_bus import bus
from app.services import project_io
from app.services import undo as undo_stack
from app.services.project_io import NewProjectSpec
from app.views.main_window import MainWindow


def _open_window_with_project(qapp, path) -> MainWindow:
    """建主窗体并按既有用例的方式（广播 + 手动装树）挂上已打开的工程。"""
    window = MainWindow()
    window.show()
    bus().project_opened.emit(str(path) if path else "")
    window._tree_panel.vm.load()
    qapp.processEvents()
    return window


def test_undo_stack_saved_point_lifecycle(tmp_path, monkeypatch) -> None:
    """撤销栈的已保存点：修改置脏、显式保存清脏、撤销回保存内容也清脏。"""
    # 关掉时间窗合并：测试里两次 commit 间隔极短，Windows 的 time.monotonic
    # 粒度约 15ms，同一刻度内 delta 恰为 0.0，补 0 挡不住（0 <= 0 成立），
    # 两步会被并成一步、undo 落点变成基线——用负值让合并条件恒不成立
    monkeypatch.setattr(undo_stack, "_COALESCE_SECONDS", -1.0)
    path = tmp_path / "保存点.stn"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程"]))
    assert not undo_stack.is_dirty()  # 打开的工程内容来自磁盘，从无星号开始

    project_io.update_basic_info(project_name="改名工程")
    assert undo_stack.is_dirty()
    project_io.save()
    assert not undo_stack.is_dirty()  # 显式保存：已保存点刷新为当前内容

    project_io.update_basic_info(author="张三")
    assert undo_stack.is_dirty()
    snapshot = undo_stack.undo()
    assert snapshot is not None
    project_io.restore_snapshot(snapshot[0])
    assert not undo_stack.is_dirty()  # 撤销回已保存内容：按内容比较自动清星号


def test_transient_project_is_dirty_until_save_as(tmp_path) -> None:
    """新建临时工程（未保存到任何文件）没有保存点：一开始就是脏。

    另存为成功后才有保存点，星号才消失；1.0 转译打开同理（reset saved=False）。
    """
    project_io.new_project(NewProjectSpec())  # 无 path：临时工程
    assert undo_stack.is_dirty()

    project_io.save_as(tmp_path / "另存.stn")
    assert not undo_stack.is_dirty()  # 显式保存：已保存点建立


def test_window_title_without_project_shows_app_name(qapp) -> None:
    """未开工程：标题就是应用名 Section2（Qt 不再追加后缀，任务栏只显示它）。"""
    from app.core.version import APP_TITLE_NAME

    window = MainWindow()
    try:
        assert window.windowTitle() == APP_TITLE_NAME
    finally:
        window.close()
        qapp.processEvents()


def test_window_title_shows_file_name(qapp, project) -> None:
    """开工程后标题只显示工程文件名，不拼应用名；未修改无星号。"""
    window = _open_window_with_project(qapp, project)
    try:
        assert window.windowTitle() == "测试工程.stn"
    finally:
        window.close()
        qapp.processEvents()


def test_window_title_dirty_star_and_save_clears(qapp, project) -> None:
    """修改后标题加 *；显式保存后清掉（保存广播含 AI 保存工具同一路径）。"""
    window = _open_window_with_project(qapp, project)
    try:
        assert window.windowTitle() == "测试工程.stn"

        project_io.update_basic_info(author="张三")  # commit → 撤销栈监听刷新标题
        assert window.windowTitle() == "*测试工程.stn"

        project_io.save()
        # 保存广播（界面保存 / AI 保存都会发）触发标题刷新，星号清掉
        bus().project_saved.emit(str(project))
        qapp.processEvents()
        assert window.windowTitle() == "测试工程.stn"
    finally:
        window.close()
        qapp.processEvents()


def test_window_title_transient_project_uses_suggested_name(qapp) -> None:
    """新建临时工程标题显示建议文件名并带 *（内容尚未保存到任何文件）。

    临时工程带着未保存修改时 window.close() 会弹模态保存询问（阻塞离屏
    测试），所以先用 project_io.close_project() 关掉再拆窗体。
    """
    window = None
    try:
        project_io.new_project(NewProjectSpec())  # 无 path：临时工程
        window = _open_window_with_project(qapp, "")
        assert window.windowTitle() == "*新建项目.stn"

        project_io.update_basic_info(author="张三")
        assert window.windowTitle() == "*新建项目.stn"
    finally:
        project_io.close_project()
        if window is not None:
            window.close()
        qapp.processEvents()
