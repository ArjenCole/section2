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


def test_stale_detail_id_after_project_close(qapp, project_with_element) -> None:
    """回归（2026-10-29 08:29）：工程关闭后延迟到达的旧 id 不得再查工作库。

    现场栈：``_on_detail_loaded → _refresh_section_for → set_element →
    _build_scene → orm.session() → NoProjectOpenError``。旧 id 不是 None，
    必须在进断面构建前被拦住。
    """
    from app.views.panels.section_view import _build_group_scene, _build_scene
    from app.views.panels.unit_panel import UnitPanel

    stale_id = project_with_element
    project_io.close_project()
    assert not orm.is_open()

    panel = UnitPanel()
    # 延迟信号直接打到处理器：必须静默忽略，不能抛
    panel._on_detail_loaded(stale_id, [], [], [])
    panel._refresh_section_for(stale_id)
    assert panel._section_view._element_id is None

    # 兜底：即使有人绕过面板直接构建场景，也只能返回提示
    scene, hint = _build_scene(stale_id, 320, 420)
    assert scene is None and hint == "尚未打开工程"
    scene, hint = _build_group_scene(1, 320, 420)
    assert scene is None and hint == "尚未打开工程"


# --------------------------------------------------------------------------- #
# 分层递推的进度保护（2026-10-29：分级高度异常时旧版 while True 会卡死）
# --------------------------------------------------------------------------- #
def _walk_level(height, slope=0.5, step_width=0.0):
    from types import SimpleNamespace as NS

    component = NS(params=[NS(key="A", value=f"放坡系数 1:X|{slope}")])
    return NS(h=height, step_width=step_width, components=[component])


def _walk_layers():
    from app.views.panels import section_view

    return section_view._walk_layers


def test_walk_layers_normal_has_no_problem() -> None:
    from app.core.calc.tracer import dim

    problem: list[str] = []
    segments = _walk_layers()(
        [_walk_level(-1)],
        [("a", dim(1.5), ""), ("b", dim(1.5), "")],
        bottom=1.0,
        depth=3.0,
        problem=problem,
    )
    assert problem == []
    assert segments


def test_walk_layers_stops_on_zero_height_level() -> None:
    """固定级高为 0：递推无法前进，必须立即停下（旧版会原地死循环）。"""
    from app.core.calc.tracer import dim

    problem: list[str] = []
    segments = _walk_layers()(
        [_walk_level(0.0)],
        [("a", dim(1.5), "")],
        bottom=1.0,
        depth=3.0,
        problem=problem,
    )
    assert problem and "围护分级高度异常" in problem[0]
    assert segments == []


def test_walk_layers_stops_on_non_monotonic_levels() -> None:
    """固定级高之和大于槽深后出现非单调标高：不得死循环，也不得画出负段。"""
    from app.core.calc.tracer import dim

    problem: list[str] = []
    segments = _walk_layers()(
        [_walk_level(4.0), _walk_level(-1), _walk_level(2.0)],
        [("a", dim(1.5), ""), ("b", dim(1.5), "")],
        bottom=1.0,
        depth=3.0,
        problem=problem,
    )
    assert problem and "围护分级高度异常" in problem[0]
    assert all(segment.h_delta >= 0 for segment in segments)


def test_walk_layers_stops_at_iteration_cap(monkeypatch) -> None:
    from app.core.calc.tracer import dim
    from app.views.panels import section_view

    monkeypatch.setattr(section_view, "_MAX_WALK_STEPS", 1)
    problem: list[str] = []
    section_view._walk_layers(
        [_walk_level(1.0), _walk_level(-1)],
        [("a", dim(1.5), ""), ("b", dim(1.5), "")],
        bottom=1.0,
        depth=3.0,
        problem=problem,
    )
    assert problem and "步数异常" in problem[0]


def test_walk_layers_sided_stops_on_zero_height_level() -> None:
    from app.core.calc.tracer import dim
    from app.views.panels.section_view import _walk_layers_sided

    problem: list[str] = []
    left, right = _walk_layers_sided(
        [_walk_level(0.0)],
        [_walk_level(-1)],
        [("a", dim(1.5), "")],
        bottom=1.0,
        depth=3.0,
        problem=problem,
    )
    assert problem and "围护分级高度异常" in problem[0]
    assert left == [] and right == []


def test_build_scene_reports_walk_problem(tmp_path) -> None:
    """围护分级高度异常时，断面构建返回提示而不是卡死。"""
    spec = NewProjectSpec(path=tmp_path / "异常分级.stn", unit_names=["雨水工程"])
    project_io.new_project(spec)
    from app.core.models import base as orm
    from app.core.models.models import PcpEnclosure
    from app.views.panels.section_view import _build_scene
    from app.viewmodels import unit_vm

    session = orm.session()
    pe = PcpEnclosure(name="零级高原则", order_no=90)
    session.add(pe)
    session.flush()
    project_io.new_enclosure_work(
        session, pe, project_io.component_library(), order_no=0, level_name="钢板桩"
    )
    project_io.commit()
    # 把唯一一级的固定级高改成 0：递推无法从槽底前进
    pe.works_sorted()[0].levels[0].h = 0.0
    project_io.commit()

    unit_id = project_io.units(project_io.segments()[0].id)[0].id
    element = unit_vm.create_element(
        unit_id, category=1, name="异常分级管", depth="3", amount="100", pe_name=pe.name
    )
    unit_vm.create_pipe(element.id, mat="Ⅱ级钢筋混凝土管", dn=1200)
    scene, hint = _build_scene(element.id, 320, 420)
    assert scene is None
    assert "围护分级高度异常" in hint


def test_group_left_slope_platform_opens_outward(tmp_path) -> None:
    """回归：合槽最左侧边坡在切级平台处应向外阔出一个平台后再向上放坡。

    做法取两级均分（每级平台宽 0.5m、上段 1:0.3 / 下段 1:0.5）。左边坡折线
    自地面向下时必须始终向内收（外扩宽单调减小），平台处同样是“向下收进一
    个平台”。旧实现按深度**升序稳定排序**，把切级处同一深度的下段坡顶点
    排在上段坡底点之前，结果平台处反而向外跳、折线呈 Z 形。
    """
    from app.core.models import base as orm
    from app.core.models.models import MULTI_LEVEL_TEXT, PcpEnclosure
    from app.services import principle_edit
    from app.viewmodels import unit_vm
    from app.views.panels.section_view import _build_group_scene

    spec = NewProjectSpec(path=tmp_path / "合槽平台.stn", unit_names=["雨水工程"])
    project_io.new_project(spec)
    unit_id = project_io.units(project_io.segments()[0].id)[0].id

    # 两级放坡做法（多级围护），均分槽深 + 平台宽 0.5m
    pe = PcpEnclosure(name="两级放坡平台", order_no=90)
    orm.session().add(pe)
    project_io.commit()
    principle_edit.apply_enclosure_works(
        pe.id,
        [
            {
                "min_depth": 0,
                "cpnt_cat": MULTI_LEVEL_TEXT,
                "stop_type": "无",
                "levels": [
                    {"level_type": "放坡", "h": -1, "step_width": 0.5},
                    {"level_type": "放坡", "h": -1, "step_width": 0.5},
                ],
            }
        ],
    )
    # 上段（靠地面）1:0.3、下段 1:0.5，平台跳变处外扩宽差更明显
    for level, slope in zip(
        orm.session().get(PcpEnclosure, pe.id).works_sorted()[0].levels, (0.3, 0.5)
    ):
        for param in level.components[0].params:
            if param.key == "A":
                param.value = f"放坡系数 1:X|{slope}"
    project_io.commit()

    e1 = unit_vm.create_element(
        unit_id, category=1, name="左管", depth="3", amount="100",
        pipes=[("Ⅱ级混凝土管", 600, "1")], pe_name="两级放坡平台",
        seed_atlas_defaults=True,
    )
    e2 = unit_vm.create_element(
        unit_id, category=1, name="右管", depth="3", amount="100",
        pipes=[("Ⅱ级混凝土管", 600, "1")], seed_atlas_defaults=True,
    )
    group, error = unit_vm.create_trench_group([e1.id, e2.id])
    assert group is not None and error is None

    scene, hint = _build_group_scene(group.id, 640, 480)
    assert hint == "" and scene is not None and scene.outline
    outline = scene.outline
    # 左边坡 = 首个到达最深槽底的折点之前的部分（其后为槽底 / 右边坡）
    y_min = min(y for _x, y in outline)
    end = next(index for index, (_x, y) in enumerate(outline) if abs(y - y_min) <= 1e-9)
    left = outline[:end]
    assert len(left) >= 3
    # 确实存在切级平台（同一深度两个点），否则本用例就测不到该回归
    assert any(
        abs(left[i][1] - left[i + 1][1]) <= 1e-9 for i in range(len(left) - 1)
    ), left
    runs = [-x for x, _y in left]
    for previous, current in zip(runs, runs[1:]):
        assert current <= previous + 1e-9, f"左侧边坡在平台处向外跳变（Z 形）：{runs}"


def _group_pair_fixture(tmp_path, name: str, depth2: str = "4", dn2: int = 800):
    """双管合槽（浅 3m dn600 + 深/异径右管），返回 (group, e1, e2)。"""
    from app.viewmodels import unit_vm

    spec = NewProjectSpec(path=tmp_path / f"{name}.stn", unit_names=["雨水工程"])
    project_io.new_project(spec)
    unit_id = project_io.units(project_io.segments()[0].id)[0].id
    e1 = unit_vm.create_element(
        unit_id, category=1, name="浅管", depth="3", amount="100",
        pipes=[("Ⅱ级混凝土管", 600, "1")], seed_atlas_defaults=True,
    )
    e2 = unit_vm.create_element(
        unit_id, category=1, name="右管", depth=depth2, amount="100",
        pipes=[("Ⅱ级混凝土管", dn2, "1")], seed_atlas_defaults=True,
    )
    group, error = unit_vm.create_trench_group([e1.id, e2.id])
    assert group is not None and error is None, error
    return group, e1, e2


def test_group_unified_layer_lines_span_trench(tmp_path) -> None:
    """统一回填标高：每条统筹界面画一条贯通整槽的水平线。

    统筹界面（手算 oracle = 各构件层顶标高逐角色取最浅）与独立口径的
    "构件边界之间" 分层线不同：统一口径下每条线横跨轮廓在该标高的全部宽度。
    """
    from app.core.calc.groove import layer_roles
    from app.core.calc.trench_group import _member_layers, _resolve_member
    from app.viewmodels import unit_vm
    from app.views.panels.section_view import _build_group_scene

    group, _e1, _e2 = _group_pair_fixture(tmp_path, "统一回填断面")
    session = orm.session()

    def scene_of(mode):
        unit_vm.update_group(group.id, backfill_mode=mode)
        scene, hint = _build_group_scene(group.id, 640, 480)
        assert hint == "" and scene is not None and scene.outline
        return scene

    independent = scene_of("独立回填标高")
    unified = scene_of("统一回填标高")

    # 手算统筹界面（地面以下深度，逐角色取最浅）
    best: dict[tuple[str, int], float] = {}
    for element in sorted(group.members, key=lambda item: (item.order_no, item.id)):
        member, _error = _resolve_member(session, element)
        cum = 0.0
        layers = _member_layers(member)
        for (base, occurrence), (_key, layer, _note) in zip(layer_roles(layers), layers):
            cum += layer.v
            if layer.v <= 0:
                continue
            role = (base, occurrence)
            elevation = member.depth.v - cum
            if role not in best or elevation < best[role] - 1e-9:
                best[role] = elevation
    h_max = max(member.depth.v for member in (_resolve_member(session, element)[0] for element in group.members))
    expected_ys = sorted(
        round(h_max - value, 9)
        for value in best.values()
        if 1e-9 < value < h_max - 1e-9
    )
    actual_ys = sorted({round(line[1], 9) for line in unified.layer_lines})
    assert actual_ys == expected_ys
    # 每条线水平，且跨度 >= 独立口径中任意一条线（贯通整槽）
    assert all(abs(line[3] - line[1]) <= 1e-9 for line in unified.layer_lines)
    assert all(abs(line[3] - line[1]) <= 1e-9 for line in independent.layer_lines)
    assert unified.layer_lines
    assert independent.layer_lines
    widest_unified = max(line[2] - line[0] for line in unified.layer_lines)
    widest_independent = max(line[2] - line[0] for line in independent.layer_lines)
    assert widest_unified > widest_independent


def test_group_center_split_wall_at_center_midpoint(tmp_path) -> None:
    """管中心分隔：虚拟分界墙移到两构件中心连线的中点，并下探到较深槽底。"""
    from app.viewmodels import unit_vm
    from app.views.panels.section_view import _build_group_scene

    group, e1, e2 = _group_pair_fixture(tmp_path, "中心分界断面", depth2="3", dn2=1000)
    # 右管更深（壁厚差）且共享侧内坡 1:0.5，几何完全确定
    slope_pe_name = None
    from app.core.models.models import PcpEnclosure
    from app.services import principle_edit

    pe = PcpEnclosure(name="断面内坡0.5", order_no=95)
    orm.session().add(pe)
    project_io.commit()
    principle_edit.apply_enclosure_works(
        pe.id,
        [
            {
                "min_depth": 0,
                "cpnt_cat": "放坡",
                "stop_type": "无",
                "levels": [{"level_type": "放坡", "h": -1, "step_width": 0.0}],
            }
        ],
    )
    for param in orm.session().get(PcpEnclosure, pe.id).works_sorted()[0].levels[0].components[0].params:
        if param.key == "A":
            param.value = "放坡系数 1:X|0.5"
    project_io.commit()
    slope_pe_name = pe.name
    unit_vm.update_element(e2.id, pe_left_name=slope_pe_name)

    def scene_of(split_mode):
        unit_vm.update_group(group.id, split_mode=split_mode)
        scene, hint = _build_group_scene(group.id, 640, 480)
        assert hint == "" and scene is not None
        return scene

    scene_slope = scene_of("起坡点分割")
    scene_center = scene_of("管中心分隔")
    assert len(scene_slope.dashed_lines) == 1
    assert len(scene_center.dashed_lines) == 1
    wall_slope = scene_slope.dashed_lines[0]
    wall_center = scene_center.dashed_lines[0]

    # 手算平面几何（自槽左缘起算）：起坡点分界 = 浅管工作面外缘；中点分界 = 两中心中点
    from sqlalchemy import select

    from app.core.calc.engine import (
        atlas_dims,
        build_atlas_query,
        build_element_input,
        workwidth_of,
    )
    from app.core.calc.measures import foundation_thickness as fd
    from app.core.models.models import (
        Element,
        PcpFoundation,
        PcpPrecipitation,
        PcpWidth,
    )
    from app.services.atlas import resolve_atlas

    session = orm.session()
    geometry = []
    for element_id in (e1.id, e2.id):
        element = session.get(Element, element_id)
        pw = session.scalars(select(PcpWidth).where(PcpWidth.name == element.pw_name)).first()
        pf = session.scalars(select(PcpFoundation).where(PcpFoundation.name == element.pf_name)).first()
        pp = session.scalars(select(PcpPrecipitation).where(PcpPrecipitation.name == element.pp_name)).first()
        info = build_element_input(element, None, pf, pp=pp, pw=pw)
        at = resolve_atlas(build_atlas_query(info, pf, pw))
        ad = atlas_dims(info, at)
        geometry.append(
            {
                "b": (info.size_b + (ad.t * 2 + ad.a * 2) / 1000).v,
                "h": (info.depth + (fd(pf).v + ad.t + ad.c1) / 1000).v,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    assert g2["h"] > g1["h"] + 1e-9  # dn1000 壁厚更大 → 右管更深
    run = (g2["h"] - g1["h"]) * 0.5
    wall_x = g1["ww"] + g1["b"] + g1["ww"]  # 起坡点分界（坡顶）
    base_left_2 = wall_x + run + g2["ww"]
    c1 = g1["ww"] + g1["b"] / 2
    c2 = base_left_2 + g2["b"] / 2
    half = (wall_x + run + g2["ww"] + g2["b"] + g2["ww"]) / 2.0

    assert wall_slope[0] == pytest.approx(wall_x - half, rel=1e-9)
    assert wall_center[0] == pytest.approx((c1 + c2) / 2 - half, rel=1e-9)
    assert wall_center[0] != pytest.approx(wall_slope[0])
    # 管中心分隔的分界墙下探到较深槽底；起坡点分界止于浅槽底
    assert wall_slope[1] == pytest.approx(max(scene_slope.total_h - g1["h"], 0.0), abs=1e-9)
    assert wall_center[1] == pytest.approx(max(scene_center.total_h - g2["h"], 0.0), abs=1e-9)
    assert wall_center[3] == pytest.approx(scene_center.total_h, abs=1e-9)
