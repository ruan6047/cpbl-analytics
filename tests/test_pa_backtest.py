from __future__ import annotations

from cpbl.models.pa_backtest import multiclass_metrics, walk_forward_backtest
from cpbl.models.pa_sim import OUTCOMES, GameState, PASnapshot


def _row(year: int, result: str, hitter: str, pitcher: str) -> PASnapshot:
    state = GameState(1, "1", "___", 0, 0, 0)
    return PASnapshot(1, hitter, pitcher, result, state, state, 0, False, False, year=year)


def test_multiclass_metrics_rewards_probability_on_observed_outcome():
    actual = ["K", "HR"]
    good = [
        {outcome: (0.94 if outcome == "K" else 0.01) for outcome in OUTCOMES},
        {outcome: (0.94 if outcome == "HR" else 0.01) for outcome in OUTCOMES},
    ]
    bad = [{outcome: 1 / len(OUTCOMES) for outcome in OUTCOMES}] * 2

    assert multiclass_metrics(actual, good)["log_loss"] < multiclass_metrics(actual, bad)["log_loss"]
    assert multiclass_metrics(actual, good)["brier"] < multiclass_metrics(actual, bad)["brier"]


def test_walk_forward_backtest_compares_league_hitter_pitcher_and_combined():
    rows = []
    for year in (2022, 2023, 2024):
        rows.extend([
            _row(year, "K", "strikeout-hitter", "strikeout-pitcher"),
            _row(year, "K", "strikeout-hitter", "strikeout-pitcher"),
            _row(year, "HR", "slugger", "contact-pitcher"),
            _row(year, "HR", "slugger", "contact-pitcher"),
            _row(year, "BIP_OUT", "contact", "contact-pitcher"),
        ])

    result = walk_forward_backtest(
        rows, test_years=[2023, 2024], strength_grid=[(1.0, 1.0, 1.0)],
    )

    assert result["test_years"] == [2023, 2024]
    assert result["n_test"] == 10
    assert {model["name"] for model in result["models"]} == {
        "league", "hitter_only", "pitcher_only", "combined",
    }
    assert result["models"][-1]["log_loss"] < result["models"][0]["log_loss"]
