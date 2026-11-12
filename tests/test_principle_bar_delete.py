"""原则横条「删除原则」回归测试。

用户反馈（两轮）：
1. 主页面原则横条右键「删除原则」必报 `NameError`（未导入 QMessageBox）；
2. 确认框文案里的 X 不显示（正文是富文本，``<X>`` 被当成 HTML 标签吞掉），
   且希望弹窗里能下拉选择替代原则。

这里锁定：确认框正文能真正显示原则名（含尖括号等特殊字符）、下拉框候选
与默认值、改选后按所选原则并入引用、取消不删、只剩一条时只提示。
"""

import pytest

#: 四类原则：kind → 建第二条原则的工厂名
_KINDS = {
    "enclosure": "create_enclosure",
    "foundation": "create_foundation",
    "precipitation": "create_precipitation",
    "width": "create_width",
}
_LISTERS = {
    "enclosure": "enclosures",
    "foundation": "foundations",
    "precipitation": "precipitations",
    "width": "width_principles",
}


def _make_second(kind: str):
    from app.services import project_io

    created = getattr(project_io, _KINDS[kind])()
    assert created is not None
    return created


def _names(kind: str) -> list[str]:
    from app.services import project_io

    return [item.name for item in getattr(project_io, _LISTERS[kind])()]


def _rendered_text(label) -> str:
    """QLabel 富文本正文“用户实际看到的文字”（标签被吞掉时这里也拿不到）。"""
    from PySide6.QtGui import QTextDocument

    document = QTextDocument()
    document.setHtml(label.text())
    return document.toPlainText()


class _FakeDeleteDialog:
    """替身：跳过模态 exec，按用例设定返回 Accepted / Rejected 与所选原则。"""

    last: "_FakeDeleteDialog | None" = None
    accept = True
    chosen: str | None = None

    def __init__(self, _parent, *, principle_name, candidates, target) -> None:
        from PySide6.QtWidgets import QDialog

        self._accepted = QDialog.DialogCode.Accepted if self.accept else QDialog.DialogCode.Rejected
        self.principle_name = principle_name
        self.candidates = list(candidates)
        self.target = target
        self._chosen = self.chosen or target
        _FakeDeleteDialog.last = self

    def exec(self):
        return self._accepted

    def replacement(self) -> str:
        return self._chosen


@pytest.fixture()
def fake_dialog(monkeypatch):
    """把 principle_bar 里的确认框换成替身，返回替身类（可设 accept / chosen）。"""

    from app.views.panels import principle_bar as bar_module

    _FakeDeleteDialog.last = None
    _FakeDeleteDialog.accept = True
    _FakeDeleteDialog.chosen = None
    monkeypatch.setattr(bar_module, "DeletePrincipleDialog", _FakeDeleteDialog)
    return _FakeDeleteDialog


# --------------------------------------------------------------------------- #
# 确认框本身
# --------------------------------------------------------------------------- #
# 注意：下面的对话框用例都先 show() 再 close()。无边框对话框里含 QComboBox 时，
# 未 show 就直接 close()（→ done() 排期 deleteLater）会在 Qt 拆除阶段偶发
# access violation（PySide6 6.11 + offscreen 下实测多次复现，崩溃点在 conftest
# 清理遗留顶层控件的 allWidgets() 上）；show 过之后关闭即稳定，也更贴近真实用法。
def test_delete_dialog_shows_name_and_lists_candidates(qapp):
    from app.views.dialogs.delete_principle_dialog import DeletePrincipleDialog

    dialog = DeletePrincipleDialog(
        None, principle_name="默认围护原则", candidates=["钢板桩", "放坡开挖"], target="钢板桩"
    )
    dialog.show()
    qapp.processEvents()
    try:
        assert [dialog._combo.itemText(i) for i in range(dialog._combo.count())] == [
            "钢板桩",
            "放坡开挖",
        ]
        assert dialog._combo.currentText() == "钢板桩"
        assert dialog.replacement() == "钢板桩"
        text = _rendered_text(dialog._text)
        assert "默认围护原则" in text and "钢板桩" in text
        # 改选后正文立刻跟着变
        dialog._combo.setCurrentText("放坡开挖")
        assert "放坡开挖" in _rendered_text(dialog._text)
        assert dialog.replacement() == "放坡开挖"
    finally:
        dialog.close()


def test_delete_dialog_keeps_angle_bracket_names_visible(qapp):
    """原则名里的 < > & 必须原样显示（原先写成 <目标原则> 会被富文本吞掉）。"""
    from app.views.dialogs.delete_principle_dialog import DeletePrincipleDialog

    dialog = DeletePrincipleDialog(
        None,
        principle_name="被删<原则>&1",
        candidates=["目标<原则>&2"],
        target="目标<原则>&2",
    )
    dialog.show()
    qapp.processEvents()
    try:
        text = _rendered_text(dialog._text)
        assert "被删<原则>&1" in text
        assert "目标<原则>&2" in text
    finally:
        dialog.close()


# --------------------------------------------------------------------------- #
# 删除流程
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_delete_principle_asks_and_deletes(qapp, project, fake_dialog, kind):
    from app.views.panels.principle_bar import PrincipleBar

    created = _make_second(kind)
    names_before = _names(kind)
    assert created.name in names_before

    bar = PrincipleBar()
    bar.reload()
    bar._delete_principle(kind, created.name)

    asked = fake_dialog.last
    assert asked is not None, "应当弹出删除确认框"
    assert asked.principle_name == created.name
    assert created.name not in asked.candidates  # 不能选被删的那条
    assert asked.target in asked.candidates
    assert created.name not in _names(kind)
    assert len(_names(kind)) == len(names_before) - 1


def test_delete_principle_uses_selected_replacement(qapp, project, fake_dialog):
    """在下拉框里改选另一条原则：构件引用并入所选原则，而不是默认那条。"""
    from app.services import project_io
    from app.viewmodels import unit_vm
    from app.views.panels.principle_bar import _KIND_ENCLOSURE, PrincipleBar

    from conftest import first_unit_id, make_element

    victim = _make_second(_KIND_ENCLOSURE)
    keep = _make_second(_KIND_ENCLOSURE)
    _make_second(_KIND_ENCLOSURE)  # 默认替代取“其余原则的最后一条”，与 keep 区分开
    element_id = make_element("引用被删原则的管", pe_name=victim.name)
    assert element_id
    default_target = project_io.merge_target_enclosure(victim.name)
    assert default_target != keep.name  # 默认替代不是“keep”，确保改选真的生效
    fake_dialog.chosen = keep.name

    bar = PrincipleBar()
    bar.reload()
    bar._delete_principle(_KIND_ENCLOSURE, victim.name)

    assert victim.name not in _names(_KIND_ENCLOSURE)
    assert unit_vm.element_rows(first_unit_id())[0].pe_name == keep.name


def test_delete_principle_cancelled_keeps_it(qapp, project, fake_dialog):
    from app.views.panels.principle_bar import _KIND_ENCLOSURE, PrincipleBar

    created = _make_second(_KIND_ENCLOSURE)
    fake_dialog.accept = False

    bar = PrincipleBar()
    bar.reload()
    bar._delete_principle(_KIND_ENCLOSURE, created.name)

    assert created.name in _names(_KIND_ENCLOSURE)


def test_delete_last_principle_only_hints(qapp, project, fake_dialog, monkeypatch):
    """只剩一条时不弹确认框，只提示「至少需要一种…」。"""
    from app.views.panels import principle_bar as bar_module
    from app.views.panels.principle_bar import _KIND_ENCLOSURE, PrincipleBar

    shown: list[str] = []
    monkeypatch.setattr(
        bar_module.FramelessMessageBox,
        "information",
        lambda _parent, _title, text, *_args, **_kwargs: shown.append(text),
    )
    only = _names(_KIND_ENCLOSURE)[0]

    bar = PrincipleBar()
    bar.reload()
    bar._delete_principle(_KIND_ENCLOSURE, only)

    assert fake_dialog.last is None
    assert shown and "至少需要" in shown[0]
    assert only in _names(_KIND_ENCLOSURE)


def test_delete_principle_from_main_window_reloads_table(qapp, project, fake_dialog):
    """主页面原则横条删除原则：构件引用并入替代原则、表格不报错。"""
    from app.core.event_bus import bus
    from app.services import project_io
    from app.services.element_library import element_library
    from app.viewmodels.unit_vm import element_rows
    from app.views.main_window import MainWindow

    victim = _make_second("enclosure")

    window = MainWindow()
    try:
        bus().project_opened.emit(str(project))
        window._tree_panel.vm.load()
        qapp.processEvents()
        root = window._tree_panel._tree.topLevelItem(0)
        window._tree_panel._tree.setCurrentItem(root.child(0).child(0))
        qapp.processEvents()

        template = element_library().units_of("直埋混凝土管")[0].elements[0]
        window._insert_template(template)
        qapp.processEvents()
        node = window._tree_panel.current_node
        row = element_rows(node.id)[0]
        project_io.commit()
        from app.viewmodels import unit_vm

        unit_vm.update_element(row.id, pe_name=victim.name)
        qapp.processEvents()
        assert element_rows(node.id)[0].pe_name == victim.name

        target = project_io.merge_target_enclosure(victim.name)
        window._principle_bar._delete_principle("enclosure", victim.name)
        qapp.processEvents()

        assert victim.name not in [item.name for item in project_io.enclosures()]
        # 引用并入替代原则，主表格跟着刷新
        assert element_rows(node.id)[0].pe_name == target
        assert window._unit_panel._element_table.rowCount() == 1
    finally:
        window.close()


# --------------------------------------------------------------------------- #
# 引用并入范围（左右分设 / 改名跟随）
# --------------------------------------------------------------------------- #
def test_delete_enclosure_merges_left_right_references(qapp, project):
    """左右分设 / 合槽组员按名引用左右原则：删除时一并并入替代原则（不悬空）。"""
    from app.core.models.models import LR_PE_TEXT
    from app.services import project_io
    from app.viewmodels import unit_vm

    from conftest import first_unit_id, make_element

    victim = _make_second("enclosure")
    other = _make_second("enclosure")
    element_id = make_element("分设管", pe_name=victim.name)
    unit_vm.update_element(element_id, pe_name=LR_PE_TEXT)
    unit_vm.update_element(element_id, pe_left_name=victim.name, pe_right_name=other.name)
    project_io.commit()

    target = project_io.merge_target_enclosure(victim.name)
    assert project_io.delete_enclosure(victim.id, target) is None

    row = unit_vm.element_rows(first_unit_id())[0]
    assert row.pe_name == LR_PE_TEXT  # 占位名不变
    assert row.pe_left_name == target  # 悬空引用已并入
    assert row.pe_right_name == other.name  # 另一侧不受影响


def test_rename_enclosure_follows_left_right_references(qapp, project):
    """围护原则改名时，左右分设的两列引用一起改名。"""
    from app.core.models.models import LR_PE_TEXT
    from app.services import project_io
    from app.viewmodels import unit_vm

    from conftest import first_unit_id, make_element

    victim = _make_second("enclosure")
    other = _make_second("enclosure")
    element_id = make_element("分设改名管", pe_name=victim.name)
    unit_vm.update_element(element_id, pe_name=LR_PE_TEXT)
    unit_vm.update_element(element_id, pe_left_name=victim.name, pe_right_name=other.name)
    project_io.commit()

    project_io.rename_enclosure(victim.id, "改名后的围护原则")

    row = unit_vm.element_rows(first_unit_id())[0]
    assert row.pe_left_name == "改名后的围护原则"
    assert row.pe_right_name == other.name
