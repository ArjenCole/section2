"""计算表达式详情窗体：断面示意图 + 分项 / 中间符号页 + 完整算式。

双击工程量表的“计算表达式”格打开。顶部嵌入断面示意图（单构件画单构件、
合槽成员 / 父行画整槽全景，复用 :mod:`app.views.panels.section_view` 的场景
构建与绘制），其下是主算式；**鼠标悬停分项表的某一行，断面图上用半透明
色块高亮该分项计算的断面范围**（梯形 / 矩形 / 弓形 / 半圆等，几何来自引擎
随分项记录的 ``Term.geometry``，自槽底向上的深度区间 + 左右缘或弧线点列，m）。
中间符号表按分项行分页：第一页“基本参数”（t/a/C1/C2/D/Do/b/b1/B），后面
每个面积行（S1、S2…）一页，只列该行用到的中间符号；梯形 / 三角形面积行在
上方算式列统一显示成 ``(u+v)*h/2`` / ``v*h/2``。底部保留完整数值算式。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QEvent, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QWidget,
)

from app.core.evaluator import format_number
from app.views.panels import section_view
from app.views.widgets.frameless_dialog import FramelessDialog

#: 分项表的行高与可见行数上限（超出表格内部滚动）
_ROW_HEIGHT = 30
_MAX_VISIBLE_ROWS = 5
#: 中间符号页至少容纳 8 行（窗口高度已按 +15% 放大）
_MAX_INTER_ROWS = 8

_HIGHLIGHT_FILL = QColor(255, 255, 0, 90)
_HIGHLIGHT_EDGE = QColor("yellow")
#: 中间参数行悬停时的描边色（CAD 标注亮绿）
_LINE_HIGHLIGHT = QColor("#00FF00")

#: 上下文种类：单构件 / 合槽（成员或父行）/ 多选（不画断面图）
_CONTEXT_ELEMENT = "element"
_CONTEXT_GROUP = "group"
_CONTEXT_MULTI = "multi"


@dataclass(frozen=True)
class _Dimension:
    """中间参数行悬停时画在断面图旁的尺寸标注（场景坐标，m）。"""

    points: tuple[tuple[float, float], ...]
    text: str


class _SectionCanvas(section_view.SectionCanvasBase):
    """断面示意图画布：复用 section_view 的场景绘制，叠加高亮 / 尺寸标注。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = None
        self._hint = ""
        #: 高亮多边形（场景坐标，m）：单构件为 4 点梯形，合槽已按成员平移
        self._highlight: list[tuple[float, float]] | None = None
        #: 中间参数行悬停时的尺寸标注（场景坐标，m）
        self._dimension: _Dimension | None = None

    def set_scene(self, scene, hint: str = "") -> None:
        self._scene = scene
        self._hint = hint
        self.reset_view()

    def set_highlight(self, polygon_m: list[tuple[float, float]] | None) -> None:
        self._highlight = polygon_m
        self.update()

    def set_dimension(
        self, points_m: list[tuple[float, float]] | tuple[tuple[float, float], ...] | None, text: str = ""
    ) -> None:
        self._dimension = (
            _Dimension(tuple(points_m), text) if points_m and len(points_m) >= 2 else None
        )
        self.update()

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.fillRect(self.rect(), section_view._COLOR_BG)
        if self._scene is None:
            painter.setPen(QPen(QColor("gray")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._hint)
            return
        base_zoom = self._scene.zoom
        self._scene.zoom = base_zoom * self._view_zoom
        center_x, origin_y = self.view_origin()
        try:
            section_view.draw_scene(
                painter, self._scene, center_x, origin_y, self.width()
            )
        finally:
            self._scene.zoom = base_zoom
        zoom = self._scene.zoom * self._view_zoom
        if self._highlight:
            # 半透明色块盖在分项对应的梯形上（黄描边 + 低透明度黄填充，黑底可见）
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(_HIGHLIGHT_EDGE, 1))
            painter.setBrush(_HIGHLIGHT_FILL)
            polygon = QPolygonF(
                [
                    QPointF(center_x + x * 1000.0 * zoom, origin_y - y * 1000.0 * zoom)
                    for x, y in self._highlight
                ]
            )
            painter.drawPolygon(polygon)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self._dimension:
            self._paint_dimension(painter, zoom, center_x, origin_y)

    # ------------------------------------------------------------------ 标注
    def _paint_dimension(
        self, painter: QPainter, zoom: float, center_x: float, origin_y: float
    ) -> None:
        """CAD 风格尺寸标注：引出线 + 尺寸线 + 截断线 + 文字，画在原图外侧。"""
        dim = self._dimension
        if dim is None or len(dim.points) < 2:
            return
        pts = [
            (
                center_x + x * 1000.0 * zoom,
                origin_y - y * 1000.0 * zoom,
            )
            for x, y in dim.points
        ]
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        pen = QPen(_LINE_HIGHLIGHT, 2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        horizontal = abs(y1 - y2) <= abs(x1 - x2)
        if horizontal:
            offset = 32.0
            dim_y = max(y1, y2) + offset
            if dim_y > self.height() - 8:
                dim_y = min(y1, y2) - offset
            down = dim_y > y1
            # 引出线从原边端点偏移 4px 起画，不贴着断面线
            start1 = y1 + (4 if down else -4)
            start2 = y2 + (4 if down else -4)
            end = dim_y + (4 if down else -4)
            painter.drawLine(QPointF(x1, start1), QPointF(x1, end))
            painter.drawLine(QPointF(x2, start2), QPointF(x2, end))
            self._dimension_tick(painter, x1, dim_y, horizontal=True)
            self._dimension_tick(painter, x2, dim_y, horizontal=True)
            # 尺寸线为直线（中部不再画波浪折线），文字放在线外侧
            painter.drawLine(QPointF(x1, dim_y), QPointF(x2, dim_y))
            text = dim.text
            metrics = painter.fontMetrics()
            painter.drawText(
                QPointF(
                    (x1 + x2) / 2.0 - metrics.horizontalAdvance(text) / 2.0,
                    dim_y - 6,
                ),
                text,
            )
        else:
            offset = 48.0
            dim_x = max(x1, x2) + offset
            if dim_x > self.width() - 8:
                dim_x = min(x1, x2) - offset
            right = dim_x > x1
            start1 = x1 + (4 if right else -4)
            start2 = x2 + (4 if right else -4)
            end = dim_x + (4 if right else -4)
            painter.drawLine(QPointF(start1, y1), QPointF(end, y1))
            painter.drawLine(QPointF(start2, y2), QPointF(end, y2))
            self._dimension_tick(painter, dim_x, y1, horizontal=False)
            self._dimension_tick(painter, dim_x, y2, horizontal=False)
            # 尺寸线为直线（中部不再画波浪折线），文字放在线外侧
            painter.drawLine(QPointF(dim_x, y1), QPointF(dim_x, y2))
            text = dim.text
            metrics = painter.fontMetrics()
            text_width = metrics.horizontalAdvance(text)
            if dim_x + 6 + text_width < self.width() - 2:
                painter.drawText(
                    QPointF(
                        dim_x + 6,
                        (y1 + y2) / 2.0 + metrics.ascent() / 2.0,
                    ),
                    text,
                )
            else:
                painter.drawText(
                    QPointF(
                        dim_x - 6 - text_width,
                        (y1 + y2) / 2.0 + metrics.ascent() / 2.0,
                    ),
                    text,
                )
        painter.restore()

    @staticmethod
    def _dimension_tick(
        painter: QPainter, x: float, y: float, horizontal: bool
    ) -> None:
        """尺寸线端点的 45° 短斜线（建筑工程常用）。"""
        painter.drawLine(QPointF(x - 3, y + 3), QPointF(x + 3, y - 3))


class ExpressionDetailDialog(FramelessDialog):
    """「计算表达式」详情窗体。

    ``context`` 为 ``(种类, 场景id, 成员id)``：``("element", 构件id, None)``
    普通构件单选（画自己的断面）；``("group", 合槽组id, 成员id|None)`` 合槽——
    成员单选带成员 id（画整槽、分项按成员定位高亮），父行传 None（合并行自带
    成员 id）；``("multi", None, None)`` 多选（不画断面图）。合并行
    （``per_element``）的分项按成员堆叠，说明带 ``[构件N]`` 前缀。
    """

    def __init__(
        self,
        parent: QWidget | None,
        quantity,
        context: tuple[str, int | None, int | None],
    ) -> None:
        super().__init__(parent, title="计算表达式")
        self.setModal(True)
        self._quantity = quantity
        kind, scene_id, member_id = self._expand_context(context)
        self._context = (kind, scene_id)
        #: 成员单选时的成员 id：合槽场景下用它把分项几何定位到整槽图
        self._single_member_id = member_id
        self._scene = None
        self._merged_members: list[tuple[int | None, object]] = []
        merged = getattr(quantity, "per_element", False)
        if merged:
            self._merged_members = list(getattr(quantity, "quantities", []))

        body = self.bodyLayout()
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(6)

        self._canvas = _SectionCanvas()
        # 断面画布吃掉除固定表格 / 6 行算式框之外的全部剩余高度
        self._canvas.setMinimumHeight(140)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        body.addWidget(self._canvas, stretch=1)

        self._formula_label = QLabel()
        self._formula_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        body.addWidget(self._formula_label)

        self._term_table = self._make_table(["符号", "说明", "算式", "计算结果"])
        self._inter_tabs = QTabWidget()
        self._inter_tabs.setDocumentMode(True)
        self._inter_tabs.currentChanged.connect(self._on_inter_tab_changed)
        self._inter_tables: list[QTableWidget] = []
        self._inter_table: QTableWidget | None = None
        if merged:
            self._fill_merged()
        else:
            self._fill_single(quantity.presentation())
        body.addWidget(self._term_table)
        body.addWidget(self._inter_tabs)

        copy_row = QWidget()
        copy_layout = QHBoxLayout(copy_row)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(4)
        copy_layout.addWidget(QLabel("完整数值算式（可复制到 Excel 复核）："))
        self._copy_button = QToolButton()
        self._copy_button.setAutoRaise(True)
        self._copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_icon_cache = self._copy_icon()
        self._check_icon_cache = self._check_icon()
        self._copy_button.setIcon(self._copy_icon_cache)
        self._copy_button.setIconSize(QSize(16, 16))
        self._copy_button.setFixedSize(24, 24)
        self._copy_button.setToolTip("复制计算式")
        self._copy_button.setStyleSheet(
            "QToolButton { border: none; background: transparent; padding: 0; }"
        )
        self._copy_button.clicked.connect(self._copy_full_expression)
        # 复制按钮紧贴左侧文字，右侧留白
        copy_layout.addWidget(self._copy_button)
        copy_layout.addStretch(1)
        body.addWidget(copy_row)

        full = QTextBrowser()
        full.setReadOnly(True)
        full.setText(self._full_text())
        # 只保留 6 行文字的高度，节省的空间全部给上方断面图
        line_height = full.fontMetrics().lineSpacing()
        chrome = 2 * full.frameWidth() + 2 * round(full.document().documentMargin())
        full.setFixedHeight(line_height * 6 + chrome)
        full.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        body.addWidget(full)

        self._term_table.cellEntered.connect(self._on_term_entered)
        self._term_table.installEventFilter(self)

        # 空表隐藏（无量可悬停时不占版面）
        self._term_table.setVisible(self._term_table.rowCount() > 0)
        self._inter_tabs.setVisible(bool(self._inter_tables))

        self._apply_size()
        # 场景在布局落定后再构建：zoom 按画布真实尺寸计算（构造期画布还没布局）
        QTimer.singleShot(0, self, self._load_scene)

    # ------------------------------------------------------------------ 数据
    @staticmethod
    def _expand_context(context) -> tuple[str, int | None, int | None]:
        """兼容 (kind, id) 与 (kind, id, member_id) 两种上下文写法。"""
        if len(context) == 2:
            return context[0], context[1], None
        return context

    def _fill_single(self, view) -> None:
        """单条工程量：主算式 + 分项（合并形态为断面面积）+ 中间符号页。

        中间符号表按面积行分页：第一页是基本参数（t/a/C1/C2/D/Do），后面
        每个分项（S1、S2…）一页，只列该面积行用到的中间符号。
        """
        self._formula_label.setText(
            f"主算式：{view.formula} ＝ {format_number(self._quantity.value)}"
        )
        for term in view.terms:
            self._add_term_row(
                term.symbol,
                term.note,
                term.expression,
                format_number(term.value),
                term.geometry,
                self._single_member_id,
            )
        self._refresh_table_height(self._term_table)

        self._start_tabs()
        self._add_inter_tab("基本参数", view.basic_definitions, self._single_member_id)
        for group in view.groups:
            title = f"{group.symbol} {group.note}".strip()
            self._add_inter_tab(title, group.definitions, self._single_member_id)
        self._fit_tab_height()

    def _fill_merged(self) -> None:
        """多选 / 合槽合并行：分项与中间量逐成员堆叠，说明带 [构件N] 前缀。

        基本参数页汇总各成员的 t/a/C1/C2/D/Do；每个成员的分项各占一页。
        """
        self._formula_label.setText(
            f"主算式：{self._quantity.display_expression} ＝ {format_number(self._quantity.value)}"
        )
        basic: list = []
        member_groups: list[tuple[int, int | None, object]] = []
        index = 0
        for member_no, (element_id, member) in enumerate(self._merged_members, start=1):
            view = member.presentation()
            for term in view.terms:
                index += 1
                self._add_term_row(
                    f"V{index}",
                    f"[构件{member_no}] {term.note}".strip(),
                    term.expression,
                    format_number(term.value),
                    term.geometry,
                    element_id,
                )
            for item in view.basic_definitions:
                basic.append(
                    (
                        replace(
                            item,
                            label=f"[构件{member_no}] {item.label}",
                            source=(
                                f"构件{member_no}·{item.source}"
                                if item.source
                                else f"构件{member_no}"
                            ),
                        ),
                        element_id,
                    )
                )
            for group in view.groups:
                member_groups.append((member_no, element_id, group))
        self._refresh_table_height(self._term_table)

        self._start_tabs()
        self._add_inter_tab("基本参数", basic)
        for member_no, element_id, group in member_groups:
            title = f"构件{member_no}·{group.symbol} {group.note}".strip()
            definitions = [
                replace(
                    item,
                    label=f"[构件{member_no}] {item.label}",
                    source=(
                        f"构件{member_no}·{item.source}" if item.source else f"构件{member_no}"
                    ),
                )
                for item in group.definitions
            ]
            self._add_inter_tab(title, definitions, element_id)
        self._fit_tab_height()

    def _full_text(self) -> str:
        if getattr(self._quantity, "per_element", False):
            lines = []
            for member_no, (_element_id, member) in enumerate(self._merged_members, start=1):
                lines.append(f"构件{member_no}：{member.expression}")
            return "\n".join(lines)
        return self._quantity.presentation().full

    # ------------------------------------------------------------------ 复制
    @staticmethod
    def _copy_icon() -> QIcon:
        """画一个无边框的“复制”小图标（两张叠放的纸）。"""
        color = QGuiApplication.palette().color(QPalette.ColorRole.WindowText)
        background = QGuiApplication.palette().color(QPalette.ColorRole.Window)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(4, 9, 15, 18, 2, 2)
        painter.setBrush(background)
        painter.drawRoundedRect(11, 4, 15, 18, 2, 2)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _check_icon() -> QIcon:
        """复制成功后的绿色勾图标（显示 1 秒）。"""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#22C55E"), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(
            QPolygonF([QPointF(7, 17), QPointF(13, 23), QPointF(25, 9)])
        )
        painter.end()
        return QIcon(pixmap)

    def _copy_full_expression(self) -> None:
        """把完整数值计算式复制到系统剪贴板，并短暂显示勾图标。"""
        QGuiApplication.clipboard().setText(self._full_text())
        self._copy_button.setIcon(self._check_icon_cache)
        self._copy_button.setToolTip("已复制")
        QTimer.singleShot(1000, self, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        self._copy_button.setIcon(self._copy_icon_cache)
        self._copy_button.setToolTip("复制计算式")

    # ------------------------------------------------------------------ 表格
    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        table.horizontalHeader().setHighlightSections(False)
        # cellEntered 悬停信号需要本体与 viewport 都开鼠标追踪（少一个不动）
        table.setMouseTracking(True)
        table.viewport().setMouseTracking(True)
        return table

    def _add_term_row(
        self,
        symbol: str,
        note: str,
        expression: str,
        value_text: str,
        geometry,
        member_id: int | None,
    ) -> None:
        table = self._term_table
        row = table.rowCount()
        table.insertRow(row)
        for col, text in enumerate((symbol, note, expression, value_text)):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, col, item)
        table.item(row, 0).setData(Qt.ItemDataRole.UserRole, (geometry, member_id))

    def _add_inter_row(
        self,
        table: QTableWidget,
        symbol: str,
        label: str,
        expression: str,
        value_text: str,
        source: str,
        geometry=None,
        member_id: int | None = None,
    ) -> None:
        row = table.rowCount()
        table.insertRow(row)
        for col, text in enumerate((symbol, label, expression, value_text, source)):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, col, item)
        table.item(row, 0).setData(
            Qt.ItemDataRole.UserRole, (geometry, member_id)
        )

    def _start_tabs(self) -> None:
        """清空中间符号页，准备按面积行重建。"""
        while self._inter_tabs.count():
            widget = self._inter_tabs.widget(0)
            self._inter_tabs.removeTab(0)
            widget.deleteLater()
        self._inter_tables = []
        self._inter_table = None

    def _add_inter_tab(self, title: str, definitions, member_id: int | None = None) -> QTableWidget:
        """新建一页中间符号表（列：符号 / 含义 / 代入式 / 计算结果 / 来源）。

        ``definitions`` 里每项可以是 ``ExpressionDefinition``，也可以是
        ``(ExpressionDefinition, member_id)``（合并行按成员区分断面位置）。
        """
        table = self._make_table(["符号", "含义", "代入式", "计算结果", "来源"])
        for entry in definitions:
            if isinstance(entry, tuple):
                item, item_member = entry
            else:
                item, item_member = entry, member_id
            self._add_inter_row(
                table,
                item.symbol,
                item.label,
                item.expression,
                format_number(item.value),
                item.source,
                item.geometry,
                item_member,
            )
        self._refresh_table_height(table, _MAX_INTER_ROWS)
        self._inter_tabs.addTab(table, title)
        self._inter_tables.append(table)
        if self._inter_table is None:
            self._inter_table = table
        table.cellEntered.connect(
            lambda row, column, source=table: self._on_inter_entered(
                source, row, column
            )
        )
        table.viewport().installEventFilter(self)
        return table

    def _fit_tab_height(self) -> None:
        """tab 框按“标签栏 + 最高一页表格”收高，其余页内部滚动。"""
        if not self._inter_tables or not any(
            table.rowCount() for table in self._inter_tables
        ):
            self._inter_tabs.setVisible(False)
            return
        self._inter_tabs.setVisible(True)
        table_height = max(table.height() for table in self._inter_tables)
        bar_height = self._inter_tabs.tabBar().sizeHint().height()
        self._inter_tabs.setFixedHeight(bar_height + table_height + 4)

    @staticmethod
    def _refresh_table_height(table: QTableWidget, max_rows: int = _MAX_VISIBLE_ROWS) -> None:
        """行数少时按内容收高，行数多时封顶内部滚动。"""
        rows = table.rowCount()
        visible = max(1, min(rows, max_rows))
        table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        table.setFixedHeight(
            table.horizontalHeader().height() + visible * _ROW_HEIGHT + 2
        )

    # ------------------------------------------------------------------ 场景
    def _load_scene(self) -> None:
        kind, context_id = self._context
        if kind == _CONTEXT_MULTI:
            self._scene = None
            self._canvas.set_scene(None, "多选构件不显示断面图")
            return
        from app.views.panels.section_view import _build_group_scene, _build_scene

        width = max(self._canvas.width(), 400)
        height = max(self._canvas.height(), 160)
        if kind == _CONTEXT_GROUP:
            scene, hint = _build_group_scene(context_id, width, height)
        else:
            scene, hint = _build_scene(context_id, width, height)
        self._scene = scene
        self._canvas.set_scene(scene, hint or "断面图不可用")

    def _highlight_polygon(self, geometry, member_id: int | None):
        """分项几何 → 场景坐标多边形（m）；无场景 / 无几何 / 成员不在图中返回 None。

        几何两种形态：6 元组梯形（左右缘），或点列多边形（弓形 / 半圆等
        弧边形状，弦线 + 采样弧线）。
        """
        scene = self._scene
        if scene is None or geometry is None:
            return None
        if len(geometry) == 6 and isinstance(geometry[0], (int, float)):
            h0, h1, l0, r0, l1, r1 = geometry
            pts_m = [(l0, h0), (r0, h0), (r1, h1), (l1, h1)]
        else:  # 多边形（点列）
            pts_m = [(float(x), float(y)) for x, y in geometry]
        if scene.outline is not None:
            # 合槽：按成员定位（成员本体中心 + 该成员槽底在整槽 y 中的位置）
            spans = {span[0]: span for span in scene.member_spans}
            if member_id is None or member_id not in spans:
                return None
            _eid, center, depth = spans[member_id]
            base_y = scene.total_h - depth
            return [(center + x, base_y + y) for x, y in pts_m]
        return list(pts_m)

    # ------------------------------------------------------------------ 事件
    def _scene_line_for(self, symbol: str):
        """B / H 行的兜底描边：从断面分段取横线 / 竖线。

        层底宽 / 层高在面积行里已有 ``ExpressionDefinition.geometry``；这里只
        补基本参数页里没有对应面积行的 B、H、H1（例如回填页的垫层高度）。
        """
        scene = self._scene
        if scene is None or scene.outline is not None:
            return None
        segments = list(scene.segments)
        if not segments:
            return None
        if symbol == "B":
            seg = segments[0]
            return [
                (-seg.bottom / 2.0, seg.h_current),
                (seg.bottom / 2.0, seg.h_current),
            ]
        if symbol == "H":
            seg = segments[0]
            return [(seg.bottom / 2.0, 0.0), (seg.bottom / 2.0, scene.total_h)]
        if symbol.startswith("B") and symbol[1:].isdigit():
            index = int(symbol[1:])
            if 1 <= index < len(segments):
                seg = segments[index]
                return [
                    (-seg.bottom / 2.0, seg.h_current),
                    (seg.bottom / 2.0, seg.h_current),
                ]
        if symbol.startswith("H") and symbol[1:].isdigit():
            index = int(symbol[1:])
            if 1 <= index <= len(segments):
                seg = segments[index - 1]
                return [
                    (seg.bottom / 2.0, seg.h_current),
                    (seg.bottom / 2.0, seg.h_current + seg.h_delta),
                ]
        return None

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        if event.type() == QEvent.Type.Leave:
            if obj is self._term_table:
                self._canvas.set_highlight(None)
            elif any(obj is table.viewport() for table in self._inter_tables):
                self._canvas.set_dimension(None)
        return super().eventFilter(obj, event)

    def _on_term_entered(self, row: int, _column: int) -> None:
        item = self._term_table.item(row, 0)
        if item is None:
            self._canvas.set_highlight(None)
            return
        geometry, member_id = item.data(Qt.ItemDataRole.UserRole) or (None, None)
        self._canvas.set_highlight(self._highlight_polygon(geometry, member_id))

    def _on_inter_entered(
        self, table: QTableWidget, row: int, _column: int
    ) -> None:
        item = table.item(row, 0)
        if item is None:
            self._canvas.set_dimension(None)
            return
        geometry, member_id = item.data(Qt.ItemDataRole.UserRole) or (None, None)
        if geometry is None:
            geometry = self._scene_line_for(item.text())
        line = self._highlight_polygon(geometry, member_id)
        value_item = table.item(row, 3)
        value_text = value_item.text() if value_item is not None else ""
        self._canvas.set_dimension(
            line, f"{item.text()}={value_text}" if line else ""
        )

    def _on_inter_tab_changed(self, _index: int) -> None:
        self._canvas.set_dimension(None)

    # ------------------------------------------------------------------ 尺寸
    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """首次显示时居中到父窗体（无父窗体则居中到屏幕）。"""
        super().showEvent(event)
        if getattr(self, "_centered", False):
            return
        self._centered = True
        parent = self.parentWidget()
        screen = None
        if parent is not None and parent.windowHandle() is not None:
            screen = parent.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if parent is not None:
            area = parent.window().frameGeometry()
        elif screen is not None:
            area = screen.availableGeometry()
        else:
            return
        self.move(area.center() - self.rect().center())

    def _apply_size(self) -> None:
        # 不能对未显示的窗体调 self.screen()：windowHandle 还没创建时
        # QWidget::screen() 在 Qt 6.11 会空指针访问冲突（现场 0xC0000005 闪退）。
        # 父窗体（主窗口）已显示，从它取屏；取不到退回主屏。
        screen = None
        parent = self.parent()
        if parent is not None and parent.windowHandle() is not None:
            screen = parent.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        width = min(980, int(available.width() * 0.8)) if available else 980
        # 高度在原来 85% 屏高的基础上放大 15%，并给中间符号表留出 8 行空间
        base_height = (
            min(840, int(available.height() * 0.85)) if available else 840
        )
        height = int(base_height * 1.15)
        if available:
            height = min(height, int(available.height() * 0.98))
        self.setFixedSize(width, height)
        # 列宽：算式列吃剩余，其余按内容
        for table in (self._term_table, *self._inter_tables):
            table.resizeColumnsToContents()
            table.horizontalHeader().setSectionResizeMode(
                2, QHeaderView.ResizeMode.Stretch
            )
