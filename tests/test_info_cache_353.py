"""#353 WP3：``/api/info`` 行程內快取＋lifespan 預熱。

契約不變：恆回 200、``{status, version, metrics}``、metrics 欄位名稱與數值語意不改（主站 InfoPoller
原樣存）。改變的只有「何時查 DB」：背景每 ``CACHE_TTL_SECONDS`` 用一條連線重算一次，請求只讀快取。

全部以假 scalar 模擬 DB（零 DB、零網路）。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from cpbl import db
from cpbl.api.main import app
from cpbl.api.routers import info


class _FakeDb:
    """記下每一次 scalar 查詢；``fail=True`` 時每個查詢都拋錯（模擬 DB 掛掉／逾時）。"""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.opens = 0
        self.fail = False
        self.games = 10
        self.last_sync = datetime.now(UTC) - timedelta(hours=1)

    @contextmanager
    def open_scalar(self):
        self.opens += 1
        if self.fail:
            raise RuntimeError("db down")

        def scalar(sql, params=()):
            self.queries.append(sql)
            if self.fail:
                raise RuntimeError("db down")
            if "prod-sync" in sql:
                return self.last_sync
            if "max(game_date)" in sql or "max(refreshed_at)" in sql:
                return None
            if "cv_metrics" in sql:
                return None
            if sql == "SELECT count(*) FROM cpbl.games":
                return self.games
            return 1

        yield scalar


@pytest.fixture
def fake_db(monkeypatch):
    fake = _FakeDb()
    monkeypatch.setattr(info, "_open_scalar", fake.open_scalar)
    monkeypatch.setattr(db, "configure_api_timeouts", lambda **kw: None)
    yield fake
    info.stop_cache()


def test_without_lifespan_each_call_computes_fresh(fake_db) -> None:
    """未預熱（單測直接呼叫、CLI import）：行為同舊版——每次都算，不寫快取。"""
    info.info()
    info.info()
    assert fake_db.opens == 2
    assert info._CACHE.get() is None


def test_all_metrics_are_computed_on_one_connection(fake_db) -> None:
    body = info.info()
    assert fake_db.opens == 1, "14 項 metrics 必須共用一次借連線"
    assert len(fake_db.queries) >= 14
    assert body["status"] == "running"


def test_lifespan_warms_cache_and_first_request_does_not_touch_db(fake_db) -> None:
    with TestClient(app) as client:
        opens_after_startup = fake_db.opens
        queries_after_startup = len(fake_db.queries)
        assert opens_after_startup == 1, "lifespan startup 應先算一次（預熱）"
        res = client.get("/api/info")
        assert res.status_code == 200
        assert fake_db.opens == opens_after_startup, "預熱後第一個請求不得碰 DB"
        assert len(fake_db.queries) == queries_after_startup
        assert int(res.headers[info.COMPUTED_AT_HEADER]) > 0


def test_metrics_names_unchanged_by_cache(fake_db) -> None:
    """快取前後的 metrics 鍵集合必須相同（契約：不改欄位名稱）。"""
    direct = info.info()
    with TestClient(app) as client:
        cached = client.get("/api/info").json()
    assert set(cached) == {"status", "version", "metrics"}
    assert list(cached["metrics"]) == list(direct["metrics"])


def test_prod_sync_age_is_recomputed_at_request_time(fake_db, monkeypatch) -> None:
    """``prod_sync_age_hours``／``stalled`` 的語意是「現在距上次同步」：不得隨快取凍結。"""
    fake_db.last_sync = datetime.now(UTC) - timedelta(hours=35, minutes=59)
    info.start_cache()
    first = info.info()["metrics"]
    assert first["prod_sync_stalled"] is False
    later = datetime.now(UTC) + timedelta(minutes=2)
    monkeypatch.setattr(info, "_utcnow", lambda: later)
    second = info.info()["metrics"]
    assert second["prod_sync_stalled"] is True
    assert second["prod_sync_age_hours"] > first["prod_sync_age_hours"]
    assert second["prod_sync_last_at"] == first["prod_sync_last_at"]


def test_db_down_at_startup_still_returns_200_maintenance(fake_db) -> None:
    fake_db.fail = True
    with TestClient(app) as client:
        res = client.get("/api/info")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "maintenance"
    assert set(body) == {"status", "version", "metrics"}


def test_refresh_failure_keeps_previous_snapshot(fake_db) -> None:
    info.start_cache()
    good = info._CACHE.get()
    assert good is not None and good.ok
    fake_db.fail = True
    info._refresh()
    assert info._CACHE.get() is good, "重算失敗時保留上一份成功值"
    assert info.info()["status"] == "running"


def test_stale_snapshot_degrades_to_maintenance(fake_db, monkeypatch) -> None:
    """陳舊上限：背景重算一直失敗超過 CACHE_MAX_STALE_SECONDS，不再宣稱 running。"""
    info.start_cache()
    snap = info._CACHE.get()
    monkeypatch.setattr(info, "_wall", lambda: snap.computed_at + info.CACHE_MAX_STALE_SECONDS + 1)
    body = info.info()
    assert body["status"] == "maintenance"
    assert body["metrics"]["games_indexed"] == 10, "退化時 metrics 盡量帶（CLAUDE.md /api/info 準則）"


def test_ttl_is_far_below_infopoller_period() -> None:
    """主站 InfoPoller 每 5 分鐘輪詢：陳舊時間必須遠小於這個週期（規劃 §2.3）。"""
    assert info.CACHE_TTL_SECONDS <= 60
    assert info.CACHE_TTL_SECONDS < info.CACHE_MAX_STALE_SECONDS <= 300


def test_background_thread_stops_on_shutdown(fake_db) -> None:
    with TestClient(app):
        assert any(t.name == info._THREAD_NAME for t in threading.enumerate())
    assert not any(t.name == info._THREAD_NAME and t.is_alive() for t in threading.enumerate())


def test_games_zero_is_maintenance_but_cached_as_ok(fake_db) -> None:
    fake_db.games = 0
    info.start_cache()
    assert info.info()["status"] == "maintenance"
    assert info._CACHE.get().ok


def test_failed_warmup_retries_quickly_until_the_first_success(fake_db, monkeypatch) -> None:
    """部署當下預熱失敗：不得讓 maintenance 掛滿一個 TTL；有成功值後才回到 TTL 間隔。"""
    import time

    monkeypatch.setattr(info, "CACHE_RETRY_SECONDS", 0.05)
    fake_db.fail = True
    info._CACHE.start(ttl=60.0)
    assert info._CACHE.get() is not None and not info._CACHE.get().ok
    fake_db.fail = False
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not info._CACHE.get().ok:
        time.sleep(0.02)
    assert info._CACHE.get().ok, "沒有成功快照時應以短間隔重試"
    opens = fake_db.opens
    time.sleep(0.3)
    assert fake_db.opens == opens, "有成功快照後回到 TTL 間隔，不再頻繁重算"
