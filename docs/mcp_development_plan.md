# Section 2.0 MCP 服务器 + AI 助手二期开发方案

> 版本：v1.1（2026-10-20）
> 状态：待开发（本文档即开发任务书，交给实施方按第 10 章分阶段执行）
> 实施基线：仓库 `section2` master 分支 `085304a`，APP_VERSION 2.0.0.0
>
> **v1.0 → v1.1 变更**（对照参照系 Quotor 已验证路线后的修订）：
> 1. MCP 主路线由「独立无头进程（stdio）为主」改为 **Quotor 同款「GUI 进程内嵌 Streamable
>    HTTP MCP server」为主**，同一套工具注册表同时供内置 AI 面板与外部 MCP 客户端使用；
>    独立 CLI（stdio / HTTP / stdio 桥 / headless）降为辅助入口；
> 2. SDK 选型由 FastMCP 1.x 风格改为 **mcp SDK 2.x lowlevel API**（`Server(on_list_tools/
>    on_call_tool)` + `streamable_http_app()`；FastMCP 已在 mcp 2.0 中移除——Quotor 实施记录
>    明确踩过此坑）；
> 3. 工具上下文由「全部显式 id」改为 **「显式 id 为主、内嵌模式缺省取 GUI 当前选中」**；
> 4. 新增 **第 8 章 AI 助手二期开发方案**（工具注册表类化、上下文注入、双通道确认、
>    循环治理、prompt 紧凑格式等，逐项对齐 Quotor `agent/`）。

---

## 1. 背景与目标

Section 2.0 是市政管道工程量计算软件（PySide6 单窗体桌面应用，工程文件 `.stn2` = 单文件 SQLite）。
它已经内置一个小规模 AI 助手（右栏面板，OpenAI 兼容 SSE 对话 + 4 个构件增删改查工具，M7/M8 里程碑），
但 AI 只能在 GUI 内部、以"当前选中单位工程"为上下文使用这些能力。

本方案两件事：

1. **MCP 化**：把软件的全部功能做成 MCP 服务器——让任意 MCP 客户端（Codex / Claude Desktop /
   Cursor / Cline / VS Code / WorkBuddy…）里的 AI 助手能直接、完整地操作本软件：建工程、管项目树、
   录入构件、编辑六类原则、查图集、算工程量、迁移旧工程、汇总导出；
2. **AI 助手二期**：把内置 AI 助手从「4 个工具的演示级循环」升级为 Quotor 同款的生产级
   Agent 体系（注册表类化、上下文注入、双通道确认、循环治理），并让**内置面板与 MCP 共用
   同一套工具注册表**——工具只写一遍，两个出口。

### 1.1 交付物定义

| 交付物 | 说明 |
|---|---|
| 统一工具注册表 | `src/app/agent/` 类化改造：`Tool`/`ToolRegistry`/`build_default_registry()`，全量 74 个工具（见第 7 章） |
| MCP 服务器（内嵌主方案） | `src/app/mcp_server/`：GUI 进程内嵌 Streamable HTTP server（127.0.0.1 + Bearer 鉴权），暴露同一注册表 |
| 独立 CLI（辅助入口） | `section2-mcp`：stdio / http / `--connect` stdio 桥 / `--project` headless 只读，四模式 |
| AI 助手二期 | 上下文注入、双通道确认（含结构化确认卡与 cancelled 语义）、循环治理、prompt 紧凑格式、reasoning 处理 |
| 测试 | 适配层单测 + 内嵌 HTTP 协议/鉴权闭环 + 无头冒烟 + 对拍回归（并入现有 `tests/`） |
| 文档 | `docs/mcp.md`（启用方法与各客户端配置）；README 增补 MCP 与 AI 章节 |

### 1.2 目标

- 外部 MCP 客户端与内置 AI 面板**调用同一组工具、走同一条业务代码路径**
  （`viewmodels` 模块级函数 → `services/project_io` → commit 自动落盘），
  「界面与 AI 改数据不会出现两套逻辑」的既有架构原则不被破坏；
- 内嵌模式下 GUI 与 MCP **共享同一工程会话与锁**（GUI 持锁，MCP 不另抢锁——无锁冲突、
  界面经 EventBus 实时刷新、写确认窗自然弹出），这是内嵌主路线相对独立进程的核心收益；
- 每个工具的返回是**结构化 JSON**（数值、原始算式、表达式、中间步骤齐全）；
- 无 GUI 场景（脚本化、CI、远程）由 `section2-mcp --project` headless 只读模式覆盖
  （section2 数据层全部无 GUI 依赖，headless 可用工具面远大于 Quotor 的 9 个，见 6.4）。

### 1.3 非目标（明确不做）

- **不做** MCP 服务器里的 AI 对话/模型调用：MCP 客户端自带模型（对齐 Quotor：`ai_protocol.md`
  的"客户端直连"原则）；`services/ai/`（ai_provider、ai_keychain）属客户端侧，仅内置面板使用；
- **不做** UI 类功能的 MCP 化：主题切换、窗口装饰、断面示意图实时绘制（PNG 渲染列 v2 可选）；
- **不改** ORM 表结构与 `SCHEMA_VERSION`（MCP 只是新的调用方，不产生 schema 迁移）；
- 一期**不做**导航类工具（改 GUI 当前选中：`navigate_to_*`/`select_*`，Quotor 有、section2
  列 P6 可选——见 11.2）；**不做** LangGraph 重构（列可选研究项，见 8.7）。

---

## 2. 参照系：Quotor 已验证路线（本方案蓝本）

Quotor（`F:\GithubRepos\ArjenCole\Quotor`，只读参照）已把同样的"MCP 化 + Agent 体系"完整落地
（其 `docs/mcp_plan.md` v1.1 标注 M1~M5 全部实施）。**本方案直接继承其架构与踩坑结论**：

| Quotor 已验证结论 | 出处 | section2 采纳方式 |
|---|---|---|
| 主方案 = GUI 进程内嵌 Streamable HTTP MCP server（`127.0.0.1:8765/mcp` + Bearer token + 仅回环绑定）；工具操作运行中的 GUI，stdio 子进程里没有 GUI 工具无法工作 | `mcp_plan.md` §3.1/§4.1 | 内嵌为主（第 5 章）；section2 的工程会话由 GUI 持有，结论同样成立 |
| **mcp SDK 2.x**：`from mcp.server.lowlevel import Server`，`Server(name, version, on_list_tools=…, on_call_tool=…)` + `server.streamable_http_app(streamable_http_path=…, host=…)`；`ClientSession` 必须 `async with` 启动调度器；FastMCP 与 1.x 装饰器风格已移除 | `mcp_server/server.py`、`mcp_plan.md` §15.3 | 第 6 章直接照抄该 API 形态 |
| 适配层：`Tool.parameters`（JSON Schema）原样透传为 MCP `inputSchema`；执行放 `anyio.to_thread.run_sync`，不阻塞 asyncio 事件循环 | `mcp_server/adapter.py` | 6.1 照抄 |
| 结果语义契约：`{"error": …}` → `isError=true`；`{"cancelled": true}` → `isError=false`（用户取消确认不是错误，客户端自然停手）；其余 `json.dumps(ensure_ascii=False, default=str)` 文本回传 | `adapter.py::_result_to_call_result` | 全部工具统一 dict 结果契约（8.2） |
| `READ_ONLY_TOOLS` 白名单（`allow_actions=false` 时只暴露只读）；`HEADLESS_SAFE_TOOLS` + `_gui_available()` 前置守卫（无 GUI 时返回可读错误，防止 QEventLoop 挂死） | `adapter.py` | 6.4/6.5 采纳并按 section2 工具面扩大白名单 |
| 确认双通道：`ContextVar` `_CHANNEL`（builtin/mcp）+ `channel()/override_channel()`；contextvar 不跨 Qt 信号跳转，marshal 时快照、主线程侧恢复；判定点 `confirmation_suppressed()` 分别读 `[ai]/[mcp] require_confirmation` | `agent/confirm_policy.py` | 8.4 采纳（section2 的快照/恢复点在 ConfirmBridge，见 8.4.2） |
| 独立 CLI 四模式：`--transport stdio\|http` 本地、`--connect <url>` stdio→HTTP 转发桥、`--project <path>` headless 强制只读 | `mcp_server/__main__.py` | 6.6 照抄 |
| Agent 体系：`Tool`/`ToolRegistry`（register/get/names/all_tools/execute/to_openai_tools/to_prompt_text）+ `build_default_registry()` 38 工具；上下文三层注入；五类循环治理；紧凑参数格式（token 减半） | `agent/tool_registry.py`、`langgraph_loop.py` | 第 8 章逐项对齐 |
| GUI 集成：AI 菜单「MCP 服务…」设置对话框（开关/端口/token/allow_actions + 复制客户端配置按钮）、状态栏显示运行状态、启动自动拉起、`closeEvent` 停止 | `mcp_plan.md` §8、§15.2 | 5.5 照抄 |
| config 新增 `[mcp]` 段（enabled/host/port/token/allow_actions/require_confirmation） | `mcp_plan.md` §5.4 | 5.4 照抄 |

**与 Quotor 的两点架构差异**（section2 更简单，实施时不得画蛇添足）：

1. **不需要 `AgentActionBridge`**：Quotor 工具执行器直接操作运行中的 ViewModel/Panel/Dialog
   （`panel._vm`），必须 `execute_on_main`（QEventLoop 阻塞 marshal）到 Qt 主线程；
   section2 的工具走 `unit_vm`/`project_vm` **模块级纯函数**（不碰 Qt 控件），但数据层是
   **全局单 SQLAlchemy Session（非线程安全）**，因此工具执行器同样经
   `app.core.main_thread.execute_on_main` 投递回 Qt 主线程，worker 只负责模型请求；
   跨线程触点还包括确认窗（经 `ConfirmPolicy` 队列信号到主线程）。工程生命周期操作
   （新建/打开/另存/关闭）由 `project_io` 的线程守卫强制在主线程执行；
2. **headless 可用面更大**：Quotor headless 只有 9 个纯查询工具（其余依赖主窗口）；
   section2 数据层全部无 GUI 依赖，`--project` 模式下**除写操作外的全部工具**（读树/读构件/
   读原则/计算/图集/迁移 inspect…）都可在无 GUI 进程执行。

---

## 3. 现状盘点：功能 → MCP 映射

### 3.1 代码可复用性结论（已核查源码）

| 层 | Qt 依赖 | 结论 |
|---|---|---|
| `core/models/`、`core/calc/`、`core/evaluator.py`、`core/paths.py`、`core/config.py` | 无 | 直接 import 即可无头运行 |
| `services/project_io.py`、`atlas.py`、`element_library.py`、`stn_migration.py` | 无 | 同上；project_io 模块 docstring 明示"刻意不依赖 Qt" |
| `viewmodels/unit_vm.py`、`project_vm.py` 模块级数据函数 | import PySide6.QtCore（QObject/QTimer/Signal 仅 VM 类与 EventBus 用） | 函数本身纯 SQLAlchemy；无 QApplication 可 import + 调用（Quotor headless 模式已验证同类做法；P0 冒烟复验，失败走 8.9 兜底） |
| `core/event_bus.py` | PySide6.QtCore（QObject/Signal） | `bus()` 单例无 QApplication 可创建；Signal emit 无事件循环时为直调 |
| `views/dialogs/*` 原则编辑器 | Qt | **落库逻辑混在 Qt 槽里，需抽取纯函数**（见 9.2），这是唯一的业务重构 |
| `agent/`（现状） | 仅 element_crud import unit_vm | 4 工具 + `ToolContext(unit_id, unit_name, confirm)` + `ConfirmBridge` + 手写 8 轮循环——第 8 章升级为注册表类 |

### 3.2 功能全景 → MCP 处置总表

| # | 软件功能（用户视角） | 现有实现位置 | 纯逻辑性 | MCP 处置 | 阶段 |
|---|---|---|---|---|---|
| 1 | 新建工程（向导：名称/编号/编制人/标段数/专业勾选） | `project_io.new_project(NewProjectSpec)` | ✅ | T01 `create_project` | P1 |
| 2 | 打开/关闭/保存/另存/自动保存/备份/锁 | `project_io`（open/save/save_as/close/commit、acquire/release_lock、create_backup） | ✅ | T02~T06（内嵌模式共享 GUI 会话，仅独立模式真正用锁） | P1 |
| 3 | 最近工程列表 | `core/config.py` recent_projects | ✅ | T07 | P1 |
| 4 | 项目树（标段/单位工程增删改/移动/重命名） | `project_vm` + `project_io` | ✅（VM 薄壳） | T08~T13 | P1 |
| 5 | 构件条目增删改查（8 类别、埋深/数量可写算式、四类原则引用） | `unit_vm` + `agent/tools/element_crud.py`（4 工具已存在） | ✅ | T14~T18（升级为注册表工具，id 缺省取当前选中） | P1 |
| 6 | 构件明细：管材行（材质/管径/壁厚/含量） | `unit_vm` create/update/delete_pipe | ✅ | T22~T24 | P2 |
| 7 | 构件明细：构件参数行（含图集参数行锁定语义） | `unit_vm` create/update/delete_param | ✅ | T25~T27 | P2 |
| 8 | 构件明细：构筑物工程量行（类别/项目/单位/值） | `unit_vm` create/update/delete_quantity | ✅ | T28~T30 | P2 |
| 9 | 多围护/多地基原则引用（比例加权、主围护原则） | `unit_vm` add/update/remove_principle_ref、set_main_pe | ✅ | T31~T35 | P2 |
| 10 | 构件库模板插入（407 模板、8 类别）+ 复制粘贴 | `element_library()`、`unit_vm` insert_element_template/element_snapshot | ✅ | T20~T21、T60~T61 | P2/P3 |
| 11 | 围护原则编辑（土质/坞塝/覆土/基础/做法表/多级/止水） | 对话框 + `project_io` 原语 | ⚠️ 需抽纯函数 | T37~T46、T52~T53 | P2 |
| 12 | 地基原则编辑（换填层 + 特殊地基构件） | 同上 | ⚠️ 同上 | T37、T39、T42、T47~T48 | P2 |
| 13 | 降水原则编辑（5 井型：启用/标高/井距/侧数） | 同上 | ⚠️ 同上 | T37、T40、T49 | P2 |
| 14 | 面宽原则编辑（取值方式 + 6 类管材×DN 矩阵、恢复图集默认） | 同上 | ⚠️ 同上 | T37、T41、T50~T51 | P2 |
| 15 | 原则重命名/删除（删除并入语义）/ *.spcp 导入导出 | `project_io` rename_/delete_/merge_target_/export_*_spcp/import_spcp | ✅ | T42~T43、T54~T55 | P2 |
| 16 | 构件公式编辑（参数 + F/Z 公式） | 对话框 + ComponentParam | ⚠️ 需抽 | T52~T53 | P2 |
| 17 | 图集查询（10 张表、工作面/沟槽宽度、mm→m） | `services/atlas.py` resolve_atlas 等 | ✅ | T56~T59 | P3 |
| 18 | 构件公式库（Ei/WSi/Fi 模板） | `atlas.component_library()` | ✅ | T62~T63 | P3 |
| 19 | 工程量计算（定额键、表达式、中间步骤、多原则加权合并） | `core/calc/engine.py` + `unit_vm.compute_unit` | ✅ | T64~T65 | P3 |
| 20 | 算式求值器（白名单安全求值） | `core/evaluator.py` | ✅ | T66 | P3 |
| 21 | 旧 .stn 工程迁移（报告/容错/原则补齐） | `services/stn_migration.py` | ✅ | T67~T68 | P4 |
| 22 | 汇总（量×单价=合价、单价编辑、批量载价）+ 定额/清单双表 Excel 导出 | M5 **未完成**（曾实现已移除；Price 表已在 models 中） | — | T69~T72（与 M5 协同，见 7.8） | P5 |
| 23 | 「当前选中」上下文（单位工程/构件） | GUI 选中状态 | — | T74 `get_current_context`（内嵌模式） | P1 |
| 24 | AI 助手面板/设置 | `services/ai/`、`agent/` | — | 第 8 章二期升级 | P1/P6 |
| 25 | 断面示意图绘制 | `views/panels/section_view.py`（Qt 绘制） | ✗ | v2 可选（渲染 PNG） | — |
| 26 | 主题/窗口装饰 | `views/widgets/` | ✗ | 非目标 | — |

---

## 4. 总体架构（v1.1：内嵌为主，对齐 Quotor）

### 4.1 主方案：GUI 进程内嵌 Streamable HTTP MCP server

```
┌─ Section2 桌面应用进程 (PySide6) ──────────────────────────────────────┐
│  Qt 主线程                                                              │
│    MainWindow ── closeEvent 停止 MCP ── 状态栏「MCP: 运行中 · 127.0.0.1:8765」│
│    EventBus（unit_changed / principle_changed … 界面实时刷新，现成机制）  │
│         ▲                                                               │
│         │ emit（worker 线程 → 主线程队列投递，现成机制）                    │
│  worker 线程（anyio.to_thread）                                          │
│    ┌────────────────────┐    ┌──────────────────────────┐             │
│    │ 统一工具注册表        │◄───│ 写工具 → ConfirmBridge 弹确认卡 │            │
│    │ build_default_      │    │  （channel: builtin / mcp 双通道）        │
│    │ registry() 74 工具   │    └──────────────────────────┘             │
│    │  ├─ 内置 AI 面板出口：to_openai_tools() → agent_loop（现有）          │
│    │  └─ MCP 出口：McpToolAdapter                                        │
│    └────────┬───────────┘                                               │
│             │ list_tools / call_tool                                    │
│    ┌────────▼─────────────┐   uvicorn/asyncio 后台线程                   │
│    │ MCP Server (mcp 2.x)  │   仅绑定 127.0.0.1:8765/mcp                  │
│    │ + Bearer 鉴权中间件    │                                              │
│    └────────▲─────────────┘                                              │
└─────────────┼───────────────────────────────────────────────────────────┘
              │ HTTP + Authorization: Bearer <token>
   ┌──────────┼───────────┬──────────────┐
   ▼          ▼           ▼              ▼
 Codex     Claude Desktop  Cursor/Cline   WorkBuddy …（外部 MCP 客户端）
```

- **数据流**：外部客户端 `call_tool(name, args)` → HTTP → Bearer 中间件 → mcp Server →
  `McpToolAdapter.call_tool`（`anyio.to_thread.run_sync`）→ `ToolRegistry.execute`
  （内部经 `execute_on_main` 投递回 Qt 主线程，ContextVar 随上下文复制）→
  工具执行器调 `unit_vm`/`project_io` 纯函数（commit 落盘、EventBus 广播界面刷新）→
  写操作经 `ConfirmPolicy` 在主线程弹结构化确认卡 → 用户批准/拒绝 → 结果 dict →
  `isError` 分类 → JSON 文本回传客户端；
- **会话/锁**：内嵌模式下**GUI 是唯一持锁者**，MCP 调用直接复用 GUI 进程内的全局 SQLAlchemy
  会话；**所有工具执行器与工程生命周期操作都在 Qt 主线程串行执行**（全局单 Session
  非线程安全），界面经 EventBus 实时刷新（这是内嵌路线的核心收益）；
- **鉴权**：启用时生成 `secrets.token_urlsafe(32)` 存 config；仅回环绑定，禁止 `0.0.0.0`。

### 4.2 辅助入口：独立 CLI `section2-mcp`（四模式，对齐 Quotor）

```
① 本地 stdio：  section2-mcp [--read-only]            # 进程内执行工具（无 GUI 时写工具被守卫拦截）
② 本地 HTTP：   section2-mcp --transport http [--port 8765 --token <t>]
③ stdio 桥：    section2-mcp --connect http://127.0.0.1:8765/mcp [--token <t>]
                # stdio MCP ↔ 运行中桌面应用的 HTTP 端点转发（照顾只支持 stdio 的客户端）
④ headless：    section2-mcp --project <path.stn2>    # 无 GUI 打开工程，强制只读
```

- ①②供测试与特殊部署；③是外部 stdio-only 客户端操作**运行中桌面应用**的通道；
  ④供脚本化/CI/无人值守查询计算——section2 数据层全部无 GUI 依赖，④的可用工具面
  = 全部读工具（见 6.4 白名单），远大于 Quotor 同模式的 9 个；
- ④的锁语义：headless 进程自行 `open_project`（抢 `.lock`；与桌面版互斥、先后接管——
  现成机制），退出即释放。

### 4.3 会话与工具上下文

- 工具参数中的 id（`unit_id`/`element_id`/`pipe_id`…）**保留且全部可显式给出**（MCP 客户端
  没有界面选中概念，显式 id 可复查、可跨对话引用——v1.0 的原则不变）；
- **内嵌模式新增缺省解析**：省略 id 时从 GUI 当前选中解析（单位工程 = 项目树选中；
  构件 = 主表格当前行）。解析不到 → 返回 `{"error": "当前未选中单位工程，请显式传 unit_id
  （get_project_tree 可查）"}`。内置 AI 面板同样受益（"把这条管的埋深改成 3 米"）；
- 未打开工程时（内嵌模式不可能发生；独立模式可能）：除 E 组图集/构件库查询与 T66/T73 外，
  其余工具返回 `{"error": "当前没有打开的工程，请先 open_project。"}`。

### 4.4 写操作确认（双通道，对齐 Quotor `confirm_policy`）

| 通道 | 调用方 | 配置开关 | 行为 |
|---|---|---|---|
| `builtin` | 内置 AI 面板 | `[ai] require_confirmation`（现有） | 默认 true：写工具弹结构化确认卡 |
| `mcp` | 外部 MCP 客户端 | `[mcp] require_confirmation`（新增） | 默认 true：同一确认卡在 GUI 弹出（用户就在机器旁）；false = 跳过弹窗直接执行（信任客户端自身的批准 UI） |

- 确认卡（对齐 Quotor `AiConfirmDialog` 的 `preview` 结构）：`{action, target, summary, details[]}`
  ——现有 `ConfirmBridge` 的纯文本 `ask(description)` 升级为结构化卡片；
- 拒绝返回 `{"cancelled": true, "message": "用户取消了操作"}`（不再是 v1.0 的纯文本
  "用户拒绝执行该操作。"），且 **agent_loop 收到 cancelled 立即终止本轮循环**（防止模型
  反复重调同一工具反复弹窗——Quotor 已验证的治理点）；
- channel 经 `ContextVar` 传播：工具在 worker 线程执行、确认卡经 Qt 信号投递主线程，
  contextvar 不跨信号跳转 → `ConfirmBridge` 发射前快照 `current_channel()`、主线程侧
  `override_channel()` 恢复（对齐 Quotor 在 ActionBridge 上的做法，作用点移到 ConfirmBridge）；
- 独立 stdio/HTTP/headless 模式下写工具：`--read-only` 与 `[mcp] allow_actions=false`
  走 `READ_ONLY_TOOLS` 白名单直接过滤；未过滤的写工具在无 GUI 时被 `HEADLESS_SAFE_TOOLS`
  守卫拦截（返回可读错误而非挂死，对齐 Quotor）。

### 4.5 安全边界

| 机制 | 说明 |
|---|---|
| 仅回环绑定 | host 固定 `127.0.0.1`，不可配 `0.0.0.0` |
| Bearer token | 防本机其他进程/网页（DNS rebinding）驱动 Section2 改数据 |
| `allow_actions` 开关 | `[mcp] allow_actions=false` → 只暴露 `READ_ONLY_TOOLS` 白名单 |
| 路径白名单（P6 加固） | config `[mcp] allowed_dirs = []`（空=不限制）：save_as / export_principle / migrate_legacy_project / batch_import_prices / export_excel 的目标路径必须落在允许目录内 |
| 求值安全 | `evaluate_expression` 只暴露 simpleeval 白名单（已禁任意函数调用/属性访问，无注入面） |
| 数据兜底 | 每次写 commit 落盘 + 首次修改自动备份 `Backup\`（保留 20 份，现成机制）——AI 误操作可人工恢复 |

### 4.6 返回值与错误约定（所有工具统一，对齐 Quotor 契约）

```jsonc
// 工具执行器一律返回 dict（注册表级异常包装：未捕获异常 → {"error": "工具执行失败: …"}）
// 成功
{ "ok": true, "data": { /* 结构化载荷 */ }, "summary": "一行中文摘要（可选）" }
// 业务失败（AI 可自纠：找不到 id、原则名不存在、参数非法…）  → MCP isError=true
{ "ok": false, "error": "围护原则“X”不存在。可用：A、B、C" }   // 错误文案必须带"下一步指引"
// 用户取消确认（不是错误）                                     → MCP isError=false
{ "cancelled": true, "message": "用户取消了操作" }
```

- 适配层映射（照抄 Quotor `adapter.py`）：`error` 非空 → `isError=true`；`cancelled` →
  `isError=false`；其余正常 JSON 文本回传；
- 错误文案沿用 `element_crud.py` 风格：中文 + 可用值清单 + 建议的下一步工具；
- 数值一律 `format_number`（4 位小数，与界面一致）；**算式字段保留用户原文**（埋深/数量/
  参数值/含量列可写算式，AI 读写均以字符串原文为准，另给 `*_value` 数值字段）。

---

## 5. 内嵌集成与配置（对齐 Quotor GUI 集成）

### 5.1 `[mcp]` 配置段（`core/config.py` 的 `DEFAULT_CONFIG` 新增）

```toml
[mcp]
enabled = false             # 应用启动时是否自动启动 MCP server
host = "127.0.0.1"          # 固定回环地址
port = 8765                 # 监听端口
token = ""                  # 空 = 首次启用时自动生成；用户可改写
allow_actions = true        # false = 仅暴露 READ_ONLY_TOOLS 白名单
require_confirmation = true   # MCP 通道写操作是否弹确认卡（false = 直接执行）
```

配套 `_ConfigProxy` 属性：`mcp_enabled / mcp_host / mcp_port / mcp_token / mcp_allow_actions /
mcp_require_confirmation`（照现有 `ai_*` 属性写法）。

### 5.2 菜单与状态（`views/main_window.py`）

| 项 | 行为 |
|---|---|
| `AI → MCP 服务…` | 打开 `views/dialogs/mcp_settings_dialog.py`：开关、端口、token（可复制/重置）、`allow_actions`、连接状态、「复制 Codex / Claude Desktop / WorkBuddy 配置」按钮（生成可直接粘贴的片段） |
| 启动自动拉起 | `[mcp] enabled=true` 时 `main()` 启动后调 `McpServerController.start()` |
| 状态提示 | 主窗体不放状态栏（三栏顶到窗体底部），MCP 启动结果走底部浮层一次性提示；运行状态在 `AI → MCP 服务…` 对话框里查看 |
| `closeEvent` | `McpServerController.stop()` 释放端口 |

### 5.3 生命周期（`mcp_server/controller.py`）

`McpServerController`（单例）：`start() -> (ok, message)`（校验端口/token，后台线程起
uvicorn）、`stop()`、`status() -> {running, url, token, port}`；启动失败（端口被占）给出
可读错误。工程打开/关闭不影响 server 生命周期（工具运行时自报"未打开工程"）。

---

## 6. MCP 服务器模块设计（mcp SDK 2.x，对齐 Quotor `mcp_server/`）

### 6.1 新增模块结构

```
src/app/mcp_server/
├── __init__.py        # 导出 McpToolAdapter / McpServerController / build_mcp_server
├── adapter.py         # ToolRegistry → MCP：list_tools 转换 + call_tool 执行
│                      #   （READ_ONLY_TOOLS / HEADLESS_SAFE_TOOLS 白名单 + channel(CHANNEL_MCP)）
├── server.py          # mcp 2.x lowlevel Server(on_list_tools/on_call_tool)
│                      #   + streamable_http_app() + build_http_app + run_stdio/run_http_async
├── auth.py            # Bearer token 生成（secrets.token_urlsafe(32)）+ ASGI 鉴权中间件
├── controller.py      # GUI 内嵌生命周期 start/stop/status
└── __main__.py        # CLI 四模式：--transport stdio|http / --connect 桥 / --project headless
```

`src/app/agent/`（现有，类化改造，见第 8 章）：

```
src/app/agent/
├── tool_registry.py    # Tool dataclass + ToolRegistry 类 + all_tools()（类化重写）
├── tools/              # build_default_registry() 全量 74 工具（element_crud 迁入并扩容）
│   ├── project.py / tree.py / element.py / principle.py / reference.py /
│   ├── compute.py / migrate.py / summary.py
├── confirm_policy.py   # 双通道 CHANNEL_BUILTIN/CHANNEL_MCP + ContextVar + override（升级重写）
├── confirm_policy_bridge = 现有 ConfirmBridge 升级（结构化确认卡 + cancelled + channel 快照）
└── agent_loop.py       # 现有循环保留主线 + 治理升级（第 8 章）
```

**pyproject.toml 变更**：

```toml
[project.optional-dependencies]
mcp = ["mcp>=2.0,<3", "uvicorn>=0.30", "anyio>=4"]
[project.scripts]
section2 = "app.main:main"
section2-mcp = "app.mcp_server.__main__:main"
```

### 6.2 适配层核心（照抄 Quotor `adapter.py` 形态，适配 section2 差异）

```python
# adapter.py 关键骨架（完整语义见 Quotor 同名文件）
class McpToolAdapter:
    def __init__(self, registry: ToolRegistry, *, allow_actions: bool = True): ...

    def list_tools(self) -> list[McpTool]:
        # Tool(name/description/parameters) → McpTool(inputSchema=t.parameters) 原样透传

    def execute_sync(self, name: str, arguments: dict) -> CallToolResult:
        # 1) 未注册工具 / allow_actions=false 拒写 → isError=true
        # 2) name not in HEADLESS_SAFE_TOOLS and not _gui_available() → 可读错误
        #    （section2 的 _gui_available = QCoreApplication 存在（判定确认卡可弹）；
        #     工具本身不碰 Qt，无需 Quotor 的 main_window 注册判定）
        # 3) with channel(CHANNEL_MCP): registry.execute(name, arguments)
        # 4) 结果 dict → isError 分类（error=true / cancelled=false / 其余正常）

    async def call_tool(self, name, arguments) -> CallToolResult:
        return await anyio.to_thread.run_sync(self.execute_sync, name, arguments)
```

### 6.3 server 组装（照抄 Quotor `server.py`）

```python
def build_mcp_server(adapter) -> Server:
    async def on_list_tools(ctx, params): return ListToolsResult(tools=adapter.list_tools())
    async def on_call_tool(ctx, params): return await adapter.call_tool(params.name, params.arguments or {})
    return Server("section2-mcp", version=APP_VERSION,
                  on_list_tools=on_list_tools, on_call_tool=on_call_tool)

def build_http_app(adapter, token=None, path="/mcp"):
    app = build_mcp_server(adapter).streamable_http_app(streamable_http_path=path, host="127.0.0.1")
    return BearerAuthMiddleware(app, token) if token else app
```

> SDK 踩坑备忘（Quotor 实施记录 §15.3，直接适用）：mcp 2.0 移除 FastMCP 与 1.x 装饰器；
> `ClientSession` 必须 `async with` 启动消息调度器；HTTP transport API 跨版本变动大，
> **锁定 `mcp>=2.0,<3` 并 pin 精确版本**。

### 6.4 只读白名单与 headless 守卫

```python
READ_ONLY_TOOLS = {  # [mcp] allow_actions=false 时仅暴露这些
    # A 组读：get_project_info, list_recent_projects
    # B 组读：get_project_tree
    # C 组读：list_elements, get_element_detail, list_principle_refs
    # D 组读：list_principles, get_principle_detail, get_component_detail
    # E 组全：resolve_atlas, list_atlas_tables, query_atlas_table,
    #         get_default_width_tables, list_library_templates,
    #         get_library_template, list_component_templates, get_component_template
    # F 组全：compute_unit, compute_element, evaluate_expression
    # G 组读：inspect_legacy_project
    # I 组：get_conventions, get_current_context
}
HEADLESS_SAFE_TOOLS = READ_ONLY_TOOLS  # section2 全部读工具无 GUI 可用（与 Quotor 的差异点）
```

- `--project` headless 模式强制 `allow_actions=false`（无确认面，对齐 Quotor「headless 强制只读」）；
- 本地 stdio/http 模式（①②）默认 `--read-only` 关闭时：写工具依赖确认卡，无 GUI 进程时被
  `_gui_available()` 守卫拦截并提示「请在运行中的 Section2 应用里启用 MCP 服务，或用
  `--connect` 桥接入」。

### 6.5 stdio 桥（`--connect`，照抄 Quotor `__main__.py::_run_bridge`）

stdio 端 `Server(on_list_tools/on_call_tool)` → 内部用 `mcp.client.streamable_http.
streamable_http_client` + `ClientSession`（`async with`）连接运行中桌面应用的 HTTP 端点，
透传 `list_tools/call_tool`。

### 6.6 CLI（`section2-mcp`，参数对齐 Quotor）

`--transport {stdio,http}`、`--host`（仅回环）、`--port`、`--token`、`--read-only`、
`--connect <url>`、`--project <path.stn2>`；`--project` 成功打开后强制只读。

---

## 7. MCP 能力清单（74 工具全量规格 = 统一注册表内容）

> 通用约定：
> - "写操作" = 修改 `.stn2` 或文件系统，均即时 commit 落盘（自动保存语义）；
> - **id 参数全部可省略**：内嵌模式缺省取 GUI 当前选中（4.3）；独立模式必须显式；
> - 埋深/数量/参数值/含量等"算式列"参数为 **string 原文**（如 `"2.5+0.3"`），允许纯数字；
> - 构件类别枚举：`"直埋管道" "包封" "箱涵" "顶管" "牵引管" "管廊" "构筑物"`
>   （`CATEGORY_NAMES`；接受中文名，内部 `category_from_name` 转换）；
> - 原则四类 kind 枚举：`"enclosure" 围护 / "foundation" 地基 / "precipitation" 降水 / "width" 面宽`；
> - 工具即 `agent/tools/` 注册表工具：**内置 AI 面板（to_openai_tools）与 MCP（适配层）
>   消费同一份定义**——下表既是 MCP 工具清单，也是 AI 助手二期工具清单。

### 7.1 A 组：工程与会话（T01~T07，P1）

| ID | 工具 | 读写 | 关键参数 | 返回 data | 复用 |
|---|---|---|---|---|---|
| T01 | `create_project` | 写 | `project_name*`、`project_index`、`author`（默认当前用户）、`path`（空=临时工程）、`segment_names[]`（默认 1 个）、`unit_names[]`（每个标段建这些单位工程，默认雨水/污水/给水/中水各一）、`excvt`（默认"Ⅲ类土"，7 种土质枚举）、`found_angle`（90/120/150/180，默认 120）、`con_found`（默认 true）、`enclosure_name/foundation_name/precipitation_name/width_name`（默认原则名） | `{path, project_name, schema_version, segments:[{id,name,units:[…]}]}` | `project_io.new_project(NewProjectSpec)`；默认值语义照抄 `new_project_wizard.values()` |
| T02 | `open_project` | 写(会话) | `path*` | `{path, project_name, schema_version, migrated:[…]}` | 内嵌模式=GUI 会话已在（直接报"工程已由界面打开"）；独立模式 `project_io.open_project`（抢锁/版本迁移） |
| T03 | `close_project` | 写(会话) | — | `{path}`（先 commit） | 内嵌模式返回引导（请在界面关闭）；独立模式 `project_io.close_project` |
| T04 | `save_project` | 写 | — | `{path}`；临时工程 → 提示需 save_as | `project_io.save` |
| T05 | `save_project_as` | 写 | `path*` | `{path}`（整库复制） | `project_io.save_as` |
| T06 | `get_project_info` | 读 | — | basic_info 全字段 + schema_version + 路径 + 备份数 | `orm` 查询 |
| T07 | `list_recent_projects` | 读 | — | `[{path, name}]`（剔除已不存在） | `get_config().recent_projects` |

### 7.2 B 组：项目树（T08~T13，P1）

| ID | 工具 | 读写 | 关键参数 | 返回 data | 复用 |
|---|---|---|---|---|---|
| T08 | `get_project_tree` | 读 | — | `{segments:[{id,name,order_no,units:[{id,name,order_no,element_count}]}]}` | `project_vm.build_tree` + `element_rows` 计数 |
| T09 | `add_segment` | 写 | `name` | `{segment_id}` | `project_vm.add_segment` |
| T10 | `add_unit` | 写 | `segment_id*`、`name` | `{unit_id}` | `project_vm.add_unit` |
| T11 | `rename_node` | 写 | `kind*`(`"segment"/"unit"`)、`id*`、`name*` | `{}` | `project_vm.rename` 分派 |
| T12 | `delete_node` | 写 | `kind*`、`id*` | `{}`；返回级联删除数量（**必须提示**） | `project_vm.delete`（CASCADE） |
| T13 | `move_node` | 写 | `kind*`、`id*`、`target_segment_id`（unit 用）、`index` | `{}` | `project_io.move_segment/move_unit` |

### 7.3 C 组：构件条目与子行（T14~T35）

**P1 核心（T14~T18 + T74）**——现有 `element_crud.py` 四工具迁入注册表并升级：

| ID | 工具 | 读写 | 关键参数 | 返回 data | 复用 |
|---|---|---|---|---|---|
| T14 | `list_elements` | 读 | `unit_id`（缺省取选中）、`verbose`(默认 false) | `[{id,name,category,spec,depth,depth_value,amount,amount_value,pe_name,pf_name,pp_name,pw_name,source}]` | `unit_vm.element_rows` |
| T15 | `get_element_detail` | 读 | `element_id`（缺省取选中行） | element 全字段 + `pipes[]` + `params[]`（含锁定标记）+ `quantities[]` + `principle_refs{pe[],pf[]}`（含 ratio/is_main）+ `auto:{atlas_params,pipe_thicknesses}`（自动值预览） | `element_snapshot`/`pipe_rows`/`param_rows`/`quantity_rows`/`principle_ref_rows`/`auto_atlas_params`/`auto_pipe_thicknesses` |
| T16 | `add_element` | 写 | `unit_id`（缺省）、`name*`、`category`、`depth`、`amount`、`pe_name/pf_name/pp_name/pw_name`、`pipe{mat,dn,t?,content}`、`pipes[]`、`params[{key,unit,value}]`、`quantities[]`、`pe_refs[{name,ratio}]`、`pf_refs[]`、`main_pe_name`、`seed_atlas_defaults`(默认 true) | `{element_id}` + 摘要 | `unit_vm.create_element`（全参数版）；原则名校验照抄 element_crud |
| T17 | `update_element` | 写 | `element_id`（缺省取选中行，或 `unit_id`+`name` 定位）、可改字段 = T16 除 unit 外全部 | `{}` + 变更摘要 | `unit_vm.update_element` + 引用重置语义 |
| T18 | `delete_element` | 写 | `element_id`（缺省取选中行，或定位参数） | `{}`（级联删子行） | `unit_vm.delete_element` |
| T74 | `get_current_context` | 读 | — | `{unit:{id,name}, element:{id,name,category}?, source:"gui"}`；独立模式 `source:"headless"` 并提示需显式 id | 读取 GUI 选中（EventBus/VM 现状）；对齐 Quotor `get_current_workbench` |

**P2 扩展（T19~T35）**：

| ID | 工具 | 读写 | 关键参数 | 说明 |
|---|---|---|---|---|
| T19 | `move_element` | 写 | `element_id*`、`delta`(±1) | `unit_vm.move_element` |
| T20 | `duplicate_element` | 写 | `element_id*`、`target_unit_id?` | `element_snapshot` + `insert_element_data`（复制粘贴路径） |
| T21 | `insert_element_from_template` | 写 | `unit_id`（缺省）、`category*`、`unit*`、`index*`、`before_element_id?` | `unit_vm.insert_element_template`；AI 先用 T60/T61 查三要素 |
| T22~T24 | `add_pipe` / `update_pipe` / `delete_pipe` | 写 | `element_id`（add，缺省）/`pipe_id*`；`mat`、`dn`(mm)、`content`(算式原文)、`t`(mm，**null=自动按图集**) | `unit_vm.create/update/delete_pipe` |
| T25~T27 | `add_param` / `update_param` / `delete_param` | 写 | `element_id`（add，缺省）；`param_id*` 或 `element_id+key`；`key`、`unit`、`value` | 图集参数行（工作面加宽/垫层厚/基础厚，按类别 3/2/0 行）与构筑物名称行**锁定不可删**（现成语义） |
| T28~T30 | `add_quantity` / `update_quantity` / `delete_quantity` | 写 | `element_id`（add，缺省）；`quantity_id*`；`category`、`item`、`unit`、`value` | 构筑物（cat7）工程量行 |
| T31 | `list_principle_refs` | 读 | `element_id`（缺省） | `{pe:[{ref_id,name,ratio,order_no,is_main}],pf:[…]}` |
| T32 | `add_principle_ref` | 写 | `element_id`（缺省）、`kind*`("pe"/"pf")、`name*`、`ratio`(默认 1.0) | 比例无归一化约束（引擎按比例加权） |
| T33 | `update_principle_ref` | 写 | `ref_id*`、`name?`、`ratio?` | |
| T34 | `remove_principle_ref` | 写 | `ref_id*` | **至少保留 1 条**（现成语义） |
| T35 | `set_main_pe` | 写 | `element_id`（缺省）、`name*` | 主围护原则（支撑 Z 量按主原则算） |

### 7.4 D 组：六类原则（T36~T55，P2）

先读后写：写工具前 AI 用 `get_principle_detail` 看当前完整内容。

| ID | 工具 | 读写 | 关键参数 | 说明 |
|---|---|---|---|---|
| T36 | `list_principles` | 读 | `kind*` | `[{name, 引用计数}]`（引用计数帮助删除决策） |
| T37 | `get_principle_detail` | 读 | `kind*`、`name*` | 按 kind 返回完整结构（见下） |
| T38 | `create_enclosure` | 写 | `name*`、`excvt`（7 土质枚举）、`found_angle`、`con_found`、`dock_l`、`dock_h`（4 种坞塝回填枚举）、`cover50`、`cover`、`cushions[{name,h_mm}]`（垫层，材质来自 Ei 库）、`works[{min_depth, cpnt_cat(Ei), stop_type(WSi), levels[{h 或 -1 均分, step_width, level_type(Ei)}]}]`（**整表提交**） | 全量创建（一次做完对话框所有步骤）；重名自动加后缀 |
| T39 | `create_foundation` | 写 | `name*`、`replacements[{name,h_mm}]`、`component{group:"Fi", template_name, params{…}}`（可省略=不挂特殊地基） | |
| T40 | `create_precipitation` | 写 | `name*`、`wells{湿土排水/轻型井点/喷射井点/大口井/深井:{enabled, elevation, gap, sides}}` | 存储格式 `elevation\|gap\|sides`（`format_precipitation` 现成语义） |
| T41 | `create_width_principle` | 写 | `name*`、`mode*`(`"WorkWidth"`/`"B"`)、`items[]`（缺省=播种图集默认表） | `project_io.seed_width_tables` |
| T42 | `rename_principle` | 写 | `kind*`、`name*`、`new_name*` | `project_io.rename_*` |
| T43 | `delete_principle` | 写 | `kind*`、`name*`、`merge_target_name?` | 删除时引用并入目标；**最后一条拒绝删**；缺 merge_target 时返回可用原则清单（现成语义） |
| T44 | `set_enclosure_fields` | 写 | `name*` + 顶栏字段（excvt/found_angle/con_found/dock_l/dock_h/cover50/cover/cushions 整表） | 增量修改 |
| T45 | `set_enclosure_works` | 写 | `enclosure_name*`、`works[]` 整表替换（同 T38 的 works） | 做法表（min_depth 首行恒 0 校验） |
| T46 | `set_work_levels` | 写 | `work_id*`、`levels[]` 整表替换 | 多级围护（h=-1 = 均分剩余高度，description 写清语义） |
| T47 | `set_replacement_layers` | 写 | `foundation_name*`、`layers[]` 整表替换 | 换填层 |
| T48 | `set_foundation_component` | 写 | `foundation_name*`、`group:"Fi"`、`template_name*`、`params{…}` | `attach_foundation_component` + `component_from_template` |
| T49 | `set_precipitation_wells` | 写 | `precipitation_name*`、`wells{…}` 整体替换 | |
| T50 | `set_width_items` | 写 | `width_name*`、`mode?`、`items[{pipe_type, dn(0~3000 步长100), width_mm}]` 增量替换 | pipe_type 6 枚举：混凝土管-刚性接口/混凝土管-柔性接口/金属类管道/化学建材管道/包封埋管/箱涵-管廊 |
| T51 | `reset_width_to_atlas` | 写 | `width_name*` | 恢复图集默认（界面按钮等价物） |
| T52 | `get_component_detail` | 读 | `component_id*` | `{name, params:[{key,display,expression}], f_formulas, z_formulas}`；值格式 `显示名\|表达式` 拆开返回 |
| T53 | `update_component_params` | 写 | `component_id*`、`params{key:{display,expression}}` | 只允许改模板键集内的键（A~Z/FA~FZ/ZA~ZZ；不增删行，现成语义） |
| T54 | `export_principle` | 写(文件) | `kind*`、`name*`、`path*`（*.spcp） | `project_io.export_*_spcp` |
| T55 | `import_principle` | 写 | `path*` | `{kind, name}`；重名加后缀 |

**原则数据结构**（`get_principle_detail` 各 kind 的 data 形状；序列化放 `agent/tools/principle.py`）：

```jsonc
// kind="enclosure"
{ "name": "…", "excvt": "Ⅲ类土", "found_angle": 120, "con_found": true,
  "dock_l": "…", "dock_h": "至管顶50cm", "cover50": …, "cover": …,
  "cushions": [{"name": "碎石垫层", "h": 100}],
  "works": [ { "work_id": 1, "min_depth": 0, "cpnt_cat": "钢板桩",
      "stop_type": "…", "levels": [ {"h": 3, "step_width": 0.8,
        "level_type": "钢板桩", "component_id": 11} ] } ] }
// kind="foundation"
{ "name": "…", "replacements": [{"name": "碎石", "h": 200}],
  "component": { "component_id": 7, "name": "高压旋喷桩", "params": […], "formulas": […] } }
// kind="precipitation"
{ "name": "…", "wells": { "轻型井点": {"enabled": true, "elevation": 6, "gap": 1.2, "sides": 2}, … } }
// kind="width"
{ "name": "…", "mode": "WorkWidth",
  "items": [ {"pipe_type": "混凝土管-刚性接口", "entries": {"600": 500, "800": 800}} ] }
```

### 7.5 E 组：图集与构件库查询（T56~T63，P3，全只读）

| ID | 工具 | 关键参数 | 返回 data | 复用 |
|---|---|---|---|---|
| T56 | `resolve_atlas` | `category*`、`pipes[{mat,dn,t?}]`、`con_found?`、`found_angle?`、`width_mode?`、`size_b?`、`overrides{a?,c1?,c2?}` | `{od,t,a,c1,c2,workwidth,groove_b,q}`（**全部 mm**，description 写明） | `atlas.resolve_atlas(AtlasQuery)`；语义照抄 `build_atlas_query` |
| T57 | `list_atlas_tables` | — | 10 张表清单（表号/名称/来源 xlsx） | `atlas.ATLAS_TABLES` + `catalog()` |
| T58 | `query_atlas_table` | `table_index*`、`dn*`、`angle?`、`level?` | 行数据 | `AtlasCatalog.find` |
| T59 | `get_default_width_tables` | — | 工作面/沟槽宽度默认矩阵 | `atlas.default_width_tables()` |
| T60 | `list_library_templates` | `category?`（空=全部）、`keyword?` | `[{category, units:[{name,count}], templates:[{name,label,spec}]}]`；keyword 过滤名称/规格 | `element_library().units_of` + **新增 `search_library` 薄封装**（index 寻址对 AI 不友好，必须提供关键词检索） |
| T61 | `get_library_template` | `category*`、`unit*`、`index*` | 模板全字段（可直接喂 T16/T21） | `element_library().find` |
| T62 | `list_component_templates` | `group*`("Ei"/"WSi"/"Fi") | `[{name, describe, params:[…]}]` | `atlas.component_library()` |
| T63 | `get_component_template` | `group*`、`name*` | 参数 + 公式全量（喂给 T38/T48） | 同上 |

### 7.6 F 组：计算与表达式（T64~T66，P3）

**对外最有价值的工具组，返回结构是重点。**

| ID | 工具 | 关键参数 | 返回 | 复用 |
|---|---|---|---|---|
| T64 | `compute_unit` | `unit_id`（缺省取选中）、`include_expressions`(默认 true)、`include_steps`(默认 false) | 见下方 JSON | `unit_vm.compute_unit` |
| T65 | `compute_element` | `element_id`（缺省取选中行）、`include_steps`(默认 true) | 单构件 QDict（含每步 note+expr） | `unit_vm.compute_unit` 过滤 / `engine.compute_element` |
| T66 | `evaluate_expression` | `expression*` | `{value}` 或 `{"error": …EvalError 中文说明}` | `core.evaluator.evaluate` |

`compute_unit` 返回 data（**steps 拼接不变式：各步 expr 顺序拼接 == 完整 expression，
`Quantity.steps()` 现成保证，序列化不得破坏——测试断言**）：

```jsonc
{
  "unit_id": 3, "unit_name": "雨水工程",
  "totals": [                                  // 合并后全量（多原则加权、多构件合并）
    { "key": "开挖|Ⅲ类土|m3", "category": "开挖", "item": "Ⅲ类土",
      "unit": "m3", "value": 1799.074,
      "expression": "(2×(600/1000+(65×2+130×2+500×2)/1000)+2×(2.5+0.3+(65+130)/1000)×1)×…",
      "steps": [ {"note": "槽底宽=管径+2×(壁厚+工作面+做法厚)", "expr": "600/1000+(65×2+130×2+500×2)/1000", "value": 1.86} ] } ],
  "per_element": [
    { "element_id": 12, "name": "雨水管 D600", "quantities": [ /* 同 totals 结构 */ ] } ]
}
```

- 计算**约束**：`compute_element` 要求降水 `pp` 与面宽 `pw` 原则非空——工具层缺失时返回
  `{"error": …}` 并列出可用原则（引导 AI 先 `update_element` 补齐）；
- 数值与表达式同源（`Dim.v`/`Dim.e`），序列化两者都给，**绝不另行拼字符串**。

### 7.7 G 组：旧工程迁移（T67~T68，P4）

| ID | 工具 | 读写 | 关键参数 | 返回 | 复用 |
|---|---|---|---|---|---|
| T67 | `inspect_legacy_project` | 读 | `path*`(.stn) | 预览报告：版本/各对象计数/警告列表（**不写任何文件**；headless 可用） | `stn_migration.parse_legacy` |
| T68 | `migrate_legacy_project` | 写 | `source_path*`、`target_path*`(.stn2) | 迁移报告全文（计数/warnings/skipped/原则补齐） | `stn_migration.migrate(source, target)` |

### 7.8 H 组：汇总与导出（T69~T72，P5，**与 M5 协同**）

> 现状：M5（汇总面板 + 定额/清单双表 Excel 导出）曾实现后移除待重做；`Price` 表已在
> `core/models/models.py` 保留。**开发顺序约定**：P5 先落地无头 `services/summary.py`
> （汇总计算 + Excel 导出纯函数），桌面 M5 重做与工具**共用**该 service——避免两套逻辑。

| ID | 工具 | 读写 | 关键参数 | 返回 | 依赖 |
|---|---|---|---|---|---|
| T69 | `get_unit_summary` | 读 | `unit_id`（缺省） | `[{key, 项目, 单位, 工程量, 单价, 合价}]` | 新 `services/summary.py` |
| T70 | `set_price` | 写 | `key*`、`value*` | `{}` | Price 表 |
| T71 | `batch_import_prices` | 写 | `path*`（xlsx/CSV 两列） | `{imported, skipped}` | 新 service |
| T72 | `export_excel` | 写(文件) | `unit_id?`（空=全工程）、`kind*`("定额"/"清单")、`path*` | `{path, rows}`；**含表达式列** | 新 service（openpyxl 已是依赖） |

### 7.9 I 组：约定与上下文（T73~T74，P1）

| ID | 工具 | 内容 |
|---|---|---|
| T73 `get_conventions` | 领域约定全文（类别枚举/参数键/值格式/表达式"不做预运算"规则/井型字段）——AI 冷启动自取；description 单一事实来源放 `agent/conventions.py` |
| T74 `get_current_context` | 见 7.3 |

### 7.10 资源与提示（可选，P6，低优先级）

| 类型 | 名称 | 内容 |
|---|---|---|
| resource | `section2://project/current` | 当前工程 info（等价 T06） |
| resource | `section2://conventions` | 领域约定（与 T73 同源） |
| prompt | `复核工程量` | 模板：取 compute_unit 结果逐项复核表达式与中间步骤（v2 视客户端支持度） |

---

## 8. AI 助手二期开发方案（对齐 Quotor `agent/`）

> 原则：**同一套工具注册表、同一个执行器、同一个确认策略，两个出口**（内置面板
> `to_openai_tools()` / MCP 适配层）。本章是把现有 M7/M8 的演示级实现升级为 Quotor
> 生产级体系的任务书。Quotor 现状参照：38 工具注册表、三层上下文注入、五类循环治理、
> 双通道确认、紧凑 prompt 格式（token 减半以上）。

### 8.1 工具注册表类化（P0~P1，一切的地基）

现状：`tool_registry.py` 是 30 行薄壳（`openai_tools()/is_write()/execute()` 全部转发
`element_crud.TOOL_SPECS`），无类、无统一结果契约、无遍历接口。

改造（照抄 Quotor `tool_registry.py`）：

```python
@dataclass
class Tool:
    name: str                # 唯一工具名（如 "list_elements"）
    description: str         # 给模型的说明（决定模型何时调用）
    parameters: dict         # JSON Schema（顶层 type=object，MCP inputSchema 直接透传）
    executor: Callable[[dict], dict]   # 接收参数 dict，返回结果 dict

class ToolRegistry:
    def register(self, tool: Tool) -> None: ...        # 重名覆盖
    def get(self, name) -> Tool | None: ...
    def names(self) -> list[str]: ...
    def all_tools(self) -> list[Tool]: ...             # MCP 适配层读取口（Quotor 为此加的唯一方法）
    def execute(self, name, arguments) -> dict: ...    # 未注册/异常统一 → {"error": ...}
    def to_openai_tools(self) -> list[dict]: ...       # 内置面板出口（现有 agent_loop 继续用）
    def read_only_tools(self) -> list[Tool]: ...       # READ_ONLY 白名单来源（MCP allow_actions 用）

def build_default_registry() -> ToolRegistry: ...      # 注册全部 74 工具（tools/ 子包分文件）
```

- `agent/tools/element_crud.py` 四工具迁入 `tools/element.py`，执行器改返回 dict 契约
  （4.6）；校验与错误文案风格保留；
- `agent_loop.py` 的 `tool_registry.execute/openai_tools` 调用点改走新类（外部行为不变，
  现有 `tests/` 保绿即验收）；
- `is_write` 判定改为注册表级元数据（`Tool.read_only: bool = False` 字段，或
  `WRITE_TOOLS` 名单由 `tools/` 各文件声明汇总）。

### 8.2 统一结果契约与序列化（P1）

- 全部执行器返回 dict；`{"error"}` / `{"cancelled": true}` / 正常三分（4.6）；
- 新增 `agent/serializers.py`（ORM/QDict → dict）：element_snapshot、principle_detail
  四 kind、quantity（key 拆解 category|item|unit + steps）、tree、library_template；
  `json.dumps(ensure_ascii=False, default=str)` 统一出口；
- **steps 拼接不变式**写入测试：`"".join(step.expr) == expression`、`Dim.e` 重算 == `Dim.v`。

### 8.3 上下文注入（P1，三层，对齐 Quotor）

现状：`ToolContext(unit_id, unit_name, confirm)` 是单层静态快照（面板发起对话时构造一次）。

升级为三层：

| 层 | 机制 | 内容 |
|---|---|---|
| ① 事件层 | EventBus 新增 `ai_context_changed = Signal(object)`；`tree_panel`（选中单位工程）、`unit_panel`（选中构件/当前行）选中变化时 emit | `{unit_id, unit_name, element_id?, element_name?}` |
| ② prompt 层 | `AiPanel` 持 `_current_context`，每轮请求组装 system 消息时经注册表新方法 `to_rules_for_context(context)` 动态追加规则段（"当前选中单位工程 X（unit_id=…），可直接调 list_elements / add_element…"；无选中时提示先 get_project_tree） | 按上下文追加规则（Quotor `to_prompt_text(context)` 的对应物） |
| ③ 运行时层 | T74 `get_current_context` 工具读实时选中（Quotor `get_current_workbench` 的对应物） | 工具可自查 |

- 工具执行器的 id 缺省解析（4.3）共享同一上下文源；
- ②注意：Quotor 的 `_format_params_compact` 紧凑参数格式与"核心约束/任务速查"分层
  system prompt 一并引入（见 8.6）。

### 8.4 确认策略升级（P1，双通道 + 结构化卡 + cancelled）

现状：`ConfirmBridge.ask(description:str)->bool`（300s 超时默认 False）+ 拒绝回填
"用户拒绝执行该操作。"文本 + `[ai] require_confirmation` 单开关。

升级三步：

1. **双通道**（照抄 Quotor `confirm_policy.py`）：`ContextVar _CHANNEL`
   （`CHANNEL_BUILTIN`/`CHANNEL_MCP`）+ `channel()/override_channel()` +
   `confirmation_suppressed()`（分别读 `[ai]/[mcp] require_confirmation`）；
   MCP 适配层执行时 `with channel(CHANNEL_MCP): registry.execute(...)`；
2. **结构化确认卡**：`ConfirmBridge.ask(preview: dict) -> dict`，preview =
   `{action, target, summary, details[]}`（对齐 Quotor `AiConfirmDialog`）；
   现有确认对话框 UI 升级为卡片渲染（action/summary 标题 + details 明细列表）；
   返回 `{"cancelled": true, "message": …}` 或执行结果；
3. **快照/恢复**（section2 版）：worker 线程 → ConfirmBridge 队列信号 → 主线程弹窗，
   contextvar 不跨 Qt 信号跳转 → `ConfirmBridge.request` 发射前快照
   `current_channel()`，主线程槽 `override_channel()` 包裹弹窗判定
   （对齐 Quotor 在 `AgentActionBridge.execute_on_main` 的做法，作用点移到 ConfirmBridge）。

配套（agent_loop 治理联动）：

- **cancelled 即终止**：循环收到 `{"cancelled": true}` 时把该结果回传模型并注入收尾
  指令（"用户已取消该操作，不要重试同一工具，向用户说明并询问下一步"），不再继续
  循环工具调用（Quotor 已验证：防模型反复弹窗骚扰用户）。

### 8.5 agent_loop 治理升级（P6，五类机制，对齐 Quotor `langgraph_loop.py`）

现状：手写 for 循环 `MAX_TOOL_ROUNDS=8`，无任何治理。现有原生 tool_calls 流式循环
**保留为主线**（section2 端点都是 OpenAI 兼容、原生 tools 支持；不引入 LangGraph，见 8.7），
在其上移植 Quotor 五类治理（独立函数、可单测）：

| # | 机制 | 规格（对齐 Quotor 数值） | 说明 |
|---|---|---|---|
| ① | 预算软着陆 | 时间预算 600s / 字符预算 25 万 / 轮数 40，超限注入 `WRAP_UP_PROMPT` 收尾 + 8 轮宽限后强制终止 | 防失控长跑 |
| ② | 停滞检测 | 滑动窗口 5 次调用内同签名工具 ≥3 次 → 注入 `_REPEAT_NUDGE_PROMPT` 纠偏，最多 2 次 | 防原地打转 |
| ③ | 提前收尾抢救 | `_PREMATURE_FINAL_RE` 匹配"让我/接下来/再查询"等计划句却输出终答 → 注入纠偏继续，最多 3 次 | 防任务做一半收工 |
| ④ | 空 content 重试 + 超长截断 | 空 content 重试 <2 次（注入"请继续"）；上下文超长时截断最老 `tool_result`（阈值 25000 字符，两轮观察） | 防卡死/爆上下文 |
| ⑤ | 瞬时错误退避 | 429/5xx 按 3/6/12/24s 退避、尊重 `Retry-After`、5 次上限；用户取消即终止 | `ai_provider.stream_chat` 侧实现 |
| — | 硬保险丝 | `MAX_TOOL_ROUNDS` 8 → 40（随预算软着陆放开） | 兜底 |

### 8.6 prompt 组织升级（P6，对齐 Quotor）

- **紧凑参数格式** `_format_params_compact`：把 JSON Schema 压成单行
  （`keyword*(str): 搜索关键词; limit(int)=20: 数量上限`；`*` 必填、enum 渲染
  `a|b|c`、数组 `type[item]`）——74 工具全量 Schema 直塞 system prompt 会爆炸，
  紧凑格式 token 减半以上（Quotor 实测结论：31 个工具的样板字段曾是其 prompt 膨胀主因）；
- **分层 system prompt**（注册表新方法，对齐 Quotor `to_base_prompt/to_rules_for_context/
  to_prompt_text`）：`基础层`（工具清单紧凑格式 + 调用格式 + 核心约束：*禁止编造
  id/原则名，必须来自工具结果或上下文；写操作前先查询拿真实 id* + 任务→工具速查表：
  *"录一条 D600 雨水管：list_library_templates→add_element"、"算这个单位工程：
  compute_unit"* + 执行策略：*调用前输出一行思考；搜索空结果换关键词；批量操作只弹
  一次确认*）+ `上下文层`（8.3 的动态规则段）；
- 领域约定（类别枚举/表达式规则）由 `agent/conventions.py` 单一来源注入基础层
  （与 T73 工具同源）。

### 8.7 LangGraph 重构（可选研究项，不进硬范围）

Quotor 生产路径是 `AgentLoop(QThread) 壳 → langgraph_loop.build_agent_graph()`
（StateGraph：call_model→条件边→execute_tool），动机包括为不支持 function calling 的
端点提供 `<<tool_call>>` 标签文本协议。section2 现有原生 tool_calls 流式循环工作正常、
端点均支持 tools，**一期不引入**；治理机制（8.5）设计为循环无关的独立函数，未来若
切换 LangGraph 可平移。标签文本协议（无 function calling 端点兼容）列为同项研究的
一部分（如确有局域网小模型需求再立项）。

### 8.8 reasoning 处理（P6，对齐 Quotor `provider_adapter`）

现状：`ai_provider` 有 `on_reasoning`（DeepSeek `reasoning_content` 增量）。
补齐（Quotor 已验证三点）：

1. **content 为空时从 reasoning_content 回退解析工具调用**（部分端点把 tool_call 相关
   内容放进 reasoning 流）；
2. reasoning 面板展示截断（500 字符）防刷屏；
3. 流式节流（0.3s 或 40 字符一拍）降低 UI 压力。

### 8.9 兜底项（仅当 P0 冒烟失败才执行）

无 QApplication 环境 import `app.viewmodels.unit_vm` + `bus()` 冒烟失败时：
`core/event_bus.py` 改为可选 Qt（`try: from PySide6…`，无 Qt 时同接口纯 Python 占位，
emit 直调订阅者）。正常情况下**不做**此改造（内嵌模式必然有 QApplication；Quotor headless
已证明同类架构可行）。

---

## 9. 代码改动清单（v1.1 汇总）

### 9.1 新增

| 模块 | 内容 |
|---|---|
| `src/app/mcp_server/`（5 文件） | 6.1：adapter / server / auth / controller / __main__ |
| `src/app/agent/tools/`（8 文件） | 74 工具分文件（project/tree/element/principle/reference/compute/migrate/summary）+ `__init__.py` 的 `build_default_registry()` |
| `src/app/agent/serializers.py` | 8.2 序列化 |
| `src/app/agent/conventions.py` | 领域约定单一来源（T73/prompt 基础层共用） |
| `src/app/agent/governance.py` | 8.5 五类治理（独立函数，循环无关） |
| `src/app/services/summary.py` | 7.8 H 组无头汇总 + Excel 导出（M5 共用） |
| `views/dialogs/mcp_settings_dialog.py` | 5.2 MCP 设置对话框 |
| `tests/test_mcp_*.py`、`tests/test_agent_governance.py` 等 | 各阶段测试 |

### 9.2 需要抽取/下沉的现有逻辑（唯一业务重构，P2 前置）

原则编辑器落库逻辑混在 Qt 槽里，需抽成 `project_io`（或新 `services/principle_edit.py`）
纯函数，对话框改调它们（对话框行为不变，`tests/test_principle_ui*` 保绿即验收）：

| 抽取目标 | 来源对话框 | 说明 |
|---|---|---|
| `apply_enclosure(id, fields, works)` | `enclosure_edit_dialog.py` `_apply_rows/_confirm` | 做法表整表替换（含多级重建、止水挂接） |
| `apply_work_levels(work_id, levels)` | `principle_dialogs.EnclosureWorkDialog` | h=-1 均分；按库模板建级构件 |
| `apply_foundation(id, layers, component)` | `foundation_edit_dialog.py` | 换填层整表 + 特殊地基构件挂接 |
| `apply_precipitation(id, wells)` | `principle_dialogs.PrecipitationEditDialog` | 5 井型写回 |
| `apply_width_items(id, mode, items)` | `principle_dialogs.WidthEditDialog` | 矩阵写回 + 恢复默认 |
| `apply_component_params(component_id, params)` | `principle_dialogs.ComponentEditDialog` | `显示名\|表达式` 组装 + 键集校验 |
| `search_library(category, keyword)` | 新增 | 构件库关键词检索（T60 用） |

### 9.3 升级改造（现有文件）

| 文件 | 改动 |
|---|---|
| `agent/tool_registry.py` | 类化重写（8.1） |
| `agent/tools/element_crud.py` | 迁入 `tools/element.py` 并扩容（`ToolContext` 语义并入 id 缺省解析） |
| `agent/confirm_policy.py` | 双通道 + ContextVar（8.4） |
| `agent/agent_loop.py` | 走新注册表 + cancelled 终止 + 治理挂点（8.5） |
| `services/ai/ai_provider.py` | reasoning 三点补齐（8.8） |
| `views/panels/ai_panel.py` | 上下文三层 + system prompt 分层（8.3/8.6） |
| `views/dialogs/`（确认对话框） | 结构化确认卡渲染（8.4） |
| `core/event_bus.py` | 新增 `ai_context_changed` Signal |
| `core/config.py` | `[mcp]` 段 + `_ConfigProxy.mcp_*`（5.1） |
| `views/main_window.py` | AI 菜单「MCP 服务…」+ 启动钩子 + 状态栏 + closeEvent（5.2） |
| `pyproject.toml` | `[mcp]` extra + `section2-mcp` 入口（6.1） |

### 9.4 明确不改

- `core/models/`（表结构、SCHEMA_VERSION=7、迁移链）；
- `viewmodels/unit_vm.py`、`project_vm.py` 现有函数签名与行为（工具直接调用）；
- `services/atlas.py`、`element_library.py`、`stn_migration.py`、`project_io.py` 现有函数
  （原则编辑抽取是**新增**纯函数，对话框与工具都改为调用它们）；
- `section2.spec`（GUI 打包不动；`section2-mcp` 独立入口另行处理，P6 评估是否随 GUI
  分发或单独 wheel）。

---

## 10. 分阶段实施计划

> 每阶段 = 可独立合并的 PR；验收 = 该阶段测试全绿 **且** 全量回归
> （`.venv/Scripts/python.exe -m pytest`）不回退。
> 建议在 `feature/mcp-server` 分支开发，每阶段完成后 rebase 合并。
> 节奏对齐 Quotor M1~M5：先 stdio 自检（MCP Inspector 验证），再上内嵌 HTTP + GUI 集成。

### P0 骨架 + 注册表类化（~1 人日）

| 任务 | 说明 |
|---|---|
| P0-1 | pyproject 加 `[mcp]` extra（`mcp>=2.0,<3` pin 精确版）与 `section2-mcp` 入口；`.venv` 安装 |
| P0-2 | `agent/tool_registry.py` 类化重写（8.1）；element_crud 四工具迁入 `tools/element.py` 改 dict 契约；`agent_loop` 调用点切换——**外部行为不变**，现有测试保绿 |
| P0-3 | `mcp_server/` 五文件骨架（6.2/6.3 照抄 Quotor 形态）；`--transport stdio` 本地模式先跑通 |
| P0-4 | **无头冒烟** `tests/test_mcp_headless.py`：不建 QApplication，import + 临时 `new_project`（直接调 service 层）→ 只读工具（list_library_templates / evaluate_expression）经适配层执行成功；写工具被守卫拦截返回可读错误。失败则执行 8.9 兜底后重测 |
| P0-5 | MCP Inspector 连接 `section2-mcp --transport stdio`，list_tools 正常 |

**验收**：类化后现有测试全绿；Inspector 可列工具；adapter 单测（工具数/字段/未知工具
isError/allow_actions 过滤/headless 守卫）通过。

### P1 内嵌 HTTP + 工程会话/项目树/构件核心 + 上下文注入（~2 人日）

| 任务 | 工具 |
|---|---|
| `auth.py` + `controller.py` + `server.py` HTTP 组装（uvicorn 后台线程）；`main_window` AI 菜单「MCP 服务…」+ 启动钩子 + 状态栏 + closeEvent；`[mcp]` 配置段 | — |
| confirm 双通道（8.4：ContextVar + ConfirmBridge 快照/恢复 + 结构化确认卡 + cancelled 即终止） | — |
| 上下文三层（8.3：`ai_context_changed` + prompt 动态规则 + T74） | T74 |
| A 组工程会话 + B 组项目树 + C 组核心 | T01~T18 + T73（20 个） |
| serializers 的 element/tree 部分；id 缺省解析（内嵌取选中） | — |

测试：适配层契约（正/反路径）；HTTP 协议闭环（initialize→list_tools→call_tool；无/错
token → 401；对 token → 200；仅回环可达）；E2E：临时工程 → 建树 → 加构件（含管道/
参数/引用）→ list/get → update → delete；写操作弹确认卡、拒绝返回 cancelled 且循环终止；
写后 `.stn2` 落盘且 `Backup\` 出现备份。

**验收**：`curl` 带 token 能 list_tools；Codex 或 Claude Desktop 配置后能 `get_project_info`
读回工程名；GUI 界面在 AI/MCP 写操作后实时刷新（EventBus）。

### P2 构件子行扩展 + 六类原则全套（~3 人日，工作量最大）

- 前置：完成 9.2 的原则编辑抽取重构（`test_principle_ui*` 保绿）；
- 工具：T19~T55（37 个）+ serializers 原则四 kind；
- 测试：原则建改删对拍（新建围护含多级+止水 → get_principle_detail 深度断言；降水五井型
  往返；面宽矩阵 set/reset；delete 并入语义；最后一条拒删；spcp 导出→删除→导入还原）；
  `test_multi_principle.py` 语义在工具路径重放。

**验收**：D 组契约测试绿；用工具从零建出与 `tests/baselines/对拍工程.json` 等价的
工程（数据面）。

### P3 图集查询 + 计算（~1 人日）

- 工具：T56~T66（11 个）；`compute_unit/element` 结构化序列化（含 steps 不变式断言）；
- 测试：复用 `test_calc_baseline.py` 算例——工具路径 `compute_unit` 与 baseline 数值/
  表达式**逐字段一致**（硬验收）；`resolve_atlas` 对照图集用例；缺 pp/pw 引导性错误。

### P4 旧档迁移（~0.5 人日）

- 工具 T67~T68；复用 `test_stn_migration.py` 样例集（批量导入 + warnings 断言）；
  `inspect` 不写文件（headless 白名单内）。

### P5 汇总与导出（~1.5 人日，含 M5 协同）

- 先写 `services/summary.py`（无头汇总 + Excel 导出，openpyxl）+ 对拍测试
  （与旧版导出数值一致，误差规则同对拍 0.5%）；
- 工具 T69~T72；桌面 M5 重做时直接复用该 service（界面工作另行立项，不阻塞）。

### P6 AI 助手治理 + CLI 四模式 + 加固 + 文档（~2 人日）

| 任务 | 说明 |
|---|---|
| agent_loop 五类治理（8.5）+ prompt 紧凑格式与分层（8.6）+ reasoning 三点（8.8） | AI 助手二期收尾 |
| `section2-mcp` 四模式补全（6.5/6.6）：`--connect` stdio 桥、`--project` headless 只读 | 辅助入口 |
| `allowed_dirs` 路径白名单 | 4.5 加固 |
| elicitation 评估 | 可行则实现，不可行记入开放问题 |
| `docs/mcp.md`（安装 + 客户端配置示例，附录 A 内容迁入）+ README 章节 + 打包评估（`section2-mcp` 随 GUI 或独立 wheel） | 文档 |

**验收**：治理机制单测（预算/停滞/收尾/截断/退避各触发一次）；stdio 桥端到端
（Codex stdio 配置驱动运行中的桌面应用）；headless 模式全只读工具可用；
端到端演练：外部客户端完成一次「建工程 → 录构件 → 配原则 → 算量 → 复核表达式 →
（用户确认）改数据」全流程。

---

## 11. 风险与开放问题

### 11.1 风险

| 风险 | 缓解 |
|---|---|
| mcp 2.x API 跨版本变动（Quotor 已踩坑：FastMCP 移除、ClientSession 需 async with） | pin `mcp>=2.0,<3` 精确版本；升级独立小 PR；P0 用 stdio 先跑通，HTTP 单独迭代 |
| 本机 HTTP 暴露被滥用 | 仅回环绑定 + Bearer token + `allow_actions` 开关（4.5） |
| 写操作确认在无人值守场景卡住 | `[mcp] require_confirmation=false` 跳过弹窗（信任客户端批准）；`allow_actions=false` 干脆不暴露写工具；文档写明默认行为 |
| 无 QApplication 下 PySide6.QtCore/EventBus 行为异常 | P0-4 冒烟先行；兜底 = event_bus 可选 Qt 改造（8.9）；内嵌模式（主路线）必然有 QApplication，风险只在辅助入口 |
| `compute_unit` 返回过大（token 爆炸） | include_steps 默认关（compute_unit）；紧凑 prompt 格式（8.6）；per_element 分页列 v2 |
| 全局单会话被并发写破坏（HTTP 多客户端） | **工具执行统一经 `execute_on_main` 回到 Qt 主线程串行**（`ToolRegistry.execute` 内实现，ContextVar 随调用复制）；适配层另加 `threading.Lock` 串行 MCP 调用；`project_io`/ORM 加主线程守卫，worker 直接访问会立即报错而不是偶发 `prepared` 竞态 |
| 原则抽取重构碰坏 GUI 对话框 | 对话框行为不变原则；`test_principle_ui*` + 手工过一遍六类编辑器 |
| 74 工具 system prompt 膨胀 | 紧凑参数格式（Quotor 实测 token 减半以上）+ 上下文层动态注入 |
| AI 误操作（写文件/删数据） | 双通道确认 + readonly + 路径白名单 + 备份兜底（Backup 20 份可人工恢复） |

### 11.2 开放问题（需产品决策，不阻塞 P0~P5）

1. **导航类工具**（`navigate_to_unit`/`select_element`：让 GUI 跳转选中，Quotor 有）
   ——需主线程 marshal（碰 Qt 控件），section2 需引入 Quotor 式 ActionBridge 或经
   EventBus 信号实现；收益是"AI 操作用户看得见"，列 P7 候选；
2. **LangGraph 重构 + `<<tool_call>>` 标签协议**（8.7）：仅当局域网小模型
   （无 function calling 端点）成为真实需求才立项；
3. 多工程并行会话（当前单工程/进程，与数据层全局会话一致）是否有真实需求；
4. 断面图 PNG 渲染（v2，matplotlib 重绘 `section_view` 数据源）是否排期；
5. M5 汇总/导出的最终交互形态（不影响工具契约，service 先行）；
6. `section2-mcp` 分发形态：随 GUI 安装包 / 独立 wheel / 两者。

---

## 12. 附录

### A. MCP 客户端配置示例（P6 整理入 docs/mcp.md）

```toml
# Codex CLI（~/.codex/config.toml）—— 主路线（内嵌 HTTP）
[mcp_servers.section2]
type = "http"
url = "http://127.0.0.1:8765/mcp"
headers = { Authorization = "Bearer <MCP 设置对话框生成的 token>" }

# stdio 桥（照顾只支持 stdio 的客户端）
# command = "section2-mcp", args = ["--connect", "http://127.0.0.1:8765/mcp", "--token", "<token>"]
```

```jsonc
// Claude Desktop（claude_desktop_config.json）/ Cursor / Cline / VS Code / WorkBuddy
{ "mcpServers": {
    "section2": { "url": "http://127.0.0.1:8765/mcp",
                  "headers": { "Authorization": "Bearer <token>" } } } }
// 或 stdio 桥：
//   "section2": { "command": "<venv>\\Scripts\\section2-mcp.exe",
//                  "args": ["--connect", "http://127.0.0.1:8765/mcp", "--token", "<token>"] }
// headless 只读（无 GUI、脚本化）：
//   "section2": { "command": "<venv>\\Scripts\\section2-mcp.exe",
//                  "args": ["--project", "D:\\工程\\某项目.stn2"] }
```

> 具体字段名以各客户端官方文档为准；MCP 设置对话框提供可直接粘贴的片段（5.2）。

### B. 数据模型速查（.stn2 表 → 关键字段）

`basic_info`（工程名/编号/编制人/图集名）→ `segment` → `unit` → `element`
（category 0~7、depth/amount 算式原文、pe/pf/pp/pw_name、main_pe_name、source、order_no）
→ 子表 `pipe`(mat,dn,content,t) / `element_param`(key,unit,value) /
`element_quantity`(category,item,unit,value) / `element_principle`(kind∈pe,pf, name, ratio, order_no)；
原则：`principle_enclosure`(+`enclosure_cushion`+`enclosure_work`→`enclosure_level`→`component`) /
`principle_foundation`(+`foundation_replacement`+`component`) /
`principle_precipitation`(5 井型字符串) / `principle_width`(+`principle_width_item`) /
`component_param`(key, value="显示名|表达式")；`price`(key,value)；`meta`(schema_version=7…)。

### C. 领域约定速查（conventions.py 必须完整收录，工具 description 与 prompt 基础层引用）

- 类别：直埋管道/包封/箱涵/顶管/牵引管/管廊/构筑物（`CATEGORY_NAMES`）；
- 图集参数行：直埋 3 行（工作面加宽/垫层厚/基础厚）、包封/箱涵/管廊 2 行、顶管/牵引 0 行
  （`ATLAS_PARAM_CATEGORIES`；键存在=用户覆盖，空=按图集）；
- 图集返回单位 **mm**；降水井型值格式 `elevation|gap|sides`；构件参数值格式 `显示名|表达式`；
- 表达式规则：不做预运算、毫米→米写 `值/1000`、括号只在语法必需处（详见 docs/architecture.md，
  AI 改算式相关数据前应先取 `get_conventions`）；
- 多原则：按 ratio 加权合并；支撑 Z 量按主围护原则（main_pe_name）计算。

### D. 实施记录（v1.2，已落地）

> 实施日期：2026-10-20；基线提交 `085304a`；测试结果 **182 passed**
> （原有 152 + 新增 30）。

**已交付**

| 项 | 文件 |
|---|---|
| 统一工具注册表（74 工具） | `agent/tool_registry.py`、`agent/tools/`（project/tree/element/element_parts/principle/reference/compute/migrate/summary/meta） |
| 上下文 / 约定 / 治理 / 序列化 | `agent/context.py`、`conventions.py`、`governance.py`、`serializers.py`、`errors.py` |
| 双通道确认 + 结构化确认卡 + cancelled | `agent/confirm_policy.py`、`main_window.py::_confirm_ai_write` |
| 循环升级（预算/停滞/收尾/截断/退避/文本兜底） | `agent/agent_loop.py`、`governance.py` |
| MCP 服务器（内嵌 + CLI 四模式） | `mcp_server/adapter.py`、`server.py`、`auth.py`、`controller.py`、`__main__.py` |
| 设置界面 | `views/dialogs/mcp_settings_dialog.py`、AI 菜单「MCP 服务…」、状态栏 |
| 原则编辑纯函数 | `services/principle_edit.py` |
| 汇总 / Excel 导出（M5 共用） | `services/summary.py` |
| 配置 | `core/config.py` 的 `[mcp]` 段 |
| 文档 | `docs/mcp.md`、README M10 章节 |
| 测试 | `tests/test_mcp_adapter.py`、`test_mcp_tools.py`、`test_mcp_server.py`、`test_agent_governance.py` |

**与 v1.1 方案的差异（实施决策）**

1. `add_element` 的 `seed_atlas_defaults` 默认 **false**（与界面 `create_element`
   一致；构件库插入走 `insert_element_from_template` 时由 unit_vm 自己预填）。
2. 确认卡由主窗体安装的**全局处理器**统一渲染（`install_confirm_handler` /
   关闭时 `uninstall_confirm_handler`），内置面板与外部 MCP 共用；MCP 通道判定
   在 worker 线程完成，因此不需要 Quotor 的 contextvar 快照/恢复。
3. 写操作在无界面进程直接返回可读错误（不再弹无人应答的确认框）；只读工具
   全部 headless 可用。
4. 原则对话框保留原有增量落库逻辑（复用 `project_io` 原语）；`principle_edit`
   提供工具侧整表语义，两者建立在同一批原语上。后续可把对话框统一切换过去。
5. Excel 导出列：类别/项目/单位/计算表达式/工程量/单价/合价；整工程导出多一列
   单位工程。
6. 未实现（均按方案列为 v2/可选）：导航类工具（`navigate_to_*` / `select_*`）、
   MCP elicitation、LangGraph 重构 / `<<tool_call>>` 文本协议（治理已独立实现，
   `extract_tool_call` 提供兜底解析）、断面图 PNG、`--http` 多客户端独立实例。

**验收对照**

| 方案验收项 | 结果 |
|---|---|
| 74 工具注册表，内置面板与 MCP 同一来源 | ✅（`len(names()) == 74`） |
| 无头冒烟（不建 QApplication 走业务层） | ✅（`test_mcp_tools.py`） |
| 计算对拍（数值 + 表达式逐字段一致） | ✅（复用 `test_calc_baseline.py` 算例，工具路径一致） |
| steps 拼接不变式 | ✅（`test_mcp_tools.py::test_compute_tools_and_steps_invariant`） |
| MCP 协议闭环 + Bearer 鉴权 | ✅（官方 SDK 客户端连本地 uvicorn） |
| 内嵌控制器真实启停 | ✅（74 工具，`evaluate_expression` 往返成功） |
| 全量回归不回退 | ✅ 182 passed |

### E. 术语表

| 术语 | 含义 |
|---|---|
| `.stn2` | 单文件 SQLite 工程文件；commit 即落盘 |
| `.spcp` | 单原则导出 XML（围护/地基/降水/面宽四类） |
| QDict / Quantity / steps | 工程量字典；单项量=键(类别\|项目\|单位)+数值+表达式+中间步骤 |
| Ei/WSi/Fi | 构件公式库三组：围护/止水/特殊地基模板 |
| 对拍 | 与旧版 section 1.2.2 输出逐数值比对（误差 <0.5%），基线 `tests/baselines/对拍工程.json` |
| 双通道 | builtin（内置 AI 面板）/ mcp（外部 MCP 客户端）两条确认策略通道 |
| stdio 桥 | `section2-mcp --connect`：把 stdio MCP 转发到运行中桌面应用的 HTTP 端点 |
