"""断面示意图（复刻旧版 mcPictureBox，M8）。

几何计算直接复用 M4 计算引擎的同一套函数（backfill_layers / split_h_by_step /
level_slope / groove_width），保证图上的沟槽形状与工程量公式完全一致。

绘制约定与旧版 1.0 一致：
- 黑底、青色线条；管体断面黄描边（圆）、洋红描边（矩形），内部黑填充用于挖空；
- 坐标原点在画布底边中点，Y 轴向上；左侧用左围护原则、右侧镜像；
- 自适应缩放 zoom（mm→px，只缩小不放大，上限 1）；
- 左下角输出图集参数 ``t= a= C1= C2=``。

旧版 PaintBackFilled 的逐层递推（本模块 ``_walk_layers``）：
从槽底起按"换填→垫层→坞膀下半→坞膀上半→管顶50cm→覆土"逐层向上，
每段底宽按 高度增量×放坡系数×2 外扩，跨围护分级时外扩平台宽度。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget
from sqlalchemy import select

from app.orm import base as orm
from app.orm.models import (
    CATEGORY_BURIED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_ENCASED,
    CATEGORY_GALLERY,
    CATEGORY_JACKING,
    CATEGORY_PULLING,
    Element,
    PcpEnclosure,
    PcpFoundation,
)
from app.services.calc import groove
from app.services.calc.engine import (
    ElementInput,
    build_atlas_query,
    build_element_input,
    choice_work,
    cushion_thickness,
    foundation_thickness,
    is_concrete_pipe,
    replace,
)
from app.services.calc.groove import level_slope
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
    """一次断面绘制的全部数据。"""

    segments: list[_Segment] = field(default_factory=list)
    total_h: float = 0.0  # 沟槽总深 m
    top_width: float = 0.0  # 槽顶总宽 m（地面线起点）
    zoom: float = 1.0
    shapes: list[_Shape] = field(default_factory=list)
    shift: float = 0.0  # 本体零点相对槽底的抬升 mm（旧版 TiA + C1 - mC1）
    atlas_text: str = ""


class SectionView(QWidget):
    """当前选中构件条目的沟槽断面示意图（旧版 mcPictureBox）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._element_id: int | None = None
        self._hint = "请选择构件条目"
        self._scene: _Scene | None = None
        self.setMinimumSize(180, 160)

    # ------------------------------------------------------------------ 对外
    def set_element(self, element_id: int | None) -> None:
        """切换要绘制断面的构件条目（None 清空）。"""
        self._element_id = element_id
        self._refresh()

    def show_multi(self) -> None:
        """主表格选中多行：不绘制具体断面，居中显示占位提示。"""
        self._element_id = None
        self._scene = None
        self._hint = "*多种断面"
        self.update()

    def refresh(self) -> None:
        """构件数据变化后重算重绘。"""
        self._refresh()

    def _refresh(self) -> None:
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
        for side in (1, -1):  # 旧版：左侧 +1、右侧 -1（镜像）
            previous: _Segment | None = None
            for segment in scene.segments:
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
            # 地面线：槽顶边一直到画布边缘（旧版终点是画框半宽，按像素计）
            edge_x = center_x - side * (self.width() / 2.0)
            top_y = origin_y - scene.total_h * 1000.0 * scene.zoom
            start_x = center_x - scene.top_width / 2.0 * 1000.0 * scene.zoom * side
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
        if self._element_id is not None:
            self._refresh()


# --------------------------------------------------------------------------- #
# 场景构建（几何部分复用计算引擎函数）
# --------------------------------------------------------------------------- #
def _build_scene(element_id: int | None, width: int, height: int) -> tuple[_Scene | None, str]:
    if element_id is None:
        return None, "请选择构件条目"
    session = orm.session()
    element = session.get(Element, element_id)
    if element is None:
        return None, "请选择构件条目"
    pe = (
        session.scalars(select(PcpEnclosure).where(PcpEnclosure.name == element.pe_name)).first()
        if element.pe_name else None
    )
    pf = (
        session.scalars(select(PcpFoundation).where(PcpFoundation.name == element.pf_name)).first()
        if element.pf_name else None
    )
    if pe is None or pf is None:
        return None, "该构件未指定围护/地基处理原则，无法绘制断面。"
    if not element.pipes and element.category in (CATEGORY_BURIED, CATEGORY_JACKING, CATEGORY_PULLING):
        return None, "该构件未录入管材，无法绘制断面。"

    info = build_element_input(element, pe, pf)
    at = resolve_atlas(build_atlas_query(info, pe))
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


def _build_trench_scene(
    info: ElementInput, pe: PcpEnclosure, pf: PcpFoundation, at, c1_original: float,
    width: int, height: int,
) -> tuple[_Scene | None, str]:
    """沟槽断面（直埋/包封/箱涵/管廊）：旧版 PaintBackFilled + PaintOntology。"""
    c1_display = c1_original if c1_original != 0 else cushion_thickness(pe)
    at_display = replace(at, c1=c1_display)
    depth = info.depth + groove.mm2m(foundation_thickness(pf) + at_display.t + c1_display)
    work = choice_work(pe, depth) or (pe.works_sorted() or [None])[0]
    if work is None:
        return None, "该围护原则没有任何围护分级，无法绘制断面。"

    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    layers = groove.backfill_layers(pe, pf, at_display, info.size_h, depth, cushion_name)
    segments = _walk_layers(list(work.levels), layers, groove.groove_width(at_display, info.size_b), depth)
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
    step_heights = groove.split_h_by_step(levels, depth)
    if not step_heights:
        return []
    step = len(levels) - 1

    segments: list[_Segment] = []
    current = 0.0
    for key, layer_h, _note in layers:
        target = current + layer_h
        while True:
            delta = min(target, step_heights[step]) - current
            slope = level_slope(levels[step])
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
        if pe_con_found(info) and is_concrete_pipe(info) and "预应力" not in info.pipes[0].mat:
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
        outer = info.params.get("外壁厚 mm", 350.0)
        inner = info.params.get("内壁厚 mm", 250.0)
        chambers = int(info.params.get("内壁 道", 0.0))
        bottom_slab = info.params.get("底板厚 mm", 400.0)
        top_slab = info.params.get("顶板厚 mm", 300.0)
        chamber_w = (width - outer * 2 - chambers * inner) / (chambers + 1)
        for index in range(chambers + 1):
            x = outer + (chamber_w + inner) * index - width / 2.0
            shapes.append(_Shape(
                "Rectangle", x, bottom_slab + at.c1, chamber_w, height - bottom_slab - top_slab,
            ))
        return shapes
    return shapes


def pe_con_found(info: ElementInput) -> bool:
    """围护原则是否采用砼基础（旧版 PE.ConFound，从 info.pe 取）。"""
    return bool(info.pe is not None and info.pe.con_found)


def _atlas_text(at, c1_display: float) -> str:
    return f"t={at.t:g} a={at.a:g} C1={c1_display:g} C2={at.c2:g}"
