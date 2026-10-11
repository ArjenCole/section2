# 无边框窗体自绘圆角与外阴影实现指南（PySide6 / Windows）

本文记录 Section 2.0 在 Windows 上为无边框窗体实现圆角、描边、外阴影、圆角菜单
的完整方案，供其他项目参照开发。所有代码可直接复制；本项目落地位置见文末索引。

- **效果**：窗体（主窗体 + 一切弹窗）四角 8px 抗锯齿圆角、1px 描边、向外渐隐
  20px 的柔和投影；下拉/右键菜单四角真圆角；外观在 Win10 / Win11 完全一致，
  不依赖系统版本（Win11 的 DWM 圆角、macOS 原生圆角之外的自给自足方案）。
- **平台**：Windows 10/11（Linux X11 理论可用，未充分测试）；**macOS 不要用**，
  走原生标题栏 + 系统圆角（NSWindow 自带，无需任何本文技术）。
- **依赖**：PySide6 ≥ 6.6（注意避开 6.12.0，见 §7）。

## 1. 方案总览

| 能力 | 机制 | 一句话原理 |
|---|---|---|
| 圆角轮廓 | 贴角子控件 QSS `border-radius` | 背景沿圆角路径抗锯齿填充，轮廓由子控件自己画 |
| 圆角背景真正裁剪 | 规则里**必须带 border**（1px 透明即可） | Qt 的 QSS 背景裁剪走 border 盒子路径，无 border 一律方角填充 |
| 1px 窗体描边 | 置顶、鼠标穿透的 overlay 子控件 | 沿同一圆角路径画抗锯齿描边，兼作窗体轮廓线 |
| 外阴影 | 影子窗口（贴在宿主正后方的透明 Tool 窗口） | 沿圆角路径由内向外多圈描边，透明度二次衰减 |
| 影子不挡鼠标 | `WA_TransparentForMouseEvents` + 不接受焦点 | 纯视觉层 |
| 最大化退化 | 窗体级样式表压平子控件圆角 + 隐藏影子 | 与系统行为一致，还原自动恢复 |
| 圆角菜单 | 菜单首次 polish 时开透明 + 无边框 + 关系统阴影 | 让 QSS 圆角成为菜单的真实窗口轮廓 |

## 2. 落选方案与踩坑结论（为什么是这套）

| 备选方案 | 结论 | 原因 |
|---|---|---|
| `setMask` 圆角区域 | **弃用** | mask 是 1-bit 系统级裁剪，边缘锯齿明显；描边圈盖不住从锯齿缺口透出的阴影。曾长期使用，最终整体移除 |
| `QGraphicsDropShadowEffect` | 不可用 | Qt 的 GraphicsEffect 对顶层窗口无效，套在内容容器上需要改布局且性能差 |
| 窗体内缩一圈、窗体内画阴影 | 不可行 | `QMainWindow` 的布局**忽略 `setContentsMargins`**（实测 central/statusbar 仍顶格），主窗体内容无法整体缩进 |
| DWM 系统圆角（`DWMWA_WINDOW_CORNER_PREFERENCE`） | 仅 Win11 | 属性 33 是 Win11（build 22000）引入，Win10 返回 `E_INVALIDARG`；本项目保留该调用作为 Win11 兜底，但不依赖它 |
| QSS `border-radius` 直接给窗体 | 不够 | QSS 背景的圆角裁剪需要规则带 border（见 §3.2），且裸窗体方案管不住所有贴角子控件 |

关键教训：**先在小程序里验证前提，再写方案**。本项目"窗体内缩画阴影"方案就是
没先验证 QMainWindow 边距行为、写完才发现走不通的。

## 3. 圆角实现

### 3.1 窗体准备

```python
window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
```

两个必须处理的配套点：

1. **顶层窗体命中的全局 QSS 背景**（如 `QWidget { background-color: ... }`、
   `QMainWindow/QDialog {...}`）会把整个矩形填成实心、露出方角。给窗体设
   objectName 后用窗体级样式表 + ID 选择器精确关掉（窗体级样式表优先于应用级）：

   ```python
   window.setObjectName("RoundedWindowRoot")
   base = "QMainWindow" if isinstance(window, QMainWindow) else "QDialog"
   window.setStyleSheet(f"{base}#RoundedWindowRoot {{ background: transparent; }}")
   ```

   注意选择器必须带 ID 限定：裸的 `QDialog { background: transparent }` 会连
   窗体内的子 QDialog（如内嵌 QWizard）一起变透明。

2. **圆角轮廓由贴角的子控件负责**，规则里必须显式给出半径（见 §3.2）。

### 3.2 贴角子控件的 QSS 圆角 —— 最重要的坑

**Qt 的 QSS 背景只有在规则带 border 时才按 border-radius 裁剪**；没有 border
的规则，`background-color` 一律方角填充，`border-radius` 形同虚设。这一条
Worker 了整个方案的根基，逐像素实测确认（验证方法见 §7）：

```css
/* 方角！即使写了 border-radius */
#Bad  { background-color: #EF4444; border-top-right-radius: 8px; }

/* 圆角 ✓ 1px 透明 border 激活圆角盒子路径 */
#Good { background-color: #EF4444; border-top-right-radius: 8px;
        border: 1px solid transparent; }
```

由此，窗体上所有贴角的子控件按下面方式写规则（半径与描边圈的 `_RADIUS` 保持
一致，本项目取 8px）：

```css
/* 标题栏：顶在窗体上沿（主窗体与弹窗通用），只带 border-bottom 也足以激活裁剪 */
QFrame#FramelessTitleBar {
    background-color: $bg_card;
    border-bottom: 1px solid $border;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}

/* 弹窗内容区：顶满 body，底两角倒圆 */
QDialog #FramelessDialogBody {
    background-color: $bg_dialog;
    border: 1px solid transparent;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}

/* 内嵌 QWizard（齐边充满 body 时必须自己倒圆） */
QWizard {
    border: 1px solid transparent;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}

/* 主窗体状态栏：底两角；border-top 保留原有的分隔线 */
QStatusBar {
    background-color: $bg_card;
    border: 1px solid transparent;
    border-top: 1px solid $border;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}
```

**接入前审计**：列出所有会触及窗体四角弧线区域（半径 px 以内）的子控件，
逐一确认它的背景规则有 border + 对应圆角。直边（左右两条边的中段）不用管——
直边与窗体矩形重合，天然无锯齿。本项目审计结论：各弹窗 body 四周边距 ≥10px，
弧线区域内没有子控件；唯一齐边的是向导内嵌 QWizard。

**主窗体结构对应关系**：标题栏经 `setMenuWidget()` 顶在上方（管上两角）、
状态栏 `QStatusBar` 顶在下方（管下两角）、central widget 的角都在直边中段
（无需处理）。弹窗 = 自绘标题栏（上两角）+ body（下两角）。

### 3.3 描边圈 overlay

```python
class _RingWidget(QWidget):
    """置顶 overlay：只画 1px 抗锯齿圆角边框圈，鼠标穿透。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # 全局 QSS 的 QWidget 背景规则会把它填成实心盖住窗口，这里关掉
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(theme.border), 1))   # 颜色随主题（theme_changed 时 update）
        painter.drawPath(_rounded_path(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), _RADIUS))
```

作用有二：充当 1px 窗体描边（对应 Win11 DWM 系统圆角自带的轮廓线）；盖住
QSS 圆角边缘与阴影衔接处的细缝。它在宿主 Show/Resize 时 `raise_()` 保持置顶。

### 3.4 最大化退化

与系统行为一致：最大化时直角、贴边。此时**不能**用 `setMask` 清空的老套路
（mask 已移除），改为用窗体级样式表压平贴角子控件的圆角——widget 级样式表
对同选择器规则优先于应用级，直接覆盖：

```python
_SQUARE_CORNERS_SHEET = (
    "QFrame#FramelessTitleBar, QDialog #FramelessDialogBody, QWizard, QStatusBar "
    "{ border-radius: 0px; }"
)

def _apply(self) -> None:
    squared = window.isMaximized()
    if squared != self._squared:                       # 状态变化才重设样式表
        self._squared = squared
        window.setStyleSheet(self._base_sheet + _SQUARE_CORNERS_SHEET
                             if squared else self._base_sheet)
    ...
```

`WindowStateChange` 事件必须监听：离屏平台/同尺寸最大化只发状态变化、不发
Resize，漏掉会导致最大化后仍是圆角。

## 4. 外阴影：影子窗口

**选型**：把阴影画在一个贴在宿主正后方的独立透明窗口里（业界成熟做法），
而不是画进宿主窗体——后者要求内容缩进留白，主窗体做不到（§2）；前者对宿主
内容几何零侵入，主窗体与弹窗通用。

### 4.1 结构

```python
class _ShadowWindow(QWidget):
    def __init__(self, host: QWidget) -> None:
        super().__init__(None,
            Qt.WindowType.Tool                      # 不进任务栏
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus  # 不抢焦点
            | Qt.WindowType.NoDropShadowWindowHint)   # 关掉系统方角阴影
        self._host = host
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # 输入穿透
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
```

注意：影子窗口是**独立顶层窗口**，不能设 widget 父对象（会把顶层降级为子控
件）。生命周期挂靠：`helper.destroyed.connect(shadow.deleteLater)`。

### 4.2 渲染：同心描边 + 二次衰减 + 位图缓存

影子窗口尺寸 = 宿主 `frameGeometry()` 向四周各扩 `_SHADOW_MARGIN`（20px）。
**宿主轮廓在影子窗口坐标系里是四周缩进 margin 的圆角矩形**——坐标基准千万
别再外扩（本项目曾因此把阴影画到右上/左下两个错误方向上）。

```python
def _render(self, dpr: float) -> None:
    w, h, m = self.width(), self.height(), _SHADOW_MARGIN
    pixmap = QPixmap(round(w * dpr), round(h * dpr))     # 画布 = 影子窗口本身
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    host = QRectF(m, m, w - 2.0 * m, h - 2.0 * m)        # 宿主轮廓
    for i in range(m):                                   # i = 距宿主边缘的距离
        t = i / m
        alpha = int(_SHADOW_ALPHA * (1.0 - t) ** 2)      # 贴边最深，向外二次衰减
        painter.setPen(QPen(QColor(0, 0, 0, alpha), 1.5))
        painter.drawPath(_rounded_path(
            host.adjusted(-i - 0.5, -i - 0.5, i + 0.5, i + 0.5),
            _RADIUS + i))                                # 外偏的圆角半径同步变大
    painter.end()
    self._cache = pixmap                                 # 按尺寸+DPR 缓存，仅 resize 重绘
```

描边圈内半幅压在宿主底下不可见，无副作用。参数经验值：margin 20、最深
alpha 60（≈24%）、1.5px 笔宽逐像素步进，视觉上与系统阴影接近。

### 4.3 同步与 z 序

在宿主上装事件过滤器，统一驱动圆角与影子：

| 宿主事件 | 动作 |
|---|---|
| Show / Resize / Move | 影子 `setGeometry(host.frameGeometry().adjusted(-m, -m, m, m))`；Show 后把影子插回宿主正下方 |
| WindowStateChange | 最大化/最小化 → 影子隐藏；还原 → 恢复 |
| Hide / Close | 影子隐藏 |
| ActivationChange / ZOrderChange | 影子重新插回宿主正下方（宿主被其他窗口抬起后影子不许浮到上面） |

z 序用 Win32 API 精确控制（Qt 的 `raise_/lower/stackUnder` 对跨顶层窗口不够用）：

```python
import ctypes
SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE = 0x0001 | 0x0002 | 0x0010
ctypes.windll.user32.SetWindowPos(
    int(shadow.winId()), int(host.winId()), 0, 0, 0, 0,
    SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)   # 插到宿主 HWND 正后方
```

拖动期间 Move 事件逐帧同步影子位置，实测无可感知延迟。

### 4.4 已知代价

影子窗口矩形范围内的点击会落在宿主上（输入穿透挡不住"落在影子窗口自身"的
点击，只能保证不抢焦点）。窗口边缘 20px 内若有需要点穿到其他程序的场景，
需自行评估；本项目场景可接受。

## 5. 菜单圆角

Win10 的 QMenu 弹出窗是**不透明矩形窗口**：QSS 画的 `border-radius` 外面露出
调色板底色的方角落，左下角再叠上系统菜单阴影，非常扎眼。修法是在菜单首次
polish（尚未创建原生窗口，属性才能生效）时改造它：

```python
def apply_menu_rounding(menu: QMenu) -> None:
    menu.setWindowFlags(menu.windowFlags()
                        | Qt.WindowType.FramelessWindowHint
                        | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


class _MenuRounding(QObject):
    def eventFilter(self, obj, event) -> bool:
        if (isinstance(obj, QMenu) and event.type() == QEvent.Type.Polish
                and not obj.isVisible()):
            apply_menu_rounding(obj)
        return False


def install_menu_rounding(app) -> None:
    app.installEventFilter(_MenuRounding(app))     # main() 里装一次，全局生效
```

菜单栏下拉、各级子菜单、右键菜单都经 `Polish`，一个过滤器全覆盖。前提是
QSS 里 QMenu 本身就有 `border-radius` + `border`（本项目 8px + 1px 实色边），
透明化之后圆角即真实轮廓。副作用：菜单失去系统原生阴影（它正是方角感的来源
之一），如需要可另画轻量投影。

## 6. 相关的平台坑速查

| 坑 | 现象 | 处置 |
|---|---|---|
| QSizeGrip 方角贴片 | 主窗体右下角"直角" | QMainWindow 状态栏自带 16×16 手柄压在圆角上；边缘缩放走 `WM_NCHITTEST` 时直接 `statusBar().setSizeGripEnabled(False)` |
| 关闭按钮悬停背景方角 | 红色悬停块探出窗体圆角 | 贴角的按钮规则同样要 border + 圆角（§3.2），悬停/按下背景才会被裁 |
| QSS 背景不裁圆角 | 写了 border-radius 仍是方角 | 规则必须带 border（§3.2），1px transparent 即可 |
| QMainWindow 忽略布局边距 | `layout().setContentsMargins()` 不生效 | 它的内部布局自行排布 menuWidget/central/statusbar；别指望用它缩进内容 |
| PySide6 6.12.0 QSpinBox 回归 | QSS 带 border/padding 时 spinbox 内嵌编辑区被压成 1px，数字不可见（6.8~6.11 正常） | 依赖钉 `PySide6>=6.6,<6.7`（本项目取 6.6 系列），等 Qt 修复再放开 |
| 顶层不透明窗口的像素测量陷阱 | grab()/截屏判读圆角被窗口表面填充误导 | 测量必须在**透明窗体 + 子控件**的真实结构上做，或直接量屏幕合成结果（见 §7） |

## 7. 验证方法论

改完必须逐像素验证，肉眼在缩略图上极易被描边圈和阴影"骗"出圆角感：

1. **像素探针**：`QGuiApplication.primaryScreen().grabWindow(0)` 截整屏，按
   `frameGeometry() * devicePixelRatio()` 裁出窗体，沿四个角的对角线各采样
   5~6 个像素——合格判据：角点=桌面/影子色，弧线内侧=背景色，中间是 AA 混合，
   且四条边模式一致。
2. **逐边渐变方向**（阴影）：对渲染出的阴影位图逐边断言"贴边像素 alpha >
   远处像素 alpha"，防止方向画反。
3. **最近邻放大**（`QImage.scaled(n*zoom, n*zoom)`，默认 FastTransformation
   即最近邻）人工目检四角，6~8 倍。
4. **陷阱**：不要拿顶层不透明窗口做背景圆角测试——顶层窗口表面会被规则背景
   整面填充，圆角裁剪与否看不出来；要么用"透明窗体 + 子控件"的真实结构 +
   屏幕截图，要么直接在真实应用上量。
5. 回归防护进 pytest：离屏平台下断言样式表状态（圆角/压平片段）、影子几何
   与显隐、渲染缓存尺寸与渐变方向。

## 8. 移植清单（其他项目接入步骤）

1. 复制 `rounded_window.py`（本文 §3.3/§3.4/§4/§5 的完整实现，单文件、仅依赖
   PySide6 + 自己的主题接口）。
2. QSS 增加贴角子控件规则（§3.2），半径与 `_RADIUS` 对齐；确认全局 `*`/`QWidget`
   背景规则的存在，准备 ID 选择器中和片段（§3.1）。
3. 每个无边框窗体（主窗体与弹窗基类）的非 mac 分支调用
   `RoundedWindowHelper.install(self)`；mac 分支保持原生窗口。
4. `main()` 里 `install_menu_rounding(app)`。
5. 状态栏关尺寸手柄；审计贴角控件（§3.2 审计方法）。
6. 按 §7 验证；把 §7.5 的断言加进测试。

## 9. 本项目实现位置索引

| 内容 | 位置 |
|---|---|
| 助手/描边圈/影子/菜单修整 | `src/app/views/widgets/rounded_window.py` |
| 接入点（弹窗基类） | `src/app/views/widgets/frameless_dialog.py`（`FramelessDialog.__init__` 非 mac 分支） |
| 接入点（主窗体） | `src/app/views/main_window.py`（`MainWindow.__init__` 非 mac 分支） |
| 贴角子控件 QSS | `src/app/resources/qss/theme.py`（搜 `FramelessTitleBar` / `FramelessDialogBody` / `QWizard` / `QStatusBar` / `WindowBtn`） |
| 菜单修整安装 | `src/app/main.py`（`install_menu_rounding(app)`） |
| 边缘缩放（NCHITTEST） | `src/app/views/main_window.py`（`nativeEvent`） |
| 回归测试 | `tests/test_rounded_window.py` |
| 依赖钉版（QSpinBox 回归） | `pyproject.toml`（`PySide6>=6.6,<6.7`） |
