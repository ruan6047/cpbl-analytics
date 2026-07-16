"""/api/v1/players/{id}/matchups/insights 端點契約測試（fake DB、無外部依賴）。"""

from __future__ import annotations

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


def _row(year, opp_id, opp_name, *, ab, singles=0, doubles=0, hr=0, bb=0, so=0):
    hits = singles + doubles + hr
    values = {
        "year": year, "opp_id": opp_id, "opp_name": opp_name,
        "opp_team_code": "ACN011", "opp_team": "隊",
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
    def __init__(self, rows):
        self._rows = rows
        self.description = [(c,) for c in _COLUMNS]

    def execute(self, sql, params=None):
        return self

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)


def _fake_universe():
    """官方 baseline universe：BAT 官方生涯 320 機會（覆蓋率會 ~100%），
    ACE 官方被打 wOBA 略高於聯盟（天敵候選）、NOBODY 官方接近聯盟。"""
    hyper = Hyperparameters(sigma2=0.4, tau2=0.01, pairs_used=99)
    return InsightUniverse(
        bat_league_mean=0.320,
        pit_league_mean=0.315,
        sigma2=0.4,
        hitter_baselines={"BAT": WobaLine(0.320 * 320, 320)},
        pitcher_baselines={
            "ACE": WobaLine(0.315 * 4000, 4000),
            "NOBODY": WobaLine(0.315 * 4000, 4000),
        },
        hitter_opps={"BAT": 320},
        pitcher_opps={"ACE": 4000, "NOBODY": 4000},
        pairs=(),
        expected={},
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
