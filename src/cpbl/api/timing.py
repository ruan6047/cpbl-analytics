"""請求計時：每個回應帶 ``Server-Timing`` 標頭，並以 ``cpbl.api.access`` logger 記一行耗時。

為什麼：#353 當時「P3 量不到——正式站 nginx 的 log 格式沒有 ``$request_time``」，於是每個端點
平常的耗時只能靠研究者臨時量。這裡在 app 層補上，之後任何部署的 ``docker logs`` 都有逐請求耗時；
也順帶回答「五支舊 outcome 端點到底有沒有外部呼叫者」這個一直沒查證的問題（AGENTS.md）。

- 回應標頭 ``Server-Timing: app;dur=<毫秒>``（標準標頭，瀏覽器 devtools 直接顯示在 Timing 分頁）。
- 一行 INFO log：``GET /api/v1/daily/summary?season=2026 200 12.3ms``。這一行要靠 ``configure_access_log()``
  才真的會印：uvicorn 的預設 LOGGING_CONFIG 只設定 ``uvicorn.*`` 三個 logger，root 仍是 WARNING 且沒有 handler，
  ``cpbl.api.access`` 的 INFO 會被 root 等級吞掉——#405 上線後只驗到標頭、容器 log 從未出現這一行，就是這個原因。
  ``main.py`` 在組裝 app 時呼叫一次，容器 CMD 則以 ``--no-access-log`` 關掉 uvicorn 自己那份重複的 access log。

純 ASGI middleware，⛔ 不用 Starlette 的 ``BaseHTTPMiddleware``：那個會把串流回應整個緩衝、改變
背景任務語意。⛔ 不吞例外：下游拋出照樣往上傳，log 只記已送出的狀態碼（沒送出就記 ``-``）。
⛔ 不改任何回應內容與狀態碼，``/api/info`` 永遠 200 的契約不受影響。
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("cpbl.api.access")

_HANDLER_NAME = "cpbl.api.access.stdout"


class _StdoutHandler(logging.StreamHandler):
    """每次 emit 時才取 ``sys.stdout``：uvicorn／pytest 會換掉 stdout 物件，不能在建立時綁死。"""

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    @property
    def stream(self):  # type: ignore[override]  # noqa: ANN201 — 與 StreamHandler.stream 同型
        return sys.stdout

    @stream.setter
    def stream(self, _value: Any) -> None:  # StreamHandler.__init__／setStream 會賦值，忽略即可
        return None


def configure_access_log() -> logging.Logger:
    """讓 ``cpbl.api.access`` 在 uvicorn 預設 logging 下真的印到 stdout（見模組說明）。

    冪等：重複呼叫不會加第二個 handler。保留 ``propagate``：pytest 的 caplog 靠 root handler 收紀錄；
    root 預設沒有 handler，所以正式站不會重複印。格式對齊 uvicorn 的 ``INFO:     …`` 前綴。
    """
    if not any(h.get_name() == _HANDLER_NAME for h in log.handlers):
        handler = _StdoutHandler()
        handler.set_name(_HANDLER_NAME)
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    return log

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
