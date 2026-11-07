"""測試共用：列舉 FastAPI app 實際註冊的 APIRoute（含 include_router 掛入的子路由）。

fastapi 0.137.0 起 `app.include_router()` 不再把子路由攤平成 `APIRoute` 放進 `app.routes`，
而是放一個包裝物件（帶 `original_router` 與 `include_context`）。只掃 `app.routes` 頂層
`isinstance(r, APIRoute)` 會得到 0 條，讓路由守衛測試失敗或靜默空轉。

本 helper 遇 `APIRoute` 直接收，遇帶 `original_router` 的包裝物件就下鑽
`original_router.routes`，並把沿途的 `include_context.prefix` 拼在路徑前面；舊版（攤平）
與新版（包裝）同一份程式碼都適用，不做版本判斷。

⚠️ `original_router`／`include_context` 是 FastAPI 私有實作細節。若未來再改內部結構，
這裡會少抓或抓到 0 條；呼叫端一律搭配非空斷言（`MIN_EXPECTED_ROUTES` 或與 EXPECTED
等值比對），讓失效變成大聲失敗，而不是空轉綠。不看 OpenAPI，是因為
`include_in_schema=False` 的路由（含隱藏的寫入方法）不會出現在 schema 裡。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from fastapi.routing import APIRoute

# 本專案目前 81 條；低於此數代表列舉手段失效，不是端點真的少了。
MIN_EXPECTED_ROUTES = 70


def _walk(routes: Iterable[object], prefix: str) -> Iterator[tuple[str, frozenset[str]]]:
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, frozenset(route.methods or ())
            continue
        original_router = getattr(route, "original_router", None)
        if original_router is None:
            continue
        include_context = getattr(route, "include_context", None)
        child_prefix = getattr(include_context, "prefix", "") or ""
        yield from _walk(original_router.routes, prefix + child_prefix)


def api_routes(app) -> list[tuple[str, frozenset[str]]]:
    """回傳 app 所有 APIRoute 的 (完整路徑, methods)，依註冊順序。"""
    return list(_walk(app.routes, ""))


def api_route_paths(app) -> frozenset[str]:
    """回傳 app 所有 APIRoute 的完整路徑集合。"""
    return frozenset(path for path, _ in api_routes(app))
