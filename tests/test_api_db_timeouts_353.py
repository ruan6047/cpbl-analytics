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


def test_default_values_are_the_ratified_insurance_values() -> None:
    """三個值依需求方裁定 6407182217；性質是保險，⛔ 不由此推導任何請求總耗時上界（規劃 r3）。"""
    assert settings.api_db_pool_timeout_seconds == 1.0
    assert settings.api_db_statement_timeout_ms == 3500
    assert settings.api_db_lock_timeout_ms == 2000


# --------------------------------------------------------------------------- 審核 2 回歸（規劃 r3 §3 第 5 項）
#
# 審核 2 第 2 項：aed693be 在 db.conn() 借出前送 SET LOCAL，非 autocommit 下隱式開交易，呼叫者的
# c.transaction() 變成 savepoint，SET TRANSACTION ISOLATION LEVEL REPEATABLE READ（watch_reader、
# report.py）因不是交易第一條語句而失敗。兩層都經**真的 API 請求路徑**（lifespan＋middleware＋路由），
# 所以任何「在 API 請求內、借出前送語句」的實作都會紅——不論它掛在哪一層。


class _RecordingConn:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql, *a, **k):
        self.executed.append(str(sql))


class _RecordingPool:
    def __init__(self) -> None:
        self.handed_out: list[_RecordingConn] = []

    def connection(self, timeout=None):
        from contextlib import contextmanager

        @contextmanager
        def cm():
            c = _RecordingConn()
            self.handed_out.append(c)
            yield c
        return cm()


def _api_client_with(monkeypatch):
    from cpbl.api import main
    from cpbl.api.routers import info

    monkeypatch.setattr(info, "start_cache", lambda: None)
    monkeypatch.setattr(info, "stop_cache", lambda: None)
    return TestClient(main.app)


def test_a_conn_hands_out_the_connection_without_running_any_statement(isolated_db_state, monkeypatch):
    """(a) 零 DB：API 設定生效、在真實請求路徑內，進入 ``with conn() as c`` 時連線上沒有任何語句。"""
    from cpbl.api.routers import recap

    pool = _RecordingPool()
    monkeypatch.setattr(db, "pool", lambda: pool)
    seen: list[list[str]] = []

    def load_game_row(*_a):
        with db.conn() as c:
            seen.append(list(c.executed))
        return None

    monkeypatch.setattr(recap, "_load_game_row", load_game_row)
    monkeypatch.setattr(recap, "_load_pa_rows", lambda *a: [])
    with _api_client_with(monkeypatch) as client:
        assert db._api_session == (settings.api_db_statement_timeout_ms, settings.api_db_lock_timeout_ms)
        res = client.get("/api/v1/games/1/recap-wp?season=2026&kind_code=A")
    assert res.status_code == 404
    assert seen == [[]], f"借出前不得對連線執行任何語句：{seen}"


_TXSHAPE_DB_ENV = "CPBL353_TXSHAPE_TEST_DATABASE_URL"


@pytest.mark.skipif(not __import__("os").getenv(_TXSHAPE_DB_ENV), reason=f"requires {_TXSHAPE_DB_ENV}")
def test_b_real_postgres_transaction_shapes_and_insurance_timeouts(monkeypatch):
    """(b) 拋棄式 PG：watch_reader 與 report.py 的交易形狀在 API 請求路徑上不變，逾時保險仍在。"""
    import os

    from cpbl.api.routers import report
    from cpbl.playoffs import watch_reader

    url = os.environ[_TXSHAPE_DB_ENV]
    assert url.rsplit("/", 1)[-1] == "cpbl353_txshape", "只在拋棄式資料庫上跑"
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "_api_session", None)
    monkeypatch.setattr(db, "_pool_timeout", db.DEFAULT_POOL_TIMEOUT_SECONDS)
    monkeypatch.setattr(db.settings, "database_url", url)
    seen: dict[str, list] = {}

    def show(cur, *names):
        out = []
        for name in names:
            cur.execute(f"SHOW {name}")
            out.append(cur.fetchone()[0])
        return out

    def read_watch_inputs(cur, *a, **k):  # ① 真的 playoffs_watch：c.transaction() → SET TRANSACTION → 這裡
        seen["watch"] = show(cur, "transaction_isolation", "transaction_read_only")
        return None

    monkeypatch.setattr(watch_reader, "read_watch_inputs", read_watch_inputs)
    monkeypatch.setattr(watch_reader, "compute_watch", lambda inputs, now: {"ok": True})

    def report_anchor(cur, *a):  # ② 真的 report-anchor：c.execute(SET TRANSACTION) → 這裡；③ 逾時保險
        seen["report"] = show(cur, "transaction_isolation", "statement_timeout", "lock_timeout")
        return {}

    monkeypatch.setattr(report, "report_anchor", report_anchor)
    try:
        with _api_client_with(monkeypatch) as client:
            watch = client.get("/api/v1/playoffs/watch?season=2026&series=C")
            anchor = client.get("/api/v1/games/1/report-anchor?season=2026&kind_code=C")
    finally:
        if db._pool is not None:
            db._pool.close()
    print(f"watch={watch.status_code} {seen.get('watch')} report-anchor={anchor.status_code} {seen.get('report')}")
    assert watch.status_code == 200 and seen["watch"] == ["repeatable read", "on"]
    assert anchor.status_code == 200 and seen["report"] == ["repeatable read", "3500ms", "2s"]
