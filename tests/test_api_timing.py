"""``cpbl.api.timing``：Server-Timing 標頭、access log、例外不被吞、掛在最外層。"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cpbl.api.timing import RequestTimingMiddleware


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("downstream failure")

    app.add_middleware(RequestTimingMiddleware)
    return app


def test_adds_server_timing_header_and_logs_one_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="cpbl.api.access"):
        r = TestClient(_app()).get("/ping?season=2026")
    assert r.status_code == 200 and r.json() == {"ok": True}
    header = r.headers["server-timing"]
    assert header.startswith("app;dur=")
    assert float(header.removeprefix("app;dur=")) >= 0
    lines = [rec.getMessage() for rec in caplog.records if rec.name == "cpbl.api.access"]
    assert len(lines) == 1
    assert lines[0].startswith("GET /ping?season=2026 200 ") and lines[0].endswith("ms")


def test_exceptions_propagate_and_are_logged_without_status(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(_app(), raise_server_exceptions=True)
    with caplog.at_level(logging.INFO, logger="cpbl.api.access"), pytest.raises(RuntimeError):
        client.get("/boom")
    lines = [rec.getMessage() for rec in caplog.records if rec.name == "cpbl.api.access"]
    assert len(lines) == 1 and lines[0].startswith("GET /boom - ")


def test_non_http_scopes_pass_through() -> None:
    seen: list[str] = []

    async def inner(scope, receive, send) -> None:  # noqa: ANN001 — ASGI 簽名
        seen.append(scope["type"])

    import asyncio

    asyncio.run(RequestTimingMiddleware(inner)({"type": "lifespan"}, None, None))  # type: ignore[arg-type]
    assert seen == ["lifespan"]


def test_real_app_mounts_timing_outermost() -> None:
    from cpbl.api.main import app

    assert app.user_middleware[0].cls is RequestTimingMiddleware
