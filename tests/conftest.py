"""pytest 全局配置与共享夹具。

这里先 ``import app``：包初始化里会预加载 Windows 系统 ICU，
必须早于任何模块导入 PySide6（详见 app/__init__.py 的说明）。
Qt 测试统一用离屏平台，不弹窗口。
"""

import os

import app  # noqa: F401  # ICU 预加载必须先于 PySide6
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.services import project_io
from app.services.project_io import NewProjectSpec


@pytest.fixture(scope="session")
def qapp():
    """全进程共享的离屏 QApplication。"""
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _closed_project():
    """每个用例前后都保证没有打开着的工程。"""
    project_io.close_project()
    yield
    project_io.close_project()


@pytest.fixture()
def project(tmp_path):
    """默认配置的临时工程（单个单位工程「雨水工程」），返回工程文件路径。"""
    path = tmp_path / "测试工程.stn2"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程"]))
    return path
