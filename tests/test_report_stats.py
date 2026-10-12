from datetime import UTC, date, datetime, timedelta

import pytest

from cpbl.api.between_games import pitcher_usage, pregame_schedule, sum_batting
from cpbl.reports.stats import field_candidates, sum_pitching, three_periods


def test_null_and_real_zero_are_distinct():
    assert sum_batting([])["pa"] is None
    assert sum_pitching([{"outs": 0, "pitch_cnt": 0}])["pitch_cnt"] == 0
    assert sum_pitching([{"outs": 7}, {"outs": None}])["outs"] is None
    assert sum_pitching([{"outs": 7}])["ip"] == "2.1"


def test_usage_dates_roles_and_missing_pitch_count():
    usage = pitcher_usage([
        {"game_sno": 1, "date": date(2026, 10, 9), "date_trusted": True,
         "role_type": "先發", "outs": 7, "pitch_cnt": 45},
        {"game_sno": 2, "date": date(2026, 10, 10), "date_trusted": True,
         "role_type": "最後一任", "outs": 2, "pitch_cnt": None},
    ], date(2026, 10, 11))
    assert usage["ip"] == "3.0" and usage["consecutive_days"] == 2
    assert usage["pitch_total"] is None and usage["appearances"][1]["role_type"] == "最後一任"
    usage["appearances"][1]["date_trusted"] = False
    untrusted = pitcher_usage(usage["appearances"], date(2026, 10, 11))
    assert untrusted["consecutive_days"] is None and untrusted["days_to_next"] is None


@pytest.mark.parametrize("flag", [None, "", "unknown", "Y"])
def test_no_positive_pregame_evidence_means_no_announcement(flag):
    row = {"raw_present_status": 1, "raw_game_result": None, "is_play_ball": flag,
           "raw_game_date": date(2026, 10, 10), "fetched_at": datetime(2026, 10, 10, tzinfo=UTC),
           "home_p": "fixture"}
    assert pregame_schedule([row], date(2026, 10, 10))["home_starter"]["status"] == "unverified"


def test_first_time_not_last_seen_and_late_version_is_rejected():
    first = datetime(2026, 10, 10, tzinfo=UTC)
    pre = {"raw_present_status": 1, "raw_game_result": None, "is_play_ball": "N",
           "raw_game_date": date(2026, 10, 10), "fetched_at": first,
           "last_seen_at": first + timedelta(days=3), "home_p": "early", "payload_hash": "v1"}
    opened = {"is_play_ball": "Y", "fetched_at": first + timedelta(hours=1)}
    late = {**pre, "home_p": "late", "fetched_at": first + timedelta(hours=2)}
    starter = pregame_schedule([late, opened, pre], date(2026, 10, 10))["home_starter"]
    assert starter["acnt"] == "early" and starter["observed_at"] == first


def test_three_periods_filter_real_team_and_opponent():
    rows = [
        {"player_id": "p", "team_code": "A", "opponent_code": "B", "game_key": "a1", "outs": 3},
        {"player_id": "p", "team_code": "A", "opponent_code": "C", "game_key": "a2", "outs": 6},
        {"player_id": "p", "team_code": "D", "opponent_code": "B", "game_key": "a3", "outs": 9},
    ]
    periods = three_periods(series=[], regular=rows, role="pitching", player_id="p", team="A",
                            opponent="B", series_keys=["e1"], regular_keys=["a1", "a2"],
                            cutoff="截至X", complete_population=True)
    assert periods["opponent_regular"]["counts"]["outs"] == 3
    assert periods["regular"]["counts"]["outs"] == 9
    assert periods["series"]["status"] == "missing"


def test_field_ties_remain_candidates_and_missing_is_not_dh():
    fields = field_candidates([
        {"player_id": "p1", "team_code": "A", "pos": "捕手", "g": 8},
        {"player_id": "p2", "team_code": "A", "pos": "捕手", "g": 8},
    ], team="A", player_ids={"p1", "p2", "missing"})
    assert fields["捕手"]["player_ids"] == ["p1", "p2"]
    assert fields["捕手"]["status"] == "tied" and "DH" not in fields


def _watch_player(pid, role, counts, *, origin="last_game", team="A"):
    available = {"status": "available", "counts": counts, "covered_game_keys": ["a1"],
                 "source": "fixture", "sample": {}}
    missing = {"status": "missing", "counts": {}}
    return {"player_id": pid, "team_code": team, "role": role,
            "last_game": available if origin == "last_game" else missing,
            "periods": {"series": available if origin == "series" else missing},
            "vs_starter": {**available, "pitcher_id": "starter"} if origin == "season_vs_pitcher" else missing}


def test_watch_points_do_not_promote_strikeouts_over_runs_or_squeeze_homer_hitter():
    from cpbl.reports.stats import watch_points

    players = [
        _watch_player("bad", "pitching", {"outs": 12, "er": 7, "bb": 5, "so": 8}),
        _watch_player("clean", "pitching", {"outs": 18, "er": 0, "bb": 1, "so": 0}),
        _watch_player("slugger", "batting", {"pa": 4, "h": 2, "hr": 2, "xbh": 2, "bb": 0}),
    ]
    points = watch_points(players, team_codes=["A"], anchor_key="e1")
    assert [p["player_id"] for p in points] == ["slugger", "clean"]
    assert points[1]["count_line"]["er"] == 0
    assert points[1]["count_line"]["so"] == 0
    players[0]["last_game"]["counts"]["so"] = 30
    assert watch_points(players, team_codes=["A"], anchor_key="e1") == points


def test_watch_points_require_actual_positive_evidence_without_filling_unknowns():
    from cpbl.reports.stats import watch_points

    players = [
        _watch_player("unknown-er", "pitching", {"outs": 18, "er": None, "bb": 0, "so": 10}),
        _watch_player("unknown-bb", "pitching", {"outs": 18, "er": 0, "bb": None, "so": 10}),
        _watch_player("no-outs", "pitching", {"outs": 0, "er": 0, "bb": 0, "so": 0}),
        _watch_player("single", "batting", {"h": 1, "bb": 0, "hr": 0, "xbh": 0}),
        _watch_player("walks", "batting", {"h": None, "bb": 2, "hr": None, "xbh": None}),
    ]
    points = watch_points(players, team_codes=["A"], anchor_key="e1")
    assert [p["player_id"] for p in points] == ["walks"]
    assert points[0]["count_line"]["h"] is None
    assert points[0]["count_line"]["hr"] is None


def test_watch_points_preserve_source_priority_and_one_person_per_team():
    from cpbl.reports.stats import watch_points

    players = [
        _watch_player("last", "batting", {"h": 2, "bb": 0, "hr": 0, "xbh": 0}),
        _watch_player("series", "pitching", {"outs": 21, "er": 0, "bb": 1, "so": 9}, origin="series"),
        _watch_player("pair", "batting", {"h": 10, "hr": 5, "xbh": 5, "bb": 4}, origin="season_vs_pitcher"),
        _watch_player("other-team", "batting", {"h": 20, "hr": 10}, team="B"),
    ]
    points = watch_points(players, team_codes=["A"], anchor_key="e1")
    assert [(p["player_id"], p["origin"]) for p in points] == [("last", "last_game"), ("series", "series")]
    assert len({p["player_id"] for p in points}) == len(points)
