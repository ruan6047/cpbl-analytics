"""合成跨系列 fixture；C901 不是正式場號，也不當公開資料證據。"""

from datetime import UTC, date, datetime

import pytest

from cpbl.reports import assembler, readers
from cpbl.reports.context import ContextChanged


def transition_inputs(monkeypatch):
    games = [{"year": 2026, "kind_code": "E", "game_sno": n,
              "game_date": date(2026, 10, 8 + n), "completed": True,
              "away_team_code": "ADD011", "home_team_code": "ACN011",
              "away_score": 2, "home_score": 8} for n in range(1, 5)]
    games[1].update(away_team_code="ACN011", home_team_code="ADD011", away_score=2, home_score=4)
    games[2].update(away_score=4, home_score=2)
    games += [{**games[0], "kind_code": "A", "game_sno": 88,
               "game_date": date(2026, 9, 30), "away_team_code": "ACN011", "home_team_code": "AAA011"}]
    schedule = {"year": 2026, "kind_code": "C", "game_sno": 901,
                "raw_game_date": date(2026, 10, 17), "raw_present_status": 1,
                "raw_game_result": "", "is_play_ball": "N", "payload_hash": "synthetic-C901",
                "fetched_at": datetime(2026, 10, 13, tzinfo=UTC),
                "away_p": "0000000013", "home_p": "0000000014",
                "raw_payload": {"VisitingTeamCode": "ACN011", "HomeTeamCode": "AAA011"}}
    records = [{"year": 2026, "round": kind, "team_code": team, "official": True,
                "complete": True, "source_url": "https://www.cpbl.com.tw/synthetic",
                "roster_version": f"synthetic-{kind}-{team}", "observed_at": "2026-10-13T00:00:00Z",
                "announced_total": 2, "members": [
                    {"player_id": hitter, "name": f"{kind}打者", "role": "batting"},
                    {"player_id": pitcher, "name": f"{kind}投手", "role": "pitching"}]} for kind, team, hitter, pitcher in (
                    ("E", "ADD011", "0000000001", "0000000003"),
                    ("E", "ACN011", "0000000002", "0000000013"),
                    ("C", "ACN011", "0000000011", "0000000013"),
                    ("C", "AAA011", "0000000012", "0000000014"))]
    monkeypatch.setattr(readers, "games", lambda *_: games)
    monkeypatch.setattr(readers, "schedules", lambda *_: [schedule])
    for func in ("lineup_revisions", "source_revisions", "pitching_sources", "fielding"):
        monkeypatch.setattr(readers, func, lambda *_: [])
    calls = []
    def box(cur, season, kind, snos, role):
        calls.append((kind, tuple(snos), role))
        if not snos or kind == "C":
            return []
        pid = "0000000013" if role == "pitching" else "0000000011"
        return [{"player_id": pid, "team_code": "ACN011", "opponent_code": "AAA011" if kind == "A" else "ADD011",
                 "name": "合成", "game_sno": n, "game_key": f"2026/{kind}/{n}", "role_type": "先發",
                 "outs": 18, "er": 0, "pitch_cnt": 80, "pa": 4, "ab": 4, "h": 2, "hr": 1,
                 "bb": 0, "so": 2, "b2": 0, "b3": 0, "hbp": 0, "sf": 0} for n in snos]
    monkeypatch.setattr(readers, "box", box)
    monkeypatch.setattr(readers, "people", lambda *_: {})
    monkeypatch.setattr(readers, "matchups", lambda *_: {})
    monkeypatch.setattr(assembler.background, "current_matches", lambda *_: {})
    monkeypatch.setattr(assembler.background, "team_background", lambda cur, reg, rows, teams: [])
    monkeypatch.setattr(assembler.background, "player_background", lambda *a, **k: {})
    return records, calls


def test_e4_history_and_unfinished_c_comparison_use_independent_teams_rosters_and_periods(monkeypatch):
    records, calls = transition_inputs(monkeypatch)
    base = assembler.build_report(object(), 2026, "E", 4, population_records=records)
    result = assembler.build_report(object(), 2026, "E", 4, "C", 901,
                                    base["journey_context"]["context_hash"], population_records=records)
    assert result["game"]["away_team_code"] == "ADD011"
    assert result["game"]["home_team_code"] == "ACN011"
    assert result["anchor"]["through_game_keys"] == [f"2026/E/{n}" for n in range(1, 5)]
    comparison = result["comparison"]
    assert comparison["game"]["game_sno"] == 901
    assert [comparison["game"][f"{side}_team_code"] for side in ("away", "home")] == ["ACN011", "AAA011"]
    assert {r["round"] for r in comparison["population"]} == {"C"}
    assert comparison["series_game_keys"] == []
    hitter = next(p for p in comparison["players"] if p["player_id"] == "0000000011" and p["role"] == "batting")
    assert hitter["name"] == "C打者"
    assert hitter["periods"]["series"]["counts"]["pa"] is None
    assert hitter["periods"]["opponent_regular"]["counts"]["h"] == 2
    assert hitter["vs_starter"]["pitcher_id"] == "0000000014"
    pitcher = next(p for p in comparison["players"] if p["player_id"] == "0000000013" and p["role"] == "pitching")
    assert pitcher["pitching_usage"]["appearances"][-1]["game_key"] == "2026/E/4"
    assert pitcher["pitching_usage"]["days_to_next"] == 5
    assert all(p["team_code"] != "ADD011" for p in comparison["players"])
    assert all(901 not in snos for kind, snos, role in calls)


def test_c_population_version_is_pinned_in_first_read_even_before_y_selection(monkeypatch):
    records, _ = transition_inputs(monkeypatch)
    base = assembler.build_report(object(), 2026, "E", 4, population_records=records)
    changed = [{**r, "roster_version": "changed-C"} if r["round"] == "C" else r for r in records]
    with pytest.raises(ContextChanged):
        assembler.build_report(object(), 2026, "E", 4, "C", 901,
                               base["journey_context"]["context_hash"], population_records=changed)


def test_y_preview_anchor_is_latest_completed_x_and_never_guesses_y(monkeypatch):
    transition_inputs(monkeypatch)
    found = assembler.report_anchor(object(), 2026, "C", 901)
    assert found["status"] == "ok"
    assert found["anchor"] == {"kind_code": "E", "game_sno": 4}
    assert assembler.report_anchor(object(), 2026, "E", 4)["status"] == "final"
    # 公告 G1 沒有既存正式列：不造場號、不回 E4 背景冒充。
    assert assembler.report_anchor(object(), 2026, "C", 1)["status"] == "not_found"


def test_context_only_first_read_pins_same_context_without_background_reads(monkeypatch):
    records, calls = transition_inputs(monkeypatch)
    heavy = []
    for func in ("people", "source_revisions", "pitching_sources"):
        monkeypatch.setattr(readers, func, lambda *_, name=func: heavy.append(name) or ({} if name == "people" else []))
    monkeypatch.setattr(assembler.background, "player_background",
                        lambda *a, **k: heavy.append("player_background") or {})
    light = assembler.build_report(object(), 2026, "E", 4, population_records=records, context_only=True)
    assert set(light) == {"season", "kind_code", "game_sno", "status", "game", "journey_context"}
    assert calls == [] and heavy == []  # 第一讀不做 box、來源版本或逐人背景組裝。
    full = assembler.build_report(object(), 2026, "E", 4, population_records=records)
    assert calls and "people" in heavy and "player_background" in heavy
    assert light["journey_context"] == full["journey_context"]
    enriched = assembler.build_report(object(), 2026, "E", 4, "C", 901,
                                      light["journey_context"]["context_hash"], population_records=records)
    assert enriched["comparison"]["game"]["game_sno"] == 901
    missing = assembler.build_report(object(), 2026, "E", 99)
    assert missing["status"] == "not_found" and assembler.build_report(object(), 2026, "E", 99, context_only=True) == missing


def test_full_read_without_target_rejects_changed_context(monkeypatch):
    records, _ = transition_inputs(monkeypatch)
    light = assembler.build_report(object(), 2026, "E", 4, population_records=records, context_only=True)
    pinned = light["journey_context"]["context_hash"]
    changed = [{**r, "roster_version": "changed-C"} if r["round"] == "C" else r for r in records]
    with pytest.raises(ContextChanged):
        assembler.build_report(object(), 2026, "E", 4, supplied_hash=pinned, population_records=changed)
    full = assembler.build_report(object(), 2026, "E", 4, supplied_hash=pinned, population_records=records)
    assert full["journey_context"]["context_hash"] == pinned and full["players"]
