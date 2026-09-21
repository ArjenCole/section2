# Section 2.0

线性工程（市政管道等）工程量计算软件 **section** 的 Python 重写版，跨平台（Windows / macOS / Linux）。

初代是 C# WinForms 程序（最后快照 `section 1.2.2.171220_beta`，只读参考）。2.0 复刻其全部功能，并新增：

- **计算表达式输出**：每个工程量除了结果，还给出一条数值代入的算式（如
  `(1.20+1.20+2×2.85×0.5)×2.85/2×100.0 = 583.1`）；
- **AI 助手面板**：对话 + 工具调用（一期为构件条目增删改查），模型由用户自配 OpenAI 兼容端点；
- **旧工程一次性迁移**：`文件 → 导入旧版工程(.stn)…`，把老 `.stn` 数据单向导入 `.stn2`。

新版工程文件为单文件 SQLite：**`.stn2`**（提交即落盘 = 自动保存，带 `.lock` 防双开与 Backup 自动备份）。

## 技术栈

| 项 | 选型 |
|---|---|
| Python | 3.12+（项目内 `.venv`） |
| 界面 | PySide6 (Qt6)，MVVM + EventBus |
| 架构 | `views/ → viewmodels/ → services/ → orm/` |
| 工程文件 | `.stn2` 单文件 SQLite（SQLAlchemy 2.0 ORM） |
| 算式求值 | simpleeval（白名单运算符，禁任意函数调用） |
| 图集数据 | xlsx + openpyxl（只读） |
| Excel 导出 | openpyxl |
| 旧档迁移 | lxml（只读解析旧 `.stn` XML） |
| AI | httpx + OpenAI 兼容端点（SSE 流式），API key 存 keyring |
| 配置 | platformdirs + `config.toml`（与工程文件严格分离） |
| 打包 | PyInstaller |

## 目录结构

```
app/
├── main.py            入口：QApplication、主题、主窗体、启动参数
├── core/              版本、路径、配置、事件总线、算式求值
├── orm/               .stn2 表结构（base.py 管连接与 meta，models.py 管表）
├── services/          工程文件读写、图集、计算引擎、Excel 导出、AI
├── viewmodels/        MVVM 视图模型
├── views/             主窗体、三栏面板、对话框、新建向导
├── agent/             AI 助手工具调用
└── resources/         QSS 主题、图标、字体、图集 xlsx
tests/                 单元测试（工程文件、算式求值、计算对拍）
```

## 运行方式

```bash
# 1. 建虚拟环境（项目根目录下）
py -3.12 -m venv .venv

# 2. 安装依赖（含开发依赖）
.venv/Scripts/python.exe -m pip install -e ".[dev]"      # Windows
# .venv/bin/python -m pip install -e ".[dev]"            # macOS / Linux

# 3. 启动
.venv/Scripts/python.exe app/main.py
# 也可直接带工程文件启动
.venv/Scripts/python.exe app/main.py "D:\工程\某项目.stn2"

# 4. 跑测试
.venv/Scripts/python.exe -m pytest
```

界面速查：左栏项目树（工程 → 标段 → 单位工程），中部显示当前选中节点的内容
（单位工程工作台 / 原则编辑器 / 汇总），右栏 AI 助手（`Ctrl+L` 折叠）。
`Ctrl+Shift+T` 切换亮/暗主题。

## 常见问题

**`ImportError: DLL load failed while importing QtCore: 找不到指定的程序`**

PySide6 的 `Qt6Core.dll` 依赖系统 `icuuc.dll`；如果 PATH 里有 Anaconda 的
`Library\bin`（其中的 icuuc.dll 缺少 Qt 需要的无版本号符号），就会加载失败。
`app/__init__.py` 里已经做了处理（导入 PySide6 前先按绝对路径加载系统 ICU），
所以只要通过 `app/main.py` 或 pytest（`tests/conftest.py`）启动即可。
自己写脚本时请先 `import app` 再 `import PySide6`。

## 工程文件

- 扩展名 `.stn2`，本质是一个 SQLite 库；保存 = `commit`，无需手动存盘；
- 打开工程后首次修改、以及每次显式保存时，在工程同级 `Backup\` 下备份
  `<工程名>_yyMMdd_HHmmss.stn2`，保留最近 20 份；
- 同一工程不允许双开（`<工程文件>.lock` 记录 pid 与时间，进程已退出时自动接管）。

## 开发计划

任务、数据模型、验收标准见 [开发计划.md](开发计划.md)（里程碑 M1~M9）。

当前进度：M1 骨架、M2 数据层与工程文件已完成。

## 参考

- 初代源码（只读）：`section/section1.2.2.171220_beta/section/`
- 技术栈与界面参照（只读）：`../Quotor/`
