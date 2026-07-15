from __future__ import annotations

import pytest

from cpbl.models.umpire_impact import (
    Call,
    PitchState,
    ProxyZone,
    post_to_pre_count,
    proxy_call,
    signed_edge_distance_cm,
    transition_called_pitch,
)


def _state(
    *,
    batting_side: str = "1",
    score_diff_home: int = 0,
    bases: str = "___",
    outs: int = 0,
    balls: int = 0,
    strikes: int = 0,
) -> PitchState:
    return PitchState(
        batting_side=batting_side,
        inning=1,
        score_diff_home=score_diff_home,
        bases=bases,
        outs=outs,
        balls=balls,
        strikes=strikes,
    )


@pytest.mark.parametrize(
    ("call", "post_balls", "post_strikes", "expected"),
    [
        (Call.BALL, 1, 0, (0, 0)),
        (Call.BALL, 4, 2, (3, 2)),
        (Call.STRIKE, 0, 1, (0, 0)),
        (Call.STRIKE, 3, 3, (3, 2)),
    ],
)
def test_post_to_pre_count_restores_valid_called_pitch_state(
    call: Call, post_balls: int, post_strikes: int, expected: tuple[int, int]
) -> None:
    assert post_to_pre_count(call, post_balls, post_strikes) == expected


@pytest.mark.parametrize(
    ("call", "post_balls", "post_strikes"),
    [
        (Call.BALL, 0, 0),
        (Call.BALL, 1, 3),
        (Call.STRIKE, 0, 0),
        (Call.STRIKE, 4, 1),
    ],
)
def test_post_to_pre_count_rejects_impossible_state(
    call: Call, post_balls: int, post_strikes: int
) -> None:
    with pytest.raises(ValueError):
        post_to_pre_count(call, post_balls, post_strikes)


def test_nonterminal_called_pitch_changes_only_count() -> None:
    before = _state(bases="1_3", outs=1, balls=1, strikes=1)

    after_ball = transition_called_pitch(before, Call.BALL)
    after_strike = transition_called_pitch(before, Call.STRIKE)

    assert after_ball.next_state == _state(bases="1_3", outs=1, balls=2, strikes=1)
    assert after_strike.next_state == _state(bases="1_3", outs=1, balls=1, strikes=2)
    assert after_ball.immediate_runs == after_strike.immediate_runs == 0
    assert not after_ball.half_over
    assert not after_strike.half_over


@pytest.mark.parametrize(
    ("bases", "expected_bases", "expected_runs"),
    [
        ("___", "1__", 0),
        ("1__", "12_", 0),
        ("_2_", "12_", 0),
        ("__3", "1_3", 0),
        ("12_", "123", 0),
        ("1_3", "123", 0),
        ("_23", "123", 0),
        ("123", "123", 1),
    ],
)
def test_fourth_ball_applies_only_forced_advances(
    bases: str, expected_bases: str, expected_runs: int
) -> None:
    transition = transition_called_pitch(_state(bases=bases, balls=3, strikes=2), Call.BALL)

    expected_diff = -expected_runs
    assert transition.next_state == _state(
        score_diff_home=expected_diff, bases=expected_bases, balls=0, strikes=0
    )
    assert transition.immediate_runs == expected_runs
    assert not transition.half_over


def test_bases_loaded_walk_updates_home_score_diff_when_home_team_bats() -> None:
    transition = transition_called_pitch(
        _state(batting_side="2", bases="123", balls=3, strikes=2), Call.BALL
    )

    assert transition.next_state == _state(
        batting_side="2", score_diff_home=1, bases="123", balls=0, strikes=0
    )
    assert transition.immediate_runs == 1


def test_third_strike_starts_next_plate_appearance_when_inning_continues() -> None:
    transition = transition_called_pitch(
        _state(bases="_23", outs=1, balls=3, strikes=2), Call.STRIKE
    )

    assert transition.next_state == _state(bases="_23", outs=2, balls=0, strikes=0)
    assert transition.immediate_runs == 0
    assert not transition.half_over


def test_third_strike_with_two_outs_ends_half_inning() -> None:
    transition = transition_called_pitch(
        _state(bases="123", outs=2, balls=3, strikes=2), Call.STRIKE
    )

    assert transition.next_state is None
    assert transition.immediate_runs == 0
    assert transition.half_over


def test_proxy_zone_uses_existing_fixed_contract_and_signed_distance() -> None:
    zone = ProxyZone()

    assert proxy_call(0.0, 0.75, zone) is Call.STRIKE
    assert proxy_call(0.30, 0.75, zone) is Call.BALL
    assert signed_edge_distance_cm(0.0, 0.75, zone) == pytest.approx(25.3)
    assert signed_edge_distance_cm(0.30, 0.75, zone) == pytest.approx(-4.7)


def test_proxy_zone_sensitivity_expands_and_contracts_symmetrically() -> None:
    zone = ProxyZone()

    expanded = zone.shifted(2.0)
    contracted = zone.shifted(-2.0)

    assert expanded.half_width == pytest.approx(zone.half_width + 0.02)
    assert expanded.bottom == pytest.approx(zone.bottom - 0.02)
    assert expanded.top == pytest.approx(zone.top + 0.02)
    assert contracted.half_width == pytest.approx(zone.half_width - 0.02)
    assert contracted.bottom == pytest.approx(zone.bottom + 0.02)
    assert contracted.top == pytest.approx(zone.top - 0.02)
