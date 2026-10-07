"""原则编辑子对话框（复刻旧版 FmPcp 各窗体）。

从 principle_panel 迁移而来，供原则编辑主对话框（EnclosureEditDialog /
FoundationEditDialog，复刻 FormPE / FormPF）与横条等处复用：

* :class:`EnclosureWorkDialog` —— 分级围护编辑（FormEcls：围护构件分级表 +
  右侧确认/取消，做法埋深与止水构件在原则主窗体编辑）；
* :class:`ComponentEditDialog` —— 构件编辑器（FormCpntEdit：左参数表、
  右上围护公式、右下支撑公式，行头显示键名）；
* :class:`WorkWidthDialog` —— 工作面宽度 / 沟槽宽度表（FormWorkWidth）；
* :class:`PrecipitationDialog` —— 降水编辑（FormPrecipitation）。
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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
    WorkWidth,
    format_precipitation,
    parse_precipitation,
)
from app.services import project_io
from app.views.widgets.cell_fill_table import CellFillTable
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox

_WIDTH_DNS = tuple(range(0, 3100, 100))

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
    """原则子编辑对话框的公共骨架：无边框（Quotor 风格）+ 确定 = 写库 / 取消 = 丢弃。

    ``with_buttons=False`` 时不加底部按钮行，由子类自建（如分级围护编辑的
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
    """分级围护编辑（旧版 FormEcls）：围护构件分级表 + 右侧竖排确认/取消。

    布局与交互照抄 FormEcls：固定勾选 ↔ 级高 1 / -1（均分级高只读显示
    “均分高度”）；围护类型下拉按库模板重建级构件；双击“围护形式描述”打开
    构件编辑器（FormCpntEdit）；Insert 插入分级、Delete 删除选中分级
    （至少保留一级）；“+” 加在最后。做法埋深与止水构件在原则主窗体
    （FormPE）编辑，本窗体不再重复。
    """

    def __init__(self, work: EnclosureWork, parent: QWidget | None = None) -> None:
        super().__init__("分级围护编辑", parent, with_buttons=False)
        self.resize(695, 460)
        self._work = work
        self._repair_levels()
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
            project_io.commit()

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
        project_io.commit()
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
        project_io.commit()
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
        project_io.commit()
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
        project_io.commit()
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
            project_io.commit()
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
        self.horizontalHeader().setStretchLastSection(True)
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


class ComponentEditDialog(PrincipleSubDialog):
    """构件编辑器（旧版 FormCpntEdit）：左参数表（A~Z），右上围护公式（FA~FZ）、
    右下支撑公式（ZA~ZZ），底部确认/取消修改。

    行头显示参数键；表格只列构件已有的参数行（旧版不提供增删行，参数集
    来自构件库模板）；描述公式为库数据，不在本窗体编辑。
    """

    _GROUPS = (
        # (键前缀, 表头, 网格位置)
        ("", "参数名称", "参数值", 0, 0),
        ("F", "围护工程量", "计算公式", 0, 1),
        ("Z", "支撑工程量", "计算公式", 1, 1),
    )

    def __init__(self, component: Component, parent: QWidget | None = None) -> None:
        super().__init__("构件编辑器", parent)
        self.resize(940, 480)
        self._component = component
        self._tables: dict[str, QTableWidget] = {}
        self._build()
        self._fill()

    def _build(self) -> None:
        grid = QGridLayout()
        grid.setSpacing(6)
        for prefix, header_key, header_value, row, column in self._GROUPS:
            table = CellFillTable(0, 2)
            table.setHorizontalHeaderLabels([header_key, header_value])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.verticalHeader().setDefaultSectionSize(28)
            grid.addWidget(table, row, column)
            self._tables[prefix] = table
        grid.addWidget(self._tables[""], 0, 0, 2, 1)  # 参数表跨两行（左列上下满高）
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        self._body.addLayout(grid, 1)

    def _fill(self) -> None:
        from app.core.calc.engine import load_params

        params = load_params(self._component)
        groups: dict[str, list[tuple[str, tuple[str, str]]]] = {"": [], "F": [], "Z": []}
        for key, pair in params.items():
            # 旧版 FlashdGV：F/Z 开头且键长为 2 的进公式表，其余进参数表
            prefix = key[:1] if key[:1] in ("F", "Z") and len(key) == 2 else ""
            groups[prefix].append((key, pair))
        for prefix, table in self._tables.items():
            rows = groups[prefix]
            table.setRowCount(len(rows))
            for index, (key, (display, expression)) in enumerate(rows):
                table.setVerticalHeaderItem(index, QTableWidgetItem(key))
                table.setItem(index, 0, QTableWidgetItem(display))
                table.setItem(index, 1, QTableWidgetItem(expression))

    def save(self) -> None:
        component = self._component
        existing = {param.key: param for param in component.params}
        for prefix, table in self._tables.items():
            for index in range(table.rowCount()):
                header = table.verticalHeaderItem(index)
                key = header.text() if header else ""
                if not key:
                    continue
                display_item = table.item(index, 0)
                value_item = table.item(index, 1)
                display = display_item.text().strip() if display_item else ""
                value = value_item.text().strip() if value_item else ""
                if display == "" and value == "":
                    if key in existing:
                        orm.session().delete(existing.pop(key))
                    continue
                if key in existing:
                    existing[key].value = f"{display}|{value}"
                else:
                    component.params.append(ComponentParam(key=key, value=f"{display}|{value}"))


class WorkWidthDialog(PrincipleSubDialog):
    """工作面宽度 / 沟槽宽度表（旧版 FormWorkWidth）：类别 × DN0~DN3000。"""

    def __init__(self, enclosure: PcpEnclosure, parent: QWidget | None = None) -> None:
        super().__init__("工作面宽度与沟槽宽度", parent)
        self._enclosure = enclosure
        self._tables: dict[str, QTableWidget] = {}
        self._build()
        self._fill()

    def _build(self) -> None:
        mode_box = QGroupBox("沟槽宽度取值")
        mode_layout = QHBoxLayout(mode_box)
        self._radio_work = QRadioButton("按工作面宽度表（断面推算）")
        self._radio_b = QRadioButton("直接采用沟槽宽度表")
        group = QButtonGroup(self)
        group.addButton(self._radio_work)
        group.addButton(self._radio_b)
        mode_layout.addWidget(self._radio_work)
        mode_layout.addWidget(self._radio_b)
        mode_layout.addStretch(1)
        self._body.addWidget(mode_box)

        for kind, title in (("work", "工作面宽度表（mm）"), ("groove_b", "沟槽宽度表（mm）")):
            box = QGroupBox(title)
            layout = QVBoxLayout(box)
            table = CellFillTable(len(_WIDTH_CATEGORY_ORDER), len(_WIDTH_DNS) + 1)
            table.setHorizontalHeaderLabels(["类别"] + [f"DN{dn}" for dn in _WIDTH_DNS])
            table.verticalHeader().setVisible(False)
            for row_index, category in enumerate(_WIDTH_CATEGORY_ORDER):
                item = QTableWidgetItem(category)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                table.setItem(row_index, 0, item)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            layout.addWidget(table)
            self._body.addWidget(box, 1)
            self._tables[kind] = table

        reset = QPushButton("恢复图集默认")
        reset.clicked.connect(self._reset)
        self._body.addWidget(reset)

    def _fill(self) -> None:
        self._radio_work.setChecked(self._enclosure.groove_width == "WorkWidth")
        self._radio_b.setChecked(self._enclosure.groove_width != "WorkWidth")
        for kind, table in self._tables.items():
            data: dict[str, dict[int, float]] = {}
            for row in self._enclosure.widths:
                if row.kind == kind:
                    data.setdefault(row.pipe_type, {})[int(row.dn)] = row.width
            for row_index, category in enumerate(_WIDTH_CATEGORY_ORDER):
                for column, dn in enumerate(_WIDTH_DNS, start=1):
                    value = data.get(category, {}).get(dn)
                    table.setItem(row_index, column, QTableWidgetItem("" if value is None else f"{value:g}"))

    def _reset(self) -> None:
        work, groove = project_io.default_width_tables()
        session = orm.session()
        for row in list(self._enclosure.widths):
            session.delete(row)
        session.flush()
        project_io.seed_width_tables(session, self._enclosure, work, groove)
        session.expire(self._enclosure)  # expire_on_commit=False：让 widths 集合重载
        project_io.commit()
        self._enclosure = session.get(PcpEnclosure, self._enclosure.id)
        self._fill()

    def save(self) -> None:
        self._enclosure.groove_width = GROOVE_WIDTH_WORK if self._radio_work.isChecked() else GROOVE_WIDTH_B
        session = orm.session()
        for kind, table in self._tables.items():
            for row_index, category in enumerate(_WIDTH_CATEGORY_ORDER):
                for column, dn in enumerate(_WIDTH_DNS, start=1):
                    item = table.item(row_index, column)
                    text = item.text().strip() if item else ""
                    try:
                        value = float(text)
                    except ValueError:
                        continue
                    row = next(
                        (
                            width
                            for width in self._enclosure.widths
                            if width.kind == kind and width.pipe_type == category and width.dn == dn
                        ),
                        None,
                    )
                    if row is None:
                        session.add(
                            WorkWidth(
                                enclosure_id=self._enclosure.id,
                                pipe_type=category,
                                dn=dn,
                                width=value,
                                kind=kind,
                                order_no=row_index * 100 + column,
                            )
                        )
                    else:
                        row.width = value
        session.expire(self._enclosure)  # expire_on_commit=False：新增/改动的宽度行重载


class PrecipitationDialog(PrincipleSubDialog):
    """降水编辑（旧版 FormPrecipitation）：五种井型的启用 / 深度 / 井距 / 侧数。"""

    _ROWS = tuple(reversed(PRECIPITATION_COLUMNS))  # 深井 → 湿土排水，与旧版行序一致

    def __init__(self, enclosure: PcpEnclosure, parent: QWidget | None = None) -> None:
        super().__init__("降水设置", parent)
        self._enclosure = enclosure
        self._build()
        self._fill()

    def _build(self) -> None:
        box = QGroupBox("井型（深度阈值 m / 井距 m / 侧数）")
        layout = QVBoxLayout(box)
        self._table = CellFillTable(len(self._ROWS), 4)
        self._table.setHorizontalHeaderLabels(["启用", "深度阈值 m", "井距 m", "侧数"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setDefaultSectionSize(28)
        for row_index, key in enumerate(self._ROWS):
            name_item = QTableWidgetItem(PRECIPITATION_LABELS[key])
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setVerticalHeaderItem(row_index, None)
            self._table.setItem(row_index, 0, name_item)
        layout.addWidget(self._table)
        self._describe = QLabel("")
        self._describe.setProperty("role", "hint")
        self._describe.setWordWrap(True)
        layout.addWidget(self._describe)
        self._table.itemChanged.connect(self._describe_change)
        self._body.addWidget(box)

    def _fill(self) -> None:
        self._loading = True
        for row_index, key in enumerate(self._ROWS):
            enabled, elevation, gap, sides = precipitation_enabled(key, self._enclosure)
            self._table.setVerticalHeaderItem(row_index, QTableWidgetItem(PRECIPITATION_LABELS[key]))
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
            self._table.setItem(row_index, 0, check)
            self._table.setItem(row_index, 1, QTableWidgetItem("" if not enabled else f"{elevation:g}"))
            self._table.setItem(row_index, 2, QTableWidgetItem(f"{gap:g}"))
            self._table.setItem(row_index, 3, QTableWidgetItem(f"{sides:g}"))
        self._loading = False
        self._describe_change()

    def _describe_change(self, *_args) -> None:
        self._apply_rows()
        self._describe.setText(precipitation_text(self._enclosure))

    def _apply_rows(self) -> None:
        if getattr(self, "_loading", True):
            return
        for row_index, key in enumerate(self._ROWS):
            check = self._table.item(row_index, 0)
            enabled = check is not None and check.checkState() == Qt.CheckState.Checked

            def _num(column: int, default: float) -> float:
                item = self._table.item(row_index, column)
                try:
                    return float(item.text()) if item and item.text().strip() else default
                except ValueError:
                    return default

            elevation = _num(1, -1.0) if enabled else -1.0
            gap = _num(2, 0.0)
            sides = _num(3, 0.0)
            setattr(self._enclosure, key, format_precipitation(elevation, gap, sides))

    def save(self) -> None:
        project_io.commit()
