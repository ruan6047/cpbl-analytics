"""賽果預測：特徵清單、即時 fit 評估、離線回測、對戰卡與模擬。"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _parse_features
from cpbl.config import settings
from cpbl.db import conn
from cpbl.features.outcome import CANDIDATE_FEATURES, FEATURE_DESC
from cpbl.models import matchup, outcome
from cpbl.models.outcome_simple import ORIENT, load_artifact, load_outcome_rows
from cpbl.models.pa_sim import (
    GameState,
    load_game_pa_snapshot,
    load_pa_artifact,
    predict_outcomes,
    simulate_plate_appearance,
)

router = APIRouter()


@router.get("/api/v1/outcome/features")
def outcome_features() -> dict:
    """賽果預測的候選特徵清單（含說明/群組/相依，給前端分群 + tooltip + 共線軟提醒）。"""
    from cpbl.features.outcome import FEATURE_CORR, FEATURE_GROUP
    return {
        "features": [
            {"key": k, "label": label, "desc": FEATURE_DESC.get(k, ""),
             "group": FEATURE_GROUP.get(k, "其他"), "corr": FEATURE_CORR.get(k)}
            for k, label in CANDIDATE_FEATURES
        ]
    }


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


@router.get("/api/v1/outcome/evaluate")
def outcome_evaluate(features: str = Query(..., description="逗號分隔的特徵 key")) -> dict:
    """用選定特徵子集即時 fit + 時間切分回測。"""
    try:
        return outcome.evaluate(_parse_features(features))
    except ValueError as e:
        return {"error": str(e)}


@router.get("/api/v1/outcome/teams")
def outcome_teams(season: int = Query(DEFAULT_SEASON)) -> dict:
    """當季球隊清單（給任選兩隊模擬的下拉選單）。"""
    return {"season": season, "teams": matchup.list_teams(season)}
@router.get("/api/v1/outcome/matchups")
def outcome_matchups(
    features: str = Query(..., description="逗號分隔的變因 key"),
    season: int = Query(DEFAULT_SEASON),
    limit: int = Query(20, ge=1, le=60),
) -> dict:
    """今日起未開打賽事的對戰卡（含雙方真實數字 + 預設權重 + 標準化值 z）。"""
    try:
        return matchup.upcoming(_parse_features(features), season, limit)
    except ValueError as e:
        return {"error": str(e)}


@router.get("/api/v1/outcome/simulate")
def outcome_simulate(
    home: str = Query(..., description="主隊 team_code"),
    away: str = Query(..., description="客隊 team_code"),
    features: str = Query(...),
    season: int = Query(DEFAULT_SEASON),
) -> dict:
    """任選兩隊的假想對戰卡（用當季到當日統計）。"""
    try:
        return matchup.simulate(home, away, _parse_features(features), season)
    except ValueError as e:
        return {"error": str(e)}


@router.get("/api/v1/outcome/pregame")
def outcome_pregame(limit: int = Query(20, ge=1, le=60)) -> dict:
    """固定語意群賽前勝率；不接受特徵勾選或權重。"""
    path = settings.artifact_dir / "outcome_simple.joblib"
    if not path.exists():
        return {"available": False, "reason": "outcome_simple artifact 未建置"}
    artifact = load_artifact(path)
    rows = [row for row in load_outcome_rows(completed_only=False)
            if row.game_date and row.game_date >= date.today()][:limit]
    if not rows:
        return {"available": True, "trained_through": artifact["trained_through"],
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
    return {"available": True, "trained_through": artifact["trained_through"],
            "signals": artifact["signals"], "interval": artifact.get("interval"),
            "items": items}


@router.get("/api/v1/outcome/pregame/backtest")
def outcome_pregame_backtest() -> dict:
    with conn() as connection:
        row = connection.execute(
            "SELECT id,trained_at,cv_metrics FROM cpbl.model_versions "
            "WHERE task='outcome_simple' ORDER BY trained_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return {"available": False}
    return {"available": True, "version": row[0],
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


@router.get("/api/v1/outcome/plate-appearance/from-game")
def outcome_plate_appearance_from_game(
    year: int = Query(DEFAULT_SEASON), kind_code: str = Query("A", pattern="^A$"),
    game_sno: int = Query(..., ge=1), main_event_no: int = Query(..., ge=1),
) -> dict:
    snapshot = load_game_pa_snapshot(year, kind_code, game_sno, main_event_no)
    if not snapshot or not snapshot.game_date:
        return {"available": False, "reason": "無法唯一定位完整打席"}
    artifact, reason = _read_pa_artifact()
    if artifact is None:
        return {"available": False, "reason": reason}
    if artifact["trained_through"] >= snapshot.game_date.year:
        return {"available": False, "reason": "無符合 trained_through < game_date 的 artifact"}
    return {"source": {"year": year, "kind_code": kind_code, "game_sno": game_sno,
                        "main_event_no": main_event_no, "pa_start": snapshot.event_no,
                        "pa_end": snapshot.end_event_no},
            **_pa_response(artifact, snapshot.hitter, snapshot.pitcher, snapshot.before)}
