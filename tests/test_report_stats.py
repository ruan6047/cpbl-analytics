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
