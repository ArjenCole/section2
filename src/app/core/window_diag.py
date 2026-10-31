"""窗口"消失"诊断黑匣子（仅 Windows；默认开启，``SECTION2_DIAG=0`` 关闭）。

背景（2026-10-22 两次现场）：弹窗开着时点一下主窗体，主窗体与弹窗一起从屏幕上
消失、进程却还在运行。两次取证都表明**不是崩溃**：GUI 线程空闲在 ``app.exec()``、
``SendMessageTimeout`` 有应答，但 ``EnumWindows`` 里主窗体的 HWND 已经不存在
（健康时类名是 ``Qt6xxxQWindowIcon``）。结论是"顶层原生窗口被销毁且没有再 show"；
弹窗连坐，是因为它是主窗体的 owned 窗口（Windows 规则：owner 销毁 → owned 全灭）。

2026-10-29 的现场进一步确认：主窗体先收到一个**没有 Close、也不是最小化**的
``QEvent::Hide``，随后原生 HWND 被销毁，而 QWidget/进程都还活着。``hide()``
本身不会销毁原生窗口；这种"Hide + DESTROY + 无 Close"与
``QWindow.destroy()`` / ``QWidget.destroy()`` 的特征一致。

本模块做三件事：

1. ``SetWinEventHook`` 监听本进程的 SHOW / HIDE / DESTROY —— 原生真相；
2. 记录可疑路径上的每一次原生窗口操作（自绘圆角 / 影子窗口那一层、原则弹窗、
   主窗体进出事件），带相对时间戳、当前模态窗、HWND、spontaneous 标志与深栈；
3. 一旦"被跟踪的顶层窗口"出现异常（主窗体无 Close 的 Hide、HWND 被销毁、
   或 1s 自检发现失效），立刻落盘 ``logs/window_diag_<时间>.dump.txt``：
   最近 600 条时序 + 本进程全部顶层窗口快照 + 当时的 Python 栈。

正常启动默认启用；不想要时设环境变量 ``SECTION2_DIAG=0`` 关掉（离屏测试里也
自动不启用）。关闭后 :func:`install` 返回 ``None``，:func:`record` 是空操作。

用法::

    .venv\\Scripts\\python.exe src\\app\\main.py          # 默认开启
    set SECTION2_DIAG=0 && .venv\\Scripts\\python.exe src\\app\\main.py
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from collections import deque
from datetime import datetime

from app.core.paths import log_dir

_logger = logging.getLogger("section2.window_diag")

#: 环境变量开关
ENV_FLAG = "SECTION2_DIAG"

#: 环形缓冲保留条数
_RING_SIZE = 600

#: 自检间隔（毫秒）
_POLL_MS = 1000

# --- Win32 常量 ---------------------------------------------------------------
_EVENT_OBJECT_DESTROY = 0x8001
_EVENT_OBJECT_SHOW = 0x8002
_EVENT_OBJECT_HIDE = 0x8003
_WINEVENT_OUTOFCONTEXT = 0x0000
_OBJID_WINDOW = 0
_GWL_EXSTYLE = -20
_GW_OWNER = 4
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_LAYERED = 0x00080000

_EVENT_NAMES = {
    _EVENT_OBJECT_DESTROY: "DESTROY",
    _EVENT_OBJECT_SHOW: "SHOW",
    _EVENT_OBJECT_HIDE: "HIDE",
}

#: 记录的 Qt 事件（只对顶层窗口）
_WATCHED_EVENTS: set = set()

#: 单独用得上的几个事件类型（在 _init_watched_events 里填充）
_EV_SHOW = _EV_HIDE = _EV_CLOSE = _EV_QUIT = None

#: 一个会话最多落盘几份 dump（防止异常循环把磁盘写满）
_MAX_DUMPS = 20

#: 被跟踪窗口 Hide/Close 时保留的栈层数。这类事件频率低，尽量多留调用者：
#: 2026-10-29 的现场栈只留了 9 层，刚好在 SQLAlchemy 的 ``all()`` 处截断，
#: 看不到真正触发窗口销毁的业务代码。
_DEEP_STACK = 40


# --------------------------------------------------------------------------- #
# Win32 绑定（只在 Windows 上建立；argtypes 必须写全，否则 64 位下 HWND 会被截断）
# --------------------------------------------------------------------------- #
if sys.platform == "win32":  # pragma: no cover - 平台相关
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _WinEventProc = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,  # hWinEventHook
        wintypes.DWORD,  # event
        wintypes.HWND,  # hwnd
        wintypes.LONG,  # idObject
        wintypes.LONG,  # idChild
        wintypes.DWORD,  # idEventThread
        wintypes.DWORD,  # dwmsEventTime
    )

    _user32.SetWinEventHook.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HMODULE,
        _WinEventProc,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    _user32.SetWinEventHook.restype = wintypes.HANDLE
    _user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetWindow.restype = wintypes.HWND
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _kernel32.GetCurrentProcessId.restype = wintypes.DWORD
else:  # pragma: no cover - 非 Windows 只保证 import 不炸
    _user32 = None
    _kernel32 = None


def _init_watched_events() -> None:
    """把需要记录的 QEvent 类型装进集合（延迟到真正启用时再 import PySide6）。"""
    global _EV_SHOW, _EV_HIDE, _EV_CLOSE, _EV_QUIT
    if _WATCHED_EVENTS:
        return
    from PySide6.QtCore import QEvent

    _EV_SHOW = QEvent.Type.Show
    _EV_HIDE = QEvent.Type.Hide
    _EV_CLOSE = QEvent.Type.Close
    _EV_QUIT = getattr(QEvent.Type, "Quit", None)
    for name in (
        "Show",
        "Hide",
        "Close",
        "Destroy",
        "Polish",
        "StyleChange",
        "ActivationChange",
        "WindowActivate",
        "WindowDeactivate",
        "WindowStateChange",
        "ZOrderChange",
    ):
        value = getattr(QEvent.Type, name, None)
        if value is not None:
            _WATCHED_EVENTS.add(value)


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #
#: 当前实例（未启用时为 None；record() 只看这个全局）
_INSTANCE: "WindowDiag | None" = None


def record(kind: str, detail: str = "", *, stack: int = 0) -> str:
    """记录一条诊断事件（未启用时是空操作，调用点不必判断）。

    ``stack`` > 0 时附带 ``stack`` 层调用点（file:line 函数），用于埋点定位。
    返回本次记录的调用点文本（未启用 / 无栈时为空串）。
    """
    instance = _INSTANCE
    if instance is not None:
        return instance.record(kind, detail, stack=stack)
    return ""


def enabled() -> bool:
    """是否已启用（用于避免在热路径上白算参数）。"""
    return _INSTANCE is not None


def install(app) -> "WindowDiag | None":
    """安装诊断（Windows + 真实 windows 平台插件；默认开启）。

    屏幕上的"主窗体+弹窗一起消失、进程还在"目前只能靠这套记录定位，所以默认常开；
    不想要时设环境变量 ``SECTION2_DIAG=0`` 关掉（离屏测试里也自动不启用）。
    """
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    if sys.platform != "win32":
        return None
    try:
        if app.platformName() != "windows":  # 离屏/Qt 测试里不启用
            return None
    except Exception:  # noqa: BLE001
        return None
    if os.environ.get(ENV_FLAG, "").strip().lower() in {"0", "false", "no", "off"}:
        return None
    _INSTANCE = WindowDiag(app)
    return _INSTANCE


def shutdown() -> None:
    """卸载钩子与定时器（退出/测试用）。"""
    global _INSTANCE
    instance = _INSTANCE
    _INSTANCE = None
    if instance is not None:
        instance.dispose()


# --------------------------------------------------------------------------- #
# 黑匣子
# --------------------------------------------------------------------------- #
class WindowDiag:  # pragma: no cover - 需要真实 Windows 窗口
    """窗口事件黑匣子。"""

    def __init__(self, app) -> None:
        from PySide6.QtCore import QObject, QTimer

        _init_watched_events()
        self._app = app
        self._ring: deque[str] = deque(maxlen=_RING_SIZE)
        self._started = time.monotonic()
        self._hwnds: dict[int, str] = {}  # hwnd -> 标签（首次见到可视窗口时登记）
        self._tracked: set[int] = set()  # 已装过滤器的 widget（按 id 去重）
        self._hidden: set[int] = set()  # Qt 侧已经 Hide/Close 过的 hwnd
        self._closed: set[int] = set()  # Qt 侧明确收到过 Close 的 hwnd（正常关窗）
        self._important: set[int] = set()  # QMainWindow：消失即异常，判定比弹窗严格
        self._anomaly_dumped: set[int] = set()  # 已因"异常 Hide"落过盘的 hwnd
        self._main_hwnd: int | None = None  # 主窗体 HWND（退出时判断是否正常 Close）
        self._main_closed = False  # 主窗体收到过 Close（跨 DESTROY 清理保留）
        self._incident = 0  # 异常事件序号：让同一窗口的多次现场都能各落一份
        self._widgets: dict[int, object] = {}  # hwnd -> weakref(widget)，用于查 Qt 侧可见性
        self._dumped: set[int] = set()
        self._dump_count = 0
        self._pid = _kernel32.GetCurrentProcessId()
        self._log_path = log_dir() / "window_diag.log"
        # 每启动一次追加一份；超过 8MB 就滚动成 .1（诊断期间默认常开，别让它无限长）
        try:
            if self._log_path.exists() and self._log_path.stat().st_size > 8 * 1024 * 1024:
                self._log_path.replace(self._log_path.with_suffix(".log.1"))
        except OSError:
            pass
        self._log_file = open(self._log_path, "a", encoding="utf-8", buffering=1)

        # ctypes 回调必须持有引用：临时对象被回收后，钩子会调到野指针上，直接崩进程
        self._hook = None
        self._proc = _WinEventProc(self._on_win_event)

        class _Filter(QObject):
            """顶层窗口事件过滤器（同一个实例可装到多个窗口上）。"""

            def __init__(self, owner: "WindowDiag") -> None:
                super().__init__()
                self._owner = owner

            def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名
                self._owner._on_widget_event(obj, event)
                return False

        self._filter = _Filter(self)

        class _AppFilter(QObject):
            """应用级事件：收到 Quit 说明有人调了 quit()/closeAllWindows()。"""

            def __init__(self, owner: "WindowDiag") -> None:
                super().__init__()
                self._owner = owner

            def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名
                if _EV_QUIT is not None and event.type() == _EV_QUIT:
                    self._owner.record("app.quit", "收到 QEvent::Quit", stack=_DEEP_STACK)
                    # 正常退出前主窗体一定收到过 Close；没收到就说明是异常退出
                    # （例如窗口已被销毁、或有人直接 quit()），才值得落盘。
                    if self._owner._quit_without_close():
                        self._owner._dump("应用收到 Quit，但主窗体没有走过正常的 Close")
                return False

        self._app_filter = _AppFilter(self)
        try:
            app.installEventFilter(self._app_filter)
        except Exception:  # noqa: BLE001
            self._app_filter = None

        self._hook = _user32.SetWinEventHook(
            _EVENT_OBJECT_DESTROY,
            _EVENT_OBJECT_HIDE,
            None,
            self._proc,
            self._pid,
            0,
            _WINEVENT_OUTOFCONTEXT,
        )

        self._timer = QTimer()
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        # 原生崩溃兜底：真出 SIGSEGV 时把崩线程的 Python 栈落到 faulthandler.log
        # （Qt 内部崩溃不会走 sys.excepthook，这是唯一能留下痕迹的地方）
        self._fault_file = None
        try:
            import faulthandler

            self._fault_file = open(log_dir() / "faulthandler.log", "a", encoding="utf-8")
            faulthandler.enable(self._fault_file)
        except Exception:  # noqa: BLE001
            self._fault_file = None

        self._write(f"=== 窗口诊断开启 pid={self._pid} {datetime.now():%Y-%m-%d %H:%M:%S} ===")
        self.record("diag.install", f"事件流：{self._log_path}")
        self._poll()  # 立刻登记当前已有的窗口（主窗体此时还没建也没关系，1s 内会补上）
        _logger.info("窗口诊断已开启：%s", self._log_path)

    # ------------------------------------------------------------------ 记录
    def record(self, kind: str, detail: str = "", *, stack: int = 0) -> str:
        site = ""
        try:
            from PySide6.QtWidgets import QApplication

            line = f"{time.monotonic() - self._started:9.3f}s  [{kind}]"
            if detail:
                line += f"  {detail}"
            modal = QApplication.activeModalWidget()
            if modal is not None:
                line += f"  {{modal={type(modal).__name__}}}"
            if stack:
                site = _call_site(stack + 1)
                line += "  @ " + site
            self._ring.append(line)
            self._write(line)
        except Exception:  # noqa: BLE001 - 诊断永远不能反过来搞崩程序
            pass
        return site

    def _write(self, line: str) -> None:
        try:
            self._log_file.write(line + "\n")
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ 原生事件
    def _on_win_event(self, hook, event, hwnd, id_object, id_child, thread, when):
        try:
            if id_object != _OBJID_WINDOW or not hwnd:
                return
            label = self._hwnds.get(int(hwnd))
            cls, title = _window_info(int(hwnd))
            mark = f"  <<< 跟踪中：{label}" if label else ""
            self.record(
                f"native.{_EVENT_NAMES.get(event, hex(event))}",
                f"hwnd={hwnd} {cls} {title!r}{mark}",
            )
            if label and event == _EVENT_OBJECT_DESTROY:
                anomaly = int(hwnd) in self._anomaly_dumped
                expected = self._destroy_expected(int(hwnd))
                if expected:
                    self.record("native.destroy_expected", f"hwnd={hwnd} {label}（Qt 已关窗，正常）")
                elif anomaly:
                    # 这个窗口的异常 Hide 已经落过盘，不重复写第二份
                    self.record(
                        "native.destroy_after_anomaly",
                        f"hwnd={hwnd} {label}（Hide 异常已落盘，此处只记录）",
                    )
                else:
                    # 关键信号：没有 Close、也没有可解释的 Hide，原生窗口就被销毁了
                    self._dump(f"窗口未经 Qt 的 Close 就被销毁：{label} hwnd={hwnd}")
                self._forget(int(hwnd))
        except Exception:  # noqa: BLE001 - 回调里绝不能抛
            pass

    # ------------------------------------------------------------------ Qt 事件
    def _on_widget_event(self, widget, event) -> None:
        try:
            etype = event.type()
            if etype not in _WATCHED_EVENTS:
                return
            if not widget.isWindow():
                return
            hwnd = int(widget.winId())
            tracked = hwnd in self._hwnds
            try:
                spontaneous = bool(event.spontaneous())
            except Exception:  # noqa: BLE001
                spontaneous = False
            # 被跟踪的窗口收到 Close / Hide 时把完整调用栈一起记下来。
            # 2026-10-29 的现场只留了 9 层，刚好在 SQLAlchemy 的 all() 处截断；
            # 这里改成深栈，下一次能直接看到业务层调用者。
            site = self.record(
                f"qt.{etype.name}",
                f"{type(widget).__name__} hwnd={hwnd} title={widget.windowTitle()!r}"
                + (f" spontaneous={spontaneous}" if etype in (_EV_HIDE, _EV_CLOSE, _EV_SHOW) else "")
                + (f"  跟踪中：{self._hwnds[hwnd]}" if tracked else ""),
                stack=_DEEP_STACK if tracked and etype in (_EV_HIDE, _EV_CLOSE) else 0,
            )
            if etype == _EV_CLOSE:
                # 明确关窗：之后的 Hide / 原生 DESTROY 都属正常。
                # 注意 closeEvent 可能被用户取消（未保存提示），所以这里只记
                # "收到 Close"；真正算关闭要等 Hide 真的跟上来（见下）。
                self._closed.add(hwnd)
                self._hidden.add(hwnd)
            elif etype == _EV_HIDE:
                self._hidden.add(hwnd)
                if hwnd in self._closed and hwnd == self._main_hwnd:
                    # Close 之后真的 Hide 了：这次关闭被接受
                    self._main_closed = True
                if self._is_anomalous_hide(widget, hwnd, spontaneous, site):
                    # 主窗体被 Hide，却没有先 Close、也不是最小化：
                    # hide() 本身不会销毁原生窗口，后续 DESTROY 很可能是
                    # QWindow.destroy()/QWidget.destroy() 或外部 DestroyWindow。
                    # 立刻落盘，把深栈留在现场。
                    self._incident += 1
                    self._anomaly_dumped.add(hwnd)
                    self._dump(
                        "主窗体被 Hide 但未走 close/minimize"
                        f"（spontaneous={spontaneous}，疑似原生窗口被销毁）："
                        f"{self._hwnds.get(hwnd, type(widget).__name__)} hwnd={hwnd} "
                        f"incident={self._incident}"
                    )
            elif etype == _EV_SHOW:
                self._hidden.discard(hwnd)
                self._closed.discard(hwnd)
                self._anomaly_dumped.discard(hwnd)
                if hwnd == self._main_hwnd:
                    self._main_closed = False
        except Exception:  # noqa: BLE001
            pass

    def _is_anomalous_hide(self, widget, hwnd: int, spontaneous: bool, site: str) -> bool:
        """主窗体"非正常 Hide"判定。

        正常路径只有三种：``close()``（先有 Close）、最小化（栈里有
        ``_on_minimize``/``showMinimized``，或 ``isMinimized()`` 为真）、
        系统级隐藏（spontaneous=True，如锁屏/显示桌面）。其余一律可疑。
        """
        if hwnd not in self._important:
            return False
        if hwnd in self._closed or spontaneous:
            return False
        if "_on_minimize" in site or "showMinimized" in site:
            return False
        try:
            if widget.isMinimized():
                return False
        except RuntimeError:
            return False
        return True

    @staticmethod
    def _close_was_ignored(widget) -> bool:
        """收到 Close 后窗口仍可见，且不是“closeEvent 正在弹模态框”。

        closeEvent 里弹“是否保存”确认框（2026-10-31 20:32 等现场）：从弹框到
        用户点按钮的整段时间窗口都可见，但 Close 并没有被取消。此期间不能把
        ``_closed`` 撤掉，否则用户确认后的正常 Hide 会被误判为异常 Hide。
        """
        from PySide6.QtWidgets import QApplication

        try:
            if not widget.isVisible():
                return False
        except RuntimeError:
            return False
        return QApplication.activeModalWidget() is None

    def _quit_without_close(self) -> bool:
        """收到 Quit 时主窗体是否没有走过正常 Close（用于过滤正常退出噪音）。"""
        if self._main_hwnd is not None:
            return not self._main_closed
        return any(hwnd not in self._closed for hwnd in self._important)

    def _forget(self, hwnd: int) -> None:
        """窗口已销毁：清理该 HWND 的所有跟踪状态（``_main_hwnd`` 保留给退出判定）。"""
        self._hwnds.pop(hwnd, None)
        self._widgets.pop(hwnd, None)
        self._hidden.discard(hwnd)
        self._closed.discard(hwnd)
        self._important.discard(hwnd)
        self._anomaly_dumped.discard(hwnd)

    def _destroy_expected(self, hwnd: int) -> bool:
        """该 HWND 被销毁是否属于"正常关窗"。

        主窗体（QMainWindow）走严格口径：只有明确收到过 Close 才算正常；
        ``hide()``/最小化都不会销毁原生窗口，没 Close 的 DESTROY 必须落盘。
        其它顶层窗口（菜单、提示、对话框）保持宽松口径，避免正常弹层退出刷屏。
        """
        reference = self._widgets.get(hwnd)
        widget = reference() if reference is not None else None
        if widget is None:
            return True  # widget 本身已销毁：正常
        if hwnd in self._important:
            return hwnd in self._closed
        if hwnd in self._hidden:
            return True
        try:
            return not widget.isVisible()
        except RuntimeError:
            return True

    # ------------------------------------------------------------------ 自检
    def _poll(self) -> None:
        """登记新出现的可视顶层窗口；校验已登记窗口的 HWND 是否还活着。"""
        try:
            import weakref

            from PySide6.QtWidgets import QApplication, QMainWindow

            for widget in QApplication.topLevelWidgets():
                if not _is_alive(widget):
                    continue
                try:
                    if not widget.isWindow() or not widget.isVisible():
                        continue
                    key = id(widget)
                    if key in self._tracked:
                        continue
                    hwnd = int(widget.winId())
                    label = f"{type(widget).__name__}:{widget.windowTitle()}"
                    self._tracked.add(key)
                    # 同一 HWND 只记一次（不同 widget 可能共用同一个原生窗口）
                    self._hwnds.setdefault(hwnd, label)
                    self._widgets.setdefault(hwnd, weakref.ref(widget))
                    self._hidden.discard(hwnd)
                    self._closed.discard(hwnd)
                    self._anomaly_dumped.discard(hwnd)
                    if isinstance(widget, QMainWindow):
                        # 主窗体消失是"必须落盘"的异常；弹窗/菜单保持宽松口径
                        self._important.add(hwnd)
                        self._main_hwnd = hwnd
                        self._main_closed = False
                    widget.installEventFilter(self._filter)
                    self.record("track", f"{label} hwnd={hwnd}")
                except (RuntimeError, TypeError):
                    continue

            # closeEvent 被取消（如“是否保存”里点取消）时窗口仍然可见：
            # 撤销“已关闭”标记，否则后续真正的异常销毁会被误判为正常。
            # 但 closeEvent 弹出模态确认框期间（2026-10-31 20:32 等五次现场）
            # 窗口同样可见——那不是“被取消”，此刻撤销标记会把随后的正常
            # Hide 误判成异常。只在“可见且当前没有任何模态框”时才判取消。
            main = self._main_hwnd
            if main is not None and main in self._closed:
                reference = self._widgets.get(main)
                widget = reference() if reference is not None else None
                if widget is not None and WindowDiag._close_was_ignored(widget):
                    self._closed.discard(main)
                    self._main_closed = False
                    self.record(
                        "close_ignored",
                        f"hwnd={main} Close 被 closeEvent 忽略，窗口仍在",
                    )

            for hwnd, label in list(self._hwnds.items()):
                if _user32.IsWindow(hwnd):
                    continue
                anomaly = hwnd in self._anomaly_dumped
                expected = self._destroy_expected(hwnd)
                self._forget(hwnd)
                if not expected and not anomaly:
                    self._dump(
                        f"自检发现窗口的 HWND 已失效（未收到 Close）：{label} hwnd={hwnd}"
                    )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ 落盘
    def _dump(self, reason: str) -> None:
        key = hash(reason)
        if key in self._dumped:
            return
        self._dumped.add(key)
        if self._dump_count >= _MAX_DUMPS:
            self._write(f"!!! 已达 dump 上限（{_MAX_DUMPS} 份），忽略：{reason}")
            return
        self._dump_count += 1
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = log_dir() / f"window_diag_{stamp}_{self._dump_count:02d}.dump.txt"
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(f"窗口诊断 dump —— {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                handle.write(f"原因：{reason}\n")
                handle.write(f"进程：pid={self._pid}\n")
                handle.write(
                    f"主窗体：hwnd={self._main_hwnd} closed={self._main_closed}\n"
                )
                handle.write(
                    f"异常 Hide 已落盘：{sorted(self._anomaly_dumped) or '无'}\n\n"
                )
                handle.write("== 跟踪表（首次见到时登记的可视顶层窗口）==\n")
                if not self._hwnds:
                    handle.write("  (空)\n")
                for hwnd, label in self._hwnds.items():
                    cls, title = _window_info(int(hwnd))
                    reference = self._widgets.get(hwnd)
                    widget = reference() if reference is not None else None
                    visible = minimized = state = "?"
                    if widget is not None:
                        try:
                            visible = str(widget.isVisible())
                            minimized = str(widget.isMinimized())
                            state = str(widget.windowState())
                        except RuntimeError:
                            pass
                    handle.write(
                        f"  hwnd={hwnd} {label} | 存活={bool(_user32.IsWindow(hwnd))} "
                        f"visible={visible} minimized={minimized} state={state} "
                        f"closed={hwnd in self._closed} "
                        f"anomaly={hwnd in self._anomaly_dumped} {cls} {title!r}\n"
                    )
                handle.write("\n== 本进程当前全部顶层窗口（EnumWindows）==\n")
                handle.write(_enumerate_process_windows(self._pid) + "\n")
                handle.write(
                    f"\n== 最近 {len(self._ring)} 条事件（时间 = 开启诊断后的秒数）==\n"
                )
                for line in self._ring:
                    handle.write(line + "\n")
                handle.write(
                    "\n== 此刻的 Python 栈 ==\n"
                    "（事件回调发生在消息循环里，真正动手的调用已经返回；"
                    "定位靠上面的时序：DESTROY 前最后几条 qt.* / rounded.* / principle.* 记录）\n"
                )
                import faulthandler

                faulthandler.dump_traceback(file=handle, all_threads=True)
        except Exception as error:  # noqa: BLE001
            _logger.error("窗口诊断落盘失败：%s", error)
            return
        _logger.error("窗口诊断：%s —— 已落盘 %s", reason, path)
        self._write(f"!!! DUMP {reason} -> {path}")

    # ------------------------------------------------------------------ 清理
    def dispose(self) -> None:
        try:
            self._timer.stop()
        except Exception:  # noqa: BLE001
            pass
        app_filter = getattr(self, "_app_filter", None)
        if app_filter is not None:
            try:
                self._app.removeEventFilter(app_filter)
            except Exception:  # noqa: BLE001
                pass
            self._app_filter = None
        try:
            import faulthandler

            faulthandler.disable()
        except Exception:  # noqa: BLE001
            pass
        if getattr(self, "_fault_file", None) is not None:
            try:
                self._fault_file.close()
            except Exception:  # noqa: BLE001
                pass
            self._fault_file = None
        if self._hook:
            try:
                _user32.UnhookWinEvent(self._hook)
            except Exception:  # noqa: BLE001
                pass
            self._hook = None
        self._proc = None
        try:
            self._log_file.close()
        except Exception:  # noqa: BLE001
            pass
        _logger.info("窗口诊断已关闭")


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _call_site(depth: int = 3) -> str:
    """``文件名:行号 函数`` 链（由内向外），用于埋点。"""
    import traceback

    frames = traceback.extract_stack()[:-2]
    picked = frames[-depth:] if depth else frames[-3:]
    return " <- ".join(f"{frame.name}@{os.path.basename(frame.filename)}:{frame.lineno}" for frame in reversed(picked))


def _is_alive(widget) -> bool:
    try:
        import shiboken6

        return shiboken6.isValid(widget)
    except Exception:  # noqa: BLE001
        return True


def _window_info(hwnd: int) -> tuple[str, str]:
    """(类名, 标题)；窗口正在销毁的过程中也尽量取到。"""
    if _user32 is None:
        return "", ""
    cls = ctypes.create_unicode_buffer(256)
    title = ctypes.create_unicode_buffer(256)
    try:
        _user32.GetClassNameW(hwnd, cls, 256)
        _user32.GetWindowTextW(hwnd, title, 256)
    except Exception:  # noqa: BLE001
        pass
    return cls.value, title.value


def _enumerate_process_windows(pid: int) -> str:
    """枚举本进程的全部顶层窗口（含隐藏），一行一个。"""
    from ctypes import wintypes

    lines: list[str] = []

    def _cb(hwnd, _lparam):
        owner_pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value != pid:
            return True
        cls, title = _window_info(int(hwnd))
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        exstyle = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        owner = _user32.GetWindow(hwnd, _GW_OWNER)
        flags = []
        if exstyle & _WS_EX_LAYERED:
            flags.append("LAYERED")
        if exstyle & _WS_EX_TOOLWINDOW:
            flags.append("TOOL")
        lines.append(
            f"  hwnd={hwnd:>10} 可见={str(bool(_user32.IsWindowVisible(hwnd))):<5} "
            f"({rect.left},{rect.top},{rect.right - rect.left},{rect.bottom - rect.top}) "
            f"owner={owner} {'|'.join(flags) or '-'} {cls} | {title!r}"
        )
        return True

    procedure = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_cb)
    _user32.EnumWindows(procedure, 0)
    return "\n".join(lines) if lines else "  (无)"
