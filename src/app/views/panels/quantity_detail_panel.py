"""工程量明细表：单位工程节点的工程量计算表（主面板顶级 tab）。

表格内容与「导出 Excel」的工程数量表同源（去掉表达式 / 算式两列）：行前
带“编号”列（内容与构件列表详情面板 定额 / 清单工程量 tab 首列一致：清单
项目行填“清单项目”、定额拆分行留空），列见 :data:`_HEADERS`（编号 / 类别 /
名称 / 单位 / 数量 / 单价 / 合价），清单项目行按导出规则整行浅蓝底色。
单价列参照综合单价汇总表交互：可编辑，按“项目”名全项目联动写库（见
``summary.set_price_propagate``）；合价 = 数量 × 单价自动算出，不可编辑。
清单项目行（清单表）的单价 / 合价为派生值：合价 = 该条目下所有定额工程量
行合价的合计，单价 = 合价 ÷ 数量，不可编辑、随定额行单价联动刷新。
定额 / 清单两张表（对应 xlsx 两张 sheet）用页内分段控件切换（Apple HIG
同款，避免与主面板 tab 连成两行）。

分段控件同一行的右侧是表格动作按钮（SVG 图标 + 文字，作用于下方当前显示的
那张表），从左到右依次为展开 / 收起、复制、导出：

* **展开 / 收起表格** —— 只在「清单工程量」出现：展开态（默认）显示清单
  项目行 + 其下的工程量行，收起态只显示清单项目行。该状态同时决定
  「导出当前表格」是否带表达式 / 算式两列，但**不影响**工具栏「导出 Excel」；
* **复制当前表格** —— 整张表（含表头）按制表符分隔进系统剪贴板，
  可以直接粘进 Excel；
* **导出当前表格** —— 单 sheet xlsx，列为页面 7 列，展开态再在右侧追加
  表达式 / 算式两列（与工具栏「导出 Excel」同口径的取值，但只导当前单位
  工程、当前这张表）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.calc.tracer import fmt
from app.core.config import update_config
from app.core.event_bus import bus, connect_weak
from app.resources.qss.theme import ThemeManager
from app.services import project_io
from app.services import summary as summary_service
from app.viewmodels.unit_vm import compute_unit
from app.views.widgets.frameless_dialog import FramelessMessageBox, load_icon
from app.views.widgets.table_edit_delegate import TableEditDelegate
from app.views.widgets.table_width import fixed_width_behavior

# 与导出 Excel 同源：行生成器与清单行底色（导出同款浅蓝）
from app.services.summary import (
    _LISTING_FILL,
    _QUOTA_WIDTHS,
    _listing_rows,
    _quota_rows,
)

#: 页面表格列：编号 + 类别/名称/单位/数量 + 单价/合价（编号列内容与构件
#: 列表详情面板定额 / 清单工程量 tab 首列一致，单价列交互同综合单价汇总表）
_HEADERS = ["编号", "类别", "名称", "单位", "数量", "单价", "合价"]
_COL_NO, _COL_CAT, _COL_NAME, _COL_UNIT, _COL_AMOUNT, _COL_PRICE, _COL_TOTAL = range(7)
_WIDTHS = (77, *(width * 8 for width in _QUOTA_WIDTHS[:4]), 110, 140)

#: 清单项目行标识（存首列条目，委托据此整行画浅蓝底）
_LISTING_ROLE = Qt.ItemDataRole.UserRole + 4

#: 单价条目 key（类别|项目|单位，存单价列条目）与数量浮点值（存数量列条目）
_PRICE_KEY_ROLE = Qt.ItemDataRole.UserRole + 5
_AMOUNT_ROLE = Qt.ItemDataRole.UserRole + 6

#: 清单项目行浅蓝底（#D6EAF8）固定配的深色文字：暗色主题下默认亮字在浅蓝底上看不清
_LISTING_TEXT = "#17324F"

#: 数据变更后的延迟重算（构件增删改时避免逐次全量重算拖慢录入）
_RELOAD_DELAY_MS = 300

#: 导出文件名里的非法字符（单位工程名可能带 / 等）
_INVALID_FILE_CHARS = re.compile(r'[\\/:*?"<>|]')


class _Row(NamedTuple):
    """一行工程量：源值（类别 / 名称 / 单位 / 数量 / 表达式 / 算式）+ 派生价。"""

    values: list      # (类别, 名称, 单位, 数量, 表达式, 算式)
    is_listing: bool
    price: float
    total: float
    price_key: str | None


class _ListingRowDelegate(TableEditDelegate):
    """清单项目行整行浅蓝底（导出 Excel 同款）+ 单价列编辑态抛光。

    全局 QSS 的 ``QTableWidget::item { background-color: transparent; }``
    会盖掉逐条目 ``setBackground`` 设置的底色，必须由委托在默认绘制前自绘。
    继承 :class:`TableEditDelegate` 让可编辑的单价列获得同款无边框编辑器。
    """

    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self._table = table

    def paint(self, painter, option, index) -> None:
        item = self._table.item(index.row(), 0)
        if item is not None and item.data(_LISTING_ROLE):
            painter.save()
            painter.fillRect(option.rect, QColor(f"#{_LISTING_FILL}"))
            painter.restore()
        super().paint(painter, option, index)


class QuantityDetailPanel(QWidget):
    """工程量明细表页：定额工程量 / 清单工程量两张子表（对应 xlsx 两张 sheet）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._node = None
        self._loading = False  # 程序化填装表格时屏蔽信号
        self._dirty = False  # 页面不可见期间数据变了，显示时补一次重载
        #: 清单工程量是否收起（收起 = 只显示清单项目行，隐藏其下工程量行）
        self._listing_collapsed = False
        #: 单价索引（summary.price_maps 的快照，改单价后局部刷新）
        self._by_key: dict[str, float] = {}
        self._by_item: dict[str, float] = {}
        #: 最近一次算出的行（原始值对 + 补价后的行），改单价只重乘、导出复用
        self._quota_pairs: list[tuple[list, bool]] = []
        self._listing_pairs: list[tuple[list, bool]] = []
        self._quota_rowset: list[_Row] = []
        self._listing_rowset: list[_Row] = []
        #: 单位工程的工程量源数据（导出「当前表格」解析表达式时复用）
        self._summary = None
        self._detail: list = []
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(_RELOAD_DELAY_MS)
        self._reload_timer.timeout.connect(self._on_reload_timer)
        self._build_ui()
        connect_weak(bus().unit_changed, self, "_on_data_changed")
        connect_weak(bus().principle_changed, self, "_on_data_changed")
        connect_weak(bus().project_closed, self, "set_node", None)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._quota_table = self._make_table(_HEADERS)
        self._listing_table = self._make_table(_HEADERS)
        self._quota_table.itemChanged.connect(self._on_price_item_changed)
        self._listing_table.itemChanged.connect(self._on_price_item_changed)
        self._tables = QStackedWidget()
        self._tables.addWidget(self._quota_table)   # 段 0：定额工程量
        self._tables.addWidget(self._listing_table)  # 段 1：清单工程量

        # 页内同层视图切换用分段控件（Apple HIG 同款），避免与主面板 tab 连成两行
        seg_row = QHBoxLayout()
        seg_row.setContentsMargins(0, 0, 0, 0)
        seg_row.addWidget(self._build_segment_control())
        seg_row.addStretch(1)
        # 表格动作按钮：作用于下方当前显示的那张表；整个按钮区靠右对齐，
        # 顺序固定为 展开 / 收起 → 复制 → 导出（展开 / 收起只在清单表出现）
        self._btn_toggle = self._make_action_button(
            "收起表格",
            "table-collapse",
            self._toggle_listing_collapse,
            "只显示清单项目行，收起其下的工程量行",
        )
        self._btn_copy = self._make_action_button(
            "复制当前表格",
            "copy",
            self._copy_current_table,
            "把当前表格（含表头）复制到系统剪贴板，可直接粘进 Excel",
        )
        self._btn_export = self._make_action_button(
            "导出当前表格",
            "export-excel",
            self._export_current_table,
            "把当前表格导出成 Excel（单 sheet，展开态附带表达式 / 算式两列）",
        )
        for button in (self._btn_toggle, self._btn_copy, self._btn_export):
            seg_row.addWidget(button)
        layout.addLayout(seg_row)
        layout.addWidget(self._tables, 1)

        self._tables.setCurrentIndex(0)
        self._on_segment_clicked(0)
        self._set_actions_enabled(False)

    def _build_segment_control(self) -> QWidget:
        """灰底圆角轨道 + 两段互斥按钮（定额工程量 / 清单工程量）。"""
        host = QWidget()
        host.setProperty("role", "segment-host")
        host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        seg_layout = QHBoxLayout(host)
        seg_layout.setContentsMargins(2, 2, 2, 2)
        seg_layout.setSpacing(2)
        self._segment_group = QButtonGroup(self)
        self._segment_group.setExclusive(True)
        for index, text in enumerate(("定额工程量", "清单工程量")):
            button = QPushButton(text)
            button.setProperty("role", "segment-btn")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(index == 0)
            self._segment_group.addButton(button, index)
            seg_layout.addWidget(button)
        self._segment_group.idClicked.connect(self._on_segment_clicked)
        return host

    def _make_action_button(
        self, text: str, icon_name: str, slot, tooltip: str
    ) -> QToolButton:
        """图标 + 文字的表格动作按钮（图标随主题重着色，见 ``_on_theme_changed``）。"""
        button = QToolButton()
        button.setProperty("role", "table-action")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(16, 16))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setText(text)
        button.setToolTip(tooltip)
        button.setIcon(load_icon(icon_name, color=self._icon_color(), size=16))
        button.clicked.connect(slot)
        return button

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(False)  # 单元格同色，不按行间隔变色
        # 固定列宽（可拖动调整）：表格不随父控件拉伸（全项目约定）
        fixed_width_behavior(table)
        table.horizontalHeader().setHighlightSections(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.setWordWrap(False)
        # 列宽沿用导出 Excel 的字符宽（×8 ≈ px）
        for index, width in enumerate(_WIDTHS):
            table.setColumnWidth(index, width)
        # 清单项目行浅蓝底：QSS 盖掉 item 底色，须委托自绘
        table.setItemDelegate(_ListingRowDelegate(table))
        return table

    def _on_segment_clicked(self, index: int) -> None:
        """分段切换：换表，「展开 / 收起表格」只对清单表出现（定额表没有分组）。"""
        self._tables.setCurrentIndex(index)
        self._btn_toggle.setVisible(index == 1)

    def _on_theme_changed(self, _name: str = "") -> None:
        """主题切换：动作按钮的 SVG 图标按新主题色重着色。"""
        color = self._icon_color()
        self._btn_copy.setIcon(load_icon("copy", color=color, size=16))
        self._btn_export.setIcon(load_icon("export-excel", color=color, size=16))
        self._refresh_toggle_button()

    def _icon_color(self) -> str:
        """图标描边色（与同排分段控件的未选中文字同色）。"""
        return ThemeManager.instance().current().text_secondary

    def _refresh_toggle_button(self) -> None:
        """展开 / 收起按钮的文字、提示与图标跟随当前状态。"""
        collapsed = self._listing_collapsed
        self._btn_toggle.setText("展开表格" if collapsed else "收起表格")
        self._btn_toggle.setToolTip(
            "显示清单项目下全部工程量行" if collapsed else "只显示清单项目行，收起其下的工程量行"
        )
        self._btn_toggle.setIcon(
            load_icon(
                "table-expand" if collapsed else "table-collapse",
                color=self._icon_color(),
                size=16,
            )
        )

    def _set_actions_enabled(self, enabled: bool) -> None:
        for button in (self._btn_copy, self._btn_export, self._btn_toggle):
            button.setEnabled(enabled)

    def _current_table(self) -> QTableWidget:
        """下方当前显示的表（定额 / 清单）。"""
        return self._listing_table if self._tables.currentIndex() == 1 else self._quota_table

    # ------------------------------------------------------------------ 数据刷新
    def set_node(self, node) -> None:
        """项目树选中变化：单位工程节点装填本页，None 清空。"""
        self._node = node
        if node is None:
            self._dirty = False
            self._by_key, self._by_item = {}, {}
            self._quota_pairs, self._listing_pairs = [], []
            self._quota_rowset, self._listing_rowset = [], []
            self._summary, self._detail = None, []
            self._quota_table.setRowCount(0)
            self._listing_table.setRowCount(0)
            self._set_actions_enabled(False)
            return
        self._set_actions_enabled(True)
        if self.isVisible():
            self._reload()
        else:
            self._dirty = True

    def maybe_reload(self) -> None:
        """主面板 tab 切换后调用：页面脏且当前可见时补一次重载。"""
        if self._dirty and self.isVisible():
            self._dirty = False
            self._reload()

    def _on_data_changed(self, *_args) -> None:
        if self._node is None:
            return
        if not self.isVisible():
            self._dirty = True
            return
        self._reload_timer.start()

    def _on_reload_timer(self) -> None:
        if not self.isVisible():
            self._dirty = True
            return
        self._reload()

    def _reload(self) -> None:
        self._loading = True
        try:
            node = self._node
            if node is None or not project_io.is_open():
                self._quota_table.setRowCount(0)
                self._listing_table.setRowCount(0)
                self._quota_pairs, self._listing_pairs = [], []
                self._quota_rowset, self._listing_rowset = [], []
                self._summary, self._detail = None, []
                return
            # 与导出 Excel（分单位工程口径）同源：compute_unit → 行生成器。
            # 本页不显示算式两列，with_expression=False 跳过主算式解析
            # （该解析极重，是切换节点卡顿的元凶）；导出「当前表格」按缓存的
            # 源数据再解析一次（见 _export_current_table）
            summary, detail = compute_unit(node.id)
            self._summary, self._detail = summary, detail
            self._by_key, self._by_item = summary_service.price_maps()
            self._quota_pairs = [
                (row, False) for row in _quota_rows(summary, with_expression=False)
            ]
            self._listing_pairs = list(_listing_rows(detail, with_expression=False))
            self._quota_rowset = self._compose(self._quota_pairs)
            self._listing_rowset = self._compose(self._listing_pairs)
            self._fill_table(self._quota_table, self._quota_rowset)
            self._fill_table(self._listing_table, self._listing_display_rows())
        finally:
            self._loading = False

    def _listing_display_rows(self) -> list[_Row]:
        """清单表实际显示的行：收起态只留清单项目行（合价仍按分项合计）。"""
        if not self._listing_collapsed:
            return self._listing_rowset
        return [row for row in self._listing_rowset if row.is_listing]

    def _compose(self, rows: list[tuple[list, bool]]) -> list[_Row]:
        """给行补上单价 / 合价（纯重乘，不算工程量、不解析表达式）。

        定额行单价按 key 取价目表、合价 = 数量 × 单价；清单项目行合价 = 该
        条目下所有定额工程量行合价的合计、单价 = 合价 ÷ 数量（派生值，不写库）。
        合价始终按**全量**行合计——收起态表格里只剩清单项目行时也不受影响。
        """
        composed: list[_Row] = []
        for row_index, (values, is_listing) in enumerate(rows):
            category, name, unit, amount = values[:4]
            amount = float(amount)
            if is_listing:
                total = 0.0
                for child_values, child_is_listing in rows[row_index + 1:]:
                    if child_is_listing:
                        break
                    child_category, child_name, child_unit, child_amount = child_values[:4]
                    child_key = f"{child_category}|{child_name}|{child_unit}"
                    total += float(child_amount) * self._resolve_price(child_key, child_name)
                price = total / amount if amount else 0.0
                price_key = None
            else:
                price_key = f"{category}|{name}|{unit}"
                price = self._resolve_price(price_key, name)
                total = amount * price
            composed.append(_Row(list(values), is_listing, price, total, price_key))
        return composed

    def _fill_table(self, table: QTableWidget, rows: list[_Row]) -> None:
        """把补好价的行写进表格。

        编号列内容与构件列表详情面板定额 / 清单工程量 tab 首列一致（清单项目
        行填“清单项目”，其余留空）。定额行单价可编辑（key = 类别|项目|单位）；
        合价不可编辑，清单项目行整行浅蓝（委托自绘）。
        """
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            amount = float(row.values[3])
            texts = (
                "清单项目" if row.is_listing else "",
                str(row.values[0]),
                str(row.values[1]),
                str(row.values[2]),
                fmt(amount),
                fmt(row.price),
                fmt(row.total),
            )
            for column, text in enumerate(texts):
                item = QTableWidgetItem(text)
                if column == _COL_PRICE and row.price_key is not None:
                    item.setData(_PRICE_KEY_ROLE, row.price_key)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if row.is_listing:
                        # 浅蓝底固定配深色文字（暗色主题下亮字在浅蓝底上看不清）
                        item.setForeground(QBrush(QColor(_LISTING_TEXT)))
                    elif column == _COL_NO:
                        item.setForeground(QBrush(self._secondary_color()))
                if column == _COL_AMOUNT:
                    item.setData(_AMOUNT_ROLE, amount)
                if column == _COL_NO and row.is_listing:
                    item.setData(_LISTING_ROLE, True)
                table.setItem(row_index, column, item)

    # ------------------------------------------------------------------ 展开 / 收起
    def _toggle_listing_collapse(self) -> None:
        """切换清单表的展开 / 收起（只改显示，不影响工具栏「导出 Excel」）。"""
        self._listing_collapsed = not self._listing_collapsed
        self._loading = True
        try:
            self._fill_table(self._listing_table, self._listing_display_rows())
        finally:
            self._loading = False
        self._refresh_toggle_button()
        rows = self._listing_table.rowCount()
        bus().status_message.emit(
            f"清单工程量已收起，只显示 {rows} 个清单项目行。"
            if self._listing_collapsed
            else f"清单工程量已展开，显示 {rows} 行。",
            3000,
        )

    # ------------------------------------------------------------------ 复制 / 导出
    def _copy_current_table(self) -> None:
        """当前表格（含表头）按制表符分隔进剪贴板，可直接粘进 Excel。"""
        table = self._current_table()
        if table.rowCount() == 0:
            bus().status_message.emit("当前表格没有内容可复制。", 3000)
            return
        lines = []
        headers = []
        for column in range(table.columnCount()):
            header = table.horizontalHeaderItem(column)
            headers.append(header.text() if header is not None else "")
        lines.append("\t".join(headers))
        for row in range(table.rowCount()):
            cells = []
            for column in range(table.columnCount()):
                item = table.item(row, column)
                cells.append(item.text() if item is not None else "")
            lines.append("\t".join(cells))
        QGuiApplication.clipboard().setText("\n".join(lines))
        bus().status_message.emit(f"已复制当前表格 {table.rowCount()} 行到剪贴板。", 3000)

    def _export_current_table(self) -> None:
        """当前表格导出成单 sheet xlsx（展开态右侧追加表达式 / 算式两列）。"""
        if self._node is None or not project_io.is_open():
            FramelessMessageBox.warning(self, "无法导出", "请先在项目结构里选择一个单位工程。")
            return
        if self._dirty or self._summary is None:
            # 页面不可见期间数据变过 / 还没算过：先补一次重载，避免导出旧数
            self._dirty = False
            self._reload()
        is_listing = self._tables.currentIndex() == 1
        # 收起态没有工程量行，也就不导出表达式 / 算式两列
        collapsed = is_listing and self._listing_collapsed
        tab_name = "清单工程量" if is_listing else "定额工程量"

        from app.views.dialogs.new_project_wizard import suggested_dir

        start = suggested_dir() / f"{_safe_file_name(self._node.name)}-{tab_name}.xlsx"
        target, _filter = QFileDialog.getSaveFileName(
            self, "导出当前表格", str(start), "Excel 工作簿 (*.xlsx)"
        )
        if not target:
            return
        path = Path(target)

        error_text = ""
        result: dict = {}
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = summary_service.export_detail_table(
                path,
                self._export_rows(is_listing, collapsed),
                with_expression=not collapsed,
                sheet_title=tab_name,
            )
        except PermissionError:
            error_text = "文件被占用，无法写入。请先关闭已打开的同名 Excel 文件再重试。"
        except Exception as error:  # 计算失败 / 路径非法等，一律弹窗不崩溃
            error_text = str(error)
        finally:
            QApplication.restoreOverrideCursor()
        if error_text:
            FramelessMessageBox.warning(self, "导出失败", error_text)
            return

        from app.views.dialogs.export_excel_dialog import open_exported_file

        update_config({"ui": {"last_dir": str(path.parent)}})
        bus().status_message.emit(f"已导出：{result['path']}", 5000)
        if (
            FramelessMessageBox.question(
                self, "提示", f"导出完成，是否打开文件？\n{result['path']}"
            )
            == FramelessMessageBox.Yes
        ):
            open_exported_file(path)

    def _export_rows(self, is_listing: bool, collapsed: bool) -> list[tuple[list, bool]]:
        """按当前显示状态组装导出行：页面 7 列（+ 展开态的表达式 / 算式）。

        值里的数量 / 单价 / 合价写 float（Excel 里可直接再计算），编号列沿用
        页面口径；表达式 / 算式与工具栏「导出 Excel」同源，只在展开态输出。
        """
        if is_listing:
            # 收起态不必解析主算式（省掉那一次极重的解析）
            pairs = list(_listing_rows(self._detail, with_expression=not collapsed))
            if collapsed:
                pairs = [(values, True) for values, flag in pairs if flag]
        else:
            pairs = [
                (row, False) for row in _quota_rows(self._summary, with_expression=True)
            ]
        rows: list[tuple[list, bool]] = []
        for row in self._compose(pairs):
            values = [
                "清单项目" if row.is_listing else "",
                str(row.values[0]),
                str(row.values[1]),
                str(row.values[2]),
                float(row.values[3]),
                row.price,
                row.total,
            ]
            if not collapsed:
                values.extend([str(row.values[4]), str(row.values[5])])
            rows.append((values, row.is_listing))
        return rows

    # ------------------------------------------------------------------ 单价
    def _resolve_price(self, key: str, item: str) -> float:
        """key 显式记录优先，无记录回落到同“项目”名单价（按项目名全局联动）。"""
        price = self._by_key.get(key)
        if price is not None:
            return price
        return self._by_item.get(item, 0.0)

    def _on_price_item_changed(self, item: QTableWidgetItem) -> None:
        """单价编辑落定：按“项目”名联动写库，两表单价 / 合价同步重乘刷新。"""
        if self._loading or item.column() != _COL_PRICE:
            return
        price_key = item.data(_PRICE_KEY_ROLE)
        if price_key is None:
            return
        text = item.text().strip()
        try:
            value = float(text)
        except ValueError:
            bus().status_message.emit(f"单价“{text}”不是有效数字。", 4000)
            self._loading = True
            try:
                item.setText(fmt(self._resolve_price(price_key, self._item_of(price_key))))
            finally:
                self._loading = False
            return
        summary_service.set_price_propagate(price_key, value)
        # 单价按项目名联动后重建索引，两表一起刷（只重乘，不重算工程量）
        self._loading = True
        try:
            self._by_key, self._by_item = summary_service.price_maps()
            self._refresh_price_cells()
        finally:
            self._loading = False

    def _refresh_price_cells(self) -> None:
        """按最新单价索引重写两表的单价 / 合价（数量不重算）。

        从缓存的行结构重算，不重建表格（正在编辑的单价编辑器不会被顶掉）；
        清单项目行的合价仍按**全量**分项合计，收起态也一致。
        """
        self._quota_rowset = self._compose(self._quota_pairs)
        self._listing_rowset = self._compose(self._listing_pairs)
        self._rewrite_price_cells(self._quota_table, self._quota_rowset)
        self._rewrite_price_cells(self._listing_table, self._listing_display_rows())

    @staticmethod
    def _rewrite_price_cells(table: QTableWidget, rows: list[_Row]) -> None:
        for row_index, row in enumerate(rows):
            price_item = table.item(row_index, _COL_PRICE)
            if price_item is not None:
                price_item.setText(fmt(row.price))
            total_item = table.item(row_index, _COL_TOTAL)
            if total_item is not None:
                total_item.setText(fmt(row.total))

    @staticmethod
    def _item_of(price_key: str) -> str:
        parts = price_key.split("|")
        return parts[1] if len(parts) > 1 else ""

    @staticmethod
    def _secondary_color() -> QColor:
        return QColor(ThemeManager.instance().current().text_secondary)


def _safe_file_name(name: str) -> str:
    """文件名去掉 Windows 非法字符（单位工程名可能带 / 等）。"""
    return _INVALID_FILE_CHARS.sub("_", str(name)).strip() or "工程量明细表"
