"""賽果預測：特徵清單、即時 fit 評估、離線回測、對戰卡與模擬。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _parse_features
from cpbl.db import conn
from cpbl.features.outcome import CANDIDATE_FEATURES, FEATURE_DESC
from cpbl.models import matchup, outcome

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
