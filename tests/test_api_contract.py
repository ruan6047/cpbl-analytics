"""子專案契約測試：/api/info 永不拋錯（主站 InfoPoller 5 秒 timeout、非 200 視為不可達）。

DB 失效情境在 `cpbl.db._pool` 邊界模擬：換成一個未開啟的連線池，任何借連線立即
拋錯（不等 30 秒 pool timeout），驗證 info 端點降級為 maintenance 而非 500。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from cpbl import db
from cpbl.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def broken_db(monkeypatch):
    """把全域連線池換成永遠借不到連線的池（closed → 立即拋 PoolClosed）。"""
    dead = ConnectionPool("postgresql://x:x@127.0.0.1:1/x", open=False)
    monkeypatch.setattr(db, "_pool", dead)
    yield
    # monkeypatch 會還原 _pool；dead 池未開啟無需關閉


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_info_contract_shape_when_db_down(client, broken_db):
    """DB 掛掉：仍回 200、status 降級 maintenance、三鍵齊全。"""
    res = client.get("/api/info")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"status", "version", "metrics"}
    assert body["status"] == "maintenance"
    assert isinstance(body["metrics"], dict)


def test_info_status_vocabulary(client, broken_db):
    """status 只允許契約詞彙。"""
    res = client.get("/api/info")
    assert res.json()["status"] in ("running", "maintenance", "stopped")
