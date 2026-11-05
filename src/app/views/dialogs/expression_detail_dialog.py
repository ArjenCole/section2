"""计算表达式详情窗体：断面示意图 + 分项 / 中间符号页 + 完整算式。

双击工程量表的“计算表达式”格打开。顶部嵌入断面示意图（单构件画单构件、
合槽成员 / 父行画整槽全景，复用 :mod:`app.views.panels.section_view` 的场景
构建与绘制），其下是主算式；**鼠标悬停分项表的某一行，断面图上用半透明
色块高亮该分项计算的梯形范围**——几何来自引擎随分项记录的 ``Term.geometry``
（自槽底向上的深度区间 + 左右缘，m）。中间符号表按分项行分页：第一页“基本
参数”（t/a/C1/C2/D/Do），后面每个面积行（S1、S2…）一页，只列该行用到的
中间符号；梯形 / 三角形面积行在上方算式列统一显示成 ``(u+v)*h/2`` /
``v*h/2``。底部保留完整数值算式。
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QWidget,
)

from app.core.evaluator import format_number
from app.views.panels import section_view
from app.views.widgets.frameless_dialog import FramelessDialog

#: 分项 / 中间量表的行高与可见行数上限（超出表格内部滚动）
_ROW_HEIGHT = 30
_MAX_VISIBLE_ROWS = 5

_HIGHLIGHT_FILL = QColor(255, 255, 0, 90)
_HIGHLIGHT_EDGE = QColor("yellow")

#: 上下文种类：单构件 / 合槽（成员或父行）/ 多选（不画断面图）
_CONTEXT_ELEMENT = "element"
_CONTEXT_GROUP = "group"
_CONTEXT_MULTI = "multi"


class _SectionCanvas(QWidget):
    """断面示意图画布：复用 section_view 的场景绘制，叠加半透明高亮梯形。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = None
        self._hint = ""
        #: 高亮多边形（场景坐标，m）：单构件为 4 点梯形，合槽已按成员平移
        self._highlight: list[tuple[float, float]] | None = None

    def set_scene(self, scene, hint: str = "") -> None:
        self._scene = scene
        self._hint = hint
        self.update()

    def set_highlight(self, polygon_m: list[tuple[float, float]] | None) -> None:
        self._highlight = polygon_m
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.fillRect(self.rect(), section_view._COLOR_BG)
        if self._scene is None:
            painter.setPen(QPen(QColor("gray")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._hint)
            return
        center_x = self.width() / 2.0
        origin_y = self.height() - section_view._BOTTOM_GAP
        section_view.draw_scene(painter, self._scene, center_x, origin_y, self.width())
        if not self._highlight:
            return
        # 半透明色块盖在分项对应的梯形上（黄描边 + 低透明度黄填充，黑底可见）
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(_HIGHLIGHT_EDGE, 1))
        painter.setBrush(_HIGHLIGHT_FILL)
        zoom = self._scene.zoom
        polygon = QPolygonF(
            [
                QPointF(center_x + x * 1000.0 * zoom, origin_y - y * 1000.0 * zoom)
                for x, y in self._highlight
            ]
        )
        painter.drawPolygon(polygon)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)


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
        # 断面画布按剩余空间伸缩：窗口较矮时让出高度给下方文字，避免画布
        # 盖住主算式（旧版固定 260px，窗口一矮就被压到算式标签上）
        self._canvas.setMinimumHeight(160)
        self._canvas.setMaximumHeight(320)
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
        self._inter_tables: list[QTableWidget] = []
        self._inter_table: QTableWidget | None = None
        if merged:
            self._fill_merged()
        else:
            self._fill_single(quantity.presentation())
        body.addWidget(self._term_table)
        body.addWidget(self._inter_tabs)

        body.addWidget(QLabel("完整数值算式（可复制到 Excel 复核）："))
        full = QTextBrowser()
        full.setReadOnly(True)
        full.setText(self._full_text())
        body.addWidget(full, stretch=1)

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
        self._add_inter_tab("基本参数", view.basic_definitions)
        for group in view.groups:
            title = f"{group.symbol} {group.note}".strip()
            self._add_inter_tab(title, group.definitions)
        self._fit_tab_height()

    def _fill_merged(self) -> None:
        """多选 / 合槽合并行：分项与中间量逐成员堆叠，说明带 [构件N] 前缀。

        基本参数页汇总各成员的 t/a/C1/C2/D/Do；每个成员的分项各占一页。
        """
        self._formula_label.setText(
            f"主算式：{self._quantity.display_expression} ＝ {format_number(self._quantity.value)}"
        )
        basic: list = []
        member_groups: list[tuple[int, object]] = []
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
                    replace(
                        item,
                        label=f"[构件{member_no}] {item.label}",
                        source=(
                            f"构件{member_no}·{item.source}" if item.source else f"构件{member_no}"
                        ),
                    )
                )
            for group in view.groups:
                member_groups.append((member_no, group))
        self._refresh_table_height(self._term_table)

        self._start_tabs()
        self._add_inter_tab("基本参数", basic)
        for member_no, group in member_groups:
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
            self._add_inter_tab(title, definitions)
        self._fit_tab_height()

    def _full_text(self) -> str:
        if getattr(self._quantity, "per_element", False):
            lines = []
            for member_no, (_element_id, member) in enumerate(self._merged_members, start=1):
                lines.append(f"构件{member_no}：{member.expression}")
            return "\n".join(lines)
        return self._quantity.presentation().full

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
    ) -> None:
        row = table.rowCount()
        table.insertRow(row)
        for col, text in enumerate((symbol, label, expression, value_text, source)):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, col, item)

    def _start_tabs(self) -> None:
        """清空中间符号页，准备按面积行重建。"""
        while self._inter_tabs.count():
            widget = self._inter_tabs.widget(0)
            self._inter_tabs.removeTab(0)
            widget.deleteLater()
        self._inter_tables = []
        self._inter_table = None

    def _add_inter_tab(self, title: str, definitions) -> QTableWidget:
        """新建一页中间符号表（列：符号 / 含义 / 代入式 / 计算结果 / 来源）。"""
        table = self._make_table(["符号", "含义", "代入式", "计算结果", "来源"])
        for item in definitions:
            self._add_inter_row(
                table,
                item.symbol,
                item.label,
                item.expression,
                format_number(item.value),
                item.source,
            )
        self._refresh_table_height(table)
        self._inter_tabs.addTab(table, title)
        self._inter_tables.append(table)
        if self._inter_table is None:
            self._inter_table = table
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
    def _refresh_table_height(table: QTableWidget) -> None:
        """行数少时按内容收高，行数多时封顶内部滚动。"""
        rows = table.rowCount()
        visible = max(1, min(rows, _MAX_VISIBLE_ROWS))
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
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        if obj is self._term_table and event.type() == QEvent.Type.Leave:
            self._canvas.set_highlight(None)
        return super().eventFilter(obj, event)

    def _on_term_entered(self, row: int, _column: int) -> None:
        item = self._term_table.item(row, 0)
        if item is None:
            self._canvas.set_highlight(None)
            return
        geometry, member_id = item.data(Qt.ItemDataRole.UserRole) or (None, None)
        self._canvas.set_highlight(self._highlight_polygon(geometry, member_id))

    # ------------------------------------------------------------------ 尺寸
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
        height = min(840, int(available.height() * 0.85)) if available else 840
        self.setFixedSize(width, height)
        # 列宽：算式列吃剩余，其余按内容
        for table in (self._term_table, *self._inter_tables):
            table.resizeColumnsToContents()
            table.horizontalHeader().setSectionResizeMode(
                2, QHeaderView.ResizeMode.Stretch
            )
