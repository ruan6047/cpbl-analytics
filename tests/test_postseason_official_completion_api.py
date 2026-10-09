"""#237：2026 起季後 E／C 的完賽只認官方 final／證據——games 路由（calendar／live／winprob）。

全部以腳本化 cursor 驗證，不連任何資料庫。SQL 片段的**求值語意**由
`tests/test_completion.py` 的 sqlite 矩陣負責；這裡只驗：
  * calendar／live 的查詢真的帶上同一支 canonical 判準（`completed` 欄），
  * winprob 不會把賽中部分比分補成終點 1/0，而 A／D／歷史年份仍走原本的比分判斷。

E1 的比分抄自官方 2026-10-09 17:52 台北擷取（HomeScore=3、VisitingScore=0、
PresentStatus=1、GameResult=''）。
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from cpbl.api.routers import games
from cpbl.completion import completed_games_sql_with_evidence


class _Cursor:
    def __init__(self, script: list[tuple[list[str], list[tuple]]]):
        self._script = list(script)
        self.queries: list[str] = []
        self.description: list = []
        self._rows: list[tuple] = []

    def execute(self, sql, params=None):
        self.queries.append(" ".join(str(sql).split()))
        cols, rows = self._script.pop(0) if self._script else ([], [])
        self.description = [(c,) for c in cols]
        self._rows = rows
        return self

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def _conn(cursor: _Cursor):
    @contextmanager
    def factory():
        class _C:
            def cursor(self):
                return cursor
        yield _C()
    return factory


def test_calendar_exposes_the_canonical_completed_column(monkeypatch) -> None:
    cur = _Cursor([(["year", "kind_code", "game_sno", "completed"], [(2026, "E", 1, False)])])
    monkeypatch.setattr(games, "conn", _conn(cur))

    body = games.games_calendar(season=2026, kind_code="A")

    assert body["items"] == [{"year": 2026, "kind_code": "E", "game_sno": 1, "completed": False}]
    expected = " ".join(f"COALESCE({completed_games_sql_with_evidence('g')}, false) AS completed".split())
    assert expected in cur.queries[0]


def test_live_game_row_exposes_the_canonical_completed_column(monkeypatch) -> None:
    empty: tuple[list[str], list[tuple]] = (["x"], [])
    cur = _Cursor([
        (["year", "kind_code", "game_sno", "home_score", "away_score", "completed"],
         [(2026, "E", 1, 3, 0, False)]),
        empty, empty, empty, empty,          # scoreboard／livelog／batting／pitching
        empty,                               # tracking（published PA mapping）
        (["exists"], [(False,)]),            # has_raw_tracking
        empty,                               # game_detail
    ])
    monkeypatch.setattr(games, "conn", _conn(cur))
    monkeypatch.setattr(games.pitcher_decisions, "game_decisions", lambda *_: {})
    monkeypatch.setattr(games.matchup, "team_stats", lambda *_: {})
    monkeypatch.setattr(games, "get_public_live_snapshot", lambda *_: None)
    monkeypatch.setattr(games.pitch_type_live, "annotate", lambda snapshot, _season: snapshot)

    body = games.game_live(1, season=2026, kind_code="E")

    assert body["game"]["completed"] is False
    assert body["live_snapshot"] is None
    expected = " ".join(f"COALESCE({completed_games_sql_with_evidence('games')}, false) AS completed".split())
    assert expected in cur.queries[0]


_EVENT_COLS = ["main_event_no", "inning_seq", "visiting_home_type", "batting_order", "out_cnt",
               "is_change_player", "hitter_acnt", "hitter_name", "first_base", "second_base",
               "third_base", "visiting_score", "home_score"]
_EVENT = ("0001001", 1, "1", 1, 0, False, "h1", "打者一", None, None, None, 0, 0)


def _winprob(monkeypatch, *, kind: str, season: int, fin: tuple):
    from cpbl.models import winprob

    cur = _Cursor([(_EVENT_COLS, [_EVENT]), (["home_score", "away_score", "done"], [fin])])
    monkeypatch.setattr(games, "conn", _conn(cur))
    monkeypatch.setattr(games, "_wp_tables", lambda *_: (None, None, None))
    monkeypatch.setattr(winprob, "wp_state", lambda *_: 0.5)
    return games.game_winprob(1, season=season, kind_code=kind), cur


def test_winprob_does_not_close_a_live_2026_postseason_game(monkeypatch) -> None:
    body, cur = _winprob(monkeypatch, kind="E", season=2026, fin=(3, 0, False))

    assert body["completed"] is False
    assert [p["evt"] for p in body["items"]] == ["0001001"], "不得補終點 1/0"
    assert completed_games_sql_with_evidence("games") in cur.queries[1]


def test_winprob_closes_a_2026_postseason_game_only_on_official_completion(monkeypatch) -> None:
    body, _ = _winprob(monkeypatch, kind="C", season=2026, fin=(3, 0, True))

    assert body["completed"] is True
    assert body["items"][-1] == {"evt": None, "inning": None, "half": None, "hitter": None,
                                 "away": 0, "home": 3, "wp": 1.0}


@pytest.mark.parametrize(("kind", "season"), [("A", 2026), ("D", 2026), ("E", 2025), ("C", 2025)])
def test_winprob_keeps_the_score_rule_outside_2026_postseason(monkeypatch, kind, season) -> None:
    # canonical 欄刻意給 False：這些賽別必須仍只看比分（原行為），不讀它。
    body, _ = _winprob(monkeypatch, kind=kind, season=season, fin=(3, 0, False))

    assert body["completed"] is True
    assert body["items"][-1]["wp"] == 1.0
