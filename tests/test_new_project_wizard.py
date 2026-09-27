"""新建工程向导回归测试：预填默认项目名时“下一步”必须可用。

Qt 6.9+ 把 registerField("x*") 的必填判定改成“当前值 ≠ 初始值”，
预填默认值会让下一步一直禁用；向导因此改为显式 isComplete 按非空判断。
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWizard


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _next_button(wizard) -> bool:
    return wizard.button(QWizard.WizardButton.NextButton).isEnabled()


def test_next_enabled_with_default_name(qapp):
    from app.views.wizard.new_project_wizard import NewProjectWizard

    wizard = NewProjectWizard()
    wizard.restart()
    assert wizard._basic_page.project_name.text()
    assert _next_button(wizard)


def test_next_disabled_when_name_cleared(qapp):
    from app.views.wizard.new_project_wizard import NewProjectWizard

    wizard = NewProjectWizard()
    wizard.restart()
    wizard._basic_page.project_name.clear()
    qapp.processEvents()
    assert not _next_button(wizard)


def test_walk_through_all_pages(qapp):
    from app.views.wizard.new_project_wizard import NewProjectWizard

    wizard = NewProjectWizard()
    wizard.restart()
    wizard.next()
    assert wizard.currentPage().title() == "默认原则"
    wizard.next()
    assert wizard.currentPage().title() == "图集选择"
    assert wizard.button(QWizard.WizardButton.FinishButton).isEnabled()
