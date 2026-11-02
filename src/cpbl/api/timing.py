"""請求計時：每個回應帶 ``Server-Timing`` 標頭，並以 ``cpbl.api.access`` logger 記一行耗時。

為什麼：#353 當時「P3 量不到——正式站 nginx 的 log 格式沒有 ``$request_time``」，於是每個端點
平常的耗時只能靠研究者臨時量。這裡在 app 層補上，之後任何部署的 ``docker logs`` 都有逐請求耗時；
也順帶回答「五支舊 outcome 端點到底有沒有外部呼叫者」這個一直沒查證的問題（AGENTS.md）。

- 回應標頭 ``Server-Timing: app;dur=<毫秒>``（標準標頭，瀏覽器 devtools 直接顯示在 Timing 分頁）。
- 一行 INFO log：``GET /api/v1/daily/summary?season=2026 200 12.3ms``。

純 ASGI middleware，⛔ 不用 Starlette 的 ``BaseHTTPMiddleware``：那個會把串流回應整個緩衝、改變
背景任務語意。⛔ 不吞例外：下游拋出照樣往上傳，log 只記已送出的狀態碼（沒送出就記 ``-``）。
⛔ 不改任何回應內容與狀態碼，``/api/info`` 永遠 200 的契約不受影響。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("cpbl.api.access")

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class RequestTimingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status: int | None = None

        async def send_with_timing(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                elapsed_ms = (time.perf_counter() - start) * 1000
                headers = list(message.get("headers", []))
                headers.append((b"server-timing", f"app;dur={elapsed_ms:.1f}".encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_timing)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            query = scope.get("query_string", b"").decode("latin-1")
            log.info(
                "%s %s%s %s %.1fms",
                scope.get("method", "-"),
                scope.get("path", ""),
                f"?{query}" if query else "",
                "-" if status is None else status,
                elapsed_ms,
            )
