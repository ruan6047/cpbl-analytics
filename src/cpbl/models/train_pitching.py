"""訓練與回測投手成績預測：Marcel（投手版）baseline vs LightGBM。

鏡射 models/train.py 的紀律：時間切分（target_year >= TEST_FROM 為測試）、
新模型必須在回測對照表打贏 Marcel 才可採用。與打者版差異：
- 目標 = ERA / WHIP / K9 / BB9（分母 outs；ip 棒球記法已在 features 層轉換）
- Marcel 壓艙量 reg_outs 於「訓練期內」grid 挑選（給 baseline 最強版本，
  避免弱 baseline 讓 LGBM 虛胖——紅線誠實性的一部分）
- LGBM 額外特徵：gs_share（先發比重，角色轉換訊號；Marcel 保持純血）
**Ship 決策（2026-07-06）＝純 Marcel，LGBM 落選**。證據鏈：
1. 共用壓艙量首輪：LGBM 2勝2敗（era/whip 勝、k9/bb9 敗）。
2. per-stat 壓艙量把 Marcel 調到最強後（era/whip 1200、k9 600、bb9 800 outs），
   測試段 Marcel 3/4 勝、唯一輸的 whip 僅差 0.5%。
3. 曾試「驗證段(2014-2017)凍結選模」的 hybrid：驗證選擇泛化到測試段僅 2/4
   （era/bb9 翻車）——877 列樣本下選模程序本身不穩定，hybrid 無立足點。
K9/BB9 為投手年際最穩定技能、加權+回歸已近最優；ERA 噪音大到誰都只能貼均值。
LGBM 對照表保留於 cv_metrics 存證；資料量增長後（>1500 列）可重啟挑戰。

    docker compose run --rm api cpbl-train-pitching   # 對照需 LightGBM → 容器內跑
"""

from __future__ import annotations

import json
import logging
from datetime import date

import lightgbm as lgb
import numpy as np

from cpbl.db import conn
from cpbl.features.pitching import (
    HEADLINE_STATS,
    MIN_PRIOR_OUTS,
    STAT_DEFS,
    _league_rates,
    _load_aggregates,
    build_pitching_dataset,
)
from cpbl.models import marcel

log = logging.getLogger("cpbl.train")

TEST_FROM = 2018
RATE_STATS = HEADLINE_STATS  # era/whip/k9/bb9 皆直接預測（無 ops 型組合）
FEATURE_COLS = (
    ["age"]
    + [f"outs_lag{i}" for i in (1, 2, 3)]
    + [f"gs_share_lag{i}" for i in (1, 2, 3)]
    + [f"{s}_lag{i}" for s in RATE_STATS for i in (1, 2, 3)]
)
# per-stat 壓艙量 grid（K9 年際穩定需輕壓、ERA 噪音大需重壓——共用單值會顧此失彼）
REG_OUTS_GRID = (60, 120, 210, 300, 400, 600, 800, 1200)

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
    return {stat: (sum(d[stat] for d in lg.values() if d.get(stat))
                   / max(sum(1 for d in lg.values() if d.get(stat)), 1))
            for stat in RATE_STATS}


def _marcel_preds(rows: list[dict], aggs, lg,
                  reg_outs: dict[str, int]) -> dict[str, np.ndarray]:
    overall = _overall_league(lg)
    preds: dict[str, list[float]] = {s: [] for s in RATE_STATS}
    for r in rows:
        pid, year = r["player_id"], r["target_year"]
        priors = [aggs.get((pid, year - k)) for k in (1, 2, 3)]
        lr = lg.get(year - 1, overall)  # 前一季聯盟均值（避免目標季洩漏）
        for s in RATE_STATS:
            m = marcel.project_pitching_stat(priors, s, r.get("age"),
                                             lr.get(s, 0.0), reg_outs[s])
            preds[s].append(m if m is not None else np.nan)
    return {s: np.array(v, dtype=float) for s, v in preds.items()}


def _tune_reg_outs(train_rows: list[dict], aggs, lg) -> dict[str, int]:
    """訓練期內 per-stat 挑 Marcel 壓艙量（MAE 最小者）。"""
    best: dict[str, int] = {}
    for s in RATE_STATS:
        y = np.array([r.get(f"y_{s}", np.nan) for r in train_rows], dtype=float)
        best_mae = float("inf")
        for reg in REG_OUTS_GRID:
            preds = _marcel_preds(train_rows, aggs, lg,
                                  dict.fromkeys(RATE_STATS, reg))[s]
            valid = ~np.isnan(y) & ~np.isnan(preds)
            mae = _mae(y[valid], preds[valid])
            if mae < best_mae:
                best_mae, best[s] = mae, reg
        log.info("Marcel %s: reg_outs=%d（%.0f IP）訓練期MAE=%.4f",
                 s, best[s], best[s] / 3, best_mae)
    return best


def _build_inference_rows(aggs: dict, births: dict, target_year: int) -> list[dict]:
    rows: list[dict] = []
    for pid in {pid for (pid, _y) in aggs}:
        priors = [aggs.get((pid, target_year - k)) for k in (1, 2, 3)]
        if priors[0] is None or priors[0].outs < MIN_PRIOR_OUTS:
            continue
        row: dict = {"player_id": pid, "target_year": target_year}
        row["age"] = (target_year - births[pid]) if pid in births else None
        for i, p in enumerate(priors, start=1):
            row[f"outs_lag{i}"] = p.outs if p else None
            row[f"gs_share_lag{i}"] = (p.gs / p.g) if p and p.g else None
            for stat in RATE_STATS:
                if p:
                    num, den = STAT_DEFS[stat](p.__dict__)
                    row[f"{stat}_lag{i}"] = (num / den) if den else None
                else:
                    row[f"{stat}_lag{i}"] = None
        rows.append(row)
    return rows


def _persist(model_version: str, cv_metrics: dict, backtest_rows,
             backtest_preds, infer_rows, infer_preds) -> None:
    params = {"weights": marcel.WEIGHTS,
              "reg_outs": cv_metrics.get("_marcel_reg_outs"),
              "peak_age": marcel.PIT_PEAK_AGE,
              "lgb_challenger": LGB_PARAMS}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            INSERT INTO cpbl.model_versions (id, task, algo, params, cv_metrics)
            VALUES (%s, 'pitching_projection', 'marcel', %s, %s)
            ON CONFLICT (id) DO UPDATE SET params=EXCLUDED.params,
                cv_metrics=EXCLUDED.cv_metrics, trained_at=now()
            """,
            (model_version, json.dumps(params), json.dumps(cv_metrics)),
        )
        cur.execute("DELETE FROM cpbl.projections WHERE model_version = %s", (model_version,))
        records = []
        for stat in RATE_STATS:
            for r, pred in zip(backtest_rows, backtest_preds[stat], strict=True):
                if np.isnan(pred):
                    continue
                records.append((r["player_id"], r["target_year"], model_version, stat,
                                float(pred), r.get(f"y_{stat}")))
        for stat in RATE_STATS:
            for r, pred in zip(infer_rows, infer_preds[stat], strict=True):
                if np.isnan(pred):
                    continue
                records.append((r["player_id"], r["target_year"], model_version, stat,
                                float(pred), None))
        cur.executemany(
            """
            INSERT INTO cpbl.projections (player_id, target_year, model_version, stat,
                predicted, actual)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id, target_year, model_version, stat) DO UPDATE SET
                predicted=EXCLUDED.predicted, actual=EXCLUDED.actual
            """,
            records,
        )


def train() -> dict:
    rows = build_pitching_dataset()
    aggs, births = _load_aggregates()
    lg = _league_rates(aggs)
    log.info("dataset rows: %d", len(rows))

    train_rows = [r for r in rows if r["target_year"] < TEST_FROM]
    test_rows = [r for r in rows if r["target_year"] >= TEST_FROM]
    log.info("train=%d test=%d (split at %d)", len(train_rows), len(test_rows), TEST_FROM)

    Xtr, Xte = _to_x(train_rows), _to_x(test_rows)

    # ---- Marcel baseline（壓艙量在訓練期內挑，測試期不碰）----
    reg_outs = _tune_reg_outs(train_rows, aggs, lg)
    marcel_te = _marcel_preds(test_rows, aggs, lg, reg_outs)

    # ---- LightGBM 挑戰者（全訓練期）→ 測試段對照（僅存證，不 ship）----
    lgbm_te: dict[str, np.ndarray] = {}
    for stat in RATE_STATS:
        ytr = np.array([r[f"y_{stat}"] for r in train_rows], dtype=float)
        mask = ~np.isnan(ytr)
        model = lgb.LGBMRegressor(**LGB_PARAMS)
        model.fit(Xtr[mask], ytr[mask])
        lgbm_te[stat] = model.predict(Xte)

    metrics: dict[str, dict] = {"_marcel_reg_outs": reg_outs,
                                "_ship": "marcel",
                                "_note": "LGBM 未穩健勝出（3/4 測試段落敗），依紅線不採用"}
    for stat in RATE_STATS:
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

    # ---- 下季投影（ship＝Marcel 直投）----
    next_year = max(y for (_p, y) in aggs) + 1
    infer_rows = _build_inference_rows(aggs, births, next_year)
    overall = _overall_league(lg)
    lr_next = lg.get(next_year - 1, overall)
    infer_preds: dict[str, np.ndarray] = {}
    for stat in RATE_STATS:
        vals = []
        for r in infer_rows:
            priors = [aggs.get((r["player_id"], next_year - k)) for k in (1, 2, 3)]
            m = marcel.project_pitching_stat(priors, stat, r.get("age"),
                                             lr_next.get(stat, 0.0), reg_outs[stat])
            vals.append(m if m is not None else np.nan)
        infer_preds[stat] = np.array(vals, dtype=float)

    model_version = f"marcel-pitching-{date.today():%Y.%m.%d}"
    _persist(model_version, metrics, test_rows, marcel_te, infer_rows, infer_preds)
    return {"model_version": model_version, "metrics": metrics, "next_year": next_year,
            "projected_players": len(infer_rows)}


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    result = train()
    print("\n=== 投手回測（test target_year >= %d；ship=Marcel，LGBM 為落選挑戰者）===" % TEST_FROM)
    print(f"{'stat':<6}{'n':>6}{'Marcel MAE':>13}{'LGBM MAE':>11}{'勝出':>8}")
    for stat in RATE_STATS:
        m = result["metrics"][stat]
        winner = "Marcel" if m["marcel_mae"] <= m["lgbm_mae"] else "LGBM"
        print(f"{stat:<6}{m['n']:>6}{m['marcel_mae']:>13.4f}{m['lgbm_mae']:>11.4f}{winner:>8}")
    print(f"\nmodel_version={result['model_version']}  "
          f"下季({result['next_year']})投影投手={result['projected_players']}")


if __name__ == "__main__":
    main()
