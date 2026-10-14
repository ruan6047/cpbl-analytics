"""#283 S02 WP3：讀取層（腳本化 cursor，不連 DB）與 postseason-summary 新欄位。

SQL 語意（完賽判準同源、單一唯讀交易）另由 ``test_postseason_contract_isolated.py`` 在隔離 Postgres 驗。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from postseason_context_inputs import READER_GAME_COLS as _GAME_COLS
from postseason_context_inputs import READER_GAMES as _GAMES
from postseason_context_inputs import ScriptedCursor as _Cursor
from postseason_context_inputs import reader_table as _table

from cpbl import postseason_contract as pc
from cpbl.api.routers import standings

NOW = datetime(2026, 10, 14, 17, 0, tzinfo=UTC)   # 台北 10/15 01:00


def test_reader_builds_inputs_and_context_from_one_cursor():
    cur = _Cursor(_table())
    inputs = pc.read_series_inputs(cur, 2026, now=NOW, live_reader=lambda *a, **k: None)
    assert cur.calls[0] == pc.GAMES_V2_SQL
    assert inputs.standings.source == "official"
    ctx = pc.compute_series_context(inputs, now=NOW)
    assert ctx["series"]["E"]["winner"] == "ACN011"
    assert ctx["series"]["E"]["analysis_status"] == "ready"
    assert ctx["state"]["default_series"] == "C"
    sources = {m["source"]: m["status"] for m in ctx["source_manifest"]}
    assert sources["standings"] == "ok" and sources["live_snapshot"] == "ok"


def test_optional_sources_degrade_and_are_listed():
    cur = _Cursor(_table(), fail={pc.OFFICIAL_STANDINGS_SQL, pc.REVISIONS_V2_SQL, pc.RECAP_BUILDS_SQL})
    inputs = pc.read_series_inputs(cur, 2026, now=NOW, live_reader=None)
    ctx = pc.compute_series_context(inputs, now=NOW)
    assert ctx["series"]["E"]["series_status"] == "unknown"           # 讀不到戰績 ⇒ 不猜讓勝
    assert {"standings_unavailable", "official_status_unavailable",
            "recap_builds_unavailable", "live_snapshot_unavailable"} <= set(ctx["missing_reason"])


def test_games_failure_raises():
    cur = _Cursor(_table(), fail={pc.GAMES_V2_SQL})
    try:
        pc.read_series_inputs(cur, 2026, now=NOW)
    except RuntimeError:
        return
    raise AssertionError("games 失敗必須上浮")


def test_live_reader_marks_live_only_for_candidate_games():
    seen = []

    def live(year, kind, sno, *, now):
        seen.append((year, kind, sno))
        return {"phase": "live"}

    ctx = pc.compute_series_context(pc.read_series_inputs(_Cursor(_table()), 2026, now=NOW, live_reader=live), now=NOW)
    assert seen == [(2026, "C", 1)]                 # 只讀每系列下一場（E 已全部完賽）
    assert ctx["state"]["default_series"] == "C" and ctx["state"]["layout_state"] == "T4"


def test_postseason_summary_keeps_existing_fields_and_adds_context(monkeypatch):
    class _C:
        def execute(self, sql, params):
            class R:
                def fetchall(self_inner):
                    return []
            return R()

    class _Ctx:
        def __enter__(self):
            return _C()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(standings, "conn", lambda: _Ctx())
    sentinel = {"contract": pc.CONTEXT_CONTRACT}
    monkeypatch.setattr(pc, "postseason_series_context", lambda season, **kw: sentinel)
    resp = standings.postseason_summary(season=2026, kind_code="A")
    assert resp == {"season": 2026, "series": [], "series_context": sentinel}
    assert "series_context" not in standings.postseason_summary(season=2026, kind_code="D")


def test_postseason_summary_context_failure_is_null_not_500(monkeypatch):
    class _Ctx:
        def __enter__(self):
            class C:
                def execute(self, sql, params):
                    class R:
                        def fetchall(self_inner):
                            return []
                    return R()
            return C()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(standings, "conn", lambda: _Ctx())

    def boom(season, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(pc, "postseason_series_context", boom)
    assert standings.postseason_summary(season=2026, kind_code="A")["series_context"] is None


def test_later_live_game_is_read_even_when_earlier_game_is_unsynced():
    """F2（再審）：C1（10/17）尚未同步完賽、C2（10/18）唯一 live ⇒ 讀到 C2 快照、輸出 T4／target C2。"""
    t = _table()
    t[pc.GAMES_V2_SQL] = (_GAME_COLS, [*_GAMES, (2026, "C", 2, date(2026, 10, 18), "大巨蛋", None,
                                                  "ACN011", "AAA011", 0, 0, False)])
    now = datetime.fromisoformat("2026-10-18T18:00:00+08:00")
    seen = []

    def live(year, kind, sno, *, now):
        seen.append((year, kind, sno))
        return {"phase": "live"} if sno == 2 else None

    ctx = pc.compute_series_context(pc.read_series_inputs(_Cursor(t), 2026, now=now, live_reader=live), now=now)
    assert seen == [(2026, "C", 1), (2026, "C", 2)]
    assert (ctx["state"]["layout_state"], ctx["state"]["target_game_key"]) == (
        "T4", {"year": 2026, "kind_code": "C", "game_sno": 2})
    assert ctx["state"]["layout_reason"] == "live_observed"


def test_future_game_without_signal_is_not_probed_but_signalled_one_is():
    """日期在未來且無異動訊號的列不會 live；有未決異動訊號（日期可能已改）就要讀。"""
    t = _table()
    t[pc.GAMES_V2_SQL] = (_GAME_COLS, [*_GAMES, (2026, "C", 2, date(2026, 10, 18), "大巨蛋", None,
                                                  "ACN011", "AAA011", 0, 0, False)])
    seen = []

    def live(year, kind, sno, *, now):
        seen.append(sno)

    pc.read_series_inputs(_Cursor(t), 2026, now=NOW, live_reader=live)
    assert seen == [1]
    t[pc.CHANGE_SIGNALS_SQL] = (["year", "kind_code", "game_sno", "field", "official_value", "detected_at",
                                 "local_game_date"],
                                [(2026, "C", 2, "date", "2026-10-15", NOW, date(2026, 10, 18))])
    seen.clear()
    pc.read_series_inputs(_Cursor(t), 2026, now=NOW, live_reader=live)
    assert seen == [1, 2]


def test_live_cache_exception_stops_further_probes():
    t = _table()
    t[pc.GAMES_V2_SQL] = (_GAME_COLS, [*_GAMES, (2026, "C", 2, date(2026, 10, 15), "大巨蛋", None,
                                                  "ACN011", "AAA011", 0, 0, False)])
    calls = []

    def live(year, kind, sno, *, now):
        calls.append(sno)
        raise OSError("redis down")

    ctx = pc.compute_series_context(pc.read_series_inputs(_Cursor(t), 2026, now=NOW, live_reader=live), now=NOW)
    assert len(calls) == 1   # 第一次例外後不再逐場等逾時（候選有 C1、C2 兩場）
    assert "live_snapshot_unavailable" in ctx["missing_reason"]
