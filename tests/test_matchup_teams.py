"""#201 生涯對戰對手隊別：逐打席證據＋≤2017 官方逐年列判定，清單／篩選／洞察／單組一致。

樣本數字取自本機 DB 真實配對（published build、state='ready'，2026-09-24 唯讀查核）：
林立 0000002286 的對手清單中，官方對戰表把以下投手標成現任隊 AJL011（自家樂天）。
≤2017 證據一律讀真實資源檔（``matchup_pre2018_rows.v1.json``），不 mock；只有
資源檔沒有的情境（同年轉隊 split_unverified）才另以 monkeypatch 注入。
代號 ``00000090xx`` 為合成對手，只用來覆蓋首批／非首批與各狀態的組合。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient

from cpbl.api import matchup_teams
from cpbl.api.main import app
from cpbl.api.matchup_teams import (
    CONFIRMED,
    PARTIAL,
    PRIOR_PITCHER_WALK_COUNTS,
    SPLIT_UNVERIFIED,
    UNKNOWN,
    add_pre2018_evidence,
    charged_walk_pitcher,
    classify_team_evidence,
    matches_team,
    pre2018_rows,
)
from cpbl.api.routers import players as players_module


@pytest.mark.parametrize(
    ("official", "evidence", "expected"),
    [
        # 陳柏豪 vs 林立：19 PA 全在中信兄弟，官方隊號卻是 AJL011。
        (19, {"ACN011": 19}, (["ACN011"], CONFIRMED)),
        # 陳鴻文：2018 後可證 36 PA 屬富邦，其餘 5 PA 無逐打席證據。
        (41, {"AEO011": 36}, (["AEO011"], PARTIAL)),
        # 楊達翔：2 PA 皆無 2018 後證據。
        (2, {}, ([], UNKNOWN)),
        # 艾士特：中信 21＋台鋼 20＝官方 41 → 已確認多隊。
        (41, {"ACN011": 21, "AKP011": 20}, (["ACN011", "AKP011"], CONFIRMED)),
        # 林靖凱 vs 鄭凱文：證據 40 > 官方 39，對不上官方 → 不宣稱任何隊。
        (39, {"ACN011": 40}, ([], UNKNOWN)),
        # 申皓瑋 vs 朱承洋型：Lamigo／樂天兩個隊碼屬同一 franchise → 單隊。
        (24, {"AJK011": 10, "AJL011": 14}, (["AJL011"], CONFIRMED)),
        # 官方 0 PA 不得因任何證據被宣稱。
        (0, {"AEO011": 1}, ([], UNKNOWN)),
        (None, None, ([], UNKNOWN)),
        # 2017 前同年轉隊（拆分語意未證實）：打席計入總數，但不宣稱隊別、不得判已確認。
        (10, {"AEO011": 6, SPLIT_UNVERIFIED: 4}, (["AEO011"], PARTIAL)),
        (4, {SPLIT_UNVERIFIED: 4}, ([], UNKNOWN)),
        (9, {"AEO011": 6, SPLIT_UNVERIFIED: 4}, ([], UNKNOWN)),
    ],
)
def test_classify_team_evidence(official, evidence, expected):
    assert classify_team_evidence(official, evidence) == expected


def test_pre2018_resource_is_pre2018_only_and_holds_lin_li_row():
    rows = pre2018_rows()
    # 林立 × 陳鴻文 2017 例行賽：林立 Lamigo（AJK011）、陳鴻文中信（ACN011）5 PA。
    assert rows[("A", "0000002286", "0000003606")] == (("AJK011", "ACN011", 5, False),)
    manifest = json.loads(matchup_teams._PRE2018_RESOURCE.read_text())["manifest"]
    assert sum(len(v) for v in rows.values()) == manifest["rows"] == 1506
    assert manifest["requests_failed"] == 0 and manifest["target_years_failed"] == []


@pytest.mark.parametrize(
    ("pair", "official", "evidence_2018", "expected"),
    [
        # 補入 2016／2017 共 3 PA 後 5 > 官方 4：保守為未知，不改官方統計。
        (("0000001291", "0000000152"), 4, {"AJK011": 1, "AJL011": 1}, ([], UNKNOWN)),
        # 補入 2017 共 2 PA 後 56 > 官方 55。
        (("0000001318", "0000002348"), 55, {"ADD011": 43, "AKP011": 11}, ([], UNKNOWN)),
        # 補入 3 PA 後 15 < 官方 16：已證實 Lamigo／樂天，其餘未知。
        (("0000002661", "0000000128"), 16, {"AJK011": 5, "AJL011": 7}, (["AJL011"], PARTIAL)),
        # 林立 × 陳鴻文：富邦 36 ＋ 2017 中信 5 ＝ 官方 41 → 已確認兩隊。
        (("0000002286", "0000003606"), 41, {"AEO011": 36}, (["ACN011", "AEO011"], CONFIRMED)),
    ],
)
def test_real_pre2018_rows_merge_with_2018_evidence(pair, official, evidence_2018, expected):
    hitter, pitcher = pair
    evidence = {pitcher: dict(evidence_2018)}
    add_pre2018_evidence(evidence, hitter, "batting", "A", [pitcher])
    assert classify_team_evidence(official, evidence[pitcher]) == expected


def test_pre2018_pitching_view_uses_hitter_team():
    # 陳鴻文視角：林立 2018 後 Lamigo 13＋樂天 23，2017 Lamigo 5 → 同一 franchise 單隊。
    evidence = {"0000002286": {"AJK011": 13, "AJL011": 23}}
    add_pre2018_evidence(evidence, "0000003606", "pitching", "A", ["0000002286"])
    assert classify_team_evidence(41, evidence["0000002286"]) == (["AJL011"], CONFIRMED)


def test_matches_team_expands_historical_codes():
    assert matches_team(["AJL011"], "AJK011")
    assert matches_team(["ACN011", "AKP011"], "AKP011")
    assert not matches_team(["AEO011"], "AJL011")
    assert not matches_team([], "AJL011")


# ───────────────────────── 端點（fake DB） ─────────────────────────

_COLUMNS = (
    "year", "opp_id", "opp_name", "opp_team_code", "opp_team",
    "plate_appearances", "at_bats", "hits", "rbi", "singles", "doubles", "triples",
    "home_runs", "total_bases", "sac_hit", "sac_fly", "bb", "ibb", "hbp", "so",
    "ground_out", "fly_out", "goao", "strike_pct", "ball_pct", "swing_pct",
    "first_pitch_swing_pct", "whiff_pct", "gb_pct", "ld_pct", "fb_pct",
)


def _row(opp_id, name, pa, hits, team="AJL011", year=9999):
    values: dict[str, object] = dict.fromkeys(_COLUMNS, 0)
    values.update({
        "year": year, "opp_id": opp_id, "opp_name": name, "opp_team_code": team,
        "opp_team": "樂天桃猿", "plate_appearances": pa, "at_bats": pa, "hits": hits,
        "singles": hits, "total_bases": hits,
    })
    for key in ("goao", "strike_pct", "ball_pct", "swing_pct", "first_pitch_swing_pct",
                "whiff_pct", "gb_pct", "ld_pct", "fb_pct"):
        values[key] = None
    return tuple(values[c] for c in _COLUMNS)


# 官方生涯列：官方隊號是爬取當時的現任隊（真實值）。
_LIN_LI_ROWS = [
    _row("0000000779", "陳柏豪", 19, 5),
    _row("0000003606", "陳鴻文", 41, 9),
    _row("0000000777", "楊達翔", 2, 1, team="AKP011"),
    _row("0000007053", "艾士特", 41, 12, team="AKP011"),
    _row("0000009001", "合成非首批", 10, 3),
    _row("0000009002", "合成無證據", 5, 1),
    _row("0000009003", "合成部分可證", 10, 2),
]
# 2018 起逐打席證據 (opp_id, 交手時隊號, PA)；≤2017 另由真實資源檔併入
# （陳鴻文 2017 中信 5、楊達翔 2017 中信 2）。
_LIN_LI_EVIDENCE = [
    ("0000000779", "ACN011", 19),
    ("0000003606", "AEO011", 36),
    ("0000007053", "ACN011", 21),
    ("0000007053", "AKP011", 20),
    ("0000009001", "ACN011", 10),  # 非首批：有證據也不得套用
    ("0000009003", "AEO011", 4),
]
# 首批：對手投手 2024–2026 A/D 有出賽（合成 9001 除外）。
_FIRST_BATCH = {"0000000779", "0000003606", "0000000777", "0000007053",
                "0000009002", "0000009003"}
_TEAM_NAMES = [("ACN", "中信兄弟"), ("AEO", "富邦悍將"), ("AJL", "樂天桃猿"), ("AKP", "台鋼雄鷹")]


class _Cursor:
    def __init__(self, state):
        self._rows, self._evidence, self._log = state["rows"], state["evidence"], state["log"]
        self._first = state["first_batch"]
        self._mid_walk = state.get("mid_walk", {})
        self._result = []
        self.description = [(c,) for c in state.get("columns", _COLUMNS)]

    def execute(self, sql, params=None):
        self._log.append((sql, params))
        if "game_pa_events" in sql:
            opp = params.get("opp")
            key = "batting" if "batting_gamelog" in sql else "pitching"
            rows = self._mid_walk.get(key, [])
            self._result = [r for r in rows if opp is None or opp in (
                r[2:4] if key == "batting" else r[1:2])]
        elif "UNION SELECT hitter_acnt FROM cpbl.batting_gamelog" in sql:
            assert (params["y0"], params["y1"], params["kinds"]) == (2024, 2026, ["A", "D"])
            self._result = [(i,) for i in params["ids"] if i in self._first]
        elif "game_plate_appearances" in sql:
            opp = params.get("opp") if isinstance(params, dict) else None
            key = "batting" if "batting_gamelog" in sql else "pitching"
            self._result = [e for e in self._evidence.get(key, []) if opp in (None, e[0])]
        elif "FROM cpbl.teams" in sql:
            self._result = _TEAM_NAMES
        elif "_current WHERE year" in sql or "FROM cpbl.players WHERE id" in sql:
            self._result = []
        elif "SELECT DISTINCT year" in sql:
            self._result = [(9999,)]
        else:
            self._result = self._rows
            # 非生涯範圍的舊路徑仍以 SQL 隊號篩選：如實套用，驗證它沒被改動。
            for param in params or ():
                if isinstance(param, list) and param and all(len(p) == 3 for p in param):
                    idx = _COLUMNS.index("opp_team_code")
                    self._result = [r for r in self._rows if r[idx][:3] in param]
        return self

    def fetchall(self):
        return self._result


@pytest.fixture
def fake_db(monkeypatch):
    state = {"rows": _LIN_LI_ROWS, "evidence": {"batting": _LIN_LI_EVIDENCE},
             "first_batch": set(_FIRST_BATCH), "log": []}

    class _Conn:
        def cursor(self):
            return _Cursor(state)

    @contextmanager
    def fake_conn():
        yield _Conn()

    monkeypatch.setattr(players_module, "conn", fake_conn)
    return state


def _list(client, **params):
    base = {"scope": "career", "limit": 200}
    res = client.get("/api/v1/players/0000002286/matchups", params={**base, **params})
    assert res.status_code == 200
    return {item["opp_id"]: item for item in res.json()["items"]}


def test_career_list_labels_only_evidenced_teams(fake_db):
    items = _list(TestClient(app))

    chen_bh = items["0000000779"]
    assert (chen_bh["opp_team_status"], chen_bh["opp_franchises"]) == (CONFIRMED, ["ACN011"])
    assert chen_bh["opp_team_code"] == chen_bh["opp_franchise"] == "ACN011"
    assert chen_bh["opp_team"] == "中信兄弟"

    # 林立 × 陳鴻文：富邦 36（2018 後）＋中信 5（2017，資源檔）＝官方 41。
    chen_hw = items["0000003606"]
    assert (chen_hw["opp_team_status"], chen_hw["opp_franchises"]) == (
        CONFIRMED, ["ACN011", "AEO011"])
    # 楊達翔：2018 後 0，2017 中信 2 ＝ 官方 2 → 單隊已確認，舊欄位改為交手隊。
    yang = items["0000000777"]
    assert (yang["opp_team_status"], yang["opp_franchises"]) == (CONFIRMED, ["ACN011"])
    assert yang["opp_team_code"] == yang["opp_franchise"] == "ACN011"
    aster = items["0000007053"]
    assert (aster["opp_team_status"], aster["opp_franchises"]) == (
        CONFIRMED, ["ACN011", "AKP011"])
    none = items["0000009002"]
    assert (none["opp_team_status"], none["opp_franchises"]) == (UNKNOWN, [])
    part = items["0000009003"]
    assert (part["opp_team_status"], part["opp_franchises"]) == (PARTIAL, ["AEO011"])
    # 首批非「已確認單隊」一律不帶舊隊號欄位，舊讀取端不會再顯示錯隊。
    for item in (chen_hw, aster, none, part):
        assert item["opp_team_code"] is None
        assert item["opp_franchise"] is None
        assert item["opp_team"] is None
    # 統計欄仍是官方對戰表，一人一列。
    assert sorted(i["plate_appearances"] for i in items.values()) == [2, 5, 10, 10, 19, 41, 41]
    assert items["0000003606"]["hits"] == 9 and items["0000003606"]["avg"] == round(9 / 41, 4)


def test_career_list_non_first_batch_keeps_official_team(fake_db):
    # 非首批：即使 2018 後證據是中信，仍照現行官方隊號顯示，不帶證據欄。
    item = _list(TestClient(app))["0000009001"]
    assert "opp_team_status" not in item and "opp_franchises" not in item
    assert item["opp_team_code"] == item["opp_franchise"] == "AJL011"
    assert item["opp_team"] == "樂天桃猿"


def test_career_team_filter_first_batch_by_evidence_rest_by_official(fake_db):
    client = TestClient(app)
    # 中信：首批有中信證據者（含只靠 2017 資源的陳鴻文／楊達翔）；非首批 9001 不因證據進來。
    assert set(_list(client, opponent_team="ACN011")) == {
        "0000000779", "0000003606", "0000000777", "0000007053"}
    # 富邦：陳鴻文 2018 後 36、9003 部分可證；未知的 9002 不進任何隊。
    assert set(_list(client, opponent_team="AEO011")) == {"0000003606", "0000009003"}
    # 樂天：首批無人有樂天交手證據；非首批 9001 照官方隊號納入（現行行為不變）。
    assert set(_list(client, opponent_team="AJL011")) == {"0000009001"}
    # 歷史隊碼依 franchise 展開：Lamigo 篩選＝樂天。
    assert set(_list(client, opponent_team="AJK011")) == {"0000009001"}
    akp = _list(client, opponent_team="AKP011")
    # 楊達翔官方隊號是 AKP011，但他是首批、證據只有中信 → 不列入台鋼。
    assert set(akp) == {"0000007053"} and akp["0000007053"]["plate_appearances"] == 41
    # 生涯篩選不把隊號塞進 SQL（否則首批會先被現任隊號錯篩）。
    list_params = [p for s, p in fake_db["log"] if "FROM cpbl.batter_pitcher_matchups m" in s]
    assert list_params and all(not any(isinstance(x, list) for x in p) for p in list_params)


def test_career_all_non_first_batch_matches_pre_201_behaviour(fake_db):
    fake_db["first_batch"] = set()
    client = TestClient(app)
    items = _list(client)
    assert all("opp_team_status" not in i for i in items.values())
    assert {k: i["opp_franchise"] for k, i in items.items()} == {
        k: ("AKP011" if k in ("0000000777", "0000007053") else "AJL011") for k in items}
    assert set(_list(client, opponent_team="AKP011")) == {"0000000777", "0000007053"}
    # 沒有首批就不查逐打席證據。
    assert not any("game_plate_appearances" in sql for sql, _ in fake_db["log"])


def test_season_scope_keeps_official_team_behaviour(fake_db):
    fake_db["rows"] = [_row(r[1], r[2], r[5], r[7], team=r[3], year=2026) for r in _LIN_LI_ROWS]
    client = TestClient(app)
    items = _list(client, scope="season", limit=200)
    assert all("opp_team_status" not in item for item in items.values())
    assert items["0000000779"]["opp_franchise"] == "AJL011"
    assert set(_list(client, scope="season", opponent_team="AJL011")) == {
        "0000000779", "0000003606", "0000009001", "0000009002", "0000009003"}
    assert not any("game_plate_appearances" in sql for sql, _ in fake_db["log"])
    assert not any("batting_gamelog" in sql for sql, _ in fake_db["log"])


def test_pitching_role_first_batch_follows_subject_pitcher(fake_db):
    # 陳鴻文視角：對手林立 2018 後 Lamigo 13＋樂天 23，2017 Lamigo 5（資源）＝官方 41。
    fake_db["rows"] = [_row("0000002286", "林立", 41, 9)]
    fake_db["evidence"] = {"pitching": [("0000002286", "AJK011", 13),
                                        ("0000002286", "AJL011", 23)]}
    fake_db["first_batch"] = {"0000003606"}
    client = TestClient(app)

    def pitching(**params):
        res = client.get("/api/v1/players/0000003606/matchups",
                         params={"scope": "career", "role": "pitching", **params})
        assert res.status_code == 200
        return {item["opp_id"]: item for item in res.json()["items"]}

    lin = pitching()["0000002286"]
    assert (lin["opp_team_status"], lin["opp_franchises"]) == (CONFIRMED, ["AJL011"])
    assert set(pitching(opponent_team="AJL011")) == {"0000002286"}
    evidence_sql = [s for s, _ in fake_db["log"] if "game_plate_appearances" in s]
    assert evidence_sql and all("pitching_gamelog" in s for s in evidence_sql)

    # 主角投手不是首批：整份清單維持官方隊號。
    fake_db["first_batch"] = set()
    lin = pitching()["0000002286"]
    assert "opp_team_status" not in lin and lin["opp_franchise"] == "AJL011"


def _pair(client, pitcher="0000003606"):
    res = client.get(
        "/api/v1/matchups",
        params={"hitter": "0000002286", "pitcher": pitcher, "scope": "career"},
    )
    assert res.status_code == 200
    return res.json()["items"][0]


def test_pair_detail_career_adds_evidence_for_both_sides(fake_db):
    fake_db["columns"] = (
        "kind_code", "year", "hitter_name", "pitcher_name",
        "hitter_team_code", "pitcher_team_code", *_COLUMNS[5:],
    )
    fake_db["rows"] = [(
        "A", 9999, "林立", "陳鴻文", "AJL011", "AJL011",
        *_row("0000003606", "陳鴻文", 41, 9)[5:],
    )]
    fake_db["evidence"] = {
        "batting": [("0000003606", "AEO011", 36)],
        "pitching": [("0000002286", "AJK011", 13), ("0000002286", "AJL011", 23)],
    }
    client = TestClient(app)
    item = _pair(client)
    # 與兩個清單視角同一判定：打者視角看陳鴻文＝中信＋富邦；投手視角看林立＝樂天。
    assert (item["pitcher_team_status"], item["pitcher_franchises"]) == (
        CONFIRMED, ["ACN011", "AEO011"])
    assert (item["hitter_team_status"], item["hitter_franchises"]) == (CONFIRMED, ["AJL011"])
    # 既有隊號欄位與統計不變（前端主角側照舊）。
    assert item["pitcher_team_code"] == "AJL011" and item["plate_appearances"] == 41

    # 非首批投手：兩側都不帶證據欄，前端照舊顯示官方隊號。
    fake_db["first_batch"] = set()
    item = _pair(client)
    assert not any(key.endswith(("_team_status", "_franchises")) for key in item)
    assert item["pitcher_franchise"] == "AJL011" and item["plate_appearances"] == 41


def test_career_insights_filter_uses_same_evidence(fake_db, monkeypatch):
    from cpbl.api.matchups import InsightUniverse
    from cpbl.models.matchup_insights import WobaLine

    universe = InsightUniverse(
        bat_league_mean=0.32, pit_league_mean=0.32, sigma2=0.4,
        hitter_baselines={"0000002286": WobaLine(30.0, 100)}, pitcher_baselines={},
        hitter_opps={"0000002286": 100}, pitcher_opps={}, pairs=(), contexts={}, hyper=None,
    )
    monkeypatch.setattr(players_module, "load_insight_universe", lambda *a, **k: universe)
    client = TestClient(app)

    def sample(team):
        res = client.get("/api/v1/players/0000002286/matchups/insights",
                         params={"scope": "career", "opponent_team": team})
        assert res.status_code == 200
        return res.json()

    # 與清單篩選同集合：樂天只剩非首批 9001、中信 4 人、富邦 2 人。
    assert sample("AJL011")["query_sample"]["opponents"] == 1
    assert sample("ACN011")["query_sample"]["opponents"] == 4
    assert sample("AEO011")["query_sample"]["opponents"] == 2
    # 覆蓋率仍以全部對手評估，不受隊別判定影響。
    assert sample("AJL011")["coverage"]["sampled_opportunities"] == 128


def test_split_unverified_pre2018_row_never_confirms(fake_db, monkeypatch):
    # 資源檔目前 0 列 split_unverified；以注入列驗證：打席計入、隊別不宣稱、不判已確認。
    monkeypatch.setattr(matchup_teams, "pre2018_rows", lambda: {
        ("A", "0000002286", "0000009002"): (("AJK011", "AEO011", 3, True),
                                           ("AJK011", "ACN011", 2, False)),
    })
    items = _list(TestClient(app))
    assert (items["0000009002"]["opp_team_status"], items["0000009002"]["opp_franchises"]) == (
        PARTIAL, ["ACN011"])
    assert set(_list(TestClient(app), opponent_team="AEO011")) == {
        "0000003606", "0000009003"}


# ───────────────────── 打席中換投後四壞（規則 9.16(h)(1)） ─────────────────────

_PRIOR, _RELIEF = "0000007580", "0000005285"


def _mid_walk_events(ball, strike, *, change_ball=None, change_flag=True, relief=_RELIEF):
    """2026/A/328 真實形狀：前任投一球後換投（換投事件帶當下球數、pitch_cnt 0），接手投完四壞。"""
    change_ball = ball if change_ball is None else change_ball
    return [
        (_PRIOR, ball, strike, False),
        (relief, change_ball, strike, change_flag),
        (relief, 4, strike, False),
    ]


@pytest.mark.parametrize("ball", range(4))
@pytest.mark.parametrize("strike", range(3))
def test_charged_walk_pitcher_rule_table(ball, strike):
    # 2-0／2-1／3-0／3-1／3-2 歸前任；其餘（含 0-0、1-0、1-1、2-2）歸接手。
    expected = _PRIOR if (ball, strike) in {(2, 0), (2, 1), (3, 0), (3, 1), (3, 2)} else _RELIEF
    assert charged_walk_pitcher(_PRIOR, _RELIEF, _mid_walk_events(ball, strike)) == expected


def test_prior_pitcher_counts_match_rule_text():
    assert PRIOR_PITCHER_WALK_COUNTS == {(2, 0), (2, 1), (3, 0), (3, 1), (3, 2)}


@pytest.mark.parametrize("events", [
    # 換投事件球數缺失
    [(_PRIOR, 2, 0, False), (_RELIEF, None, 0, True), (_RELIEF, 4, 0, False)],
    # 換投事件球數與前任最後一球不符
    _mid_walk_events(2, 0, change_ball=1),
    # 接手第一筆不是換人事件（找不到換投事件）
    _mid_walk_events(2, 0, change_flag=False),
    # 打席中超過兩位投手
    [*_mid_walk_events(2, 0), ("0000009999", 4, 0, True)],
    # 事件缺投手
    [(_PRIOR, 2, 0, False), (None, 2, 0, True), (_RELIEF, 4, 0, False)],
    # 投手順序往返
    [(_PRIOR, 2, 0, False), (_RELIEF, 2, 0, True), (_PRIOR, 3, 0, True)],
])
def test_charged_walk_pitcher_unresolved(events):
    assert charged_walk_pitcher(_PRIOR, _RELIEF, events) is None


def _mid_walk_row(events, *, hitter="0000002286", team="ACN011", game=date(2026, 5, 1),
                  cutoff=date(2026, 7, 14)):
    return [(1, hitter, _PRIOR, _RELIEF, team, game, cutoff, cutoff, *e) for e in events]


def _pitchers_case(fake_db, events, **kwargs):
    """林立 vs 前任（官方 5、其餘證據 4）與接手（官方 3、其餘證據 3），外加一筆換投四壞。"""
    fake_db["rows"] = [_row(_PRIOR, "前任", 5, 1, team="ACN011"),
                       _row(_RELIEF, "接手", 3, 1, team="ACN011")]
    fake_db["evidence"] = {"batting": [(_PRIOR, "ACN011", 4), (_RELIEF, "ACN011", 3)]}
    fake_db["first_batch"] = {_PRIOR, _RELIEF}
    fake_db["mid_walk"] = {"batting": _mid_walk_row(events, **kwargs)}
    items = _list(TestClient(app))
    return {k: (i["opp_team_status"], i["opp_franchises"]) for k, i in items.items()}


def test_mid_pa_walk_follows_count_at_change(fake_db):
    # 2-1 換投 → 前任：兩位投手都與官方打席數閉合。
    assert _pitchers_case(fake_db, _mid_walk_events(2, 1)) == {
        _PRIOR: (CONFIRMED, ["ACN011"]), _RELIEF: (CONFIRMED, ["ACN011"])}
    # 1-0 換投 → 接手：前任缺 1、接手多 1，都不宣稱已確認。
    assert _pitchers_case(fake_db, _mid_walk_events(1, 0)) == {
        _PRIOR: (PARTIAL, ["ACN011"]), _RELIEF: (UNKNOWN, [])}


def test_mid_pa_walk_after_official_snapshot_is_ignored(fake_db):
    # 與主 SQL 同一截止：官方生涯列爬取日當天及之後的比賽不算證據。
    assert _pitchers_case(fake_db, _mid_walk_events(2, 1), game=date(2026, 7, 14)) == {
        _PRIOR: (PARTIAL, ["ACN011"]), _RELIEF: (CONFIRMED, ["ACN011"])}


def test_mid_pa_walk_unresolved_never_confirms_either_pitcher(fake_db):
    # 無法判定時不歸給任何一方：前任恰好湊滿官方數也不得判已確認；
    # 接手即使其他證據已閉合，也因這筆未歸屬打席降為未確認（不互相抵銷）。
    events = _mid_walk_events(2, 1, change_ball=1)
    assert _pitchers_case(fake_db, events) == {
        _PRIOR: (PARTIAL, ["ACN011"]), _RELIEF: (UNKNOWN, [])}


def test_mid_pa_walk_does_not_mask_stale_snapshot(fake_db):
    # 0000005510×0000005285 形狀：接手側其他證據已比官方多 1（#215 舊快照），
    # 1-0 換投四壞仍歸接手 → 維持未知，不因任何歸屬手段被抵銷成已確認。
    fake_db["rows"] = [_row(_RELIEF, "接手", 4, 1, team="ACN011")]
    fake_db["evidence"] = {"batting": [(_RELIEF, "ACN011", 4)]}
    fake_db["first_batch"] = {_RELIEF}
    fake_db["mid_walk"] = {"batting": _mid_walk_row(_mid_walk_events(1, 0))}
    item = _list(TestClient(app))[_RELIEF]
    assert (item["opp_team_status"], item["opp_franchises"]) == (UNKNOWN, [])


def test_mid_pa_walk_pitching_view_credits_prior_pitcher(fake_db):
    # 前任投手視角：2-1 換投四壞歸自己 → 林立打席數補回、閉合；接手視角不計。
    fake_db["rows"] = [_row("0000002286", "林立", 5, 1, team="AJL011")]
    fake_db["first_batch"] = {_PRIOR, _RELIEF}
    fake_db["mid_walk"] = {"pitching": _mid_walk_row(_mid_walk_events(2, 1), team="AJL011")}
    client = TestClient(app)

    def lin_li(pitcher, evidence_pa):
        fake_db["evidence"] = {"pitching": [("0000002286", "AJL011", evidence_pa)]}
        res = client.get(f"/api/v1/players/{pitcher}/matchups",
                         params={"scope": "career", "role": "pitching"})
        item = res.json()["items"][0]
        return item["opp_team_status"], item["opp_franchises"]

    assert lin_li(_PRIOR, 4) == (CONFIRMED, ["AJL011"])
    assert lin_li(_RELIEF, 5) == (CONFIRMED, ["AJL011"])


# ───────────────────── 林立三筆非首批例外（需求方裁定） ─────────────────────

_EXTRA_ROWS = [
    _row("0000004621", "紐維拉", 23, 5),
    _row("0000004770", "索沙", 40, 8),
    _row("0000005085", "包林傑", 20, 4),
    _row("0000009001", "合成非首批", 10, 3),
]
# 本機真實證據（2018 起，2026-09-26 唯讀）：與官方打席數相等。
_EXTRA_EVIDENCE = [("0000004621", "ACN011", 23), ("0000004770", "AEO011", 40),
                   ("0000005085", "AEO011", 20), ("0000009001", "ACN011", 10)]


def test_lin_li_extra_pairs_labeled_and_filtered_by_evidence(fake_db):
    fake_db["rows"] = _EXTRA_ROWS
    fake_db["evidence"] = {"batting": _EXTRA_EVIDENCE}
    fake_db["first_batch"] = set()  # 三人皆非首批
    client = TestClient(app)
    items = _list(client)
    assert {k: (i.get("opp_team_status"), i["opp_team"]) for k, i in items.items()} == {
        "0000004621": (CONFIRMED, "中信兄弟"),
        "0000004770": (CONFIRMED, "富邦悍將"),
        "0000005085": (CONFIRMED, "富邦悍將"),
        "0000009001": (None, "樂天桃猿"),  # 其他非首批不擴張：仍是官方隊號
    }
    assert set(_list(client, opponent_team="AJL011")) == {"0000009001"}
    assert set(_list(client, opponent_team="ACN011")) == {"0000004621"}
    assert set(_list(client, opponent_team="AEO011")) == {"0000004770", "0000005085"}
    assert [items[k]["plate_appearances"] for k in ("0000004621", "0000004770")] == [23, 40]


def test_lin_li_extra_pairs_pitching_view(fake_db):
    # 包林傑視角（非首批）：林立列依證據＝樂天；其他打者不擴張，仍官方隊號。
    fake_db["rows"] = [_row("0000002286", "林立", 20, 4),
                       _row("0000000362", "合成他人", 18, 5, team="AEO011")]
    fake_db["evidence"] = {"pitching": [("0000002286", "AJK011", 20),
                                        ("0000000362", "AJL011", 18)]}
    fake_db["first_batch"] = set()
    res = TestClient(app).get("/api/v1/players/0000005085/matchups",
                              params={"scope": "career", "role": "pitching"})
    items = {i["opp_id"]: i for i in res.json()["items"]}
    lin = items["0000002286"]
    assert (lin["opp_team_status"], lin["opp_franchises"]) == (CONFIRMED, ["AJL011"])
    other = items["0000000362"]
    assert "opp_team_status" not in other and other["opp_franchise"] == "AEO011"
