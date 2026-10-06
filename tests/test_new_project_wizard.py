"""新建工程向导回归测试：单页（基本信息）+ 默认原则/图集按配置默认。

Qt 6.9+ 把 registerField("x*") 的必填判定改成“当前值 ≠ 初始值”，
预填默认值会让按钮一直禁用；向导因此改为显式 isComplete 按非空判断。
默认围护/地基原则与图集不再设页收集，values() 直接按配置默认带出。
"""

import os
from dataclasses import fields

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWizard

from app.services.project_io import NewProjectSpec


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _finish_button(wizard) -> bool:
    return wizard.button(QWizard.WizardButton.FinishButton).isEnabled()


def test_finish_enabled_with_default_name(qapp):
    from app.views.dialogs.new_project_wizard import NewProjectWizard

    wizard = NewProjectWizard()
    wizard.restart()
    assert wizard._basic_page.project_name.text()
    # 只保留第一步：基本信息
    assert wizard.currentPage() is wizard._basic_page
    assert _finish_button(wizard)


def test_finish_disabled_when_name_cleared(qapp):
    from app.views.dialogs.new_project_wizard import NewProjectWizard

    wizard = NewProjectWizard()
    wizard.restart()
    wizard._basic_page.project_name.clear()
    qapp.processEvents()
    assert not _finish_button(wizard)


def test_values_align_with_spec_and_use_defaults(qapp):
    """values() 键与 NewProjectSpec 字段对齐；原则/图集按默认带出。"""
    from app.views.dialogs.new_project_wizard import NewProjectWizard

    wizard = NewProjectWizard()
    wizard.restart()
    values = wizard.values()

    spec_keys = {field.name for field in fields(NewProjectSpec)}
    assert set(values) <= spec_keys
    spec = NewProjectSpec(**values)  # 能直接构造，不抛未知字段

    assert values["project_name"] == "新建项目"
    assert values["segment_names"] == ["新建标段"]
    assert values["unit_names"] == ["雨水工程"]
    assert values["enclosure_name"] == "默认围护原则"
    assert values["enclosure_excvt"] == "Ⅲ类土"
    assert values["enclosure_found_angle"] == 120
    assert values["enclosure_con_found"] is True
    assert values["foundation_name"] == "默认地基处理原则"
    assert values["atlas_name"] == spec.atlas_name
