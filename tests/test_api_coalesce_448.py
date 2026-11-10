"""#448：8 支未快取端點的「到達後合併」（cpbl.api.coalesce）。

判準 F1（需求方核定）：每個請求拿到的資料，讀取必須在該請求抵達**之後**才開始；不跨請求保留回應。
這裡全部以假計算驗證機制本身與 8 支接線，不連 DB。
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from cpbl.api import coalesce
from cpbl.api.coalesce import Coalescer


def _start(fn, *args):
    out: dict = {}

    def run():
        try:
            out["value"] = fn(*args)
        except BaseException as e:  # noqa: BLE001
            out["error"] = e

    t = threading.Thread(target=run)
    t.start()
    return t, out


def _wait_until(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.005)
    return False


class _Gate:
    """假計算：每次呼叫記下開始序號，然後卡住直到被放行；回傳開始序號。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.started: list[int] = []
        self.release: list[threading.Event] = []
        self.active = 0
        self.max_active = 0

    def __call__(self):
        ev = threading.Event()
        with self.lock:
            n = len(self.started) + 1
            self.started.append(n)
            self.release.append(ev)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        ev.wait(5)
        with self.lock:
            self.active -= 1
        return n

    def open(self, i):
        self.release[i - 1].set()


def test_arrival_during_computation_gets_next_batch_not_current():
    """F1：計算進行中抵達的請求⛔ 不拿那一批的結果，而是拿下一批（抵達後才開始）的結果。"""
    c = Coalescer()
    g = _Gate()
    t1, o1 = _start(c.run, "k", g)
    assert _wait_until(lambda: g.started == [1])
    t2, o2 = _start(c.run, "k", g)          # 第 1 批計算中抵達
    t3, o3 = _start(c.run, "k", g)
    time.sleep(0.05)
    assert g.started == [1]                 # 第 2 批要等第 1 批結束才開始
    g.open(1)
    t1.join(2)
    assert o1["value"] == 1
    assert _wait_until(lambda: g.started == [1, 2])
    g.open(2)
    t2.join(2)
    t3.join(2)
    assert o2["value"] == 2 and o3["value"] == 2


def test_same_key_runs_at_most_one_computation():
    c = Coalescer()
    g = _Gate()
    threads = [_start(c.run, "k", g) for _ in range(6)]
    assert _wait_until(lambda: len(g.started) == 1)
    g.open(1)
    assert _wait_until(lambda: len(g.started) == 2)
    g.open(2)
    for t, _ in threads:
        t.join(2)
    assert g.max_active == 1
    assert len(g.started) == 2              # 6 個請求只算 2 次（領頭 1 次＋下一批 1 次）


def test_different_keys_do_not_block_each_other():
    c = Coalescer()
    g = _Gate()
    ta, _ = _start(c.run, "a", g)
    tb, _ = _start(c.run, "b", g)
    assert _wait_until(lambda: len(g.started) == 2)
    assert g.max_active == 2
    g.open(1)
    g.open(2)
    ta.join(2)
    tb.join(2)


def test_result_is_not_retained_after_batch():
    c = Coalescer()
    calls = []
    assert c.run("k", lambda: calls.append(1) or len(calls)) == 1
    assert c.run("k", lambda: calls.append(1) or len(calls)) == 2   # 依序請求每次都重算
    assert c.inflight_keys() == 0                                    # 沒有殘留狀態


def _failing_then(values):
    """依序回傳／拋出 values 的假計算（例外物件就拋出）。"""
    it = iter(values)
    lock = threading.Lock()
    started = threading.Event()
    gate = threading.Event()

    def fn():
        with lock:
            v = next(it)
        started.set()
        gate.wait(5)
        if isinstance(v, BaseException):
            raise v
        return v

    return fn, started, gate


def test_leader_failure_does_not_cascade_followers_retry_once():
    """R2：領頭失敗⛔ 不連坐；同批跟隨者重新排入下一批（每個請求最多一次）。"""
    c = Coalescer()
    fn, started, gate = _failing_then([RuntimeError("pool"), "ok"])
    t1, o1 = _start(c.run, "k", fn)
    assert started.wait(2)
    t2, o2 = _start(c.run, "k", fn)
    time.sleep(0.05)
    gate.set()
    t1.join(2)
    t2.join(2)
    assert isinstance(o1["error"], RuntimeError)
    assert o2["value"] == "ok"


def test_follower_second_failure_returns_error():
    c = Coalescer()
    fn, started, gate = _failing_then([RuntimeError("a"), RuntimeError("b")])
    t1, o1 = _start(c.run, "k", fn)
    assert started.wait(2)
    t2, o2 = _start(c.run, "k", fn)
    time.sleep(0.05)
    gate.set()
    t1.join(2)
    t2.join(2)
    assert isinstance(o1["error"], RuntimeError)
    assert str(o2["error"]) == "b"


def test_http_5xx_is_retried_but_4xx_is_shared():
    c = Coalescer()
    fn, started, gate = _failing_then([HTTPException(503, "x"), "ok"])
    t1, o1 = _start(c.run, "k", fn)
    assert started.wait(2)
    t2, o2 = _start(c.run, "k", fn)
    time.sleep(0.05)
    gate.set()
    t1.join(2)
    t2.join(2)
    assert o1["error"].status_code == 503 and o2["value"] == "ok"

    c2 = Coalescer()
    fn, started, gate = _failing_then([HTTPException(404, "nf"), "unused"])
    t1, o1 = _start(c2.run, "k", fn)
    assert started.wait(2)
    t2, o2 = _start(c2.run, "k", fn)
    time.sleep(0.05)
    gate.set()
    t1.join(2)
    t2.join(2)
    # 404 是領頭那次計算的正常結果；同批（抵達在計算開始後）照 F1 進下一批，下一批也算一次
    assert o1["error"].status_code == 404


def test_4xx_from_batch_is_shared_with_its_members():
    """同一批的成員共用該批的 4xx（不重試）。"""
    c = Coalescer()
    calls = []
    g = _Gate()
    t1, _ = _start(c.run, "k", g)            # 第 1 批卡住
    assert _wait_until(lambda: len(g.started) == 1)

    def nf():
        calls.append(1)
        raise HTTPException(404, "nf")

    t2, o2 = _start(c.run, "k", nf)          # 第 2 批成員
    t3, o3 = _start(c.run, "k", nf)
    time.sleep(0.05)
    g.open(1)
    t1.join(2)
    t2.join(2)
    t3.join(2)
    assert len(calls) == 1
    assert o2["error"].status_code == 404 and o3["error"].status_code == 404


def test_decorator_key_is_full_resolved_params():
    """鍵＝模組＋函式＋解析後全部參數（含 Query 預設值）＝完整路徑＋query。"""
    from fastapi import Query

    seen = []

    @coalesce.coalesced
    def ep(game_sno: int, season: int = Query(2026), kind_code: str = Query("A")) -> dict:
        seen.append((game_sno, season, kind_code))
        return {"s": season}

    assert ep(game_sno=1) == {"s": 2026}
    assert ep(game_sno=1, season=2025, kind_code="D") == {"s": 2025}
    k1, _ = coalesce._key(ep, (), {"game_sno": 1})
    k2, _ = coalesce._key(ep, (1,), {"season": 2026, "kind_code": "A"})
    k3, _ = coalesce._key(ep, (), {"game_sno": 1, "season": 2025})
    assert k1 == k2 and k1 != k3


# ---------------------------------------------------------------------------
# 8 支接線：每支端點本體都經過合併（F1 在該端點成立）。以 monkeypatch 讓計算卡住，
# 證明計算中抵達的第二個請求不拿第一批的結果、而是另算一次。
# ---------------------------------------------------------------------------

ENDPOINTS = [
    ("/api/v1/games/1/winprob", "cpbl.api.routers.games", "_game_winprob"),
    ("/api/v1/games/1/live", "cpbl.api.routers.games", "_game_live"),
    ("/api/v1/games/1/facts", "cpbl.api.routers.facts", "_facts_payload"),
    ("/api/v1/games/1/milestones", "cpbl.api.routers.games", "_game_milestones"),
    ("/api/v1/games/calendar", "cpbl.api.routers.games", "_games_calendar"),
    ("/api/v1/postseason-summary", "cpbl.api.routers.standings", "_postseason_summary"),
    ("/api/v1/daily/summary", "cpbl.api.routers.daily", "_daily_summary"),
    ("/api/v1/playoffs/overview", "cpbl.api.routers.playoffs", "_playoffs_overview"),
]


@pytest.mark.parametrize(("path", "module", "attr"), ENDPOINTS)
def test_endpoint_is_wired_through_coalescer(path, module, attr, monkeypatch):
    import importlib

    mod = importlib.import_module(module)
    fn = getattr(mod, attr)
    assert getattr(fn, "coalesced", False) is True, f"{module}.{attr} 未接上合併"


@pytest.mark.parametrize(("path", "module", "attr"), ENDPOINTS)
def test_endpoint_f1_arrival_during_compute_gets_fresh_compute(path, module, attr, monkeypatch):
    import importlib

    from cpbl.api.main import app

    mod = importlib.import_module(module)
    fn = getattr(mod, attr)
    g = _Gate()
    if attr == "_facts_payload":
        monkeypatch.setattr(fn, "compute", lambda **kw: {"n": g(), "render_state": "authoritative",
                                                        "season": 2025})
    else:
        monkeypatch.setattr(fn, "compute", lambda **kw: {"n": g()})
    client = TestClient(app)
    t1, o1 = _start(client.get, path)
    assert _wait_until(lambda: len(g.started) == 1)
    t2, o2 = _start(client.get, path)     # 第 1 批計算中抵達
    time.sleep(0.1)
    assert len(g.started) == 1
    g.open(1)
    assert _wait_until(lambda: len(g.started) == 2)
    g.open(2)
    t1.join(5)
    t2.join(5)
    assert o1["value"].status_code == 200 and o1["value"].json()["n"] == 1
    assert o2["value"].status_code == 200 and o2["value"].json()["n"] == 2


# ---------------------------------------------------------------------------
# 巢狀借池移除：milestones 的 _season_decisions、live（非 A）的 team_stats 都會自借連線，
# 必須在端點那條連線歸還後才呼叫（池滿時拿著一條等第二條會放大 PoolTimeout）。
# ---------------------------------------------------------------------------


class _DepthConn:
    """假 conn()：記錄目前借出的連線數；查詢依 SQL 片段回固定列。"""

    def __init__(self, rows_for):
        self.depth = 0
        self.rows_for = rows_for

    def __call__(self):
        outer = self

        class _CM:
            def __enter__(self):
                outer.depth += 1
                return _FakeConn(outer.rows_for)

            def __exit__(self, *exc):
                outer.depth -= 1
                return False

        return _CM()


class _FakeConn:
    def __init__(self, rows_for):
        self.rows_for = rows_for

    def cursor(self):
        return _FakeCursor(self.rows_for)


class _FakeCursor:
    def __init__(self, rows_for):
        self.rows_for = rows_for
        self.rows: list = []
        self.description = [("c",)]

    def execute(self, sql, params=None):
        cols, self.rows = self.rows_for(sql)
        self.description = [(c,) for c in cols]

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else (False,)


def test_milestones_does_not_hold_a_connection_while_building_season_decisions(monkeypatch):
    import datetime as dt

    from cpbl.api.routers import games

    def rows_for(sql):
        if "SELECT game_date, winning_pitcher_id FROM cpbl.games" in sql:
            return ["game_date", "winning_pitcher_id"], [(dt.date(2026, 5, 1), None)]
        return ["c"], []

    fake = _DepthConn(rows_for)
    seen = []

    def season_decisions(season, kind):
        seen.append(fake.depth)
        return {}

    monkeypatch.setattr(games, "conn", fake)
    monkeypatch.setattr(games, "_season_decisions", season_decisions)
    assert games.game_milestones(1, season=2026, kind_code="A") == {"items": []}
    assert seen == [0]


def test_live_non_a_does_not_hold_a_connection_while_reading_team_stats(monkeypatch):
    from cpbl.api.routers import games

    def rows_for(sql):
        if "FROM cpbl.games WHERE year = %s AND kind_code = %s AND game_sno = %s" in sql:
            return ["away_team_code", "home_team_code", "game_date"], [("AAA011", "ACN011", None)]
        return ["c"], []

    fake = _DepthConn(rows_for)
    seen = []

    def team_stats(season):
        seen.append(fake.depth)
        return {"AAA011": {"w": 3, "l": 1, "last10": "WWWL"}}

    monkeypatch.setattr(games, "conn", fake)
    monkeypatch.setattr(games, "get_public_live_snapshot", lambda *a: None)
    monkeypatch.setattr(games.matchup, "team_stats", team_stats)
    monkeypatch.setattr(games.pitcher_decisions, "game_decisions", lambda *a: {})
    body = games.game_live(1, season=2026, kind_code="E")
    assert seen == [0]
    assert body["records"] == {"AAA011": {"w": 3, "l": 1, "form": "WWWL"}}
