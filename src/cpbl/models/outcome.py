"""賽果預測：即時 fit 使用者選定的特徵子集（邏輯回歸）。

設計重點（見專案 CLAUDE.md「賽果預測」段）：
- 使用者每選一組特徵，就**只用該子集**即時訓練一個邏輯回歸，回傳「這組合的
  回測準確率」。每個子集都是獨立真模型 → 機率有統計意義，揭露各特徵的邊際價值。
- `home_field` 特殊處理：它控制是否啟用 intercept（= 是否讓模型學主場基準勝率），
  而非當成欄位標準化（常數欄位標準化後會被歸零，主場優勢會消失）。
- 其餘 5 個差值特徵標準化 → 係數可直接比大小（feature importance）。
- 時間切分：train = 完成且 season < 最新完成季；test = 最新完成季。無資料洩漏。
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

from cpbl.db import conn
from cpbl.features.outcome import FEATURE_KEYS

HOME_FIELD = "home_field"
REAL_FEATURES = [k for k in FEATURE_KEYS if k != HOME_FIELD]
_BASE = 5  # _load 回傳中特徵欄位起始 index


def _load(completed_only: bool):
    cols = ", ".join(FEATURE_KEYS)
    where = "completed = true AND home_win IN (0,1)" if completed_only else "completed = false"
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT season, game_date, home_team_name, away_team_name, home_win, {cols}
            FROM cpbl.game_features
            WHERE {where}
            ORDER BY game_date, game_sno
            """
        )
        return cur.fetchall()


def _matrix(rows, idx: list[int]) -> np.ndarray:
    return np.array([[r[_BASE + i] for i in idx] for r in rows], dtype=float)


def _validate(features: list[str]):
    sel = [f for f in features if f in FEATURE_KEYS]
    if not sel:
        raise ValueError("至少需選一個特徵")
    real = [f for f in sel if f != HOME_FIELD]
    use_intercept = HOME_FIELD in sel
    return sel, real, use_intercept


def _fit(train, real: list[str], use_intercept: bool):
    """回傳 predict 函式 proba(rows)->np.ndarray 與標準化係數 dict。"""
    ytr = np.array([r[4] for r in train], dtype=int)

    if not real:  # 只選主場 → intercept-only 常數模型（預測主場基準勝率）
        base = float(ytr.mean())
        return (lambda rows: np.full(len(rows), base)), {HOME_FIELD: round(base, 4)}

    idx = [FEATURE_KEYS.index(f) for f in real]
    scaler = StandardScaler().fit(_matrix(train, idx))
    clf = LogisticRegression(fit_intercept=use_intercept, max_iter=1000)
    clf.fit(scaler.transform(_matrix(train, idx)), ytr)

    coefs = {f: round(float(c), 4) for f, c in zip(real, clf.coef_[0], strict=True)}
    if use_intercept:
        coefs[HOME_FIELD] = round(float(clf.intercept_[0]), 4)

    def proba(rows):
        return clf.predict_proba(scaler.transform(_matrix(rows, idx)))[:, 1]

    return proba, coefs


def evaluate(features: list[str]) -> dict:
    """用選定特徵子集做時間切分回測，回傳準確率/Brier/係數。"""
    sel, real, use_intercept = _validate(features)
    rows = _load(completed_only=True)
    # 丟掉「選定特徵有 NULL」的場次 → 覆蓋年限不同的特徵（如 2018+ 當季細項）自動限縮訓練年限。
    fidx = [_BASE + FEATURE_KEYS.index(f) for f in real]
    rows = [r for r in rows if all(r[i] is not None for i in fidx)]
    if not rows:
        return {"error": "no completed games"}

    seasons = sorted({r[0] for r in rows})
    test_season = seasons[-1]
    train = [r for r in rows if r[0] < test_season]
    test = [r for r in rows if r[0] == test_season]
    if not train or not test:
        train, test = rows[: int(len(rows) * 0.8)], rows[int(len(rows) * 0.8):]

    proba_fn, coefs = _fit(train, real, use_intercept)
    proba = proba_fn(test)
    pred = (proba >= 0.5).astype(int)
    yte = np.array([r[4] for r in test], dtype=int)
    home_rate = float(yte.mean())

    return {
        "features": sel,
        "n_train": len(train),
        "n_test": len(test),
        "test_season": test_season,
        "accuracy": round(float(accuracy_score(yte, pred)), 4),
        "baseline_home_always": round(max(home_rate, 1 - home_rate), 4),
        "brier": round(float(brier_score_loss(yte, proba)), 4),
        "log_loss": round(float(log_loss(yte, proba, labels=[0, 1])), 4),
        "coefficients": coefs,
    }


def predict_upcoming(features: list[str], limit: int = 30) -> dict:
    """用全部完成場次 fit，預測「今天起」未開打場次的主隊勝率。"""
    from datetime import date

    sel, real, use_intercept = _validate(features)
    train = _load(completed_only=True)
    upcoming = [r for r in _load(completed_only=False) if r[1] and r[1] >= date.today()]
    if not train or not upcoming:
        return {"features": sel, "items": []}

    proba_fn, _ = _fit(train, real, use_intercept)
    proba = proba_fn(upcoming)

    items = [
        {
            "game_date": r[1].isoformat(),
            "home": r[2], "away": r[3],
            "home_win_prob": round(float(p), 4),
        }
        for r, p in zip(upcoming, proba, strict=True)
    ]
    items.sort(key=lambda x: x["game_date"])
    return {"features": sel, "items": items[:limit]}
