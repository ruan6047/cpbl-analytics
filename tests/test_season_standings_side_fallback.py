"""#223：戰績榜團隊 OPS/ERA/WHIP 依打擊／投球側分別退回 *_seasons（不連 DB）。

2025 實況：pitching_current 仍有殘留列（ERA/WHIP 有值、鍵為 6 碼 AAA011），batting_current
整年無列 → 舊邏輯只看「整包非空」就不退回，六隊 OPS 全 None。"""
import pytest

from cpbl.api.routers import standings

_TEAMS = ["AAA011", "ACN011", "ADD011", "AEO011", "AJL011", "AKP011"]


def _team_stats(season):
    return {
        c: {"name": c, "w": 70, "l": 50, "g": 120, "win_pct": 0.5 + i / 100,
            "rs_pg": 4.0, "ra_pg": 3.5, "last10": []}
        for i, c in enumerate(_TEAMS)
    }


def _patch(monkeypatch, current, seasons):
    calls: list[int] = []

    def fake_seasons(season):
        calls.append(season)
        return seasons

    monkeypatch.setattr(standings.matchup, "team_stats", _team_stats)
    monkeypatch.setattr(standings, "_team_advanced_current_computed", lambda s: current)
    monkeypatch.setattr(standings, "_team_advanced_from_seasons", fake_seasons)
    monkeypatch.setattr(standings, "_team_advanced", lambda s: pytest.fail("不應經過 team_current"))
    return calls


def _by_code(resp):
    return {r["code"]: r for r in resp["standings"]}


def test_missing_batting_side_falls_back_to_seasons(monkeypatch):
    # current 只有投球側（6 碼鍵）；seasons 兩側都有（3 碼鍵），其 ERA/WHIP 刻意與 current 不同。
    current = {c: {"era": 3.0 + i / 10, "whip": 1.2 + i / 100} for i, c in enumerate(_TEAMS)}
    seasons = {c[:3]: {"ops": 0.650 + i / 100, "era": 9.99, "whip": 9.99} for i, c in enumerate(_TEAMS)}
    calls = _patch(monkeypatch, current, seasons)

    rows = _by_code(standings.season_standings(season=2025))

    assert calls == [2025]
    for i, c in enumerate(_TEAMS):
        assert rows[c]["ops"] == pytest.approx(0.650 + i / 100)
        assert rows[c]["era"] == current[c]["era"]
        assert rows[c]["whip"] == current[c]["whip"]


def test_no_batting_in_either_source_stays_none(monkeypatch):
    current = {c: {"era": 3.0, "whip": 1.2} for c in _TEAMS}
    seasons = {c[:3]: {"era": 9.99, "whip": 9.99} for c in _TEAMS}
    _patch(monkeypatch, current, seasons)

    rows = _by_code(standings.season_standings(season=2025))

    for c in _TEAMS:
        assert rows[c]["ops"] is None
        assert rows[c]["era"] == 3.0
        assert rows[c]["whip"] == 1.2


def test_complete_current_is_unchanged_and_skips_seasons(monkeypatch):
    current = {c: {"ops": 0.700 + i / 100, "era": 3.0 + i / 10, "whip": 1.2 + i / 100}
               for i, c in enumerate(_TEAMS)}
    calls = _patch(monkeypatch, current, {})

    rows = _by_code(standings.season_standings(season=2026))

    assert calls == []
    for c in _TEAMS:
        assert {k: rows[c][k] for k in ("ops", "era", "whip")} == current[c]
