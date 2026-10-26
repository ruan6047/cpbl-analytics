"""#353 WP2：API 讀端逾時只在 API 行程（uvicorn lifespan）生效。

背景（研究 2 事實）：每日鏈第 3 步 PA 同步持 ACCESS EXCLUSIVE 約 7 分 20 秒，API 連線池 8 條
全被等鎖的查詢占滿，連 ``/api/info`` 都等不到連線。WP2 讓一條卡住的路徑快速失敗、不拖垮整個池：
借池逾時、session ``statement_timeout``、session ``lock_timeout``。

⛔ ``migrate()``、``cpbl-train*``、ingest CLI 是不同行程、合法地會跑超過 4 秒，不得吃到這些值——
所以設定點是 ``cpbl.api.main`` 的 lifespan（只有 uvicorn 起 app 時才跑），不是 import 時。

本檔不需要 DB：以假連線記下 ``_configure`` 送出的 SQL、以 monkeypatch 隔離全域池。
鎖注入下池不耗盡的行為證據在拋棄式 DB 上跑（``~/.wf-evidence/cpbl-analytics/353/exec-1/``）。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from cpbl import db
from cpbl.config import settings


class _FakeConn:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.committed = False

    def execute(self, sql: str) -> None:
        self.sql.append(sql)

    def commit(self) -> None:
        self.committed = True


@pytest.fixture
def isolated_db_state(monkeypatch):
    """configure_api_timeouts 會改模組全域；monkeypatch 讓每個測試結束後還原。"""
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "_api_session", None)
    monkeypatch.setattr(db, "_pool_timeout", db.DEFAULT_POOL_TIMEOUT_SECONDS)
    monkeypatch.setattr(db, "_request_budget_s", None)


def test_default_session_has_only_timezone(isolated_db_state) -> None:
    """未經 API lifespan（CLI、migrate、訓練）：連線只設時區，沒有任何逾時。"""
    c = _FakeConn()
    db._configure(c)
    assert c.sql == [f"SET TIME ZONE '{db.SESSION_TIMEZONE}'"]
    assert c.committed
    assert db._pool_timeout == 30.0, "非 API 行程的借池等待維持 psycopg_pool 預設 30s"


def test_api_timeouts_are_applied_to_new_connections(isolated_db_state) -> None:
    db.configure_api_timeouts(pool_timeout_s=3.0, statement_timeout_ms=4000, lock_timeout_ms=2000)
    c = _FakeConn()
    db._configure(c)
    assert c.sql == [
        f"SET TIME ZONE '{db.SESSION_TIMEZONE}'",
        "SET statement_timeout = 4000",
        "SET lock_timeout = 2000",
    ]
    assert c.committed, "configure 回傳前必須結束交易，否則 pool 會丟棄該連線"
    assert db._pool_timeout == 3.0


def test_configure_api_timeouts_discards_a_pool_created_before_it(isolated_db_state, monkeypatch):
    """已建立的池是用舊設定開的連線；必須關掉重建，否則逾時對既有連線不生效。"""
    closed: list[bool] = []

    class _Pool:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(db, "_pool", _Pool())
    db.configure_api_timeouts(pool_timeout_s=3.0, statement_timeout_ms=4000, lock_timeout_ms=2000)
    assert closed == [True]
    assert db._pool is None


@pytest.mark.parametrize("bad", [
    {"pool_timeout_s": 0, "statement_timeout_ms": 4000, "lock_timeout_ms": 2000},
    {"pool_timeout_s": 3.0, "statement_timeout_ms": -1, "lock_timeout_ms": 2000},
    {"pool_timeout_s": 3.0, "statement_timeout_ms": 4000, "lock_timeout_ms": -5},
])
def test_configure_api_timeouts_rejects_invalid_values(isolated_db_state, bad) -> None:
    with pytest.raises(ValueError):
        db.configure_api_timeouts(**bad)


def test_pool_uses_configured_checkout_timeout(isolated_db_state, monkeypatch) -> None:
    seen: dict = {}

    class _Pool:
        def __init__(self, *args, **kwargs) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(db, "ConnectionPool", _Pool)
    db.configure_api_timeouts(pool_timeout_s=3.0, statement_timeout_ms=4000, lock_timeout_ms=2000)
    db.pool()
    assert seen["timeout"] == 3.0
    assert seen["max_size"] == 8, "WP2 不加大池（規劃 §2.2）"


def test_api_lifespan_applies_settings_and_cli_import_does_not(monkeypatch) -> None:
    """只有 uvicorn 起 app（lifespan）才套逾時；單純 import app（測試、腳本）不套。"""
    calls: list[dict] = []
    monkeypatch.setattr(db, "configure_api_timeouts", lambda **kw: calls.append(kw))
    from cpbl.api import main
    from cpbl.api.routers import info

    monkeypatch.setattr(info, "start_cache", lambda: None, raising=False)
    monkeypatch.setattr(info, "stop_cache", lambda: None, raising=False)

    assert calls == [], "import cpbl.api.main 不得套 API 逾時"
    with TestClient(main.app):
        pass
    assert calls == [{
        "pool_timeout_s": settings.api_db_pool_timeout_seconds,
        "statement_timeout_ms": settings.api_db_statement_timeout_ms,
        "lock_timeout_ms": settings.api_db_lock_timeout_ms,
        "request_budget_ms": settings.api_db_request_budget_ms,
    }]


def test_migrate_and_cli_entrypoints_never_call_api_timeouts() -> None:
    """碼面守衛：設定點只在 API lifespan；migrate／訓練／ingest 不得呼叫。"""
    from pathlib import Path

    root = Path(__file__).parents[1] / "src" / "cpbl"
    callers = sorted(
        str(p.relative_to(root)) for p in root.rglob("*.py")
        if "configure_api_timeouts(" in p.read_text(encoding="utf-8") and p.name != "db.py"
    )
    assert callers == ["api/main.py"], callers


def test_default_request_budget_is_under_the_5s_acceptance_bound() -> None:
    """整個請求的 DB 時間由預算封頂（不是「借池＋一條語句」——審核 1 第 4 項）。"""
    assert 0 < settings.api_db_request_budget_ms < 5000
    assert settings.api_db_pool_timeout_seconds * 1000 < settings.api_db_request_budget_ms
    assert 0 < settings.api_db_lock_timeout_ms <= settings.api_db_statement_timeout_ms


# --------------------------------------------------------------------------- 請求預算（零 DB）


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class _BudgetConn:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str) -> None:
        self.sql.append(sql)


class _BudgetPool:
    def __init__(self, clock: _Clock, wait: float = 0.0) -> None:
        self.clock, self.wait, self.timeouts, self.conns = clock, wait, [], []

    def connection(self, timeout=None):
        from contextlib import contextmanager

        @contextmanager
        def cm():
            self.timeouts.append(timeout)
            self.clock.t += self.wait
            c = _BudgetConn()
            self.conns.append(c)
            yield c
        return cm()


@pytest.fixture
def budget_env(isolated_db_state, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(db.time, "monotonic", clock)
    db.configure_api_timeouts(pool_timeout_s=1.0, statement_timeout_ms=3500, lock_timeout_ms=2000,
                              request_budget_ms=4500)
    pool = _BudgetPool(clock)
    monkeypatch.setattr(db, "pool", lambda: pool)
    return clock, pool


def test_each_borrow_is_capped_by_the_remaining_request_budget(budget_env) -> None:
    """審核 1 第 4 項的形狀：兩條查詢各 2.6s——第二次借用只剩 1.9s 可用。"""
    clock, pool = budget_env
    with db.request_budget():
        with db.conn() as c:
            assert c.sql == ["SET LOCAL statement_timeout = 3500", "SET LOCAL lock_timeout = 2000"]
            clock.t += 2.6
        with db.conn() as c:
            assert c.sql == ["SET LOCAL statement_timeout = 1900", "SET LOCAL lock_timeout = 1900"]
            clock.t += 1.9
        with pytest.raises(db.RequestBudgetExceeded):
            with db.conn():
                pass
    assert pool.timeouts == [1.0, 1.0], "借池等待仍受 1.0s 上限"
    with db.request_budget():
        clock.t += 3.8
        with db.conn():
            pass
    assert pool.timeouts[-1] == pytest.approx(0.7), "剩餘預算小於借池上限時，借池等待跟著縮短"


def test_pool_wait_counts_against_the_budget(budget_env) -> None:
    clock, pool = budget_env
    pool.wait = 4.6
    with db.request_budget():
        with pytest.raises(db.RequestBudgetExceeded):
            with db.conn():
                pass


def test_without_a_request_context_conn_is_unchanged(budget_env) -> None:
    """背景執行緒（/api/info 快取重算）與 CLI：沒有請求截止時刻，不加 SET LOCAL。"""
    _, pool = budget_env
    with db.conn() as c:
        assert c.sql == []
    assert pool.timeouts == [None]


def test_budget_is_a_no_op_until_configured(isolated_db_state) -> None:
    with db.request_budget():
        assert db._request_deadline.get() is None


def test_middleware_sets_the_deadline_inside_sync_endpoints(monkeypatch) -> None:
    """同步端點在 threadpool 執行；截止時刻必須跟著 context 進去，且請求結束後清掉。"""
    from cpbl.api import main
    from cpbl.api.routers import info, recap

    monkeypatch.setattr(db, "_request_budget_s", 4.5)
    seen: list = []
    monkeypatch.setattr(recap, "_load_game_row", lambda *a: seen.append(db._request_deadline.get()) or None)
    monkeypatch.setattr(recap, "_load_pa_rows", lambda *a: [])
    monkeypatch.setattr(info, "start_cache", lambda: None)
    monkeypatch.setattr(db, "configure_api_timeouts", lambda **kw: None)
    res = TestClient(main.app).get("/api/v1/games/1/recap-wp?season=2026&kind_code=A")
    assert res.status_code == 404
    assert seen and seen[0] is not None
    assert db._request_deadline.get() is None


# --------------------------------------------------------------------------- 請求預算（拋棄式 DB）

_BUDGET_DB_ENV = "CPBL353_BUDGET_TEST_DATABASE_URL"


@pytest.mark.skipif(not __import__("os").getenv(_BUDGET_DB_ENV), reason=f"requires {_BUDGET_DB_ENV}")
def test_real_postgres_two_slow_queries_stay_within_the_budget(monkeypatch) -> None:
    """審核 1 第 4 項的反例在真 PostgreSQL 上重現：兩條各 2.6s，無預算＝>5.2s；有預算＝<5s。"""
    import os

    import psycopg

    url = os.environ[_BUDGET_DB_ENV]
    assert url.rsplit("/", 1)[-1] == "cpbl353_budget", "只在拋棄式資料庫上跑"
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "_api_session", None)
    monkeypatch.setattr(db.settings, "database_url", url)

    def two_queries() -> tuple[float, str]:
        t0 = time.monotonic()
        outcome = "ok"
        try:
            with db.request_budget():
                for _ in range(2):
                    with db.conn() as c:
                        c.execute("SELECT pg_sleep(2.6)")
        except (psycopg.errors.QueryCanceled, db.RequestBudgetExceeded) as exc:
            outcome = type(exc).__name__
        return time.monotonic() - t0, outcome

    try:
        db.configure_api_timeouts(pool_timeout_s=1.0, statement_timeout_ms=3500, lock_timeout_ms=2000)
        db.pool().wait()
        control, control_outcome = two_queries()
        db.configure_api_timeouts(pool_timeout_s=1.0, statement_timeout_ms=3500, lock_timeout_ms=2000,
                                  request_budget_ms=4500)
        db.pool().wait()
        bounded, bounded_outcome = two_queries()
    finally:
        if db._pool is not None:
            db._pool.close()
    print(f"control={control:.3f}s({control_outcome}) bounded={bounded:.3f}s({bounded_outcome})")
    assert control > 5.2 and control_outcome == "ok"
    assert bounded < 5.0 and bounded_outcome == "QueryCanceled"
