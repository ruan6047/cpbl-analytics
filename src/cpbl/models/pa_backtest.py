"""單一打席互斥結果機率的時間走查與校準指標。"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import replace

from cpbl.models.pa_sim import (
    OUTCOMES,
    PASnapshot,
    _posterior,
    fit_empirical_bayes,
    predict_outcomes,
)

DEFAULT_STRENGTH_GRID = [
    (hitter, pitcher, direct)
    for hitter in (100.0, 200.0, 400.0)
    for pitcher in (100.0, 200.0, 400.0)
    for direct in (50.0, 100.0, 200.0)
]


def multiclass_metrics(actual: list[str], probabilities: list[dict[str, float]]) -> dict:
    if not actual or len(actual) != len(probabilities):
        raise ValueError("actual 與 probabilities 必須等長且非空")
    log_loss = 0.0
    brier = 0.0
    confidence_bins = [[0.0, 0.0, 0] for _ in range(10)]
    for observed, predicted in zip(actual, probabilities, strict=True):
        log_loss -= math.log(max(predicted[observed], 1e-15))
        brier += sum(
            (predicted[outcome] - (1.0 if outcome == observed else 0.0)) ** 2
            for outcome in OUTCOMES
        )
        guessed = max(OUTCOMES, key=predicted.__getitem__)
        confidence = predicted[guessed]
        bucket = confidence_bins[min(int(confidence * 10), 9)]
        bucket[0] += confidence
        bucket[1] += float(guessed == observed)
        bucket[2] += 1
    n = len(actual)
    reliability = [
        {"confidence": total_confidence / count, "accuracy": correct / count, "n": count}
        for total_confidence, correct, count in confidence_bins if count
    ]
    ece = sum(abs(row["confidence"] - row["accuracy"]) * row["n"] / n for row in reliability)
    return {
        "log_loss": log_loss / n,
        "brier": brier / n,
        "ece": ece,
        "reliability": reliability,
    }


def _component_probabilities(model, snapshot: PASnapshot, component: str) -> dict[str, float]:
    if component == "league":
        return model.league
    if component == "hitter_only":
        return _posterior(
            model.hitters.get(snapshot.hitter), model.league, model.hitter_strength,
        )
    if component == "pitcher_only":
        return _posterior(
            model.pitchers.get(snapshot.pitcher), model.league, model.pitcher_strength,
        )
    return predict_outcomes(model, snapshot.hitter, snapshot.pitcher)


def select_prior_strengths(
    rows: list[PASnapshot], strength_grid: list[tuple[float, float, float]],
) -> tuple[float, float, float]:
    seasons = sorted({row.year for row in rows})
    if len(seasons) < 2:
        return strength_grid[0]
    validation_year = seasons[-1]
    train = [row for row in rows if row.year < validation_year]
    validation = [row for row in rows if row.year == validation_year]
    base_model = fit_empirical_bayes(train, *strength_grid[0])
    best = None
    for strengths in strength_grid:
        model = replace(
            base_model,
            hitter_strength=strengths[0],
            pitcher_strength=strengths[1],
            direct_strength=strengths[2],
        )
        predicted = [predict_outcomes(model, row.hitter, row.pitcher) for row in validation]
        score = multiclass_metrics([row.result for row in validation], predicted)["log_loss"]
        if best is None or score < best[0]:
            best = (score, strengths)
    return best[1]


def walk_forward_backtest(
    snapshots: Iterable[PASnapshot],
    test_years: list[int] | None = None,
    strength_grid: list[tuple[float, float, float]] | None = None,
) -> dict:
    rows = list(snapshots)
    seasons = sorted({row.year for row in rows})
    if len(seasons) < 2:
        raise ValueError("時間走查至少需要兩季資料")
    test_years = test_years or seasons[-5:]
    strength_grid = strength_grid or DEFAULT_STRENGTH_GRID
    names = ("league", "hitter_only", "pitcher_only", "combined")
    pooled_actual: list[str] = []
    pooled_predictions = {name: [] for name in names}
    folds = []
    for year in test_years:
        train = [row for row in rows if row.year < year]
        test = [row for row in rows if row.year == year]
        if not train or not test:
            continue
        strengths = select_prior_strengths(train, strength_grid)
        model = fit_empirical_bayes(train, *strengths)
        actual = [row.result for row in test]
        pooled_actual.extend(actual)
        fold_metrics = {}
        for name in names:
            predicted = [_component_probabilities(model, row, name) for row in test]
            pooled_predictions[name].extend(predicted)
            fold_metrics[name] = multiclass_metrics(actual, predicted)
        folds.append({"year": year, "n_train": len(train), "n_test": len(test),
                      "strengths": strengths, "models": fold_metrics})
    if not pooled_actual:
        raise ValueError("指定 test_years 無可走查資料")
    return {
        "test_years": [fold["year"] for fold in folds],
        "n_test": len(pooled_actual),
        "models": [
            {"name": name, **multiclass_metrics(pooled_actual, pooled_predictions[name])}
            for name in names
        ],
        "folds": folds,
    }
