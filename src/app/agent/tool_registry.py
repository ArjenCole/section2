"""工具注册表：名称 → (描述, JSON Schema, 执行器)。

单一事实来源：
- 内置 AI 面板消费 :meth:`ToolRegistry.to_openai_tools`（OpenAI function calling）
  与 :meth:`ToolRegistry.to_prompt_text`（不支持 function calling 时的文本协议）；
- MCP 适配层消费 :meth:`ToolRegistry.all_tools`（`Tool.parameters` 原样透传为
  ``inputSchema``）。

执行器签名 ``Callable[[dict], dict]``；业务失败返回 ``{"error": ...}``（带下一步
指引），用户取消确认返回 ``{"cancelled": true}``，正常结果也必须是 dict。
:meth:`execute` 统一兜底：未注册工具 / 未捕获异常都转成 ``{"error": ...}``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from app.agent.errors import ToolError

ToolExecutor = Callable[[dict], dict]


@dataclass
class Tool:
    """单个工具定义。"""

    name: str
    description: str
    parameters: dict
    executor: ToolExecutor
    #: 只读工具（allow_actions=false / headless 白名单的来源）
    read_only: bool = False


class ToolRegistry:
    """工具注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ------------------------------------------------------------------ 注册
    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def all_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def read_only_tools(self) -> list[Tool]:
        return [tool for tool in self._tools.values() if tool.read_only]

    def is_write(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool is not None and not tool.read_only

    # ------------------------------------------------------------------ 执行
    def execute(self, name: str, arguments: dict | str | None) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"未知工具：{name}。可用工具见 get_conventions 或工具列表。"}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError as error:
                return {"error": f"参数不是合法 JSON：{error}"}
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {"error": "参数必须是 JSON 对象。"}
        try:
            result = tool.executor(arguments)
        except ToolError as error:
            return {"error": str(error)}
        except Exception as error:  # 未预期异常：包成业务错误，避免循环中断
            return {"error": f"工具执行失败：{type(error).__name__}: {error}"}
        if not isinstance(result, dict):
            return {"error": f"工具 {name} 返回了非法结果类型：{type(result).__name__}"}
        return result

    # ------------------------------------------------------------------ 协议出口
    def to_openai_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    # ------------------------------------------------------------------ prompt
    @staticmethod
    def _format_params_compact(params: dict) -> str:
        """把参数 JSON Schema 压成单行文本（token 减半以上，Quotor 同款）。"""
        props = params.get("properties") or {}
        required = set(params.get("required") or [])
        parts: list[str] = []
        for name, spec in props.items():
            if not isinstance(spec, dict):
                spec = {}
            type_text = str(spec.get("type", "any"))
            enum_values = spec.get("enum")
            if enum_values:
                type_text = "|".join(str(value) for value in enum_values)
            items = spec.get("items")
            if isinstance(items, dict) and items.get("type"):
                type_text = f"{type_text}[{items['type']}]"
            text = name + ("*" if name in required else "") + f"({type_text})"
            if "default" in spec:
                text += f"={spec['default']}"
            description = " ".join(str(spec.get("description", "")).split())
            if description:
                text += f": {description}"
            parts.append(text)
        return "; ".join(parts) if parts else "无参数"

    def to_base_prompt(self) -> str:
        from app.agent.conventions import CONVENTIONS_TEXT

        if not self._tools:
            return ""
        lines = ["你可以调用以下工具操作 Section 2.0 市政管道工程量计算软件：", ""]
        for tool in self._tools.values():
            lines.append(f"### {tool.name} — {tool.description}")
            lines.append(f"参数: {self._format_params_compact(tool.parameters)}")
        lines.extend(
            [
                "",
                "## 调用格式",
                "需要工具时输出 function call；一次只调一个工具，等结果返回后再决定下一步。",
                "工具结果是 JSON：ok=true 为正常；含 error 为业务失败；",
                "含 cancelled=true 表示用户取消（不要重试同一工具）。",
                "",
                "## 核心约束",
                "- 禁止编造 id / 原则名 / 构件库索引：必须先查询再写。",
                "- 写操作前先用查询工具确认目标；批量操作先列计划。",
                "- 埋深/数量/参数值/含量可写算式原文（如 2.5+0.3），不要预计算后回写。",
                "- 计算结果的 expression / steps 是产品核心数据，原样引用，不要改写。",
                "- 用户取消操作后停止重试，说明状态并询问下一步。",
                "",
                "## 任务→工具速查",
                "- 看工程结构: get_project_tree；看构件: list_elements / get_element_detail",
                "- 录一条管: list_library_templates → insert_element_from_template（或 add_element）",
                "- 算工程量: compute_unit / compute_element（返回数值+表达式+中间步骤）",
                "- 改原则: list_principles → get_principle_detail → set_* / create_*",
                "- 查图集: resolve_atlas / query_atlas_table；查构件库: list_component_templates",
                "- 迁移旧工程: inspect_legacy_project → migrate_legacy_project",
                "- 汇总导出: get_unit_summary / export_excel",
                "",
                CONVENTIONS_TEXT,
            ]
        )
        return "\n".join(lines)

    def to_rules_for_context(self, context: dict | None = None) -> str:
        """按当前选中上下文生成补充规则（三层上下文的 prompt 层）。"""
        if not context:
            return ""
        parts: list[str] = []
        unit_id = context.get("unit_id")
        element_id = context.get("element_id")
        if unit_id:
            unit_name = context.get("unit_name") or ""
            parts.append(f"## 当前选中单位工程\nunit_id={unit_id}" + (f"（{unit_name}）" if unit_name else ""))
            parts.append(
                "可直接调用 list_elements / add_element / compute_unit；这些工具的 unit_id 可省略。"
            )
        if element_id:
            element_name = context.get("element_name") or ""
            parts.append(f"## 当前选中构件\nelement_id={element_id}" + (f"（{element_name}）" if element_name else ""))
            parts.append(
                "可直接调用 get_element_detail / update_element / add_pipe / add_param 等；"
                "element_id 可省略。"
            )
        if not parts:
            parts.append(
                "## 注意\n当前无选中单位工程/构件。请先 get_project_tree 获取 unit_id，"
                "或显式传 id；不要假设“当前”指向任何对象。"
            )
        return "\n\n".join(parts)

    def to_prompt_text(self, context: dict | None = None) -> str:
        base = self.to_base_prompt()
        rules = self.to_rules_for_context(context)
        return f"{base}\n\n{rules}" if base and rules else (base or rules)


# --------------------------------------------------------------------------- #
# 默认注册表（懒加载，避免模块循环导入）
# --------------------------------------------------------------------------- #
_DEFAULT: ToolRegistry | None = None


def build_default_registry() -> ToolRegistry:
    from app.agent.tools import build_default_registry as _build

    return _build()


def default_registry() -> ToolRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = build_default_registry()
    return _DEFAULT
