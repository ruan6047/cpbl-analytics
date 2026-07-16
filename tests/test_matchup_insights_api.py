"""/api/v1/players/{id}/matchups/insights 端點契約測試（fake DB、無外部依賴）。"""

from __future__ import annotations

import dataclasses
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from cpbl.api.main import app
from cpbl.api.matchups import InsightUniverse
from cpbl.api.routers import players as players_module
from cpbl.models.matchup_insights import Hyperparameters, WobaLine

_COLUMNS = (
    "year", "opp_id", "opp_name", "opp_team_code", "opp_team",
    "plate_appearances", "at_bats", "hits", "rbi", "singles", "doubles", "triples",
    "home_runs", "total_bases", "sac_hit", "sac_fly", "bb", "ibb", "hbp", "so",
    "ground_out", "fly_out", "goao", "strike_pct", "ball_pct", "swing_pct",
    "first_pitch_swing_pct", "whiff_pct", "gb_pct", "ld_pct", "fb_pct",
)


def _row(year, opp_id, opp_name, *, ab, singles=0, doubles=0, hr=0, bb=0, so=0,
         team="ACN011"):
    hits = singles + doubles + hr
    values = {
        "year": year, "opp_id": opp_id, "opp_name": opp_name,
        "opp_team_code": team, "opp_team": "隊",
        "plate_appearances": ab + bb, "at_bats": ab, "hits": hits, "rbi": 0,
        "singles": singles, "doubles": doubles, "triples": 0, "home_runs": hr,
        "total_bases": singles + 2 * doubles + 4 * hr, "sac_hit": 0, "sac_fly": 0,
        "bb": bb, "ibb": 0, "hbp": 0, "so": so, "ground_out": 0, "fly_out": 0,
        "goao": None, "strike_pct": None, "ball_pct": None, "swing_pct": None,
        "first_pitch_swing_pct": None, "whiff_pct": None, "gb_pct": None,
        "ld_pct": None, "fb_pct": None,
    }
    return tuple(values[c] for c in _COLUMNS)


class _FakeCursor:
    """模擬 batter_pitcher_matchups 查詢；若參數帶三碼隊碼清單（舊版把
    opponent_team 過濾放進 SQL 的 `=ANY(%s)`），如實在資料層套用該過濾，
    讓「SQL 端先過濾再算覆蓋率」的缺陷行為能被端點測試重現。"""

    def __init__(self, rows):
        self._rows = rows
        self._result = rows
        self.description = [(c,) for c in _COLUMNS]

    def execute(self, sql, params=None):
        self._result = self._rows
        for param in params or ():
            if (
                isinstance(param, (list, set, tuple))
                and param
                and all(isinstance(p, str) and len(p) == 3 for p in param)
            ):
                team_idx = _COLUMNS.index("opp_team_code")
                self._result = [
                    row for row in self._rows if (row[team_idx] or "")[:3] in param
                ]
        return self

    def fetchall(self):
        return self._result


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)


def _fake_universe():
    """官方 baseline universe：BAT 官方生涯 320 機會（覆蓋率會 ~100%）。

    官方母體 self-inclusive（= 配對加權和 26.7＋2.1 ＋ 19 機會 @聯盟均值），
    與 leave-pair-out 語意一致；ACE 對 BAT 大幅壓制（天敵候選）。"""
    hyper = Hyperparameters(sigma2=0.4, tau2=0.01, pairs_used=99)
    return InsightUniverse(
        bat_league_mean=0.320,
        pit_league_mean=0.315,
        sigma2=0.4,
        hitter_baselines={"BAT": WobaLine(26.7 + 2.10 + 19 * 0.32, 320)},
        pitcher_baselines={
            "ACE": WobaLine(0.315 * 4000, 4000),
            "NOBODY": WobaLine(0.315 * 4000, 4000),
        },
        hitter_opps={"BAT": 320},
        pitcher_opps={"ACE": 4000, "NOBODY": 4000},
        pairs=(),
        contexts={},
        hyper=hyper,
    )


@pytest.fixture
def client(monkeypatch):
    # ACE 跨兩年彙總後為大樣本壓制；NOBODY 是 1 打數 1 轟。
    rows = [
        _row(2024, "ACE", "王牌", ab=150, singles=15, so=45),
        _row(2025, "ACE", "王牌", ab=150, singles=15, so=45),
        _row(2025, "NOBODY", "路人", ab=1, hr=1),
    ]

    @contextmanager
    def fake_conn():
        yield _FakeConn(rows)

    monkeypatch.setattr(players_module, "conn", fake_conn)
    monkeypatch.setattr(
        players_module, "load_insight_universe", lambda *a, **k: _fake_universe()
    )
    return TestClient(app)


def test_batter_insights_use_official_baseline_and_pass_coverage(client):
    res = client.get(
        "/api/v1/players/BAT/matchups/insights",
        params={"role": "batting", "scope": "range", "from_year": 2024, "to_year": 2025},
    )
    assert res.status_code == 200
    body = res.json()

    # 覆蓋率：樣本 301 機會 / 官方生涯 320 ≈ 0.94，過閘門。
    assert body["coverage"]["passed"] is True
    assert body["coverage"]["official_opportunities"] == 320
    assert body["coverage"]["ratio"] == pytest.approx(0.941, abs=0.01)
    # ACE 官方被打接近聯盟，但對 BAT 觀察 wOBA 極低 → 天敵；1 轟路人被閘門擋下。
    assert [c["opp_id"] for c in body["disadvantages"]] == ["ACE"]
    assert body["advantages"] == []
    ace = body["disadvantages"][0]
    assert ace["opportunities"] == 300
    assert ace["opponent_official_opportunities"] == 4000
    assert ace["credibility"] >= body["method"]["credibility_gate"]
    # baseline 與聯盟均值來自官方完整季彙總，非對戰樣本。
    assert body["baseline"]["official_opportunities"] == 320
    assert body["league"]["source"] == "official_season_aggregates"
    assert body["method"]["baseline_source"].startswith("official")
    assert "官方完整季彙總" in body["disclaimer"]


def test_pitcher_insights_fail_closed_on_low_coverage(client):
    # 投手主角：官方生涯 4000 機會，但對戰樣本只覆蓋 300（僅本季登錄打者）→
    # 覆蓋率 0.075 << 0.60，fail-closed 不輸出方向性結論。
    res = client.get(
        "/api/v1/players/ACE/matchups/insights",
        params={"role": "pitching", "scope": "range", "from_year": 2024, "to_year": 2025},
    )
    assert res.status_code == 200
    body = res.json()

    assert body["coverage"]["passed"] is False
    assert body["coverage"]["ratio"] < 0.60
    assert body["advantages"] == [] and body["disadvantages"] == []
    assert body["sensitivity"] is None
    assert "覆蓋" in body["sample_note"]


def test_insights_degrade_honestly_without_rows(client, monkeypatch):
    @contextmanager
    def empty_conn():
        yield _FakeConn([])

    monkeypatch.setattr(players_module, "conn", empty_conn)
    res = client.get("/api/v1/players/BAT/matchups/insights")
    body = res.json()

    assert res.status_code == 200
    assert body["advantages"] == [] and body["disadvantages"] == []
    assert body["sample_note"] is not None
    assert body["baseline"] is None


def test_insights_reject_mixed_scope(client):
    res = client.get(
        "/api/v1/players/BAT/matchups/insights",
        params={"scope": "career", "from_year": 2024, "to_year": 2025},
    )
    assert res.status_code == 422


# ───────────── 第二輪審核 regression（P1-1／P1-2）：端點層級 ─────────────
# 用動態欄位建 InsightUniverse（缺陷版欄位是 expected、修正版是 contexts），
# 讓同一批測試能在 a1fcbe7 上有意義地跑紅，而非 import／建構錯誤。


def _make_universe(**overrides):
    field_names = {f.name for f in dataclasses.fields(InsightUniverse)}
    base = dict(
        bat_league_mean=0.320,
        pit_league_mean=0.315,
        sigma2=0.4,
        hitter_baselines={},
        pitcher_baselines={},
        hitter_opps={},
        pitcher_opps={},
        pairs=(),
        hyper=None,
    )
    base["contexts" if "contexts" in field_names else "expected"] = {}
    base.update(overrides)
    return InsightUniverse(**base)


# BAT 官方母體＝四個配對之和＋148 機會 @聯盟均值（self-inclusive、可覆蓋率≈0.75）：
#   ACE   300 機會、weighted 26.7（被壓制）→ 天敵候選
#   BULLY 150 機會、weighted 92.5（宰制）  → 優勢對位（隊碼用舊碼 AJK011，
#         驗證 franchise 映射：查 AJL011 需命中）
#   NOBODY 1 PA 1 HR（weighted 2.10）、SUPPRESS 1 PA 0-for-1 → 永不入榜
_OFFICIAL_BAT_W = 26.7 + 92.5 + 2.10 + 0.0 + 148 * 0.32
_OFFICIAL_BAT_N = 300 + 150 + 1 + 1 + 148


def _rich_rows():
    return [
        _row(2024, "ACE", "王牌", ab=150, singles=15, so=45),
        _row(2025, "ACE", "王牌", ab=150, singles=15, so=45),
        _row(2025, "BULLY", "肥羊", ab=150, singles=40, doubles=20, hr=15,
             team="AJK011"),
        _row(2025, "NOBODY", "路人", ab=1, hr=1),
        _row(2025, "SUPPRESS", "剋星", ab=1, so=1),
    ]


def _rich_universe(hyper):
    pitchers = {
        pid: WobaLine(0.315 * 4000, 4000)
        for pid in ("ACE", "BULLY", "NOBODY", "SUPPRESS")
    }
    return _make_universe(
        hitter_baselines={"BAT": WobaLine(_OFFICIAL_BAT_W, _OFFICIAL_BAT_N)},
        pitcher_baselines=pitchers,
        hitter_opps={"BAT": _OFFICIAL_BAT_N},
        pitcher_opps={pid: 4000 for pid in pitchers},
        hyper=hyper,
    )


@pytest.fixture
def rich_client(monkeypatch):
    rows = _rich_rows()

    @contextmanager
    def fake_conn():
        yield _FakeConn(rows)

    hyper = Hyperparameters(sigma2=0.4, tau2=0.01, pairs_used=99)
    monkeypatch.setattr(players_module, "conn", fake_conn)
    monkeypatch.setattr(
        players_module, "load_insight_universe", lambda *a, **k: _rich_universe(hyper)
    )
    return TestClient(app)


def test_unfiltered_coverage_passes_and_both_sides_rank(rich_client):
    """未篩選：全 scope 覆蓋率過閘門，天敵／優勢雙向產生，1 PA 永不入榜。"""
    res = rich_client.get(
        "/api/v1/players/BAT/matchups/insights",
        params={"role": "batting", "scope": "range",
                "from_year": 2024, "to_year": 2025},
    )
    assert res.status_code == 200
    body = res.json()

    assert body["coverage"]["passed"] is True
    assert body["coverage"]["ratio"] == pytest.approx(452 / 600, abs=0.01)
    assert [c["opp_id"] for c in body["disadvantages"]] == ["ACE"]
    assert [c["opp_id"] for c in body["advantages"]] == ["BULLY"]
    ranked_ids = {c["opp_id"] for c in body["advantages"] + body["disadvantages"]}
    assert "NOBODY" not in ranked_ids and "SUPPRESS" not in ranked_ids


def test_opponent_team_filter_restricts_candidates_only(rich_client):
    """P1-1：指定隊伍只限制候選對手，覆蓋率仍以全 scope 評估。

    缺陷版把 opponent_team 過濾放在覆蓋率之前（分子縮成單隊、分母仍是全
    生涯官方機會數），查 AJL011 時 coverage 150/600=0.25 會誤觸 fail-closed
    → 此測試在 a1fcbe7 必紅。
    """
    res = rich_client.get(
        "/api/v1/players/BAT/matchups/insights",
        params={"role": "batting", "scope": "range",
                "from_year": 2024, "to_year": 2025, "opponent_team": "AJL011"},
    )
    assert res.status_code == 200
    body = res.json()

    # 全 scope 覆蓋率不受隊伍篩選影響。
    assert body["coverage"]["passed"] is True
    assert body["coverage"]["ratio"] == pytest.approx(452 / 600, abs=0.01)
    assert body["coverage"]["scope"] == "all_opponents"
    # 候選只剩指定 franchise（AJK011 舊碼須被 AJL011 命中）。
    assert [c["opp_id"] for c in body["advantages"]] == ["BULLY"]
    assert body["disadvantages"] == []
    # 查詢後樣本量與全 scope 覆蓋率分開回報，不共用同一欄位。
    assert body["query_sample"]["opponent_team"] == "AJL011"
    assert body["query_sample"]["opponents"] == 1
    assert body["query_sample"]["sampled_opportunities"] == 150


def test_opponent_team_filter_other_franchise(rich_client):
    res = rich_client.get(
        "/api/v1/players/BAT/matchups/insights",
        params={"role": "batting", "scope": "range",
                "from_year": 2024, "to_year": 2025, "opponent_team": "ACN011"},
    )
    body = res.json()

    assert body["coverage"]["passed"] is True
    assert [c["opp_id"] for c in body["disadvantages"]] == ["ACE"]
    assert body["advantages"] == []
    # ACE(300)+NOBODY(1)+SUPPRESS(1) 同隊。
    assert body["query_sample"]["sampled_opportunities"] == 302


def test_truly_low_coverage_still_fails_closed(monkeypatch):
    """P1-1 保護保留：全 scope 覆蓋率真的不足時仍 fail-closed。"""
    rows = [_row(2025, "ACE", "王牌", ab=150, singles=15, so=45)]

    @contextmanager
    def fake_conn():
        yield _FakeConn(rows)

    universe = _rich_universe(Hyperparameters(sigma2=0.4, tau2=0.01, pairs_used=99))
    monkeypatch.setattr(players_module, "conn", fake_conn)
    monkeypatch.setattr(
        players_module, "load_insight_universe", lambda *a, **k: universe
    )
    client = TestClient(app)

    res = client.get(
        "/api/v1/players/BAT/matchups/insights",
        params={"role": "batting", "scope": "season", "season": 2025},
    )
    body = res.json()

    # 樣本 150／官方 600 = 0.25 < 0.60。
    assert body["coverage"]["passed"] is False
    assert body["advantages"] == [] and body["disadvantages"] == []
    assert body["sensitivity"] is None
    assert "覆蓋" in body["sample_note"]


@pytest.fixture
def no_prior_client(monkeypatch):
    rows = _rich_rows()

    @contextmanager
    def fake_conn():
        yield _FakeConn(rows)

    monkeypatch.setattr(players_module, "conn", fake_conn)
    monkeypatch.setattr(
        players_module, "load_insight_universe", lambda *a, **k: _rich_universe(None)
    )
    return TestClient(app)


def test_prior_unavailable_fails_closed(no_prior_client):
    """P1-2：pairs_used=0（hyper=None）→ 不輸出方向性排行，metadata 如實回報。

    缺陷版用 tau²=sigma² 偽先驗（等效 1 機會），1 PA 對手 credibility 可達
    0.99 而入榜 → 此測試在 a1fcbe7 必紅。
    """
    res = no_prior_client.get(
        "/api/v1/players/BAT/matchups/insights",
        params={"role": "batting", "scope": "range",
                "from_year": 2024, "to_year": 2025},
    )
    assert res.status_code == 200
    body = res.json()

    # 1 PA 1 HR 與 1 PA 極端壓制永遠不得入榜；先驗不可估時全面 fail-closed。
    assert body["advantages"] == [] and body["disadvantages"] == []
    assert body["sensitivity"] is None
    assert body["method"]["prior_available"] is False
    assert body["method"]["pairs_used"] == 0
    assert body["method"]["tau2"] is None
    assert "先驗" in body["sample_note"]
