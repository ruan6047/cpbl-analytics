"""#283 S02 WP3：讀取層（腳本化 cursor，不連 DB）與 postseason-summary 新欄位。

SQL 語意（完賽判準同源、單一唯讀交易）另由 ``test_postseason_contract_isolated.py`` 在隔離 Postgres 驗。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from cpbl import postseason_contract as pc
from cpbl.api.routers import standings

NOW = datetime(2026, 10, 14, 17, 0, tzinfo=UTC)   # 台北 10/15 01:00


class _Cursor:
    """依 SQL 常數回列；``fail`` 內的 SQL 一律丟例外（模擬缺表／權限）。"""

    def __init__(self, table: dict, fail=()):
        self.table, self.fail, self.calls = table, set(fail), []
        self._rows, self.description = [], None

    def execute(self, sql, params=None):
        self.calls.append(sql)
        if sql in self.fail:
            raise RuntimeError("relation does not exist")
        cols, rows = self.table.get(sql, ([], []))
        self.description = [(c,) for c in cols]
        self._rows = list(rows)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


_GAME_COLS = ["year", "kind_code", "game_sno", "game_date", "venue", "mvp_id", "away_team_code",
              "home_team_code", "away_score", "home_score", "completed"]
# 2026 真實 E1–E4、C1（本機 DB 唯讀，見 tests/fixtures/postseason_real_years.json）
_GAMES = [
    (2026, "E", 1, date(2026, 10, 9), "洲際", None, "ADD011", "ACN011", 1, 4, True),
    (2026, "E", 2, date(2026, 10, 10), "亞太主", None, "ACN011", "ADD011", 0, 1, True),
    (2026, "E", 3, date(2026, 10, 11), "洲際", None, "ADD011", "ACN011", 4, 2, True),
    (2026, "E", 4, date(2026, 10, 12), "洲際", None, "ADD011", "ACN011", 2, 8, True),
    (2026, "C", 1, date(2026, 10, 17), "大巨蛋", None, "ACN011", "AAA011", 0, 0, False),
]
_OFFICIAL = [(0, "AAA011", 67, 53, 0), (0, "ADD011", 64, 55, 1), (0, "AEO011", 59, 61, 0),
             (0, "ACN011", 56, 62, 2), (1, "AAA011", 39, 21, 0), (1, "ACN011", 20, 38, 2),
             (1, "ADD011", 30, 29, 1), (2, "ACN011", 36, 24, 0), (2, "ADD011", 34, 26, 0),
             (2, "AAA011", 28, 32, 0)]


def _table():
    return {
        pc.GAMES_V2_SQL: (_GAME_COLS, _GAMES),
        pc.OFFICIAL_STANDINGS_SQL: (["season_code", "team_code", "w", "l", "t"], _OFFICIAL),
        pc.REFRESH_SQL: (["refreshed_at", "ok", "scope"], [(NOW, True, "daily")]),
        pc.RECAP_BUILDS_SQL: (["year", "kind_code", "game_sno", "state", "built_at"],
                              [(2026, "E", n, "published", NOW) for n in (1, 2, 3, 4)]),
    }


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
