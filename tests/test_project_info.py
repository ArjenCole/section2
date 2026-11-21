"""编辑菜单「项目基本信息」与项目名称同步的回归测试。

覆盖：

* 编辑菜单里挂有「项目基本信息…」，未开工程禁用、开工程启用；
* 对话框读取 / 返回三项内容（项目名称 / 项目编号 / 编制人）；
* 确认后写回 BasicInfo、刷新树根节点与窗口标题；
* 项目结构树根节点重命名同步修改项目名称（见 test_tree_inline_rename）。
"""

from __future__ import annotations

import app  # noqa: F401  # ICU 预加载必须先于 PySide6

from PySide6.QtWidgets import QDialog

from app.core.event_bus import bus
from app.services import project_io
from app.views.dialogs import project_info_dialog
from app.views.dialogs.project_info_dialog import ProjectInfoDialog
from app.views.main_window import MainWindow


def test_dialog_reads_and_returns_three_fields(qapp) -> None:
    """对话框用传入值初始化，values() 去掉首尾空白。"""
    dialog = ProjectInfoDialog(
        None,
        project_name="  测试工程  ",
        project_index=" T-001 ",
        author=" 张三 ",
    )
    try:
        assert dialog.values() == {
            "project_name": "测试工程",
            "project_index": "T-001",
            "author": "张三",
        }
    finally:
        dialog.close()


def test_dialog_rejects_empty_project_name(qapp, monkeypatch) -> None:
    """项目名称是文件头必填项：空名称不关闭对话框，弹提示。"""
    warnings: list[tuple] = []
    monkeypatch.setattr(
        project_info_dialog.FramelessMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    dialog = ProjectInfoDialog(None, project_name="")
    try:
        dialog._accept()
        assert warnings
        assert dialog.result() != QDialog.DialogCode.Accepted

        dialog._project_name.setText("有名字了")
        dialog._accept()
        assert dialog.result() == QDialog.DialogCode.Accepted
    finally:
        dialog.close()


def test_edit_menu_project_info_updates_basic_info_tree_and_title(qapp, project, monkeypatch) -> None:
    """点击菜单项 → 对话框确认 → 三项写回、树根节点与窗口标题同步。"""
    import app.views.main_window as main_window_module

    window = MainWindow()
    window.show()
    try:
        bus().project_opened.emit(str(project))
        window._tree_panel.vm.load()
        qapp.processEvents()

        assert window._act_project_info in window._edit_menu.actions()
        # 编辑菜单第一行就是「项目基本信息…」
        assert window._edit_menu.actions()[0] is window._act_project_info
        assert window._act_project_info.isEnabled()

        captured: dict = {}

        class FakeDialog:
            DialogCode = QDialog.DialogCode

            def __init__(self, parent, **kwargs) -> None:
                captured.update(kwargs)

            def exec(self) -> int:
                return QDialog.DialogCode.Accepted

            def values(self) -> dict[str, str]:
                return {
                    "project_name": "改后的工程",
                    "project_index": "P-2026",
                    "author": "李四",
                }

        monkeypatch.setattr(main_window_module, "ProjectInfoDialog", FakeDialog)

        window._edit_project_info()
        qapp.processEvents()

        # 对话框初始值来自当前 BasicInfo
        assert captured["project_name"] == "新建项目"
        assert captured["project_index"] == "001"

        info = project_io.basic_info()
        assert info is not None
        assert (info.project_name, info.project_index, info.author) == (
            "改后的工程",
            "P-2026",
            "李四",
        )
        root = window._tree_panel._tree.topLevelItem(0)
        assert root.text(0) == "改后的工程"
        # 窗口标题只显示工程文件名（Quotor 同款），项目名称变化不进标题；
        # 改名是一次未显式保存的修改，标题带 * 星号
        assert window.windowTitle() == "*测试工程.stn"
    finally:
        window.close()
        qapp.processEvents()


def test_project_info_action_disabled_without_project(qapp) -> None:
    """未打开工程时菜单项不可用（与其它工程级动作一致）。"""
    window = MainWindow()
    try:
        assert not window._act_project_info.isEnabled()
    finally:
        window.close()
        qapp.processEvents()
