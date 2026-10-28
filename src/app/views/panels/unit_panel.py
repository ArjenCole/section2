"""中部工作区：单位工程面板。

上部：构件录入表（复刻旧版 dGVmain）。
下部横向三栏（旧版 FormUnit 的 spltCtnerR 布局）：
  左  选中构件的明细（管材 / 构件参数 / 工程量 / 多原则）；
  中  工程量表（定额工程量 / 清单工程量）——“计算表达式”列在“工程量”列之前；
  右  断面示意图（旧版 mcPictureBox，随选中构件联动重绘）。

埋深、数量两列允许写算式（如 2.5+0.3）：单元格 tooltip 显示求值结果，
算式不合法时用警示色标出并给出原因，不静默按 0 处理。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QItemSelectionModel, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QLabel,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.evaluator import EvalError, evaluate, format_number
from app.core.event_bus import bus, connect_weak
from app.core.atlas_candidates import MATCH_LEVEL_LABELS, columns_for, is_cross_group
from app.core.param_naming import (
    PARAM_A_NAME,
    PARAM_C1_NAME,
    PARAM_C2_NAME,
    PARAM_T_NAME,
    STRUCTURE_NAME_PARAM,
    STRUCTURE_UNIT_PARAM,
)
from app.core.pipe_category import is_concrete as _pipe_is_concrete
from app.views.widgets.mac_window import is_mac
from app.core.models.models import (
    CATEGORY_BOX_CULVERT,
    CATEGORY_BURIED,
    CATEGORY_ENCASED,
    CATEGORY_GALLERY,
    CATEGORY_JACKING,
    CATEGORY_PULLING,
    CATEGORY_STRUCTURE,
    LR_PE_TEXT,
    category_name,
)
from app.core.pipe_category import PIPE_CATEGORIES
from app.resources.qss.theme import ThemeManager
from app.services import project_io
from app.viewmodels.project_vm import TreeNode
from app.viewmodels.unit_vm import (
    ElementRow,
    GroupRow,
    ParamRow,
    PipeRow,
    QuantityRow,
    SINGLE_PIPE_CATEGORIES,
    UnitViewModel,
    group_side_plan,
)
from app.views.widgets.frameless_dialog import FramelessMessageBox
from app.views.widgets.panel_splitter import SPLITTER_HANDLE_WIDTH, LineSplitter
from app.views.widgets.row_button_column import RowButtonColumn
from app.views.widgets.table_edit_delegate import TableEditDelegate
from app.views.widgets.table_width import fixed_width_behavior, header_fit_width

_ELEMENT_ROLE = Qt.ItemDataRole.UserRole + 1

#: 名称列树形元数据（Quotor ResourceSeqDelegate 同款）：合槽父行 / 子行挂
#: {"indent": int, "has_children": bool, "expanded": bool}，普通行不挂
_TREE_ROLE = Qt.ItemDataRole.UserRole + 2
#: 合槽父节点行的标记（name item 的 UserRole 数据 = ("group", 组 id)）
_GROUP_ROLE_TAG = "group"
_COL_NAME, _COL_CATEGORY, _COL_SPEC, _COL_DEPTH, _COL_UNIT, _COL_AMOUNT, _COL_PE, _COL_PF, _COL_PP, _COL_PW, _COL_SOURCE = range(11)
_ELEMENT_HEADERS = ["名称", "类型", "规格", "埋深", "单位", "数量", "沟槽围护原则", "地基处理原则", "挖填降水原则", "工作面宽原则", "来源"]
#: 复刻旧版 dGVmain 列结构（类型 / 规格 / 来源列只读）
#: 围护/地基原则两列等宽（下拉框完整显示 6 个字）；
#: 规格列两倍宽；埋深=数量列宽；类型/单位列容得下表头两字；埋深/单位/数量居中
_ELEMENT_WIDTHS = [130, 48, 280, 70, 48, 70, 130, 130, 130, 130, 80]

#: 详情面板「围护原则」tab（左右分设构件显示）：四行的行头
_LR_ROWS = ("左侧围护", "右侧围护", "左侧支撑", "右侧支撑")

#: 类型列简称（仅显示层，数据库 / 工程量 / 导出等仍用完整类别名）：
#: 直埋管道→直；包封埋管/箱涵/管廊（构件库“混凝土结构”组）→箱；
#: 顶管/牵引管（构件库“非开挖管道”组）→顶；构筑物（附属构筑物）→井
_CATEGORY_ABBRS = {
    CATEGORY_BURIED: "直",
    CATEGORY_ENCASED: "箱",
    CATEGORY_BOX_CULVERT: "箱",
    CATEGORY_GALLERY: "箱",
    CATEGORY_JACKING: "顶",
    CATEGORY_PULLING: "顶",
    CATEGORY_STRUCTURE: "井",
}

_QUANTITY_HEADERS = ["编号", "类别", "项目", "单位", "工程量", "计算表达式"]
_QCOL_EXPRESSION = 5
_QCOL_AMOUNT = 4
#: 定额/清单表格列宽默认值（取自运行实例实测；末列不拉伸，保持实测宽度）
_QUANTITY_WIDTHS = [77, 66, 193, 48, 135, 434]

_PIPE_ROLE = Qt.ItemDataRole.UserRole + 1
#: 管材表 6 列：管材（材质文字）/ 管径 / 壁厚 / 含量 / 类别 / 行尾「-」删行按钮。
#: 直埋管道的壁厚只读——由构件参数行「管道壁厚」自动带出（候选值驱动）；
#: 其他类别壁厚空 = 自动按图集（灰字显示图集值），可手填。"类别"是计算唯一
#: 依据（面宽表行、图集分流、断面图砼判断都读它），默认由构件库快照写入；
#: "管材"是材质描述文字（规格与设备材料表用），不参与计算。
#: 删行按钮列只在包封 / 箱涵 / 管廊显示（直埋 / 非开挖恒一条管材、构筑物
#: 不带管材，增删入口整列隐藏，见 _pipe_panel_editable）。
_PIPE_HEADERS = ["管材", "管径mm", "壁厚mm", "含量", "类别", ""]
_PIPE_COL_MAT = 0
_PIPE_COL_DN = 1
_PIPE_COL_T = 2
_PIPE_COL_CONTENT = 3
_PIPE_COL_CAT = 4
_PIPE_COL_DEL = 5
_PARAM_ROLE = Qt.ItemDataRole.UserRole + 1
#: 候选参数格携带 (候选行 id, 字段名 a/c1/c2)
_CANDIDATE_ROLE = Qt.ItemDataRole.UserRole + 2
#: 该组合还没有候选行（图集没这组数据）时空格携带 (构件 id, 列键, 字段名)；
#: 手填即建行，见 unit_vm.set_atlas_candidate_value
_CANDIDATE_NEW_ROLE = Qt.ItemDataRole.UserRole + 4
#: 当前匹配到的候选格的底色标记（"same" / "cross"）。只存语义、不存颜色：
#: 颜色在绘制代理里按当前主题现算，切换深浅主题时自动跟着变。必须走代理自绘：
#: 全局 QSS 里 ``QTableWidget::item { background-color: transparent }`` 会让
#: QStyleSheetStyle 接管单元格背景绘制、忽略 Qt.BackgroundRole 的刷子
#: （``setBackground`` 静默无效，实测像素与相邻格完全一致）。
_MATCH_BG_ROLE = Qt.ItemDataRole.UserRole + 3
#: 同组命中（砼/非砼各自组内）
_MATCH_BG_SAME = "same"
#: 跨组借值（另一组的同角度值）
_MATCH_BG_CROSS = "cross"
#: 参数名 / 单位 / 参数值三列；直埋构件在"参数值"右侧追加候选参数列
#: （砼基础/非砼基础 × 90/120/150/180，混凝土管 8 列、其他管材 4 列）。
#: 锁定行（该类别显示的图集参数行、构筑物名称 / 单位行）参数名 / 单位只读，
#: 单位列居中，构筑物名称 / 单位行的单位列显示 “-”
_PARAM_HEADERS = ["参数名", "单位", "参数值"]
#: 直埋 + 有候选时参数值列锁定（自动从候选里选），候选列可编辑
_CANDIDATE_FIELD_BY_PARAM = {
    PARAM_T_NAME: "t",
    PARAM_A_NAME: "a",
    PARAM_C1_NAME: "c1",
    PARAM_C2_NAME: "c2",
}
#: 参数表列宽：参数名列窄、单位列宽（单位内容居中显示）；
#: 参数值列与候选参数列按列头文字定宽（见 header_fit_width）
_PARAM_NAME_WIDTH = 90
_PARAM_UNIT_WIDTH = 84
#: 没有单位的参数行（附属构筑物的名称 / 单位行，库里单位列为空）显示 “-”
_NO_UNIT_TEXT = "-"
_NO_UNIT_PARAM_ROWS: tuple[tuple[str, str], ...] = (
    (STRUCTURE_NAME_PARAM, ""),
    (STRUCTURE_UNIT_PARAM, ""),
)
_QTY_ROLE = Qt.ItemDataRole.UserRole + 1
#: 附属构筑物的工程量行（类别|项目|单位 三段合一 + 值算式）；末列空表头 = 按钮
#: 列（「+」表头格 + 行尾「-」，见 RowButtonColumn）
_QTY_HEADERS = ["类别", "项目", "单位", "值", ""]

#: 共享单元格焦点的归属标记（挂在 QTableWidget 实例属性上，Quotor _GLOBAL_LATEST 同款）
_FOCUS_OWNER_ATTR = "_unit_panel_focus_owner"
#: 格式刷防抖（毫秒）：选中变化后停顿此时长才整体生效一次并退出——
#: 覆盖拖选 / Ctrl·Shift 多选的选中间隔，单击目标也只多等这一瞬
_FORMAT_PAINTER_DEBOUNCE_MS = 300
#: 明细面板四张表标记（多选边框 / 选区互斥只作用于它们，主表格行选不受影响）
_DETAIL_TABLE_ATTR = "_unit_panel_detail_table"


def _select_row(table: QTableWidget, row: int, column: int) -> None:
    """把主表格的当前单元格与选中行设到 (row, column)，**清除其余选中**。

    必须走显式 ``ClearAndSelect | Rows`` 命令而不是 ``setCurrentCell``：
    撤销 / 重做在 Ctrl+Z / Ctrl+Y 按键处理过程中同步执行，Ctrl 修饰键还
    按着，QAbstractItemView 的 selectionCommand 会把 setCurrentCell 推断成
    "追加选择"——重做的每一步都把新行加进选区，最终整表被持续选中。
    显式命令不受修饰键影响。
    """
    table.selectionModel().setCurrentIndex(
        table.model().index(row, column),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )


class _FocusCellDelegate(TableEditDelegate):
    """当前单元格用加粗边框表示（Quotor FullCellDelegate 同款）。

    主表格与下方面板（管材/构件参数/定额工程量/清单工程量）共享唯一焦点：
    只有"最新点选"的那张表（``_FOCUS_OWNER_ATTR`` 为 True）绘制当前单元格
    边框，其余表的选中行保持普通高亮，不画边框。

    明细面板四张表（``_DETAIL_TABLE_ATTR`` 为 True）额外支持多选边框：
    拖拽 / Ctrl 点选的每个选中单元格画 2px 边框，相邻单元格的边自动
    合并成包围整个选区的外框（逐边判断：跨边邻居被选中则不画该边）。

    编辑态抛光（去边框/清边距/占满单元格）由基类 TableEditDelegate 提供。
    """

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802 - Qt 命名
        view = self.parent()
        is_table = isinstance(view, QTableWidget)
        is_focus_cell = (
            is_table
            and getattr(view, _FOCUS_OWNER_ATTR, False)
            and view.currentIndex() == index
        )
        is_detail = is_table and getattr(view, _DETAIL_TABLE_ATTR, False)
        # 底色先铺：QSS 的 ::item 背景是 transparent，样式表接管后不会画
        # BackgroundRole，只能在这里自己填（见 _MATCH_BG_ROLE 的说明）
        match_bg = index.data(_MATCH_BG_ROLE)
        if match_bg:
            painter.fillRect(
                option.rect,
                _candidate_borrowed_bg()
                if match_bg == _MATCH_BG_CROSS
                else _candidate_selected_bg(),
            )
        # 去掉默认的虚线焦点框，统一用边框表示
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)
        if is_focus_cell:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(QPen(QColor(ThemeManager.instance().current().table_selected_border), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(option.rect).adjusted(1, 1, -2, -2))
            painter.restore()
        if is_detail:
            self._draw_selection_outline(painter, option, index, view)

    def _draw_selection_outline(self, painter: QPainter, option, index, view: QTableWidget) -> None:
        """给选中单元格画 2px 边框；相邻选中格的边自动合并成选区外框。"""
        selection_model = view.selectionModel()
        if selection_model is None or not selection_model.isSelected(index):
            return
        row, column = index.row(), index.column()

        def selected(neighbor_row: int, neighbor_column: int) -> bool:
            if not (0 <= neighbor_row < view.rowCount() and 0 <= neighbor_column < view.columnCount()):
                return False
            return selection_model.isSelected(view.model().index(neighbor_row, neighbor_column))

        top = not selected(row - 1, column)
        bottom = not selected(row + 1, column)
        left = not selected(row, column - 1)
        right = not selected(row, column + 1)
        if not (top or bottom or left or right):
            return  # 四边都有选中邻居：整个大选区的内部，无需画线

        rect = QRect(option.rect)
        line_left = rect.left() + 1
        line_top = rect.top() + 1
        line_right = rect.right() - 1
        line_bottom = rect.bottom() - 1
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor(ThemeManager.instance().current().table_selected_border), 2))
        if top:
            painter.drawLine(line_left, line_top, line_right, line_top)
        if bottom:
            painter.drawLine(line_left, line_bottom, line_right, line_bottom)
        if left:
            painter.drawLine(line_left, line_top, line_left, line_bottom)
        if right:
            painter.drawLine(line_right, line_top, line_right, line_bottom)
        painter.restore()

    # --- 编辑态抛光见基类 TableEditDelegate（去 QLineEdit 边框/边距并占满单元格） ---


class _ElementNameDelegate(_FocusCellDelegate):
    """构件表名称列委托：合槽父行画 +/- 展开方框，成员行画缩进竖线（Quotor
    ResourceSeqDelegate 同款视觉语言）。

    树形元数据存于名称条目的 _TREE_ROLE（dict），普通行不带该角色、按
    基类原样绘制。点击父行的 +/- 方框区域触发 toggle_callback 切换展开。
    """

    INDENT_UNIT = 18      # 每级缩进像素
    ICON_SIZE = 11        # 方框图标边长
    ICON_LINE_WIDTH = 1
    TEXT_MARGIN = 6
    LEFT_PADDING = 8      # 与 QSS ::item 的 8px 左内边距对齐
    LINE_INSET = 3        # +/- 线条距方框边缘的缩进

    def __init__(self, parent: QWidget | None = None, toggle_callback=None) -> None:
        super().__init__(parent)
        self._toggle_callback = toggle_callback

    def _icon_slot_x(self, rect, indent_level: int) -> float:
        return rect.x() + self.LEFT_PADDING + self.INDENT_UNIT * indent_level

    def _text_x(self, rect, indent: int) -> float:
        return self._icon_slot_x(rect, indent) + self.ICON_SIZE + self.TEXT_MARGIN

    def _icon_rect(self, rect, meta) -> QRectF:
        icon_y = rect.center().y() - self.ICON_SIZE / 2.0
        return QRectF(
            self._icon_slot_x(rect, meta["indent"]), icon_y,
            self.ICON_SIZE, self.ICON_SIZE,
        )

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802 - Qt 命名
        meta = index.data(_TREE_ROLE)
        if meta is None:
            super().paint(painter, option, index)
            return
        view = self.parent()
        is_focus_cell = (
            isinstance(view, QTableWidget)
            and getattr(view, _FOCUS_OWNER_ATTR, False)
            and view.currentIndex() == index
        )
        indent = int(meta.get("indent", 0))
        has_children = bool(meta.get("has_children"))
        expanded = bool(meta.get("expanded"))

        painter.save()
        # 底色自绘（Quotor ResourceSeqDelegate 同款）：选中行 = QSS ::item:selected
        # 的 table_selected_bg；未选中行统一 = 表背景 bg_card（主表格不画交替行条纹）
        theme = ThemeManager.instance().current()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(theme.table_selected_bg))
        else:
            # 主表格不使用交替行底色：未选中行统一取两种条纹色中更浅的 bg_card
            painter.fillRect(option.rect, QColor(theme.bg_card))

        rect = option.rect
        # 缩进竖线（成员行）：在该级图标槽位之后
        if indent >= 1:
            line_x = self._icon_slot_x(rect, indent) - self.TEXT_MARGIN / 2.0
            painter.setPen(QPen(QColor(theme.text_disabled), self.ICON_LINE_WIDTH))
            painter.drawLine(
                QPointF(line_x, rect.y() + 0.5),
                QPointF(line_x, rect.bottom() - 0.5),
            )

        # +/- 方框（仅合槽父行）：展开 = 「−」，收起 = 「+」
        if has_children:
            icon_y = rect.center().y() - self.ICON_SIZE / 2.0
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor(theme.text_primary), self.ICON_LINE_WIDTH)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            box = QRectF(
                self._icon_slot_x(rect, indent), icon_y,
                self.ICON_SIZE, self.ICON_SIZE,
            )
            painter.drawRect(box)
            center_y = icon_y + self.ICON_SIZE / 2.0
            painter.drawLine(
                QPointF(box.left() + self.LINE_INSET, center_y),
                QPointF(box.right() - self.LINE_INSET, center_y),
            )
            if not expanded:
                center_x = box.center().x()
                painter.drawLine(
                    QPointF(center_x, box.top() + self.LINE_INSET),
                    QPointF(center_x, box.bottom() - self.LINE_INSET),
                )
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # 名称文本（从图标槽位之后统一 x 起始，同级对齐）
        text_x = self._text_x(rect, indent)
        painter.setPen(QPen(QColor(theme.text_primary)))
        text_rect = QRect(
            int(text_x), rect.y(), rect.right() - int(text_x) - self.LEFT_PADDING,
            rect.height(),
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.restore()

        # 当前单元格加粗边框（与 _FocusCellDelegate 同款）
        if is_focus_cell:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(QPen(QColor(ThemeManager.instance().current().table_selected_border), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(option.rect).adjusted(1, 1, -2, -2))
            painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802 - Qt 命名
        """点击 +/- 方框区域 → 切换合槽组展开/收起（Quotor 同款交互）。"""
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            meta = index.data(_TREE_ROLE)
            if meta and meta.get("has_children"):
                if self._icon_rect(option.rect, meta).contains(event.position()):
                    if self._toggle_callback is not None:
                        self._toggle_callback(index.row())
                    return True
        return super().editorEvent(event, model, option, index)


class _PipeCategoryDelegate(_FocusCellDelegate):
    """管材表“管材”列下拉：四类管材（宽度表行），其余列仍是文本框。

    管材类别是计算唯一依据（面宽表行 / 图集分流 / 断面图砼判断 / 包封扣管位），
    所以做成固定枚举，避免用户敲出表外文字导致静默兜底。
    """

    def createEditor(self, parent, option, index):  # noqa: N802 - Qt 命名
        if index.column() != _PIPE_COL_CAT:
            return super().createEditor(parent, option, index)
        combo = QComboBox(parent)
        combo.addItems(list(PIPE_CATEGORIES))
        combo.setFrame(False)
        return combo

    def setEditorData(self, editor, index):  # noqa: N802 - Qt 命名
        if isinstance(editor, QComboBox):
            editor.setCurrentText(str(index.data() or ""))
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):  # noqa: N802 - Qt 命名
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText())
            return
        super().setModelData(editor, model, index)


class UnitPanel(QWidget):
    """单位工程工作台。"""

    #: 格式刷状态变化（开启 / 取消）——主窗体据此同步工具栏按钮的勾选态
    format_painter_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self._vm = UnitViewModel()
        self._unit_id: int | None = None
        self._loading = False
        # 构件库插入后待选中的新条目 id：表格刷新经 unit_changed → QTimer 延后，
        # 插入返回时还是旧行，由 _on_unit_loaded 在重载落地后按它选中新行
        self._pending_select_id: int | None = None
        # 明细面板跟随主表格选中行：多选时左右中三块都显示占位/合计
        self._multi_detail = False
        self._current_detail_id: int | None = None
        # 撤销 / 重做重建工作库后置位：表格行上的构件 id 已失效，
        # 下一次 _on_unit_loaded 不再按 id 恢复选中（见 mark_ids_stale）
        self._ids_stale = False
        #: 参数表当前显示的候选列（直埋构件有候选时非空，见 _on_detail_loaded）
        self._candidate_columns: list = []
        #: 最近一次装填的表格行（含父节点行；_current_element_row 用）
        self._rows_cache: list = []
        #: 收起的合槽组 id（跨表格重载保留；仅视图状态，不入库）
        self._collapsed_group_ids: set[int] = set()
        #: 合槽父行选中时的成员 id（工程量合计 / 断面图用；空 = 非父行态）
        self._group_member_ids: list[int] = []
        #: 格式刷：True = 等待把样板构件的四项原则刷到后续选中的构件上
        self._format_painter_active = False
        self._format_painter_source: int | None = None
        #: 格式刷光标覆盖是否已设置（进出成对，避免重复 set / restore）
        self._format_painter_cursor_active = False
        #: 格式刷防抖：选中包含样板以外的构件后停顿片刻才整体生效一次并退出
        #: （拖选 / Ctrl·Shift 多选是逐步发生的，见 _schedule_format_painter）
        self._format_painter_timer = QTimer(self)
        self._format_painter_timer.setSingleShot(True)
        self._format_painter_timer.setInterval(_FORMAT_PAINTER_DEBOUNCE_MS)
        self._format_painter_timer.timeout.connect(self._flush_format_painter)
        self._build_ui()
        self._connect()
        self._show_unit(None)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 自绘 1px 线的手柄：抓取区加宽，鼠标移上去线会高亮
        splitter = LineSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(SPLITTER_HANDLE_WIDTH)
        splitter.addWidget(self._build_element_table())
        splitter.addWidget(self._build_bottom_area())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        # 主表格区 / 明细面板默认高度（取自运行实例实测）
        splitter.setSizes([536, 311])
        self._work_area = splitter
        layout.addWidget(splitter, 1)

        self._placeholder = QLabel("请先在左侧选择单位工程。")
        self._placeholder.setProperty("role", "placeholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._placeholder, 1)
        self._placeholder.setVisible(False)

    def _build_element_table(self) -> QTableWidget:
        self._element_table = self._make_table(_ELEMENT_HEADERS)
        # 主表格不画交替行条纹：所有单元格统一用更浅的底色（见 _ElementNameDelegate）
        self._element_table.setAlternatingRowColors(False)
        # 全部列都按 _ELEMENT_WIDTHS 定宽（含末列「来源」）：表格总宽即各列之和，
        # 不随父控件拉伸（固定列宽约定见 table_width 模块）
        for index, width in enumerate(_ELEMENT_WIDTHS):
            self._element_table.setColumnWidth(index, width)
        self._element_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._element_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # 名称列树形委托：合槽父行 +/- 展开方框（点击切换），成员行缩进竖线
        self._element_table.setItemDelegateForColumn(
            _COL_NAME, _ElementNameDelegate(self._element_table, self._on_group_toggle_requested)
        )
        self._element_table.setSortingEnabled(False)
        self._element_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._element_table.customContextMenuRequested.connect(self._on_element_context_menu)
        self._element_table.installEventFilter(self)
        return self._element_table

    def _build_bottom_area(self) -> QWidget:
        """横向三栏：构件明细（管材/构件参数/工程量/多原则）｜工程量表（定额/清单）｜断面示意图。"""
        bottom = LineSplitter(Qt.Orientation.Horizontal)
        bottom.setHandleWidth(SPLITTER_HANDLE_WIDTH)

        # 左：选中构件的明细
        detail = QTabWidget()
        # Windows：documentMode 让页签文字左对齐、外观交给全局 QSS；
        # mac 不能开 documentMode——QMacStyle 会在页签首次显示时重置窗口
        # 样式掩码，把透明标题栏打回系统样式（对齐由 MacStyleTweaks 处理）
        if not is_mac():
            detail.setDocumentMode(True)
        detail.tabBar().setDrawBase(False)
        self._pipe_table = self._make_table(_PIPE_HEADERS, card_header=True)
        self._param_table = self._make_table(_PARAM_HEADERS, card_header=True)
        # 手设列宽：管径/壁厚列收窄到刚好完整显示列头四个字（管径、壁厚、含量
        # 三列的内容居中显示，见 _on_detail_loaded）；末列是按钮列（「+」表头格
        # + 每行行尾「-」，见 RowButtonColumn），类别列固定宽
        self._pipe_table.setColumnWidth(_PIPE_COL_MAT, 120)
        self._pipe_table.setColumnWidth(
            _PIPE_COL_DN, header_fit_width(self._pipe_table, _PIPE_HEADERS[_PIPE_COL_DN])
        )
        self._pipe_table.setColumnWidth(
            _PIPE_COL_T, header_fit_width(self._pipe_table, _PIPE_HEADERS[_PIPE_COL_T])
        )
        self._pipe_table.setColumnWidth(_PIPE_COL_CONTENT, 66)
        self._pipe_table.setColumnWidth(_PIPE_COL_CAT, 100)
        self._pipe_table.setColumnHidden(_PIPE_COL_DEL, True)
        self._pipe_table.setItemDelegate(_PipeCategoryDelegate(self._pipe_table))
        self._param_table.setColumnWidth(0, _PARAM_NAME_WIDTH)
        self._param_table.setColumnWidth(1, _PARAM_UNIT_WIDTH)
        self._param_table.setColumnWidth(2, header_fit_width(self._param_table, _PARAM_HEADERS[2]))
        self._qty_table = self._make_table(_QTY_HEADERS, card_header=True)
        # 类别列刚好容纳内容「构筑物」三个字（实测 62px：55px 会被截成省略号）
        self._qty_table.setColumnWidth(0, 62)
        self._qty_table.setColumnWidth(1, 140)
        self._qty_table.setColumnWidth(2, 56)
        self._qty_table.setColumnWidth(3, 120)
        # 管材/工程量两张表的「+ / -」按钮列：+ 在按钮列表头格，每行行尾「-」
        # 删该行；类别不允许时整列不显示（_update_pipe_buttons / _on_detail_loaded
        # 控制显隐）。参数表不装按钮列——参数行由图集/构件库自动带出，不允许
        # 用户增删（AI 工具走 VM 层 add_param，不经此 UI）
        self._pipe_buttons = RowButtonColumn(
            self._pipe_table,
            add_tooltip="为选中构件新增一行管材",
            delete_tooltip="删除该管材行",
        )
        self._pipe_buttons.add_clicked.connect(self._add_pipe)
        self._pipe_buttons.delete_clicked.connect(self._delete_pipe_row)
        self._pipe_buttons.attach()
        self._qty_buttons = RowButtonColumn(
            self._qty_table,
            add_tooltip="为选中构筑物新增一行工程量",
            delete_tooltip="删除该工程量行",
        )
        self._qty_buttons.add_clicked.connect(self._add_quantity)
        self._qty_buttons.delete_clicked.connect(self._delete_qty_row)
        self._qty_buttons.attach()
        self._qty_buttons.set_visible(False)  # 仅附属构筑物显示，等明细加载定

        pipe_page = QWidget()
        # 页面背景与表格空白区同色（bg_card，浅色主题即白色），表格外区域不再发灰
        pipe_page.setProperty("role", "panel")
        pipe_page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        pipe_layout = QVBoxLayout(pipe_page)
        pipe_layout.setContentsMargins(6, 6, 6, 6)
        pipe_layout.setSpacing(4)
        pipe_layout.addWidget(self._pipe_table, 1)

        param_page = QWidget()
        # 页面底色与管材页一致（bg_card，role="panel" + WA_StyledBackground 同款）
        param_page.setProperty("role", "panel")
        param_page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        param_layout = QVBoxLayout(param_page)
        param_layout.setContentsMargins(6, 6, 6, 6)
        param_layout.setSpacing(4)
        param_layout.addWidget(self._param_table, 1)

        # 附属构筑物的工程量行（类别 / 项目 / 单位 三段合一的编辑界面）；
        # 其它类别不显示表格，空面板居中提示（多原则 Tab 的 placeholder 同款）
        qty_page = QWidget()
        qty_page.setProperty("role", "panel")
        qty_page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        qty_layout = QVBoxLayout(qty_page)
        qty_layout.setContentsMargins(6, 6, 6, 6)
        qty_layout.setSpacing(4)
        qty_layout.addWidget(self._qty_table, 1)
        self._qty_placeholder = QLabel(
            "仅附属构筑物可录入工程量行。\n"
            "选中附属构筑物后在此逐行录入类别｜项目｜单位｜值算式。"
        )
        self._qty_placeholder.setProperty("role", "placeholder")
        self._qty_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qty_placeholder.setWordWrap(True)
        self._qty_placeholder.setVisible(False)
        qty_layout.addWidget(self._qty_placeholder, 1)

        # 左右分设构件的「围护原则」页（v3）：四行（行头见 _LR_ROWS），
        # 未选分设的构件整页隐藏（setTabVisible）。合槽子节点的左侧行由父节点
        # 接管，置灰展示。v10 起挖填类型 / 管道基础分别归挖填降水原则与地基原则，
        # 不再因左右围护不一致而分侧取值，故本页不再出现这两项。
        lr_page = QWidget()
        lr_page.setProperty("role", "panel")
        lr_page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lr_layout = QVBoxLayout(lr_page)
        lr_layout.setContentsMargins(6, 6, 6, 6)
        lr_layout.setSpacing(4)
        self._lr_table = QTableWidget(0, 1)
        self._lr_table.setVerticalHeaderLabels([])
        self._lr_table.setHorizontalHeaderLabels(["取值"])
        self._lr_table.setProperty("cardHeader", True)
        self._lr_table.horizontalHeader().setHighlightSections(False)
        self._lr_table.verticalHeader().setVisible(True)
        self._lr_table.verticalHeader().setDefaultSectionSize(32)
        fixed_width_behavior(self._lr_table)
        self._lr_table.setColumnWidth(0, 170)
        self._lr_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._lr_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        lr_layout.addWidget(self._lr_table, 1)
        self._lr_placeholder = QLabel(
            "该构件未使用左右分设。\n"
            "在主表格「沟槽围护原则」列选择「左右分设」后在此设置左右原则与支撑。"
        )
        self._lr_placeholder.setProperty("role", "placeholder")
        self._lr_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lr_placeholder.setWordWrap(True)
        self._lr_placeholder.setVisible(False)
        lr_layout.addWidget(self._lr_placeholder, 1)

        detail.addTab(pipe_page, "管材")
        detail.addTab(param_page, "构件参数")
        detail.addTab(qty_page, "工程量")
        detail.addTab(lr_page, "围护原则")

        # 三个页签（管材/构件参数/工程量）在窄面板下会被省略并出现滚动箭头：
        # 按页签条完整宽度设最小宽度，保证全部页签可见
        detail.setMinimumWidth(detail.tabBar().sizeHint().width() + 16)
        self._detail_tabs = detail
        bottom.addWidget(detail)

        # 中：工程量表（定额工程量 / 清单工程量）
        bottom.addWidget(self._build_quantity_area())

        # 右：断面示意图（旧版 FormUnit 右侧 spltCtnerR.Panel2 + PNLpicCtrler）
        section_page = QWidget()
        section_layout = QVBoxLayout(section_page)
        section_layout.setContentsMargins(6, 6, 6, 6)
        section_layout.setSpacing(4)
        section_title = QLabel("断 面 示 意 图")
        section_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        section_layout.addWidget(section_title)
        from app.views.panels.section_view import SectionPanel

        self._section_view = SectionPanel()
        section_layout.addWidget(self._section_view, 1)
        bottom.addWidget(section_page)

        bottom.setStretchFactor(0, 2)
        bottom.setStretchFactor(1, 3)
        bottom.setStretchFactor(2, 2)
        # 管材/构件参数｜定额/清单｜断面图 默认宽度：左栏加宽以容下三个明细页签
        bottom.setSizes([500, 880, 286])
        return bottom

    def _build_quantity_area(self) -> QWidget:
        tabs = QTabWidget()
        if not is_mac():
            tabs.setDocumentMode(True)
        tabs.tabBar().setDrawBase(False)
        self._quantity_tables: dict[str, QTableWidget] = {}
        for name in ("定额工程量", "清单工程量"):
            page = QWidget()
            page.setProperty("role", "panel")
            page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(6, 6, 6, 6)
            page_layout.setSpacing(4)
            table = self._make_table(_QUANTITY_HEADERS, card_header=True)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setWordWrap(False)
            table.itemDoubleClicked.connect(self._show_expression_detail)
            # 列宽取自运行实例实测（定额/清单共用同一组），固定列宽不随父控件拉伸
            for index, width in enumerate(_QUANTITY_WIDTHS):
                table.setColumnWidth(index, width)
            self._quantity_tables[name] = table
            page_layout.addWidget(table, 1)
            tabs.addTab(page, name)
        self._quantity_tabs = tabs
        return tabs

    @staticmethod
    def _make_table(headers: list[str], *, card_header: bool = False) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        if card_header:
            # 明细面板页签里的表格：行头 / 列头底色与页签页面同色（bg_card），
            # 否则白底页面配一圈灰底表头（QSS 按 [cardHeader="true"] 命中）
            table.setProperty("cardHeader", True)
        table.setAlternatingRowColors(True)
        # 固定列宽（可拖动调整）：表格不随父控件拉伸，父控件宽时右侧留白、
        # 窄时出横向滚动条（全项目约定，见 table_width.fixed_width_behavior）
        fixed_width_behavior(table)
        # 选中单元格时对应列的列头不再加粗重绘（QSS 列头规则没有 :selected
        # 背景，highlightSections 的唯一表现是选中列列头文字变粗，见 CellFillTable）
        table.horizontalHeader().setHighlightSections(False)
        # 行高与 Quotor 计价主表一致（32px）：表格内嵌下拉框的纵向内边距
        # 已在 QSS 里压到 2px，32px 行高足以完整显示文字
        table.verticalHeader().setDefaultSectionSize(32)
        table.setWordWrap(False)
        table.setItemDelegate(_FocusCellDelegate(table))
        setattr(table, _FOCUS_OWNER_ATTR, False)
        return table

    def _focus_tables(self) -> list[QTableWidget]:
        """共享单元格焦点的六张表：主表格 + 管材/构件参数/工程量/定额/清单。"""
        return [
            self._element_table,
            self._pipe_table,
            self._param_table,
            self._qty_table,
            *self._quantity_tables.values(),
        ]

    def _detail_tables(self) -> list[QTableWidget]:
        """明细面板五张表（多选边框 / 选区互斥的作用范围）。"""
        return [
            self._pipe_table,
            self._param_table,
            self._qty_table,
            *self._quantity_tables.values(),
        ]

    def _mark_focus_table(self, table: QTableWidget) -> None:
        """把共享焦点转移到 table：只有它绘制当前单元格边框。"""
        for other in self._focus_tables():
            is_owner = other is table
            if getattr(other, _FOCUS_OWNER_ATTR, False) != is_owner:
                setattr(other, _FOCUS_OWNER_ATTR, is_owner)
                other.viewport().update()

    def _on_detail_selection_changed(self, source: QTableWidget) -> None:
        """四张明细表只能有一个处于多选状态：一张表出现新选区，其余三张自动取消。

        选区变化时强制重绘整个视口：拖拽扩选时 Qt 只重绘状态变化的单元格，
        而已选中单元格的内侧边（邻居新加入选中）也变了，不重绘会残留边框线。
        """
        if self._syncing_detail_selection:
            return
        self._syncing_detail_selection = True
        try:
            for other in self._detail_tables():
                if other is not source:
                    if other.selectionModel().hasSelection():
                        other.clearSelection()
                    other.viewport().update()
            source.viewport().update()  # 擦掉大边框内部因扩选残留的边框线
        finally:
            self._syncing_detail_selection = False

    def _on_detail_tab_changed(self, *_args) -> None:
        """切走 tab 时清空该 tab 下表格的多选（管材↔构件参数↔工程量、定额↔清单）。"""
        self._clear_detail_selections(
            self._pipe_table, self._param_table, self._qty_table
        )
        self._clear_detail_selections(*self._quantity_tables.values())

    def _clear_detail_selections(self, *tables: QTableWidget) -> None:
        if self._syncing_detail_selection:
            return
        self._syncing_detail_selection = True
        try:
            for table in tables:
                if table.selectionModel().hasSelection():
                    table.clearSelection()
        finally:
            self._syncing_detail_selection = False

    def _connect(self) -> None:
        self._vm.unit_loaded.connect(self._on_unit_loaded)
        self._vm.detail_loaded.connect(self._on_detail_loaded)
        self._vm.error_occurred.connect(lambda message: bus().status_message.emit(message, 4000))
        self._element_table.itemChanged.connect(self._on_element_item_changed)
        self._element_table.currentCellChanged.connect(self._on_current_element_changed)
        self._element_table.itemSelectionChanged.connect(self._on_element_selection_changed)
        self._pipe_table.itemChanged.connect(self._on_pipe_item_changed)
        self._param_table.itemChanged.connect(self._on_param_item_changed)
        self._qty_table.itemChanged.connect(self._on_qty_item_changed)
        # 共享单元格焦点：任一表被点选/键盘导航即成为焦点归属表
        for table in self._focus_tables():
            table.cellClicked.connect(lambda _row, _col, t=table: self._mark_focus_table(t))
            table.currentCellChanged.connect(
                lambda _r, _c, _pr, _pc, t=table: self._mark_focus_table(t)
            )
        setattr(self._element_table, _FOCUS_OWNER_ATTR, True)  # 初始焦点在主表格
        # 明细面板四张表：多选边框 + 选区互斥（一张表出现新选区，其余自动取消）
        self._syncing_detail_selection = False
        for table in self._detail_tables():
            setattr(table, _DETAIL_TABLE_ATTR, True)
            table.itemSelectionChanged.connect(
                lambda t=table: self._on_detail_selection_changed(t)
            )
        # 切走 tab 时清空该 tab 下表格的多选
        self._detail_tabs.currentChanged.connect(self._on_detail_tab_changed)
        self._quantity_tabs.currentChanged.connect(self._on_detail_tab_changed)
        bus().node_selected.connect(self._on_node_selected)
        # 新增构件获得焦点：面板在延后的表格重装落地后选中新行
        # （构件库插入、AI/MCP 新增共用一条路径）
        bus().element_focused.connect(self._on_element_focused)
        # 换成连接时先清空选中：夹带常量 None，走弱引用连接
        connect_weak(bus().project_closed, self, "_show_unit", None)
        connect_weak(bus().project_opened, self, "_show_unit", None)
        # 原则窗体确认修改：工程量与断面图重算（编辑过程中不刷新）
        bus().principle_changed.connect(self._on_principle_changed)
        # 原则增删改名 / 标段单位变化：整表重载（原则下拉、工程量、断面全刷新）
        bus().tree_structure_changed.connect(self._on_tree_structure_changed)

    # ------------------------------------------------------------------ 选中
    def _on_node_selected(self, node: TreeNode | None) -> None:
        if node is not None and node.is_unit:
            self._show_unit(node.id, node.name)
        # 选中其它节点时保留当前内容，切回来不用重新加载

    def _on_element_focused(self, unit_id: int, element_id: int) -> None:
        """新增构件获得焦点：记下待选中 id，表格延后重装落地后选中新行。"""
        if unit_id == self._unit_id:
            self._pending_select_id = element_id

    def _on_principle_changed(self) -> None:
        """原则窗体点击确认修改后：工程量与断面图按确认后的原则重算重绘。"""
        if self._unit_id is None:
            return
        self._fill_quantities()
        if self._multi_detail:
            self._section_view.show_multi()
        else:
            self._section_view.refresh()

    def _on_tree_structure_changed(self) -> None:
        """原则增删改名 / 标段单位变化：重载当前单位工程（含原则下拉、工程量、断面）。

        当前单位工程已被删除时退回占位页。
        """
        if self._unit_id is None:
            return
        from app.core.models import base as orm
        from app.core.models.models import Unit

        if orm.session().get(Unit, self._unit_id) is None:
            self._show_unit(None)
            return
        self.refresh()
        # 明细区（尤其「围护原则」tab 的左右下拉）也要按新原则表重建：refresh()
        # 只重载主表格，重新选中同一构件时 _sync_detail_to_selection 不再重填明细，
        # 下拉项会停留在旧原则列表——新增的原则选不到，只剩默认那一条。
        element_id = self._current_element_id()
        if element_id is not None and not self._multi_detail:
            self._show_single_detail(element_id)

    def _show_unit(self, unit_id: int | None, name: str = "") -> None:
        self._unit_id = unit_id
        self._multi_detail = False
        self._current_detail_id = None
        self._pending_select_id = None
        # 切换单位工程 / 关闭工程：样板不再有效，格式刷自动结束（撤销未生效的待刷）
        self._cancel_format_painter()
        has_unit = unit_id is not None
        self._placeholder.setVisible(not has_unit)
        self._work_area.setVisible(has_unit)
        if not has_unit:
            self._vm.load_unit(None)
            self._element_table.setRowCount(0)
            self._pipe_buttons.clear_row_buttons()  # 行尾「-」按钮显式销毁
            self._pipe_table.setRowCount(0)
            self._param_table.setRowCount(0)
            self._qty_table.setRowCount(0)
            # 未选中单位工程：工程量页签同样显示空面板提示
            self._qty_table.setVisible(False)
            self._qty_placeholder.setVisible(True)
            self._section_view.set_element(None)
            bus().ai_context_changed.emit({"element_id": None, "element_name": ""})
            return
        self._vm.load_unit(unit_id)

    # ------------------------------------------------------------------ 构件表
    def _on_unit_loaded(self, unit_id: int, rows: list[ElementRow]) -> None:
        if unit_id != self._unit_id:
            return
        keep_element = self._current_element_id()
        keep_group = self._group_id_at(self._element_table.currentRow())
        keep_column = self._element_table.currentColumn()
        if self._ids_stale:
            # 撤销 / 重做重建了工作库：旧 id 在新库里要么缺失（_restore_current_element
            # 会回落第 0 行）要么撞到别的构件（选中跳到毫不相干的行）——一律不信，
            # 选中由撤销快照按行号恢复（restore_ui_state 紧随其后）
            keep_element = None
            keep_group = None
            self._ids_stale = False
        pending = self._pending_select_id
        self._pending_select_id = None
        self._loading = True
        try:
            _clear_cell_widgets(self._element_table)  # 旧内嵌下拉框显式销毁，避免残留叠加
            self._rows_cache = rows
            self._element_table.setRowCount(len(rows))
            enclosure_names = _combo_names(project_io.enclosure_names(), rows, "pe_name")
            foundation_names = _combo_names(project_io.foundation_names(), rows, "pf_name")
            precipitation_names = _combo_names(project_io.precipitation_names(), rows, "pp_name")
            width_names = _combo_names(project_io.width_names(), rows, "pw_name")
            for index, row in enumerate(rows):
                self._fill_element_row(
                    index, row, enclosure_names, foundation_names, precipitation_names, width_names
                )
            self._apply_group_visibility()
        finally:
            self._loading = False
        self._loading = True
        try:
            self._restore_current_element(
                pending if pending is not None else keep_element,
                keep_column,
                None
                if (pending is not None or keep_element is not None)
                else keep_group,
            )
        finally:
            self._loading = False
        # 恢复出的选中索引可能与重载前完全相同（不发 currentCellChanged），
        # 这里显式同步一次，保证父行/构件的明细一定按最新数据重算。
        self._sync_detail_to_selection()
        # 合槽父行：上一步已重建占位、成员合计工程量与整槽断面；不能再走下面
        # 按构件 id 的分支（_current_element_id() 为 None 会触发 _clear_detail，
        # 把刚填好的父行明细与断面全部清掉）。
        if self._group_id_at(self._element_table.currentRow()) is not None:
            return
        if self._current_element_id() is None:
            # 表格空（撤销 / 重做到没有构件的状态，或构件被删光）：明细面板
            # 不能停留在上一个构件的内容上
            self._clear_detail()
            return
        self._refresh_grouped_lr_tab()
        self._refresh_section_for(self._current_element_id())

    def _refresh_grouped_lr_tab(self) -> None:
        """埋深变化后刷新合槽子节点的「围护原则」tab 左右侧可编辑状态。

        同一条构件重新加载时选中行不变，``_sync_detail_to_selection`` 只刷新
        工程量、不会重建 LR tab；而合槽子节点的某一侧是否可选取决于与相邻
        构件的槽底深度比较（规则 4 / 5），埋深一改就必须重建。
        """
        element_id = self._current_element_id()
        if element_id is None:
            return
        from app.viewmodels.unit_vm import _element

        element = _element(element_id)
        if element is None or element.group_id is None:
            return
        self._loading = True
        try:
            self._fill_lr_tab(element)
        finally:
            self._loading = False

    def _fill_quantities(self) -> None:
        """填充工程量表：显示主表格当前选中行的工程量与计算表达式。

        单行 → 该行的定额/清单；多行 → 各键求和（表达式用 " + " 连接，
        仍可直接求值复核）。
        """
        from app.core.calc.tracer import fmt as calc_fmt
        from app.core.calc.tracer import order_key, sorted_items
        from app.viewmodels.unit_vm import compute_unit

        if self._unit_id is None:
            for table in self._quantity_tables.values():
                table.setRowCount(0)
            return
        _summary, detail = compute_unit(self._unit_id)
        per_element = {row.id: (row, dq) for row, dq in detail}
        ids = self._selected_element_ids() or (
            [self._current_detail_id] if self._current_detail_id else []
        )
        if not ids and getattr(self, "_group_member_ids", None):
            ids = list(self._group_member_ids)  # 合槽父行选中：成员合计
        chosen = [per_element[i] for i in ids if i in per_element]
        if not chosen:
            for table in self._quantity_tables.values():
                table.setRowCount(0)
            return

        digests = self._quantity_tables["定额工程量"]
        digests.setRowCount(0)
        if len(chosen) == 1:
            quantities = sorted_items(chosen[0][1])
        else:
            quantities = self._merge_quantities([dq for _row, dq in chosen])
        digests.setRowCount(len(quantities))
        for row_index, quantity in enumerate(quantities):
            parts = quantity.key.split("|")
            category = parts[0] if parts else ""
            item_name = parts[1] if len(parts) > 1 else ""
            unit_name = parts[2] if len(parts) > 2 else ""
            for column, text in enumerate(("", category, item_name, unit_name)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                digests.setItem(row_index, column, item)
            expression = QTableWidgetItem(quantity.expression)
            expression.setFlags(expression.flags() & ~Qt.ItemFlag.ItemIsEditable)
            expression.setData(Qt.ItemDataRole.UserRole, quantity.expression)
            expression.setToolTip(_expression_detail(quantity))
            digests.setItem(row_index, _QCOL_EXPRESSION, expression)
            amount = QTableWidgetItem(calc_fmt(quantity.value))
            amount.setFlags(amount.flags() & ~Qt.ItemFlag.ItemIsEditable)
            digests.setItem(row_index, _QCOL_AMOUNT, amount)

        listing = self._quantity_tables["清单工程量"]
        listing.clearSpans()
        listing.setRowCount(0)
        row_index = 0
        from app.core.models.models import category_name
        from app.resources.qss.theme import ThemeManager

        highlight = QBrush(QColor(ThemeManager.instance().current().primary_soft))

        def _shade_row(row: int) -> None:
            for column in range(len(_QUANTITY_HEADERS)):
                cell = listing.item(row, column)
                if cell is None:
                    cell = QTableWidgetItem("")
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    listing.setItem(row, column, cell)
                cell.setBackground(highlight)

        # 多选时先给一行合计（工程量 = 选中行数量求和）
        if len(chosen) > 1:
            listing.setRowCount(row_index + 1)
            total_amount = sum(element_row.amount_value for element_row, _dq in chosen)
            for offset, text in enumerate(
                ("清单项目", f"（{len(chosen)} 行合计）", "", "", calc_fmt(total_amount))
            ):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                listing.setItem(row_index, offset, item)
            _shade_row(row_index)
            row_index += 1

        for element_row, dq in chosen:
            # 清单项目行（浅蓝标记行）：类别 / 项目（规格）/ 单位 /
            # 工程量 = 用户输入的数量算式的计算结果 / 计算表达式 = 该算式
            listing.setRowCount(row_index + 1)
            header_cells = (
                "清单项目",
                category_name(element_row.category),
                element_row.spec or element_row.name,
                element_row.unit,
                calc_fmt(element_row.amount_value),
                element_row.amount,
            )
            for offset, text in enumerate(header_cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                listing.setItem(row_index, offset, item)
            _shade_row(row_index)
            row_index += 1

            # 定额拆解行（原样式）
            for quantity in sorted_items(dq):
                listing.setRowCount(row_index + 1)
                parts = quantity.key.split("|")
                cells = (
                    "",
                    parts[0] if parts else "",
                    parts[1] if len(parts) > 1 else "",
                    parts[2] if len(parts) > 2 else "",
                    calc_fmt(quantity.value),
                    quantity.expression,
                )
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if column == _QCOL_EXPRESSION:
                        item.setData(Qt.ItemDataRole.UserRole, quantity.expression)
                        item.setToolTip(_expression_detail(quantity))
                    listing.setItem(row_index, column, item)
                row_index += 1

    @staticmethod
    def _merge_quantities(qlists: list) -> list:
        """把多个构件的工程量按键合并：数值求和、表达式用 " + " 连接，步骤逐条累加。"""
        from app.core.calc.tracer import order_key

        merged: dict[str, dict] = {}
        for element_index, dq in enumerate(qlists, start=1):
            for quantity in sorted(dq.items(), key=lambda q: (order_key(q.key), q.key)):
                entry = merged.setdefault(quantity.key, {"value": 0.0, "exprs": [], "steps": []})
                entry["value"] += quantity.value
                if quantity.value or quantity.expression not in ("", "0"):
                    entry["exprs"].append(quantity.expression)
                entry["steps"].extend(
                    (f"[构件{element_index}] {note}" if note else f"[构件{element_index}]", text)
                    for note, text in quantity.steps()
                )

        class _Merged:
            """多选合并行：算式是各构件算式的 " + " 连接，步骤按构件分组。"""

            __slots__ = ("key", "value", "expression", "_steps")
            #: 展示层据此换用“按构件列出”的说法（只有同一构件内的步骤才构成该构件的算式）
            per_element = True

            def __init__(self, key: str, value: float, expression: str, steps: list) -> None:
                self.key = key
                self.value = value
                self.expression = expression
                self._steps = steps

            def steps(self) -> list:
                return self._steps

        return [
            _Merged(key, entry["value"], " + ".join(entry["exprs"]) or "0", entry["steps"])
            for key, entry in merged.items()
        ]

    def _show_expression_detail(self, item: QTableWidgetItem) -> None:
        """双击“计算表达式”列：弹窗展示完整算式与中间步骤（各步说明 + 该步算式）。"""
        text = item.toolTip()
        if not text:
            return
        FramelessMessageBox.information(
            self, "计算表达式", f"<pre style='white-space:pre-wrap'>{text}</pre>"
        )

    def _fill_element_row(
        self,
        index: int,
        row,
        enclosure_names: list[str],
        foundation_names: list[str],
        precipitation_names: list[str],
        width_names: list[str],
    ) -> None:
        if isinstance(row, GroupRow):
            self._fill_group_row(index, row)
            return
        name_item = QTableWidgetItem(row.name)
        name_item.setData(_ELEMENT_ROLE, row.id)
        if row.group_id is not None:
            # 合槽子节点：委托画缩进竖线（组内从上到下 = 沟槽从左到右）
            name_item.setData(_TREE_ROLE, {"indent": 1, "has_children": False, "expanded": False})
            name_item.setToolTip(f"合槽组成员（左起第 {row.group_index + 1} 条），上下移动即左右排序。")
        self._element_table.setItem(index, _COL_NAME, name_item)

        category_item = QTableWidgetItem(_category_abbr(row.category))
        category_item.setFlags(category_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        category_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        category_item.setForeground(QBrush(_secondary_color()))
        category_item.setToolTip(category_name(row.category))
        self._element_table.setItem(index, _COL_CATEGORY, category_item)

        spec_item = QTableWidgetItem(row.spec)
        spec_item.setFlags(spec_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        spec_item.setForeground(QBrush(_secondary_color()))
        self._element_table.setItem(index, _COL_SPEC, spec_item)

        depth_item = QTableWidgetItem(row.depth)
        depth_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._element_table.setItem(index, _COL_DEPTH, depth_item)
        _apply_expression_hint(depth_item, row.depth, row.depth_error)

        unit_item = QTableWidgetItem(row.unit)
        unit_item.setFlags(unit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        unit_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        unit_item.setForeground(QBrush(_secondary_color()))
        self._element_table.setItem(index, _COL_UNIT, unit_item)

        amount_item = QTableWidgetItem(row.amount)
        amount_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if row.group_id is not None:
            # 合槽子节点：数量强制取父节点（只读，改父行即同步）
            amount_item.setFlags(amount_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            amount_item.setForeground(QBrush(_secondary_color()))
            amount_item.setToolTip("合槽子构件数量由父节点统一控制（只读）。")
        self._element_table.setItem(index, _COL_AMOUNT, amount_item)
        _apply_expression_hint(amount_item, row.amount, row.amount_error)

        if row.group_id is not None:
            # 合槽子节点：围护原则强制「左右分设」，具体左右侧在「围护原则」tab 选
            pe_item = QTableWidgetItem(LR_PE_TEXT)
            pe_item.setFlags(pe_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            pe_item.setForeground(QBrush(_secondary_color()))
            pe_item.setToolTip(
                "合槽子节点强制左右分设：左右侧围护原则在下方「围护原则」tab 选择。"
            )
            self._element_table.setItem(index, _COL_PE, pe_item)
        else:
            pe_combo = QComboBox()
            # 普通构件：库原则 + 「左右分设」占位
            pe_combo.addItems(enclosure_names + ([] if LR_PE_TEXT in enclosure_names else [LR_PE_TEXT]))
            pe_combo.setCurrentText(row.pe_name)
            pe_combo.currentTextChanged.connect(
                lambda text, element_id=row.id: self._vm.set_element_field(
                    element_id, "pe_name", text
                )
            )
            self._element_table.setCellWidget(index, _COL_PE, pe_combo)

        pf_combo = QComboBox()
        pf_combo.addItems(foundation_names)
        pf_combo.setCurrentText(row.pf_name)
        pf_combo.currentTextChanged.connect(
            lambda text, element_id=row.id: self._vm.set_element_field(element_id, "pf_name", text)
        )
        self._element_table.setCellWidget(index, _COL_PF, pf_combo)

        pp_combo = QComboBox()
        pp_combo.addItems(precipitation_names)
        pp_combo.setCurrentText(row.pp_name)
        pp_combo.currentTextChanged.connect(
            lambda text, element_id=row.id: self._vm.set_element_field(element_id, "pp_name", text)
        )
        self._element_table.setCellWidget(index, _COL_PP, pp_combo)

        pw_combo = QComboBox()
        pw_combo.addItems(width_names)
        pw_combo.setCurrentText(row.pw_name)
        pw_combo.currentTextChanged.connect(
            lambda text, element_id=row.id: self._vm.set_element_field(element_id, "pw_name", text)
        )
        self._element_table.setCellWidget(index, _COL_PW, pw_combo)

        source_item = QTableWidgetItem(row.source)
        source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        source_item.setForeground(QBrush(_secondary_color()))
        self._element_table.setItem(index, _COL_SOURCE, source_item)

    def _fill_group_row(self, index: int, row: GroupRow) -> None:
        """合槽父节点行：名称 / 数量（L_组）可编辑；埋深恒 "-"、不参与计算。"""
        name_item = QTableWidgetItem(row.name)
        name_item.setData(_ELEMENT_ROLE, (_GROUP_ROLE_TAG, row.id))
        name_item.setData(
            _TREE_ROLE,
            {"indent": 0, "has_children": True, "expanded": row.id not in self._collapsed_group_ids},
        )
        name_item.setToolTip(
            f"合槽组（{row.member_count} 条构件，从上到下 = 从左到右）。"
            "父节点不持有工程量，仅作子构件合计视图；围护 / 面宽原则全部由子构件自己决定。"
            "点击 +/- 展开或收起成员行。"
        )
        brush = QBrush(QColor(ThemeManager.instance().current().primary_soft))
        for column in range(len(_ELEMENT_HEADERS)):
            item = QTableWidgetItem()
            item.setBackground(brush)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._element_table.setItem(index, column, item)
        self._element_table.setItem(index, _COL_NAME, name_item)
        # 名称可编辑（改的是父节点名称）
        name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable)

        category_item = self._element_table.item(index, _COL_CATEGORY)
        category_item.setText("组")
        category_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        spec_item = self._element_table.item(index, _COL_SPEC)
        spec_item.setText(row.spec)
        depth_item = self._element_table.item(index, _COL_DEPTH)
        depth_item.setText(row.depth)
        depth_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        depth_item.setToolTip("父节点埋深不参与计算（显示 -），组内槽深由各子构件自己的埋深推导。")
        depth_item.setForeground(QBrush(_secondary_color()))
        unit_item = self._element_table.item(index, _COL_UNIT)
        unit_item.setText("m")
        unit_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        amount_item = self._element_table.item(index, _COL_AMOUNT)
        amount_item.setText(row.amount)
        amount_item.setToolTip("L_组：子构件数量统一取此值，修改后同步全部子构件。")
        amount_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # 数量列可编辑（改父节点即同步全部子构件）
        amount_item.setFlags(amount_item.flags() | Qt.ItemFlag.ItemIsEditable)
        _apply_expression_hint(amount_item, row.amount, row.amount_error)

        # 父节点四个原则单元格一律留空：围护 / 地基 / 挖填降水 / 面宽
        # 全部由子构件自己的原则决定
        for column, tooltip in (
            (_COL_PE, "父节点不选围护原则：左边坡取首构件左原则、右边坡取末构件右原则。"),
            (_COL_PF, "父节点不选地基处理原则：每条构件按自己的地基处理原则计算。"),
            (_COL_PP, "父节点不选挖填降水原则：每条构件按自己的挖填降水原则计算。"),
            (_COL_PW, "父节点不选工作面宽原则：每条构件按自己的面宽原则确定工作面。"),
        ):
            item = self._element_table.item(index, column)
            item.setText("")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QBrush(_secondary_color()))
            item.setToolTip(tooltip)

    def _on_group_toggle_requested(self, row_index: int) -> None:
        """点击合槽父行 +/- 方框：切换该组成员行的显示/隐藏（Quotor 组合定额同款）。"""
        item = self._element_table.item(row_index, _COL_NAME)
        if item is None:
            return
        data = item.data(_ELEMENT_ROLE)
        if not (isinstance(data, tuple) and data[0] == _GROUP_ROLE_TAG):
            return
        group_id = data[1]
        collapsed = group_id not in self._collapsed_group_ids
        if collapsed:
            self._collapsed_group_ids.add(group_id)
        else:
            self._collapsed_group_ids.discard(group_id)
        # 图标重绘走 setData（触发 itemChanged），用 _loading 挡住重命名逻辑
        self._loading = True
        try:
            item.setData(
                _TREE_ROLE,
                {"indent": 0, "has_children": True, "expanded": not collapsed},
            )
            self._apply_group_visibility()
        finally:
            self._loading = False
        # 焦点落在被隐藏的成员行上时移回父行，避免选中态悬空
        current = self._element_table.currentRow()
        if current >= 0 and self._element_table.isRowHidden(current):
            _select_row(self._element_table, row_index, _COL_NAME)
            self._sync_detail_to_selection()

    def _apply_group_visibility(self) -> None:
        """按收起集合显隐成员行：收起的组，其成员行全部隐藏，父行恒显示。"""
        for index, row in enumerate(self._rows_cache):
            if isinstance(row, ElementRow) and row.group_id is not None:
                self._element_table.setRowHidden(
                    index, row.group_id in self._collapsed_group_ids
                )

    def _on_element_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        row = item.row()
        group_id = self._group_id_at(row)
        if group_id is not None:
            # 合槽父节点行：名称 / 数量（L_组）可编辑
            if item.column() == _COL_NAME:
                from app.viewmodels.unit_vm import update_group

                update_group(group_id, name=item.text().strip())
            elif item.column() == _COL_AMOUNT:
                from app.viewmodels.unit_vm import update_group

                text = item.text()
                _apply_expression_hint(item, text, "")
                update_group(group_id, amount=text)
            return
        element_id = self._element_id_at(row)
        if element_id is None:
            return
        field = {_COL_NAME: "name", _COL_DEPTH: "depth", _COL_AMOUNT: "amount"}.get(item.column())
        if field is None:
            return
        text = item.text()
        if field == "name":
            self._vm.set_element_field(element_id, field, text)
            return
        _apply_expression_hint(item, text, "")
        self._vm.set_element_field(element_id, field, text)
        label = "埋深" if field == "depth" else "数量"
        try:
            value = evaluate(text)
        except EvalError as error:
            bus().status_message.emit(f"{label}算式错误：{error}", 6000)
        else:
            bus().status_message.emit(f"{label} {text} = {format_number(value)}", 4000)

    def _on_current_element_changed(self, row: int, _column: int, _previous_row: int, _previous_column: int) -> None:
        if self._loading:
            return
        self._sync_detail_to_selection()

    def _on_element_selection_changed(self) -> None:
        if self._loading:
            return
        self._sync_detail_to_selection()

    # ------------------------------------------------------------------ 明细面板跟随选中行
    def _sync_detail_to_selection(self) -> None:
        """明细面板（管材/参数、围护原则、工程量、断面）跟随主表格当前选中行。

        多选（≥2 行）→ 左侧显示 *多种管材/*多种参数、断面显示 *多种断面、
        工程量显示选中行求和；合槽父行 → 成员合计工程量 + 整槽断面；
        单行 → 显示该行内容。
        """
        if self._format_painter_active and not self._loading:
            self._schedule_format_painter()
        ids = self._selected_element_ids()
        if len(ids) >= 2:
            self._show_multi_detail()
            return
        if not ids:
            group_id = self._selected_group_row_id()
            if group_id is not None:
                self._show_group_detail(group_id)
                return
        element_id = ids[0] if ids else self._current_element_id()
        if element_id is None:
            if self._current_detail_id is not None or self._multi_detail:
                self._clear_detail()
            return
        if self._multi_detail or element_id != self._current_detail_id:
            self._show_single_detail(element_id)
        else:
            self._fill_quantities()  # 同一行重新选中：只刷新工程量

    # ------------------------------------------------------------------ 格式刷
    def set_format_painter(self, on: bool) -> None:
        """格式刷开关（主窗体工具栏按钮 / 编辑菜单调用）。

        开启时以当前选中构件为样板；随后选中的构件自动同步其四项原则
        （围护 / 地基 / 挖填降水 / 面宽），**生效一次后自动退出**；
        Esc 或再次点击可提前结束。
        """
        if on:
            source_id = self._current_element_id()
            if source_id is None:
                self._format_painter_active = False
                self._format_painter_source = None
                bus().status_message.emit("请先选中一条构件，再使用格式刷。", 4000)
                self.format_painter_changed.emit(False)
                return
            self._format_painter_timer.stop()
            self._format_painter_active = True
            self._format_painter_source = source_id
            self._set_format_painter_cursor(True)
            bus().status_message.emit(
                "格式刷已取样板：点选或框选其他构件即同步其四项原则（生效一次后自动退出，Esc 取消）。", 0
            )
        else:
            self._cancel_format_painter()

    def _set_format_painter_cursor(self, active: bool) -> None:
        """格式刷状态期间把鼠标换成刷形光标（应用级覆盖，退出即恢复原样）。

        热点在刷毛尖端（图标左下 (3, 19)），点选的位置就是刷毛指的位置。
        """
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        if active:
            if self._format_painter_cursor_active:
                return
            from app.views.widgets.frameless_dialog import load_icon

            color = ThemeManager.instance().current().text_primary
            pixmap = load_icon("paintbrush", color=color, size=24).pixmap(24, 24)
            self._format_painter_cursor_active = True
            QApplication.setOverrideCursor(QCursor(pixmap, 3, 19))
        else:
            if not self._format_painter_cursor_active:
                return
            self._format_painter_cursor_active = False
            QApplication.restoreOverrideCursor()

    def _cancel_format_painter(self) -> None:
        if not self._format_painter_active and self._format_painter_source is None:
            return
        self._format_painter_timer.stop()
        self._format_painter_active = False
        self._format_painter_source = None
        self._set_format_painter_cursor(False)
        self.format_painter_changed.emit(False)
        bus().status_message.emit("", 0)

    def _schedule_format_painter(self) -> None:
        """选中变化时的格式刷调度（防抖）：以**最后一次选中**为准，一次刷完。

        拖选 / Ctrl·Shift 多选的选中是逐步发生的（每次都会触发选中事件），
        不能在第一个事件就生效退出；这里在选中包含样板以外的构件时启动
        短防抖定时器，选中继续变化就重置，停顿片刻后整体生效一次。
        只选中样板（或没选中构件）时保持待刷并撤销未生效的定时。
        """
        if not self._format_painter_active:
            return
        source_id = self._format_painter_source
        if any(element_id != source_id for element_id in self._selected_element_ids()):
            self._format_painter_timer.start()
        else:
            self._format_painter_timer.stop()

    def _flush_format_painter(self) -> None:
        """防抖到点：把样板构件的四项原则刷到当前选中的构件上，然后自动退出。"""
        if not self._format_painter_active:
            return
        source_id = self._format_painter_source
        # 先退出再刷：update_element 触发表格重载，重载路径不得再进入格式刷调度
        self._format_painter_active = False
        self._format_painter_source = None
        self._set_format_painter_cursor(False)
        self.format_painter_changed.emit(False)
        from app.core.models.models import LR_PE_TEXT
        from app.viewmodels.unit_vm import _element, update_element

        source = _element(source_id)
        if source is None:
            bus().status_message.emit("格式刷：样板构件已不存在，已退出。", 4000)
            return
        source_pe = source.pe_name
        if source_pe == LR_PE_TEXT:
            # 左右分设样板（合槽成员）：取左原则作为普通构件的围护原则
            source_pe = source.pe_left_name or source.pe_right_name or ""
        changed = 0
        for element_id in self._selected_element_ids():
            if element_id == source_id:
                continue
            element = _element(element_id)
            if element is None:
                continue
            fields: dict = {}
            if element.group_id is None and source_pe and element.pe_name != source_pe:
                fields["pe_name"] = source_pe
            if source.pf_name and element.pf_name != source.pf_name:
                fields["pf_name"] = source.pf_name
            if source.pp_name and element.pp_name != source.pp_name:
                fields["pp_name"] = source.pp_name
            if source.pw_name and element.pw_name != source.pw_name:
                fields["pw_name"] = source.pw_name
            if not fields:
                continue
            update_element(element_id, **fields)
            changed += 1
        if changed:
            bus().status_message.emit(
                f"格式刷：已同步 {changed} 条构件的原则，已自动退出格式刷。", 4000
            )
        else:
            bus().status_message.emit("格式刷：目标与样板原则一致，已退出。", 4000)

    def _show_group_detail(self, group_id: int) -> None:
        """合槽父行选中：明细占位 + 成员合计工程量 + 整槽断面图。"""
        from app.core.models import base as orm
        from app.core.models.models import TrenchGroup

        self._multi_detail = True
        self._vm.clear_detail()  # 父行没有构件明细，别让后续重载补发上一个构件的内容
        self._current_detail_id = None
        group = orm.session().get(TrenchGroup, group_id)
        self._group_member_ids = (
            [member.id for member in sorted(group.members, key=lambda item: (item.order_no, item.id))]
            if group is not None
            else []
        )
        self._update_pipe_buttons(None)
        self._fill_multi_placeholders()
        self._section_view.set_group(group_id)
        self._fill_quantities()
        bus().ai_context_changed.emit({"element_id": None, "element_name": ""})

    def _show_single_detail(self, element_id: int) -> None:
        self._multi_detail = False
        self._current_detail_id = element_id
        self._group_member_ids = []
        self._vm.load_detail(element_id)
        self._refresh_section_for(element_id)
        self._fill_quantities()
        from app.viewmodels.unit_vm import _element

        element = _element(element_id)
        bus().ai_context_changed.emit(
            {
                "element_id": element_id,
                "element_name": element.name if element is not None else "",
            }
        )

    def _refresh_section_for(self, element_id: int | None) -> None:
        """断面图跟随选中构件：合槽成员也画整个合槽断面。

        选中的是合槽组成员时看的是整槽全景（与选中父行一致），普通构件
        才画自己的单管断面。
        """
        from app.viewmodels.unit_vm import _element

        element = _element(element_id) if element_id is not None else None
        if element is not None and element.group_id is not None:
            self._section_view.set_group(element.group_id)
        else:
            self._section_view.set_element(element_id)

    def _show_multi_detail(self) -> None:
        self._multi_detail = True
        self._vm.clear_detail()  # 多选没有单一构件明细（同上）
        self._current_detail_id = None
        self._group_member_ids = []
        # 多选显示占位行：增删没有明确目标构件，按钮一律禁用
        self._update_pipe_buttons(None)
        self._fill_multi_placeholders()
        self._section_view.show_multi()
        self._fill_quantities()
        bus().ai_context_changed.emit({"element_id": None, "element_name": ""})

    def _fill_multi_placeholders(self) -> None:
        """管材 / 构件参数 / 工程量三张表显示居中的“*多种…”占位行。"""
        # 多选下增删没有明确目标行：行尾「-」全部销毁，按钮列整列隐藏
        # （参数表没有按钮列，无需处理）
        self._pipe_buttons.clear_row_buttons()
        self._qty_buttons.clear_row_buttons()
        self._qty_buttons.set_visible(False)
        # 多选恢复显示工程量表（非构筑物选中态把它换成了空面板提示）
        self._qty_table.setVisible(True)
        self._qty_placeholder.setVisible(False)
        _clear_cell_widgets(self._lr_table)
        self._lr_table.setRowCount(0)
        self._lr_table.setVisible(False)
        self._lr_placeholder.setVisible(True)
        for table, text in (
            (self._pipe_table, "*多种管材"),
            (self._param_table, "*多种参数"),
            (self._qty_table, "*多种工程量"),
        ):
            table.clearSpans()
            table.setRowCount(1)
            placeholder = QTableWidgetItem(text)
            placeholder.setFlags(Qt.ItemFlag.ItemIsEnabled)
            placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setForeground(QBrush(_secondary_color()))
            table.setItem(0, 0, placeholder)
            table.setSpan(0, 0, 1, table.columnCount())

    def _clear_detail(self) -> None:
        """主表格没有选中行（表格空 / 撤销回到没有构件的状态）：清空明细面板。

        此前无选中时各路径直接返回，管材 / 构件参数表会残留上一个构件的
        内容——撤销 / 重做到某单位工程没有构件的状态时，下方面板显示的
        还是撤销前的过期参数。工程量与断面图随之清空，多原则页签、AI
        上下文一并复位。
        """
        self._multi_detail = False
        self._vm.clear_detail()  # 无选中构件：清掉明细目标，避免重载补发过期明细
        self._current_detail_id = None
        self._group_member_ids = []
        self._pipe_buttons.clear_row_buttons()
        self._pipe_buttons.set_visible(False)
        self._pipe_table.setRowCount(0)
        self._param_table.clearSpans()
        # 候选参数列是按上一个构件动态追加的，一并撤掉（回到三列基础布局）
        self._param_table.setColumnCount(len(_PARAM_HEADERS))
        self._param_table.setHorizontalHeaderLabels(list(_PARAM_HEADERS))
        self._param_table.setRowCount(0)
        self._qty_buttons.clear_row_buttons()
        self._qty_buttons.set_visible(False)
        self._qty_table.clearSpans()
        self._qty_table.setRowCount(0)
        self._qty_table.setVisible(False)
        self._qty_placeholder.setVisible(True)
        _clear_cell_widgets(self._lr_table)
        self._lr_table.setRowCount(0)
        self._lr_table.setVisible(False)
        self._lr_placeholder.setVisible(True)
        self._section_view.set_element(None)
        self._fill_quantities()
        bus().ai_context_changed.emit({"element_id": None, "element_name": ""})

    def _current_element_id(self) -> int | None:
        return self._element_id_at(self._element_table.currentRow())

    def _element_id_at(self, row: int) -> int | None:
        item = self._element_table.item(row, _COL_NAME) if row >= 0 else None
        if item is None:
            return None
        data = item.data(_ELEMENT_ROLE)
        if isinstance(data, tuple):
            return None  # 合槽父节点行（不是构件）
        return data

    def _group_id_at(self, row: int) -> int | None:
        """该行若是合槽父节点行，返回组 id；否则 None。"""
        item = self._element_table.item(row, _COL_NAME) if row >= 0 else None
        if item is None:
            return None
        data = item.data(_ELEMENT_ROLE)
        if isinstance(data, tuple) and data[0] == _GROUP_ROLE_TAG:
            return int(data[1])
        return None

    def _insert_anchor_element_id(self) -> int | None:
        """构件库插入锚点（新条目插到该构件之前）；None = 追加末尾。

        普通构件取当前行下一行的构件；选中合槽父行或合槽子条目时，锚点取
        整组合槽所有条目之后的下一条构件，新条目不会插进合槽组内部。
        """
        row_index = self._element_table.currentRow()
        if row_index < 0 or row_index >= len(self._rows_cache):
            return None
        row = self._rows_cache[row_index]
        if isinstance(row, GroupRow):
            return self._element_id_after_group(row.id)
        if isinstance(row, ElementRow) and row.group_id is not None:
            return self._element_id_after_group(row.group_id)
        return self._element_id_at(row_index + 1)

    def _element_id_after_group(self, group_id: int) -> int | None:
        """合槽组最后一条成员之后的下一条构件 id；组在末尾时为 None。"""
        last_index = -1
        for index, row in enumerate(self._rows_cache):
            if isinstance(row, GroupRow):
                if row.id == group_id:
                    last_index = index
            elif isinstance(row, ElementRow) and row.group_id == group_id:
                last_index = index
        if last_index < 0:
            return None
        for index in range(last_index + 1, len(self._rows_cache)):
            row = self._rows_cache[index]
            if isinstance(row, ElementRow):
                return row.id
        return None

    def _restore_current_element(
        self, element_id: int | None, column: int, group_id: int | None = None
    ) -> None:
        """重建表格后恢复选中行；本来没有选中就选第一行，让明细区直接可用。

        ``group_id`` 用于恢复合槽父行的选中：父行不是构件（``_element_id_at``
        恒为 None），只按构件 id 恢复会让编辑父节点后选中跳到第 0 行。
        """
        if self._element_table.rowCount() == 0:
            return
        if element_id is None and group_id is None:
            _select_row(self._element_table, 0, max(0, column))
            return
        for row in range(self._element_table.rowCount()):
            if element_id is not None:
                if self._element_id_at(row) == element_id:
                    _select_row(self._element_table, row, max(0, column))
                    return
            elif self._group_id_at(row) == group_id:
                _select_row(self._element_table, row, max(0, column))
                return
        _select_row(self._element_table, 0, max(0, column))

    def refresh(self) -> None:
        """重新加载当前单位工程（主题切换、树结构变化时用）。"""
        if self._unit_id is not None:
            self._vm.load_unit(self._unit_id)

    def ui_state(self) -> dict:
        """撤销快照携带的工作台状态：主表格焦点/滚动 + 明细与工程量页签。

        与项目树一样按位置记录——撤销恢复会重建工作库，构件 id 全部改变，
        只有行序跨快照稳定（brackets2 快照携带焦点单元格/滚动位置同款）。
        """
        table = self._element_table
        return {
            "cell": (table.currentRow(), table.currentColumn()),
            "scroll": (table.horizontalScrollBar().value(), table.verticalScrollBar().value()),
            "detail_tab": self._detail_tabs.currentIndex(),
            "qty_tab": self._quantity_tabs.currentIndex(),
        }

    def restore_ui_state(self, state) -> None:
        """撤销 / 重做后恢复工作台状态（须在主表格按新数据装填后调用）。

        行号越界（如重做落到内容更少的快照）时收敛到相邻行；-1 表示快照
        里本来就没有选中，保持不选中。
        """
        if not isinstance(state, dict) or self._unit_id is None:
            return
        index = state.get("detail_tab")
        if isinstance(index, int) and 0 <= index < self._detail_tabs.count():
            self._detail_tabs.setCurrentIndex(index)
        index = state.get("qty_tab")
        if isinstance(index, int) and 0 <= index < self._quantity_tabs.count():
            self._quantity_tabs.setCurrentIndex(index)
        table = self._element_table
        cell = state.get("cell")
        if isinstance(cell, (tuple, list)) and len(cell) == 2 and table.rowCount() > 0:
            try:
                row, column = int(cell[0]), int(cell[1])
            except (TypeError, ValueError):
                return
            if row < 0 or column < 0:
                return  # 快照记录的就是"无选中"
            row = min(row, table.rowCount() - 1)
            column = min(column, table.columnCount() - 1)
            _select_row(table, row, column)
        scroll = state.get("scroll")
        if isinstance(scroll, (tuple, list)) and len(scroll) == 2:
            try:
                table.horizontalScrollBar().setValue(int(scroll[0]))
                table.verticalScrollBar().setValue(int(scroll[1]))
            except (TypeError, ValueError):
                pass

    def mark_ids_stale(self) -> None:
        """撤销 / 重做重建工作库后调用：表格行上的构件 id 已全部失效。

        重建后的库按位置重新编号，旧 id 要么缺失、要么撞到别的构件；
        随后的重载不再按 id 恢复选中（选中由撤销快照按行号恢复）。
        """
        self._ids_stale = True

    def _delete_element(self) -> None:
        element_id = self._current_element_id()
        if element_id is None:
            return
        answer = FramelessMessageBox.question(
            self,
            "删除确认",
            "确定删除该构件条目及其管材、参数？",
            FramelessMessageBox.StandardButton.Yes | FramelessMessageBox.StandardButton.No,
            FramelessMessageBox.StandardButton.No,
        )
        if answer == FramelessMessageBox.StandardButton.Yes:
            self._vm.remove_element(element_id)

    def _move_element(self, delta: int) -> None:
        element_id = self._current_element_id()
        if element_id is not None:
            self._vm.move_element(element_id, delta)

    # ------------------------------------------------------------------ 主表格快捷键 / 右键菜单（复刻旧版 dGVmain_KeyUp / CMSmain）
    def eventFilter(self, source, event) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent, QKeySequence

        if source is self._element_table and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() == Qt.Key.Key_Delete:
                self._delete_selected_elements()
                return True
            # 复制 / 剪切 / 粘贴（brackets 同款：Ctrl+C/X/V，剪贴板内容可跨文件）
            if event.matches(QKeySequence.StandardKey.Copy):
                self._copy_elements()
                return True
            if event.matches(QKeySequence.StandardKey.Cut):
                self._cut_elements()
                return True
            if event.matches(QKeySequence.StandardKey.Paste):
                self._paste_elements()
                return True
            if event.key() == Qt.Key.Key_Escape and self._format_painter_active:
                self._cancel_format_painter()
                return True
        return super().eventFilter(source, event)

    def _selected_element_ids(self) -> list[int]:
        """选中行对应的构件 id（多选，按行号升序）。"""
        rows = sorted({index.row() for index in self._element_table.selectedIndexes()})
        return [element_id for element_id in (self._element_id_at(row) for row in rows) if element_id]

    def _delete_selected_elements(self) -> None:
        """Delete 键：删除选中行（与原版一致，不经确认）。

        合槽父节点行的删除语义 = 父节点连同全部子节点一并删除；只想删父节点
        而保留子节点时用右键「解散合槽」。
        """
        from app.viewmodels.unit_vm import delete_trench_group

        # 先把选中行快照成 id：删除会经 unit_changed 触发整表重载，行号随即失效
        rows = sorted({index.row() for index in self._element_table.selectedIndexes()})
        group_ids = [group_id for row in rows if (group_id := self._group_id_at(row)) is not None]
        element_ids = [element_id for row in rows if (element_id := self._element_id_at(row)) is not None]
        for group_id in group_ids:
            self._collapsed_group_ids.discard(group_id)
            delete_trench_group(group_id)
        for element_id in element_ids:
            self._vm.remove_element(element_id)

    def _selected_group_row_id(self) -> int | None:
        """选中行里的合槽父节点组 id（单选父行时用）。"""
        return self._group_id_at(self._element_table.currentRow())

    def _on_element_context_menu(self, position) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction("删除选中构件", self._delete_selected_elements)
        menu.addSeparator()
        menu.addAction("复制", self._copy_elements)
        menu.addAction("剪切", self._cut_elements)
        paste = menu.addAction("粘贴", self._paste_elements)
        from app.services import element_clipboard

        paste.setEnabled(element_clipboard.has_payload())
        menu.addSeparator()
        principle_menu = menu.addMenu("选择沟槽围护原则")
        for name in project_io.enclosure_names():
            principle_menu.addAction(name, lambda name=name: self._apply_to_selected("pe_name", name))
        foundation_menu = menu.addMenu("选择地基处理原则")
        for name in project_io.foundation_names():
            foundation_menu.addAction(name, lambda name=name: self._apply_to_selected("pf_name", name))
        menu.addSeparator()
        menu.addAction("复制原则", self._copy_principles)
        apply_menu = menu.addMenu("应用原则")
        apply_menu.addAction("应用沟槽及地基原则", lambda: self._paste_principles(True, True))
        apply_menu.addAction("应用沟槽围护原则", lambda: self._paste_principles(True, False))
        apply_menu.addAction("应用地基处理原则", lambda: self._paste_principles(False, True))
        # ---- 合槽编组（v3）----
        menu.addSeparator()
        ids = self._selected_element_ids()
        group_action = menu.addAction("合槽编组", lambda: self._vm.create_group(ids))
        group_action.setEnabled(len(ids) >= 2)
        group_action.setToolTip(
            "多选构件后编组：成员转为左右分设，上下顺序 = 沟槽从左到右；"
            "约束不满足时状态栏提示原因。"
        )
        # 选中父行或组成员时给解散 / 移出入口
        current_group = self._selected_group_row_id()
        element = self._current_element_row()
        if current_group is None and element is not None:
            current_group = element.group_id
        if current_group is not None:
            menu.addAction("解散合槽", lambda: self._vm.dissolve_group(current_group))
            if element is not None and element.group_id is not None:
                menu.addAction("移出合槽", lambda: self._vm.remove_from_group(element.id))
                menu.addSeparator()
                menu.addAction(
                    "组内左移（上移）", lambda: self._vm.move_element(element.id, -1)
                )
                menu.addAction(
                    "组内右移（下移）", lambda: self._vm.move_element(element.id, 1)
                )
        elif len(ids) >= 1:
            join_menu = menu.addMenu("加入合槽…")
            from app.core.models import base as orm
            from app.core.models.models import TrenchGroup
            from sqlalchemy import select

            groups = list(orm.session().scalars(select(TrenchGroup).order_by(TrenchGroup.id)))
            if not groups:
                join_menu.setEnabled(False)
            for group in groups:
                target = element.id if element is not None else (ids[0] if ids else None)
                join_menu.addAction(
                    group.name,
                    lambda group_id=group.id, target_id=target: target_id is not None
                    and self._vm.add_to_group(target_id, group_id),
                )
        menu.exec(self._element_table.viewport().mapToGlobal(position))

    def _current_element_row(self):
        """当前选中行的 ElementRow（父行 / 空表返回 None）。"""
        element_id = self._current_element_id()
        if element_id is None:
            return None
        for row in self._rows_cache:
            if isinstance(row, ElementRow) and row.id == element_id:
                return row
        return None

    #: 原则剪贴板（原版 mClipboard_PCP 的内存版）；构件剪贴板在
    #: services.element_clipboard（系统剪贴板，跨文件可用）
    _principle_clipboard: tuple[str, str] | None = None

    def _copy_elements(self, *, cut: bool = False) -> None:
        """复制选中行到构件剪贴板（系统剪贴板，跨文件/跨工程可用）。

        选中合槽父行时整组复制；只选中部分成员（没选父行）时按独立构件
        复制（还原为普通单原则）。剪切 = 复制 + 删除原条目。
        """
        from app.services import element_clipboard
        from app.viewmodels.unit_vm import element_copy_snapshot, group_snapshot

        rows = sorted({index.row() for index in self._element_table.selectedIndexes()})
        items: list[dict] = []
        seen_groups: set[int] = set()
        element_ids: list[int] = []
        group_ids: list[int] = []
        for row in rows:
            group_id = self._group_id_at(row)
            if group_id is not None:
                if group_id in seen_groups:
                    continue
                seen_groups.add(group_id)
                data = group_snapshot(group_id)
                if data is not None:
                    items.append({"type": "group", "data": data})
                    group_ids.append(group_id)
                continue
            element_id = self._element_id_at(row)
            if element_id is None:
                continue
            from app.viewmodels.unit_vm import _element

            element = _element(element_id)
            if element is not None and element.group_id is not None:
                if element.group_id in seen_groups:
                    continue  # 整组已随父行复制
            data = element_copy_snapshot(element_id)
            if data is not None:
                items.append({"type": "element", "data": data})
                element_ids.append(element_id)
        if not items:
            return
        element_clipboard.write_items(items)
        if cut:
            from app.viewmodels.unit_vm import delete_trench_group

            for group_id in group_ids:
                self._collapsed_group_ids.discard(group_id)
                delete_trench_group(group_id)
            for element_id in element_ids:
                self._vm.remove_element(element_id)
        verb = "剪切" if cut else "复制"
        bus().status_message.emit(
            f"已{verb} {len(items)} 项到剪贴板（跨工程文件可用）。", 4000
        )

    def _cut_elements(self) -> None:
        self._copy_elements(cut=True)

    # 编辑菜单 / 快捷键入口（主窗体调用）
    def copy_selection(self) -> None:
        self._copy_elements()

    def cut_selection(self) -> None:
        self._cut_elements()

    def paste_selection(self) -> None:
        self._paste_elements()

    def _paste_target_group(self) -> int | None:
        """粘贴目标合槽组：选中父行返回该组，选中组成员返回其组。"""
        group_id = self._selected_group_row_id()
        if group_id is not None:
            return group_id
        element = self._current_element_row()
        if element is not None and element.group_id is not None:
            return element.group_id
        return None

    def _paste_elements(self) -> None:
        """粘贴剪贴板快照（brackets 同款：内容来自系统剪贴板，可跨文件）。

        选中合槽（父行或成员）时粘贴普通构件 = 加入该组；粘贴合槽组被拒
        （合槽不允许嵌套）。普通位置按行序逐项插入（锚点固定为当前行下一
        条构件，插入顺序 = 复制顺序）。
        """
        from app.services import element_clipboard

        items = element_clipboard.read_items()
        if not items or self._unit_id is None:
            return
        items = element_clipboard.remap_items(items)
        target_group = self._paste_target_group()
        if target_group is not None:
            if any(item.get("type") == "group" for item in items):
                bus().status_message.emit("合槽不允许嵌套：不能把合槽组粘贴到另一组合槽内。", 5000)
                return
            from app.viewmodels.unit_vm import add_to_group, insert_element_data

            pasted = 0
            for item in items:
                element = insert_element_data(self._unit_id, item.get("data") or {}, None)
                if element is None:
                    continue
                ok, error = add_to_group(element.id, target_group)
                if ok:
                    pasted += 1
                elif error:
                    bus().status_message.emit(error, 5000)
            if pasted:
                bus().status_message.emit(f"已粘贴 {pasted} 条构件到合槽组。", 4000)
            return
        from app.viewmodels.unit_vm import insert_element_data, insert_group_data

        anchor = self._current_element_id()
        count = 0
        for item in items:
            if item.get("type") == "group":
                group = insert_group_data(self._unit_id, item.get("data") or {}, anchor)
                if group is not None:
                    count += 1
                    from app.viewmodels.unit_vm import element_id_after_group

                    anchor = element_id_after_group(group.id)
            else:
                element = insert_element_data(self._unit_id, item.get("data") or {}, anchor)
                if element is not None:
                    count += 1
        if count:
            bus().status_message.emit(f"已粘贴 {count} 项。", 4000)

    def _copy_principles(self) -> None:
        element_id = self._current_element_id()
        if element_id is None:
            return
        from app.viewmodels.unit_vm import element_snapshot

        data = element_snapshot(element_id)
        if data is not None:
            self._principle_clipboard = (data["pe_name"], data["pf_name"])

    def _apply_to_selected(self, field: str, value: str) -> None:
        for element_id in self._selected_element_ids():
            self._vm.set_element_field(element_id, field, value)

    def _paste_principles(self, use_pe: bool, use_pf: bool) -> None:
        """CopyPCP/PastePCP：把记住的原则批量应用到选中行。"""
        if self._principle_clipboard is None:
            return
        pe_name, pf_name = self._principle_clipboard
        for element_id in self._selected_element_ids():
            if use_pe:
                self._vm.set_element_field(element_id, "pe_name", pe_name)
            if use_pf:
                self._vm.set_element_field(element_id, "pf_name", pf_name)

    # ------------------------------------------------------------------ 构件库插入（原版 FormMdi 构件库双击）
    def insert_template(self, template) -> None:
        """把构件库模板插入当前单位工程主表格，并选中新条目。

        普通构件插到当前选中行的下一行；选中合槽父行或其子条目时插到整组
        合槽所有条目之后（合槽组在末尾则追加到末尾）。
        """
        if self._unit_id is None:
            bus().status_message.emit("请先选中单位工程，再从构件库插入。", 4000)
            return
        from app.viewmodels.unit_vm import insert_element_template

        # 插入语义是“锚点行之前”：锚点由 _insert_anchor_element_id 计算
        # （选中合槽相关行时取整组之后，避免插进组内部或替换父行）。
        # 表格刷新经 unit_changed → QTimer.singleShot(0) 延后，此处只记下新 id，
        # 由 _on_unit_loaded 在重载落地后选中新行
        element = insert_element_template(
            self._unit_id, template, self._insert_anchor_element_id()
        )
        if element is not None:
            self._pending_select_id = element.id

    # ------------------------------------------------------------------ 明细
    def _on_detail_loaded(
        self,
        element_id: int,
        pipes: list[PipeRow],
        params: list[ParamRow],
        quantities: list[QuantityRow],
    ) -> None:
        if self._multi_detail:
            return  # 多选模式显示占位行，不显示具体条目
        from app.viewmodels.unit_vm import (
            _element,
            auto_atlas_params,
            auto_pipe_thicknesses,
            selected_candidate_combo,
        )

        self._loading = True
        try:
            element = _element(element_id)
            # 管材增删入口随类别显隐（直埋/非开挖一条、构筑物无管材时不显示）
            pipe_editable = self._update_pipe_buttons(element)
            # 管材表：管道壁厚列空 = 自动按图集（灰字显示图集值）
            self._pipe_buttons.clear_row_buttons()  # 旧的行尾「-」按钮显式销毁
            self._pipe_table.clearSpans()
            self._pipe_table.setRowCount(len(pipes))
            auto_ts = auto_pipe_thicknesses(element) if (element is not None and pipes) else {}
            for index, pipe in enumerate(pipes):
                mat_item = QTableWidgetItem(pipe.mat)
                mat_item.setData(_PIPE_ROLE, pipe.id)
                mat_item.setToolTip("管材（材质文字）：只用于规格与设备材料表，不参与计算。")
                self._pipe_table.setItem(index, _PIPE_COL_MAT, mat_item)
                # 管径/壁厚/含量三列内容居中（列头不变）
                dn_item = QTableWidgetItem(str(pipe.dn))
                dn_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._pipe_table.setItem(index, _PIPE_COL_DN, dn_item)
                auto_t = auto_ts.get(pipe.id)
                # 直埋管道的壁厚由构件参数行「管道壁厚」自动带出（候选值驱动），
                # 管材行不再手填；多管构件只有首根管跟参数行走，其余仍可手填
                from_param = (
                    element is not None
                    and element.category == CATEGORY_BURIED
                    and index == 0
                )
                if from_param:
                    param_value = next(
                        (row.value for row in params if row.key == PARAM_T_NAME), ""
                    ).strip()
                    text = param_value or ("" if not auto_t else format_number(auto_t))
                    t_item = QTableWidgetItem(text)
                    t_item.setFlags(t_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if param_value:
                        t_item.setToolTip(
                            "壁厚由构件参数「管道壁厚」自动带出（改候选值即可）。"
                        )
                    else:
                        t_item.setForeground(QBrush(_secondary_color()))
                        t_item.setToolTip("壁厚：暂无匹配的候选值，按图集自动。")
                elif pipe.t is None:
                    t_item = QTableWidgetItem("" if auto_t is None else format_number(auto_t))
                    t_item.setForeground(QBrush(_secondary_color()))
                    t_item.setToolTip(
                        "管道壁厚：空 = 自动按图集。"
                        if auto_t is None
                        else f"管道壁厚：空 = 自动按图集（图集值 {format_number(auto_t)}mm）。"
                    )
                else:
                    t_item = QTableWidgetItem(format_number(pipe.t))
                    t_item.setToolTip(f"管道壁厚（手填覆盖）：{format_number(pipe.t)}mm。")
                t_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._pipe_table.setItem(index, _PIPE_COL_T, t_item)
                content_item = QTableWidgetItem(pipe.content)
                content_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._pipe_table.setItem(index, _PIPE_COL_CONTENT, content_item)
                cat_item = QTableWidgetItem(pipe.cat)
                cat_item.setToolTip(
                    "类别（计算唯一依据）：决定面宽表行、图集分流、断面图是否砼基础、"
                    "包封砼扣管位取壁厚。默认由构件库快照写入，可改。"
                )
                self._pipe_table.setItem(index, _PIPE_COL_CAT, cat_item)
                if pipe_editable:
                    # 行尾「-」删行按钮：与条目行对齐，一行一个（无行即无按钮）
                    self._pipe_buttons.add_row_button(index)

            # 参数表：直埋构件且有候选时，"参数值"右侧追加候选参数列
            # （混凝土管 8 列 / 其他管材 4 列）；此时参数值列锁定（自动从
            # 候选里选），候选列可编辑。其他构件维持三列、值可编辑。
            show_candidates = (
                element is not None
                and element.category == CATEGORY_BURIED
                and bool(element.atlas_candidates)
            )
            first_pipe = element.pipes[0] if (element is not None and element.pipes) else None
            self._candidate_columns = list(
                columns_for(
                    _pipe_is_concrete(
                        first_pipe.cat if first_pipe else "",
                        mat=first_pipe.mat if first_pipe else "",
                    )
                )
                if show_candidates
                else ()
            )
            headers = list(_PARAM_HEADERS) + [c.label for c in self._candidate_columns]
            self._param_table.clearSpans()
            self._param_table.setColumnCount(len(headers))
            self._param_table.setHorizontalHeaderLabels(headers)
            # 候选列逐列按列头文字定宽（砼90° / 非砼180° …字数不一，宽窄随之）
            for offset, column in enumerate(self._candidate_columns):
                self._param_table.setColumnWidth(
                    len(_PARAM_HEADERS) + offset,
                    header_fit_width(self._param_table, column.label),
                )
            self._param_table.setRowCount(len(params))
            auto_params = auto_atlas_params(element) if element is not None else {}
            # 当前匹配到的候选组合（键 + 层级）：那一列的格子用浅底色标出来，
            # 跨组借值时换警示浅色，让"这格不是本组的数"一眼可见。
            selected_key, selected_level = (
                selected_candidate_combo(element_id) if show_candidates else (None, None)
            )
            selected_column = next(
                (c for c in self._candidate_columns if c.key == selected_key), None
            )
            level_label = MATCH_LEVEL_LABELS.get(selected_level or "", "")
            for index, param in enumerate(params):
                key_item = QTableWidgetItem(param.key)
                key_item.setData(_PARAM_ROLE, param.id)
                if (param.key, param.unit) in _NO_UNIT_PARAM_ROWS:
                    unit_item = QTableWidgetItem(_NO_UNIT_TEXT)
                else:
                    unit_item = QTableWidgetItem(param.unit)
                unit_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                value_item = QTableWidgetItem(param.value)
                if (
                    param.lock_name
                    and not param.value.strip()
                    and param.unit == "mm"
                    and param.key in auto_params
                ):
                    auto_value = auto_params[param.key]
                    value_item = QTableWidgetItem(format_number(auto_value))
                    value_item.setForeground(QBrush(_secondary_color()))
                    value_item.setToolTip(
                        f"参数值：空 = 自动按图集（图集值 {format_number(auto_value)}）。"
                    )
                value_locked = bool(show_candidates) and param.key in _CANDIDATE_FIELD_BY_PARAM
                if param.lock_name:
                    key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    unit_item.setFlags(unit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if value_locked:
                    value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if selected_column is None:
                        value_tip = (
                            "没有可用的候选参数（四级匹配都没命中）→ 参数值留空，"
                            "计算按图集自动查表。"
                        )
                    else:
                        value_tip = (
                            f"参数值 = 当前匹配的候选「{selected_column.label}」"
                            f"（{level_label}），改候选列即可生效。"
                        )
                        if is_cross_group(selected_level):
                            value_tip += (
                                "本组没有可用数据，借用了另一组（砼基础 ↔ 非砼基础）"
                                "的角度对应值。"
                            )
                    value_item.setToolTip(value_tip)
                self._param_table.setItem(index, 0, key_item)
                self._param_table.setItem(index, 1, unit_item)
                self._param_table.setItem(index, 2, value_item)
                if show_candidates:
                    candidate_field = _CANDIDATE_FIELD_BY_PARAM.get(param.key)
                    for offset, column in enumerate(self._candidate_columns):
                        entry = param.candidates.get(column.key)
                        if candidate_field is None:
                            cell = QTableWidgetItem("")
                            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        elif entry is None:
                            # 图集没这组数据（如 dn<600 的砂基础 90°）：留空格但
                            # 允许手填，填了就建一行候选（见 set_atlas_candidate_value）
                            cell = QTableWidgetItem("")
                            cell.setData(
                                _CANDIDATE_NEW_ROLE,
                                (element_id, column.key, candidate_field),
                            )
                            cell.setToolTip(
                                f"图集没有这一组（{column.label}）的数据，可直接填；"
                                f"填了就作为该组的候选值参与自动匹配。{column.tooltip}"
                            )
                        else:
                            cid, raw_value = entry
                            cell = QTableWidgetItem(
                                "" if raw_value is None else format_number(raw_value)
                            )
                            cell.setData(_CANDIDATE_ROLE, (cid, candidate_field))
                            if column.key == selected_key:
                                cell.setData(
                                    _MATCH_BG_ROLE,
                                    _MATCH_BG_CROSS
                                    if is_cross_group(selected_level)
                                    else _MATCH_BG_SAME,
                                )
                                cell.setToolTip(
                                    f"当前选中（{level_label}）：参数值取这一列。{column.tooltip}"
                                )
                            else:
                                cell.setToolTip(column.tooltip)
                        self._param_table.setItem(index, len(_PARAM_HEADERS) + offset, cell)

            # 工程量表：仅附属构筑物可录入；其它类别显示占位说明，
            # 按钮列（+ 表头格 + 行尾「-」）只在构筑物下显示
            self._qty_table.clearSpans()
            is_structure = element is not None and element.category == CATEGORY_STRUCTURE
            self._qty_buttons.set_visible(is_structure)
            self._qty_buttons.clear_row_buttons()
            # 非附属构筑物不显示表格，空面板居中提示（多原则 Tab 同款）
            self._qty_table.setVisible(is_structure)
            self._qty_placeholder.setVisible(not is_structure)
            if is_structure:
                self._qty_table.setRowCount(len(quantities))
                for index, quantity in enumerate(quantities):
                    category_item = QTableWidgetItem(quantity.category)
                    category_item.setData(_QTY_ROLE, quantity.id)
                    self._qty_table.setItem(index, 0, category_item)
                    self._qty_table.setItem(index, 1, QTableWidgetItem(quantity.item))
                    self._qty_table.setItem(index, 2, QTableWidgetItem(quantity.unit))
                    self._qty_table.setItem(index, 3, QTableWidgetItem(quantity.value))
                    self._qty_buttons.add_row_button(index)
            else:
                self._qty_table.setRowCount(0)

            # 「围护原则」tab：左右分设构件显示六行设置，其余显示占位说明
            self._fill_lr_tab(element)
        finally:
            self._loading = False
        # 管径/壁厚/参数/工程量都影响断面几何与工程量结果，明细变化后重绘
        if element_id:
            self._section_view.set_element(element_id)
        else:
            self._section_view.set_element(None)

    def _fill_lr_tab(self, element) -> None:
        """「围护原则」tab：分设构件显示四行设置，其余显示占位说明。

        合槽子节点：只有首构件左侧、末构件右侧、以及比相邻构件更深的一侧
        可编辑；等深 / 更浅的一侧强制 "-"（虚拟垂直空围护），对应支撑勾选
        同步禁用。左右支撑语义 = 该构件朝向该面的支撑。
        v10 起挖填类型 / 管道基础归各自原则，不再在此分侧取值。
        """
        is_lr = element is not None and element.pe_name == LR_PE_TEXT
        grouped = is_lr and element.group_id is not None
        _clear_cell_widgets(self._lr_table)
        self._lr_table.setVisible(is_lr)
        self._lr_placeholder.setVisible(not is_lr)
        if not is_lr:
            return
        element_id = element.id
        names = project_io.enclosure_names() or [""]
        left_active = right_active = True
        if grouped:
            left_active, right_active = group_side_plan(element.group_id).get(element.id, (True, True))

        def _side_combo(active: bool, field: str, current: str, active_tip: str, forced_tip: str) -> QComboBox:
            combo = QComboBox()
            if active:
                combo.addItems([name for name in names if name != LR_PE_TEXT])
                combo.setCurrentText(current or "")
                combo.currentTextChanged.connect(
                    lambda text, eid=element_id, f=field: self._vm.set_element_field(eid, f, text)
                )
                combo.setToolTip(active_tip)
            else:
                combo.addItem("-")
                combo.setEnabled(False)
                combo.setToolTip(forced_tip)
            return combo

        left = _side_combo(
            left_active,
            "pe_left_name",
            element.pe_left_name,
            "左侧围护原则（合槽首构件 = 左边坡；其余 = 比左邻更深时的内侧放坡）。",
            "等深 / 更浅的一侧不设围护：强制 \"-\"，由自身工作面宽 + 虚拟垂直空围护承担。",
        )
        right = _side_combo(
            right_active,
            "pe_right_name",
            element.pe_right_name,
            "右侧围护原则（合槽末构件 = 右边坡；其余 = 比右邻更深时的内侧放坡）。",
            "等深 / 更浅的一侧不设围护：强制 \"-\"，由自身工作面宽 + 虚拟垂直空围护承担。",
        )

        support_left = QCheckBox("计算支撑（类别“支撑”）")
        support_left.setChecked(bool(element.support_left))
        support_left.toggled.connect(
            lambda checked, eid=element_id: self._vm.set_element_field(eid, "support_left", checked)
        )
        if grouped and not left_active:
            support_left.setEnabled(False)
            support_left.setToolTip("该侧围护为 \"-\"（更浅 / 等深），不产生支撑量。")
        else:
            support_left.setToolTip(
                "勾选 = 左侧做法的支撑 / 围檩公式参与计算（合槽首构件 = 左边坡支撑；"
                "深侧构件 = 其左侧内侧坡支撑）。"
            )

        support_right = QCheckBox("计算支撑（类别“支撑”）")
        support_right.setChecked(bool(element.support_right))
        support_right.toggled.connect(
            lambda checked, eid=element_id: self._vm.set_element_field(eid, "support_right", checked)
        )
        if grouped and not right_active:
            support_right.setEnabled(False)
            support_right.setToolTip("该侧围护为 \"-\"（更浅 / 等深），不产生支撑量。")
        else:
            support_right.setToolTip(
                "勾选 = 右侧做法的支撑 / 围檩公式参与计算（合槽末构件 = 右边坡支撑；"
                "深侧构件 = 其右侧内侧坡支撑）。"
            )

        widgets = (left, right, support_left, support_right)
        self._lr_table.setRowCount(len(widgets))
        self._lr_table.setVerticalHeaderLabels(list(_LR_ROWS))
        for row, widget in enumerate(widgets):
            self._lr_table.setCellWidget(row, 0, widget)

    def _on_pipe_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        pipe_id = self._pipe_id_at(item.row())
        if pipe_id is None:
            return
        field = {
            _PIPE_COL_MAT: "mat",
            _PIPE_COL_DN: "dn",
            _PIPE_COL_T: "t",
            _PIPE_COL_CONTENT: "content",
            _PIPE_COL_CAT: "cat",
        }.get(item.column())
        if field is None:
            return
        if field == "t":
            text = item.text().strip()
            if not text:  # 清空 = 回到自动按图集
                self._vm.set_pipe_field(pipe_id, field, "")
                return
            try:
                value = float(text)
            except ValueError:
                bus().status_message.emit("管道壁厚需为数字（mm），留空自动按图集。", 5000)
                value_item = QTableWidgetItem("")
                self._loading = True
                try:
                    self._pipe_table.setItem(item.row(), item.column(), value_item)
                finally:
                    self._loading = False
                return
            self._vm.set_pipe_field(pipe_id, field, value)
            return
        if field == "dn":
            try:
                value = int(float(item.text().strip() or 0))
            except ValueError:
                bus().status_message.emit("管径需为数字（mm）。", 5000)
                return
            self._vm.set_pipe_field(pipe_id, field, value)
            return
        self._vm.set_pipe_field(pipe_id, field, item.text())

    def _on_param_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        param_id = self._param_id_at(item.row())
        if param_id is None:
            return
        field = {0: "key", 1: "unit", 2: "value"}.get(item.column())
        if field is not None:
            self._vm.set_param_field(param_id, field, item.text())
            return
        # 候选参数列：格子带着 (候选行 id, 字段 a/c1/c2)；空格带的是
        # (构件 id, 列键, 字段) —— 图集没这组数据，手填即建行。
        offset = item.column() - len(_PARAM_HEADERS)
        if not 0 <= offset < len(self._candidate_columns):
            return
        payload = item.data(_CANDIDATE_ROLE)
        if payload is not None:
            candidate_id, candidate_field = payload
            self._vm.update_atlas_candidate(candidate_id, candidate_field, item.text())
            return
        blank = item.data(_CANDIDATE_NEW_ROLE)
        if blank is not None:
            element_id, combo, candidate_field = blank
            self._vm.set_atlas_candidate_value(
                element_id, combo, candidate_field, item.text()
            )

    def _on_qty_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        quantity_id = self._qty_id_at(item.row())
        if quantity_id is None:
            return
        field = {0: "category", 1: "item", 2: "unit", 3: "value"}.get(item.column())
        if field is not None:
            self._vm.set_quantity_field(quantity_id, field, item.text())

    def _pipe_id_at(self, row: int) -> int | None:
        item = self._pipe_table.item(row, 0) if row >= 0 else None
        return item.data(_PIPE_ROLE) if item is not None else None

    def _param_id_at(self, row: int) -> int | None:
        item = self._param_table.item(row, 0) if row >= 0 else None
        return item.data(_PARAM_ROLE) if item is not None else None

    def _qty_id_at(self, row: int) -> int | None:
        item = self._qty_table.item(row, 0) if row >= 0 else None
        return item.data(_QTY_ROLE) if item is not None else None

    def _add_pipe(self) -> None:
        self._vm.add_pipe()

    def _delete_pipe_row(self, row: int) -> None:
        pipe_id = self._pipe_id_at(row)
        if pipe_id is not None:
            self._vm.remove_pipe(pipe_id)

    def _update_pipe_buttons(self, element) -> bool:
        """按构件类别显隐管材增删入口，返回是否可增删（决定是否建行尾「-」按钮）。

        直埋 / 顶管 / 牵引管恒为一条管材、附属构筑物不带管材——「+」和删行
        按钮列直接不显示（不做禁用态）；包封 / 箱涵 / 管廊可增删：「+」在
        按钮列的表头格里，每行行尾一个「-」（无管材行即无按钮）。
        """
        editable = _pipe_panel_editable(element)
        self._pipe_buttons.set_visible(editable)
        return editable

    def _add_quantity(self) -> None:
        self._vm.add_quantity()

    def _delete_qty_row(self, row: int) -> None:
        quantity_id = self._qty_id_at(row)
        if quantity_id is not None:
            self._vm.remove_quantity(quantity_id)


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _clear_cell_widgets(table: QTableWidget) -> None:
    """显式销毁表格里的旧单元格控件：QTableWidget.setCellWidget 在 PySide6 下
    只隐藏被替换的控件并不删除，残留的旧内嵌下拉框会与新控件叠加渲染。"""
    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            old = table.cellWidget(row, column)
            if old is not None:
                table.removeCellWidget(row, column)
                old.deleteLater()


def _category_abbr(category: int) -> str:
    """类型列显示文本：类别简称（仅显示层）；不在简称表里的类别回退完整名。"""
    return _CATEGORY_ABBRS.get(int(category or 0)) or category_name(category)


def _pipe_panel_editable(element) -> bool:
    """管材增删入口是否显示：只有包封 / 箱涵 / 管廊可增删管材行。

    直埋 / 顶管 / 牵引管恒为一条管材、附属构筑物不带管材——增删按钮直接
    不显示（数据层的拦截见 unit_vm.pipe_add_error / pipe_delete_error）。
    """
    return element is not None and element.category not in (
        CATEGORY_STRUCTURE,
        *SINGLE_PIPE_CATEGORIES,
    )


def _combo_names(names: list[str], rows: list[ElementRow], field: str) -> list[str]:
    """下拉项 = 库中原则名；若某构件引用的名字已不在库里也保留，避免显示为空。

    "-" 是合槽父节点的占位文本、不是原则名，不进入下拉项（本项目不存在
    "-" 类型的原则）。
    """
    result = [name for name in names if name and name != "-"]
    for row in rows:
        value = getattr(row, field)
        if value and value != "-" and value not in result:
            result.append(value)
    if not result:
        result = [""]
    return result


def _expression_detail(quantity) -> str:
    """「计算表达式」列的 tooltip / 详情弹窗正文：完整算式 + 中间步骤。

    中间步骤每行 = 该步说明 + 该步算式（由 ``Quantity.steps()`` 派生，见 tracer），
    各步算式按顺序拼起来就是上面那条完整算式；只有一步且带说明时（没有可拆的
    步骤，例如“基础 − 弓形占位”）只补一行说明，不重复整条算式。
    多选合并行（``_Merged``）的步骤是按构件分组的，标题相应改写。
    """
    steps = quantity.steps()
    if len(steps) < 2:
        notes = [note for note, _text in steps if note]
        return quantity.expression + ("\n\n" + "\n".join(notes) if notes else "")
    lines = [
        f"{index}. {note}：{text}" if note else f"{index}. {text}"
        for index, (note, text) in enumerate(steps, start=1)
    ]
    if getattr(quantity, "per_element", False):
        heading = "中间步骤（按构件列出；同一构件内各步拼接 = 该构件的算式）："
    else:
        heading = "中间步骤（各步拼接 = 上式）："
    return f"{quantity.expression}\n\n{heading}\n" + "\n".join(lines)


def _apply_expression_hint(item: QTableWidgetItem, text: str, error: str) -> None:
    """把算式求值结果显示在 tooltip；不合法时用警示色标出。"""
    if not text.strip():
        item.setToolTip("")
        item.setForeground(QBrush(_primary_color()))
        return
    if error:
        item.setToolTip(f"算式错误：{error}")
        item.setForeground(QBrush(_warning_color()))
        return
    try:
        value = evaluate(text)
    except EvalError as exc:
        item.setToolTip(f"算式错误：{exc}")
        item.setForeground(QBrush(_warning_color()))
        return
    item.setToolTip(f"{text} = {format_number(value)}")
    item.setForeground(QBrush(_primary_color()))


def _primary_color() -> QColor:
    return QColor(ThemeManager.instance().current().text_primary)


def _secondary_color() -> QColor:
    return QColor(ThemeManager.instance().current().text_secondary)


def _warning_color() -> QColor:
    return QColor(ThemeManager.instance().current().warning)


def _mix(base: QColor, target: QColor, ratio: float) -> QColor:
    """把 base 按 ratio 混向 target（ratio=0 → base，1 → target）。"""
    ratio = max(0.0, min(1.0, float(ratio)))
    return QColor(
        round(base.red() + (target.red() - base.red()) * ratio),
        round(base.green() + (target.green() - base.green()) * ratio),
        round(base.blue() + (target.blue() - base.blue()) * ratio),
    )


def _candidate_selected_bg() -> QColor:
    """当前匹配到的候选格底色：主题主色按 12% 混进卡片底色（很浅但可辨）。"""
    theme = ThemeManager.instance().current()
    return _mix(QColor(theme.bg_card), QColor(theme.primary), 0.12)


def _candidate_borrowed_bg() -> QColor:
    """跨组借值时的底色：警示色按 14% 混进卡片底色，仍是浅色但偏暖。"""
    theme = ThemeManager.instance().current()
    return _mix(QColor(theme.bg_card), QColor(theme.warning), 0.14)
