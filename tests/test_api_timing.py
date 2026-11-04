"""``cpbl.api.timing``：Server-Timing 標頭、access log、例外不被吞、掛在最外層。"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cpbl.api.timing import RequestTimingMiddleware, configure_access_log


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


def test_access_log_reaches_stdout_under_uvicorn_default_logging(capfd: pytest.CaptureFixture[str]) -> None:
    """uvicorn 的 LOGGING_CONFIG 不碰 root（WARNING、無 handler）；沒有 configure_access_log 這行 INFO 永遠不會出現。"""
    import logging.config

    import uvicorn.config

    logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)
    logger = configure_access_log()
    configure_access_log()  # 冪等：不加第二個 handler
    assert [h.get_name() for h in logger.handlers].count("cpbl.api.access.stdout") == 1
    assert logger.isEnabledFor(logging.INFO) and logger.propagate

    TestClient(_app()).get("/ping")
    out, err = capfd.readouterr()
    assert "INFO:     GET /ping 200 " in out and "ms" in out
    assert "GET /ping" not in err


def test_real_app_configures_access_log() -> None:
    import cpbl.api.main  # noqa: F401 — 組裝時呼叫 configure_access_log

    logger = logging.getLogger("cpbl.api.access")
    assert any(h.get_name() == "cpbl.api.access.stdout" for h in logger.handlers)
    assert logger.isEnabledFor(logging.INFO)
