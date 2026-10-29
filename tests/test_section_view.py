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
        path=tmp_path / "断面工程.stn",
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


def test_lr_walk_layers_keeps_each_side_aligned() -> None:
    """左右放坡系数不同：每侧折线连续，槽顶半宽按本侧坡度累加（不取两侧平均）。"""
    from types import SimpleNamespace as NS

    from app.core.calc.tracer import dim
    from app.views.panels.section_view import _walk_layers_sided

    def level(height, slope, step_width=0.0):
        component = NS(params=[NS(key="A", value=f"放坡系数 1:X|{slope}")])
        return NS(h=height, step_width=step_width, components=[component])

    layers = [("a", dim(1.5), ""), ("b", dim(1.5), "")]
    left, right = _walk_layers_sided(
        [level(-1, 0.5)], [level(-1, 0.0)], layers, bottom=1.0, depth=3.0
    )
    for segments, slope in ((left, 0.5), (right, 0.0)):
        for previous, segment in zip(segments, segments[1:]):
            start = previous.bottom / 2 + previous.h_delta * previous.slope
            assert segment.bottom / 2 == pytest.approx(start)
        top_half = segments[-1].bottom / 2 + segments[-1].h_delta * segments[-1].slope
        assert top_half == pytest.approx(1.0 / 2 + 3.0 * slope)


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
    spec = NewProjectSpec(path=tmp_path / "无原则.stn", unit_names=["雨水工程"])
    project_io.new_project(spec)
    from app.viewmodels import unit_vm

    unit_id = project_io.units(project_io.segments()[0].id)[0].id
    element = unit_vm.create_element(unit_id, category=1, name="无原则管")
    unit_vm.update_element(element.id, pe_name="不存在的原则")
    view = _make_view(qapp, element.id)
    assert view._scene is None
    assert "原则" in view._hint
    assert orm.is_open()


def test_detail_reload_sentinel_zero_without_project(qapp) -> None:
    """未打开工程时的空明细重载（哨兵 id=0）不得触碰工作库。

    VM 的 ``load_unit(None)`` 发 ``detail_loaded(0, [], [], [])``——0 是
    “没有条目”的哨兵，不是真实 id；断面刷新必须把它与 None 同等对待，
    否则启动时（尚未打开工程）就抛 NoProjectOpenError。
    """
    assert not orm.is_open()
    from app.viewmodels.unit_vm import UnitViewModel
    from app.views.panels.unit_panel import UnitPanel

    panel = UnitPanel()  # __init__ 即走 _show_unit(None) → load_unit(None)
    panel._vm = UnitViewModel()
    panel._vm.detail_loaded.connect(panel._on_detail_loaded)
    panel._vm.load_unit(None)  # 空明细重载：哨兵 0
    panel._on_detail_loaded(0, [], [], [])  # 同一哨兵直接走处理器也不崩
    assert not orm.is_open()
