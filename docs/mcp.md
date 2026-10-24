# Section 2.0 MCP 服务

Section 2.0 把**全部功能**暴露为 MCP（Model Context Protocol）工具，共 **74 个**：
外部 AI 客户端（Claude Desktop / Claude Code / Codex / Cursor / Cline / VS Code /
WorkBuddy…）可以直接建工程、管项目树、录构件、编辑六类原则、查图集、算工程量、
迁移旧工程、汇总导出。

> 本项目**没有业务服务端**：MCP 端点只是协议入口（默认关闭、仅本机回环），
> 不改变"纯桌面应用"的定位；模型调用仍由客户端自己完成。

## 两种入口

| 入口 | 传输 | 说明 |
|---|---|---|
| **GUI 内嵌**（主方案） | Streamable HTTP（`127.0.0.1:8765/mcp`） | 在桌面应用里启用；与界面共享同一个工程会话和锁，工具执行器经 `execute_on_main` 回到主线程串行执行，界面经 EventBus 实时刷新，写操作在界面弹确认卡 |
| **独立 CLI** `section2-mcp` | stdio / 本地 HTTP / stdio 桥 / headless | 见下文四种模式 |

内嵌与 CLI 用的是**同一套工具注册表**（`app/agent/tools/`），与内置 AI 助手
（右栏面板）完全同一条业务代码路径，不存在两套逻辑。

## 启用（GUI 内嵌）

1. 菜单 `AI → MCP 服务…`；
2. 勾选「应用启动时自动启动 MCP 服务」（或点「启动服务」）；
3. 首次启用会自动生成 Bearer token（可复制/重置）；
4. 点「复制配置」把片段粘贴到客户端配置文件。

配置保存在 `config.toml`：

```toml
[mcp]
enabled = false             # 应用启动时是否自动启动
port = 8765                 # 固定监听 127.0.0.1
token = ""                  # 空 = 首次启用时自动生成
allow_actions = true        # false = 只暴露只读工具（24 个）
require_confirmation = true # 外部客户端写操作是否在界面弹确认卡
allowed_dirs = []           # 文件写入类工具的目标目录白名单；空 = 不限制
```

## 客户端配置

```jsonc
// Claude Desktop（claude_desktop_config.json）/ Cursor / Cline / VS Code / WorkBuddy
{
  "mcpServers": {
    "section2": {
      "url": "http://127.0.0.1:8765/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

```toml
# Codex CLI（~/.codex/config.toml）
[mcp_servers.section2]
type = "http"
url = "http://127.0.0.1:8765/mcp"
headers = { Authorization = "Bearer <token>" }
```

只支持 stdio 的客户端：用 stdio 桥（客户端拉起 `section2-mcp`，转发到运行中的
桌面应用）：

```jsonc
{
  "mcpServers": {
    "section2": {
      "command": "<仓库>/.venv/Scripts/section2-mcp.exe",
      "args": ["--connect", "http://127.0.0.1:8765/mcp", "--token", "<token>"]
    }
  }
}
```

## 独立 CLI 四种模式

```bash
# 1) 本地 stdio（进程内执行工具；无界面时写工具被拒绝）
section2-mcp

# 2) 本地 Streamable HTTP
section2-mcp --transport http --port 8765 --token <token>

# 3) stdio 桥：转发到运行中桌面应用的 HTTP 端点
section2-mcp --connect http://127.0.0.1:8765/mcp --token <token>

# 4) headless 只读：无界面打开工程（脚本化 / CI 查询计算）
section2-mcp --project "D:\工程\某项目.stn"
```

- 模式 4 会抢 `.lock`（与桌面版互斥、先后接管，进程退出自动释放），
  **强制只读**：读树/构件/原则、图集、计算、汇总、inspect 等全部可用；
  写操作与迁移不可用（没有确认面）。
- 所有本地模式都只绑定 `127.0.0.1`。

## 工具清单（74 个，按组）

| 组 | 数量 | 代表性工具 |
|---|---|---|
| 工程与会话 | 7 | `create_project` `open_project` `save_project_as` `get_project_info` |
| 项目树 | 6 | `get_project_tree` `add_segment` `add_unit` `delete_node` `move_node` |
| 构件条目 | 8 | `list_elements` `add_element` `update_element` `delete_element` `duplicate_element` |
| 构件子行 | 17 | `add_pipe` `update_param` `add_quantity` `add_principle_ref` `set_main_pe` |
| 六类原则 | 20 | `list_principles` `get_principle_detail` `create_enclosure` `set_enclosure_works` `set_width_items` `export_principle` |
| 图集/构件库 | 8 | `resolve_atlas` `query_atlas_table` `list_library_templates` `get_component_template` |
| 计算 | 3 | `compute_unit` `compute_element` `evaluate_expression` |
| 旧档迁移 | 2 | `inspect_legacy_project` `migrate_legacy_project` |
| 汇总导出 | 4 | `get_unit_summary` `set_price` `batch_import_prices` `export_excel` |
| 约定/上下文 | 2 | `get_conventions` `get_current_context` |

返回约定（与内置 AI 工具一致）：

```jsonc
{ "ok": true, "data": { … } }                    // 正常
{ "ok": false, "error": "…下一步指引…" }          // 业务失败（MCP isError=true）
{ "cancelled": true, "message": "用户取消了操作" } // 用户取消（MCP isError=false）
```

工程量结果包含 `value`、`expression`（数值代入算式）与 `steps`（中间步骤）；
**steps 各步拼接恒等于 expression**，不要改写。

## 权限与安全

| 机制 | 行为 |
|---|---|
| 仅回环 | 端点固定 `127.0.0.1`，不暴露局域网 |
| Bearer token | 所有 HTTP 请求校验 `Authorization: Bearer <token>` |
| `allow_actions=false` | 只暴露只读工具（写工具从 `tools/list` 中消失） |
| `require_confirmation=true` | 外部客户端写操作在桌面界面弹结构化确认卡 |
| headless 守卫 | 无界面进程拒绝写工具（返回可读错误，不会挂死） |
| `allowed_dirs` | 非空时 save_as / 导出 / 迁移目标路径必须在白名单内 |
| 备份 | 每次写即时落盘；首次修改自动备份到工程同级 `Backup\`（保留 20 份） |

## 代码位置

```
src/app/agent/
├── tool_registry.py   # Tool / ToolRegistry / 74 工具注册表
├── tools/             # 按领域分文件的工具实现
├── confirm_policy.py  # builtin / mcp 双通道确认
├── context.py         # 当前选中上下文（内嵌模式 id 缺省解析）
├── governance.py      # 循环治理（预算/停滞/退避…）
├── serializers.py     # ORM / QDict → dict
└── conventions.py     # 领域约定（工具描述与 prompt 共用）
src/app/mcp_server/
├── adapter.py         # ToolRegistry → MCP（唯一适配层）
├── server.py          # mcp SDK 2.x lowlevel Server + Streamable HTTP
├── auth.py            # Bearer 鉴权中间件
├── controller.py      # GUI 内嵌生命周期
└── __main__.py        # section2-mcp CLI（四模式）
src/app/services/
├── principle_edit.py  # 原则编辑纯函数（工具与对话框共用）
└── summary.py         # 汇总 + Excel 导出（MCP 与 M5 共用）
```

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests/test_mcp_adapter.py tests/test_mcp_tools.py \
    tests/test_mcp_server.py tests/test_agent_governance.py
```

- `test_mcp_adapter.py`：工具面、只读过滤、headless 守卫、结果语义；
- `test_mcp_tools.py`：无界面全链路（工程/树/构件/原则/图集/计算/迁移/汇总导出）；
- `test_mcp_server.py`：Bearer 鉴权 + 官方 SDK 客户端 HTTP 协议闭环；
- `test_agent_governance.py`：预算/停滞/收尾/截断/退避/文本兜底解析。
