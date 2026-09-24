"""#201 生涯對戰對手隊別：逐打席證據判定＋清單／篩選／洞察／單組一致（fake DB）。

樣本數字取自本機 DB 真實配對（published build、state='ready'，2026-09-24 唯讀查核）：
林立 0000002286 的對手清單中，官方對戰表把以下投手標成現任隊 AJL011（自家樂天）。
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from cpbl.api.main import app
from cpbl.api.matchup_teams import (
    CONFIRMED,
    PARTIAL,
    UNKNOWN,
    classify_team_evidence,
    matches_team,
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
    ],
)
def test_classify_team_evidence(official, evidence, expected):
    assert classify_team_evidence(official, evidence) == expected


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


# 官方生涯列：四人都被標成 AJL011（爬取當時的現任隊）。
_LIN_LI_ROWS = [
    _row("0000000779", "陳柏豪", 19, 5),
    _row("0000003606", "陳鴻文", 41, 9),
    _row("0000000777", "楊達翔", 2, 1),
    _row("0000007053", "艾士特", 41, 12, team="AKP011"),
]
# 逐打席證據 (opp_id, 交手時隊號, PA)。
_LIN_LI_EVIDENCE = [
    ("0000000779", "ACN011", 19),
    ("0000003606", "AEO011", 36),
    ("0000007053", "ACN011", 21),
    ("0000007053", "AKP011", 20),
]
_TEAM_NAMES = [("ACN", "中信兄弟"), ("AEO", "富邦悍將"), ("AJL", "樂天桃猿"), ("AKP", "台鋼雄鷹")]


class _Cursor:
    def __init__(self, state):
        self._rows, self._evidence, self._log = state["rows"], state["evidence"], state["log"]
        self._result = []
        self.description = [(c,) for c in state.get("columns", _COLUMNS)]

    def execute(self, sql, params=None):
        self._log.append((sql, params))
        if "game_plate_appearances" in sql:
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
    state = {"rows": _LIN_LI_ROWS, "evidence": {"batting": _LIN_LI_EVIDENCE}, "log": []}

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

    chen_hw = items["0000003606"]
    assert (chen_hw["opp_team_status"], chen_hw["opp_franchises"]) == (PARTIAL, ["AEO011"])
    yang = items["0000000777"]
    assert (yang["opp_team_status"], yang["opp_franchises"]) == (UNKNOWN, [])
    aster = items["0000007053"]
    assert (aster["opp_team_status"], aster["opp_franchises"]) == (
        CONFIRMED, ["ACN011", "AKP011"])
    # 非「已確認單隊」一律不帶舊隊號欄位，舊讀取端不會再顯示錯隊。
    for item in (chen_hw, yang, aster):
        assert item["opp_team_code"] is None
        assert item["opp_franchise"] is None
        assert item["opp_team"] is None
    # 統計欄仍是官方對戰表，一人一列。
    assert [items[k]["plate_appearances"] for k in items] == [41, 41, 19, 2]
    assert items["0000003606"]["hits"] == 9 and items["0000003606"]["avg"] == round(9 / 41, 4)


def test_career_team_filter_uses_evidence_not_current_team(fake_db):
    client = TestClient(app)
    # 四人官方隊號都是 AJL011／AKP011，但沒有一人有以樂天交手的證據。
    assert _list(client, opponent_team="AJL011") == {}
    # 部分可證：已證實的富邦納入，未知的楊達翔不進任何隊。
    assert set(_list(client, opponent_team="AEO011")) == {"0000003606"}
    # 多隊列在每一個已證實的隊下都出現，同一列總計。
    assert set(_list(client, opponent_team="ACN011")) == {"0000000779", "0000007053"}
    akp = _list(client, opponent_team="AKP011")
    assert set(akp) == {"0000007053"} and akp["0000007053"]["plate_appearances"] == 41
    # 生涯篩選不再把隊號塞進 SQL（否則會先被現任隊號錯篩）。
    list_params = [p for s, p in fake_db["log"] if "FROM cpbl.batter_pitcher_matchups m" in s]
    assert list_params and all(not any(isinstance(x, list) for x in p) for p in list_params)


def test_season_scope_keeps_official_team_behaviour(fake_db):
    fake_db["rows"] = [_row(r[1], r[2], r[5], r[7], team=r[3], year=2026) for r in _LIN_LI_ROWS]
    client = TestClient(app)
    items = _list(client, scope="season", limit=200)
    assert all("opp_team_status" not in item for item in items.values())
    assert items["0000000779"]["opp_franchise"] == "AJL011"
    assert set(_list(client, scope="season", opponent_team="AJL011")) == {
        "0000000779", "0000003606", "0000000777"}
    assert not any("game_plate_appearances" in sql for sql, _ in fake_db["log"])


def test_pitching_role_reads_opponent_batting_team(fake_db):
    fake_db["evidence"] = {"pitching": [("0000000779", "ACN011", 19)]}
    items = _list(TestClient(app), role="pitching")
    assert items["0000000779"]["opp_team_status"] == CONFIRMED
    evidence_sql = [s for s, _ in fake_db["log"] if "game_plate_appearances" in s]
    assert evidence_sql and all("pitching_gamelog" in s for s in evidence_sql)


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
        "pitching": [("0000002286", "AJL011", 36)],
    }
    res = TestClient(app).get(
        "/api/v1/matchups",
        params={"hitter": "0000002286", "pitcher": "0000003606", "scope": "career"},
    )
    assert res.status_code == 200
    item = res.json()["items"][0]
    assert (item["pitcher_team_status"], item["pitcher_franchises"]) == (PARTIAL, ["AEO011"])
    assert (item["hitter_team_status"], item["hitter_franchises"]) == (PARTIAL, ["AJL011"])
    # 既有隊號欄位不變（前端主角側照舊）。
    assert item["pitcher_team_code"] == "AJL011" and item["plate_appearances"] == 41


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

    assert sample("AJL011")["query_sample"]["opponents"] == 0
    assert sample("AEO011")["query_sample"]["opponents"] == 1
    assert sample("ACN011")["query_sample"]["opponents"] == 2
    # 覆蓋率仍以全部對手評估，不受隊別判定影響。
    assert sample("AJL011")["coverage"]["sampled_opportunities"] == 103
