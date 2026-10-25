"""默认工具注册表：全量工具在这里组装。

工具按领域分文件（project/tree/element/element_parts/principle/reference/
compute/migrate/summary/meta），每个模块提供 ``register(registry)``。
共 69 个工具（多原则引用 5 个工具已随功能取消移除）：

- project 7、tree 6、element 8、element_parts 12、principle 20、
  reference 8、compute 3、migrate 2、summary 4、meta 2（含 get_conventions）——
  减去重复计数的 get_current_context（在 meta 中）= 69。
"""

from __future__ import annotations

from app.agent.tool_registry import ToolRegistry


def build_default_registry() -> ToolRegistry:
    from app.agent.tools import (
        compute,
        element,
        element_parts,
        meta,
        migrate,
        principle,
        project,
        reference,
        summary,
        tree,
    )

    registry = ToolRegistry()
    for module in (
        project,
        tree,
        element,
        element_parts,
        principle,
        reference,
        compute,
        migrate,
        summary,
        meta,
    ):
        module.register(registry)
    return registry
