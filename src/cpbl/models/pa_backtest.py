"""單一打席互斥結果機率的時間走查與校準指標。"""

from __future__ import annotations

import gc
import math
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import replace

from cpbl.models.pa_sim import (
    OUTCOMES,
    GameState,
    PASnapshot,
    Transition,
    _posterior,
    fit_empirical_bayes,
    fit_transition_kernel,
    predict_outcomes,
    simulate_plate_appearance,
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


def build_run_dist_from_snapshots(
    snapshots: Iterable[PASnapshot],
) -> dict[tuple[str, str, int], list[float]]:
    """只用訓練 fold 重建半局剩餘得分分布，供 WP 驗證避免跨季洩漏。"""
    from cpbl.models.winprob import K_CAP

    groups: dict[tuple[int, int, int, str], list[PASnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        groups[(snapshot.year, snapshot.game_sno, snapshot.before.inning,
                snapshot.before.half)].append(snapshot)
    last_half = {
        game: max((inning, half) for year, sno, inning, half in groups
                  if (year, sno) == game)
        for game in {(year, sno) for year, sno, _, _ in groups}
    }
    counts: dict[tuple[str, str, int], list[int]] = defaultdict(lambda: [0] * (K_CAP + 1))
    for (year, sno, inning, half), group in groups.items():
        if (inning, half) == last_half[(year, sno)]:
            continue  # 再見／免打下半局會截短得分，與正式 winprob.py 同樣排除末半局
        end_score = max(
            snapshot.after.away_score if half == "1" else snapshot.after.home_score
            for snapshot in group
        )
        for snapshot in group:
            start_score = (snapshot.before.away_score if half == "1"
                           else snapshot.before.home_score)
            remaining = max(0, min(K_CAP, end_score - start_score))
            counts[(half, snapshot.before.bases, snapshot.before.outs)][remaining] += 1
    return {
        key: [count / sum(values) for count in values]
        for key, values in counts.items() if sum(values)
    }


def _wp_from_training(snapshots: list[PASnapshot]) -> Callable[[GameState], float]:
    from cpbl.models.winprob import _we_solver, wp_state

    distribution = build_run_dist_from_snapshots(snapshots)
    for half in ("1", "2"):
        if (half, "___", 0) not in distribution:
            raise ValueError(f"訓練 fold 缺少 {half}/___/0 run distribution")
    we_top, we_bot = _we_solver(distribution[("1", "___", 0)],
                                distribution[("2", "___", 0)])

    def calculate(state: GameState) -> float:
        return wp_state(distribution, we_top, we_bot, state.inning, state.half,
                        state.home_score - state.away_score, state.bases, state.outs)

    return calculate


def transition_walk_forward(
    snapshots: Iterable[PASnapshot], test_years: list[int],
    strengths_by_year: dict[int, tuple[float, float, float]] | None = None,
) -> dict:
    """留出季驗證轉移分布與加權 WP；所有 run_dist／kernel 只由較早季建立。"""
    rows = list(snapshots)
    folds = []
    total = transition_total = 0
    next_wp_error = model_brier = current_brier = transition_nll = 0.0
    for year in test_years:
        train = [row for row in rows if row.year < year]
        test = [row for row in rows if row.year == year]
        if not train or not test:
            continue
        strengths = ((strengths_by_year or {}).get(year)
                     or select_prior_strengths(train, DEFAULT_STRENGTH_GRID))
        model = fit_empirical_bayes(train, *strengths)
        kernel = fit_transition_kernel(train)
        wp = _wp_from_training(train)
        fold_n = 0
        for snapshot in test:
            try:
                simulated = simulate_plate_appearance(
                    model, kernel, snapshot.hitter, snapshot.pitcher, snapshot.before, wp,
                )
            except RuntimeError:
                continue
            predicted_wp = simulated["weighted_win_probability"]
            actual_next_wp = snapshot.game_outcome if snapshot.game_ended else wp(snapshot.after)
            next_wp_error += abs(predicted_wp - actual_next_wp)
            model_brier += (predicted_wp - snapshot.game_outcome) ** 2
            current_brier += (simulated["current_win_probability"] - snapshot.game_outcome) ** 2
            if not snapshot.game_ended:
                actual_transition = Transition(snapshot.runs_delta, snapshot.after.bases,
                                               snapshot.after.outs, snapshot.inning_ended)
                distribution, _, _ = kernel.distribution(
                    snapshot.result, snapshot.before.bases, snapshot.before.outs,
                )
                probability = next((p for transition, p in distribution
                                    if transition == actual_transition), 0.0)
                transition_nll -= math.log(max(probability, 1e-15))
                transition_total += 1
            total += 1
            fold_n += 1
        folds.append({"year": year, "n_test": fold_n, "strengths": strengths})
        del model, kernel, wp, train, test
        gc.collect()
    if not total:
        raise ValueError("無可驗證打席")
    return {
        "test_years": [fold["year"] for fold in folds],
        "n_test": total,
        "next_wp_mae": next_wp_error / total,
        "weighted_wp_brier": model_brier / total,
        "current_wp_brier": current_brier / total,
        "transition_log_loss": transition_nll / transition_total if transition_total else None,
        "folds": folds,
    }
