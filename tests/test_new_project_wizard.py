"""新建工程向导回归测试：单页（基本信息）+ 默认原则/图集按配置默认。

Qt 6.9+ 把 registerField("x*") 的必填判定改成“当前值 ≠ 初始值”，
预填默认值会让按钮一直禁用；向导因此改为显式 isComplete 按非空判断。
默认围护/地基原则与图集不再设页收集，values() 直接按配置默认带出。
"""

from dataclasses import fields

import pytest
from PySide6.QtWidgets import QWizard

from app.services.project_io import NewProjectSpec


@pytest.fixture(autouse=True)
def _fresh_config_cache():
    """用例前后清掉配置缓存：下面几个用例会把配置目录指到临时目录。"""
    from app.core import config

    config._Proxy.reload()
    yield
    config._Proxy.reload()


def _finish_button(wizard) -> bool:
    return wizard.button(QWizard.WizardButton.FinishButton).isEnabled()


def test_finish_enabled_only_with_nonempty_name(qapp):
    """默认名下 Finish 可用；名称清空后禁用（isComplete 按非空判断）。"""
    from app.views.dialogs.new_project_wizard import NewProjectWizard

    wizard = NewProjectWizard()
    wizard.restart()
    assert wizard._basic_page.project_name.text()
    # 只保留第一步：基本信息
    assert wizard.currentPage() is wizard._basic_page
    assert _finish_button(wizard)

    wizard._basic_page.project_name.clear()
    qapp.processEvents()
    assert not _finish_button(wizard)


def test_values_align_with_spec_and_use_defaults(qapp):
    """values() 键与 NewProjectSpec 字段对齐；四个默认原则名与图集按代码缺省带出。"""
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
    assert values["foundation_name"] == "默认地基原则"
    assert values["precipitation_name"] == "默认降水原则"
    assert values["width_name"] == "默认面宽原则"
    assert values["atlas_name"] == spec.atlas_name


def test_new_project_defaults_come_from_code_not_config(qapp, tmp_path, monkeypatch):
    """新建工程的默认名写死在代码里：配置里的 new_project 覆盖不了，也不再保留在文件里。

    背景：这些默认值以前能从 config.toml 覆盖，但“文件值优先 + 整份写回”会把
    默认值固化进文件、改代码里的默认值时老机器不生效（默认地基处理原则 →
    默认地基原则 就是这么被钉住的）。现在这一节已废弃。
    """
    from app.core import config
    from app.views.dialogs.new_project_wizard import NewProjectWizard

    monkeypatch.setenv("SECTION2_DATA_DIR", str(tmp_path))
    path = tmp_path / "config.toml"
    path.write_text(
        '[new_project]\nfoundation_name = "本项目地基原则"\nproject_name = "老工程"\n',
        encoding="utf-8",
    )
    # 读取时丢掉废弃节，向导不会用它
    assert "new_project" not in config.load_config()
    wizard = NewProjectWizard()
    wizard.restart()
    values = wizard.values()
    assert values["foundation_name"] == "默认地基原则"
    assert values["project_name"] == "新建项目"

    # 下一次保存后，文件里不再有这一节
    config.save_config(config.load_config())
    text = path.read_text(encoding="utf-8")
    assert "new_project" not in text and "本项目地基原则" not in text


def test_config_keeps_only_user_settings(qapp, tmp_path, monkeypatch):
    """空配置下向导仍按代码缺省；写入的是用户数据（最近打开），默认值不落盘。"""
    from app.core.config import add_recent_project
    from app.views.dialogs.new_project_wizard import NewProjectWizard

    monkeypatch.setenv("SECTION2_DATA_DIR", str(tmp_path))  # 空目录：无 config.toml
    wizard = NewProjectWizard()
    wizard.restart()
    assert wizard.values()["foundation_name"] == "默认地基原则"

    add_recent_project(tmp_path / "某工程.stn2")
    path = tmp_path / "config.toml"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "某工程.stn2" in text  # 用户数据在
    assert "new_project" not in text and "默认地基原则" not in text  # 默认值不在
