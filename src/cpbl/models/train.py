"""訓練與回測打擊成績預測：Marcel baseline vs LightGBM。

時間切分回測（walk-forward 的簡化版）：target_year < TEST_FROM 為訓練，
>= TEST_FROM 為測試，確保「用過去預測未來」、無資料洩漏。

產出：
- artifacts/lgbm_batting_{stat}.txt    最終模型（全資料訓練，供推論）
- cpbl.model_versions                  本次模型登錄 + 回測 metrics
- cpbl.projections                     回測預測（含 actual）＋ 下季投影（actual NULL）

    uv run cpbl-train
"""

from __future__ import annotations

import json
import logging
from datetime import date

import lightgbm as lgb
import numpy as np

from cpbl.config import settings
from cpbl.db import conn
from cpbl.features.batting import (
    HEADLINE_STATS,
    MIN_PRIOR_AB,
    STAT_DEFS,
    SeasonAgg,
    _league_rates,
    _load_aggregates,
    build_batting_dataset,
)
from cpbl.models import marcel

log = logging.getLogger("cpbl.train")

TEST_FROM = 2018
RATE_STATS = list(STAT_DEFS.keys())  # avg, obp, slg
FEATURE_COLS = (
    ["age"]
    + [f"pa_lag{i}" for i in (1, 2, 3)]
    + [f"{s}_lag{i}" for s in RATE_STATS for i in (1, 2, 3)]
)

LGB_PARAMS = dict(
    objective="regression_l1",
    n_estimators=500,
    learning_rate=0.03,
    num_leaves=31,
    min_child_samples=30,
    subsample=0.8,
    colsample_bytree=0.8,
    verbosity=-1,
)


def _mae(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean(np.abs(y - p)))


def _rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - p) ** 2)))


def _to_x(rows: list[dict]) -> np.ndarray:
    return np.array(
        [[(r[c] if r.get(c) is not None else np.nan) for c in FEATURE_COLS] for r in rows],
        dtype=float,
    )


def _overall_league(lg: dict[int, dict[str, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for stat in RATE_STATS:
        vals = [d[stat] for d in lg.values() if d.get(stat)]
        out[stat] = sum(vals) / len(vals) if vals else 0.0
    return out


# ---------- Marcel ----------


def _marcel_preds(rows: list[dict], aggs, births, lg) -> dict[str, np.ndarray]:
    overall = _overall_league(lg)
    preds: dict[str, list[float]] = {s: [] for s in HEADLINE_STATS}
    for r in rows:
        pid, year = r["player_id"], r["target_year"]
        priors = [aggs.get((pid, year - k)) for k in (1, 2, 3)]
        lr = lg.get(year - 1, overall)
        m = marcel.project(priors, r.get("age"), lr)
        for s in HEADLINE_STATS:
            preds[s].append(m[s] if m[s] is not None else np.nan)
    return {s: np.array(v, dtype=float) for s, v in preds.items()}


# ---------- 推論：下季投影 ----------


def _build_inference_rows(aggs: dict, births: dict, target_year: int) -> list[dict]:
    """為 target_year 建推論列（不需 actual），只取近兩年內有出賽的球員。"""
    rows: list[dict] = []
    seen: set[str] = {pid for (pid, _y) in aggs}
    for pid in seen:
        priors = [aggs.get((pid, target_year - k)) for k in (1, 2, 3)]
        if priors[0] is None or priors[0].ab < MIN_PRIOR_AB:
            continue  # 上一季沒打 → 視為非現役，不投影
        row: dict = {"player_id": pid, "target_year": target_year}
        row["age"] = (target_year - births[pid]) if pid in births else None
        for i, p in enumerate(priors, start=1):
            row[f"pa_lag{i}"] = p.pa if p else None
            for stat in RATE_STATS:
                if p:
                    num, den = STAT_DEFS[stat](p.__dict__)
                    row[f"{stat}_lag{i}"] = (num / den) if den else None
                else:
                    row[f"{stat}_lag{i}"] = None
        rows.append(row)
    return rows


# ---------- 持久化 ----------


def _persist(model_version: str, cv_metrics: dict, boosters: dict, backtest_rows, backtest_preds,
             infer_rows, infer_preds) -> None:
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            INSERT INTO cpbl.model_versions (id, task, algo, params, cv_metrics)
            VALUES (%s, 'batting_projection', 'lightgbm', %s, %s)
            ON CONFLICT (id) DO UPDATE SET params=EXCLUDED.params, cv_metrics=EXCLUDED.cv_metrics,
                trained_at=now()
            """,
            (model_version, json.dumps(LGB_PARAMS), json.dumps(cv_metrics)),
        )
        # 清掉本版舊預測，重寫
        cur.execute("DELETE FROM cpbl.projections WHERE model_version = %s", (model_version,))

        records = []
        # 回測預測（含 actual）
        for stat in HEADLINE_STATS:
            for r, pred in zip(backtest_rows, backtest_preds[stat], strict=True):
                if np.isnan(pred):
                    continue
                records.append((r["player_id"], r["target_year"], model_version, stat,
                                float(pred), r.get(f"y_{stat}")))
        # 下季投影（actual = NULL）
        for stat in HEADLINE_STATS:
            for r, pred in zip(infer_rows, infer_preds[stat], strict=True):
                if np.isnan(pred):
                    continue
                records.append((r["player_id"], r["target_year"], model_version, stat,
                                float(pred), None))

        cur.executemany(
            """
            INSERT INTO cpbl.projections (player_id, target_year, model_version, stat, predicted, actual)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id, target_year, model_version, stat) DO UPDATE SET
                predicted=EXCLUDED.predicted, actual=EXCLUDED.actual
            """,
            records,
        )
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    for stat, booster in boosters.items():
        booster.booster_.save_model(str(settings.artifact_dir / f"lgbm_batting_{stat}.txt"))


def train() -> dict:
    rows = build_batting_dataset()
    aggs, births = _load_aggregates()
    lg = _league_rates(aggs)
    log.info("dataset rows: %d", len(rows))

    train_rows = [r for r in rows if r["target_year"] < TEST_FROM]
    test_rows = [r for r in rows if r["target_year"] >= TEST_FROM]
    log.info("train=%d test=%d (split at %d)", len(train_rows), len(test_rows), TEST_FROM)

    Xtr, Xte = _to_x(train_rows), _to_x(test_rows)

    # ---- Marcel baseline ----
    marcel_te = _marcel_preds(test_rows, aggs, births, lg)

    # ---- LightGBM per rate stat（ops 由 obp+slg 推得，與 Marcel 一致）----
    boosters: dict = {}
    lgbm_te: dict[str, np.ndarray] = {}
    for stat in RATE_STATS:
        ytr = np.array([r[f"y_{stat}"] for r in train_rows], dtype=float)
        mask = ~np.isnan(ytr)
        model = lgb.LGBMRegressor(**LGB_PARAMS)
        model.fit(Xtr[mask], ytr[mask])
        boosters[stat] = model
        lgbm_te[stat] = model.predict(Xte)
    lgbm_te["ops"] = lgbm_te["obp"] + lgbm_te["slg"]

    # ---- 評估（對齊兩者：只比兩邊都有預測且有 actual 的列）----
    metrics: dict[str, dict] = {}
    for stat in HEADLINE_STATS:
        y = np.array([r.get(f"y_{stat}", np.nan) for r in test_rows], dtype=float)
        m, g = marcel_te[stat], lgbm_te[stat]
        valid = ~np.isnan(y) & ~np.isnan(m) & ~np.isnan(g)
        metrics[stat] = {
            "n": int(valid.sum()),
            "marcel_mae": _mae(y[valid], m[valid]),
            "lgbm_mae": _mae(y[valid], g[valid]),
            "marcel_rmse": _rmse(y[valid], m[valid]),
            "lgbm_rmse": _rmse(y[valid], g[valid]),
        }

    # ---- 下季投影（用全資料重訓 → 推論 next year）----
    next_year = max(y for (_p, y) in aggs) + 1
    infer_rows = _build_inference_rows(aggs, births, next_year)
    Xall = _to_x(rows)
    Xinfer = _to_x(infer_rows)
    infer_preds: dict[str, np.ndarray] = {}
    final_boosters: dict = {}
    for stat in RATE_STATS:
        yall = np.array([r[f"y_{stat}"] for r in rows], dtype=float)
        mask = ~np.isnan(yall)
        model = lgb.LGBMRegressor(**LGB_PARAMS)
        model.fit(Xall[mask], yall[mask])
        final_boosters[stat] = model
        infer_preds[stat] = model.predict(Xinfer)
    infer_preds["ops"] = infer_preds["obp"] + infer_preds["slg"]

    model_version = f"lgbm-batting-{date.today():%Y.%m.%d}"
    _persist(model_version, metrics, final_boosters, test_rows, lgbm_te, infer_rows, infer_preds)

    return {"model_version": model_version, "metrics": metrics, "next_year": next_year,
            "projected_players": len(infer_rows)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    result = train()
    print("\n=== 回測結果（test target_year >= %d）===" % TEST_FROM)
    print(f"{'stat':<6}{'n':>6}{'Marcel MAE':>13}{'LGBM MAE':>11}{'勝出':>8}")
    for stat, m in result["metrics"].items():
        winner = "LGBM" if m["lgbm_mae"] < m["marcel_mae"] else "Marcel"
        print(f"{stat:<6}{m['n']:>6}{m['marcel_mae']:>13.4f}{m['lgbm_mae']:>11.4f}{winner:>8}")
    print(f"\nmodel_version={result['model_version']}  "
          f"下季({result['next_year']})投影球員={result['projected_players']}")


if __name__ == "__main__":
    main()
