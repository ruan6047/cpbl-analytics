"""賽事預測：時間切分回測對照（LightGBM vs 邏輯回歸 vs 全押主場 baseline）。

定位（對齊 CLAUDE.md 紅線）：
- 互動式「特徵子集探索器」(models/outcome.py) 仍是產品核心──透明、可解釋、即時 fit。
- 本模組另跑一個**全特徵**的離線回測對照，誠實回答「上更強的模型 + 全史資料，
  到底比『無腦全押主場』好多少」。單場勝負天花板 ~60%，重點在透明，不在擊敗賭盤。
- 時間切分：train = 完成且 season < 最新完成季；test = 最新完成季。無資料洩漏。
- 結果寫入 cpbl.model_versions(task='outcome')，供 API /api/info 與 /predict 展示。

LightGBM 需 libgomp → 在容器內跑（`docker compose run --rm api cpbl-train-outcome`）。
"""

from __future__ import annotations

import json
import logging
import time

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

from cpbl.db import conn
from cpbl.features.outcome import FEATURE_KEYS, REAL_FEATURES_LABELS
from cpbl.models.outcome import REAL_FEATURES, _load, _matrix

log = logging.getLogger("cpbl.models.outcome_gbm")

IDX = [FEATURE_KEYS.index(f) for f in REAL_FEATURES]  # _matrix 取全部 real 特徵欄位


_GBM_PARAMS = dict(
    n_estimators=400, learning_rate=0.02, num_leaves=15, min_child_samples=60,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
    random_state=42, n_jobs=-1, verbose=-1,
)
_WALK_SEASONS = 5  # 走查回測涵蓋的最近 N 季（彙整成單一 test pool）


def _metrics(y: np.ndarray, proba: np.ndarray) -> dict:
    pred = (proba >= 0.5).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "brier": round(float(brier_score_loss(y, proba)), 4),
        "log_loss": round(float(log_loss(y, np.clip(proba, 1e-6, 1 - 1e-6), labels=[0, 1])), 4),
    }


def _fit_predict(train, test):
    """回傳 (lr_proba, gbm_proba, home_rate_train)；三方共用一次切分。"""
    from lightgbm import LGBMClassifier

    # 覆蓋年限不同的特徵（如 2018+ 當季細項）在更早年份為 NULL → NaN；邏輯回歸/scaler 不接受，
    # 以 0（中性）填補（LightGBM 本可吃 NaN，一併填補保持一致）。
    xtr = np.nan_to_num(_matrix(train, IDX), nan=0.0)
    xte = np.nan_to_num(_matrix(test, IDX), nan=0.0)
    ytr = np.array([r[4] for r in train], dtype=int)
    scaler = StandardScaler().fit(xtr)
    lr = LogisticRegression(max_iter=1000).fit(scaler.transform(xtr), ytr)
    lr_p = lr.predict_proba(scaler.transform(xte))[:, 1]
    gbm = LGBMClassifier(**_GBM_PARAMS).fit(xtr, ytr)
    gbm_p = gbm.predict_proba(xte)[:, 1]
    return lr_p, gbm_p, float(ytr.mean()), gbm


def backtest() -> dict:
    """走查回測：對最近 N 季逐季 train(<s)→predict(s)，把各季預測彙整成單一 test pool
    再算三方（全押主場 / 全特徵邏輯回歸 / LightGBM）準確率，避免單一季中樣本過小。
    另持久化最新一季的特徵重要度與細項。"""
    rows = _load(completed_only=True)
    if not rows:
        return {"error": "no completed games"}

    seasons = sorted({r[0] for r in rows})
    test_seasons = [s for s in seasons[-_WALK_SEASONS:] if any(r[0] < s for r in rows)]
    if not test_seasons:  # 僅單季資料 → 退化 80/20
        cut = int(len(rows) * 0.8)
        test_seasons = [None]
        splits = [(rows[:cut], rows[cut:])]
    else:
        splits = [([r for r in rows if r[0] < s], [r for r in rows if r[0] == s]) for s in test_seasons]

    y_all: list[int] = []
    base_p, lr_all, gbm_all = [], [], []
    last_gbm = None
    for train, test in splits:
        lr_p, gbm_p, home_rate_tr, gbm = _fit_predict(train, test)
        y_all.extend(r[4] for r in test)
        base_p.extend([home_rate_tr] * len(test))
        lr_all.extend(lr_p.tolist()); gbm_all.extend(gbm_p.tolist())
        last_gbm = gbm
    y = np.array(y_all, dtype=int)
    home_rate = float(y.mean())

    base = {"name": "全押主場", **_metrics(y, np.array(base_p)),
            "accuracy": round(max(home_rate, 1 - home_rate), 4)}
    logistic = {"name": "全特徵邏輯回歸", **_metrics(y, np.array(lr_all))}
    lightgbm = {"name": "LightGBM（全特徵）", **_metrics(y, np.array(gbm_all))}

    importance = sorted(
        ({"key": k, "label": REAL_FEATURES_LABELS.get(k, k), "gain": int(g)}
         for k, g in zip(REAL_FEATURES, last_gbm.feature_importances_, strict=True)),
        key=lambda x: -x["gain"],
    )
    best = max([base, logistic, lightgbm], key=lambda m: m["accuracy"])
    return {
        "test_seasons": test_seasons,
        "n_train": len(splits[-1][0]),
        "n_test": len(y),
        "home_rate_test": round(home_rate, 4),
        "models": [base, logistic, lightgbm],
        "best": best["name"],
        "beats_baseline": bool(max(logistic["accuracy"], lightgbm["accuracy"]) > base["accuracy"]),
        "importance": importance,
        "features": REAL_FEATURES,
    }


def persist(result: dict) -> str:
    """寫入 cpbl.model_versions(task='outcome')，回傳 version id。"""
    vid = f"outcome-{int(time.time())}"
    with conn() as c:
        cur = c.cursor()
        # 只保留最新一筆 outcome 回測（避免每日 cron 無限累積）。
        cur.execute("DELETE FROM cpbl.model_versions WHERE task = 'outcome'")
        cur.execute(
            """
            INSERT INTO cpbl.model_versions (id, task, algo, params, cv_metrics)
            VALUES (%s, 'outcome', 'lightgbm-vs-logistic', %s, %s)
            """,
            (vid, json.dumps({"features": result["features"], "test_seasons": result["test_seasons"]}),
             json.dumps(result)),
        )
    return vid


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    r = backtest()
    if "error" in r:
        log.info("回測失敗：%s", r["error"]); return
    seasons = ",".join(str(s) for s in r["test_seasons"])
    log.info("\n=== 賽事預測走查回測（test 季=%s, pool n_test=%d）===", seasons, r["n_test"])
    log.info("%-18s %8s %8s %9s", "模型", "準確率", "Brier", "LogLoss")
    for m in r["models"]:
        log.info("%-18s %8.4f %8.4f %9.4f", m["name"], m["accuracy"], m["brier"], m["log_loss"])
    log.info("\n最佳：%s　打贏全押主場：%s", r["best"], "是 ✅" if r["beats_baseline"] else "否 ❌")
    log.info("\nLightGBM 特徵重要度（gain）：")
    for f in r["importance"]:
        log.info("  %-18s %d", f["label"], f["gain"])
    vid = persist(r)
    log.info("\n已寫入 model_versions：%s", vid)


if __name__ == "__main__":
    main()
