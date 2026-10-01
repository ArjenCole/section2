"""新建工程向导（计划 §7.1：基本信息 → 默认原则 → 图集选择）。

沿用旧版 FormNewGuide 的字段：项目名称 / 项目编号 / 编制人 / 标段数量 / 涵盖专业，
再补上默认原则与图集两页。向导只负责收集输入，建文件由 project_io.new_project 执行。
"""

from __future__ import annotations

import getpass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from app.core.paths import atlas_dir
from app.core.version import DEFAULT_ATLAS_NAME
from app.views.widgets.frameless_dialog import FramelessDialog

#: 旧版 FormNewGuide 的“涵盖专业”勾选项，勾上的会建成单位工程
_MAJORS = ("雨水工程", "污水工程", "给水工程", "中水工程")

#: 旧版 FormPE 的下拉项
_EXCVT_CHOICES = ("Ⅰ、Ⅱ类土", "Ⅲ类土", "Ⅳ类土", "松石", "次坚石", "普坚石", "特坚石")
_FOUND_ANGLE_CHOICES = ("90", "120", "150", "180")


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
        # 预填的默认名会令下一步一直禁用，这里显式按非空判断。
        self.project_name.textChanged.connect(self.completeChanged)

    def isComplete(self) -> bool:
        return bool(self.project_name.text().strip())

    def unit_names(self) -> list[str]:
        return [box.text() for box in self.major_boxes if box.isChecked()]


class PrinciplePage(QWizardPage):
    """默认围护原则 / 地基处理原则。"""

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("默认原则")
        self.setSubTitle("新工程的默认原则；详细做法（分层、构件公式、工作面宽度、降水）在 M3 的原则编辑器里维护。")

        defaults = get_config().new_project
        layout = QVBoxLayout(self)

        enclosure_box = QGroupBox("围护原则（PE）")
        form = QFormLayout(enclosure_box)
        self.enclosure_name = QLineEdit(str(defaults.get("enclosure_name", "默认围护原则")))
        self.excvt = QComboBox()
        self.excvt.addItems(_EXCVT_CHOICES)
        self.excvt.setCurrentText("Ⅲ类土")
        self.found_angle = QComboBox()
        self.found_angle.addItems(_FOUND_ANGLE_CHOICES)
        self.found_angle.setCurrentText("120")
        self.con_found = QComboBox()
        self.con_found.addItems(("采用混凝土基础", "不采用混凝土基础"))
        form.addRow("原则名称", self.enclosure_name)
        form.addRow("开挖土质", self.excvt)
        form.addRow("基础角度", self.found_angle)
        form.addRow("管道基础", self.con_found)
        layout.addWidget(enclosure_box)

        foundation_box = QGroupBox("地基处理原则（PF）")
        foundation_form = QFormLayout(foundation_box)
        self.foundation_name = QLineEdit(str(defaults.get("foundation_name", "默认地基处理原则")))
        foundation_form.addRow("原则名称", self.foundation_name)
        layout.addWidget(foundation_box)
        layout.addStretch(1)


class AtlasPage(QWizardPage):
    """通用图集选择。"""

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("图集选择")
        self.setSubTitle("查表用的通用图集；图集数据文件放在 app/resources/atlas 下（M3 从旧版复制）。")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        default = str(get_config().new_project.get("atlas_name", DEFAULT_ATLAS_NAME))
        self.atlas = QComboBox()
        self.atlas.addItems(_available_atlases(default))
        self.atlas.setCurrentText(default)
        form.addRow("通用图集", self.atlas)
        layout.addLayout(form)
        self.hint = QLabel("")
        self.hint.setProperty("role", "hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        layout.addStretch(1)
        self._update_hint()

    def _update_hint(self) -> None:
        folder = atlas_dir()
        files = sorted(folder.glob("*.xlsx")) if folder.exists() else []
        if files:
            self.hint.setText(f"已发现 {len(files)} 个图集文件：{folder}")
        else:
            self.hint.setText(f"尚未复制图集数据文件（{folder}），M3 会从旧版 bin\\Debug\\Atlas 复制。")


class NewProjectWizardCore(QWizard):
    """新建工程向导核心（QWizard 页面流，由 NewProjectWizard 无边框容器承载）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self._basic_page = BasicInfoPage()
        self._principle_page = PrinciplePage()
        self._atlas_page = AtlasPage()
        self.setPage(0, self._basic_page)
        self.setPage(1, self._principle_page)
        self.setPage(2, self._atlas_page)

    def values(self) -> dict:
        """收集向导输入，交给 NewProjectSpec。"""
        defaults = get_config().new_project
        segment_count = self._basic_page.segment_count.value()
        segment_name = str(defaults.get("segment_name", "新建标段"))
        return {
            "project_name": self._basic_page.project_name.text().strip(),
            "project_index": self._basic_page.project_index.text().strip(),
            "author": self._basic_page.author.text().strip(),
            "atlas_name": self._atlas_page.atlas.currentText().strip(),
            "segment_names": [segment_name] * segment_count,
            "unit_names": self._basic_page.unit_names(),
            "enclosure_name": self._principle_page.enclosure_name.text().strip(),
            "enclosure_excvt": self._principle_page.excvt.currentText(),
            "enclosure_found_angle": int(self._principle_page.found_angle.currentText()),
            "enclosure_con_found": self._principle_page.con_found.currentText().startswith("采用"),
            "foundation_name": self._principle_page.foundation_name.text().strip(),
        }


class NewProjectWizard(FramelessDialog):
    """新建工程向导（无边框：自绘标题栏 + 内嵌 QWizard 页面流）。

    对外接口与原 QWizard 版一致：exec() / values()，并把常用的
    QWizard 导航 API（restart/next/button/currentPage）与三个页面
    属性委托到内嵌向导。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, "新建工程向导")
        self.setMinimumSize(560, 460)
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

    def next(self) -> None:
        self._wizard.next()

    def back(self) -> None:
        self._wizard.back()

    def button(self, which) -> "QWizard":
        return self._wizard.button(which)

    def currentPage(self):
        return self._wizard.currentPage()

    @property
    def _basic_page(self):
        return self._wizard._basic_page

    @property
    def _principle_page(self):
        return self._wizard._principle_page

    @property
    def _atlas_page(self):
        return self._wizard._atlas_page


def _available_atlases(configured: str = "") -> list[str]:
    """图集下拉项：优先列 atlas 目录里的文件，目录为空时给默认值。"""
    names: list[str] = []
    folder = atlas_dir()
    if folder.exists():
        names = sorted(path.stem for path in folder.glob("*.xlsx"))
    for fallback in (configured, DEFAULT_ATLAS_NAME):
        if fallback and fallback not in names:
            names.insert(0, fallback)
    return names


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
