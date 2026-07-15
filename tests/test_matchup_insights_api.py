"""/api/v1/players/{id}/matchups/insights 端點契約測試（fake DB、無外部依賴）。"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from cpbl.api.main import app
from cpbl.api.matchups import InsightUniverse
from cpbl.api.routers import players as players_module
from cpbl.models.matchup_insights import Hyperparameters, PairSample, WobaLine

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
    hyper = Hyperparameters(sigma2=0.4, tau2=0.002, pairs_used=99)
    ace_line = WobaLine(0.089 * 300, 300)   # 對應 SQL rows：300AB 30 一安
    nobody_line = WobaLine(2.10, 1)
    pairs = (
        PairSample("BAT", "ACE", ace_line),
        PairSample("BAT", "NOBODY", nobody_line),
    )
    bat_total = WobaLine(
        ace_line.weighted_sum + nobody_line.weighted_sum + 0.32 * 2000,
        301 + 2000,
    )
    return InsightUniverse(
        league=WobaLine(0.32 * 10_000, 10_000),
        league_mean=0.32,
        hitter_totals={"BAT": bat_total},
        pitcher_totals={
            "ACE": WobaLine(ace_line.weighted_sum + 0.32 * 1500, 1800),
            "NOBODY": WobaLine(nobody_line.weighted_sum + 0.32 * 300, 301),
        },
        pairs=pairs,
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


def test_insights_surface_credible_suppression_and_gate_small_samples(client):
    res = client.get(
        "/api/v1/players/BAT/matchups/insights",
        params={"role": "batting", "scope": "range", "from_year": 2024, "to_year": 2025},
    )
    assert res.status_code == 200
    body = res.json()

    assert [c["opp_id"] for c in body["disadvantages"]] == ["ACE"]
    assert body["advantages"] == []          # 1 轟路人被閘門擋下
    assert body["gated_out"] >= 1
    # 跨年先加總：ACE 顯示的資料期間涵蓋兩年。
    ace = body["disadvantages"][0]
    assert (ace["from_year"], ace["to_year"]) == (2024, 2025)
    assert ace["opportunities"] == 300
    assert ace["credibility"] >= body["method"]["credibility_gate"]
    assert body["method"]["metric"] == "woba_generic_v1"
    assert body["sensitivity"]["reference_members"] == ["ACE"]
    assert "描述性統計" in body["disclaimer"]


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
