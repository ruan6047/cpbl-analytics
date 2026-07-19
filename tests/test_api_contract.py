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
from cpbl.api.routers import info


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


def test_info_freshness_metrics_use_completed_game_contract(monkeypatch):
    """未完成保留賽的中止比分不得推高 completed 或最後比賽日。"""
    queries: list[str] = []

    def scalar(sql, params=()):
        queries.append(sql)
        if "max(game_date)" in sql:
            return None
        return 0

    monkeypatch.setattr(info, "_scalar", scalar)

    body = info.info()

    assert body["metrics"]["season_games_completed"] == 0
    assert any(
        "WHERE year = %s AND home_score + away_score > 0 AND game_date <= CURRENT_DATE" in sql
        for sql in queries
    )
    assert any(
        "SELECT max(game_date) FROM cpbl.games "
        "WHERE home_score + away_score > 0 AND game_date <= CURRENT_DATE" in sql
        for sql in queries
    )


def test_matchup_query_parameters_are_exposed_in_openapi():
    paths = app.openapi()["paths"]

    roster_params = {
        parameter["name"]
        for parameter in paths["/api/v1/players/roster"]["get"]["parameters"]
    }
    assert {"role", "season", "q", "limit"} <= roster_params

    player_params = {
        parameter["name"]
        for parameter in paths["/api/v1/players/{player_id}/matchups"]["get"]["parameters"]
    }
    assert {
        "role",
        "kind_code",
        "scope",
        "season",
        "from_year",
        "to_year",
        "opponent_team",
        "opponent_id",
        "limit",
        "sort",
        "order",
    } <= player_params

    detail_params = {
        parameter["name"] for parameter in paths["/api/v1/matchups"]["get"]["parameters"]
    }
    assert {"kind_code", "scope", "season", "from_year", "to_year"} <= detail_params
