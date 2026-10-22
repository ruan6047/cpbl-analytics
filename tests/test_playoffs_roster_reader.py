"""#286 S05 WP1：第 3 區名單讀取面純組裝（compute_roster／background_of／pr_tags）。

合成形狀的事實輸入，不連 DB。SQL 的去重與對帳另以本機唯讀 DB 冒煙（執行證據），不在此重測。
"""

from __future__ import annotations

from datetime import UTC, datetime

from cpbl.playoffs import roster_reader as rr
from cpbl.playoffs.roster_reader import RosterInputs, compute_roster

NOW = datetime(2026, 10, 16, 2, 0, tzinfo=UTC)
AWAY, HOME = "AAA011", "ACN011"


def context(teams=(AWAY, HOME)):
    return {
        "context_version": "ctx-v1",
        "as_of": {"last_refresh_at": "2026-10-16T02:00:00+00:00", "last_completed_game_date": "2026-10-12"},
        "series": {"C": {"series_id": {"year": 2026, "kind_code": "C", "teams": list(teams)}}},
    }


def roster(*members, rev=1):
    return {"roster_id": "r1", "published_date": "2026-10-16", "source_url": "https://www.cpbl.com.tw/x",
            "annotation_version": rev,
            "members": [{"player_id": pid, "announced_name": f"球員{pid[-2:]}", "official_position": pos,
                         "tactical_role": role} for pid, pos, role in members]}


def inputs(rosters, **kw) -> RosterInputs:
    return RosterInputs(year=2026, series="C", context=kw.pop("ctx", context()), rosters=rosters,
                        team_names={AWAY: "味全", HOME: "兄弟"}, background_cutoff="2026-10-06", **kw)


def members(out, team=AWAY):
    return {m["player_id"]: m for t in out["teams"] if t["team_code"] == team for m in t["members"]}


def test_envelope_carries_mount_contract_fields():
    out = compute_roster(inputs({AWAY: roster(("0000000001", "投手", "終結")), HOME: roster()}), now=NOW)
    for k in ("contract", "context_version", "series_id", "as_of", "status"):
        assert k in out
    assert out["contract"] == "playoffs-roster/v1"
    assert out["context_version"] == "ctx-v1"
    assert out["default_scope"] == "background"
    assert out["scopes"]["series"]["status"] == "no_games"      # PR2：context 無完賽場
    assert out["registration"]["status"] == "unknown"   # 28 人：S11 前恆 unknown，⛔ 推算


def test_one_team_missing_is_partial_and_team_kept_without_members():
    out = compute_roster(inputs({AWAY: roster(("0000000001", "投手", None)), HOME: None}), now=NOW)
    assert out["status"] == "partial"
    t = {x["team_code"]: x for x in out["teams"]}
    assert t[HOME]["roster_status"] == "missing" and t[HOME]["members"] == []
    assert t[HOME]["team_name"] == "兄弟"
    assert "roster_missing:ACN011" in out["missing_reason"]


def test_both_missing_and_source_unavailable():
    assert compute_roster(inputs({AWAY: None, HOME: None}), now=NOW)["status"] == "roster_missing"
    out = compute_roster(inputs(None), now=NOW)
    assert out["status"] == "unavailable"
    assert {t["roster_status"] for t in out["teams"]} == {"unavailable"}


def test_series_teams_unknown():
    out = compute_roster(inputs({}, ctx=context(teams=())), now=NOW)
    assert out["status"] == "series_unknown" and out["teams"] == []


def test_role_null_and_unclassified_are_null():
    out = compute_roster(inputs({AWAY: roster(("0000000001", "捕手", None), ("0000000002", "外野手", "unclassified"),
                                              ("0000000003", "投手", "輪值")), HOME: roster()}), now=NOW)
    m = members(out)
    assert m["0000000001"]["tactical_role"] is None
    assert m["0000000002"]["tactical_role"] is None
    assert m["0000000003"]["tactical_role"] == "輪值"
    assert m["0000000003"]["role"] == "pitching" and m["0000000001"]["role"] == "batting"


def test_members_sorted_by_official_position_then_id():
    out = compute_roster(inputs({AWAY: roster(("0000000009", "外野手", None), ("0000000005", "投手", None),
                                              ("0000000002", "內野手", None), ("0000000001", "投手", None)),
                                 HOME: roster()}), now=NOW)
    t = next(x for x in out["teams"] if x["team_code"] == AWAY)
    assert [m["player_id"] for m in t["members"]] == ["0000000001", "0000000005", "0000000002", "0000000009"]


def test_background_a_then_d_then_none():
    counts = {
        ("0000000001", "batting", "A"): {"g": 52, "pa": 200, "ab": 180, "h": 54, "bb": 15, "hbp": 2, "sf": 3,
                                          "tb": 80, "hr": 5},
        ("0000000001", "batting", "D"): {"g": 10, "pa": 30, "ab": 28, "h": 9, "bb": 2, "hbp": 0, "sf": 0,
                                          "tb": 12, "hr": 0},
        ("0000000002", "batting", "D"): {"g": 40, "pa": 150, "ab": 130, "h": 40, "bb": 15, "hbp": 3, "sf": 2,
                                          "tb": 60, "hr": 3},
        ("0000000003", "pitching", "D"): {"g": 20, "outs": 60, "er": 8, "so": 22, "bb": 7},
    }
    adv = {("0000000002", "batting"): {"woba_pr": 99}}   # 二軍球員即使有 A 進階列也不得標（只有 D 背景）
    out = compute_roster(inputs({AWAY: roster(("0000000001", "內野手", "主力"), ("0000000002", "外野手", "代打"),
                                              ("0000000003", "投手", "長中繼"), ("0000000004", "捕手", None)),
                                 HOME: roster()}, counts=counts, advanced=adv), now=NOW)
    m = members(out)
    a = m["0000000001"]["background"]
    assert a["level"] == "A" and a["g"] == 52
    assert a["line"]["avg"] == 0.3 and a["line"]["ops"] == round((54 + 15 + 2) / 200 + 80 / 180, 3)
    d = m["0000000002"]["background"]
    assert d["level"] == "D" and d["g"] == 40 and d["pr_tags"] == []
    p = m["0000000003"]["background"]
    assert p["level"] == "D" and p["line"]["ip"] == "20.0" and p["line"]["era"] == 3.6
    n = m["0000000004"]["background"]
    assert {k: v for k, v in n.items() if k != "arrow"} == {
        "level": "none", "g": None, "line": None, "pr_tags": [],
        "positions": [], "primary_position": None, "dh_starts": 0, "dh_starts_unknown": 0}   # #350 野手欄照帶
    assert n["arrow"]["status"] == "insufficient"
    assert "background_none" in out["missing_reason"]


def test_zero_g_is_not_a_background():
    counts = {("0000000001", "batting", "A"): {"g": 0}}
    out = compute_roster(inputs({AWAY: roster(("0000000001", "內野手", None)), HOME: roster()}, counts=counts), now=NOW)
    assert members(out)["0000000001"]["background"]["level"] == "none"


def test_pinch_runner_appearance_counts_g_without_pa():
    """純代跑／守備：box 有列但 PA=0，G 仍計；率分母 0 ⇒ None（⛔ 0）。"""
    counts = {("0000000001", "batting", "A"): {"g": 7, "pa": 0, "ab": 0, "h": 0, "bb": 0, "hbp": 0, "sf": 0,
                                                "tb": 0, "hr": 0}}
    out = compute_roster(inputs({AWAY: roster(("0000000001", "外野手", "守備")), HOME: roster()}, counts=counts),
                         now=NOW)
    b = members(out)["0000000001"]["background"]
    assert b["level"] == "A" and b["g"] == 7
    assert b["line"]["avg"] is None and b["line"]["ops"] is None


def test_pr_tags_boundary_and_order():
    assert rr.pr_tags(None) == []
    assert rr.pr_tags({"woba_pr": 89, "kp_pr": None}) == []
    tags = rr.pr_tags({"woba_pr": 90, "ev_pr": 95, "kp_pr": 95, "ba_pr": 100, "brl_pr": 99})
    assert [t["key"] for t in tags] == ["ba_pr", "ev_pr", "kp_pr", "woba_pr"]   # 高到低；同值依球員頁欄序
    assert all(t["key"] != "brl_pr" for t in tags)                              # 球員頁去重的計數欄不列


def test_pr_tags_only_from_role_matching_a_row():
    counts = {("0000000001", "pitching", "A"): {"g": 30, "outs": 90, "er": 10, "so": 30, "bb": 10}}
    adv = {("0000000001", "batting"): {"woba_pr": 99}, ("0000000001", "pitching"): {"kp_pr": 92}}
    out = compute_roster(inputs({AWAY: roster(("0000000001", "投手", "終結")), HOME: roster()}, counts=counts,
                                advanced=adv), now=NOW)
    assert members(out)["0000000001"]["background"]["pr_tags"] == [{"key": "kp_pr", "value": 92}]


def test_era_zero_outs_and_zero_er():
    assert rr.pitching_line({"outs": 0, "er": 0})["era"] is None
    assert rr.pitching_line({"outs": 3, "er": 0})["era"] == 0.0


def test_roster_version_changes_with_annotation_but_context_does_not():
    """名單／角色更新不在 S02 manifest（P1-4）：靠 roster_version 辨認。"""
    a = compute_roster(inputs({AWAY: roster(("0000000001", "投手", "終結"), rev=1), HOME: None}), now=NOW)
    b = compute_roster(inputs({AWAY: roster(("0000000001", "投手", "輪值"), rev=2), HOME: None}), now=NOW)
    assert a["context_version"] == b["context_version"]
    assert a["roster_version"] != b["roster_version"]


class _Cur:
    """記錄 execute 次數的假 cursor（查詢次數與人數無關）。"""

    def __init__(self):
        self.calls = 0
        self.description = []
        self._rows = []

    def execute(self, sql, params=None):
        self.calls += 1
        self._rows = ([(None,)] if "max(g.game_date)" in sql else [(0,) * 6] if "sum(ab)" in sql else [])
        self.description = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def _ids(n, prefix):
    return [(f"{prefix}{i:05d}", "投手" if i % 2 else "內野手", None) for i in range(n)]


def test_query_count_independent_of_roster_size():
    def calls(rosters):
        cur = _Cur()
        rr.read_background(cur, inputs(rosters))
        return cur.calls

    one = calls({AWAY: roster(*_ids(32, "11111")), HOME: None})
    two = calls({AWAY: roster(*_ids(32, "11111")), HOME: roster(*_ids(32, "22222"))})
    # cutoff＋打擊計數＋投球計數＋官方 PR＋兩個聯盟基準＋兩個最近出賽批次＋守位＋DH 先發（#350）
    assert one == two == 10


class _RowsCur:
    """依 SQL 回傳真實形狀列（欄名＝SELECT 別名）的假 cursor：走 read_background 的真讀取／解析路徑。"""

    def __init__(self, ids_bat, ids_pit):
        self.ids_bat, self.ids_pit = ids_bat, ids_pit
        self.description, self._rows = [], []

    def _set(self, cols, rows):
        self.description = [(c,) for c in cols]
        self._rows = rows

    def execute(self, sql, params=None):
        if "max(g.game_date)" in sql:
            from datetime import date
            self._set(["max"], [(date(2026, 10, 6),)])
        elif "FROM cpbl.batting_gamelog b\n     WHERE" in sql:
            self._set(["pid", "kind_code", "g", "pa", "ab", "h", "bb", "hbp", "sf", "tb", "hr"],
                      [(p, "A", 30, 100, 90, 27, 8, 1, 1, 40, 3) for p in self.ids_bat]
                      + [(self.ids_bat[0], "D", 5, 20, 18, 5, 2, 0, 0, 7, 0)])
        elif "FROM cpbl.pitching_gamelog p\n     WHERE" in sql:
            self._set(["pid", "kind_code", "g", "outs", "er", "so", "bb"], [(p, "A", 40, 120, 12, 35, 10) for p in self.ids_pit])
        elif "cpbl.advanced_stats" in sql:
            self._set(["acnt", "role", *rr.PR_COLUMNS], [(self.ids_bat[0], "batting", *([95] + [None] * 12))])
        elif "FROM cpbl.batting_current" in sql:
            self._set(["s"] * 6, [(4000, 1100, 400, 50, 30, 1600)])
        elif "FROM cpbl.pitching_current" in sql:
            self._set(["ip", "er"], [(1000.0, 400)])
        elif "cpbl.fielding_current" in sql:
            self._set(["pid", "pos", "g"], [(self.ids_bat[0], "游擊手", 35), (self.ids_bat[0], "三壘手", 11)])
        elif "DISTINCT ON" in sql:
            assert params["kind"] == "A" and params["snos"] is None and params["ids"] == self.ids_bat
            self._set(["pid", "dh", "unknown"], [(self.ids_bat[0], 22, 1)])
        elif "RECENT" in sql or "row_number()" in sql:
            if "hitter_acnt" in sql:
                self._set(["pid", "game_date", "game_sno", "ab", "h", "bb", "hbp", "sf", "tb"],
                          [(self.ids_bat[0], None, i, 3, 1, 0, 0, 0, 1) for i in range(30)])
            else:
                self._set(["pid", "game_date", "game_sno", "ipc", "ip3", "er"],
                          [(self.ids_pit[0], None, i, 1, 0, 0) for i in range(30)])
        else:
            raise AssertionError(f"unexpected SQL: {sql[:60]}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def test_read_background_parses_real_row_shapes():
    """真讀取路徑：計數列含 kind_code 字串、PR 列含 acnt／role（規劃者以真 DB 抓到的 pop 求值順序缺陷的回歸）。"""
    bat, pit = ["0000000001", "0000000002"], ["0000000003"]
    rosters = {AWAY: roster(*[(p, "內野手", None) for p in bat], *[(p, "投手", None) for p in pit]), HOME: None}
    inp = inputs(rosters)
    rr.read_background(_RowsCur(bat, pit), inp)
    assert inp.counts[("0000000001", "batting", "A")]["g"] == 30
    assert inp.counts[("0000000001", "batting", "D")]["g"] == 5
    assert inp.counts[("0000000003", "pitching", "A")]["outs"] == 120
    assert inp.advanced[("0000000001", "batting")]["ev_pr"] == 95
    assert inp.background_cutoff == "2026-10-06"
    assert len(inp.recent["0000000001"]) == 30 and len(inp.recent["0000000003"]) == 30
    out = compute_roster(inp, now=NOW)
    m = members(out)
    assert m["0000000001"]["background"]["pr_tags"] == [{"key": "ev_pr", "value": 95}]
    assert m["0000000001"]["background"]["arrow"]["status"] == "flat"
    assert m["0000000003"]["background"]["arrow"]["status"] == "undefined"   # 全程 0 自責 ⇒ ERA0
    b1 = m["0000000001"]["background"]
    assert b1["primary_position"] == "游擊手" and b1["positions"][0] == {"pos": "游擊手", "g": 35}
    assert (b1["dh_starts"], b1["dh_starts_unknown"]) == (22, 1)
    assert (m["0000000002"]["background"]["dh_starts"], m["0000000002"]["background"]["primary_position"]) == (0, None)
    assert "dh_starts" not in m["0000000003"]["background"]                   # 投手不加
