"""固定語意群的賽前勝率模型與 nested walk-forward。"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import date

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


@dataclass(frozen=True)
class OutcomeRow:
    season: int
    game_date: date
    home_win: int
    features: dict[str, float | None]


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
            f"SELECT season, game_date, home_win, {columns} FROM cpbl.game_features "
            f"WHERE {where} ORDER BY game_date, game_sno"
        )
        return [
            OutcomeRow(
                season=int(row[0]),
                game_date=row[1],
                home_win=int(row[2]) if row[2] is not None else 0,
                features=dict(zip(FULL_SIGNALS, row[3:], strict=True)),
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
) -> dict:
    seasons = sorted({row.season for row in rows})
    test_years = test_years or seasons[-5:]
    names = ("home_baseline", "full_logistic", "fixed_semantic")
    pooled_actual: list[int] = []
    pooled = {name: [] for name in names}
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
        fold_metrics = {name: _metrics(actual, probability)
                        for name, probability in fold_probabilities.items()}
        fixed_wins += fold_metrics["fixed_semantic"]["brier"] < fold_metrics["home_baseline"]["brier"]
        pooled_actual.extend(actual.tolist())
        for name, probability in fold_probabilities.items():
            pooled[name].extend(probability.tolist())
        folds.append({"year": season, "n_train": len(train), "n_test": len(test),
                      "signals": selection, "models": fold_metrics})
    if not pooled_actual:
        raise ValueError("指定 test_years 無可走查資料")
    actual = np.array(pooled_actual)
    models = [{"name": name, **_metrics(actual, np.array(pooled[name]))} for name in names]
    baseline = models[0]
    fixed = models[-1]
    return {
        "test_years": [fold["year"] for fold in folds],
        "n_test": len(actual),
        "models": models,
        "folds": folds,
        "seasons_beating_baseline": int(fixed_wins),
        "beats_baseline": (
            fixed["brier"] < baseline["brier"]
            and fixed["log_loss"] < baseline["log_loss"]
            and fixed_wins >= math.ceil(len(folds) / 2)
        ),
    }
