"""GUI 进程内 MCP server 生命周期（单例）。

启动 = 读取 [mcp] 配置 → 必要时生成 token → 后台线程跑 uvicorn；
停止 = 置 should_exit 并等待线程退出。工程打开/关闭不影响服务生命周期
（工具运行时自己报“未打开工程”）。
"""

from __future__ import annotations

import threading
import time

from app.agent import tool_registry
from app.core.config import get_config, update_config
from app.mcp_server.adapter import McpToolAdapter
from app.mcp_server.auth import generate_token
from app.mcp_server.server import build_http_app


class McpServerController:
    _instance: "McpServerController | None" = None

    @classmethod
    def instance(cls) -> "McpServerController":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._server = None
        self._thread: threading.Thread | None = None
        self._error = ""

    # ------------------------------------------------------------------ 状态
    @property
    def url(self) -> str:
        config = get_config()
        return f"http://127.0.0.1:{config.mcp_port}/mcp"

    def running(self) -> bool:
        return bool(self._server is not None and getattr(self._server, "started", False))

    def status(self) -> dict:
        config = get_config()
        return {
            "running": self.running(),
            "url": self.url,
            "port": config.mcp_port,
            "token": config.mcp_token,
            "allow_actions": config.mcp_allow_actions,
            "require_confirmation": config.mcp_require_confirmation,
            "error": self._error,
        }

    # ------------------------------------------------------------------ 启停
    def start(self) -> tuple[bool, str]:
        if self.running():
            return True, f"MCP 服务已在运行：{self.url}"
        config = get_config()
        token = config.mcp_token
        if not token:
            token = generate_token()
            update_config({"mcp": {"token": token}})
        adapter = McpToolAdapter(
            tool_registry.default_registry(), allow_actions=config.mcp_allow_actions
        )
        app = build_http_app(adapter, token=token)
        import uvicorn

        self._error = ""
        try:
            self._server = uvicorn.Server(
                uvicorn.Config(app, host="127.0.0.1", port=config.mcp_port, log_level="warning")
            )
            self._thread = threading.Thread(target=self._server.run, daemon=True)
            self._thread.start()
        except Exception as error:  # noqa: BLE001
            self._error = str(error)
            self._server = None
            return False, f"MCP 服务启动失败：{error}"
        for _ in range(40):
            if getattr(self._server, "started", False):
                return True, f"MCP 服务已启动：{self.url}"
            if getattr(self._server, "should_exit", False):
                break
            time.sleep(0.1)
        self._error = f"端口 {config.mcp_port} 可能被占用"
        return False, f"MCP 服务启动失败：{self._error}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._server = None
        self._thread = None
