# Section 2.0

线性工程（市政管道等）工程量计算软件 **section** 的 Python 重写版，跨平台（Windows / macOS / Linux）。

初代是 C# WinForms 程序（最终版参照 `section/section-master`，只读参考）。2.0 复刻其全部功能，并新增：

- **计算表达式输出**：每个工程量除了结果，还给出一条数值代入的算式，例如
  `(1.99+1.99+2×2.995×1)×2.995/2×120.5 = 1799.074`；
  算式与结果共用同一套数值，双击表格可查看中间步骤；
- **AI 助手面板**（`Ctrl+L`）：流式对话 + 工具调用（一期为构件条目增删改查 4 个工具，
  写操作一律弹确认窗），支持任意 OpenAI 兼容端点（DeepSeek / OpenAI / Ollama / vLLM / 通义…）；
- **旧工程一次性迁移**：`文件 → 导入旧版工程(.stn)…`，把老 `.stn` 数据单向导入 `.stn2`，
  带解析摘要、原则补齐警告与可复制的迁移报告。

新版工程文件为单文件 SQLite：**`.stn2`**（提交即落盘 = 自动保存，带 `.lock` 防双开与 Backup 自动备份）。

## 功能总览（里程碑 M1~M9）

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 骨架 | 三栏单窗体（无边框自绘标题栏）、light/dark 主题 | ✅ |
| M2 数据层 | `.stn2`（单文件 SQLite）、自动保存、锁、备份、新建向导、项目树、录入表格（算式求值） | ✅ |
| M3 原则与图集 | 图集 xlsx 加载查询、构件库、6 个原则编辑器（围护/地基/做法/构件公式/工作面宽度/降水）、多围护/多地基原则引用（按比例） | ✅ |
| M4 计算引擎 | 沟槽土方/回填、管道基础、降水、围护与特殊地基公式、表达式记录器、对拍测试 | ✅ |
| M5 导出与汇总 | 汇总面板（量×单价=合价、单价可编辑、批量载价）、定额/清单双表 Excel 导出（含表达式列） | ⏳ 曾随旧版界面实现，未接入现行界面，已移除待重做 |
| M6 旧工程迁移 | 旧 `.stn` XML 解析、原则重建、容错报告，全部样例工程批量导入测试 | ✅ |
| M7 AI 对话 | AI 设置（keyring 存 key）、SSE 流式对话、思考过程折叠 | ✅ |
| M8 AI 工具 | 构件条目增删改查 4 个工具 + 确认弹窗 + 自动刷新 | ✅ |
| M9 发布 | 全量回归、PyInstaller 打 Windows 包 | ✅ |

## 技术栈

| 项 | 选型 |
|---|---|
| Python | 3.12+（项目内 `.venv`） |
| 界面 | PySide6 (Qt6)，MVVM + EventBus，无边框自绘标题栏 |
| 架构 | `views/ → viewmodels/ → services/ → core/models/`（src 布局） |
| 工程文件 | `.stn2` 单文件 SQLite（SQLAlchemy 2.0 ORM） |
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
│   ├── models/        .stn2 表结构（base.py 管连接与 meta，models.py 管表）
│   └── calc/          计算引擎：groove / foundation / precipitation / engine / tracer
├── services/          工程文件读写、图集与构件库、旧档迁移
│   └── ai/            ai_provider（SSE 流式）、ai_keychain（keyring）
├── viewmodels/        MVVM 视图模型
├── views/             主窗体（含无边框标题栏）、三栏面板、对话框、新建/导入向导
├── agent/             AI 工具调用（tool_registry / agent_loop / confirm_policy / tools）
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
.venv/Scripts/python.exe src/app/main.py "D:\工程\某项目.stn2"

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
多围护原则 / 多地基原则」参数面板）；右栏 AI 助手（`Ctrl+L` 折叠）。
`Ctrl+Shift+T` 切换亮/暗主题。

## 多原则引用与附属构筑物（对齐 section-master）

- **多围护原则 / 多地基原则**：主表格“沟槽围护原则 / 地基处理原则”列除具体原则外，
  还可选“多围护原则 / 多地基原则”——一个构件按比例引用多条原则（旧版 PEname 字典）。
  选中后左下「管材 / 构件参数」面板自动切到对应 Tab：每行 = 原则名称（下拉）+ 比例
  （可写算式），围护 Tab 另有“主要原则”下拉（沟槽回填材质命名、管道基础、支撑按主要
  原则计算）。计算时断面量 = Σ(各 pe×pf 组合量 × 比例)，与旧版 mscGroove.Cal 一致；
- **附属构筑物（构筑物类）**：检查井、雨水口、排放口等不参与沟槽计算的计数构件，
  单位“个”。工程量直接来自构件参数表（键本身即“构筑物|垫层|m3”这类定额键，
  值可写算式），并自动按 `井筒方量 = 个数 × max(埋深−井高, 0.4) × 每米方量` 追加
  “构筑物|井筒|m3”；参数行可增删改（“-名称 / -单位”两个键锁定）；
- **构件库**：已随 section-master 更新到 1.3.2.7 版，新增“附属构筑物”分类
  （24 座检查井 + 单篦/双篦雨水口 + 排放口 + 自定义构筑物，共 27 个模板）；
  工程文件结构版本升至 v3（旧 .stn2 打开时自动迁移：单原则引用补成比例 1 的引用行）。

## 工程文件

- 扩展名 `.stn2`，本质是一个 SQLite 库；保存 = `commit`，无需手动存盘；
- 打开工程后首次修改、以及每次显式保存时，在工程同级 `Backup\` 下备份
  `<工程名>_yyMMdd_HHmmss.stn2`，保留最近 20 份；
- 同一工程不允许双开（`<工程文件>.lock` 记录 pid 与时间，进程已退出时自动接管）；
- 旧 `.stn` 只在 `文件 → 导入旧版工程(.stn)…` 时被读取一次，绝不写回旧格式。

## AI 助手

- `AI → AI 设置…`：配置 OpenAI 兼容端点（名称 / base_url / 默认模型 / 温度），
  API key 只写入系统钥匙串（条目 `section2/<名称>`），配置文件里永远没有 key；
- 一期工具：`list_elements` / `add_element` / `update_element` / `delete_element`，
  只作用于项目树里当前选中的单位工程；新增、修改、删除都会先弹确认窗，
  执行后工程量表自动刷新。

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
