# PySide6 导入失败：WinError 127 与 ICU DLL 解析问题

> 状态：**已定位并修复**（2026-10-30）。
> 本文记录 `.venv` 中 `import PySide6.QtWidgets` 报
> `DLL load failed while importing QtWidgets: 找不到指定的程序`（WinError 127）
> 的完整原因、排查证据与两种修复方式，供换机/重建环境时对照。

## 1. 现象

在项目根目录用项目虚拟环境执行：

```powershell
.venv\Scripts\python.exe -c "import PySide6.QtWidgets"
```

报错：

```
ImportError: DLL load failed while importing QtWidgets: 找不到指定的程序。
```

`from PySide6 import QtCore` / `QtGui` 同样失败；`import PySide6`（只加载包，不加载 Qt 扩展）正常。
而 `D:\anaconda3\python.exe` 里的 PyQt5 可以正常使用——说明环境本身没坏，是 **PySide6 的 Qt 依赖解析**出了问题。

## 2. 根因（通俗版）

Windows 加载 `Qt6Core.dll` 时先读它的"购物清单"（PE 导入表），发现要向 `icuuc.dll`
借 20 个函数：`ucnv_open`、`ucnv_close`、`ucnv_toUnicode`…… 然后按固定顺序去找
**任意一个叫 `icuuc.dll` 的文件**：模块自身目录 → 应用目录 → `C:\Windows\System32`
→ 当前目录 → `PATH` 里的目录。

找到文件只是第一步，**还要核对文件里是否真导出清单上的函数名**——找不到导出函数时，
Windows 报的正是 `ERROR_PROC_NOT_FOUND`，即 `WinError 127「找不到指定的程序」`
（注意：`WinError 126` 才是"找不到文件/模块"）。

本机命中的是 Anaconda 的 ICU：

| 文件 | 结果 |
|---|---|
| `D:\Anaconda3\Library\bin\icuuc.dll`（ICU 73，2.6 MB） | 导出名全部带版本后缀（`ucnv_open_73`），**缺无后缀的 `ucnv_open`** → 127 |
| `C:\Windows\System32\icuuc.dll`（36 KB 转发器，转发到 `icu.dll`，ICU 72.1） | 导出无后缀名，与 Qt 6.11 期望一致 → 可用 |

> PySide6 的 wheel **本身不带任何 ICU DLL**（RECORD 里只有数据文件
> `PySide6/resources/icudtl.dat`），它假定 Windows 提供 `icuuc.dll`（Win10 1903+ / Win11 均有）。

### 为什么"终端进程"会命中 Anaconda 的 ICU

`.venv` 是用 conda 的解释器创建的：

```
# .venv/pyvenv.cfg
home = d:\anaconda3
executable = D:\anaconda3\python.exe
command = d:\anaconda3\python.exe -m venv .venv
```

所以这个进程的 DLL 搜索路径里带着 Anaconda 的 `Library\bin`。**实测即使在进程内把
`PATH` 清到只剩 `C:\Windows\System32;C:\Windows`，`icuuc.dll` 仍解析到
`d:\anaconda3\Library\bin\icuuc.dll`**——不是 PATH 偶发问题，而是"conda 基础解释器"
这个组合自带的行为。用 PyCharm 启动时进程环境与之不同，可能恰好命中系统 ICU，于是出现
"IDE 能跑、终端不能跑"的差异。

## 3. 排查证据（可复现）

```powershell
# 1) 确认失败点：Qt6Core.dll 的依赖里有 icuuc.dll
#    （用自写 PE 导入表解析或 Dependencies 工具均可，结论：静态导入 20 个无后缀符号）

# 2) 裸名加载 icuuc.dll，看实际解析到哪个文件
.venv\Scripts\python.exe -c "import ctypes; k=ctypes.WinDLL('kernel32'); m=ctypes.WinDLL('icuuc.dll');
b=ctypes.create_unicode_buffer(1024); k.GetModuleFileNameW(ctypes.c_void_p(m._handle), b, 1024); print(b.value)"
# 输出：d:\anaconda3\Library\bin\icuuc.dll

# 3) 对照实验
.venv\Scripts\python.exe -c "import ctypes,os; ctypes.WinDLL(os.path.join(os.environ['SystemRoot'],'System32','icuuc.dll'));
from PySide6 import QtCore; print('OK')"     # → OK（系统 ICU 可满足 Qt）

.venv\Scripts\python.exe -c "import ctypes; ctypes.WinDLL(r'D:\Anaconda3\Library\bin\icuuc.dll');
from PySide6 import QtCore; print('OK')"     # → 仍报 127（Anaconda ICU 缺无后缀导出）

# 4) 把系统 ICU 放到 Qt DLL 旁边（Qt 依赖优先搜索自身目录）后即可导入
Copy-Item C:\Windows\System32\icuuc.dll .venv\Lib\site-packages\PySide6\icuuc.dll
.venv\Scripts\python.exe -c "from PySide6 import QtWidgets; print('OK')"
```

## 4. 修复方式 A：一次性补丁（应急）

```powershell
Copy-Item C:\Windows\System32\icuuc.dll .venv\Lib\site-packages\PySide6\icuuc.dll -Force
```

原理：Qt6Core 的依赖先在其自身目录（`site-packages\PySide6`）里查找，把兼容的
`icuuc.dll` 放在这里，就不再依赖进程搜索顺序。

缺点：

* 重装 / 升级 PySide6 会被覆盖，需要重新复制；
* 属于修改第三方包目录，换机器要重复操作；
* 依赖目标机是 Win10 1903+（`System32\icu.dll` 存在）。

## 5. 修复方式 B：用官方 Python 重建 venv（根治，推荐）

不要用 conda 的 python 建 venv。使用 **python.org 官方安装包**（3.12.x）：

```powershell
# 1) 安装官方 Python 3.12（用户级安装，无需管理员权限）
winget install --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements

# 2) 备份旧 venv（确认新环境无误后再删除）
Rename-Item .venv .venv-anaconda-bak

# 3) 用官方 Python 重建 venv（路径按实际安装位置调整）
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv

# 4) 安装依赖
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 5) 验证：此时 PySide6 目录下不应再有手工复制的 icuuc.dll
.venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')"
```

PyCharm / Trae 的 Python 解释器需要重新指向新的 `.venv`（重新选一次解释器即可）。

## 5.1 本机实施记录（2026-10-30）

按方式 B 已在本机完成切换，实测数据如下：

| 项目 | 结果 |
|---|---|
| 官方解释器 | Python **3.12.10**，`%LOCALAPPDATA%\Programs\Python\Python312`（winget `--scope user` 安装） |
| 依赖安装 | `pip install -r requirements.txt` 全部成功（PySide6 6.11.2 / shiboken6 6.11.2 等版本与快照一致） |
| 无补丁导入 | 新 venv 的 `site-packages\PySide6` 下**没有任何** `icuuc.dll`，`from PySide6.QtWidgets import QApplication` 直接成功 |
| ICU 解析 | 裸名 `icuuc.dll` 解析到 `C:\WINDOWS\SYSTEM32\icuuc.dll`（不再是 Anaconda 的） |
| 测试 | `pytest tests` → **400 passed**（进程退出码 `-1073741819`/`0xC0000005` 偶发出现于解释器退出阶段，单文件运行退出码为 0，用例本身全过） |
| 目录切换 | `.venv` → `.venv-anaconda-bak`，新环境改名为 `.venv`；确认无误后可删除旧目录 |

`.gitignore` 已增加 `.venv-*/`，备份目录不会进仓库。

> IDE（PyCharm / Trae）如仍显示旧的解释器信息，重新选择一次 `.venv\Scripts\python.exe` 即可。

## 6. 验证清单

```powershell
.venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; print('import ok')"
.venv\Scripts\python.exe -m pytest tests -q          # 项目全量用例
.venv\Scripts\python.exe src\app\main.py             # 应用可启动
```

## 7. 打包 / 分发注意

`section2.spec` 用 PyInstaller 打包，`Qt6Core.dll` 对 `icuuc.dll` 是**静态依赖**：

* 用官方 Python 环境构建，PyInstaller 会从 System32 解析依赖，产物在 Win10 1903+ / Win11 上正常；
* 若目标机是 Win7/8/2012 等没有系统 `icuuc.dll` 的系统，会变成"找不到模块"（126）——
  需要随包附带一份 ICU（真实 ICU DLL 而不仅是 36 KB 转发器）；
* 反过来，**千万不要在 conda 环境里打包**：PyInstaller 可能把 Anaconda 那份带后缀导出的
  `icuuc.dll` 收进 `dist`，产物换台机器一样报 127。

## 8. 速查表

| 错误码 | 含义 | 典型原因 |
|---|---|---|
| 126 | 找不到指定的模块 | 依赖 DLL 文件不存在（路径/架构不对） |
| 127 | 找不到指定的程序 | DLL 找到了，但缺少所需导出函数（版本不匹配） |
| 193 | 不是有效的 Win32 应用程序 | 32/64 位不匹配 |

| 现象 | 判断 |
|---|---|
| IDE 能运行、终端导入失败 | 两个进程的 DLL 搜索环境不同，比对 `icuuc.dll` 的实际解析路径 |
| `import PySide6` 正常、`QtCore` 失败 | 一定是 Qt 的某个 DLL 依赖解析问题（本文件即此案） |
