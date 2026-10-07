"""新建工程向导（只保留第一步：项目基本信息）。

沿用旧版 FormNewGuide 的字段：项目名称 / 项目编号 / 编制人 / 标段数量 / 涵盖专业。
默认围护原则、地基处理原则与图集不再向用户收集，直接按配置默认值
（config.new_project，缺省同旧版构造）带入 NewProjectSpec；建文件由
project_io.new_project 执行。
"""

from __future__ import annotations

import getpass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from app.core.config import get_config
from app.core.version import DEFAULT_ATLAS_NAME
from app.views.widgets.frameless_dialog import FramelessDialog

#: 旧版 FormNewGuide 的“涵盖专业”勾选项，勾上的会建成单位工程
_MAJORS = ("雨水工程", "污水工程", "给水工程", "中水工程")

#: 默认围护原则的固定缺省（原第二页的初始值；config 里没有对应键）
_DEFAULT_EXCVT = "Ⅲ类土"
_DEFAULT_FOUND_ANGLE = 120
_DEFAULT_CON_FOUND = True


class BasicInfoPage(QWizardPage):
    """项目基本信息 + 标段数量 + 涵盖专业。"""

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("基本信息")
        self.setSubTitle("工程名称与结构；标段、单位工程的名称稍后可在项目树中重命名。")

        defaults = get_config().new_project
        layout = QVBoxLayout(self)

        info_box = QGroupBox("项目基本信息")
        form = QFormLayout(info_box)
        self.project_name = QLineEdit(str(defaults.get("project_name", "新建项目")))
        self.project_name.setPlaceholderText("必填")
        self.project_index = QLineEdit(str(defaults.get("project_index", "001")))
        self.author = QLineEdit(str(defaults.get("author", "")) or getpass.getuser())
        form.addRow("项目名称", self.project_name)
        form.addRow("项目编号", self.project_index)
        form.addRow("编制人", self.author)
        layout.addWidget(info_box)

        structure_box = QGroupBox("工程结构")
        structure = QGridLayout(structure_box)
        self.segment_count = QSpinBox()
        self.segment_count.setRange(1, 50)
        self.segment_count.setValue(1)
        self.segment_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        structure.addWidget(QLabel("标段数量"), 0, 0)
        structure.addWidget(self.segment_count, 0, 1)
        structure.addWidget(QLabel("涵盖专业"), 1, 0)
        majors = QWidget()
        majors_layout = QGridLayout(majors)
        majors_layout.setContentsMargins(0, 0, 0, 0)
        self.major_boxes: list[QCheckBox] = []
        for index, name in enumerate(_MAJORS):
            box = QCheckBox(name)
            box.setChecked(index == 0)
            majors_layout.addWidget(box, index // 2, index % 2)
            self.major_boxes.append(box)
        structure.addWidget(majors, 1, 1)
        layout.addWidget(structure_box)
        layout.addStretch(1)

        # 不用 registerField("name*")：Qt 6.9+ 把必填字段判定为“当前值 ≠ 初始值”，
        # 预填的默认名会令完成按钮一直禁用，这里显式按非空判断。
        self.project_name.textChanged.connect(self.completeChanged)

    def isComplete(self) -> bool:
        return bool(self.project_name.text().strip())

    def unit_names(self) -> list[str]:
        return [box.text() for box in self.major_boxes if box.isChecked()]


class NewProjectWizardCore(QWizard):
    """新建工程向导核心（单页：基本信息，由 NewProjectWizard 无边框容器承载）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        # Apple HIG：取消在左下角，完成在右下角（单页无上一步/下一步）
        self.setButtonLayout(
            (
                QWizard.WizardButton.CancelButton,
                QWizard.WizardButton.Stretch,
                QWizard.WizardButton.FinishButton,
            )
        )
        self._basic_page = BasicInfoPage()
        self.setPage(0, self._basic_page)

    def values(self) -> dict:
        """收集向导输入，交给 NewProjectSpec；原则与图集直接取配置默认。"""
        defaults = get_config().new_project
        segment_count = self._basic_page.segment_count.value()
        segment_name = str(defaults.get("segment_name", "新建标段"))
        return {
            "project_name": self._basic_page.project_name.text().strip(),
            "project_index": self._basic_page.project_index.text().strip(),
            "author": self._basic_page.author.text().strip(),
            "atlas_name": str(defaults.get("atlas_name", DEFAULT_ATLAS_NAME)),
            "segment_names": [segment_name] * segment_count,
            "unit_names": self._basic_page.unit_names(),
            "enclosure_name": str(defaults.get("enclosure_name", "默认围护原则")),
            "enclosure_excvt": _DEFAULT_EXCVT,
            "enclosure_found_angle": _DEFAULT_FOUND_ANGLE,
            "enclosure_con_found": _DEFAULT_CON_FOUND,
            "foundation_name": str(defaults.get("foundation_name", "默认地基处理原则")),
        }


class NewProjectWizard(FramelessDialog):
    """新建工程向导（无边框：自绘标题栏 + 内嵌单页 QWizard）。

    对外接口：exec() / values()，以及 restart / button / currentPage /
    _basic_page 委托（测试沿用）。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, "新建工程向导")
        self.setMinimumSize(560, 420)
        self._wizard = NewProjectWizardCore(self)
        # QWizard 是 QDialog，嵌入布局前把窗口类型降为普通子控件
        self._wizard.setWindowFlags(Qt.WindowType.Widget)
        self._wizard.setVisible(True)
        self.bodyLayout().addWidget(self._wizard)
        # 内嵌 QWizard 点“完成”/“取消”时只隐藏自己，exec() 停在外层容器上；
        # 把结果转发给容器，外层才会关闭并返回
        self._wizard.accepted.connect(self.accept)
        self._wizard.rejected.connect(self.reject)

    def values(self) -> dict:
        return self._wizard.values()

    # --- QWizard API 委托（测试与外部调用沿用原接口） ---
    def restart(self) -> None:
        self._wizard.restart()

    def button(self, which) -> "QWizard":
        return self._wizard.button(which)

    def currentPage(self):
        return self._wizard.currentPage()

    @property
    def _basic_page(self):
        return self._wizard._basic_page


def suggested_file_name(project_name: str) -> str:
    """按项目名称给出建议文件名（去掉路径非法字符）。"""
    safe = "".join(ch for ch in (project_name or "新建项目") if ch not in '\\/:*?"<>|').strip()
    return f"{safe or '新建项目'}.stn2"


def suggested_dir() -> Path:
    """新建工程的默认目录：上次用过的目录，否则我的文档\\Section2。"""
    from app.core.paths import default_project_dir

    last = get_config().last_dir
    if last and Path(last).is_dir():
        return Path(last)
    return default_project_dir()
