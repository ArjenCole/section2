"""原则编辑子对话框（复刻旧版 FmPcp 各窗体）。

从 principle_panel 迁移而来，供原则编辑主对话框（EnclosureEditDialog /
FoundationEditDialog，复刻 FormPE / FormPF）与横条等处复用：

* :class:`EnclosureWorkDialog` —— 做法编辑（FormEcls：多级围护 + 止水构件）；
* :class:`ComponentEditDialog` —— 构件公式编辑（FormCpntEdit：A~Z / FA~FZ / ZA~ZZ）；
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
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import base as orm
from app.core.models.models import (
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
    """原则子编辑对话框的公共骨架：无边框（Quotor 风格）+ 确定 = 写库 / 取消 = 丢弃。"""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, title)
        self.setMinimumWidth(560)
        self.saved = False
        self._loading = False
        self._body = QVBoxLayout()
        self._body.setSpacing(6)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", "true")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        outer = self.bodyLayout()
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(10)
        outer.addLayout(self._body)
        outer.addWidget(buttons)

    def _accept(self) -> None:
        self.save()
        self.saved = True
        self.accept()

    def save(self) -> None:  # pragma: no cover - 子类实现
        raise NotImplementedError


class EnclosureWorkDialog(PrincipleSubDialog):
    """做法编辑（旧版 FormEcls）：多级围护构件 + 止水构件。"""

    def __init__(self, work: EnclosureWork, parent: QWidget | None = None) -> None:
        super().__init__("编辑围护做法", parent)
        self._work = work
        self._build()
        self._fill()

    def _build(self) -> None:
        form_box = QGroupBox("做法参数")
        form = QFormLayout(form_box)
        self._min_depth = QLineEdit()
        form.addRow("最小适用埋深 m", self._min_depth)
        self._body.addWidget(form_box)
        box = QGroupBox("围护构件分级（自上而下；固定高度不勾选时与其余分级均分深度）")
        layout = QVBoxLayout(box)
        self._level_table = _LevelTable()
        self._level_table.insert_requested.connect(
            lambda: self._insert_level(self._level_table.currentRow())
        )
        self._level_table.delete_requested.connect(self._delete_levels)
        self._level_table.itemChanged.connect(self._on_level_changed)
        layout.addWidget(self._level_table, 1)
        level_bar = QHBoxLayout()
        for text, slot in (
            ("＋级", self._add_level),
            ("✕级", self._delete_levels),
            ("编辑构件公式…", self._edit_level_component),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            level_bar.addWidget(button)
        level_bar.addStretch(1)
        layout.addLayout(level_bar)
        self._describe = QLabel("")
        self._describe.setProperty("role", "hint")
        self._describe.setWordWrap(True)
        layout.addWidget(self._describe)
        self._body.addWidget(box, 1)

        waterstop_box = QGroupBox("止水构件")
        waterstop_form = QFormLayout(waterstop_box)
        self._waterstop_picker = QComboBox()
        self._waterstop_picker.addItems(project_io.component_library().names("WSi"))
        self._waterstop_picker.currentTextChanged.connect(self._on_waterstop_pick)
        self._btn_waterstop = QPushButton("编辑止水公式…")
        self._btn_waterstop.clicked.connect(self._edit_waterstop)
        waterstop_form.addRow("止水类型", self._waterstop_picker)
        waterstop_form.addRow("", self._btn_waterstop)
        self._body.addWidget(waterstop_box)
        self._ei_names = project_io.component_library().names("Ei")

    def _fill(self) -> None:
        self._loading = True
        try:
            work = self._work
            self._min_depth.setText(f"{work.min_depth:g}")
            levels = list(work.levels)
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
                self._level_table.setItem(row_index, 4, QTableWidgetItem(describe_component(component)))
            self._waterstop_picker.setCurrentText(
                work.waterstops[0].name if work.waterstops else "无"
            )
            component = work.levels[0].components[0] if work.levels and work.levels[0].components else None
            self._describe.setText(describe_component(component))
        finally:
            self._loading = False

    def _levels(self) -> list[EnclosureLevel]:
        return list(self._work.levels)

    def _add_level(self) -> None:
        # BTNadd（FormEcls）：新级加在最后
        self._insert_level()

    def _insert_level(self, position: int | None = None) -> None:
        """InsertCpnt（FormEcls）：新增一级（默认加最后，Insert 键插到当前行前）。"""
        library = project_io.component_library()
        names = library.names("Ei")
        levels = self._levels()
        if position is None or position < 0 or position > len(levels):
            position = len(levels)
        for item in levels:
            if item.order_no >= position:
                item.order_no += 1
        session = orm.session()
        session.add(
            EnclosureLevel(
                work_id=self._work.id,
                name=names[0] if names else "放坡",
                h=-1.0,
                step_width=1.0,
                order_no=position,
            )
        )
        session.flush()
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
        self._fill()

    def _edit_level_component(self) -> None:
        row = self._level_table.currentRow()
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

    def _on_waterstop_pick(self, text: str) -> None:
        library = project_io.component_library()
        old = self._work.waterstops[0] if self._work.waterstops else None
        if old is not None and old.name == text:
            return
        if old is not None:
            orm.session().delete(old)
        project_io.component_from_template(
            orm.session(), library, "WSi", text, enclosure_work_id=self._work.id
        )
        orm.session().expire(self._work)  # expire_on_commit=False：让 waterstops 集合重载
        self._work = orm.session().get(EnclosureWork, self._work.id)

    def _edit_waterstop(self) -> None:
        component = self._work.waterstops[0] if self._work.waterstops else None
        if component is None:
            return
        dialog = ComponentEditDialog(component, self)
        if dialog.exec() and dialog.saved:
            project_io.commit()

    def save(self) -> None:
        try:
            self._work.min_depth = float(self._min_depth.text() or 0)
        except ValueError:
            pass
        enclosure = orm.session().get(PcpEnclosure, self._work.enclosure_id)
        works = enclosure.works_sorted() if enclosure else []
        if self._work in works:
            for index, item in enumerate(works):
                item.order_no = index


class _LevelTable(QTableWidget):
    """做法分级表格：Insert 插入行 / Delete 删除选中行（原版 dGVCpnt_KeyUp）。"""

    insert_requested = Signal()
    delete_requested = Signal()

    def __init__(self) -> None:
        super().__init__(0, 5)
        self.setHorizontalHeaderLabels(
            ["固定高度", "级高 m", "平台宽度 m", "围护类型", "围护形式描述"]
        )
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
    """构件公式编辑（旧版 FormCpntEdit）：参数 A~Z / 工程量公式 FA~FZ / 支撑公式 ZA~ZZ。"""

    _GROUPS = (
        ("", "参数（A~Z）"),
        ("F", "工程量公式（FA~FZ，可用 height/width/count）"),
        ("Z", "支撑公式（ZA~ZZ）"),
    )

    def __init__(self, component: Component, parent: QWidget | None = None) -> None:
        super().__init__("编辑构件公式", parent)
        self.setMinimumWidth(720)
        self._component = component
        self._tables: dict[str, QTableWidget] = {}
        self._build()
        self._fill()

    def _build(self) -> None:
        name_box = QGroupBox("构件")
        form = QFormLayout(name_box)
        self._formula = QLineEdit()
        form.addRow("描述公式", self._formula)
        self._body.addWidget(name_box)
        for key, label in self._GROUPS:
            box = QGroupBox(label)
            layout = QVBoxLayout(box)
            table = QTableWidget(26, 3)
            table.setHorizontalHeaderLabels(["键", "显示名", "表达式 / 数值"])
            table.setColumnWidth(0, 40)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            table.verticalHeader().setVisible(False)
            layout.addWidget(table)
            self._body.addWidget(box, 1 if key == "" else 2)
            self._tables[key] = table

    def _fill(self) -> None:
        self._formula.setText(self._component.formula)
        from app.core.calc.engine import load_params

        params = load_params(self._component)
        for prefix, table in self._tables.items():
            for index in range(26):
                key = f"{prefix}{chr(ord('A') + index)}"
                display, expression = params.get(key, ("", ""))
                key_item = QTableWidgetItem(key)
                key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(index, 0, key_item)
                table.setItem(index, 1, QTableWidgetItem(display))
                table.setItem(index, 2, QTableWidgetItem(expression))

    def save(self) -> None:
        component = self._component
        component.formula = self._formula.text()
        existing = {param.key: param for param in component.params}
        for prefix, table in self._tables.items():
            for index in range(26):
                key = f"{prefix}{chr(ord('A') + index)}"
                display_item = table.item(index, 1)
                value_item = table.item(index, 2)
                display = display_item.text().strip() if display_item else ""
                value = value_item.text().strip() if value_item else ""
                if display == "" and value == "":
                    if key in existing:
                        orm.session().delete(existing.pop(key))
                    continue
                if display and value:
                    combined = f"{display}|{value}"
                elif display:
                    combined = f"{display}|"
                else:
                    combined = f"|{value}"
                if key in existing:
                    existing[key].value = combined
                else:
                    component.params.append(ComponentParam(key=key, value=combined))


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
            table = QTableWidget(len(_WIDTH_CATEGORY_ORDER), len(_WIDTH_DNS) + 1)
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
        self._enclosure = session.get(PcpEnclosure, self._enclosure.id)
        self._fill()

    def save(self) -> None:
        self._enclosure.groove_width = "WorkWidth" if self._radio_work.isChecked() else "B"
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
        self._table = QTableWidget(len(self._ROWS), 4)
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
