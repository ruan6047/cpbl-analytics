from __future__ import annotations

from datetime import date

from cpbl.models.outcome_simple import (
    GROUP_CANDIDATES,
    OutcomeRow,
    candidate_signal_sets,
    deployment_gate,
    load_artifact,
    save_artifact,
    train_final_model,
    walk_forward_backtest,
)


def _row(season: int, value: float, home_win: int) -> OutcomeRow:
    features = {
        "prior_winpct_diff": value,
        "winrate_diff": value,
        "runs_scored_diff": value,
        "prior_team_ops_diff": value,
        "team_ops_now_diff": value,
        "runs_allowed_diff": -value,
        "starter_era_diff": -value,
        "rest_days_diff": 0.0,
    }
    return OutcomeRow(season, date(season, 5, 1), home_win, features)


def test_candidate_signal_sets_have_exactly_one_signal_per_semantic_group():
    candidates = candidate_signal_sets()

    assert candidates
    for signals in candidates:
        assert len(signals) == len(GROUP_CANDIDATES)
        assert len(set(signals)) == len(signals)
        assert all(signal in GROUP_CANDIDATES[group] for group, signal in signals.items())


def test_walk_forward_fixed_model_beats_home_baseline_on_predictive_signal():
    rows = []
    for season in (2021, 2022, 2023, 2024):
        rows.extend([
            _row(season, 2.0, 1), _row(season, 1.0, 1),
            _row(season, -2.0, 0), _row(season, -1.0, 0),
        ] * 8)

    result = walk_forward_backtest(rows, test_years=[2023, 2024])

    assert result["test_years"] == [2023, 2024]
    assert result["n_test"] == 64
    assert {model["name"] for model in result["models"]} == {
        "home_baseline", "full_logistic", "fixed_semantic",
    }
    fixed = next(model for model in result["models"] if model["name"] == "fixed_semantic")
    baseline = next(model for model in result["models"] if model["name"] == "home_baseline")
    assert fixed["brier"] < baseline["brier"]
    assert fixed["log_loss"] < baseline["log_loss"]


def test_final_artifact_round_trip_preserves_probability(tmp_path):
    rows = []
    for season in (2021, 2022, 2023):
        rows.extend([_row(season, 2.0, 1), _row(season, -2.0, 0)] * 8)
    artifact = train_final_model(rows, trained_through=2023, bootstrap_models=3)
    path = tmp_path / "outcome-simple.joblib"

    save_artifact(artifact, path)
    restored = load_artifact(path)

    assert restored["trained_through"] == 2023
    assert restored["signals"] == artifact["signals"]
    assert len(restored["ensemble"]) == 3
    assert restored["model"].predict([_row(2024, 1.0, 1)])[0] == artifact["model"].predict([
        _row(2024, 1.0, 1)
    ])[0]


def test_deployment_gate_requires_probability_metrics_season_stability_and_calibration():
    result = {
        "seasons_beating_baseline": 3,
        "paired_bootstrap": {"brier_delta_ci95": [-0.02, -0.001],
                             "log_loss_delta_ci95": [-0.04, -0.002]},
        "models": [
            {"name": "home_baseline", "brier": 0.25, "log_loss": 0.69},
            {"name": "fixed_semantic", "brier": 0.24, "log_loss": 0.67,
             "calibration_intercept": 0.05, "calibration_slope": 1.05},
        ],
    }

    assert deployment_gate(result, required_season_wins=3)["deployable"] is True
    result["models"][1]["calibration_slope"] = 1.3
    assert deployment_gate(result, required_season_wins=3)["deployable"] is False
