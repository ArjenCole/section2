"""2.0 零影响硬性约束的回归测试（docs/legacy_migration_plan.md §0.1 / §12.7）。

* 正常 2.0 启动 / 打开 / 保存 / 计算 / 汇总 / 导出路径不得 import
  ``legacy_migration``（模块级 import 图检查 + 运行时 sys.modules 检查）；
* 正常 2.0 工程保存 / 重开后 ``raw_key`` / ``legacy_meta`` 为空、来源原样，
  算量 / 汇总结果与改动前一致（新增可选字段零漂移）；
* 迁移后的 `.stn` 由 ``open_project`` 正常打开，无迁移专用分支、不弹迁移提示。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"

#: 允许（且必须）在函数内延迟 import 迁移包的入口（模块名）
_ALLOWED_MODULES = {
    "app.services.legacy_migration",  # 包自身（含全部子模块）
    "app.services.stn_migration",  # 薄兼容层（re-export）
    "app.services.element_library",  # _from_legacy_file：无 JSON 资产时的兜底
    "app.services.project_io",  # open_legacy_project / import_spcp：检测到 1.0 后
    "app.agent.tools.migrate",  # AI 迁移工具：调用时
}


def _module_name(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_type_checking(node: ast.If) -> bool:
    test = node.test
    return (
        isinstance(test, ast.Name)
        and test.id == "TYPE_CHECKING"
        or isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
    )


def _module_level_legacy_imports(tree: ast.AST) -> list[ast.stmt]:
    """模块顶层（不在任何函数 / 类体内）对 legacy_migration 的 import 语句。

    ``if TYPE_CHECKING:`` 分支只供类型标注，不进运行时 import 图，跳过。
    """
    found: list[ast.stmt] = []

    def visit(node: ast.AST, top_level: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(child, False)
                continue
            if isinstance(child, ast.If) and top_level and _is_type_checking(child):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name for alias in child.names]
                    if isinstance(child, ast.Import)
                    else [child.module or ""]
                )
                if top_level and any("legacy_migration" in name for name in names):
                    found.append(child)
            else:
                visit(child, top_level)

    visit(tree, True)
    return found


def test_no_module_level_import_of_legacy_migration() -> None:
    """除白名单入口外，任何模块顶层不得 import legacy_migration（静态检查）。"""
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        module = _module_name(path)
        if module in _ALLOWED_MODULES or module.startswith("app.services.legacy_migration"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - 语法错误由别的检查兜底
            continue
        if _module_level_legacy_imports(tree):
            offenders.append(module)
    assert not offenders, f"模块顶层 import 了迁移包（必须延迟）：{offenders}"


def test_core_modules_do_not_pull_legacy_migration(tmp_path: Path) -> None:
    """运行时检查：导入 2.0 核心模块不带入迁移包（独立子进程，杜绝会话污染）。

    子进程覆盖打开 / 保存 / 计算 / 汇总的非 Qt 核心链（project_io /
    stn_codec / summary / engine / element_library）；unit_vm 等带 Qt 的
    模块由 :func:`test_no_module_level_import_of_legacy_migration` 的静态
    AST 检查覆盖。
    """
    import os
    import subprocess

    script = "\n".join(
        [
            "import sys",
            "import app  # ICU 预加载",
            "for module in (",
            "    'app.services.stn_codec',",
            "    'app.services.stn_format',",
            "    'app.services.project_io',",
            "    'app.services.summary',",
            "    'app.services.element_library',",
            "    'app.core.calc.engine',",
            "):",
            "    __import__(module)",
            "assert 'app.services.legacy_migration' not in sys.modules, '正常路径带入了迁移包'",
        ]
    )
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONPATH"] = str(SRC)
    env["SECTION2_DATA_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=120,
    )
    assert result.returncode == 0, f"子进程检查失败：\n{result.stdout}\n{result.stderr}"


def test_normal_project_keeps_optional_fields_empty(tmp_path: Path, qapp) -> None:
    """正常 2.0 工程保存 / 重开后 raw_key / legacy_meta 为空、算量口径不变。"""
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element, ElementQuantity, PcpFoundation
    from app.services import project_io
    from app.services.project_io import NewProjectSpec

    spec = NewProjectSpec(
        path=tmp_path / "normal.stn",
        project_name="零漂移工程",
        unit_names=["工程一"],
    )
    project_io.new_project(spec)
    try:
        unit = project_io.units(project_io.segments()[0].id)[0]
        from app.viewmodels import unit_vm

        element = unit_vm.create_element(
            unit.id,
            category=7,  # 构筑物：带工程量行
            name="检查井",
            depth="3",
            amount="4",
            quantities=[("构筑物", "垫层", "m3", "1.5")],
        )
        # 原生工程量行不带 raw_key；构件不带 legacy_meta
        assert element.quantities[0].raw_key == ""
        assert (element.legacy_meta or "") == ""
        foundation = orm.session().scalars(select(PcpFoundation)).first()
        assert (foundation.legacy_meta or "") == ""
        project_io.save()

        path = project_io.current_path()
    finally:
        project_io.close_project()

    # 重开：可选字段仍为空、工程量键按三列拼
    project_io.open_project(path)
    try:
        rows = list(orm.session().scalars(select(ElementQuantity)))
        assert len(rows) == 1
        assert rows[0].raw_key == ""
        elements = list(orm.session().scalars(select(Element)))
        assert all((e.legacy_meta or "") == "" for e in elements)
        # 汇总正常出数（键 = 类别|项目|单位）
        from app.services.summary import unit_summary

        summary = unit_summary(elements[0].unit_id)
        assert any(row["key"] == "构筑物|垫层|m3" for row in summary)
    finally:
        project_io.close_project()


def test_migrated_file_opens_without_notice(tmp_path: Path, qapp) -> None:
    """迁移产物是普通 2.0 文件：open_project 正常分支打开，不弹迁移提示。"""
    from app.services import legacy_migration, project_io

    source = Path(__file__).parent / "fixtures" / "legacy" / "样例-基础版.stn"
    target = tmp_path / "migrated.stn"
    legacy_migration.migrate(source, target)

    assert project_io.open_project(target) == target
    try:
        # 无迁移提示（迁移文件不区别对待；只有打开 1.0 原文件时才有提示）
        assert project_io.last_migration_notice() == ""
    finally:
        project_io.close_project()
