"""主窗体：单窗体 + 三栏，不做 MDI、不做子窗体。

    ┌ 菜单栏 + 工具栏 ─────────────────────────────┐
    │ 项目树 250px │ 中部工作区 │ AI 助手 360px │
    └ 状态栏 ────────────────────────────────────┘

中部工作区是 QStackedWidget，项目树选中的任何节点都显示对应
单位工程的工程量工作台；原则编辑走顶部原则横条 + 模态对话框。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.config import add_recent_project, get_config, remove_recent_project, update_config
from app.core.event_bus import bus
from app.core.version import (
    APP_DISPLAY_NAME,
    APP_VERSION,
    PROJECT_FILE_FILTER,
)
from app.core.models.base import NotAProjectFileError, ProjectFileError, SchemaTooNewError
from app.resources.qss.theme import ThemeManager
from app.services import project_io
from app.services.project_io import ProjectIoError, ProjectLockedError, NewProjectSpec
from app.viewmodels.project_vm import KIND_UNIT, TreeNode
from app.views.panels.ai_panel import AiPanel
from app.views.panels.principle_bar import PrincipleBar
from app.views.panels.tree_panel import TreePanel
from app.views.panels.unit_panel import UnitPanel
from app.views.widgets.frameless_dialog import FramelessMessageBox
from app.views.widgets.mac_window import apply_mac_window_chrome, is_mac
from app.views.widgets.rounded_window import RoundedWindowHelper
from app.views.dialogs.new_project_wizard import (
    NewProjectWizard,
    suggested_dir,
    suggested_file_name,
)

_TREE_WIDTH = 250  # 左侧面板默认宽度（取自运行实例实测）
_AI_WIDTH = 360
_AI_TOGGLE_WIDTH = 14


class _WindowButton(QToolButton):
    """窗口控制按钮：悬停切换高亮图标（照搬 Quotor views/widgets/title_bar.py）。"""

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WindowBtn")
        self.setProperty("kind", kind)
        self.setAutoRaise(True)
        self.setFixedSize(46, 36)
        self._kind = kind
        self._normal_color = "#C0C0C0"
        self._hover_color = "#FFFFFF"
        self._hovered = False
        self._refresh()

    def set_colors(self, normal: str, hover: str) -> None:
        self._normal_color = normal
        self._hover_color = hover
        self._refresh()

    def set_kind(self, kind: str) -> None:
        if kind != self._kind:
            self._kind = kind
            self._refresh()

    def _refresh(self) -> None:
        self._normal_icon = _make_window_icon(self._kind, self._normal_color)
        self._hover_icon = _make_window_icon(self._kind, self._hover_color)
        self.setIcon(self._hover_icon if self._hovered else self._normal_icon)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._hovered = True
        self.setIcon(self._hover_icon)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._hovered = False
        self.setIcon(self._normal_icon)
        super().leaveEvent(event)


def _make_window_icon(kind: str, color: str):
    """程序绘制窗口控制图标，避免外部资源依赖（照搬 Quotor）。"""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

    size = 16
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(color), 1.3))
    if kind == "minimize":
        painter.drawLine(3, size - 5, size - 3, size - 5)
    elif kind == "maximize":
        painter.drawRect(QRectF(4, 4, size - 8, size - 8))
    elif kind == "restore":
        painter.drawRect(QRectF(6.5, 3.5, 8, 8))
        painter.drawRect(QRectF(3.5, 6.5, 8, 8))
    elif kind == "close":
        painter.drawLine(4, 4, size - 4, size - 4)
        painter.drawLine(size - 4, 4, 4, size - 4)
    painter.end()
    return QIcon(pixmap)


class FramelessTitleBar(QFrame):
    """无边框窗口的自绘标题栏：应用标识 + 菜单栏 + 最小化/最大化/关闭。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FramelessTitleBar")
        self.setFixedHeight(36)
        self._pressed = False
        self._drag_offset = None
        self._drag_from_max = False
        self._drag_start = None
        self._press_pos = None

        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        self._mac = is_mac()
        layout.setContentsMargins(TRAFFIC_LIGHT_INSET_ALL if self._mac else 12, 0, 0, 0)

        self._icon_label = QLabel("§")
        self._icon_label.setObjectName("TitleBarIcon")
        self._icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._menu_bar = QMenuBar(self)
        self._menu_bar.setObjectName("TitleBarMenuBar")
        self._menu_bar.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        layout.addWidget(self._icon_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._menu_bar, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch()

        self._btn_min = _WindowButton("minimize", self)
        self._btn_max = _WindowButton("maximize", self)
        self._btn_close = _WindowButton("close", self)
        layout.addWidget(self._btn_min)
        layout.addWidget(self._btn_max)
        layout.addWidget(self._btn_close)

        self._btn_min.clicked.connect(self._on_minimize)
        self._btn_max.clicked.connect(self._on_toggle_max)
        self._btn_close.clicked.connect(self._on_close)
        if self._mac:
            # Apple HIG：关闭/最小化/缩放用系统红绿灯（左上角），隐藏自绘控制按钮
            for button in (self._btn_min, self._btn_max, self._btn_close):
                button.setVisible(False)

    @property
    def menu_bar(self) -> QMenuBar:
        """供 MainWindow 填充菜单。"""
        return self._menu_bar

    def refresh_theme(self, colors) -> None:
        self._btn_min.set_colors(colors.text_secondary, colors.text_primary)
        self._btn_max.set_colors(colors.text_secondary, colors.text_primary)
        self._btn_close.set_colors(colors.text_secondary, colors.text_inverse)
        self.update_max_icon()

    def update_max_icon(self) -> None:
        window = self.window()
        maximized = bool(window is not None and window.isMaximized())
        self._btn_max.set_kind("restore" if maximized else "maximize")

    def _on_minimize(self) -> None:
        window = self.window()
        if window is not None:
            window.showMinimized()

    def _on_toggle_max(self) -> None:
        window = self.window()
        if window is None:
            return
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()

    def _on_close(self) -> None:
        window = self.window()
        if window is not None:
            window.close()

    # --- 拖拽移动（照搬 Quotor：从最大化拖出自动还原） ---
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window is not None:
                self._pressed = True
                self._drag_start = event.globalPosition().toPoint()
                if window.isMaximized():
                    self._drag_from_max = True
                    self._press_pos = event.position().toPoint()
                else:
                    self._drag_from_max = False
                    self._drag_offset = (
                        event.globalPosition().toPoint() - window.frameGeometry().topLeft()
                    )
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if not self._pressed or self._drag_start is None:
            return
        window = self.window()
        if window is None:
            return
        if self._drag_from_max:
            if (event.globalPosition().toPoint() - self._drag_start).manhattanLength() <= 5:
                event.accept()
                return
            screen = window.screen()
            if screen is not None:
                available = screen.availableGeometry()
                target_w = min(1440, int(available.width() * 0.8))
                target_h = min(900, int(available.height() * 0.8))
            else:
                target_w, target_h = 1440, 900
            ratio = self._press_pos.x() / max(self.width(), 1)
            new_x = int(event.globalPosition().x() - target_w * ratio)
            new_y = int(event.globalPosition().y() - self._press_pos.y())
            if screen is not None:
                available = screen.availableGeometry()
                new_x = max(available.left() + 10, min(new_x, available.right() - target_w - 10))
                new_y = max(available.top() + 10, min(new_y, available.bottom() - target_h - 10))
            if sys.platform == "win32":
                import ctypes

                hwnd = int(window.winId())
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.MoveWindow(hwnd, new_x, new_y, target_w, target_h, True)
                window.setWindowState(Qt.WindowState.WindowNoState)
            else:
                window.showNormal()
                window.setGeometry(new_x, new_y, target_w, target_h)
            self.update_max_icon()
            self._drag_from_max = False
            self._drag_offset = event.globalPosition().toPoint() - QPoint(new_x, new_y)
        elif self._drag_offset is not None:
            window.move(event.globalPosition().toPoint() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._pressed = False
        self._drag_from_max = False
        self._drag_offset = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_toggle_max()
        event.accept()


class _ToggleBar(QToolButton):
    """AI 面板折叠条（竖条，14px）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "toggle-bar")
        self.setFixedWidth(_AI_TOGGLE_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)

    def set_expanded(self, expanded: bool) -> None:
        self.setText("›" if expanded else "‹")
        self.setToolTip("折叠 AI 助手 (Ctrl+L)" if expanded else "展开 AI 助手 (Ctrl+L)")


class MainWindow(QMainWindow):
    """Section 2.0 主窗体。"""

    def __init__(self, project_path: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if is_mac():
            # mac：保留原生窗口（系统圆角/阴影/红绿灯），标题栏由 mac_window.py 藏进自绘界面
            self.setWindowFlags(Qt.WindowType.Window)
        else:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.resize(1440, 900)
        if is_mac():
            # Apple HIG：主窗体不放自绘标题栏行，菜单挂系统菜单栏，
            # 红绿灯（系统绘制）浮在工具栏上方左上角
            self._title_bar = None
        else:
            self._title_bar = FramelessTitleBar()
            self.setMenuWidget(self._title_bar)  # 标题栏替代原生菜单栏行
            # Windows/Linux：自绘圆角（不依赖 Win11 DWM，Win10/11 外观一致）
            self._rounded = RoundedWindowHelper.install(self)
        self._build_central()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._connect_events()
        self._update_title()
        self._refresh_recent_menu()
        self._enable_win11_rounded_corners()
        if is_mac():
            # mac 的 chrome 在首次 showEvent 里套用：show 时 Qt 会按窗口标志重置
            # NSWindow 样式掩码，提前设置会被覆盖（对话框无此问题，见 FramelessDialog）
            self._mac_chrome_applied = False
            self.winId()
        if project_path:
            QTimer.singleShot(0, lambda: self._open_path(project_path))

    # ------------------------------------------------------------------ 原生窗口辅助
    def _enable_win11_rounded_corners(self) -> None:
        """Windows 11：为无边框窗口启用原生圆角（Win10 自动忽略）。照搬 Quotor。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            preference = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference)
            )
        except Exception:
            pass

    def nativeEvent(self, event_type, message):  # noqa: N802 - Qt 命名
        """Windows：无边框窗口的边缘缩放（WM_NCHITTEST）。照搬 Quotor。"""
        if event_type == "windows_generic_MSG":
            import ctypes
            from ctypes import wintypes

            try:
                message_struct = wintypes.MSG.from_address(int(message))
            except Exception:
                return super().nativeEvent(event_type, message)
            if message_struct.message == 0x0084 and not self.isMaximized():
                x = ctypes.c_short(message_struct.lParam & 0xFFFF).value
                y = ctypes.c_short((message_struct.lParam >> 16) & 0xFFFF).value
                position = self.mapFromGlobal(QPoint(x, y))
                border = 6
                rect = self.rect()
                on_left = position.x() <= border
                on_right = position.x() >= rect.width() - border
                on_top = position.y() <= border
                on_bottom = position.y() >= rect.height() - border
                if on_top and on_left:
                    return True, 13
                if on_top and on_right:
                    return True, 14
                if on_bottom and on_left:
                    return True, 16
                if on_bottom and on_right:
                    return True, 17
                if on_left:
                    return True, 10
                if on_right:
                    return True, 11
                if on_top:
                    return True, 12
                if on_bottom:
                    return True, 15
        return super().nativeEvent(event_type, message)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if is_mac() and not self._mac_chrome_applied:
            self._mac_chrome_applied = True
            apply_mac_window_chrome(self)
        super().showEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if (
            event.type() == QEvent.Type.WindowStateChange
            and getattr(self, "_title_bar", None) is not None
        ):
            self._title_bar.update_max_icon()
        super().changeEvent(event)

    # ------------------------------------------------------------------ 布局
    def _build_central(self) -> None:
        self._tree_panel = TreePanel()
        self._unit_panel = UnitPanel()
        self._ai_panel = AiPanel()

        self._center_stack = QStackedWidget()
        placeholder = QLabel("请从左侧选择节点。\n文件 → 新建工程 / 打开工程")
        placeholder.setProperty("role", "placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._center_stack.addWidget(placeholder)
        self._center_stack.addWidget(self._unit_panel)

        # 原则横条（复刻原版 panelPrincple）：位于中部工作区上方，未打开工程时隐藏
        self._principle_bar = PrincipleBar()
        self._principle_bar.setVisible(False)
        self._tree_panel.insert_requested.connect(self._insert_template)

        center_page = QWidget()
        center_layout = QVBoxLayout(center_page)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self._principle_bar)
        center_layout.addWidget(self._center_stack, 1)

        ai_container = QWidget()
        ai_layout = QHBoxLayout(ai_container)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        ai_layout.setSpacing(0)
        self._ai_toggle = _ToggleBar()
        self._ai_toggle.clicked.connect(self._toggle_ai_panel)
        ai_layout.addWidget(self._ai_toggle)
        ai_layout.addWidget(self._ai_panel)
        self._ai_container = ai_container

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree_panel)
        splitter.addWidget(center_page)
        splitter.addWidget(ai_container)
        splitter.setHandleWidth(1)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        self._splitter = splitter
        self.setCentralWidget(splitter)

        self._ai_saved_width = _AI_WIDTH
        expanded = get_config().ai_panel_expanded
        self._apply_ai_visible(expanded, initial=True)

    def _insert_template(self, template) -> None:
        """构件库双击：当前树选中的必须是单位工程（原版守卫逻辑）。"""
        node = self._tree_panel.current_node
        if node is None or not node.is_unit:
            self._set_status("请于项目树中选中单位工程后再插入构件。", 4000)
            return
        self._unit_panel.insert_template(template)

    def _apply_ai_visible(self, expanded: bool, *, initial: bool = False) -> None:
        self._ai_panel.setVisible(expanded)
        self._ai_toggle.set_expanded(expanded)
        if expanded:
            self._ai_container.setMaximumWidth(16777215)
        else:
            self._ai_container.setMaximumWidth(_AI_TOGGLE_WIDTH)

        if initial:
            # 窗口还没显示过，splitter.sizes() 全是 0，直接用默认宽度
            # （中间给 600，剩下的宽度由窗口分配，保证左右两栏拿到 250 / 360）
            sizes = [
                _TREE_WIDTH,
                600,
                _AI_WIDTH + _AI_TOGGLE_WIDTH if expanded else _AI_TOGGLE_WIDTH,
            ]
        else:
            sizes = self._splitter.sizes()
            if expanded:
                target = self._ai_saved_width + _AI_TOGGLE_WIDTH
                take = min(max(0, target - sizes[2]), max(0, sizes[1] - 200))
                sizes[1] -= take
                sizes[2] += take
            else:
                self._ai_saved_width = max(240, self._ai_panel.width())
                sizes[1] += max(0, sizes[2] - _AI_TOGGLE_WIDTH)
                sizes[2] = _AI_TOGGLE_WIDTH
        self._splitter.setSizes(sizes)

    # ------------------------------------------------------------------ 动作
    #: 工具栏动作 → Lucide 图标名（svg 随主题重着色，Quotor 同款机制）
    _ACTION_ICONS = {
        "act_new": "file-plus",
        "act_open": "folder-open",
        "act_save": "save",
        "act_add_segment": "folder-plus",
        "act_add_unit": "file-text",
        "act_add_element": "plus",
        "act_refresh": "refresh-cw",
        "act_theme": "moon",
        "act_ai_panel": "panel-right",
    }

    def _build_actions(self) -> None:
        self._act_new = self._action("新建工程(&N)", self._new_project, "Ctrl+N")
        self._act_open = self._action("打开工程(&O)…", self._open_project, "Ctrl+O")
        self._act_save = self._action("保存(&S)", self._save_project, "Ctrl+S")
        self._act_save_as = self._action("另存为(&A)…", self._save_project_as, "Ctrl+Shift+S")
        self._act_close = self._action("关闭工程(&C)", self._close_project)
        self._act_import_legacy = self._action("导入旧版工程(.stn)…", self._import_legacy)
        self._act_exit = self._action("退出(&Q)", self.close, "Ctrl+Q")

        self._act_add_segment = self._action("新增标段", lambda: self._tree_panel.add_segment())
        self._act_add_unit = self._action("新增单位工程", lambda: self._tree_panel.add_unit())
        self._act_add_element = self._action("新增构件条目", self._add_element)
        self._act_refresh = self._action("刷新", self._refresh, "F5")
        self._act_theme = self._action("切换暗色主题", self._toggle_theme, "Ctrl+Shift+T")
        self._act_ai_panel = self._action("AI 助手", lambda: self._toggle_ai_panel(), "Ctrl+L")
        self._act_ai_settings = self._action("AI 设置…", self._ai_settings)
        self._act_about = self._action("关于 Section", self._about)

        for attr, icon_name in self._ACTION_ICONS.items():
            action = getattr(self, f"_{attr}")
            # setData 存图标名，主题切换时按新主题色重载（Quotor _make_action 同款）
            action.setData(icon_name)
            self._apply_action_icon(action)

        for action in (
            self._act_save,
            self._act_save_as,
            self._act_close,
            self._act_add_segment,
            self._act_add_unit,
            self._act_add_element,
            self._act_refresh,
        ):
            action.setEnabled(False)
        self._project_actions = (
            self._act_save,
            self._act_save_as,
            self._act_close,
            self._act_add_segment,
            self._act_add_unit,
            self._act_add_element,
            self._act_refresh,
        )

    def _action(self, text: str, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _apply_action_icon(self, action: QAction) -> None:
        """按 action.data() 里存的图标名，用当前主题色渲染 SVG 图标。"""
        icon_name = action.data()
        if not isinstance(icon_name, str) or not icon_name:
            return
        from app.views.widgets.frameless_dialog import load_icon

        color = ThemeManager.instance().current().text_primary
        action.setIcon(load_icon(icon_name, color=color, size=18))

    def _refresh_action_icons(self) -> None:
        """主题切换后遍历工具栏 + 菜单栏动作，用新主题色重载图标（Quotor 同款）。"""
        menubar = self.menuBar() if self._title_bar is None else self._title_bar.menu_bar
        containers = [menubar, self._toolbar]
        for container in containers:
            for action in container.actions():
                self._apply_action_icon(action)
                menu = action.menu()
                if menu is not None:
                    for sub_action in menu.actions():
                        self._apply_action_icon(sub_action)

    def _set_theme_action_icon(self) -> None:
        """主题按钮图标：暗色显示太阳（切到亮色）、亮色显示月亮（切到暗色），Quotor 同款。"""
        dark = ThemeManager.instance().is_dark()
        self._act_theme.setData("sun" if dark else "moon")
        self._apply_action_icon(self._act_theme)

    def _build_menus(self) -> None:
        if self._title_bar is not None:
            menubar = self._title_bar.menu_bar  # Windows 无边框：菜单栏在自绘标题栏内
        else:
            menubar = self.menuBar()  # mac：原生菜单栏（QMenuBar 在 mac 默认原生化）
            # Apple HIG：「退出」「关于」归系统菜单栏的应用菜单，从业务菜单里移走
            self._act_exit.setMenuRole(QAction.MenuRole.QuitRole)
            self._act_about.setMenuRole(QAction.MenuRole.AboutRole)

        file_menu = menubar.addMenu("文件(&F)")
        file_menu.addAction(self._act_new)
        file_menu.addAction(self._act_open)
        self._recent_menu = file_menu.addMenu("最近打开")
        file_menu.addSeparator()
        file_menu.addAction(self._act_save)
        file_menu.addAction(self._act_save_as)
        file_menu.addAction(self._act_close)
        file_menu.addSeparator()
        file_menu.addAction(self._act_import_legacy)
        file_menu.addSeparator()
        file_menu.addAction(self._act_exit)

        project_menu = menubar.addMenu("项目(&P)")
        project_menu.addAction(self._act_add_segment)
        project_menu.addAction(self._act_add_unit)
        project_menu.addAction(self._act_add_element)
        project_menu.addSeparator()
        project_menu.addAction("添加沟槽围护原则", lambda: self._principle_bar.add_enclosure())
        project_menu.addAction("添加地基处理原则", lambda: self._principle_bar.add_foundation())
        project_menu.addAction("添加降水原则", lambda: self._principle_bar.add_precipitation())
        project_menu.addAction("添加面宽原则", lambda: self._principle_bar.add_width())
        project_menu.addSeparator()
        project_menu.addAction(self._act_refresh)

        view_menu = menubar.addMenu("视图(&V)")
        view_menu.addAction(self._act_theme)
        view_menu.addSeparator()
        view_menu.addAction(self._act_ai_panel)

        ai_menu = menubar.addMenu("AI(&A)")
        ai_menu.addAction(self._act_ai_settings)
        ai_menu.addAction(self._act_ai_panel)

        help_menu = menubar.addMenu("帮助(&H)")
        help_menu.addAction(self._act_about)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))  # Quotor 同款：纯图标 + 18px
        self.addToolBar(toolbar)
        self._toolbar = toolbar
        toolbar.addAction(self._act_new)
        toolbar.addAction(self._act_open)
        toolbar.addAction(self._act_save)
        toolbar.addSeparator()
        toolbar.addAction(self._act_add_segment)
        toolbar.addAction(self._act_add_unit)
        toolbar.addAction(self._act_add_element)
        toolbar.addSeparator()
        toolbar.addAction(self._act_refresh)
        toolbar.addAction(self._act_theme)
        toolbar.addAction(self._act_ai_panel)
        self.addToolBar(toolbar)

    def _build_statusbar(self) -> None:
        statusbar = QStatusBar()
        # 右下角的尺寸手柄是 16x16 方角贴片，会盖掉状态栏的 QSS 圆角；
        # 边缘缩放由 nativeEvent 的 WM_NCHITTEST 处理，手柄冗余
        statusbar.setSizeGripEnabled(False)
        self.setStatusBar(statusbar)
        self._status_path = QLabel("未打开工程")
        self._status_path.setProperty("role", "hint")
        statusbar.addPermanentWidget(self._status_path)
        statusbar.showMessage("就绪")

    # ------------------------------------------------------------------ 事件
    def _connect_events(self) -> None:
        bus().project_opened.connect(self._on_project_opened)
        bus().project_closed.connect(self._on_project_closed)
        bus().project_saved.connect(lambda path: self._set_status(f"已保存：{path}"))
        bus().node_selected.connect(self._on_node_selected)
        bus().status_message.connect(self._set_status)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
        # 主题切换按钮文字与图标随当前主题变化：暗色 → 太阳「切换亮色…」、亮色 → 月亮「切换暗色…」
        self._act_theme.setText("切换亮色主题" if ThemeManager.instance().is_dark() else "切换暗色主题")
        self._set_theme_action_icon()

    def _on_project_opened(self, path: str) -> None:
        if project_io.is_transient():
            # 临时工程：临时路径不进最近列表，状态栏提示尚未保存
            self._set_project_actions(True)
            self._update_title()
            self._status_path.setText("（尚未保存到文件）")
            self._set_status("已创建临时工程（尚未保存），点击「保存」选择文件位置", 5000)
            return
        add_recent_project(path)
        update_config({"ui": {"last_dir": str(Path(path).parent)}})
        self._refresh_recent_menu()
        self._set_project_actions(True)
        self._update_title()
        self._status_path.setText(str(path))
        self._set_status(f"已打开工程：{path}")

    def _on_project_closed(self) -> None:
        self._set_project_actions(False)
        self._update_title()
        self._status_path.setText("未打开工程")
        self._center_stack.setCurrentIndex(0)

    def _on_node_selected(self, node: TreeNode | None) -> None:
        self._ai_panel.set_current_unit(
            node.id if node is not None and node.kind == KIND_UNIT else None,
            node.name if node is not None and node.kind == KIND_UNIT else "",
        )
        if node is None:
            self._center_stack.setCurrentIndex(0)
            return
        self._center_stack.setCurrentIndex(1)

    def _on_theme_changed(self, _name: str) -> None:
        self._act_theme.setText("切换亮色主题" if ThemeManager.instance().is_dark() else "切换暗色主题")
        self._set_theme_action_icon()
        self._refresh_action_icons()
        if self._title_bar is not None:  # mac 上没有自绘标题栏
            self._title_bar.refresh_theme(ThemeManager.instance().current())
        elif is_mac():
            # mac：重套 chrome 同步 NSWindow 外观，系统标题文字颜色跟随主题亮暗
            apply_mac_window_chrome(self)
        self._unit_panel.refresh()
        self._ai_panel.refresh_theme()

    def _set_status(self, message: str, timeout: int = 0) -> None:
        self.statusBar().showMessage(message, timeout)

    def _set_project_actions(self, enabled: bool) -> None:
        for action in self._project_actions:
            action.setEnabled(enabled)

    def _update_title(self) -> None:
        if not project_io.is_open():
            title = f"{APP_DISPLAY_NAME} {APP_VERSION}"
        else:
            # 临时工程没有文件路径，也照常显示工程名（Quotor 同款）
            name = project_io.project_name() or "未命名工程"
            title = f"{name} - {APP_DISPLAY_NAME} {APP_VERSION}"
        self.setWindowTitle(title)
        if self._title_bar is not None:  # mac 上标题只由系统菜单栏/红绿灯行呈现
            self._title_bar.setToolTip(title)

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        recent = get_config().recent_projects
        if not recent:
            action = self._recent_menu.addAction("（空）")
            action.setEnabled(False)
            return
        for path in recent:
            action = self._recent_menu.addAction(path)
            action.triggered.connect(lambda _checked=False, target=path: self._open_path(target))

    # ------------------------------------------------------------------ 工程操作
    def _new_project(self) -> None:
        # 当前有未保存的临时工程时先询问（Quotor 同款）
        if not self._prompt_save_if_unsaved():
            return
        wizard = NewProjectWizard(self)
        if wizard.exec() != NewProjectWizard.DialogCode.Accepted:
            return
        values = wizard.values()
        # 不立即要求选择保存位置：先建临时工程，首次保存时再定路径
        spec = NewProjectSpec(**values)
        try:
            project_io.new_project(spec)
        except ProjectIoError as error:
            self._error("新建工程失败", str(error))
            return
        bus().project_opened.emit("")
        self._tree_panel.vm.load()

    def _prompt_save_if_unsaved(self, verb: str = "切换") -> bool:
        """当前工程尚未保存到文件时提示是否先保存（Quotor _prompt_save_current_if_dirty 同款）。

        在新建/打开/关闭工程与退出前调用。返回是否可以继续：
        - True：无需保存 / 已保存 / 用户选择不保存 → 继续
        - False：用户取消 → 调用方应中止当前操作
        """
        if not project_io.is_transient():
            return True
        name = project_io.project_name() or "当前工程"
        reply = FramelessMessageBox.question(
            self,
            f"确认{verb}",
            f"“{name}”尚未保存到文件，是否在{verb}前保存？",
            FramelessMessageBox.StandardButton.Save
            | FramelessMessageBox.StandardButton.Discard
            | FramelessMessageBox.StandardButton.Cancel,
            FramelessMessageBox.StandardButton.Save,
        )
        if reply == FramelessMessageBox.StandardButton.Save:
            target = self._prompt_save_as_path("保存工程")
            if target is None:
                return False
            return self._save_as_target(target, "保存失败")
        return reply == FramelessMessageBox.StandardButton.Discard

    def _open_project(self) -> None:
        if not self._prompt_save_if_unsaved():
            return
        start = get_config().last_dir or str(suggested_dir())
        target, _filter = QFileDialog.getOpenFileName(self, "打开工程", start, PROJECT_FILE_FILTER)
        if target:
            self._open_path(target)

    def _open_path(self, path: str) -> None:
        if not self._prompt_save_if_unsaved():
            return
        if not Path(path).exists():
            self._error("打开工程失败", f"文件不存在：{path}")
            remove_recent_project(path)
            self._refresh_recent_menu()
            return
        try:
            opened = project_io.open_project(path)
        except ProjectLockedError as error:
            self._error("工程已打开", str(error))
            return
        except SchemaTooNewError as error:
            self._error("版本不兼容", str(error))
            return
        except NotAProjectFileError as error:
            self._error("无法打开", str(error))
            return
        except ProjectFileError as error:
            self._error("打开工程失败", str(error))
            return
        bus().project_opened.emit(str(opened))
        self._tree_panel.vm.load()

    def _save_project(self) -> None:
        if project_io.is_transient():
            # 首次保存：临时工程还没有文件，选好位置后转为正式工程
            target = self._prompt_save_as_path("保存工程")
            if target is None:
                return
            self._save_as_target(target, "保存失败")
            return
        try:
            path = project_io.save()
        except ProjectIoError as error:
            self._error("保存失败", str(error))
            return
        if path is not None:
            bus().project_saved.emit(str(path))

    def _save_project_as(self) -> None:
        target = self._prompt_save_as_path()
        if target is None:
            return
        self._save_as_target(target, "另存为失败")

    def _prompt_save_as_path(self, caption: str = "另存为") -> Path | None:
        """弹出文件选择框，让用户选保存位置（首次保存 / 另存为共用，Quotor 同款）。"""
        name = project_io.project_name() or "新建项目"
        current = project_io.current_path()
        if current is not None:
            start = str(current)
        else:
            start = str(Path(get_config().last_dir or str(suggested_dir())) / suggested_file_name(name))
        target, _filter = QFileDialog.getSaveFileName(self, caption, start, PROJECT_FILE_FILTER)
        return Path(target) if target else None

    def _save_as_target(self, target: Path, error_title: str) -> bool:
        """把当前工程保存到 target 并广播刷新；成功返回 True。"""
        try:
            path = project_io.save_as(target)
        except ProjectIoError as error:
            self._error(error_title, str(error))
            return False
        bus().project_saved.emit(str(path))
        bus().project_opened.emit(str(path))
        self._tree_panel.vm.load()
        return True

    def _close_project(self) -> None:
        if not project_io.is_open():
            return
        if not self._prompt_save_if_unsaved("关闭"):
            return
        project_io.close_project()
        bus().project_closed.emit()

    def _import_legacy(self) -> None:
        """旧 .stn 单向迁移导入（M6）。"""
        from app.views.dialogs.legacy_import_dialog import LegacyImportDialog

        self._legacy_import = LegacyImportDialog(self)
        self._legacy_import.show()

    def _add_element(self) -> None:
        node = self._tree_panel.vm.current()
        if node is None or not node.is_unit:
            self._set_status("请先在左侧选择单位工程。", 4000)
            return
        self._unit_panel.add_element()

    def _refresh(self) -> None:
        self._tree_panel.vm.load()
        self._unit_panel.refresh()
        self._set_status("已刷新", 2000)

    def _toggle_theme(self) -> None:
        name = ThemeManager.instance().toggle(QApplication.instance())
        update_config({"ui": {"theme": name}})
        self._set_status("已切换到暗色主题" if name == "dark" else "已切换到亮色主题", 3000)

    def _toggle_ai_panel(self) -> None:
        expanded = not self._ai_panel.isVisible()
        self._apply_ai_visible(expanded)
        update_config({"ui": {"ai_panel_expanded": expanded}})

    def _ai_settings(self) -> None:
        """AI 模型配置（M7）。"""
        from app.views.dialogs.ai_settings_dialog import AiSettingsDialog

        dialog = AiSettingsDialog(self)
        dialog.exec()
        self._ai_panel._refresh_hint()

    def _about(self) -> None:
        FramelessMessageBox.about(
            self,
            "关于 Section",
            f"{APP_DISPLAY_NAME}　版本 {APP_VERSION}<br><br>"
            "线性工程（市政管道）工程量计算软件，Python + PySide6 重写版。<br>"
            "工程文件：.stn2（单文件 SQLite）<br><br>"
            "参考初代 C# 版 section 1.2.2.171220_beta。",
        )

    def _error(self, title: str, message: str) -> None:
        FramelessMessageBox.warning(self, title, message)

    # ------------------------------------------------------------------ 退出
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """退出前检查未保存的临时工程，然后落盘并释放锁。"""
        # 临时工程（尚未保存到文件）在退出前提示保存；用户取消则不关闭
        if not self._prompt_save_if_unsaved("关闭"):
            event.ignore()
            return
        try:
            project_io.close_project()
        except Exception as error:  # pragma: no cover - 退出路径不阻塞
            self._set_status(f"关闭工程时出错：{error}", 5000)
        super().closeEvent(event)
