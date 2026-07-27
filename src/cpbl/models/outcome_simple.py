"""固定語意群的賽前勝率模型與 nested walk-forward。"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

from cpbl.db import conn
from cpbl.features.outcome import FEATURE_KEYS

GROUP_CANDIDATES = {
    "strength": ("prior_winpct_diff", "winrate_diff"),
    "offense": ("runs_scored_diff", "prior_team_ops_diff", "team_ops_now_diff"),
    "suppression": ("runs_allowed_diff", "starter_era_diff"),
    "schedule": ("rest_days_diff",),
}
ORIENT = {"runs_allowed_diff": -1.0, "starter_era_diff": -1.0}
FULL_SIGNALS = tuple(signal for signal in FEATURE_KEYS if signal != "home_field")

# 校準斜率零假設模擬（ML-OUTCOME-SIMPLE-LEAK2）。
CALIBRATION_NULL_ITERATIONS = 2000
CALIBRATION_NULL_SEED = 17
# 舊的固定門檻。已退場為「診斷指標」而非閘門判準，保留是為了在 metrics 裡並排揭露
# 它在當前模型辨別力下的偽失敗率（見 _calibration_slope_null 的 docstring）。
LEGACY_CALIBRATION_BAND = (0.8, 1.2)


@dataclass(frozen=True)
class OutcomeRow:
    season: int
    game_date: date
    home_win: int
    features: dict[str, float | None]
    game_sno: int = 0
    home: str = ""
    away: str = ""


@dataclass
class FittedOutcomeModel:
    signals: tuple[str, ...]
    medians: np.ndarray
    scaler: StandardScaler
    classifier: LogisticRegression

    def predict(self, rows: list[OutcomeRow]) -> np.ndarray:
        matrix = _matrix(rows, self.signals)
        matrix = np.where(np.isnan(matrix), self.medians, matrix)
        return self.classifier.predict_proba(self.scaler.transform(matrix))[:, 1]


def candidate_signal_sets() -> list[dict[str, str]]:
    groups = tuple(GROUP_CANDIDATES)
    return [
        dict(zip(groups, signals, strict=True))
        for signals in itertools.product(*(GROUP_CANDIDATES[group] for group in groups))
    ]


def load_outcome_rows(completed_only: bool = True) -> list[OutcomeRow]:
    columns = ", ".join(FULL_SIGNALS)
    where = "completed=true AND home_win IN (0,1)" if completed_only else "completed=false"
    with conn() as connection:
        cur = connection.cursor()
        cur.execute(
            f"SELECT season, game_date, game_sno, home_team_name, away_team_name, "
            f"home_win, {columns} FROM cpbl.game_features "
            f"WHERE {where} ORDER BY game_date, game_sno"
        )
        return [
            OutcomeRow(
                season=int(row[0]),
                game_date=row[1],
                home_win=int(row[5]) if row[5] is not None else 0,
                features=dict(zip(FULL_SIGNALS, row[6:], strict=True)),
                game_sno=int(row[2]),
                home=row[3],
                away=row[4],
            )
            for row in cur.fetchall()
        ]


def _matrix(rows: list[OutcomeRow], signals: tuple[str, ...]) -> np.ndarray:
    return np.array([
        [
            np.nan if row.features.get(signal) is None
            else float(row.features[signal]) * ORIENT.get(signal, 1.0)
            for signal in signals
        ]
        for row in rows
    ], dtype=float)


def _fit(rows: list[OutcomeRow], signals: tuple[str, ...]) -> FittedOutcomeModel:
    matrix = _matrix(rows, signals)
    medians = np.array([
        0.0 if np.isnan(column).all() else float(np.nanmedian(column))
        for column in matrix.T
    ])
    matrix = np.where(np.isnan(matrix), medians, matrix)
    scaler = StandardScaler().fit(matrix)
    classifier = LogisticRegression(max_iter=1000).fit(
        scaler.transform(matrix), np.array([row.home_win for row in rows]),
    )
    return FittedOutcomeModel(signals, medians, scaler, classifier)


def _lightgbm_probability(train: list[OutcomeRow], test: list[OutcomeRow]) -> np.ndarray:
    from lightgbm import LGBMClassifier

    from cpbl.models.outcome_gbm import _GBM_PARAMS

    train_matrix = _matrix(train, FULL_SIGNALS)
    test_matrix = _matrix(test, FULL_SIGNALS)
    medians = np.array([
        0.0 if np.isnan(column).all() else float(np.nanmedian(column))
        for column in train_matrix.T
    ])
    train_matrix = np.where(np.isnan(train_matrix), medians, train_matrix)
    test_matrix = np.where(np.isnan(test_matrix), medians, test_matrix)
    model = LGBMClassifier(**_GBM_PARAMS).fit(
        train_matrix, np.array([row.home_win for row in train]),
    )
    return model.predict_proba(test_matrix)[:, 1]


def _metrics(actual: np.ndarray, probability: np.ndarray) -> dict:
    probability = np.clip(probability, 1e-6, 1 - 1e-6)
    bins = [[0.0, 0.0, 0] for _ in range(10)]
    for observed, predicted in zip(actual, probability, strict=True):
        bucket = bins[min(int(predicted * 10), 9)]
        bucket[0] += float(predicted)
        bucket[1] += int(observed)
        bucket[2] += 1
    reliability = [
        {"predicted": predicted / n, "observed": observed / n, "n": n}
        for predicted, observed, n in bins if n
    ]
    ece = sum(abs(row["predicted"] - row["observed"]) * row["n"] / len(actual)
              for row in reliability)
    logit = np.log(probability / (1 - probability)).reshape(-1, 1)
    calibration = LogisticRegression(C=np.inf, max_iter=1000).fit(logit, actual)
    return {
        "accuracy": float(accuracy_score(actual, probability >= 0.5)),
        "brier": float(brier_score_loss(actual, probability)),
        "log_loss": float(log_loss(actual, probability, labels=[0, 1])),
        "calibration_intercept": float(calibration.intercept_[0]),
        "calibration_slope": float(calibration.coef_[0][0]),
        "ece": ece,
        "reliability": reliability,
    }


def _logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(probability, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def _calibration_mle(x: np.ndarray, y: np.ndarray, steps: int = 40) -> np.ndarray:
    """再校準回歸 `y ~ sigmoid(a + b·x)` 的斜率 b，對每一列 y 各解一次。

    與 `_metrics` 用的 `LogisticRegression(C=np.inf)` 是同一個無懲罰 MLE，改用向量化
    Newton–Raphson 只是為了讓 2,000 次零假設模擬能一次算完（同一組 x、只換 y）。
    `tests/test_outcome_simple.py` 釘住兩者的數值一致性。
    """
    y = np.atleast_2d(y).astype(float)
    coefficients = np.zeros((y.shape[0], 2))
    for _ in range(steps):
        eta = np.clip(coefficients[:, :1] + coefficients[:, 1:] * x, -30.0, 30.0)
        probability = 1.0 / (1.0 + np.exp(-eta))
        weight = probability * (1.0 - probability)
        residual = y - probability
        gradient = np.stack([residual.sum(1), (residual * x).sum(1)], axis=1)
        h00, h01 = weight.sum(1), (weight * x).sum(1)
        h11 = (weight * x * x).sum(1)
        determinant = h00 * h11 - h01**2
        safe = np.where(np.abs(determinant) < 1e-12, np.nan, determinant)
        step = np.stack([
            (h11 * gradient[:, 0] - h01 * gradient[:, 1]) / safe,
            (-h01 * gradient[:, 0] + h00 * gradient[:, 1]) / safe,
        ], axis=1)
        step = np.nan_to_num(step, nan=0.0)
        coefficients = coefficients + step
        if np.nanmax(np.abs(step)) < 1e-10:
            break
    return coefficients[:, 1]


def _calibration_slope_null(
    probability: np.ndarray,
    observed_slope: float,
    iterations: int = CALIBRATION_NULL_ITERATIONS,
) -> dict:
    """校準斜率在「模型完美校準」零假設下的抽樣分布。

    為什麼需要它：斜率是以 `logit(p̂)` 為唯一解釋變數的再校準回歸係數，其抽樣變異約與
    `Var(logit p̂)` 成反比。辨別力愈弱、預測愈往基準率壓縮，同一個「完美校準」的模型
    量到的斜率就愈飄。**固定寬度的門檻因此不是校準檢定，而是變相的辨別力檢定**——
    模型愈誠實（訊號愈弱）愈容易被判失敗，這正是 ML-OUTCOME-LEAK1 去洩漏後發生的事。

    模擬方式：固定 p̂，重抽 `y ~ Bernoulli(p̂)`（即假設 p̂ 完全正確），重解斜率。

    **條件零假設**：「給定 p̂，各場賽果彼此獨立」。5% 的型一誤差只在這個條件下成立。
    若同週賽果存在殘餘相關，真實零分布會比模擬的更寬，用較窄的 IID 區間**會提高**實際
    偽拒絕率（高於名目 5%）——就檢定本身而言是偏嚴、就「不讓失準模型上線」而言是偏安全，
    但不能宣稱它是普遍意義下的固定 5% 檢定。
    """
    x = _logit(probability)
    rng = np.random.default_rng(CALIBRATION_NULL_SEED)
    draws = (rng.random((iterations, len(x))) < np.clip(probability, 1e-6, 1 - 1e-6))
    slopes = _calibration_mle(x, draws.astype(float))
    slopes = slopes[np.isfinite(slopes)]
    low, high = np.quantile(slopes, [0.025, 0.975]).tolist()
    band_low, band_high = LEGACY_CALIBRATION_BAND
    return {
        "method": "parametric bootstrap under H0: predicted probabilities are calibrated",
        "iterations": int(slopes.size),
        "predicted_logit_sd": float(np.std(x)),
        "slope_ci95": [float(low), float(high)],
        "p_two_sided": float(np.mean(np.abs(slopes - 1.0) >= abs(observed_slope - 1.0))),
        "legacy_band": list(LEGACY_CALIBRATION_BAND),
        "legacy_band_false_failure_rate": float(
            np.mean((slopes < band_low) | (slopes > band_high))
        ),
    }


def _select_signals(rows: list[OutcomeRow]) -> dict[str, str]:
    seasons = sorted({row.season for row in rows})
    if len(seasons) < 2:
        return candidate_signal_sets()[0]
    validation_year = seasons[-1]
    train = [row for row in rows if row.season < validation_year]
    validation = [row for row in rows if row.season == validation_year]
    actual = np.array([row.home_win for row in validation])
    best = None
    for candidate in candidate_signal_sets():
        signals = tuple(candidate.values())
        probability = _fit(train, signals).predict(validation)
        score = brier_score_loss(actual, probability)
        if best is None or score < best[0]:
            best = (score, candidate)
    return best[1]


def walk_forward_backtest(
    rows: list[OutcomeRow], test_years: list[int] | None = None,
    include_lightgbm: bool = False,
) -> dict:
    seasons = sorted({row.season for row in rows})
    test_years = test_years or seasons[-5:]
    names = (
        ("home_baseline", "full_logistic", "lightgbm", "fixed_semantic")
        if include_lightgbm else ("home_baseline", "full_logistic", "fixed_semantic")
    )
    pooled_actual: list[int] = []
    pooled = {name: [] for name in names}
    pooled_blocks: list[tuple[int, int]] = []
    folds = []
    fixed_wins = 0
    for season in test_years:
        train = [row for row in rows if row.season < season]
        test = [row for row in rows if row.season == season]
        if not train or not test:
            continue
        selection = _select_signals(train)
        actual = np.array([row.home_win for row in test])
        baseline = np.full(len(test), np.mean([row.home_win for row in train]))
        full = _fit(train, FULL_SIGNALS).predict(test)
        fixed = _fit(train, tuple(selection.values())).predict(test)
        fold_probabilities = {
            "home_baseline": baseline, "full_logistic": full, "fixed_semantic": fixed,
        }
        if include_lightgbm:
            fold_probabilities["lightgbm"] = _lightgbm_probability(train, test)
        fold_metrics = {name: _metrics(actual, probability)
                        for name, probability in fold_probabilities.items()}
        fixed_wins += fold_metrics["fixed_semantic"]["brier"] < fold_metrics["home_baseline"]["brier"]
        pooled_actual.extend(actual.tolist())
        pooled_blocks.extend((row.season, row.game_date.isocalendar().week) for row in test)
        for name, probability in fold_probabilities.items():
            pooled[name].extend(probability.tolist())
        folds.append({"year": season, "n_train": len(train), "n_test": len(test),
                      "signals": selection, "models": fold_metrics})
    if not pooled_actual:
        raise ValueError("指定 test_years 無可走查資料")
    actual = np.array(pooled_actual)
    models = [{"name": name, **_metrics(actual, np.array(pooled[name]))} for name in names]
    baseline = models[0]
    fixed = next(model for model in models if model["name"] == "fixed_semantic")
    paired_bootstrap = _paired_block_bootstrap(
        actual, np.array(pooled["home_baseline"]), np.array(pooled["fixed_semantic"]),
        pooled_blocks,
    )
    return {
        "test_years": [fold["year"] for fold in folds],
        "n_test": len(actual),
        "models": models,
        "folds": folds,
        "paired_bootstrap": paired_bootstrap,
        "calibration_null": _calibration_slope_null(
            np.array(pooled["fixed_semantic"]), fixed["calibration_slope"],
        ),
        "seasons_beating_baseline": int(fixed_wins),
        "beats_baseline": (
            fixed["brier"] < baseline["brier"]
            and fixed["log_loss"] < baseline["log_loss"]
            and fixed_wins >= math.ceil(len(folds) / 2)
        ),
    }


def _paired_block_bootstrap(
    actual: np.ndarray,
    baseline: np.ndarray,
    fixed: np.ndarray,
    blocks: list[tuple[int, int]],
    iterations: int = 2000,
) -> dict:
    grouped: dict[tuple[int, int], list[int]] = {}
    for index, block in enumerate(blocks):
        grouped.setdefault(block, []).append(index)
    block_indices = list(grouped.values())
    rng = np.random.default_rng(42)
    brier_delta = []
    log_loss_delta = []
    for _ in range(iterations):
        sample = np.array([index for selected in rng.integers(0, len(block_indices),
                                                              len(block_indices))
                           for index in block_indices[selected]])
        y = actual[sample]
        base = np.clip(baseline[sample], 1e-6, 1 - 1e-6)
        model = np.clip(fixed[sample], 1e-6, 1 - 1e-6)
        brier_delta.append(float(np.mean((model - y) ** 2 - (base - y) ** 2)))
        base_ll = -(y * np.log(base) + (1 - y) * np.log(1 - base))
        model_ll = -(y * np.log(model) + (1 - y) * np.log(1 - model))
        log_loss_delta.append(float(np.mean(model_ll - base_ll)))
    return {
        "method": "paired calendar-week block bootstrap",
        "iterations": iterations,
        "brier_delta_ci95": np.quantile(brier_delta, [0.025, 0.975]).tolist(),
        "log_loss_delta_ci95": np.quantile(log_loss_delta, [0.025, 0.975]).tolist(),
    }


def train_final_model(
    rows: list[OutcomeRow], trained_through: int, bootstrap_models: int = 50,
) -> dict:
    training = [row for row in rows if row.season <= trained_through]
    if not training:
        raise ValueError("無可訓練資料")
    selection = _select_signals(training)
    signals = tuple(selection.values())
    rng = np.random.default_rng(42)
    blocks: dict[tuple[int, int], list[OutcomeRow]] = {}
    for row in training:
        blocks.setdefault((row.season, row.game_date.isocalendar().week), []).append(row)
    block_rows = list(blocks.values())
    ensemble = []
    for _ in range(bootstrap_models):
        sample = [row for index in rng.integers(0, len(block_rows), len(block_rows))
                  for row in block_rows[index]]
        ensemble.append(_fit(sample, signals))
    return {
        "version": 1,
        "trained_through": trained_through,
        "signals": selection,
        "model": _fit(training, signals),
        "ensemble": ensemble,
        "interval": "calendar-week block bootstrap 5th-95th percentile",
    }


def save_artifact(artifact: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_artifact(path: Path) -> dict:
    return joblib.load(path)


def deployment_gate(result: dict, required_season_wins: int = 3) -> dict:
    """七項部署閘門。`calibration_slope` 以零假設抽樣分布定界（見下）。

    ML-OUTCOME-SIMPLE-LEAK2：舊版用固定區間 `[0.8, 1.2]`。該區間與**洩漏模型**的零假設
    95% 區間 `[0.787, 1.229]` 高度吻合（洩漏模型 logit 離散度 sd 0.56）；歷史上是不是
    照著它訂的無從查證，但可驗證的是：去洩漏後離散度掉到 0.21，同一個固定區間會誤判
    42% 的**完美校準**模型為失敗。

    改以每次回測當場算出的零假設 95% 區間為界。條件零假設下型一誤差為 5%（見
    `_calibration_slope_null`），且區間寬度隨辨別力自動調整——模型愈強區間愈窄。
    在洩漏模型那個辨別力水準上，新界線 `[0.787, 1.229]` 比舊門檻**略寬**（兩端各鬆
    約 0.02）而非更嚴；實質放寬只發生在誠實模型那一端，且放寬幅度就是抽樣雜訊本身。
    `calibration_intercept` 的絕對門檻不動——截距衡量的是機率水準本身，沒有同樣的
    辨別力相依問題。
    """
    baseline = next(model for model in result["models"] if model["name"] == "home_baseline")
    fixed = next(model for model in result["models"] if model["name"] == "fixed_semantic")
    slope_low, slope_high = result["calibration_null"]["slope_ci95"]
    checks = {
        "brier": fixed["brier"] < baseline["brier"],
        "log_loss": fixed["log_loss"] < baseline["log_loss"],
        "season_stability": result["seasons_beating_baseline"] >= required_season_wins,
        "calibration_intercept": abs(fixed["calibration_intercept"]) <= 0.1,
        "calibration_slope": slope_low <= fixed["calibration_slope"] <= slope_high,
        "brier_ci": result["paired_bootstrap"]["brier_delta_ci95"][1] <= 0,
        "log_loss_ci": result["paired_bootstrap"]["log_loss_delta_ci95"][1] <= 0,
    }
    return {"deployable": all(checks.values()), "checks": checks}
