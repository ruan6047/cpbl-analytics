"""ML-OUTCOME-SIMPLE-LEAK2 留痕：校準斜率閘門重校的全部依據，**不寫入** DB／artifact。

產出四段證據（對應研究報告 docs/research/ML-OUTCOME-SIMPLE-LEAK2_RESULTS.md）：

1. `null`         — 誠實模型的斜率零假設分布、觀測值的雙尾 p、舊固定門檻的偽失敗率。
2. `leaked`       — 洩漏模型的同一組數字（由既存 model_versions 的 reliability decile
                    近似還原 p̂）。用途是顯示 `[0.8, 1.2]` 與洩漏模型的 H0 區間高度吻合、
                    且同一個固定區間換成誠實模型就失效；**不主張**舊門檻在歷史上是照著
                    這個模型訂出來的（無紀錄可查證）。
3. `temperature`  — 時間外溫度縮放（選項 b）的實際收益。
4. `cohort_2018`  — 限制訓練池為 2018+（starter 欄語意同質）的對照。

    docker run --rm --add-host=host.docker.internal:host-gateway \
      -e DATABASE_URL=... -v "$PWD":/w cpbl-leak2 \
      python /w/scripts/outcome_simple_calibration_audit.py [out.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import brier_score_loss, log_loss

from cpbl.models.outcome_simple import (
    LEGACY_CALIBRATION_BAND,
    _calibration_mle,
    _calibration_slope_null,
    _fit,
    _logit,
    _metrics,
    _select_signals,
    load_outcome_rows,
)

TRAINED_THROUGH = 2025

# 洩漏訓練版 fixed_semantic 的十分位 reliability（predicted 均值, n），逐位取自重訓前的
# model_versions(task='outcome_simple') = outcome-simple-1784128417（2026-07-15 訓練，
# 斜率 1.054727570523953、ECE 0.028952222789126184）。該列已被本卡重訓覆寫（trainer 是
# DELETE + INSERT），故在此固化，讓「舊門檻是對著洩漏模型校準的」這項證據可永久重現。
LEAKED_RELIABILITY = [
    (0.04967282547474827, 7), (0.17656608372610683, 8), (0.26238853245047666, 46),
    (0.3558027311430363, 203), (0.454797395598275, 442), (0.5465777637708273, 528),
    (0.6413612239654997, 260), (0.7325034706202829, 68), (0.8453040046768389, 14),
    (0.9414255394359322, 9),
]
LEAKED_SLOPE = 1.054727570523953


def _walk_forward_predictions(rows, test_years, train_from=None):
    """走查各測試季的 OOS 預測（與 walk_forward_backtest 同一條選訊號＋擬合路徑）。"""
    actual, predicted, blocks, years = [], [], [], []
    for season in test_years:
        train = [r for r in rows if r.season < season
                 and (train_from is None or r.season >= train_from)]
        test = [r for r in rows if r.season == season]
        if not train or not test:
            continue
        selection = _select_signals(train)
        predicted.extend(_fit(train, tuple(selection.values())).predict(test).tolist())
        actual.extend(r.home_win for r in test)
        blocks.extend((r.season, r.game_date.isocalendar().week) for r in test)
        years.extend([season] * len(test))
    return (np.array(actual), np.array(predicted), blocks, np.array(years))


def _block_bootstrap_slope(actual, predicted, blocks, iterations=2000, seed=42):
    """觀測斜率的非參數區間（重抽行事曆週），與零假設模擬互為佐證。"""
    grouped: dict = {}
    for index, block in enumerate(blocks):
        grouped.setdefault(block, []).append(index)
    block_indices = list(grouped.values())
    rng = np.random.default_rng(seed)
    slopes = []
    for _ in range(iterations):
        sample = np.array([i for s in rng.integers(0, len(block_indices), len(block_indices))
                           for i in block_indices[s]])
        y = actual[sample]
        if y.min() == y.max():
            continue
        slopes.append(float(_calibration_mle(_logit(predicted[sample]), y)[0]))
    return np.quantile(slopes, [0.025, 0.975]).tolist()


def _leaked_reference():
    """洩漏模型的 reliability decile → 近似 p̂ → 同一組零假設數字。

    以分箱均值當點質量會低估箱內離散度，使零分布偏寬、偽失敗率偏高；故「洩漏模型下舊門檻
    偽失敗率很低」這個結論是保守下界。
    """
    probability = np.array([p for p, n in LEAKED_RELIABILITY for _ in range(n)])
    return {"stored_slope": LEAKED_SLOPE,
            **_calibration_slope_null(probability, LEAKED_SLOPE)}


def _temperature_scaling(actual, predicted, years, test_years):
    """選項 (b)：溫度只以「該季之前的測試季 OOS 預測」擬合，嚴格時間外。"""
    scaled, used = [], []
    for index, season in enumerate(test_years):
        mask = years == season
        if index == 0:
            scaled.extend(predicted[mask].tolist())
            used.append({"year": season, "temperature": None})
            continue
        prior = years < season
        temperature = float(_calibration_mle(_logit(predicted[prior]), actual[prior])[0])
        scaled.extend((1 / (1 + np.exp(-temperature * _logit(predicted[mask])))).tolist())
        used.append({"year": season, "temperature": temperature})
    scaled = np.array(scaled)
    evaluated = years > test_years[0]
    return {
        "per_year_temperature": used,
        "evaluated_on_years": test_years[1:],
        "brier_raw": float(brier_score_loss(actual[evaluated], predicted[evaluated])),
        "brier_scaled": float(brier_score_loss(actual[evaluated], scaled[evaluated])),
        "log_loss_raw": float(log_loss(actual[evaluated], predicted[evaluated], labels=[0, 1])),
        "log_loss_scaled": float(log_loss(actual[evaluated], scaled[evaluated], labels=[0, 1])),
        "accuracy_raw": float(np.mean((predicted >= 0.5) == actual)),
        "accuracy_scaled": float(np.mean((scaled >= 0.5) == actual)),
        "slope_scaled": float(_calibration_mle(_logit(scaled), actual)[0]),
    }


def _summary(actual, predicted, label, train_from=None):
    metrics = _metrics(actual, predicted)
    metrics.pop("reliability", None)
    null = _calibration_slope_null(predicted, metrics["calibration_slope"])
    return {"label": label, "train_from": train_from, "n_test": int(actual.size),
            **metrics, **{k: v for k, v in null.items() if k != "method"}}


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outcome_simple_calibration_audit.json")
    rows = [r for r in load_outcome_rows() if r.season <= TRAINED_THROUGH]
    test_years = sorted({r.season for r in rows})[-5:]
    actual, predicted, blocks, years = _walk_forward_predictions(rows, test_years)

    cohort_actual, cohort_predicted, _, _ = _walk_forward_predictions(rows, test_years, 2018)

    payload = {
        "test_years": test_years,
        "legacy_band": list(LEGACY_CALIBRATION_BAND),
        "honest": _summary(actual, predicted, "全史訓練池（現行）"),
        "block_bootstrap_slope_ci95": _block_bootstrap_slope(actual, predicted, blocks),
        "leaked": _leaked_reference(),
        "temperature": _temperature_scaling(actual, predicted, years, test_years),
        "cohort_2018": _summary(cohort_actual, cohort_predicted, "僅 2018+ 訓練池", 2018),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
