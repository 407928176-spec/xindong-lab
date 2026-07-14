"""FastAPI 应用入口：注册中间件与路由。"""

import app.dotenv_load  # noqa: F401 — 先于其它 ``app.*`` 导入，加载 backend/.env（override=False）

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.routes import attachments, characters, config, health, personas


class PrivateNetworkAccessMiddleware:
    """为带 Origin 的响应补上 ``Access-Control-Allow-Private-Network``。

    Chrome 等对「公网/本地页面访问 loopback 上另一主机名」（如 localhost:3000 → 127.0.0.1:8000）
    要求预检/响应携带该头；缺失时 fetch 会表现为 ``TypeError: Failed to fetch``，而后端路由可能已执行。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        has_origin = any(k.lower() == b"origin" for k, _ in scope.get("headers", []))

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and has_origin:
                headers = MutableHeaders(scope=message)
                headers.setdefault("Access-Control-Allow-Private-Network", "true")
            await send(message)

        await self.app(scope, receive, send_wrapper)


# 单一应用实例，供 uvicorn 以字符串路径加载：app.main:app
app = FastAPI(title="心动实验室 API", version="1.0.0")

# 前端直连后端时必须开启 CORS。
# 单机游戏只在本机跑，所以只放行本机来源。三种写法都要放行：localhost 可能解析到
# IPv6 的 ::1，与 127.0.0.1 在浏览器眼里是不同的 Origin。
_cors_origin_regex = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 须在 CORS 外层，以便把额外头写进 CORS 生成的 OPTIONS 响应。
app.add_middleware(PrivateNetworkAccessMiddleware)

app.include_router(health.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(personas.router, prefix="/api")
app.include_router(characters.router, prefix="/api")
