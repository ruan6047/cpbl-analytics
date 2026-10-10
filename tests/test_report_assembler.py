from datetime import UTC, date, datetime

import pytest

from cpbl.reports import assembler, readers
from cpbl.reports.context import bounded_context


def enriched_inputs(monkeypatch):
    x = {"year": 2026, "kind_code": "E", "game_sno": 1, "game_date": date(2026, 10, 9),
         "completed": True, "away_team_code": "ADD011", "home_team_code": "ACN011",
         "away_score": 1, "home_score": 4}
    a = {**x, "kind_code": "A", "game_date": date(2026, 9, 30)}
    schedule = {"year": 2026, "kind_code": "E", "game_sno": 2,
                "raw_game_date": date(2026, 10, 10), "raw_present_status": 1,
                "raw_game_result": "", "is_play_ball": "N", "payload_hash": "fixture",
                "fetched_at": datetime(2026, 10, 10, tzinfo=UTC),
                "away_p": "dual", "home_p": "other-p",
                "raw_payload": {"VisitingTeamCode": "ADD011", "HomeTeamCode": "ACN011"}}
    games, schedules = [a, x], [schedule]
    monkeypatch.setattr(readers, "games", lambda *_: games)
    monkeypatch.setattr(readers, "schedules", lambda *_: schedules)
    monkeypatch.setattr(readers, "source_revisions", lambda *_: [])
    monkeypatch.setattr(readers, "pitching_sources", lambda *_: [])
    def box(cur, season, kind, snos, role):
        common = {"game_sno": 1, "game_key": f"2026/{kind}/1", "team_code": "ADD011",
                  "opponent_code": "ACN011", "name": "fixture", "pa": 4, "h": 1,
                  "hr": 0, "bb": 1, "so": 1}
        if role == "pitching":
            return [{**common, "player_id": "pitch-only", "role_type": "最後一任",
                     "outs": 2, "pitch_cnt": 19, "er": 0}]
        return [{**common, "player_id": pid, "ab": 3, "b2": 0, "b3": 0,
                 "hbp": 0, "sf": 0, "ibb": 0} for pid in ("hitter", "dual")]
    monkeypatch.setattr(readers, "box", box)
    monkeypatch.setattr(readers, "people", lambda *_: {})
    monkeypatch.setattr(readers, "fielding", lambda *_: [])
    monkeypatch.setattr(assembler.background, "current_matches", lambda *_: {})
    monkeypatch.setattr(assembler.background, "team_background", lambda *_: [])
    monkeypatch.setattr(assembler.background, "player_background", lambda *a, **k: {})
    return x, games, schedules


def test_enrichment_pairs_only_batting_roles_and_preserves_dual_player(monkeypatch):
    x, games, schedules = enriched_inputs(monkeypatch)
    calls = []
    def pairs(cur, season, hitters, pitchers):
        calls.append(hitters)
        return {(pid, "other-p"): {"pitcher_acnt": "other-p", "pa": 3, "ab": 3,
                                  "h": 1, "b2": 0, "b3": 0, "hr": 0, "bb": 0,
                                  "hbp": 0, "sf": 0, "so": 2, "updated_at": None}
                for pid in ("pitch-only", "dual")}
    monkeypatch.setattr(readers, "matchups", pairs)
    context = bounded_context(x, games, schedules)
    assert context["rows"][0]["game_date"] == "2026-10-10"  # DB date 已經統一 JSON 化。
    result = assembler.build_report(object(), 2026, "E", 1, "E", 2, context["context_hash"])
    assert set(calls[0]) == {"hitter", "dual"}
    pitchers = [p for p in result["players"] if p["role"] == "pitching"]
    assert all(p["vs_starter"]["status"] == "not_applicable" and p["vs_starter"]["pitcher_id"] is None for p in pitchers)
    dual = next(p for p in result["players"] if p["player_id"] == "dual" and p["role"] == "batting")
    assert dual["vs_starter"]["status"] == "available"


def test_usage_box_coverage_is_explicit_and_separate_from_roster(monkeypatch):
    enriched_inputs(monkeypatch)
    result = assembler.build_report(object(), 2026, "E", 1)
    pitcher = next(p for p in result["players"] if p["player_id"] == "pitch-only")
    assert not result["population"][0]["complete"]
    assert pitcher["pitching_usage"]["coverage_status"] == "complete"
    assert pitcher["pitching_usage"]["dates_trusted"] is True


def test_missing_series_box_does_not_claim_precise_usage_interval(monkeypatch):
    x, games, _ = enriched_inputs(monkeypatch)
    games.append({**x, "game_sno": 2, "game_date": date(2026, 10, 10)})
    result = assembler.build_report(object(), 2026, "E", 2)
    pitcher = next(p for p in result["players"] if p["player_id"] == "pitch-only")
    assert pitcher["pitching_usage"]["coverage_status"] == "partial"
    assert pitcher["pitching_usage"]["consecutive_days"] is None
    assert pitcher["pitching_usage"]["days_to_next"] is None


def test_identical_game_sides_rejected_before_roster_or_box_reads(monkeypatch):
    x, _, _ = enriched_inputs(monkeypatch)
    monkeypatch.setattr(readers, "games", lambda *_: [{**x, "home_team_code": x["away_team_code"]}])
    with pytest.raises(ValueError, match="隊伍"):
        assembler.build_report(object(), 2026, "E", 1)


def test_report_keeps_box_source_time_scope_and_x_counts_without_fabricating_population(monkeypatch):
    x = {"year": 2026, "kind_code": "E", "game_sno": 1, "game_date": date(2026, 10, 9),
         "completed": True, "away_team_code": "ADD011", "home_team_code": "ACN011",
         "away_score": 1, "home_score": 4}
    later = {**x, "game_sno": 2, "game_date": date(2026, 10, 10), "home_score": 9}
    fetched = datetime(2026, 10, 10, 3, tzinfo=UTC)
    monkeypatch.setattr(readers, "games", lambda *_: [x, later])
    monkeypatch.setattr(readers, "schedules", lambda *_: [])
    monkeypatch.setattr(readers, "source_revisions", lambda *_: [])
    def versions(cur, season, kind, snos):
        assert (season, kind, snos) == (2026, "E", [1])
        return [{"game_sno": 1, "player_id": "0000000001", "source_version": "fixture-hash",
                 "fetched_at": fetched, "last_seen_at": fetched}]
    monkeypatch.setattr(readers, "pitching_sources", versions)
    def box(cur, season, kind, snos, role):
        if kind == "A":
            assert snos == []
            return []
        assert snos == [1]
        return [{"player_id": "0000000001", "name": "測試投手", "game_sno": 1,
                 "game_key": "2026/E/1", "team_code": "ADD011", "opponent_code": "ACN011",
                 "role_type": "最後一任", "outs": 2, "pitch_cnt": 19,
                 "pa": 4, "h": 2, "hr": 0, "er": 0, "bb": 1, "so": 1}] if role == "pitching" else []
    monkeypatch.setattr(readers, "box", box)
    monkeypatch.setattr(readers, "people", lambda *_: {})
    result = assembler.build_report(object(), 2026, "E", 1)
    assert result["anchor"]["through_game_keys"] == ["2026/E/1"]
    source = next(s for s in result["sources"] if s["source"] == "box_pitching")
    assert source["scope"] == {"year": 2026, "kind": "E", "role": "pitching", "player_id": "0000000001"}
    assert source["source_version"] == "fixture-hash" and source["fetched_at"] == fetched
    assert source["updated_at"] is None  # 取得時間不能冒官方更正發生時刻。
    assert source["covered_game_keys"] == ["2026/E/1"] and source["cutoff_basis"] == "through_X"
    assert all(not r["complete"] for r in result["population"])
    assert result["announcements"]["lineup"]["status"] == "unverified"
    player = result["players"][0]
    assert player["periods"]["series"]["counts"]["ip"] == "0.2"
    assert player["pitching_usage"]["appearances"][0]["role_type"] == "最後一任"
    assert player["ability"]["status"] == "source_unverified"
