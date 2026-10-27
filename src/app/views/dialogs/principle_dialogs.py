"""原则编辑子对话框（复刻旧版 FmPcp 各窗体）。

从 principle_panel 迁移而来，供原则编辑主对话框（EnclosureEditDialog /
FoundationEditDialog，复刻 FormPE / FormPF）与横条等处复用：

* :class:`EnclosureWorkDialog` —— 多级围护编辑窗体（FormEcls：围护构件分级表 +
  右侧确认/取消，做法埋深与止水构件在原则主窗体编辑）；
* :class:`ComponentEditDialog` —— 构件编辑器（FormCpntEdit：左参数表、
  右上围护公式、右下支撑公式，行头显示键名）；
* :class:`WidthEditDialog` —— 面宽原则编辑（FormWorkWidth：按工作面宽度 /
  按沟槽总宽度两个 tab，各自一张宽度表，当前 tab 即取值方式）；
* :class:`PrecipitationEditDialog` —— 挖填降水原则编辑（FormPrecipitation：
  左侧「挖填类型」面板 + 右侧井型表（措施名称 / 选用 / 埋深 / 范围 / 侧数 /
  间隔，五种井型）左右布置；v10 起原降水措施原则并入挖填类型。

持久化约定（原版“编辑副本、确认生效”）：编辑过程只写共享会话不 commit，
「确认」才统一落库，「取消」回滚会话整体丢弃——编辑期间落库会让“取消修改”
形同虚设（做法表、子编辑器曾沿用即改即存，取消后修改仍然生效）。
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.event_bus import bus
from app.core.models import base as orm
from app.core.models.models import (
    GROOVE_WIDTH_B,
    GROOVE_WIDTH_WORK,
    PRECIPITATION_COLUMNS,
    PRECIPITATION_LABELS,
    Component,
    ComponentParam,
    EnclosureLevel,
    EnclosureWork,
    PcpEnclosure,
    PcpFoundation,
    PcpPrecipitation,
    PcpWidth,
    WidthItem,
    WIDTH_KIND_WORK,
    WIDTH_KIND_GROOVE_B,
    format_precipitation,
    parse_precipitation,
)
from app.services import project_io
from app.views.widgets.cell_fill_table import CellFillTable
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox
from app.views.widgets.row_button_column import RowButtonColumn
from app.views.widgets.table_width import fixed_width_behavior

_WIDTH_DNS = tuple(range(0, 3100, 100))

#: 「挖填类型」面板选项（原属围护原则窗体，v10 起并入挖填降水原则）
_EXCVT_CHOICES = ("Ⅰ、Ⅱ类土", "Ⅲ类土", "Ⅳ类土", "松石", "次坚石", "普坚石", "特坚石")
_DOCK_CHOICES = ("至管顶50cm", "至管顶标高", "至管中心标高", "至沟槽顶标高")

_WIDTH_CATEGORY_ORDER = (
    "混凝土管-刚性接口",
    "混凝土管-柔性接口",
    "金属类管道",
    "化学建材管道",
    "包封埋管",
    "箱涵-管廊",
)


def describe_component(component: Component | None) -> str:
    """构件描述（旧版 mcComponent.Discribe：描述公式去掉括号）。"""
    if component is None:
        return ""
    from app.core.calc.engine import load_params

    params = load_params(component)
    if not params:
        return component.formula
    text = component.formula
    for key in params:
        text = re.sub(r"\b" + re.escape(key) + r"\b", params[key][1], text)
    if "参数循环引用" in text:
        return "参数循环引用"
    return text.replace("(", "").replace(")", "")


def precipitation_enabled(key: str, enclosure: PcpEnclosure) -> tuple[bool, float, float, float]:
    """解析降水列 → (是否启用, 深度阈值, 井距, 侧数)。"""
    elevation, gap, sides = parse_precipitation(getattr(enclosure, key), key)
    return elevation >= 0, elevation, gap, sides


def precipitation_text(enclosure: PcpEnclosure) -> str:
    """降水描述（复刻旧版 mcPcpEnclosure.DiscribePreciptitation）。

    每个深度范围独占一行（旧版标签是多行文本）；末行以句号结尾。
    """
    lines: list[str] = []
    current: float | None = None
    for key in ("light_well", "jet_well", "big_well", "deep_well"):
        enabled, elevation, _gap, _sides = precipitation_enabled(key, enclosure)
        if enabled:
            lines.append(f"深度{elevation:g}m以上，采用{PRECIPITATION_LABELS[key]}降水；")
            current = elevation
    wet_enabled, _e, _g, _s = precipitation_enabled("wet_soil", enclosure)
    if wet_enabled:
        if current is None:
            lines.insert(0, "湿土排水；")
        elif current > 0:
            lines.insert(0, f"深度{current:g}m以下，采用湿土排水；")
        else:
            lines.insert(0, "不采用湿土排水；")
    if not lines:
        return "未设置降水。"
    text = "\n".join(lines)
    if text.endswith("；"):
        text = text[:-1] + "。"
    return text


class PrincipleSubDialog(FramelessDialog):
    """原则子编辑对话框的公共骨架：无边框（Quotor 风格）+ 确定 = 生效 / 取消 = 丢弃。

    修改只写共享会话、不落库：落库统一由原则主窗体（EnclosureEditDialog 等）
    在其「确认修改」时 commit，主窗体「取消修改」回滚会话时一并丢弃（与旧版
    FormPE 编辑副本的语义一致）。

    ``with_buttons=False`` 时不加底部按钮行，由子类自建（如多级围护编辑窗体的
    右侧竖排按钮，旧版 FormEcls 布局）。
    """

    def __init__(self, title: str, parent: QWidget | None = None, *, with_buttons: bool = True) -> None:
        super().__init__(parent, title)
        self.setMinimumWidth(560)
        self.saved = False
        self._loading = False
        self._body = QVBoxLayout()
        self._body.setSpacing(6)
        outer = self.bodyLayout()
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(10)
        outer.addLayout(self._body)
        if with_buttons:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
            buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", "true")
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
            buttons.accepted.connect(self._accept)
            buttons.rejected.connect(self.reject)
            outer.addWidget(buttons)

    def _accept(self) -> None:
        self.save()
        self.saved = True
        self.accept()

    def save(self) -> None:  # pragma: no cover - 子类实现
        raise NotImplementedError


class EnclosureWorkDialog(PrincipleSubDialog):
    """多级围护编辑窗体（旧版 FormEcls）：围护构件分级表 + 右侧竖排确认/取消。

    布局与交互照抄 FormEcls：固定勾选 ↔ 级高 1 / -1（均分级高只读显示
    “均分高度”）；围护类型下拉按库模板重建级构件；双击“围护形式描述”打开
    构件编辑器（FormCpntEdit）；Insert 插入分级、Delete 删除选中分级
    （至少保留一级）；“+” 加在最后。做法埋深与止水构件在原则主窗体
    （FormPE）编辑，本窗体不再重复。
    """

    def __init__(self, work: EnclosureWork, parent: QWidget | None = None) -> None:
        super().__init__("多级围护编辑窗体", parent, with_buttons=False)
        self.resize(695, 460)
        self._work = work
        self._repair_levels()
        # 取消恢复用：记下进入窗体时的分级子树（级字段 + 级构件及参数）。
        # 本窗体的编辑只写会话不落库，取消时按这份快照还原，最终生效与否
        # 由原则主窗体的 确认/取消 决定
        self._level_backup = self._snapshot_levels()
        self._build()
        self._fill()

    def _build(self) -> None:
        row = QHBoxLayout()
        self._level_table = _LevelTable()
        self._level_table.insert_requested.connect(
            lambda: self._insert_level(self._level_table.currentRow())
        )
        self._level_table.delete_requested.connect(self._delete_levels)
        self._level_table.itemChanged.connect(self._on_level_changed)
        self._level_table.cellDoubleClicked.connect(self._on_level_double_clicked)
        self._level_table.setToolTip(
            "Insert 插入分级；Delete 删除选中分级；双击“围护形式描述”编辑构件公式"
        )
        row.addWidget(self._level_table, 1)

        # 右侧竖排（原版 BTNadd / BTNyes / BTNcancel）
        side = QVBoxLayout()
        btn_add = QPushButton("+")
        btn_add.setProperty("role", "icon-btn")
        btn_add.setFixedSize(28, 34)
        btn_add.setToolTip("添加分级（Insert）")
        btn_add.clicked.connect(self._add_level)
        btn_yes = QPushButton("确认\n修改")
        btn_yes.setProperty("primary", "true")
        btn_yes.setFixedSize(76, 52)
        btn_yes.clicked.connect(self._accept)
        btn_cancel = QPushButton("取消\n修改")
        btn_cancel.setFixedSize(76, 52)
        btn_cancel.clicked.connect(self.reject)
        side.addWidget(btn_add)
        side.addSpacing(6)
        side.addWidget(btn_yes)
        side.addWidget(btn_cancel)
        side.addStretch(1)
        row.addLayout(side)
        self._body.addLayout(row, 1)
        self._ei_names = project_io.component_library().names("Ei")

    def _fill(self) -> None:
        self._loading = True
        try:
            levels = list(self._work.levels)
            self._level_table.setRowCount(len(levels))
            for row_index, level in enumerate(levels):
                check = QTableWidgetItem()
                check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                check.setCheckState(Qt.CheckState.Checked if level.h >= 0 else Qt.CheckState.Unchecked)
                self._level_table.setItem(row_index, 0, check)
                # 旧版 FlashdGVCpntRow：均分级显示“均分高度”且只读
                h_item = QTableWidgetItem("均分高度" if level.h < 0 else f"{level.h:g}")
                if level.h < 0:
                    h_item.setFlags(h_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._level_table.setItem(row_index, 1, h_item)
                self._level_table.setItem(row_index, 2, QTableWidgetItem(f"{level.step_width:g}"))
                component = level.components[0] if level.components else None
                cat_combo = QComboBox()
                cat_combo.addItems(self._ei_names)
                cat_combo.setCurrentText(level.name)
                cat_combo.currentTextChanged.connect(
                    lambda text, lv=level: self._on_level_category(lv, text)
                )
                self._level_table.setCellWidget(row_index, 3, cat_combo)
                describe_item = QTableWidgetItem(describe_component(component))
                describe_item.setFlags(describe_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                describe_item.setToolTip("双击编辑围护形式")
                self._level_table.setItem(row_index, 4, describe_item)
        finally:
            self._loading = False

    def _levels(self) -> list[EnclosureLevel]:
        return list(self._work.levels)

    def _snapshot_levels(self) -> list[dict]:
        """分级子树快照：级字段 + 级构件（名称、公式、参数），取消恢复用。"""
        snaps: list[dict] = []
        for level in self._levels():
            component = level.components[0] if level.components else None
            snaps.append(
                {
                    "name": level.name,
                    "h": level.h,
                    "step_width": level.step_width,
                    "component": None
                    if component is None
                    else {
                        "name": component.name,
                        "formula": component.formula,
                        "params": [(param.key, param.value) for param in component.params],
                    },
                }
            )
        return snaps

    def reject(self) -> None:  # noqa: N802 - Qt 命名
        """取消修改：把分级子树恢复为进入窗体时的样子。

        只写会话不落库——主窗体确认时随之生效、主窗体取消时随会话回滚。
        """
        from sqlalchemy import select

        session = orm.session()
        # 级列表直接按 DB 查（级集合在编辑过程中可能陈旧）；级联删除级构件与参数
        levels = session.scalars(
            select(EnclosureLevel)
            .where(EnclosureLevel.work_id == self._work.id)
            .order_by(EnclosureLevel.order_no)
        ).all()
        for level in levels:
            session.delete(level)
        session.flush()
        for order_no, snap in enumerate(self._level_backup):
            level = EnclosureLevel(
                work_id=self._work.id,
                name=snap["name"],
                h=snap["h"],
                step_width=snap["step_width"],
                order_no=order_no,
            )
            session.add(level)
            session.flush()
            component = snap["component"]
            if component is not None:
                rebuilt = Component(
                    name=component["name"],
                    formula=component["formula"],
                    enclosure_level_id=level.id,
                )
                for key, value in component["params"]:
                    rebuilt.params.append(ComponentParam(key=key, value=value))
                session.add(rebuilt)
        session.flush()
        session.expire(self._work)  # 让 levels 集合与恢复结果一致
        super().reject()

    def _add_level(self) -> None:
        # BTNadd（FormEcls）：新级加在最后
        self._insert_level()

    def _repair_levels(self) -> None:
        """补齐缺失级构件的历史行（旧版不变量：mcEclsCpnt 构造即带模板构件）。

        早期版本新增分级只建了级行没挂构件，描述为空且双击无法编辑；打开
        窗体时按级名从构件库补齐，级名不在库中时取库第一项。
        """
        from sqlalchemy import select

        library = project_io.component_library()
        names = library.names("Ei")
        session = orm.session()
        dirty = False
        # 级列表直接按 DB 查（expire_on_commit=False，work.levels 集合可能陈旧）
        levels = session.scalars(
            select(EnclosureLevel)
            .where(EnclosureLevel.work_id == self._work.id)
            .order_by(EnclosureLevel.order_no)
        ).all()
        for level in levels:
            if level.components:
                continue
            name = level.name if library.template("Ei", level.name) else (names[0] if names else "")
            if not name:
                continue
            project_io.component_from_template(
                session, library, "Ei", name, enclosure_level_id=level.id
            )
            orm.session().expire(level)  # expire_on_commit=False：让 components 集合重载
            dirty = True
        if dirty:
            orm.session().expire(self._work)

    def _insert_level(self, position: int | None = None) -> None:
        """InsertCpnt（FormEcls）：新增一级（默认加最后，Insert 键插到当前行前）。

        旧版 new mcEclsCpnt(Ecpnti.First().Key)：新级自带按模板复制的构件，
        描述列随即有内容、双击即可编辑。
        """
        library = project_io.component_library()
        names = library.names("Ei")
        levels = self._levels()
        if position is None or position < 0 or position > len(levels):
            position = len(levels)
        for item in levels:
            if item.order_no >= position:
                item.order_no += 1
        session = orm.session()
        level = EnclosureLevel(
            work_id=self._work.id,
            name=names[0] if names else "放坡",
            h=-1.0,
            step_width=1.0,
            order_no=position,
        )
        session.add(level)
        session.flush()
        if names and library.template("Ei", names[0]) is not None:
            project_io.component_from_template(
                session, library, "Ei", names[0], enclosure_level_id=level.id
            )
        session.expire(self._work)  # 让 levels 集合包含新行
        self._fill()

    def _delete_levels(self) -> None:
        """KeyUp Delete（FormEcls）：删除选中行，至少保留一级。"""
        rows = sorted({index.row() for index in self._level_table.selectedIndexes()}, reverse=True)
        if not rows:
            row = self._level_table.currentRow()
            rows = [row] if row >= 0 else []
        if not rows:
            return
        levels = self._levels()
        if len(rows) >= len(levels):
            FramelessMessageBox.information(self, "提示", "至少需要一级围护做法。")
            return
        for row in rows:
            orm.session().delete(levels[row])
        orm.session().flush()
        orm.session().expire(self._work)
        for index, level in enumerate(self._levels()):
            level.order_no = index
        orm.session().flush()  # expire 重载不做 autoflush，先写进事务
        self._fill()

    def _on_level_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        levels = self._levels()
        if item.row() >= len(levels):
            return
        level = levels[item.row()]
        if item.column() == 0:  # 固定高度勾选
            level.h = 1.0 if item.checkState() == Qt.CheckState.Checked else -1.0
        elif item.column() == 1:
            try:
                level.h = float(item.text() or -1)
            except ValueError:
                pass
        elif item.column() == 2:
            try:
                level.step_width = float(item.text() or 0)
            except ValueError:
                pass
        else:
            return
        self._fill()

    def _on_level_category(self, level: EnclosureLevel, text: str) -> None:
        """ColEclsCat（FormEcls）：级构件按库模板重建（旧版 tmEC.Cpnt = Ecpnti[value]）。"""
        if self._loading or level.name == text or not text:
            return
        library = project_io.component_library()
        if library.template("Ei", text) is None:
            return
        level.name = text
        old = level.components[0] if level.components else None
        if old is not None:
            orm.session().delete(old)
        project_io.component_from_template(
            orm.session(), library, "Ei", text, enclosure_level_id=level.id
        )
        orm.session().expire(level)  # 让 components 集合重载新构件
        # expire 重载不做 autoflush，先把级名等未 flush 修改写进事务
        orm.session().flush()
        self._fill()

    def _on_level_double_clicked(self, row: int, column: int) -> None:
        """CellDoubleClick（FormEcls）：双击“围护形式描述”打开构件编辑器。"""
        if self._loading or column != 4:
            return
        levels = self._levels()
        if row < 0 or row >= len(levels):
            return
        component = levels[row].components[0] if levels[row].components else None
        if component is None:
            return
        dialog = ComponentEditDialog(component, self)
        if dialog.exec() and dialog.saved:
            self._fill()

    def save(self) -> None:
        enclosure = orm.session().get(PcpEnclosure, self._work.enclosure_id)
        works = enclosure.works_sorted() if enclosure else []
        if self._work in works:
            for index, item in enumerate(works):
                item.order_no = index


class _LevelTable(CellFillTable):
    """做法分级表格：Insert 插入行 / Delete 删除选中行（原版 dGVCpnt_KeyUp）。"""

    insert_requested = Signal()
    delete_requested = Signal()

    def __init__(self) -> None:
        super().__init__(0, 5)
        self.setHorizontalHeaderLabels(["固定", "高度m", "平台单侧宽", "围护类型", "围护形式描述"])
        # 固定列宽（可拖动）：表格不随窗体宽度拉伸，右侧留白 / 窄时出横向滚动条
        fixed_width_behavior(self)
        self.setColumnWidth(0, 48)
        self.setColumnWidth(1, 76)
        self.setColumnWidth(2, 90)
        self.setColumnWidth(3, 130)
        self.setColumnWidth(4, 220)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.verticalHeader().setDefaultSectionSize(32)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.key() == Qt.Key.Key_Insert:
            self.insert_requested.emit()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)


def _separator(vertical: bool) -> QFrame:
    """1px 面板分割线（theme QSS 的 role="hline"/"vline"，颜色随主题边框色）。"""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine if vertical else QFrame.Shape.HLine)
    line.setProperty("role", "vline" if vertical else "hline")
    return line


class ComponentEditDialog(PrincipleSubDialog):
    """构件编辑器（旧版 FormCpntEdit）：左参数表（A~Z），右上围护公式（FA~FZ）、
    右下支撑公式（ZA~ZZ），面板之间画分割线，底部确认/取消修改。

    三张表行头均显示参数键，行尾带「+ / -」按钮列（管材面板同款）：
    参数表与两张工程量表都允许用户增删行。工程量表的「类别 / 名称 / 单位」
    三列在库内仍拼成 ``类别|名称|单位`` 作为定额键（计算与导出沿用该格式）。

    悬空引用（方案三）：公式引用了已不存在的参数键时，该公式单元格标红并
    以悬停提示列出缺失键，计算按 0（引擎既有语义）；新增参数取最小未占用
    且未被任何公式引用的字母，避免旧公式误绑到新参数。
    """

    #: (键前缀, 数据列表头)；末列固定为空表头，留给「+ / -」按钮列
    _GROUPS = (
        ("", ("参数名称", "单位", "参数值")),
        ("F", ("类别", "名称", "单位", "计算公式")),
        ("Z", ("类别", "名称", "单位", "计算公式")),
    )
    #: 各表用于铺满面板宽度的列（按钮列固定宽，不参与拉伸）
    _STRETCH_COLUMNS = {"": 2, "F": 3, "Z": 3}
    #: 各表「公式 / 参数值」所在列（悬空引用检查读取这里）
    _EXPRESSION_COLUMNS = {"": 2, "F": 3, "Z": 3}
    #: 参数键字母表（参数表 A~Z，工程量表 FA~FZ / ZA~ZZ）
    _ALPHABET = tuple(chr(code) for code in range(ord("A"), ord("Z") + 1))
    #: 公式里的函数 / 常量名（允许出现，不算“不存在的参数”）
    _FORMULA_NAMES = frozenset(
        {
            "HEIGHT", "WIDTH", "COUNT", "SIDES",
            "ABS", "ROUND", "ROUNDUP", "SQRT", "POWER",
            "CEIL", "CEILING", "SIN", "COS", "PI",
        }
    )
    #: 参数键形态：1~2 个大写字母（A~Z / FA~FZ / ZA~ZZ）
    _KEY_PATTERN = re.compile(r"^[A-Z]{1,2}$")
    #: 悬空引用告警色（浅色 / 深色主题下都足够醒目）
    _WARN_COLOR = QColor("#d93025")

    def __init__(self, component: Component, parent: QWidget | None = None) -> None:
        super().__init__("构件编辑器", parent)
        self.resize(940, 480)
        self._component = component
        self._tables: dict[str, QTableWidget] = {}
        self._buttons: dict[str, RowButtonColumn] = {}
        self._loading = False
        self._warn_updating = False
        self._deleted_keys: set[str] = set()
        self._build()
        self._fill()

    def _build(self) -> None:
        grid = QGridLayout()
        grid.setSpacing(6)
        for prefix, headers in self._GROUPS:
            # 末列空表头 = 按钮列（「+」在表头格，行尾「-」删行）
            table = CellFillTable(0, len(headers) + 1)
            table.setHorizontalHeaderLabels([*headers, ""])
            fixed_width_behavior(table)
            # 行头最后一节也要保留右分割线（主题里 :last 会裁掉它）
            table.verticalHeader().setProperty("headerKind", "vertical")
            table.verticalHeader().setDefaultSectionSize(28)
            table.itemChanged.connect(
                lambda item, p=prefix: self._on_item_changed(p, item)
            )
            self._tables[prefix] = table

            buttons = RowButtonColumn(
                table,
                add_tooltip="新增一行",
                delete_tooltip="删除该行",
            )
            buttons.add_clicked.connect(lambda p=prefix: self._add_row(p))
            buttons.delete_clicked.connect(
                lambda row, p=prefix: self._delete_row(p, row)
            )
            buttons.attach()
            self._buttons[prefix] = buttons

            # 按钮列固定宽；另一列用 Stretch 铺满面板（本窗体是全项目
            # 「表格不随父控件拉伸」约定的例外，不能右侧留整块空白）
            table.horizontalHeader().setSectionResizeMode(
                self._STRETCH_COLUMNS[prefix], QHeaderView.ResizeMode.Stretch
            )
            if prefix == "":
                table.setColumnWidth(0, 120)
                table.setColumnWidth(1, 60)
            else:
                table.setColumnWidth(0, 90)
                table.setColumnWidth(1, 150)
                table.setColumnWidth(2, 60)

        # 左：参数表跨全部行（上下撑满窗体）；右：围护公式（上）、支撑公式
        # （下）；面板之间画 1px 分割线（theme QSS 的 role="hline"/"vline"）：
        # 竖线隔开左面板与右列，横线隔开右上与右下
        grid.addWidget(self._tables[""], 0, 0, 3, 1)
        grid.addWidget(_separator(True), 0, 1, 3, 1)
        grid.addWidget(self._tables["F"], 0, 2)
        grid.addWidget(_separator(False), 1, 2)
        grid.addWidget(self._tables["Z"], 2, 2)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 0)  # 分割线列不参与拉伸
        grid.setColumnStretch(2, 3)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 0)  # 分割线行不参与拉伸
        grid.setRowStretch(2, 1)
        self._body.addLayout(grid, 1)

    # ------------------------------------------------------------------ 数据
    @staticmethod
    def _split_quantity_display(display: str) -> tuple[str, str, str]:
        """``类别|名称|单位`` → 三列；缺段按空字符串补齐（兼容旧库两段 / 一段）。"""
        parts = (display or "").split("|")
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]
        if len(parts) == 2:
            return parts[0], parts[1], ""
        return "", parts[0] if parts else "", ""

    @staticmethod
    def _split_param_display(display: str) -> tuple[str, str]:
        """参数显示名 ``名称 单位`` →（名称, 单位）；无空格时整串即名称。"""
        text = (display or "").strip()
        name, separator, unit = text.rpartition(" ")
        if not separator:
            return text, ""
        return name, unit

    def _fill(self) -> None:
        from app.core.calc.engine import load_params

        self._loading = True
        try:
            params = load_params(self._component)
            groups: dict[str, list[tuple[str, str, str]]] = {
                prefix: [] for prefix, _headers in self._GROUPS
            }
            for key, (display, expression) in params.items():
                # 旧版 FlashdGV：F/Z 开头且键长为 2 的进公式表，其余进参数表
                prefix = key[:1] if key[:1] in ("F", "Z") and len(key) == 2 else ""
                groups[prefix].append((key, display, expression))
            for prefix, table in self._tables.items():
                self._buttons[prefix].clear_row_buttons()
                rows = groups[prefix]
                table.setRowCount(len(rows))
                for index, (key, display, expression) in enumerate(rows):
                    table.setVerticalHeaderItem(index, QTableWidgetItem(key))
                    if prefix == "":
                        name, unit = self._split_param_display(display)
                        table.setItem(index, 0, QTableWidgetItem(name))
                        table.setItem(index, 1, QTableWidgetItem(unit))
                        table.setItem(index, 2, QTableWidgetItem(expression))
                    else:
                        category, name, unit = self._split_quantity_display(display)
                        table.setItem(index, 0, QTableWidgetItem(category))
                        table.setItem(index, 1, QTableWidgetItem(name))
                        table.setItem(index, 2, QTableWidgetItem(unit))
                        table.setItem(index, 3, QTableWidgetItem(expression))
                    self._buttons[prefix].add_row_button(index)
        finally:
            self._loading = False
        self._refresh_formula_warnings()

    # ------------------------------------------------------------------ 增删
    def _next_key(self, prefix: str) -> str | None:
        """该表下一个可用键：最小未占用、且未被任何公式引用（方案三）。"""
        used = {param.key for param in self._component.params}
        used |= self._deleted_keys
        for table in self._tables.values():
            for row in range(table.rowCount()):
                header = table.verticalHeaderItem(row)
                if header and header.text():
                    used.add(header.text())
        referenced = self._referenced_identifiers()
        if prefix == "":
            candidates = self._ALPHABET
        elif prefix == "F":
            candidates = tuple("F" + letter for letter in self._ALPHABET)
        else:
            candidates = tuple("Z" + letter for letter in self._ALPHABET)
        for key in candidates:
            if key not in used and key not in referenced:
                return key
        return None

    def _add_row(self, prefix: str) -> None:
        key = self._next_key(prefix)
        if key is None:
            FramelessMessageBox.information(
                self, "提示", "该表已没有可用的参数键（已被现有行或公式占用）。"
            )
            return
        table = self._tables[prefix]
        row = table.rowCount()
        table.insertRow(row)
        table.setVerticalHeaderItem(row, QTableWidgetItem(key))
        for column in range(table.columnCount() - 1):
            table.setItem(row, column, QTableWidgetItem(""))
        self._buttons[prefix].add_row_button(row)
        table.setCurrentCell(row, 0)
        table.scrollToItem(table.item(row, 0))
        self._refresh_formula_warnings()

    def _delete_row(self, prefix: str, row: int) -> None:
        table = self._tables[prefix]
        if row < 0 or row >= table.rowCount():
            return
        header = table.verticalHeaderItem(row)
        key = header.text() if header else ""
        table.removeRow(row)
        if key:
            # 只记下待删键，真正删库留到「确定」：单机关闭子窗体（取消）
            # 不得把参数悄悄从工程里删掉
            self._deleted_keys.add(key)
        # 「-」回调闭包按行号绑定，删行后后续行的按钮必须按新行号重建
        self._rebuild_row_buttons(prefix)
        self._refresh_formula_warnings()

    def _rebuild_row_buttons(self, prefix: str) -> None:
        table = self._tables[prefix]
        buttons = self._buttons[prefix]
        buttons.clear_row_buttons()
        for row in range(table.rowCount()):
            buttons.add_row_button(row)

    # -------------------------------------------------------------- 悬空引用
    def _defined_keys(self) -> set[str]:
        keys: set[str] = set()
        for table in self._tables.values():
            for row in range(table.rowCount()):
                header = table.verticalHeaderItem(row)
                if header and header.text():
                    keys.add(header.text())
        return keys

    def _referenced_identifiers(self) -> set[str]:
        """当前编辑内容里被引用的参数键（参数值 / 工程量公式 / 描述公式）。"""
        texts = [self._component.formula or ""]
        for prefix, table in self._tables.items():
            column = self._EXPRESSION_COLUMNS[prefix]
            for row in range(table.rowCount()):
                item = table.item(row, column)
                if item is not None:
                    texts.append(item.text())
        return {
            identifier
            for text in texts
            for identifier in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text or "")
        }

    def _missing_identifiers(self, expression: str) -> list[str]:
        """公式里引用了但当前表中不存在的参数键（只认 A~Z / FA~FZ / ZA~ZZ）。"""
        defined = self._defined_keys()
        missing: list[str] = []
        for identifier in sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression or ""))):
            if identifier.upper() in self._FORMULA_NAMES:
                continue
            if not self._KEY_PATTERN.match(identifier):
                continue
            if identifier not in defined:
                missing.append(identifier)
        return missing

    def _on_item_changed(self, prefix: str, item: QTableWidgetItem) -> None:
        if self._loading or self._warn_updating:
            return
        self._refresh_formula_warnings()

    def _refresh_formula_warnings(self) -> None:
        """工程量公式引用不存在的参数时标红并给出提示；引用修正后自动恢复。"""
        if self._loading or self._warn_updating:
            return
        self._warn_updating = True
        try:
            for prefix in ("F", "Z"):
                table = self._tables[prefix]
                column = self._EXPRESSION_COLUMNS[prefix]
                for row in range(table.rowCount()):
                    item = table.item(row, column)
                    if item is None:
                        continue
                    missing = self._missing_identifiers(item.text())
                    if missing:
                        item.setForeground(self._WARN_COLOR)
                        item.setToolTip(
                            "引用了不存在的参数：" + "、".join(missing)
                        )
                    else:
                        item.setData(Qt.ItemDataRole.ForegroundRole, None)
                        item.setToolTip("")
        finally:
            self._warn_updating = False

    # ------------------------------------------------------------------ 保存
    def save(self) -> None:
        component = self._component
        existing = {param.key: param for param in component.params}
        present_keys: set[str] = set()
        for prefix, table in self._tables.items():
            expression_column = self._EXPRESSION_COLUMNS[prefix]
            for index in range(table.rowCount()):
                header = table.verticalHeaderItem(index)
                key = header.text() if header else ""
                if not key:
                    continue
                present_keys.add(key)
                expression_item = table.item(index, expression_column)
                expression = expression_item.text().strip() if expression_item else ""
                if prefix == "":
                    name_item = table.item(index, 0)
                    unit_item = table.item(index, 1)
                    name = name_item.text().strip() if name_item else ""
                    unit = unit_item.text().strip() if unit_item else ""
                    display = f"{name} {unit}".strip()
                    empty = name == "" and unit == "" and expression == ""
                else:
                    category_item = table.item(index, 0)
                    name_item = table.item(index, 1)
                    unit_item = table.item(index, 2)
                    category = category_item.text().strip() if category_item else ""
                    name = name_item.text().strip() if name_item else ""
                    unit = unit_item.text().strip() if unit_item else ""
                    display = "|".join([category, name, unit])
                    empty = category == "" and name == "" and unit == "" and expression == ""
                if empty:
                    if key in existing:
                        self._drop_param(existing.pop(key))
                    continue
                if key in existing:
                    existing[key].value = f"{display}|{expression}"
                else:
                    component.params.append(ComponentParam(key=key, value=f"{display}|{expression}"))
        # 点「确定」才真正删除被「-」移除的参数行
        for key in self._deleted_keys:
            if key not in present_keys and key in existing:
                self._drop_param(existing.pop(key))

    def _drop_param(self, param: ComponentParam) -> None:
        """立即从构件参数集合移除（delete-orphan 级联删库，取消则整体回滚）。"""
        if param in self._component.params:
            self._component.params.remove(param)
        else:
            orm.session().delete(param)


class WidthEditDialog(FramelessDialog):
    """面宽原则编辑（旧版 FormWorkWidth，v4 起独立成原则）。

    「按工作面宽度计算 / 按沟槽总宽度计算」两种方式做成 tab 切换
    （旧版沟槽宽度取值单选 WorkWidth / B），当前 tab 即取值方式，
    表格只显示当前方式的明细。
    """

    _TABS = (
        ("按工作面宽度计算", "work", "工作面宽度表（mm）", WIDTH_KIND_WORK),
        ("按沟槽总宽度计算", "groove_b", "沟槽宽度表（mm）", WIDTH_KIND_GROOVE_B),
    )

    def __init__(self, width_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, "工作面宽原则编辑")
        self.resize(860, 460)
        self._width_id = width_id
        self._loading = False
        self._tables: dict[str, CellFillTable] = {}
        self._build_ui()
        self._fill()
        # 取值方式跟随当前 tab（旧版 grooveWidth 单选），切换只写会话、确认才落库。
        # 必须在 _fill() 之后才连：QTabWidget 的 currentChanged 会在显示/布局阶段
        # 延迟补发一次，若在 _fill() 之前连上，那一发会在对话框早已关闭后触发——
        # 槽内再用 isVisible() 挡掉关窗后的补发（早先版本在槽里直接 commit，
        # 补发撞上"下一次新建工程正在提交事务"就会重入 commit，把 SQLAlchemy
        # 的提交状态机打断，实测 IllegalStateChangeError / ResourceClosedError，
        # 也就是日志里那条 "session is in 'prepared' state"）。
        self._tabs.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        root = self.bodyLayout()
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("原则名称:"))
        self._name = QLineEdit()
        name_row.addWidget(self._name, 1)
        root.addLayout(name_row)

        self._tabs = QTabWidget()
        for title, key, table_title, kind in self._TABS:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(4, 4, 4, 4)
            label = QLabel(table_title)
            label.setProperty("role", "hint")
            layout.addWidget(label)
            table = CellFillTable(len(_WIDTH_CATEGORY_ORDER), len(_WIDTH_DNS) + 1)
            table.setHorizontalHeaderLabels(["类别"] + [f"DN{dn}" for dn in _WIDTH_DNS])
            table.verticalHeader().setVisible(False)
            for row_index, category in enumerate(_WIDTH_CATEGORY_ORDER):
                item = QTableWidgetItem(category)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                table.setItem(row_index, 0, item)
            # 固定列宽（可拖动）：初始列宽由 _fill 装填后按内容定一次，
            # 之后不随内容/窗体变化，总宽超出窗体即出横向滚动条
            fixed_width_behavior(table)
            layout.addWidget(table)
            self._tabs.addTab(page, title)
            self._tables[kind] = table
        root.addWidget(self._tabs, 1)

        button_row = QHBoxLayout()
        btn_reset = QPushButton("恢复图集默认")
        btn_reset.clicked.connect(self._reset_current)
        button_row.addWidget(btn_reset)
        button_row.addStretch(1)
        # Apple HIG：取消在左，确认（默认按钮）在右
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedWidth(76)
        btn_cancel.clicked.connect(self.reject)
        btn_yes = QPushButton("确认")
        btn_yes.setFixedWidth(76)
        btn_yes.setProperty("primary", "true")
        btn_yes.setDefault(True)
        btn_yes.clicked.connect(self._confirm)
        button_row.addWidget(btn_cancel)
        button_row.addWidget(btn_yes)
        root.addLayout(button_row)

    # ------------------------------------------------------------------ 数据
    def _width(self) -> PcpWidth | None:
        # expire 后的重载路径不做 autoflush，先把未 flush 的编辑写进事务
        # （flush 不提交，「取消」的回滚仍然整体丢弃），再强制重载 items
        orm.session().flush()
        width = orm.session().get(PcpWidth, self._width_id)
        if width is not None:
            orm.session().expire(width)
        return width

    def _fill(self) -> None:
        self._loading = True
        try:
            width = self._width()
            if width is None:
                return
            self._name.setText(width.name)
            index = 0 if width.groove_width != GROOVE_WIDTH_B else 1
            self._tabs.setCurrentIndex(index)
            data: dict[str, dict[str, dict[int, float]]] = {"work": {}, "groove_b": {}}
            for row in width.items:
                data.setdefault(row.kind, {}).setdefault(row.pipe_type, {})[int(row.dn)] = row.width
            for kind, table in self._tables.items():
                for row_index, category in enumerate(_WIDTH_CATEGORY_ORDER):
                    for column, dn in enumerate(_WIDTH_DNS, start=1):
                        value = data.get(kind, {}).get(category, {}).get(dn)
                        table.setItem(row_index, column, QTableWidgetItem("" if value is None else f"{value:g}"))
                # 首次装填按内容定初始列宽（Interactive 不会随内容自动重算），
                # 之后用户可拖动调整、宽度不再被覆盖
                table.resizeColumnsToContents()
        finally:
            self._loading = False

    def _on_tab_changed(self, _index: int) -> None:
        if self._loading or not orm.is_open() or not self.isVisible():
            return
        width = self._width()
        if width is None:
            return
        desired = GROOVE_WIDTH_WORK if self._tabs.currentIndex() == 0 else GROOVE_WIDTH_B
        if width.groove_width == desired:
            return  # 值没变就不写：延迟补发的信号不该产生多余的未落库修改
        width.groove_width = desired  # 确认时随本次编辑统一落库

    def _reset_current(self) -> None:
        """把当前 tab 的表恢复为图集默认（另一种方式的表不动）。"""
        kind = WIDTH_KIND_WORK if self._tabs.currentIndex() == 0 else WIDTH_KIND_GROOVE_B
        work, groove = project_io.default_width_tables()
        table_data = work if kind == WIDTH_KIND_WORK else groove
        table = self._tables[kind]
        for row_index, category in enumerate(_WIDTH_CATEGORY_ORDER):
            for column, dn in enumerate(_WIDTH_DNS, start=1):
                value = table_data.get(category, {}).get(dn)
                table.setItem(row_index, column, QTableWidgetItem("" if value is None else f"{value:g}"))
        self._apply_tables()

    def _apply_tables(self) -> None:
        if self._loading:
            return
        width = self._width()
        if width is None:
            return
        session = orm.session()
        for row in list(width.items):
            session.delete(row)
        session.flush()
        for kind, table in self._tables.items():
            for row_index, category in enumerate(_WIDTH_CATEGORY_ORDER):
                for column, dn in enumerate(_WIDTH_DNS, start=1):
                    item = table.item(row_index, column)
                    text = item.text().strip() if item else ""
                    try:
                        value = float(text)
                    except ValueError:
                        continue
                    session.add(
                        WidthItem(
                            width_id=width.id,
                            pipe_type=category,
                            dn=dn,
                            width=value,
                            kind=kind,
                            order_no=row_index * 100 + column,
                        )
                    )
        session.expire(width)  # 强制重载 items
        # 不在此处落库：整表替换是未提交修改，确认时统一 commit、取消随会话回滚

    def _confirm(self) -> None:
        self._apply_tables()
        width = self._width()
        if width is not None:
            name = self._name.text().strip()
            if not name:
                FramelessMessageBox.warning(self, "提示", "原则名称不得为空。")
                return
            if name != width.name:
                project_io.rename_width(width.id, name)
                bus().tree_structure_changed.emit()  # 同步原则横条与引用名
        project_io.commit()  # 本次编辑（两张宽度表、取值方式）在此统一落库
        bus().principle_changed.emit()
        self.accept()

    def reject(self) -> None:  # noqa: N802 - Qt 命名
        """取消：回滚会话，丢弃宽度表与取值方式的全部未落库修改。"""
        orm.session().rollback()
        super().reject()


class PrecipitationEditDialog(FramelessDialog):
    """挖填降水原则编辑（旧版 FormPrecipitation，v4 起独立成原则）。

    v10 起「挖填类型」面板（开挖类型 / 坞塝材质 / 坞塝回填 / 顶部回填，原属
    围护原则窗体）并入本窗体，与井型面板左右布置。

    井型表格列沿用 1.0：措施名称 / 选用 / 埋深 / 范围 / 侧数 / 间隔（旧版“道数”
    字段改用“侧数”表达），行序同 1.0（湿土排水 → 深井）；未选用行埋深、
    范围显示“-”且只读，已选用行的范围自最深已选用行向浅处推算
    （+∞ → 下一已选用行埋深，旧版 FlashFm）；下方实时给出降水描述
    （旧版 DiscribePreciptitation 的等价文案）。
    """

    _ROWS = PRECIPITATION_COLUMNS  # 湿土排水 → 深井，与旧版行序一致

    _COL_NAME, _COL_ENABLED, _COL_DEPTH, _COL_RANGE, _COL_SIDES, _COL_GAP = range(6)

    def __init__(self, precipitation_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, "挖填降水原则编辑")
        self.resize(760, 505)
        self._precipitation_id = precipitation_id
        self._loading = False
        self._build_ui()
        self._fill()

    def _build_ui(self) -> None:
        root = self.bodyLayout()
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("原则名称:"))
        self._name = QLineEdit()
        name_row.addWidget(self._name, 1)
        root.addLayout(name_row)

        box = QGroupBox("井型（埋深 m / 侧数 / 间隔 m）")
        layout = QVBoxLayout(box)
        self._table = CellFillTable(len(self._ROWS), 6)
        self._table.setHorizontalHeaderLabels(
            ["措施名称", "选用", "埋深", "范围", "侧数", "间隔"]
        )
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.verticalHeader().setVisible(False)  # 行标识已由“措施名称”列承担
        header = self._table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        # 固定列宽（可拖动）：初始列宽由 _fill 装填后按内容定一次（措施名称列
        # 不低于 110），之后不随窗体拉伸；总宽超出窗体即出横向滚动条
        fixed_width_behavior(self._table)
        layout.addWidget(self._table)
        self._table.itemChanged.connect(self._describe_change)

        # 「挖填类型」面板与井型面板左右布置
        panels = QHBoxLayout()
        panels.addWidget(self._build_excavation_box())
        panels.addWidget(box, 1)
        root.addLayout(panels, 1)

        # 降水描述在两面板下方（整宽，长文字换行可读）
        self._describe = QLabel("")
        self._describe.setProperty("role", "hint")
        self._describe.setWordWrap(True)
        root.addWidget(self._describe)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        # Apple HIG：取消在左，确认（默认按钮）在右
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedWidth(76)
        btn_cancel.clicked.connect(self.reject)
        btn_yes = QPushButton("确认")
        btn_yes.setFixedWidth(76)
        btn_yes.setProperty("primary", "true")
        btn_yes.setDefault(True)
        btn_yes.clicked.connect(self._confirm)
        button_row.addWidget(btn_cancel)
        button_row.addWidget(btn_yes)
        root.addLayout(button_row)

    def _build_excavation_box(self) -> QGroupBox:
        """「挖填类型」面板（原属围护原则窗体，v10 起并入本原则）。"""
        box = QGroupBox("挖填类型")
        form = QFormLayout(box)
        self._excvt = QComboBox()
        self._excvt.addItems(_EXCVT_CHOICES)
        self._dock_material = QLineEdit()
        self._dock_mode = QComboBox()
        self._dock_mode.addItems(_DOCK_CHOICES)
        self._cover = QLineEdit()
        form.addRow("开挖类型", self._excvt)
        form.addRow("坞塝材质", self._dock_material)
        form.addRow("坞塝回填", self._dock_mode)
        form.addRow("顶部回填", self._cover)
        return box

    def _precipitation(self) -> PcpPrecipitation | None:
        return orm.session().get(PcpPrecipitation, self._precipitation_id)

    def _fill(self) -> None:
        precipitation = self._precipitation()
        if precipitation is None:
            return
        self._loading = True
        try:
            self._name.setText(precipitation.name)
            # 挖填类型面板回填（CBOdock 反向映射，同原围护原则窗体 FlashDetail：
            # 至沟槽顶标高时顶部回填强制“素土”）
            self._excvt.setCurrentText(precipitation.excvt)
            self._dock_material.setText(precipitation.dock_l)
            self._cover.setText(precipitation.cover)
            if precipitation.dock_h == precipitation.dock_l:
                if precipitation.cover50 == precipitation.dock_l:
                    if precipitation.cover == precipitation.dock_l:
                        self._dock_mode.setCurrentText("至沟槽顶标高")
                        self._cover.setText("素土")
                    else:
                        self._dock_mode.setCurrentText("至管顶50cm")
                else:
                    self._dock_mode.setCurrentText("至管顶标高")
            else:
                self._dock_mode.setCurrentText("至管中心标高")
            for row_index, key in enumerate(self._ROWS):
                enabled, elevation, gap, sides = precipitation_enabled(key, precipitation)
                name_item = QTableWidgetItem(PRECIPITATION_LABELS[key])
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row_index, self._COL_NAME, name_item)
                check = QTableWidgetItem()
                check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                check.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
                self._table.setItem(row_index, self._COL_ENABLED, check)
                self._table.setItem(
                    row_index, self._COL_DEPTH,
                    QTableWidgetItem("" if not enabled else f"{elevation:g}"),
                )
                self._table.setItem(row_index, self._COL_RANGE, QTableWidgetItem(""))
                self._table.setItem(row_index, self._COL_SIDES, QTableWidgetItem(f"{sides:g}"))
                self._table.setItem(row_index, self._COL_GAP, QTableWidgetItem(f"{gap:g}"))
                # 全表文字居中（含表头，见 _build_ui）
                for column in (self._COL_NAME, self._COL_DEPTH, self._COL_RANGE,
                               self._COL_SIDES, self._COL_GAP):
                    item = self._table.item(row_index, column)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        finally:
            self._loading = False
        # 首次装填按内容定初始列宽（Interactive 不会随内容自动重算），之后
        # 用户可拖动调整、宽度不再被覆盖
        self._table.resizeColumnsToContents()
        if self._table.columnWidth(self._COL_NAME) < 110:
            self._table.setColumnWidth(self._COL_NAME, 110)
        self._describe_change()

    def _refresh_range(self) -> None:
        """旧版 FlashFm：自最深行向浅处推算“范围”列并维护埋深列的可用态。

        已选用行：范围 = 下一已选用行（更深处）的埋深，最深已选用行为“+∞”；
        未选用行：埋深、范围显示“-”且只读，勾选时埋深“-”复位为“0”。
        """
        if self._loading:
            return
        self._loading = True
        try:
            current = "+∞"
            for row in reversed(range(self._table.rowCount())):
                depth_item = self._table.item(row, self._COL_DEPTH)
                range_item = self._table.item(row, self._COL_RANGE)
                check = self._table.item(row, self._COL_ENABLED)
                enabled = check is not None and check.checkState() == Qt.CheckState.Checked
                if enabled:
                    if range_item is not None:
                        range_item.setText(current)
                    if depth_item is not None:
                        depth_item.setFlags(depth_item.flags() | Qt.ItemFlag.ItemIsEditable)
                        if depth_item.text().strip() in ("", "-"):
                            depth_item.setText("0")
                        current = depth_item.text()
                else:
                    if depth_item is not None:
                        depth_item.setFlags(depth_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        depth_item.setText("-")
                    if range_item is not None:
                        range_item.setText("-")
        finally:
            self._loading = False

    def _describe_change(self, *_args) -> None:
        self._refresh_range()
        self._apply_rows()
        precipitation = self._precipitation()
        if precipitation is not None:
            self._describe.setText(precipitation_text(precipitation))

    def _apply_rows(self) -> None:
        if self._loading:
            return
        precipitation = self._precipitation()
        if precipitation is None:
            return
        for row_index, key in enumerate(self._ROWS):
            check = self._table.item(row_index, self._COL_ENABLED)
            enabled = check is not None and check.checkState() == Qt.CheckState.Checked

            def _num(column: int, default: float) -> float:
                item = self._table.item(row_index, column)
                try:
                    return float(item.text()) if item and item.text().strip() else default
                except ValueError:
                    return default

            elevation = _num(self._COL_DEPTH, -1.0) if enabled else -1.0
            gap = _num(self._COL_GAP, 0.0)
            sides = _num(self._COL_SIDES, 0.0)
            setattr(precipitation, key, format_precipitation(elevation, gap, sides))
        # 不在此处落库：单元格编辑是未提交修改，确认时统一 commit、取消随会话回滚

    def _confirm(self) -> None:
        self._apply_rows()
        precipitation = self._precipitation()
        if precipitation is not None:
            name = self._name.text().strip()
            if not name:
                FramelessMessageBox.warning(self, "提示", "原则名称不得为空。")
                return
            if name != precipitation.name:
                project_io.rename_precipitation(precipitation.id, name)
                bus().tree_structure_changed.emit()  # 同步原则横条与引用名
            # 挖填类型走 principle_edit.apply_precipitation_excavation（与 AI 工具同路径）
            from app.services.principle_edit import apply_precipitation_excavation

            dock_mode = self._dock_mode.currentText()
            dock = self._dock_material.text().strip()
            cover = self._cover.text().strip()
            # GetDetailFormFm 原版映射
            if dock_mode == "至管顶50cm":
                dock_h, cover50, cover_value = dock, dock, cover
            elif dock_mode == "至管顶标高":
                dock_h, cover50, cover_value = dock, cover, cover
            elif dock_mode == "至管中心标高":
                dock_h, cover50, cover_value = cover, cover, cover
            else:  # 至沟槽顶标高
                dock_h, cover50, cover_value = dock, dock, dock
            apply_precipitation_excavation(
                precipitation.id,
                {
                    "excvt": self._excvt.currentText(),
                    "dock_l": dock,
                    "dock_h": dock_h,
                    "cover50": cover50,
                    "cover": cover_value,
                },
            )
        project_io.commit()  # 本次编辑（各井型参数 + 挖填类型）在此统一落库
        bus().principle_changed.emit()
        self.accept()

    def reject(self) -> None:  # noqa: N802 - Qt 命名
        """取消：回滚会话，丢弃井型参数的全部未落库修改。"""
        orm.session().rollback()
        super().reject()
