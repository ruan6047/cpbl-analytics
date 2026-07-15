from __future__ import annotations

from dataclasses import replace

from cpbl.models.umpire_impact import RunStateKey
from cpbl.models.umpire_impact_data import (
    HISTORICAL_LIVELOG_SQL,
    LINKED_CALLED_CTE,
    SCORED_CALLED_SQL,
    LinkedCalledRow,
    LivelogRow,
    TrackingAudit,
    build_called_pitches,
    build_run_observations,
)


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def test_linker_uses_full_state_and_call_flag_without_arbitrary_row_selection() -> None:
    sql = _norm(LINKED_CALLED_CTE)

    for field in (
        "pitcher_acnt",
        "hitter_acnt",
        "inning_seq",
        "batting_order",
        "pitch_cnt",
        "ball_cnt",
        "strike_cnt",
        "out_cnt",
    ):
        assert f"l.{field} = t.{field}" in sql
    assert "t.pitch_call = 'BallCalled' AND l.is_ball" in sql
    assert "t.pitch_call = 'StrikeCalled' AND l.is_strike" in sql
    assert "row_number()" not in sql.lower()


def test_tracking_audit_fails_closed_at_spec_thresholds() -> None:
    passing = TrackingAudit(
        total_called=24_270,
        located_called=24_270,
        unique_linked=24_195,
        valid_post_count=24_226,
        linked_missing_context=0,
    )
    low_link = TrackingAudit(1_000, 1_000, 994, 1_000, 0)
    low_count = TrackingAudit(1_000, 1_000, 1_000, 994, 0)
    missing_context = TrackingAudit(1_000, 1_000, 1_000, 1_000, 1)

    assert passing.passes
    assert not low_link.passes
    assert not low_count.passes
    assert not missing_context.passes
    assert passing.link_rate == 24_195 / 24_270
    assert passing.valid_count_rate == 24_226 / 24_270


def test_tracking_audit_fails_when_no_called_pitches_exist() -> None:
    audit = TrackingAudit(0, 0, 0, 0, 0)

    assert audit.link_rate == 0.0
    assert audit.valid_count_rate == 0.0
    assert not audit.passes


def _row(
    event: int,
    *,
    inning: int = 1,
    side: str = "1",
    batting_order: int = 1,
    hitter: str = "h1",
    pitcher: str = "p1",
    pitch_cnt: int | None = 1,
    outs: int = 0,
    balls: int = 0,
    strikes: int = 0,
    first: str | None = None,
    is_ball: bool = False,
    is_strike: bool = False,
    action: str | None = None,
    away_score: int = 0,
    home_score: int = 0,
) -> LivelogRow:
    return LivelogRow(
        year=2020,
        kind_code="A",
        game_sno=1,
        main_event_no=event,
        inning=inning,
        side=side,
        batting_order=batting_order,
        hitter_acnt=hitter,
        pitcher_acnt=pitcher,
        pitch_cnt=pitch_cnt,
        outs=outs,
        balls=balls,
        strikes=strikes,
        first_base=first,
        second_base=None,
        third_base=None,
        is_ball=is_ball,
        is_strike=is_strike,
        batting_action_name=action,
        is_change_player=False,
        away_score=away_score,
        home_score=home_score,
    )


def test_historical_loader_reconstructs_pre_pitch_count_and_remaining_runs() -> None:
    rows = [
        _row(1, pitch_cnt=1, balls=1, is_ball=True),
        _row(2, pitch_cnt=2, balls=1, strikes=1, is_strike=True),
        # 同一球的投球列與結果列只能形成一個 state；結果列才更新比分。
        _row(3, pitch_cnt=3, balls=1, strikes=1, is_strike=True),
        _row(4, pitch_cnt=3, balls=1, strikes=1, action="一壘安打", away_score=1),
        _row(
            5,
            batting_order=2,
            hitter="h2",
            pitch_cnt=4,
            balls=0,
            strikes=1,
            is_strike=True,
            first="runner",
            away_score=1,
        ),
        # 每場最後半局可能因再見而截斷，必須整個排除。
        _row(6, side="2", pitcher="p2", pitch_cnt=1, balls=1, is_ball=True, away_score=1),
    ]

    result = build_run_observations(rows)

    assert [row.key for row in result.observations] == [
        RunStateKey("1", "___", 0, 0, 0),
        RunStateKey("1", "___", 0, 1, 0),
        RunStateKey("1", "___", 0, 1, 1),
        RunStateKey("1", "1__", 0, 0, 0),
    ]
    assert [row.remaining_runs for row in result.observations] == [1, 1, 1, 0]
    assert [row.state.score_diff_home for row in result.win_observations] == [0, 0, 0, -1]
    assert {row.outcome_home for row in result.win_observations} == {0.0}
    assert all(row.game_id == "2020-A-1" for row in result.win_observations)
    assert result.games == 1
    assert result.excluded_final_halves == 1
    assert result.duplicate_pitch_rows == 1
    assert result.invalid_states == 0


def test_historical_loader_skips_invalid_counts_instead_of_clamping() -> None:
    rows = [
        _row(1, pitch_cnt=1, balls=4, is_ball=True),
        _row(2, pitch_cnt=2, balls=4, strikes=1, is_strike=True),
        _row(3, side="2", pitcher="p2", pitch_cnt=1, is_strike=True),
    ]

    result = build_run_observations(rows)

    assert len(result.observations) == 1
    assert result.invalid_states == 1


def test_historical_query_is_read_only_and_time_bounded() -> None:
    sql = _norm(HISTORICAL_LIVELOG_SQL).lower()

    assert "from cpbl.game_livelog" in sql
    assert "year between %(from_year)s and %(to_year)s" in sql
    assert "kind_code = %(kind)s" in sql
    assert all(keyword not in sql for keyword in ("insert ", "update ", "delete "))


def test_scoring_loader_reconstructs_called_pitch_and_fixed_exclusions() -> None:
    valid = LinkedCalledRow(
        year=2026,
        kind_code="A",
        game_sno=1,
        pitcher_acnt="p1",
        pitch_cnt=1,
        pitch_call="BallCalled",
        ball_cnt=1,
        strike_cnt=0,
        out_cnt=0,
        inning_seq=1,
        visiting_home_type="1",
        first_base=None,
        second_base=None,
        third_base=None,
        pre_away_score=0,
        pre_home_score=0,
        plate_loc_side=0.0,
        plate_loc_height=0.75,
        catcher_acnt="c1",
        head_umpire="主審甲",
        venue="球場",
        home_team_code="HOME",
        away_team_code="AWAY",
    )
    invalid_count = replace(valid, pitch_cnt=2, ball_cnt=0)

    result = build_called_pitches([valid, invalid_count])

    assert len(result.pitches) == 1
    assert result.pitches[0].state.balls == 0
    assert result.pitches[0].observed_call.value == "ball"
    assert result.exclusions == {"invalid_post_count": 1}


def test_scoring_query_joins_umpire_venue_and_team_metadata_read_only() -> None:
    sql = _norm(SCORED_CALLED_SQL).lower()

    for token in ("head_umpire", "venue", "home_team_code", "away_team_code"):
        assert token in sql
    assert all(keyword not in sql for keyword in ("insert ", "update ", "delete "))
