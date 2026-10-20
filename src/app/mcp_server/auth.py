"""Bearer token 鉴权中间件（仅本机回环场景）。

防止本机其它进程 / 网页（DNS rebinding）驱动 Section2 改数据。
"""

from __future__ import annotations

import secrets

from starlette.responses import JSONResponse


def generate_token() -> str:
    """生成 MCP 访问 token。"""
    return secrets.token_urlsafe(32)


class BearerAuthMiddleware:
    """纯 ASGI 中间件：校验 Authorization: Bearer <token>。"""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in (scope.get("headers") or [])}
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        if authorization != f"Bearer {self.token}":
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
