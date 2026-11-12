"""pytest 全局配置与共享夹具。

这里先 ``import app``：包初始化里会预加载 Windows 系统 ICU，
必须早于任何模块导入 PySide6（详见 app/__init__.py 的说明）。
Qt 测试统一用离屏平台，不弹窗口。
"""

import gc
import os
import tempfile
from pathlib import Path

import app  # noqa: F401  # ICU 预加载必须先于 PySide6
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 配置 / 数据目录换成临时目录：测试（含 MainWindow 打开工程时的“最近打开”
# 落盘）不读写开发机上的真实 config.toml，用例结果也不再受本机配置影响
os.environ.setdefault(
    "SECTION2_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="section2-test-data-")))
)

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from app.services import project_io
from app.services.project_io import NewProjectSpec


@pytest.fixture(scope="session")
def qapp():
    """全进程共享的离屏 QApplication。"""
    yield QApplication.instance() or QApplication([])


def _dispose_top_level_widgets() -> None:
    """销毁用例遗留的顶层控件，避免其信号连接跨用例累积。

    用例里直接 ``UnitPanel()`` / ``MainWindow()`` 创建的窗体不会自动销毁，
    它们仍连着全局事件总线；后续用例每发一次 ``unit_changed``，所有历史面板
    都会重算一遍，整个套件越跑越慢（实测单个用例可从 3s 膨胀到 120s）。
    """
    application = QApplication.instance()
    if application is None:
        return
    from shiboken6 import isValid

    # ``isValid`` 不是可选的保险：无边框对话框（FramelessDialog 子类）里放了
    # QComboBox、又从未 show 就 close()（→ done() 排期 deleteLater）时，Qt 拆除
    # 阶段会留下已析构控件的 Python 包装，``allWidgets()`` 仍把它列出来，直接
    # ``widget.parent()`` 就是 access violation（进程级崩溃，不是异常）。
    leftovers = [
        widget
        for widget in QApplication.allWidgets()
        if isValid(widget) and widget.parent() is None
    ]
    if not leftovers:
        return
    for widget in leftovers:
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    gc.collect()


@pytest.fixture(autouse=True)
def _closed_project():
    """每个用例前后都保证没有打开着的工程，并销毁遗留窗体。"""
    project_io.close_project()
    yield
    project_io.close_project()
    _dispose_top_level_widgets()


@pytest.fixture()
def project(tmp_path):
    """默认配置的临时工程（单个单位工程「雨水工程」），返回工程文件路径。"""
    path = tmp_path / "测试工程.stn"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程"]))
    return path


# --------------------------------------------------------------------------- #
# 共享搭建助手（合槽/围护类测试用；原在 test_lr_enclosure 与
# test_workface_distance 里逐字重复，收拢到这里，用例文件直接 import）
# --------------------------------------------------------------------------- #
def first_unit_id():
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Unit

    return orm.session().scalar(select(Unit.id))


def make_enclosure(name: str, category: str, slope: float | None = None):
    """按库模板建一条围护原则（单一做法）；slope 非空时把放坡系数设为该值。"""
    from app.core.models import base as orm
    from app.core.models.models import PcpEnclosure

    session = orm.session()
    pe = PcpEnclosure(name=name, order_no=90 + len(project_io.enclosures()))
    session.add(pe)
    session.flush()
    project_io.new_enclosure_work(
        session, pe, project_io.component_library(), order_no=0, level_name=category
    )
    if slope is not None:
        for param in pe.works_sorted()[0].levels[0].components[0].params:
            if param.key == "A":
                param.value = f"放坡系数 1:X|{slope}"
    project_io.commit()
    return pe


def make_element(name: str, *, dn=600, depth="3", amount="120", pe_name=None):
    """建一条管材构件（默认 Ⅱ级混凝土管 DN600），返回构件 id。"""
    from app.viewmodels import unit_vm

    element = unit_vm.create_element(
        first_unit_id(),
        category=1,
        name=name,
        depth=depth,
        amount=amount,
        pipes=[("Ⅱ级混凝土管", dn, "1")],
        pe_name=pe_name,
        seed_atlas_defaults=True,
    )
    assert element is not None
    return element.id
