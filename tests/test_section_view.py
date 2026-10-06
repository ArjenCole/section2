"""断面示意图测试（M8）：场景构建的几何数据与旧版 mcPictureBox 语义一致。

所有用例都在 tmp_path 下建工程，不碰用户目录里的任何真实文件；
Qt 部分用离屏平台渲染，不弹窗口。
"""

from __future__ import annotations

import pytest

from app.core.models import base as orm
from app.services import project_io
from app.services.project_io import NewProjectSpec


@pytest.fixture()
def project_with_element(tmp_path):
    """一个带默认围护/地基原则的工程 + 一条 Dn1200 直埋混凝土管。"""
    spec = NewProjectSpec(
        path=tmp_path / "断面工程.stn2",
        project_name="断面工程",
        unit_names=["雨水工程"],
    )
    project_io.new_project(spec)
    from app.viewmodels import unit_vm

    unit_id = project_io.units(project_io.segments()[0].id)[0].id
    element = unit_vm.create_element(unit_id, category=1, name="雨水管 D1200")
    unit_vm.create_pipe(element.id, mat="Ⅱ级钢筋混凝土管", dn=1200)
    unit_vm.update_element(element.id, depth="2.5", amount="100")
    return element.id


@pytest.fixture()
def multi_pe_element(tmp_path):
    """多围护构件：引用两条放坡系数不同（1 与 0.5）的围护原则。"""
    from app.core.models import base as orm
    from app.core.models.models import MULTI_PE_TEXT
    from app.viewmodels import unit_vm

    spec = NewProjectSpec(path=tmp_path / "多围护断面.stn2", unit_names=["雨水工程"])
    project_io.new_project(spec)

    steep = project_io.create_enclosure("陡坡")
    level = steep.works_sorted()[0].levels[0]
    level.components[0].params[0].value = "放坡系数 1:X|0.5"
    project_io.commit()

    unit_id = project_io.units(project_io.segments()[0].id)[0].id
    element = unit_vm.create_element(unit_id, category=1, name="多围护管")
    unit_vm.create_pipe(element.id, mat="Ⅱ级钢筋混凝土管", dn=1200)
    unit_vm.update_element(element.id, depth="2.5", amount="100")
    unit_vm.update_element(element.id, pe_name=MULTI_PE_TEXT)
    assert unit_vm.add_principle_ref(element.id, "pe", "陡坡", 0.4) is not None
    orm.session().expire_all()
    return element.id


def _make_view(qapp, element_id):
    from app.views.panels.section_view import SectionView

    view = SectionView()
    view.resize(320, 420)
    view.set_element(element_id)
    return view


def test_trench_scene_geometry(qapp, project_with_element) -> None:
    """沟槽场景：分层回填段、总深与槽顶宽都来自计算引擎的同一套函数。"""
    from app.core.calc.engine import build_atlas_query, build_element_input, resolve_atlas
    from app.views.panels.section_view import _build_scene

    scene, hint = _build_scene(project_with_element, 320, 420)
    assert hint == ""
    assert scene is not None
    # 分层键自底向上：换填（无换填层时为 0）→ 垫层 → 坞膀下半/上半 → 管顶50 → 覆土
    keys = [segment.key for segment in scene.segments if segment.h_delta > 0]
    assert keys[0].startswith(("换填|", "垫层|"))
    assert any(key.startswith("垫层|") for key in keys)
    assert sum(key.startswith("回填|") for key in keys) >= 3
    assert keys[-1].startswith("回填|")
    # 总深 = 埋深 + (换填 + 壁厚 + 垫层)/1000，槽顶宽 > 槽底宽（放坡）
    assert scene.total_h > 2.5
    assert scene.top_width > 0
    assert 0 < scene.zoom <= 1.0
    # 图集参数文本与本体形状（外皮圆 + 内壁圆）
    assert scene.atlas_text.startswith("t=")
    kinds = [shape.kind for shape in scene.shapes]
    assert kinds.count("Ellipse") == 2


def test_view_renders_offscreen(qapp, project_with_element) -> None:
    """离屏渲染不崩，且选中清空后回到占位提示。"""
    view = _make_view(qapp, project_with_element)
    view.grab()  # 强制走一遍 paintEvent
    assert view._scene is not None
    view.set_element(None)
    view.grab()
    assert view._scene is None
    assert view._hint == "请选择构件条目"


def test_scene_without_principle(qapp, tmp_path) -> None:
    spec = NewProjectSpec(path=tmp_path / "无原则.stn2", unit_names=["雨水工程"])
    project_io.new_project(spec)
    from app.viewmodels import unit_vm

    unit_id = project_io.units(project_io.segments()[0].id)[0].id
    element = unit_vm.create_element(unit_id, category=1, name="无原则管")
    unit_vm.update_element(element.id, pe_name="不存在的原则")
    view = _make_view(qapp, element.id)
    assert view._scene is None
    assert "原则" in view._hint
    assert orm.is_open()


def test_multi_pe_left_right_per_principle(qapp, multi_pe_element) -> None:
    """多围护原则：左右两侧各按自己的围护原则放坡（旧版 PaintBackFilled L/R）。"""
    from app.views.panels.section_view import _build_scene

    scene, hint = _build_scene(multi_pe_element, 320, 420)
    assert hint == ""
    assert scene is not None
    # 默认：左侧第一条引用（放坡 1）、右侧第二条（放坡 0.5）
    assert {s.slope for s in scene.segments if s.h_delta > 0} == {1.0}
    assert {s.slope for s in scene.segments_right if s.h_delta > 0} == {0.5}
    assert scene.top_width > scene.top_width_right
    # zoom 由两侧较宽的一侧决定（旧版右画缩 zoom 后重画）
    width_avail, height_avail = 320 - 20, 420 - 60
    expected = min(
        1.0,
        width_avail / (scene.top_width * 1000.0),
        height_avail / (scene.total_h * 1000.0),
    )
    assert abs(scene.zoom - expected) < 1e-9

    # 下拉对调左右后镜像互换（旧版 CMBpicCtrlerLPE/RPE 联动）
    swapped, hint = _build_scene(
        multi_pe_element, 320, 420, left_name="陡坡", right_name="默认围护原则"
    )
    assert hint == ""
    assert {s.slope for s in swapped.segments if s.h_delta > 0} == {0.5}
    assert {s.slope for s in swapped.segments_right if s.h_delta > 0} == {1.0}
    assert swapped.top_width < swapped.top_width_right


def test_multi_pf_scene_uses_first_ref(qapp, tmp_path) -> None:
    """多地基原则构件：按第一条地基引用绘制（旧版 CMBpicCtrlerPF 默认第一条）。"""
    from app.core.models import base as orm
    from app.core.models.models import MULTI_PF_TEXT, FoundationReplacement
    from app.views.panels.section_view import _build_scene
    from app.viewmodels import unit_vm

    spec = NewProjectSpec(path=tmp_path / "多地基断面.stn2", unit_names=["雨水工程"])
    project_io.new_project(spec)
    filled = project_io.create_foundation("换填地基")
    orm.session().add(FoundationReplacement(foundation_id=filled.id, name="碎石", h=300.0))
    project_io.commit()

    unit_id = project_io.units(project_io.segments()[0].id)[0].id
    element = unit_vm.create_element(unit_id, category=1, name="多地基管")
    unit_vm.create_pipe(element.id, mat="Ⅱ级钢筋混凝土管", dn=1200)
    unit_vm.update_element(element.id, depth="2.5", amount="100")
    unit_vm.update_element(element.id, pf_name=MULTI_PF_TEXT)
    assert unit_vm.add_principle_ref(element.id, "pf", "换填地基", 0.4) is not None

    # 引用顺序 = [默认地基处理原则, 换填地基]，绘制取第一条（无换填层）
    scene, hint = _build_scene(element.id, 320, 420)
    assert hint == ""
    assert scene is not None
    keys = [segment.key for segment in scene.segments if segment.h_delta > 0]
    assert not any(key.startswith("换填|") for key in keys)

    # 地基下拉选中“换填地基”→ 断面出现 300mm 换填层
    scene, hint = _build_scene(element.id, 320, 420, pf_name="换填地基")
    assert hint == ""
    keys = [segment.key for segment in scene.segments if segment.h_delta > 0]
    assert keys[0].startswith("换填|碎石|")


def test_section_panel_selector(qapp, multi_pe_element) -> None:
    """多围护构件显示 左/右围护、地基处理 选择行（旧版 PNLpicCtrler），默认左1右2。"""
    from app.views.panels.section_view import SectionPanel

    panel = SectionPanel()
    panel.resize(320, 460)
    panel.set_element(multi_pe_element)
    assert not panel._selector.isHidden()
    assert [panel._pe_left_combo.itemText(i) for i in range(panel._pe_left_combo.count())] == [
        "默认围护原则",
        "陡坡",
    ]
    assert panel._pe_left_combo.currentText() == "默认围护原则"
    assert panel._pe_right_combo.currentText() == "陡坡"
    assert panel._pf_combo.currentText() == "默认地基处理原则"
    assert panel._canvas._scene is not None

    # 切换下拉 → 画布按新组合重绘（左陡右缓）
    panel._pe_left_combo.setCurrentIndex(1)
    panel._pe_right_combo.setCurrentIndex(0)
    scene = panel._canvas._scene
    assert {s.slope for s in scene.segments if s.h_delta > 0} == {0.5}
    assert {s.slope for s in scene.segments_right if s.h_delta > 0} == {1.0}

    # 单原则构件：隐藏选择行
    from app.viewmodels import unit_vm

    unit_vm.update_element(multi_pe_element, pe_name="默认围护原则")
    panel.set_element(multi_pe_element)
    assert panel._selector.isHidden()
