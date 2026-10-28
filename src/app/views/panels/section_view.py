"""断面示意图（复刻旧版 mcPictureBox，M8）。

几何计算直接复用 M4 计算引擎的同一套函数（backfill_layers / split_h_by_step /
level_slope / groove_width），保证图上的沟槽形状与工程量公式完全一致。

绘制约定与旧版 1.0 一致：
- 黑底、青色线条；管体断面黄描边（圆）、洋红描边（矩形），内部黑填充用于挖空；
- 坐标原点在画布底边中点，Y 轴向上；左侧用构件的围护原则、右侧镜像
  （旧版 PaintBackFilled(LmPE,1)/(RmPE,-1)；多围护原则已取消，两侧同原则）；
- 自适应缩放 zoom（mm→px，只缩小不放大，上限 1）；
- 左下角输出图集参数 ``t= a= C1= C2=``。

`SectionPanel` = 断面画布容器（旧版多原则时的 PNLpicCtrler 选择行已随功能取消）。

旧版 PaintBackFilled 的逐层递推（本模块 ``_walk_layers``）：
从槽底起按"换填→垫层→坞膀下半→坞膀上半→管顶50cm→覆土"逐层向上，
每段底宽按 高度增量×放坡系数×2 外扩，跨围护分级时外扩平台宽度。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from sqlalchemy import select

from app.core.models import base as orm
from app.core.models.models import (
    CATEGORY_BURIED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_ENCASED,
    CATEGORY_GALLERY,
    CATEGORY_JACKING,
    CATEGORY_PULLING,
    CATEGORY_STRUCTURE,
    LR_PE_TEXT,
    Element,
    PcpEnclosure,
    PcpFoundation,
    PcpPrecipitation,
    PcpWidth,
    TrenchGroup,
)
from app.core.calc import groove
from app.core.calc.engine import (
    ElementInput,
    _resolve_lr_enclosures,
    atlas_dims,
    build_atlas_query,
    build_element_input,
    choice_work,
    cushion_thickness,
    foundation_thickness,
    is_concrete_pipe,
    replace,
    workwidth_of,
)
from app.core.calc.groove import level_slope
from app.core.calc.tracer import dim, scale_sum
from app.services.atlas import resolve_atlas

_MARGIN = 10  # 画布左右留白 px（旧版 10*2）
_BOTTOM_GAP = 10  # 底边留白 px
_TOP_GAP = 50  # 顶部留白 px（旧版 Height-10-50）

_COLOR_BG = QColor("black")
_COLOR_LINE = QColor("cyan")
_COLOR_TEXT = QColor("yellow")
_COLOR_ELLIPSE = QColor("yellow")
_COLOR_RECT = QColor("#FF00FF")


@dataclass
class _Segment:
    """回填的一个梯形段（旧版 tBHSS 项，单位 m）。"""

    key: str
    bottom: float  # 段底宽 m
    h_current: float  # 段底标高 m（自槽底起）
    h_delta: float  # 段高 m
    slope: float  # 放坡系数
    continues: bool = False  # 与上一段同材料：从上一段顶边接续画线


@dataclass
class _Shape:
    """管体本体图形（旧版 OntologyShape 项，单位 mm，y 为底边标高）。"""

    kind: str  # "Ellipse" / "Rectangle"
    x: float
    y: float
    w: float
    h: float


@dataclass
class _Scene:
    """一次断面绘制的全部数据。

    ``segments_r`` 非空 = 左右分设：左侧用 ``segments``、右侧用 ``segments_r``
    各画各的折线（对称断面仍是镜像画法）；``outline`` 非空 = 合槽断面：
    一条完整折线（x 相对槽中心、右正，y 自槽底向上，单位 m），此时忽略
    segments / top_width。
    """

    segments: list[_Segment] = field(default_factory=list)
    total_h: float = 0.0  # 沟槽总深 m
    top_width: float = 0.0  # 槽顶总宽 m（左侧地面线起点）
    zoom: float = 1.0
    shapes: list[_Shape] = field(default_factory=list)
    shift: float = 0.0  # 本体零点相对槽底的抬升 mm（旧版 TiA + C1 - mC1）
    atlas_text: str = ""
    segments_r: list[_Segment] | None = None
    outline: list[tuple[float, float]] | None = None
    top_width_r: float = 0.0  # 右侧地面线起点（左右分设 / 合槽用）


class SectionView(QWidget):
    """当前选中构件条目的沟槽断面示意图（旧版 mcPictureBox）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._element_id: int | None = None
        self._group_id: int | None = None
        self._hint = "请选择构件条目"
        self._scene: _Scene | None = None
        self.setMinimumSize(180, 160)

    # ------------------------------------------------------------------ 对外
    def set_element(self, element_id: int | None) -> None:
        """切换要绘制断面的构件条目（None 清空）。"""
        self._element_id = element_id
        self._group_id = None
        self._refresh()

    def set_group(self, group_id: int | None) -> None:
        """合槽父行选中：画整槽全景断面（成员各自的左右分设也看得到）。"""
        self._element_id = None
        self._group_id = group_id
        self._refresh()

    def show_multi(self) -> None:
        """主表格选中多行：不绘制具体断面，居中显示占位提示。"""
        self._element_id = None
        self._group_id = None
        self._scene = None
        self._hint = "*多种断面"
        self.update()

    def refresh(self) -> None:
        """构件数据变化后重算重绘。"""
        self._refresh()

    def _refresh(self) -> None:
        if self._group_id is not None:
            self._scene, self._hint = _build_group_scene(self._group_id, self.width(), self.height())
        else:
            self._scene, self._hint = _build_scene(self._element_id, self.width(), self.height())
        self.update()

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.fillRect(self.rect(), _COLOR_BG)
        if self._scene is None:
            painter.setPen(QPen(QColor("gray")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._hint)
            return
        scene = self._scene
        center_x = self.width() / 2.0
        origin_y = self.height() - _BOTTOM_GAP

        pen = QPen(_COLOR_LINE, 1)
        painter.setPen(pen)
        if scene.outline is not None:
            # 合槽断面：一条完整折线（x 相对槽中心右正、y 自槽底向上，单位 m）
            previous: tuple[float, float] | None = None
            for value_x, value_y in scene.outline:
                x = center_x + value_x * 1000.0 * scene.zoom
                y = origin_y - value_y * 1000.0 * scene.zoom
                if previous is not None:
                    painter.drawLine(int(previous[0]), int(previous[1]), int(x), int(y))
                previous = (x, y)
            if previous is not None and scene.outline:
                # 地面线：折线首尾（地面高程）向两侧画到画布边缘
                top_y = int(origin_y - scene.total_h * 1000.0 * scene.zoom)
                first_x = int(center_x + scene.outline[0][0] * 1000.0 * scene.zoom)
                last_x = int(previous[0])
                painter.drawLine(0, top_y, first_x, top_y)
                painter.drawLine(last_x, top_y, int(self.width()), top_y)
        else:
            # 单管断面：左侧 +1 用左做法、右侧 -1 用右做法（左右分设各画各的
            # 折线；对称断面 segments_r 为空仍是镜像）
            for side in (1, -1):
                segments = scene.segments if side == 1 or scene.segments_r is None else scene.segments_r
                top_width = (
                    scene.top_width if side == 1 else (scene.top_width_r or scene.top_width)
                )
                previous: _Segment | None = None
                for segment in segments:
                    if segment.h_delta <= 0:
                        previous = segment
                        continue
                    points_m = []
                    if segment.continues and previous is not None:
                        start_b = previous.bottom + previous.h_delta * previous.slope * 2
                        points_m.append((start_b / 2.0, segment.h_current))
                    else:
                        points_m.append((0.0, segment.h_current))
                    points_m.append((segment.bottom / 2.0, segment.h_current))
                    points_m.append(((segment.bottom + segment.h_delta * segment.slope * 2) / 2.0,
                                     segment.h_current + segment.h_delta))
                    self._draw_side_line(painter, points_m, side, center_x, origin_y, scene.zoom)
                    previous = segment
                # 地面线：本侧槽顶边一直到画布边缘（旧版终点是画框半宽，按像素计）
                edge_x = center_x - side * (self.width() / 2.0)
                top_y = origin_y - scene.total_h * 1000.0 * scene.zoom
                start_x = center_x - top_width / 2.0 * 1000.0 * scene.zoom * side
                painter.drawLine(int(start_x), int(top_y), int(edge_x), int(top_y))

        # 管体本体（画一次，居中；黑填充挖空 + 描边，与旧版 FillRectangle/FillEllipse 一致）
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for shape in scene.shapes:
            rect = self._shape_rect(shape, scene, center_x, origin_y)
            if shape.kind == "Ellipse":
                painter.setPen(QPen(_COLOR_ELLIPSE, 1))
                painter.setBrush(_COLOR_BG)
                painter.drawEllipse(rect)
            else:
                painter.setPen(QPen(_COLOR_RECT, 1))
                painter.setBrush(_COLOR_BG)
                painter.drawRect(rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # 图集参数输出（旧版 OnPaint 左下角黄字；面板较高时固定在左上角更清晰）
        painter.setPen(QPen(_COLOR_TEXT, 1))
        painter.drawText(4, 14, scene.atlas_text)

    def _draw_side_line(
        self, painter: QPainter, points_m: list[tuple[float, float]], side: int,
        center_x: float, origin_y: float, zoom: float,
    ) -> None:
        """把以米为单位的折线按 side 镜像画到画布（旧版旋转坐标系下的 DrawLines）。"""
        previous_x: float | None = None
        previous_y = 0.0
        for value_x, value_y in points_m:
            x = center_x - value_x * 1000.0 * zoom * side
            y = origin_y - value_y * 1000.0 * zoom
            if previous_x is not None:
                painter.drawLine(int(previous_x), int(previous_y), int(x), int(y))
            previous_x, previous_y = x, y

    def _shape_rect(self, shape: _Shape, scene: _Scene, center_x: float, origin_y: float) -> QRectF:
        zoom = scene.zoom
        # mm 坐标 → 屏幕：x 镜像（旧版旋转 180°），y 向上，再叠加本体抬升
        left = center_x - (shape.x + shape.w) * zoom
        top = origin_y - (shape.y + shape.h + scene.shift) * zoom
        return QRectF(left, top, shape.w * zoom, shape.h * zoom)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        if self._element_id is not None or self._group_id is not None:
            self._refresh()


class SectionPanel(QWidget):
    """断面图面板：画布容器（旧版多原则时 PNLpicCtrler 的三个下拉已随功能取消）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._element_id: int | None = None

        self._canvas = SectionView()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._canvas, 1)

    # ------------------------------------------------------------------ 对外
    def set_element(self, element_id: int | None) -> None:
        """跟随主表格选中行。"""
        self._element_id = element_id
        self._canvas.set_element(element_id)

    def set_group(self, group_id: int | None) -> None:
        """合槽父行选中：画整槽全景断面。"""
        self._element_id = None
        self._canvas.set_group(group_id)

    def show_multi(self) -> None:
        """主表格选中多行：画布显示 *多种断面 占位。"""
        self._element_id = None
        self._canvas.show_multi()

    def refresh(self) -> None:
        """构件数据变化后重算重绘。"""
        self._canvas.refresh()


# --------------------------------------------------------------------------- #
# 场景构建（几何部分复用计算引擎函数）
# --------------------------------------------------------------------------- #
def _build_scene(
    element_id: int | None,
    width: int,
    height: int,
) -> tuple[_Scene | None, str]:
    if element_id is None:
        return None, "请选择构件条目"
    session = orm.session()
    element = session.get(Element, element_id)
    if element is None:
        return None, "请选择构件条目"
    if element.category == CATEGORY_STRUCTURE:
        # 附属构筑物（旧版 mcPictureBox 无 mcE7 分支）：不画沟槽与本体
        return None, "附属构筑物不参与沟槽计算，无断面图。"

    pe = _enclosure_by_name(session, element.pe_name)
    pf = _foundation_by_name(session, element.pf_name)
    if pe is None and element.pe_name == LR_PE_TEXT:
        return _build_trench_scene_lr(element, session, pf, width, height)
    if pe is None or pf is None:
        return None, "该构件未指定围护/地基处理原则，无法绘制断面。"
    if not element.pipes and element.category in (CATEGORY_BURIED, CATEGORY_JACKING, CATEGORY_PULLING):
        return None, "该构件未录入管材，无法绘制断面。"

    # 降水/面宽按元素引用解析（面宽决定图集宽度表；失效回退第一条，同计算引擎）
    pw_name = element.pw_name
    pw = session.scalars(select(PcpWidth).where(PcpWidth.name == pw_name)).first() if pw_name else None
    if pw is None:
        pw = _first_of(session, PcpWidth)
    pp = _precipitation_for(session, element)
    info = build_element_input(element, pe, pf, pp=pp, pw=pw)
    at = resolve_atlas(build_atlas_query(info, pf, pw))
    c1_original = at.c1
    if info.category in (CATEGORY_JACKING, CATEGORY_PULLING):
        # 旧版 mcE4/mcE5：不画沟槽，只按管径 + 换填厚自适应缩放画管体
        c1_display = 0.0
        extent = info.pipes[0].dn + at.t * 2 + foundation_thickness(pf)
        zoom = min(
            1.0,
            (width - _MARGIN * 2) / max(extent, 1.0),
            (height - _BOTTOM_GAP - _TOP_GAP) / max(extent, 1.0),
        )
        scene = _Scene(zoom=max(zoom, 0.0), shift=foundation_thickness(pf) + c1_display - c1_original)
        scene.shapes = _ontology_shapes(info, at, c1_original)
        scene.atlas_text = _atlas_text(at, c1_display)
        return scene, ""
    return _build_trench_scene(info, pe, pf, at, c1_original, width, height)


def _enclosure_by_name(session, name: str | None) -> PcpEnclosure | None:
    if not name:
        return None
    return session.scalars(select(PcpEnclosure).where(PcpEnclosure.name == name)).first()


def _foundation_by_name(session, name: str | None) -> PcpFoundation | None:
    if not name:
        return None
    return session.scalars(select(PcpFoundation).where(PcpFoundation.name == name)).first()


def _first_of(session, model):
    """取某类原则的第一条（元素引用失效时的回退，与计算引擎一致）。"""
    from sqlalchemy import select as _select

    return session.scalars(_select(model).order_by(model.order_no, model.id)).first()


def _precipitation_for(session, element) -> PcpPrecipitation | None:
    """构件引用的挖填降水原则（失效回退第一条），与计算引擎同口径。"""
    name = element.pp_name
    pp = (
        session.scalars(select(PcpPrecipitation).where(PcpPrecipitation.name == name)).first()
        if name
        else None
    )
    return pp or _first_of(session, PcpPrecipitation)


def _build_trench_scene(
    info: ElementInput, pe: PcpEnclosure, pf: PcpFoundation, at, c1_original: float,
    width: int, height: int,
) -> tuple[_Scene | None, str]:
    """沟槽断面（直埋/包封/箱涵/管廊）：旧版 PaintBackFilled + PaintOntology。"""
    # 垫层 / 管道基础取地基原则 pf（v10 起）；回填材质取挖填降水原则 info.pp
    c1_display = c1_original if c1_original != 0 else cushion_thickness(pf)
    at_display = replace(at, c1=c1_display)
    depth = info.depth + groove.mm2m(foundation_thickness(pf) + at_display.t + c1_display)
    work = choice_work(pe, depth)
    if work is None:
        return None, "该围护原则没有任何围护分级，无法绘制断面。"

    cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    ad_display = atlas_dims(info, at_display)  # 图集参数的算式伴随（这里只取数值）
    layers = groove.backfill_layers(info.pp, pf, ad_display, info.size_h_dim, dim(depth), cushion_name)
    bottom = groove.groove_width(ad_display, info.size_b_dim).v
    segments = _walk_layers(list(work.levels), layers, bottom, depth)
    total_h = segments[-1].h_current + segments[-1].h_delta if segments else 0.0
    top_width = segments[-1].bottom + segments[-1].h_delta * segments[-1].slope * 2 if segments else 0.0
    if total_h <= 0:
        return None, "沟槽深度为 0，无法绘制断面。"

    zoom = min(
        1.0,
        (width - _MARGIN * 2) / (top_width * 1000.0),
        (height - _BOTTOM_GAP - _TOP_GAP) / (total_h * 1000.0),
    )
    scene = _Scene(
        segments=segments,
        total_h=total_h,
        top_width=top_width,
        zoom=max(zoom, 0.0),
        shapes=_ontology_shapes(info, at, c1_original),
        # 本体零点抬升：换填厚 + (显示垫层厚 - 图集垫层厚)，旧版 PaintOntology 的 Translate
        shift=foundation_thickness(pf) + c1_display - c1_original,
    )
    scene.atlas_text = _atlas_text(at, c1_display)
    return scene, ""


def _walk_layers(levels: list, layers: list[tuple[str, float, str]], bottom: float, depth: float) -> list[_Segment]:
    """按旧版 PaintBackFilled 的递推把回填层切成随深度放坡的梯形段（单位 m）。"""
    step_heights = [step.v for step in groove.split_h_by_step(levels, dim(depth))]
    if not step_heights:
        return []
    step = len(levels) - 1

    segments: list[_Segment] = []
    current = 0.0
    for key, layer, _note in layers:
        layer_h = layer.v
        target = current + layer_h
        while True:
            delta = min(target, step_heights[step]) - current
            slope = level_slope(levels[step]).v
            continues = bool(segments) and segments[-1].key == key
            segments.append(_Segment(key, bottom, current, delta, slope, continues))
            current += delta
            bottom += delta * slope * 2
            if current == step_heights[step] and step > 0:
                step -= 1
                if step_heights[step] != step_heights[step + 1] and step_heights[step + 1] != 0:
                    bottom += levels[step].step_width * 2
            if current - target >= -0.0001:
                break
    return segments


def _walk_layers_sided(
    levels_l: list,
    levels_r: list,
    layers: list[tuple[str, float, str]],
    bottom: float,
    depth: float,
) -> tuple[list[_Segment], list[_Segment]]:
    """左右分设的逐层递推（与 cal_groove_sided 同构，只出几何不出量）。

    返回 (左段列表, 右段列表)：切段口径与 :func:`cal_groove_sided` 相同（级标高
    取两侧并集），但绘图必须让每侧**各自**维护半宽——两列 ``bottom`` 分别是
    ``2×该侧半宽``（随该侧坡度外扩、平台只加发生切级的一侧）。若两列共用按
    ``sL+sR`` 外扩的总底宽，坡度不等时下一段 ``bottom/2`` 会跳过上一段终点，
    折线随之错位折断。
    """
    heights_l = [step.v for step in groove.split_h_by_step(levels_l, dim(depth))]
    heights_r = [step.v for step in groove.split_h_by_step(levels_r, dim(depth))]
    if not heights_l or not heights_r:
        return [], []
    step_l, step_r = len(levels_l) - 1, len(levels_r) - 1

    segments_l: list[_Segment] = []
    segments_r: list[_Segment] = []
    half_l = half_r = bottom / 2.0
    current = 0.0
    for key, layer, _note in layers:
        layer_h = layer.v
        target = current + layer_h
        while True:
            top_l, top_r = heights_l[step_l], heights_r[step_r]
            step_top = min(top_l, top_r)
            delta = min(target, step_top) - current
            slope_l = level_slope(levels_l[step_l]).v
            slope_r = level_slope(levels_r[step_r]).v
            segments_l.append(
                _Segment(key, half_l * 2.0, current, delta, slope_l,
                         bool(segments_l) and segments_l[-1].key == key)
            )
            segments_r.append(
                _Segment(key, half_r * 2.0, current, delta, slope_r,
                         bool(segments_r) and segments_r[-1].key == key)
            )
            current += delta
            half_l += delta * slope_l
            half_r += delta * slope_r
            if current == top_l and step_l > 0:
                step_l -= 1
                if heights_l[step_l] != heights_l[step_l + 1] and heights_l[step_l + 1] != 0:
                    half_l += levels_l[step_l].step_width
            if current == top_r and step_r > 0:
                step_r -= 1
                if heights_r[step_r] != heights_r[step_r + 1] and heights_r[step_r + 1] != 0:
                    half_r += levels_r[step_r].step_width
            if current - target >= -0.0001:
                break
    return segments_l, segments_r


def _build_trench_scene_lr(
    element: Element, session, pf: PcpFoundation | None, width: int, height: int
) -> tuple[_Scene | None, str]:
    """左右分设构件的沟槽断面：两侧各自的围护做法，各画各的折线。"""
    pe_l, pe_r = _resolve_lr_enclosures(element)
    if pe_l is None or pe_r is None:
        return None, "左右分设的围护原则不可用，无法绘制断面。"
    if pf is None:
        pf = _first_of(session, PcpFoundation)
    if pf is None:
        return None, "该构件未指定地基处理原则，无法绘制断面。"
    pw_name = element.pw_name
    pw = (
        session.scalars(select(PcpWidth).where(PcpWidth.name == pw_name)).first()
        if pw_name
        else None
    ) or _first_of(session, PcpWidth)
    # 垫层 / 管道基础取地基原则 pf、回填材质取挖填降水原则（v10 起不再分侧）
    info = build_element_input(element, pe_l, pf, pp=_precipitation_for(session, element), pw=pw)
    at = resolve_atlas(build_atlas_query(info, pf, pw))
    c1_original = at.c1
    c1_display = c1_original if c1_original != 0 else cushion_thickness(pf)
    at_display = replace(at, c1=c1_display)
    depth = info.depth + groove.mm2m(foundation_thickness(pf) + at_display.t + c1_display)
    work_l = choice_work(pe_l, depth)
    work_r = choice_work(pe_r, depth)
    if work_l is None or work_r is None:
        return None, "左右任一侧围护原则没有任何围护分级，无法绘制断面。"

    ad_display = atlas_dims(info, at_display)
    cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    layers = groove.backfill_layers(
        info.pp, pf, ad_display, info.size_h_dim, dim(depth), cushion_name
    )
    bottom = groove.groove_width(ad_display, info.size_b_dim).v
    segments_l, segments_r = _walk_layers_sided(
        list(work_l.levels), list(work_r.levels), layers, bottom, depth
    )
    if not segments_l or not segments_r:
        return None, "沟槽深度为 0，无法绘制断面。"
    total_h = segments_l[-1].h_current + segments_l[-1].h_delta
    top_width = segments_l[-1].bottom + segments_l[-1].h_delta * segments_l[-1].slope * 2
    top_width_r = segments_r[-1].bottom + segments_r[-1].h_delta * segments_r[-1].slope * 2
    zoom = min(
        1.0,
        (width - _MARGIN * 2) / (max(top_width, top_width_r) * 1000.0),
        (height - _BOTTOM_GAP - _TOP_GAP) / (total_h * 1000.0),
    )
    scene = _Scene(
        segments=segments_l,
        segments_r=segments_r,
        total_h=total_h,
        top_width=top_width,
        top_width_r=top_width_r,
        zoom=max(zoom, 0.0),
        shapes=_ontology_shapes(info, at, c1_original),
        shift=foundation_thickness(pf) + c1_display - c1_original,
    )
    scene.atlas_text = _atlas_text(at, c1_display)
    return scene, ""


def _build_group_scene(group_id: int, width: int, height: int) -> tuple[_Scene | None, str]:
    """合槽整槽全景断面（与 :func:`app.core.calc.trench_group.compute_group` 同口径）。

    * 父节点不参与几何：左边坡 = 首构件左原则，右边坡 = 末构件右原则；
    * 每个构件按**自己的**面宽原则取工作面宽；
    * 相邻等深 → 两侧围护均为 "-"，平底直接相连；
    * 相邻异深 → 浅侧工作面 + 深侧放坡（深侧所选原则）；坡到浅槽底后竖直
      向上即浅侧虚拟垂直围护，也是挖填拆分的分界线。

    折线坐标：x 相对槽中心（右正）、y 自**最深槽底**向上，单位 m。
    """
    from app.core.calc.trench_group import _internal_run, _side_name, _slope_points

    session = orm.session()
    group = session.get(TrenchGroup, group_id)
    if group is None:
        return None, "合槽组不存在。"
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    if len(members) < 2:
        return None, "合槽组至少需要两条构件。"

    # 成员快照：原则一律取子构件自己的（父节点不持有 PE / PW）
    snapshots = []
    for element in members:
        pf = _foundation_by_name(session, element.pf_name) or _first_of(session, PcpFoundation)
        pw = (
            session.scalars(select(PcpWidth).where(PcpWidth.name == element.pw_name)).first()
            if element.pw_name
            else None
        ) or _first_of(session, PcpWidth)
        if pf is None or pw is None:
            return None, f"构件「{element.name}」缺少地基 / 面宽原则。"
        info = build_element_input(element, None, pf, pp=_precipitation_for(session, element), pw=pw)
        # 垫层 / 管道基础取地基原则 pf（v10 起；图集查询同计算引擎）
        at = resolve_atlas(build_atlas_query(info, pf, pw))
        ad = atlas_dims(info, at)
        c1_display = at.c1 if at.c1 != 0 else cushion_thickness(pf)
        depth = info.depth + groove.mm2m(foundation_thickness(pf) + ad.t.v + c1_display)
        base_width = (info.size_b_dim + scale_sum((ad.t, ad.a), 2.0) / 1000).v
        snapshots.append(
            {
                "element": element,
                "info": info,
                "pf": pf,
                "at": at,
                "c1_display": c1_display,
                "depth": depth,
                "base_width": base_width,
                "work_width": workwidth_of(pw, info) / 1000,
            }
        )

    n = len(snapshots)
    first, last = snapshots[0], snapshots[n - 1]
    pe_left = _enclosure_by_name(session, _side_name(first["element"], "left")) or _first_of(
        session, PcpEnclosure
    )
    pe_right = _enclosure_by_name(session, _side_name(last["element"], "right")) or _first_of(
        session, PcpEnclosure
    )
    work_left = choice_work(pe_left, first["depth"]) if pe_left is not None else None
    work_right = choice_work(pe_right, last["depth"]) if pe_right is not None else None
    if work_left is None or work_right is None:
        return None, "边缘围护原则没有任何围护分级，无法绘制断面。"

    # 相邻区（规则 4 / 5）：等深两侧 "-"；异深时深侧选原则放坡到浅槽底
    pairs: list[dict] = []
    for i in range(n - 1):
        left, right = snapshots[i], snapshots[i + 1]
        h_left, h_right = left["depth"], right["depth"]
        if abs(h_right - h_left) <= 1e-9:
            pairs.append(
                {
                    "deep_index": None,
                    "run": 0.0,
                    "work": None,
                    "left_width": left["work_width"],
                    "right_width": right["work_width"],
                }
            )
            continue
        if h_right > h_left:
            deep_index, deep = i + 1, right
            pe_name = _side_name(deep["element"], "left")
        else:
            deep_index, deep = i, left
            pe_name = _side_name(deep["element"], "right")
        pe_deep = _enclosure_by_name(session, pe_name) or _first_of(session, PcpEnclosure)
        delta = abs(h_right - h_left)
        work = choice_work(pe_deep, delta) if pe_deep is not None else None
        if work is None:
            return None, "深侧围护原则没有任何围护分级，无法绘制断面。"
        run = _internal_run(work, deep["depth"], min(h_left, h_right)).v
        deep_is_right = h_right > h_left
        pairs.append(
            {
                "deep_index": deep_index,
                "run": run,
                "work": work,
                "left_width": left["work_width"] if deep_is_right else run,
                "right_width": run if deep_is_right else right["work_width"],
            }
        )

    # 各构件在平面上的归属区间（自左平底缘起算）：
    # 首构件左工作面 / 末构件右工作面由自身 PW 决定，相邻区宽 = 左构件右宽 + 右构件左宽
    extents: list[tuple[float, float]] = []
    cursor = 0.0
    for i, snap in enumerate(snapshots):
        left_ext = first["work_width"] if i == 0 else pairs[i - 1]["right_width"]
        right_ext = snap["work_width"] if i == n - 1 else pairs[i]["left_width"]
        cursor += left_ext
        base_left = cursor
        cursor += snap["base_width"]
        base_right = cursor
        cursor += right_ext
        extents.append((base_left, base_right))
    total_flat = cursor

    # 槽底折线（自左向右）：工作面 / 本体平段 + 异深内侧坡（浅底 → 坡 → 深底）
    bottoms: list[tuple[float, float]] = [(0.0, first["depth"])]
    for i, snap in enumerate(snapshots):
        base_left, base_right = extents[i]
        if i == 0:
            bottoms.append((base_left, snap["depth"]))
        else:
            pair = pairs[i - 1]
            prev_right = extents[i - 1][1]
            h_prev = snapshots[i - 1]["depth"]
            if pair["deep_index"] == i:  # 自身更深（右深）：浅侧工作面 + 自身放坡
                h_shallow = h_prev
                bottoms.append((prev_right + pair["left_width"], h_shallow))
                for d_rel, run in reversed(_slope_points(pair["work"], snap["depth"] - h_shallow)):
                    bottoms.append((base_left - run, h_shallow + d_rel))
            elif pair["deep_index"] == i - 1:  # 左邻更深：自身工作面在坡脚，坡自深底向上
                h_shallow = snap["depth"]
                for d_rel, run in _slope_points(pair["work"], h_prev - h_shallow):
                    bottoms.append((prev_right + run, h_shallow + d_rel))
            # 等深：平底直接连到 base_left
        bottoms.append((base_left, snap["depth"]))
        bottoms.append((base_right, snap["depth"]))
        if i == n - 1:
            bottoms.append((base_right + snap["work_width"], snap["depth"]))

    half = total_flat / 2.0
    h_max = max(snap["depth"] for snap in snapshots)
    outline: list[tuple[float, float]] = []
    # 左边坡：自地面向下（depth 升序），x = −half − 外扩
    for d, run in sorted(_slope_points(work_left, first["depth"]), key=lambda p: p[0]):
        outline.append((-half - run, h_max - d))
    for base_x, d in bottoms:
        outline.append((base_x - half, h_max - d))
    # 右边坡：自槽底向上（depth 降序），x = +half + 外扩
    for d, run in sorted(_slope_points(work_right, last["depth"]), key=lambda p: -p[0]):
        outline.append((half + run, h_max - d))

    # 各构件本体：偏移到各自本体中心（shape 的 x 轴在屏幕上向左，故取负偏移），
    # 抬升 = 自身槽底到最深槽底的高差 + 同单管的换填 / 垫层抬升
    shapes: list[_Shape] = []
    for i, snap in enumerate(snapshots):
        base_left, base_right = extents[i]
        center_x = (base_left + base_right) / 2.0 - half
        depth_raise_mm = (h_max - snap["depth"]) * 1000.0
        raise_mm = foundation_thickness(snap["pf"]) + snap["c1_display"] - snap["at"].c1
        for shape in _ontology_shapes(snap["info"], snap["at"], snap["at"].c1):
            shapes.append(
                _Shape(
                    shape.kind,
                    shape.x - center_x * 1000.0,
                    shape.y + depth_raise_mm + raise_mm,
                    shape.w,
                    shape.h,
                )
            )

    total_w = total_flat + max(
        (run for _d, run in _slope_points(work_left, first["depth"])), default=0.0
    ) + max((run for _d, run in _slope_points(work_right, last["depth"])), default=0.0)
    zoom = min(
        1.0,
        (width - _MARGIN * 2) / (total_w * 1000.0),
        (height - _BOTTOM_GAP - _TOP_GAP) / (h_max * 1000.0),
    )
    scene = _Scene(
        total_h=h_max,
        zoom=max(zoom, 0.0),
        shapes=shapes,
        shift=0.0,
        outline=outline,
    )
    scene.atlas_text = f"合槽断面：{n} 条构件（从左到右）"
    return scene, ""


def _ontology_shapes(info: ElementInput, at, c1: float) -> list[_Shape]:
    """管体本体图形（旧版各 mcE 子类的 OntologyShape，mm；c1 为图集原值）。"""
    category = info.category
    shapes: list[_Shape] = []
    if category in (CATEGORY_JACKING, CATEGORY_PULLING):
        dn = info.pipes[0].dn
        t = at.t
        if category == CATEGORY_PULLING:
            c1 = at.c1  # 牵引管保持图集值（旧版 mcE5.OntologyShape）
        else:
            c1 = 0.0  # 顶管不设垫层（旧版 mcE4.OntologyShape）
        shapes.append(_Shape("Ellipse", -dn / 2.0 - t, c1, dn + 2 * t, dn + 2 * t))
        shapes.append(_Shape("Ellipse", -dn / 2.0, t + c1, dn, dn))
        return shapes
    if category == CATEGORY_BURIED:
        dn = info.pipes[0].dn
        if pf_con_found(info) and is_concrete_pipe(info) and "预应力" not in info.pipes[0].mat:
            width = info.size_b * 1000 + at.t * 2 + at.a * 2
            shapes.append(_Shape("Rectangle", -width / 2.0, 0.0, width, at.c1 + at.c2))
        shapes.append(_Shape("Ellipse", -dn / 2.0 - at.t, at.c1, dn + 2 * at.t, dn + 2 * at.t))
        shapes.append(_Shape("Ellipse", -dn / 2.0, at.t + at.c1, dn, dn))
        return shapes
    if category == CATEGORY_ENCASED:
        width = info.size_b * 1000
        shapes.append(_Shape("Rectangle", -width / 2.0, at.c1, width, info.size_h * 1000))
        found_width = width + at.a * 2
        shapes.append(_Shape("Rectangle", -found_width / 2.0, 0.0, found_width, at.c1))
        return shapes
    if category in (CATEGORY_BOX_CULVERT, CATEGORY_GALLERY):
        width = info.size_b * 1000
        height = info.size_h * 1000
        shapes.append(_Shape("Rectangle", -width / 2.0, at.c1, width, height))
        found_width = width + at.a * 2
        shapes.append(_Shape("Rectangle", -found_width / 2.0, 0.0, found_width, at.c1))
        outer = info.params.get("外壁厚", 350.0)
        inner = info.params.get("内壁厚", 250.0)
        chambers = int(info.params.get("内壁", 0.0))
        bottom_slab = info.params.get("底板厚", 400.0)
        top_slab = info.params.get("顶板厚", 300.0)
        chamber_w = (width - outer * 2 - chambers * inner) / (chambers + 1)
        for index in range(chambers + 1):
            x = outer + (chamber_w + inner) * index - width / 2.0
            shapes.append(_Shape(
                "Rectangle", x, bottom_slab + at.c1, chamber_w, height - bottom_slab - top_slab,
            ))
        return shapes
    return shapes


def pf_con_found(info: ElementInput) -> bool:
    """地基原则是否采用砼基础（旧版 PE.ConFound，v10 起从 info.pf 取）。"""
    return bool(info.pf is not None and info.pf.con_found)


def _atlas_text(at, c1_display: float) -> str:
    return f"t={at.t:g} a={at.a:g} C1={c1_display:g} C2={at.c2:g}"
