# Section 2.0

线性工程（市政管道等）工程量计算软件 **section** 的 Python 重写版，跨平台（Windows / macOS / Linux）。

初代是 C# WinForms 程序（最终版参照 `section/section-master`，只读参考）。2.0 复刻其全部功能，并新增：

- **计算表达式输出**：每个工程量除了结果，还给出一条数值代入的算式，例如
  `(2×(600/1000+(65×2+130×2+500×2)/1000)+2×(2.5+0.3+(65+130)/1000)×1)×(2.5+0.3+(65+130)/1000)/2×120.5 = 1799.074`；
  算式**不做预运算**——槽底宽、毫米→米换算、换填总厚、弓形占位这些派生量都把
  来源（管径 / 图集参数 / 面宽原则 / 构件参数…）写全，只有直接录入或查表的原始
  数据才是单个数字；括号只在语法必需处出现；算式与结果共用同一套数值，
  悬停/双击表达式可看**中间步骤**（每步说明 + 该步算式，各步拼起来就是完整算式）；
- **AI 助手面板**（`Ctrl+L`）：流式对话 + 工具调用（一期为构件条目增删改查 4 个工具，
  写操作一律弹确认窗），支持任意 OpenAI 兼容端点（DeepSeek / OpenAI / Ollama / vLLM / 通义…）；
- **打开旧版工程自动转译**（brackets 同款）：直接打开 1.0 的 `.stn`，自动转译成 2.0 数据并弹窗
  提示；原文件先备份到软件数据目录的 `migration_backup` 再原样保留——转译结果处于
  “尚未保存”的临时状态，首次保存走另存为选新路径，旧文件绝不被覆盖。另有
  `文件 → 导入旧版工程(.stn)…` 向导可指定目标路径，带解析摘要、原则补齐警告与可复制的迁移报告。
- **撤销 / 重做**（`Ctrl+Z` / `Ctrl+Y`，brackets 同款快照式）：每次修改自动落盘时把整工程
  快照压进撤销栈（最多 25 步、总 10 MB），撤销/重做即用快照重建工作库并重写文件；
  树选中与表格焦点随快照恢复。界面操作与 AI/MCP 写操作走同一条修改通道，都可撤销。

新版工程文件扩展名沿用 **`.stn`**：开头是 1.0 风格的 XML 头（老软件误打开时能识别出
“高版本文件”并提醒，而不是崩溃），其后是 CDATA 包裹的 JSON 数据体（正式数据，
见 `src/app/services/stn_format.py` / `stn_codec.py`）。提交即落盘 = 自动保存，
带 `.lock` 防双开与 Backup 自动备份。

## 功能总览（里程碑 M1~M10）

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 骨架 | 三栏单窗体（无边框自绘标题栏）、light/dark 主题 | ✅ |
| M2 数据层 | `.stn`（1.0 兼容头 + JSON）、自动保存、锁、备份、新建向导、项目树、录入表格（算式求值） | ✅ |
| M3 原则与图集 | 图集 xlsx 加载查询、构件库、6 个原则编辑器（围护/地基/做法/构件公式/工作面宽度/降水）。多围护/多地基原则引用（按比例）在 2.0.0 后期取消，旧工程迁移时按比例拆条 | ✅ |
| M4 计算引擎 | 沟槽土方/回填、管道基础、降水、围护与特殊地基公式、表达式记录器、对拍测试 | ✅ |
| M5 导出与汇总 | 汇总面板（量×单价=合价、单价可编辑、批量载价）、定额/清单双表 Excel 导出（含表达式列） | ⏳ 曾随旧版界面实现，未接入现行界面，已移除待重做 |
| M6 旧工程迁移 | 旧 `.stn` XML 解析、原则重建、容错报告，全部样例工程批量导入测试 | ✅ |
| M7 AI 对话 | AI 设置（keyring 存 key）、SSE 流式对话、思考过程折叠 | ✅ |
| M8 AI 工具 | 构件条目增删改查 4 个工具 + 确认弹窗 + 自动刷新 | ✅ |
| M9 发布 | 全量回归、PyInstaller 打 Windows 包 | ✅ |
| M10 MCP 服务 | 全部功能 MCP 化（69 工具）：GUI 内嵌 Streamable HTTP + 独立 CLI（stdio / 桥 / headless 只读） | ✅ |

## 技术栈

| 项 | 选型 |
|---|---|
| Python | 3.12+（项目内 `.venv`） |
| 界面 | PySide6 (Qt6)，MVVM + EventBus，无边框自绘标题栏 |
| 架构 | `views/ → viewmodels/ → services/ → core/models/`（src 布局） |
| 工程文件 | `.stn`：XML 头 + JSON 数据体（`services/stn_format` 信封 + `stn_codec` 编解码）；运行时用临时 SQLite 工作库（SQLAlchemy 2.0 ORM） |
| 算式求值 | simpleeval（白名单运算符与 abs/round/sqrt/power/sin/cos，禁任意函数调用） |
| 图集 | xlsx + openpyxl（只读，随程序分发于 `src/app/resources/atlas/`）；元素模板库为 XML（`inventory/EleInventory.stn`） |
| 旧档迁移 | lxml（只读解析旧 `.stn` XML） |
| AI | httpx + OpenAI 兼容端点（SSE 流式），API key 存 keyring |
| 配置 | platformdirs + `config.toml`（与工程文件严格分离） |
| 打包 | PyInstaller（`section2.spec`） |

## 目录结构

```
src/app/
├── main.py            入口：QApplication、主题、中文翻译、主窗体、启动参数
├── core/              版本、路径、配置、事件总线、算式求值
│   ├── models/        临时工作库表结构（base.py 管连接与 meta，models.py 管表）
│   └── calc/          计算引擎：groove / foundation / precipitation / engine / tracer
├── services/          工程文件读写、图集与构件库、旧档迁移
│   └── ai/            ai_provider（SSE 流式）、ai_keychain（keyring）
├── viewmodels/        MVVM 视图模型
├── views/             主窗体（含无边框标题栏）、三栏面板、对话框、新建/导入向导
├── agent/             AI 工具调用（tool_registry / agent_loop / confirm_policy / tools）
├── mcp_server/        MCP 适配层 / Server / 鉴权 / GUI 生命周期 / CLI（section2-mcp）
└── resources/         QSS 主题、图集 xlsx、构件库、字体/图标/logo
tests/                 单元测试（工程文件、算式、计算对拍、旧档迁移）
docs/                  架构说明
```

## 运行方式

```bash
# 1. 建虚拟环境（项目根目录下）
py -3.12 -m venv .venv

# 2. 安装依赖（含开发依赖）
.venv/Scripts/python.exe -m pip install -e ".[dev]"      # Windows
# .venv/bin/python -m pip install -e ".[dev]"            # macOS / Linux

# 3. 启动
.venv/Scripts/python.exe src/app/main.py
# 也可直接带工程文件启动
.venv/Scripts/python.exe src/app/main.py "D:\工程\某项目.stn"

# 4. 跑测试
.venv/Scripts/python.exe -m pytest

# 5. 打 Windows 包
.venv/Scripts/pyinstaller section2.spec --noconfirm
# 产物：dist\Section2\Section2.exe
```

界面速查（复刻原版 section 1.2.2 的布局与交互）：左栏上半是项目树
（工程 → 标段 → 单位工程），下半是构件库（类别下拉 + 模板树，双击元素插入主表格）；
中部工作区上方是原则横条——「沟槽围护 / 地基处理」单选切换、原则名标签
（双击打开围护/地基原则编辑窗体，右键可编辑/导入/导出/删除原则，「+」直接新建）、
下方是单位工程工作台（定额工程量 / 清单工程量页签 + 断面图，左下「管材 / 构件参数 /
工程量」参数面板）；右栏 AI 助手（`Ctrl+L` 折叠）。
编辑菜单：撤销 `Ctrl+Z` / 重做 `Ctrl+Y`。
`Ctrl+Shift+T` 切换亮/暗主题。

## 附属构筑物（对齐 section-master）

（2.0 开发中期取消了旧版的“多围护原则 / 多地基原则”按比例引用功能：一个构件只能
引用一条围护、一条地基原则；旧工程里的多原则条目在迁移时按比例自动拆成多条独立
条目，详见 `services/stn_migration.py`。）
- **附属构筑物（构筑物类）**：检查井、雨水口、排放口等不参与沟槽计算的计数构件，
  单位“个”。工程量直接来自构件参数表（键本身即“构筑物|垫层|m3”这类定额键，
  值可写算式），并自动按 `井筒方量 = 个数 × max(埋深−井高, 0.4) × 每米方量` 追加
  “构筑物|井筒|m3”；参数行可增删改（“-名称 / -单位”两个键锁定）；
- **构件库**：已随 section-master 更新到 1.3.2.7 版，新增“附属构筑物”分类
  （24 座检查井 + 单篦/双篦雨水口 + 排放口 + 自定义构筑物，共 27 个模板）；
  （2.0 未发布、无旧文件兼容负担；JSON 数据体结构版本见 `core/version.py` 的 `STN_FILE_VERSION`。）

## 与旧版的偏差（修正旧版缺陷）

拿到旧版 C# 程序的输出对拍时，下面这些条目会与旧版不一致，均为有意修正：

- **围护 / 支撑 / 止水公式的 ``width``**：旧版 `mscGroove.cal_Ecpnts` 传的是
  `D10E3(SizeB + t*2 + a*2 + workwidth*2)`——把米制的断面宽混进毫米的和里
  整体除 1000，断面宽被抹掉（同一程序里 `cal_groove` 挖方与 `cal_Fcpnts`
  特殊地基用的都是正确的 `SizeB + D10E3(…)`，三处只有这里漏了）。本版按挖方
  同一条槽底宽（`groove_width`，面宽原则选“沟槽总宽度”时取沟槽宽度表值）传入。
  影响面：公式里引用 ``width`` 的做法——钢板桩 / 横列板 / SMW工法桩 的 `ZA`、
  钻孔灌注桩 的 `ZA~ZD`，全部是**支撑**量（旧版普遍偏小：直埋管少算约一个管径，
  箱涵 / 管廊只有应有槽底宽的 1/4~1/3；实测 15%~87%）。围护量（F 类公式）不受
  影响——构件库里没有一条 F 公式用 ``width``；特殊地基本来就用的是正确值；
- **图集工作面宽度 / 沟槽宽度取值**：旧版 `GetWidthOrB` 恒读 WorkWidth 表
  （沟槽宽度表形同虚设）且把 mm 当 m 用，本版按字面语义查各自表并换算（默认
  取值模式下两者一致，见 `services/atlas.py` 模块说明）。

## 工程文件

- 扩展名 `.stn`：1.0 风格 XML 头 + `Section2` CDATA 包裹的 JSON 数据体；
  保存 = `commit`（把临时工作库整体写出为 `.stn`），无需手动存盘；
- 打开工程后首次修改、以及每次显式保存时，在工程同级 `Backup\` 下备份
  `<工程名>_yyMMdd_HHmmss.stn`，保留最近 20 份；
- 同一工程不允许双开（`<工程文件>.lock` 记录 pid 与时间，进程已退出时自动接管）；
- 旧 1.0 `.stn` 用 2.0 直接打开时自动转译：原文件备份到软件数据目录的
  `migration_backup\<工程名>_v<旧版本号>_<时间戳>.stn` 后一字节不动，转译结果
  处于临时工程状态（`文件 → 导入旧版工程(.stn)…` 向导则按所选路径写出新文件）；
  反过来，1.0 软件误打开 2.0 保存的 `.stn` 时，会读到头部的 `Assembly/Version`（2.0.0.0）
  并弹“正在打开的是高版本文件”提醒，不会崩溃。

## AI 助手

- `AI → AI 设置…`：配置 OpenAI 兼容端点（名称 / base_url / 默认模型 / 温度），
  API key 只写入系统钥匙串（条目 `section2/<名称>`），配置文件里永远没有 key；
- 一期工具：`list_elements` / `add_element` / `update_element` / `delete_element`，
  只作用于项目树里当前选中的单位工程；新增、修改、删除都会先弹确认窗，
  执行后工程量表自动刷新；
- **上传文件**（输入框左下角 📎）：支持 Excel（.xlsx/.xlsm/.xltx）、Word（.docx）、
  CSV / 文本 / JSON / XML / Markdown / `.stn`（PDF 需可选依赖 pypdf）。
  文件在本地提取为文本后挂到输入框上方的附件条（可单个移除）。带附件发送走
  两段式：先调一次模型按提示词把文件内容提炼成结构化数据（`services/ai/file_extract.py`
  负责本地提取，超长文件按 10 万字符截断），再把「提取数据 + 用户要求」一并交给
  带工具的代理去操作软件——提取数据保留在对话历史里，后续追问可直接引用。

## MCP 服务（M10）

全部功能已注册为 69 个 MCP 工具，外部 AI 客户端（Claude Desktop / Codex / Cursor /
Cline / VS Code / WorkBuddy…）可直接操作本软件：

- **主入口（GUI 内嵌）**：`AI → MCP 服务…` 启用，默认 `http://127.0.0.1:8765/mcp`，
  Bearer token 鉴权、仅本机回环；与界面共享工程会话，写操作在界面弹确认卡；
- **独立 CLI**：`section2-mcp`（stdio / 本地 HTTP / `--connect` stdio 桥 /
  `--project` headless 只读）；
- 与内置 AI 助手**共用同一套工具注册表**，业务代码只有一条路径；
- `[mcp] allow_actions=false` 只暴露只读工具，`require_confirmation` 控制写确认。

安装与客户端配置见 [docs/mcp.md](docs/mcp.md)，设计方案见
[docs/mcp_development_plan.md](docs/mcp_development_plan.md)。

```bash
.venv/Scripts/python.exe -m pip install -e ".[mcp]"   # 安装 MCP 依赖与 section2-mcp 入口
```

## 常见问题

**`ImportError: DLL load failed while importing QtCore: 找不到指定的程序`**

PySide6 的 `Qt6Core.dll` 依赖系统 `icuuc.dll`；如果 PATH 里有 Anaconda 的
`Library\bin`（其中的 icuuc.dll 缺少 Qt 需要的无版本号符号），就会加载失败。
`src/app/__init__.py` 里已经做了处理（导入 PySide6 前先按绝对路径加载系统 ICU），
所以只要通过 `src/app/main.py` 或 pytest（`tests/conftest.py`）启动即可。
自己写脚本时请先 `import app` 再 `import PySide6`。

## 开发进度

里程碑 M1~M4、M6~M9 已完成；M5 的汇总面板与 Excel 导出曾随旧版界面实现，
未接入现行界面，已移除（git 历史可找回），待重做。

对拍基准见 `tests/baselines/`：拿到旧版软件对同一算例的输出后，把数值填进
`tests/baselines/对拍工程.json` 即可进行新旧数值对拍（误差 < 0.5%）。

## 参考

- 初代源码（只读）：`section/section-master/section/`
- 技术栈与界面参照（只读）：`../Quotor/`
- 架构说明：`docs/architecture.md`
