"""#286 S05 WP6（PR2）：第 3 區「本系列實戰」scope——完賽場、E／C 隔離、缺 box 待更新、預設 scope。

構造 S02 context 與計數，不連 DB；E 系列真實資料對帳另見執行證據。
"""

from __future__ import annotations

from datetime import UTC, datetime

from cpbl.playoffs import roster_reader as rr
from cpbl.playoffs.roster_reader import RosterInputs, compute_roster

NOW = datetime(2026, 10, 18, 2, 0, tzinfo=UTC)
AWAY, HOME = "AAA011", "ACN011"


def g(kind, sno, no, completed=True, away=AWAY, home=HOME):
    return {"game_key": {"year": 2026, "kind_code": kind, "game_sno": sno}, "series_game_no": no,
            "completed": completed, "away_team_code": away, "home_team_code": home}


def ctx(games, layout="T2"):
    return {"context_version": "v", "as_of": {},
            "series": {"C": {"series_id": {"year": 2026, "kind_code": "C", "teams": [AWAY, HOME]}}},
            "state": {"by_series": {"C": {"layout_state": layout}}}, "games": games}


def roster(*members):
    return {"roster_id": "r", "published_date": None, "source_url": None, "annotation_version": 1,
            "members": [{"player_id": p, "announced_name": p, "official_position": pos, "tactical_role": None}
                        for p, pos in members]}


def inp(games, layout="T2", **kw):
    return RosterInputs(year=2026, series="C", context=ctx(games, layout),
                        rosters={AWAY: roster(("0000000001", "內野手"), ("0000000002", "投手")), HOME: roster()}, **kw)


def test_no_completed_games_is_no_games_and_member_series_none():
    i = inp([g("C", 1, 1, completed=False)])
    out = compute_roster(i, now=NOW)
    assert out["scopes"]["series"] == {"status": "no_games", "completed_games": 0, "pending_games": []}
    assert all(m["series"] is None for t in out["teams"] for m in t["members"])


def test_only_selected_series_completed_games_are_counted():
    # E 已完賽場與 C 未完賽場都不算 C 的完賽場（E／C 隔離）
    games = [g("E", 4, 4), g("C", 1, 1), g("C", 2, 2, completed=False)]
    assert [x["game_key"]["game_sno"] for x in rr._series_games(inp(games))] == [1]


def test_box_missing_for_one_team_is_pending_by_series_game_no():
    games = [g("C", 1, 1), g("C", 2, 2)]
    i = inp(games, series_counts={}, series_box={1: {"away": True, "home": True}, 2: {"away": True}})
    out = compute_roster(i, now=NOW)
    assert out["scopes"]["series"] == {"status": "pending_source", "completed_games": 2, "pending_games": [2]}
    t = {x["team_code"]: x for x in out["teams"]}
    assert t[HOME]["series_pending_games"] == [2] and t[AWAY]["series_pending_games"] == []
    assert "series_box_pending" in out["missing_reason"]


def test_all_boxes_present_is_ok():
    i = inp([g("C", 1, 1)], series_counts={}, series_box={1: {"away": True, "home": True}})
    assert compute_roster(i, now=NOW)["scopes"]["series"]["status"] == "ok"


def test_member_series_counts_and_pinch_runner_g():
    counts = {("0000000001", "batting"): {"g": 1, "pa": 0, "ab": 0, "h": 0, "bb": 0, "hbp": 0, "sf": 0, "tb": 0, "hr": 0},
              ("0000000002", "pitching"): {"g": 2, "outs": 9, "er": 1, "so": 3, "bb": 0}}
    i = inp([g("C", 1, 1), g("C", 2, 2)], series_counts=counts,
            series_box={1: {"away": True, "home": True}, 2: {"away": True, "home": True}})
    m = {x["player_id"]: x for t in compute_roster(i, now=NOW)["teams"] for x in t["members"]}
    assert m["0000000001"]["series"]["g"] == 1 and m["0000000001"]["series"]["line"]["ops"] is None  # 純代跑
    assert m["0000000002"]["series"]["line"] == {"outs": 9, "ip": "3.0", "er": 1, "so": 3, "bb": 0, "era": 3.0}


def test_member_without_series_appearance_is_zero_g():
    i = inp([g("C", 1, 1)], series_counts={}, series_box={1: {"away": True, "home": True}})
    m = {x["player_id"]: x for t in compute_roster(i, now=NOW)["teams"] for x in t["members"]}
    assert m["0000000001"]["series"] == {"g": 0, "line": None}


def test_default_scope_series_only_when_t5():
    assert compute_roster(inp([], layout="T5"), now=NOW)["default_scope"] == "series"
    for layout in ("T0", "T1", "T2", "T3", "T4"):
        assert compute_roster(inp([], layout=layout), now=NOW)["default_scope"] == "background"


class _Cur:
    def __init__(self):
        self.calls, self.description, self._rows = [], [], []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "UNION" in sql:
            self.description, self._rows = [("game_sno",), ("vht",)], [(1, "1"), (1, "2")]
        elif "hitter_acnt" in sql:
            self.description = [(c,) for c in ("pid", "g", "pa", "ab", "h", "bb", "hbp", "sf", "tb", "hr")]
            self._rows = [("0000000001", 1, 4, 4, 2, 0, 0, 0, 3, 0)]
        else:
            self.description = [(c,) for c in ("pid", "g", "outs", "er", "so", "bb")]
            self._rows = [("0000000002", 1, 6, 0, 2, 1)]

    def fetchall(self):
        return self._rows


def test_read_series_queries_only_selected_series_completed_snos_and_is_size_independent():
    cur = _Cur()
    i = inp([g("E", 4, 4), g("C", 1, 1), g("C", 2, 2, completed=False)])
    rr.read_series(cur, i)
    assert len(cur.calls) == 3
    assert all(p["kind"] == "C" and p["snos"] == [1] for _, p in cur.calls)
    assert i.series_box == {1: {"away": True, "home": True}}
    assert i.series_counts[("0000000001", "batting")]["h"] == 2
    assert i.series_counts[("0000000002", "pitching")]["outs"] == 6


def test_read_series_reads_boxes_even_without_roster():
    cur = _Cur()
    i = RosterInputs(year=2026, series="C", context=ctx([g("C", 1, 1)]), rosters={AWAY: None, HOME: None})
    rr.read_series(cur, i)
    assert len(cur.calls) == 1 and i.series_box == {1: {"away": True, "home": True}}
    assert compute_roster(i, now=NOW)["scopes"]["series"]["status"] == "ok"


def test_no_completed_games_issues_no_query():
    cur = _Cur()
    rr.read_series(cur, inp([g("C", 1, 1, completed=False)]))
    assert cur.calls == []
