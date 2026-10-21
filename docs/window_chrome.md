# 无边框窗体自绘圆角与外阴影实现指南（PySide6 / Windows）

本文记录 Section 2.0 在 Windows 上为无边框窗体实现圆角、描边、外阴影、圆角
弹出层（菜单与下拉列表）的完整方案，供其他项目参照开发。所有代码可直接复制；本项目落地位置见文末索引。

- **效果**：窗体（主窗体 + 一切弹窗）四角 8px 抗锯齿圆角、1px 描边、向外渐隐
  36px（下缘 48px）的柔和投影；下拉/右键菜单四角真圆角；外观在 Win10 / Win11
  完全一致——不使用 Win11 DWM 原生圆角，也不使用系统阴影，圆角/阴影全部自绘。
  macOS 是唯一例外：走原生标题栏 + 系统圆角（NSWindow 自带，无需本文技术）。
- **平台**：Windows 10/11（Linux X11 理论可用，未充分测试）；**macOS 不要用**
  本文的自绘方案，走原生标题栏 + 系统圆角。
- **依赖**：PySide6 ≥ 6.6（注意避开 6.12.0，见 §7）。

## 1. 方案总览

| 能力 | 机制 | 一句话原理 |
|---|---|---|
| 圆角轮廓 | 贴角子控件 QSS `border-radius` | 背景沿圆角路径抗锯齿填充，轮廓由子控件自己画 |
| 圆角背景真正裁剪 | 规则里**必须带 border**（1px 透明即可） | Qt 的 QSS 背景裁剪走 border 盒子路径，无 border 一律方角填充 |
| 1px 窗体描边 | 置顶、鼠标穿透的 overlay 子控件 | 沿同一圆角路径画抗锯齿描边，兼作窗体轮廓线 |
| 外阴影 | 影子窗口（贴在宿主正后方的透明 Tool 窗口） | 核心填充 + 环带指数渐隐，整体下移并加强下缘 |
| 影子不挡鼠标 | `WA_TransparentForMouseEvents` + 不接受焦点 | 纯视觉层 |
| 最大化退化 | 窗体级样式表压平子控件圆角 + 隐藏影子 | 与系统行为一致，还原自动恢复 |
| 圆角弹出层（菜单/下拉列表） | 首次 polish 时开透明 + 无边框 + 关系统阴影 | 让 QSS 圆角成为弹出层的真实窗口轮廓 |

## 2. 落选方案与踩坑结论（为什么是这套）

| 备选方案 | 结论 | 原因 |
|---|---|---|
| `setMask` 圆角区域 | **弃用** | mask 是 1-bit 系统级裁剪，边缘锯齿明显；描边圈盖不住从锯齿缺口透出的阴影。曾长期使用，最终整体移除 |
| `QGraphicsDropShadowEffect` | 不可用 | Qt 的 GraphicsEffect 对顶层窗口无效，套在内容容器上需要改布局且性能差 |
| 窗体内缩一圈、窗体内画阴影 | 不可行 | `QMainWindow` 的布局**忽略 `setContentsMargins`**（实测 central/statusbar 仍顶格），主窗体内容无法整体缩进 |
| DWM 系统圆角（`DWMWA_WINDOW_CORNER_PREFERENCE`） | **已移除** | 属性 33 仅 Win11 有效，且与 QSS 自绘圆角叠加会形成两套轮廓；Win10 没有该效果。现在宿主/菜单均保持 `WS_POPUP` + DWM 非客户区渲染关闭，圆角/阴影完全自绘 |
| QSS `border-radius` 直接给窗体 | 不够 | QSS 背景的圆角裁剪需要规则带 border（见 §3.2），且裸窗体方案管不住所有贴角子控件 |

关键教训：**先在小程序里验证前提，再写方案**。本项目"窗体内缩画阴影"方案就是
没先验证 QMainWindow 边距行为、写完才发现走不通的。

## 3. 圆角实现

### 3.1 窗体准备

```python
window.setWindowFlags(
    Qt.WindowType.Window
    | Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.NoDropShadowWindowHint   # 禁止系统投影，阴影由影子窗口自绘
)
window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
```

**不要调用 `DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)`**：
那是 Win11 的第二套系统圆角，和 QSS 自绘圆角叠加会出现双轮廓，Win10 上又完全
没有该效果，正是跨版本不一致的来源。去掉后窗口仍是 `WS_POPUP`、DWM 非客户区
渲染关闭（本机实测 `DwmGetWindowAttribute(DWMWA_NCRENDERING_ENABLED)=0`），
系统不会参与圆角或阴影；`RoundedWindowHelper.install()` 还会统一补上
`NoDropShadowWindowHint`，防止宿主或菜单被 DWM 额外加一层阴影。

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
对同选择器规则优先于应用级，直接覆盖。**选择器必须用 `QMainWindow >` 直接
子选择器限定**（原因见 §3.5）：

```python
_SQUARE_CORNERS_SHEET = (
    "QMainWindow > QFrame#FramelessTitleBar, QMainWindow > QStatusBar "
    "{ border-radius: 0px; }"
)

def _apply(self) -> None:
    # 最大化判定只对主窗体生效：QDialog 作为最大化的 QMainWindow 的 owned
    # 窗口时 isMaximized() 会偶发误报 True（Win10 实测），弹窗不可最大化，
    # 不参与退化（见 §4.5）
    squared = window.isMaximized() and isinstance(window, QMainWindow)
    if squared != self._squared:                       # 状态变化才重设样式表
        self._squared = squared
        window.setStyleSheet(self._base_sheet + _SQUARE_CORNERS_SHEET
                             if squared else self._base_sheet)
    ...
```

主窗体的贴角控件——标题栏经 `setMenuWidget()` 挂载、状态栏经
`setStatusBar()` 挂载——都是 QMainWindow 的直接子控件，`QMainWindow >`
选择器恰好只匹配它们。

`WindowStateChange` 事件必须监听：离屏平台/同尺寸最大化只发状态变化、不发
Resize，漏掉会导致最大化后仍是圆角。

### 3.5 最大化压平的样式表会沿对象树泄漏到子弹窗（弹窗圆角变直角）

窗体级样式表不只作用于窗体本身，而是**沿 QObject 父子树作用于全部后代**。
所有弹窗都以主窗体为父控件创建，所以 §3.4 的压平片段若用裸的后代选择器
（`QDialog #FramelessDialogBody`、`QWizard`，以及 `QFrame#FramelessTitleBar`），
主窗体一最大化，规则就会命中**子弹窗**的标题栏/body——弹窗四角全部变直角
（实测：主窗体普通尺寸时弹窗圆角正常，最大化后左下/右上角立即变方）。

修法：压平片段只用 `QMainWindow >` 直接子选择器（见 §3.4），并删掉
`QDialog #FramelessDialogBody` / `QWizard` 这类对本窗体压平毫无作用、纯粹
泄漏源的选项。弹窗自身永远不压平（弹窗不可最大化，见 §3.4 与 §4.5）。

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

### 4.2 渲染：核心填充 + 环带指数渐隐 + 位图缓存

影子窗口尺寸 = 宿主 `frameGeometry()` 向四周各扩 `_SHADOW_MARGIN`（48px）。
**宿主轮廓在影子窗口坐标系里是四周缩进 margin 的圆角矩形**——坐标基准千万
别再外扩（本项目曾因此把阴影画到右上/左下两个错误方向上）。

阴影目标按本机原生 Win11 阴影实测标定（纯白背景、逐像素 alpha）：

| 位置 | 贴边 | 10px | 20px | 30px |
|---|---|---|---|---|
| 侧面 | 11% | 4.3% | 1.6% | 0.9% |
| 下缘 | 22% | 15.7% | 11.8% | 9% |
| 上缘 | 6.3% | 1.2% | 0 | 0 |

实现分三步：

1. **核心填充**：把宿主轮廓整体下移 `_SHADOW_OFFSET`（8px），用 `_SHADOW_ALPHA`
   （14 ≈ 5.5%，约为原生 11% 的一半）整体填一层。下移形成的“下重上轻”与原生
   阴影一致，也补上了偏移轮廓内部（尤其下缘）原本会漏空的区域。
2. **环带渐隐**：从核心边缘向外逐条填 40 条环带，每条只覆盖 `[e_{i-1}, e_i]`
   这一圈，透明度按 `exp(-_SHADOW_DECAY * t)` 衰减到 0。环带用 OddEven 路径
   （外圈圆角矩形 + 内圈圆角矩形）挖空，**不要再用 1.5px 描边笔**——旧实现
   相邻圈的半幅互相叠加，贴边实际不透明度约 29%，且中段衰减太慢，是
   “阴影太深”的根因。
   横向/纵向扩展距离分开取 `_SHADOW_RANGE_X=36` / `_SHADOW_RANGE_Y=40`，
   下缘因此比侧面更长。
3. **下缘增强**：填充用纵向 `QLinearGradient` 当画刷；窗体高度 75% 以下
   线性增强，到窗底为 `_SHADOW_BOTTOM_BOOST=1.5` 倍（5.5% → 约 8.2%）。
   保留原生“下重上轻”的方向，但整体强度约为原生的一半。

```python
host = QRectF(m, m, w - 2.0 * m, h - 2.0 * m)
base = host.translated(0, _SHADOW_OFFSET)                # 整体下移

def shadow_brush(alpha: int) -> QBrush:                  # 下缘增强渐变
    g = QLinearGradient(base.topLeft(), base.bottomLeft())
    top = QColor(0, 0, 0, alpha)
    bottom = QColor(0, 0, 0, min(255, round(alpha * _SHADOW_BOTTOM_BOOST)))
    g.setColorAt(0.0, top)
    g.setColorAt(_SHADOW_BOTTOM_RAMP, top)
    g.setColorAt(1.0, bottom)
    return QBrush(g)

painter.fillPath(_rounded_path(base, _RADIUS), shadow_brush(_SHADOW_ALPHA))

for i in range(1, _SHADOW_LAYERS + 1):
    t0, t1 = (i - 1) / _SHADOW_LAYERS, i / _SHADOW_LAYERS
    t = (t0 + t1) * 0.5
    alpha = round(_SHADOW_ALPHA
                  * (math.exp(-_SHADOW_DECAY * t) - math.exp(-_SHADOW_DECAY))
                  / (1.0 - math.exp(-_SHADOW_DECAY)))
    if alpha <= 0:
        continue
    ex0, ey0 = _SHADOW_RANGE_X * t0, _SHADOW_RANGE_Y * t0
    ex1, ey1 = _SHADOW_RANGE_X * t1, _SHADOW_RANGE_Y * t1
    band = QPainterPath()
    band.setFillRule(Qt.FillRule.OddEvenFill)            # 挖空内圈，只留环带
    band.addRoundedRect(base.adjusted(-ex1, -ey1, ex1, ey1),
                        _RADIUS + max(ex1, ey1), _RADIUS + max(ex1, ey1))
    band.addRoundedRect(base.adjusted(-ex0, -ey0, ex0, ey0),
                        _RADIUS + max(ex0, ey0), _RADIUS + max(ex0, ey0))
    painter.fillPath(band, shadow_brush(alpha))

self._cache = pixmap                                     # 按尺寸+DPR 缓存，仅 resize 重绘
```

环带边缘共享同一条曲线，抗锯齿覆盖互补：既不会出现旧描边方案的“亮缝”，
也不会因重叠而越描越深。调整参数时按上表逐边量 alpha，不要只凭肉眼——
缩略图上的观感误差很大。

### 4.3 同步与 z 序

在宿主上装事件过滤器，统一驱动圆角与影子：

| 宿主事件 | 动作 |
|---|---|
| Show / Resize / Move | 影子 `setGeometry(host.frameGeometry().adjusted(-m, -m, m, m))`；Show 后把影子插回宿主正下方（首次显示时继承宿主 transientParent，见 §4.5） |
| WindowStateChange | 最大化/最小化 → 影子隐藏（仅 QMainWindow 宿主，见 §3.4/§4.5）；还原 → 恢复 |
| Hide / Close | 影子隐藏 |
| ActivationChange / ZOrderChange | 影子重新插回宿主正下方（宿主被其他窗口抬起后影子不许浮到上面），并补一次 sync 自愈（§4.5） |

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

### 4.5 影子丢失：点击被模态禁用的主窗体（影子必须继承宿主的 Owner）

现象（三层，全部实测）：

1. 弹窗打开时，点击弹窗外、主窗体内任意位置 → **影子丢失**；
2. 影子丢失后，点击主窗体外（如桌面，应用失活）→ 激活中的弹窗影子恢复；
3. 两层弹窗（弹窗 A 上再开弹窗 B）时点击主窗体内 → 两层影子都丢；点桌面 →
   只有最上层（激活中）的 B 恢复，中间层的 A 不恢复。

根因：点击被模态禁用的主窗体，Windows 仍会**把主窗体 z 序抬升**——弹窗作为
owned 窗口被系统强制保持在 owner 上方（所以弹窗没被盖住、激活态也没变），
但**无主的影子窗口被压到主窗体下面**，被（最大化的）主窗体整个盖住。此刻
弹窗收不到任何事件（无激活变化、无几何变化），§4.3 的 restack 没有触发机会。
点桌面时应用失活：激活中的弹窗收到 `ActivationChange` → restack 自愈；中间层
弹窗本就不处于激活态、无状态变化、收不到事件 → 影子保持丢失。

修法（结构性，不依赖事件补救）：**影子窗口继承宿主的 transientParent
（同 Owner）**。Windows 的 owned-above-owner 规则由系统强制执行——主窗体
无论怎么被点击抬升都压不到影子；多层弹窗链式生效（B 的影子 owner=A，
A 的影子 owner=主窗体）。注意首次 sync 时影子还没有原生句柄，
`windowHandle()` 为 None，要先 `winId()` 建原生窗口才能设置：

```python
if not self.isVisible():
    host_handle = host.windowHandle()
    if host_handle is not None:
        handle = self.windowHandle()
        if handle is None:
            self.winId()                      # 先建原生窗口才能设置 owner
            handle = self.windowHandle()
        if handle is not None and handle.transientParent() is not host_handle.transientParent():
            handle.setTransientParent(host_handle.transientParent())
    self.show()
```

配套两道保险：最大化藏影只对 QMainWindow 判定（弹窗不参与，见 §3.4 的
isMaximized 误报）；宿主 `ActivationChange` 时 restack 之外补一次 `sync()`
自愈，影子若曾被隐藏会被拉回。

诊断手段（定位此坑的关键）：`EnumWindows` 枚举进程顶层窗口看 z 序变化、
`GetWindowLongPtrW(hwnd, GWLP_HWNDPARENT)` 查影子 owner、
`GetWindow(shadow, GW_HWNDPREV)` 验证"影子正上方是否恰好是宿主"。
注意 `QWidget.isVisible()` 报告的是 Qt 侧状态，影子被其他窗口盖住时它仍是
True，必须看 z 序或屏幕合成结果。

## 5. 弹出层圆角（菜单与下拉列表）

### 5.1 菜单

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

### 5.2 下拉框的弹出列表

QComboBox 的弹出列表（`QComboBoxPrivateContainer` 容器 + 内部 `QListView`）
**不是 QMenu**，§5.1 的过滤器覆盖不到，问题表现还随上下文不同：

* 主窗体里：容器按应用级 QSS 的 QWidget 背景规则画成不透明底色，圆角卡片
  画在里面，四角露出方角（右下最明显）；
* QDialog 里：`QDialog QWidget { background: transparent }` 命中弹出容器，
  不透明窗口上画透明背景，圆角外直接露出**未初始化的黑底**。

修法与菜单同款（过滤器在 Polish 时一并处理 QComboBox）：

```python
def apply_combo_popup_rounding(combo: QComboBox) -> None:
    container = combo.view().window()
    apply_menu_rounding(container)            # 透明 + 无边框 + 关系统阴影
    container.setStyleSheet(
        "QComboBoxPrivateContainer { background: transparent; }")
```

两个要点：

1. **容器必须一并透明化**。它会被应用级 QSS 的 QWidget 背景规则画成不透明
   底色，不透明则圆角外的方角照样露出来；透明后内部 QListView 的圆角卡片
   （`QComboBox QAbstractItemView` 规则）才是真实轮廓。
2. **容器样式表必须带类名选择器**。无选择器的规则等于容器内通用，会把内部
   列表也打透明（列表没了底色）。

同一过滤器覆盖全项目所有 QComboBox（主窗体各面板、表格单元格内嵌、各弹窗、
AI 设置等），无需逐处接入。

## 6. 相关的平台坑速查

| 坑 | 现象 | 处置 |
|---|---|---|
| QSizeGrip 方角贴片 | 主窗体右下角"直角" | QMainWindow 状态栏自带 16×16 手柄压在圆角上；边缘缩放走 `WM_NCHITTEST` 时直接 `statusBar().setSizeGripEnabled(False)` |
| 关闭按钮悬停背景方角 | 红色悬停块探出窗体圆角 | 贴角的按钮规则同样要 border + 圆角（§3.2），悬停/按下背景才会被裁 |
| QSS 背景不裁圆角 | 写了 border-radius 仍是方角 | 规则必须带 border（§3.2），1px transparent 即可 |
| QMainWindow 忽略布局边距 | `layout().setContentsMargins()` 不生效 | 它的内部布局自行排布 menuWidget/central/statusbar；别指望用它缩进内容 |
| PySide6 6.12.0 QSpinBox 回归 | QSS 带 border/padding 时 spinbox 内嵌编辑区被压成 1px，数字不可见（6.8~6.11 正常） | 依赖钉 `PySide6>=6.6,<6.7`（本项目取 6.6 系列），等 Qt 修复再放开 |
| 顶层不透明窗口的像素测量陷阱 | grab()/截屏判读圆角被窗口表面填充误导 | 测量必须在**透明窗体 + 子控件**的真实结构上做，或直接量屏幕合成结果（见 §7） |
| 点击被模态禁用的主窗体，弹窗影子丢失 | 主窗体 z 序被抬到弹窗之下、影子之上，无主影子被盖住；弹窗激活态不变，收不到任何可触发 restack 的事件（多层弹窗时只有激活中那层能靠 ActivationChange 自愈，见 §4.5） | 影子窗口继承宿主的 `transientParent`（QWindow.setTransientParent，首次 sync 时先 `winId()` 建原生句柄再设），owned-above-owner 规则保证主窗体永远压不到影子 |
| 主窗体最大化后弹窗圆角变直角 | 窗体级样式表沿 QObject 父子树作用于全部后代，压平片段的裸后代选择器命中子弹窗的标题栏/body（见 §3.5） | 压平片段只用 `QMainWindow >` 直接子选择器限定主窗体自己的贴角控件，删掉 `QDialog #FramelessDialogBody` / `QWizard` 等泄漏源 |
| QDialog 上 isMaximized() 误报 | 作为最大化的 QMainWindow 的 owned 窗口，普通尺寸的 QDialog 偶发 `isMaximized()==True`（Win10 实测），据此藏影/压平会把正常弹窗的影子、圆角一并丢掉 | 最大化退化与藏影判定都加 `isinstance(host, QMainWindow)` 限定（§3.4 / §4.5） |
| QWizard 自带的贯穿分隔线去不掉 | 按钮行上方的分隔条（QWizardRuler，Classic/Modern 必插入的固定 2px 手绘控件）hide() 后布局重建又被 QLayout 重新 show；且私有类没有 Q_OBJECT，`metaObject().className()` 是 "QWidget"，按类名过滤永远匹配不到（实测） | 按“最大高度 ≤3px”特征识别，`setFixedHeight(0)`（高度恒 0 画不出线，设置持久于复用的控件实例）+ 调色板 Mid/Base 改为背景色兜底；页头一条随页面 title/subTitle 删除整体隐藏 |
| 点选单元格后选中列的列头文字变粗（视觉像字体变小） | QHeaderView 的 highlightSections 默认开：选中列的列头节走另一条渲染路径，文字字重跳变；QSS 列头规则没有 :selected 背景，高亮的唯一表现就是这个跳变 | 表格统一 `horizontalHeader().setHighlightSections(False)`（CellFillTable / 主窗体 _make_table / 多原则表），列头恒定 |

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
| 助手/描边圈/影子/弹出层修整 | `src/app/views/widgets/rounded_window.py`（影子继承宿主 transientParent 在 `_ShadowWindow.sync`，压平片段 `_SQUARE_CORNERS_SHEET`，见 §3.5/§4.5） |
| 接入点（弹窗基类） | `src/app/views/widgets/frameless_dialog.py`（`FramelessDialog.__init__` 非 mac 分支） |
| 接入点（主窗体） | `src/app/views/main_window.py`（`MainWindow.__init__` 非 mac 分支） |
| 贴角子控件 QSS | `src/app/resources/qss/theme.py`（搜 `FramelessTitleBar` / `FramelessDialogBody` / `QWizard` / `QStatusBar` / `WindowBtn`） |
| 弹出层修整安装 | `src/app/main.py`（`install_menu_rounding(app)`） |
| 边缘缩放（NCHITTEST） | `src/app/views/main_window.py`（`nativeEvent`） |
| 回归测试 | `tests/test_rounded_window.py` |
| 依赖钉版（QSpinBox 回归） | `pyproject.toml`（`PySide6>=6.6,<6.7`） |
