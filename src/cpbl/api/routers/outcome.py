"""賽果預測：離線回測對照、固定語意群賽前勝率、打席模擬。

舊互動探索器的五支端點（features／evaluate／teams／matchups／simulate）與即時 fit 實作已於 #405 移除：
前端早在 DEP-PREDICT-LEGACY1 下線，正式站 API 容器 access log 14 小時零命中（同期對照流量逾 5,600 筆）。
原碼對照用 `git show 0ffd401 -- src/cpbl/api/routers/outcome.py src/cpbl/models/outcome.py src/cpbl/models/matchup.py`。
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
from fastapi import APIRouter, Query

from cpbl.api.pregame_serving import serving_state
from cpbl.config import settings
from cpbl.db import conn
from cpbl.models.outcome_simple import ORIENT, load_outcome_rows
from cpbl.models.pa_sim import (
    GameState,
    load_pa_artifact,
    predict_outcomes,
    simulate_plate_appearance,
)

router = APIRouter()


@router.get("/api/v1/outcome/backtest")
def outcome_backtest() -> dict:
    """全特徵走查回測對照（LightGBM vs 邏輯回歸 vs 全押主場），由離線 cpbl-train-outcome
    持久化於 model_versions(task='outcome')。前端「模型回測」面板用此誠實展示模型價值。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT id, trained_at, cv_metrics FROM cpbl.model_versions "
            "WHERE task = 'outcome' ORDER BY trained_at DESC LIMIT 1"
        )
        row = cur.fetchone()
    if not row:
        return {"available": False}
    vid, trained_at, m = row
    return {"available": True, "version": vid,
            "trained_at": trained_at.isoformat() if trained_at else None, **m}


@router.get("/api/v1/outcome/pregame")
def outcome_pregame(limit: int = Query(20, ge=1, le=60)) -> dict:
    """固定語意群賽前勝率；不接受特徵勾選或權重。"""
    # serving＝這份 artifact 是不是最新那一次回測產出的（ML-OUTCOME-SIMPLE-LEAK2）。
    # 前端要不要揭露看 serving["degradation"]（非 null 就要講），不是看 status：
    # serving_previous 是機率來自上一版模型，serving_current 也可能帶 serving_gate_failed
    # ——serving 就是最新回測那一版，而那一次回測沒過閘門。
    artifact, serving = serving_state()
    if artifact is None:
        return {"available": False, "reason": serving["reason"], "serving": serving}
    rows = [row for row in load_outcome_rows(completed_only=False)
            if row.game_date and row.game_date >= date.today()][:limit]
    if not rows:
        return {"available": True, "serving": serving,
                "version": serving["serving_version"],
                "trained_through": artifact["trained_through"],
                "signals": artifact["signals"], "items": []}
    point = artifact["model"].predict(rows)
    ensemble = np.array([model.predict(rows) for model in artifact.get("ensemble", [])])
    items = []
    for index, (row, probability) in enumerate(zip(rows, point, strict=True)):
        low = float(np.quantile(ensemble[:, index], 0.05)) if ensemble.size else None
        high = float(np.quantile(ensemble[:, index], 0.95)) if ensemble.size else None
        items.append({
            "season": row.season, "game_sno": row.game_sno,
            "game_date": row.game_date.isoformat(), "home": row.home, "away": row.away,
            "home_win_probability": round(float(probability), 4),
            "model_interval_90": [round(low, 4), round(high, 4)] if low is not None else None,
            "signals": {group: {"key": signal, "raw": row.features.get(signal),
                                  "direction": ("lower_favors_home" if ORIENT.get(signal) == -1
                                                else "higher_favors_home")}
                        for group, signal in artifact["signals"].items()},
        })
    return {"available": True, "serving": serving,
            "version": serving["serving_version"],
            "trained_through": artifact["trained_through"],
            "signals": artifact["signals"], "interval": artifact.get("interval"),
            "items": items}


@router.get("/api/v1/outcome/pregame/serving")
def outcome_pregame_serving() -> dict:
    """賽前模型的 serving 狀態（只讀 artifact meta 與 model_versions 最新列）。

    刻意獨立於 `/pregame/backtest`：降級揭露必須**即時**，回測指標表則可以長快取。
    前端兩個頁面都以 no-store 取這一支，因此 refresh 一跑完狀態就會反映在畫面上；
    上線程序的「驗證提示消失」也可以直接 curl 這支端點對帳，不必解析 HTML。
    """
    _, serving = serving_state()
    return serving


@router.get("/api/v1/outcome/pregame/backtest")
def outcome_pregame_backtest() -> dict:
    """最新一次走查回測紀錄，外加 serving 狀態。

    方法頁的閘門面板靠這支端點；只回傳回測結果會漏掉「這一版有沒有真的上線」——閘門未過時
    DB 這一列是 `deployable=false`，而 serving 仍在跑上一版。兩件事必須一起講。
    """
    _, serving = serving_state()
    with conn() as connection:
        row = connection.execute(
            "SELECT id,trained_at,cv_metrics FROM cpbl.model_versions "
            "WHERE task='outcome_simple' ORDER BY trained_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return {"available": False, "serving": serving}
    return {"available": True, "version": row[0], "serving": serving,
            "trained_at": row[1].isoformat() if row[1] else None, **row[2]}


def _pa_wp(span: str):
    from cpbl.models.winprob import _load_dist, _we_solver, wp_state

    dist = _load_dist(span, "A")
    we_top, we_bot = _we_solver(dist[("1", "___", 0)], dist[("2", "___", 0)])

    def calculate(state: GameState) -> float:
        return wp_state(dist, we_top, we_bot, state.inning, state.half,
                        state.home_score - state.away_score, state.bases, state.outs)

    return calculate


def _pa_response(artifact: dict, hitter: str, pitcher: str, state: GameState) -> dict:
    model = artifact["model"]
    result = simulate_plate_appearance(
        model, artifact["kernel"], hitter, pitcher, state, _pa_wp(artifact["wp_span"]),
    )
    hitter_n = sum(model.hitters.get(hitter, {}).values())
    pitcher_n = sum(model.pitchers.get(pitcher, {}).values())
    direct_n = sum(model.direct.get((hitter, pitcher), {}).values())
    effective_n = max(1.0, min(hitter_n + model.hitter_strength,
                               pitcher_n + model.pitcher_strength))
    probabilities = predict_outcomes(model, hitter, pitcher)
    for outcome_key, probability in probabilities.items():
        margin = 1.645 * math.sqrt(probability * (1 - probability) / (effective_n + 1))
        result["outcomes"][outcome_key]["probability_interval_90"] = [
            max(0.0, probability - margin), min(1.0, probability + margin),
        ]
    return {
        "available": True, "trained_through": artifact["trained_through"],
        "wp_span": artifact["wp_span"],
        "uncertainty_method": "normal approximation over shrinkage effective sample size",
        "sample": {"hitter_pa": hitter_n, "pitcher_pa": pitcher_n,
                   "direct_pa": direct_n, "low_sample": direct_n < 20,
                   "shrinkage_weight": {
                       "hitter": hitter_n / (hitter_n + model.hitter_strength),
                       "pitcher": pitcher_n / (pitcher_n + model.pitcher_strength),
                       "direct": direct_n / (direct_n + model.direct_strength),
                   }},
        "state": state.__dict__, **result,
    }


def _read_pa_artifact() -> tuple[dict | None, str | None]:
    path = settings.artifact_dir / "pa_sim.joblib"
    if not path.exists():
        return None, "pa_sim artifact 未建置"
    try:
        artifact = load_pa_artifact(path)
        required = {"trained_through", "wp_span", "model", "kernel"}
        if not isinstance(artifact, dict) or not required <= artifact.keys():
            raise ValueError("artifact contract 不完整")
    except Exception:
        return None, "pa_sim artifact 無法載入"
    return artifact, None


@router.get("/api/v1/outcome/plate-appearance")
def outcome_plate_appearance(
    hitter: str = Query(...), pitcher: str = Query(...),
    inning: int = Query(..., ge=1, le=12), half: str = Query(..., pattern="^(1|2)$"),
    away_score: int = Query(..., ge=0), home_score: int = Query(..., ge=0),
    bases: str = Query("___", pattern="^(_|1)(_|2)(_|3)$"),
    outs: int = Query(..., ge=0, le=2),
) -> dict:
    artifact, reason = _read_pa_artifact()
    if artifact is None:
        return {"available": False, "reason": reason}
    return _pa_response(artifact, hitter, pitcher,
                        GameState(inning, half, bases, outs, away_score, home_score))
