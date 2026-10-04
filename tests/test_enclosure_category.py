"""围护做法“围护类型”切换回归测试（旧版 FormPE ColEclsCat / mcEnclosure.setECpnt）。

复刻语义：切换做法的围护类型时清空原有分级、按构件库模板重建一级
（多级围护取库第一项）。构件库 Ei 里只有 放坡/喷锚护坡 的 A 参数是
“放坡系数 1:X”，钢板桩/横列板/钻孔灌注桩/SMW工法桩等支护类型 A 非
放坡系数 → 放坡系数按 0 处理，沟槽为直壁并走支护的 F/Z 公式出围护量。
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _closed_project():
    from app.services import project_io

    project_io.close_project()
    yield
    project_io.close_project()


@pytest.fixture()
def project(tmp_path):
    from app.services import project_io
    from app.services.project_io import NewProjectSpec

    path = tmp_path / "ecls.stn2"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程"]))
    return path


def _enclosure():
    from app.services import project_io

    return project_io.enclosures()[0]


# --------------------------------------------------------------------------- #
# 服务层：set_work_category（旧版 setECpnt）
# --------------------------------------------------------------------------- #
def test_set_work_category_rebuilds_level_from_template(project) -> None:
    from app.core.calc.groove import level_slope
    from app.core.models import base as orm
    from app.core.models.models import MULTI_LEVEL_TEXT, EnclosureWork
    from app.services import project_io

    library = project_io.component_library()
    session = orm.session()
    work = _enclosure().works_sorted()[0]

    project_io.set_work_category(session, work, library, "钢板桩")
    project_io.commit()
    work = session.get(EnclosureWork, work.id)
    assert work.cpnt_cat == "钢板桩"
    assert len(work.levels) == 1
    level = work.levels[0]
    assert level.name == "钢板桩"
    assert (level.h, level.step_width) == (-1.0, 1.0)  # 均分高度、平台宽 1
    params = {param.key: param.value for param in level.components[0].params}
    assert params["A"] == "单桩宽度 mm|400"  # 模板默认参数一并带入
    assert level_slope(level) == 0.0  # 非放坡类型 → 直壁

    project_io.set_work_category(session, work, library, MULTI_LEVEL_TEXT)
    project_io.commit()
    work = session.get(EnclosureWork, work.id)
    assert work.cpnt_cat == MULTI_LEVEL_TEXT
    # 多级围护：一级取库第一项（旧版 Ecpnti.First().Key）
    assert len(work.levels) == 1 and work.levels[0].name == "放坡"
    assert level_slope(work.levels[0]) == 1.0

    project_io.set_work_category(session, work, library, "放坡")
    project_io.commit()
    work = session.get(EnclosureWork, work.id)
    assert work.cpnt_cat == "放坡"
    assert level_slope(work.levels[0]) == 1.0


def test_sloped_vs_vertical_dig_and_enclosure_quantities(project) -> None:
    """钢板桩（直壁）与放坡（梯形）的挖方算式与围护量对比。"""
    from app.core.calc.engine import compute_from_orm
    from app.core.models import base as orm
    from app.core.models.models import CATEGORY_BURIED
    from app.services import project_io
    from app.viewmodels import unit_vm

    session = orm.session()
    library = project_io.component_library()
    unit_id = project_io.units(project_io.segments()[0].id)[0].id
    element = unit_vm.create_element(
        unit_id, category=CATEGORY_BURIED, name="", depth="2.5", amount="10",
        pipes=[("Ⅰ级混凝土管", 600, "1")],
    )
    assert element is not None

    # 放坡（默认做法）：挖方算式含放坡项，无支护围护量
    result = compute_from_orm(element, session)
    assert result is not None
    dig = next(q for q in result.items() if q.key.startswith("开挖|"))
    assert "2×" in dig.expression and "+" in dig.expression  # (B+B+2×H×放坡系数)×H/2
    assert not [key for key in result.keys() if key.startswith("围护|")]

    # 切成钢板桩：挖方为直壁矩形算式，出现围护/支撑量；断面图两侧应为直壁
    project_io.set_work_category(
        session, _enclosure().works_sorted()[0], library, "钢板桩"
    )
    project_io.commit()
    result = compute_from_orm(element, session)
    assert result is not None
    dig = next(q for q in result.items() if q.key.startswith("开挖|"))
    assert "+" not in dig.expression  # 放坡系数 0 → B×H
    assert any(key.startswith("围护|") for key in result.keys())
    assert any(key.startswith("支撑|") for key in result.keys())

    from app.views.panels.section_view import _build_scene

    scene, hint = _build_scene(element.id, 320, 420)
    assert scene is not None and hint == ""
    assert scene.top_width == pytest.approx(
        scene.segments[0].bottom + scene.segments[0].h_delta * 0.0, abs=1e-9
    )
    assert scene.top_width_right == pytest.approx(scene.top_width, abs=1e-9)


# --------------------------------------------------------------------------- #
# 原则编辑对话框（FormPE）：围护类型下拉切换
# --------------------------------------------------------------------------- #
def test_enclosure_dialog_switch_category_rebuilds(qapp, project) -> None:
    from app.core.models.models import MULTI_LEVEL_TEXT
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    dialog = EnclosureEditDialog(_enclosure().id)
    table = dialog._work_table
    try:
        work = dialog._enclosure().works_sorted()[0]
        dialog._on_work_category(work, "钢板桩")
        work = dialog._enclosure().works_sorted()[0]
        assert work.cpnt_cat == "钢板桩"
        assert work.levels[0].components[0].name == "钢板桩"
        # 围护类型下拉与描述列同步刷新（旧版 FlashdGVPERow）
        assert table.cellWidget(0, 2).currentText() == "钢板桩"
        assert table.item(0, 3).text() == "拉森钢板桩 支护"

        dialog._on_work_category(work, MULTI_LEVEL_TEXT)
        work = dialog._enclosure().works_sorted()[0]
        assert work.cpnt_cat == MULTI_LEVEL_TEXT
        assert table.item(0, 3).text() == MULTI_LEVEL_TEXT
        assert work.levels[0].name == "放坡"
    finally:
        dialog.close()


# --------------------------------------------------------------------------- #
# 做法编辑对话框（FormEcls）：分级增删、级类型切换、均分只读
# --------------------------------------------------------------------------- #
def test_enclosure_work_dialog_level_operations(qapp, project, monkeypatch) -> None:
    from app.views.dialogs.principle_dialogs import EnclosureWorkDialog

    # 全删被拦的提示框在 offscreen 下会阻塞，替换为记录调用
    shown: list[str] = []
    monkeypatch.setattr(
        "app.views.dialogs.principle_dialogs.FramelessMessageBox.information",
        lambda *_args, **_kwargs: shown.append("blocked"),
    )

    dialog = EnclosureWorkDialog(_enclosure().works_sorted()[0])
    try:
        assert dialog._level_table.rowCount() == 1
        dialog._add_level()
        assert dialog._level_table.rowCount() == 2  # 新级立即可见
        h_item = dialog._level_table.item(1, 1)
        assert h_item.text() == "均分高度"
        assert not (h_item.flags() & Qt.ItemFlag.ItemIsEditable)  # 均分级高只读

        # 换级类型 → 构件按库模板重建（旧版 tmEC.Cpnt = Ecpnti[value]）
        dialog._on_level_category(dialog._levels()[0], "钢板桩")
        level = dialog._levels()[0]
        assert level.name == "钢板桩"
        assert level.components[0].name == "钢板桩"
        assert dialog._level_table.item(0, 4).text() == "拉森钢板桩 支护"

        # Insert 键插到当前行之前，order_no 重排
        dialog._level_table.setCurrentCell(1, 0)
        dialog._level_table.insert_requested.emit()
        assert dialog._level_table.rowCount() == 3
        assert [item.order_no for item in dialog._levels()] == [0, 1, 2]

        # 全删被拦（至少一级），删除部分行后 order_no 归一
        dialog._level_table.selectAll()
        dialog._delete_levels()
        assert shown == ["blocked"]
        assert dialog._level_table.rowCount() == 3
        dialog._level_table.setCurrentCell(1, 0)
        dialog._delete_levels()
        assert dialog._level_table.rowCount() == 2
        assert [item.order_no for item in dialog._levels()] == [0, 1]

        # 确定保存（min_depth 写回 + order_no 归一）不再报错
        dialog._min_depth.setText("1.5")
        dialog._accept()
        assert dialog.saved
    finally:
        dialog.close()
