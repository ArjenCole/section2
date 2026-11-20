"""项目基本信息编辑对话框（编辑菜单「项目基本信息…」）。

可编辑旧版 ``mcBasicInfo`` 的三项内容：项目名称 / 项目编号 / 编制人。
项目名称同时是项目结构树根节点的显示名，提交后由调用方写库并刷新树。
"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QWidget

from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox
from app.views.widgets.platform_buttons import (
    CANCEL_TEXT,
    OK_TEXT,
    DialogButtonSpec,
    add_dialog_buttons,
)


class ProjectInfoDialog(FramelessDialog):
    """项目基本信息编辑窗体：项目名称 / 项目编号 / 编制人。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        project_name: str = "",
        project_index: str = "",
        author: str = "",
    ) -> None:
        super().__init__(parent, "项目基本信息")
        self.setMinimumWidth(460)
        self._build_ui(project_name, project_index, author)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self, project_name: str, project_index: str, author: str) -> None:
        layout = self.bodyLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)
        self._project_name = QLineEdit(project_name or "")
        self._project_name.setPlaceholderText("必填")
        self._project_index = QLineEdit(project_index or "")
        self._author = QLineEdit(author or "")
        form.addRow("项目名称", self._project_name)
        form.addRow("项目编号", self._project_index)
        form.addRow("编制人", self._author)
        layout.addLayout(form)

        # 标准按钮行：顺序 / 默认按钮 / 对齐按平台规范（见 platform_buttons）
        button_row = QHBoxLayout()
        add_dialog_buttons(
            button_row,
            [
                DialogButtonSpec(OK_TEXT, "accept", on_click=self._accept),
                DialogButtonSpec(CANCEL_TEXT, "reject", on_click=self.reject),
            ],
        )
        layout.addLayout(button_row)
        self._project_name.setFocus()
        self._project_name.selectAll()

    # ------------------------------------------------------------------ 数据
    def values(self) -> dict[str, str]:
        """返回去除首尾空白后的三项内容（``exec()`` 确认后由调用方读取）。"""
        return {
            "project_name": self._project_name.text().strip(),
            "project_index": self._project_index.text().strip(),
            "author": self._author.text().strip(),
        }

    def _accept(self) -> None:
        """校验后关闭：项目名称是文件头必填项，空名称不允许提交。"""
        if not self._project_name.text().strip():
            FramelessMessageBox.warning(self, "项目基本信息", "项目名称不能为空。")
            self._project_name.setFocus()
            return
        self.accept()
