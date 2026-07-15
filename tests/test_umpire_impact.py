from __future__ import annotations

import pytest

from cpbl.models.umpire_impact import (
    Call,
    PitchState,
    ProxyZone,
    RunObservation,
    RunStateKey,
    RunValueModel,
    bootstrap_metric_deltas,
    post_to_pre_count,
    proxy_call,
    signed_edge_distance_cm,
    transition_called_pitch,
    tune_alpha,
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


def _observations(
    key: RunStateKey, remaining_runs: list[int], *, game_prefix: str = "g"
) -> list[RunObservation]:
    return [
        RunObservation(key=key, remaining_runs=runs, game_id=f"{game_prefix}{i}")
        for i, runs in enumerate(remaining_runs)
    ]


def test_run_value_model_shrinks_state_distribution_and_backs_off() -> None:
    zero_zero = RunStateKey("1", "___", 0, 0, 0)
    one_zero = RunStateKey("1", "___", 0, 1, 0)
    observations = [
        *_observations(zero_zero, [0, 0, 1]),
        *_observations(one_zero, [1, 1, 2]),
    ]

    model = RunValueModel.fit(observations, alpha=2.0)
    seen = model.distribution(zero_zero)
    unseen_count = model.distribution(RunStateKey("1", "___", 0, 2, 1))

    assert sum(seen) == pytest.approx(1.0)
    assert all(probability > 0 for probability in seen)
    assert unseen_count == pytest.approx(model.parent_distribution(zero_zero))
    assert 0 < model.expected_runs(zero_zero) < 1


def test_run_value_metrics_compare_count_model_with_parent_baseline() -> None:
    favorable = RunStateKey("1", "___", 0, 1, 0)
    unfavorable = RunStateKey("1", "___", 0, 0, 1)
    train = [
        *_observations(favorable, [1, 1, 1, 2]),
        *_observations(unfavorable, [0, 0, 0, 0]),
    ]
    test = [
        *_observations(favorable, [1, 1], game_prefix="f"),
        *_observations(unfavorable, [0, 0], game_prefix="u"),
    ]
    model = RunValueModel.fit(train, alpha=0.1)

    candidate = model.metrics(test)
    baseline = model.metrics(test, parent_only=True)

    assert candidate.nll < baseline.nll
    assert candidate.mae < baseline.mae


def test_metric_bootstrap_resamples_whole_games_and_is_reproducible() -> None:
    favorable = RunStateKey("1", "___", 0, 1, 0)
    unfavorable = RunStateKey("1", "___", 0, 0, 1)
    train = [
        *_observations(favorable, [1, 1, 2, 2]),
        *_observations(unfavorable, [0, 0, 0, 0]),
    ]
    test = [
        RunObservation(favorable, 1, "game-a"),
        RunObservation(favorable, 2, "game-a"),
        RunObservation(unfavorable, 0, "game-b"),
        RunObservation(unfavorable, 0, "game-b"),
    ]
    model = RunValueModel.fit(train, alpha=0.1)

    first = bootstrap_metric_deltas(model, test, iterations=200, seed=42)
    second = bootstrap_metric_deltas(model, test, iterations=200, seed=42)

    assert first == second
    assert first.games == 2
    assert first.iterations == 200
    assert first.nll_delta.high < 0
    assert first.mae_delta.high < 0


def test_tune_alpha_uses_validation_nll() -> None:
    key = RunStateKey("1", "___", 0, 0, 0)
    other = RunStateKey("1", "___", 0, 3, 2)
    train = [*_observations(key, [0] * 20), *_observations(other, [2] * 20)]
    validation = _observations(key, [0] * 5, game_prefix="v")

    result = tune_alpha(train, validation, candidates=(0.1, 10.0, 100.0))

    assert result.alpha == 0.1
    assert set(result.metrics_by_alpha) == {0.1, 10.0, 100.0}


def test_run_call_values_use_count_state_and_remain_monotone() -> None:
    after_ball = RunStateKey("1", "___", 0, 1, 0)
    after_strike = RunStateKey("1", "___", 0, 0, 1)
    model = RunValueModel.fit(
        [
            *_observations(after_ball, [1] * 20),
            *_observations(after_strike, [0] * 20),
        ],
        alpha=0.1,
    )

    values = model.call_values(_state())

    assert values.ball > values.strike
    assert not values.backed_off


def test_run_call_values_back_off_instead_of_emitting_reverse_value() -> None:
    after_ball = RunStateKey("1", "___", 0, 1, 0)
    after_strike = RunStateKey("1", "___", 0, 0, 1)
    model = RunValueModel.fit(
        [
            *_observations(after_ball, [0] * 20),
            *_observations(after_strike, [1] * 20),
        ],
        alpha=0.1,
    )

    values = model.call_values(_state())

    assert values.ball == pytest.approx(values.strike)
    assert values.backed_off
