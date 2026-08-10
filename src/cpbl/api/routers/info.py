"""子專案契約：/api/info（主站 InfoPoller，永不拋錯）+ /healthz。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.api.unresolved import pending_result_count
from cpbl.completion import TAIPEI_TODAY_SQL, completed_games_sql_with_evidence
from cpbl.config import settings
from cpbl.db import conn

router = APIRouter()


def _scalar(sql: str, params: tuple = ()) -> Any:
    with conn() as c:
        cur = c.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


@router.get("/api/info")
def info() -> dict:
    """主站 InfoPoller 契約。永遠回 200；metrics 展示這個 live 資料產品的狀態。"""
    metrics: dict[str, Any] = {}
    status = "running"
    try:
        season = DEFAULT_SEASON
        # 證據感知判準：0:0 真和局需外部證據才算完成（DATA-TIE-REMEDY1）
        completed_sql = completed_games_sql_with_evidence("games")
        games = _scalar("SELECT count(*) FROM cpbl.games") or 0
        metrics["games_indexed"] = games
        metrics["seasons_covered"] = _scalar("SELECT count(DISTINCT year) FROM cpbl.games") or 0
        metrics["current_season"] = season
        metrics["season_games_completed"] = _scalar(
            f"SELECT count(*) FROM cpbl.games WHERE year = %s AND {completed_sql}", (season,)
        ) or 0
        metrics["teams_tracked"] = _scalar(
            "SELECT count(*) FROM cpbl.team_current WHERE year = %s", (season,)
        ) or 0
        metrics["pitchers_tracked"] = _scalar(
            "SELECT count(*) FROM cpbl.pitching_current WHERE year = %s", (season,)
        ) or 0
        metrics["batters_tracked"] = _scalar(
            "SELECT count(*) FROM cpbl.batting_current WHERE year = %s", (season,)
        ) or 0
        metrics["matchups_indexed"] = _scalar(
            "SELECT count(*) FROM cpbl.batter_pitcher_matchups"
        ) or 0
        metrics["player_splits_indexed"] = (
            (_scalar("SELECT count(*) FROM cpbl.batting_splits") or 0)
            + (_scalar("SELECT count(*) FROM cpbl.pitching_splits") or 0)
        )
        # 「今日待預測場次」＝排在今天且尚未有比分者。刻意**不**改用完成判準：
        # 母體限定當日，5 場歷史和局（2018–2025）不可能落入。
        #
        # 「今天」必須以**台北日**為準（DATA-TZ-BOUNDARY1／AUDIT1 C12）：DB timezone
        # 是 UTC，`CURRENT_DATE` 在台北 00:00–07:59 仍停在前一日，此處是全庫唯一的
        # **精確等值**日期界線，一偏移就整個指到錯誤的一天——該指標每日有 8 小時讀到
        # 昨天的場次數。上下界（<= / >=）頂多寬鬆或保守，等值沒有這種緩衝。
        metrics["predictions_today"] = _scalar(
            "SELECT count(*) FROM cpbl.games "
            "WHERE year = %s AND home_score + away_score = 0 "
            f"AND game_date = {TAIPEI_TODAY_SQL}", (season,)
        ) or 0
        last_game = _scalar(
            f"SELECT max(game_date) FROM cpbl.games WHERE {completed_sql}"
        )
        metrics["last_game_date"] = last_game.isoformat() if last_game else None
        try:  # refresh_log 可能尚未 migrate，獨立保護避免拖垮整個 info
            last_refresh = _scalar("SELECT max(refreshed_at) FROM cpbl.refresh_log WHERE ok")
            metrics["last_refresh"] = last_refresh.isoformat() if last_refresh else None
        except Exception:  # noqa: BLE001
            metrics["last_refresh"] = None
        try:  # 維護者訊號：官方說打完了、本站卻仍是 0–0 的場次數（近 30 天，全層級）
            # **健康態恆為 0**，這是它值得佔一格的唯一理由。延賽與保留不計入——它們在
            # 首頁的最近比賽日卡上已有徽章，混進來只會讓這個數字長期非零而沒人再看它
            # （判定與取捨見 `cpbl.api.unresolved.pending_result_count`）。
            with conn() as c:
                metrics["results_pending"] = pending_result_count(c.cursor())
        except Exception:  # noqa: BLE001 — 表缺席／權限問題時整格缺席，不宣稱 0
            pass
        try:  # 賽事預測走查回測準確率（活的 ML 系統指標：模型 vs 全押主場）
            bt = _scalar("SELECT cv_metrics FROM cpbl.model_versions WHERE task='outcome' "
                         "ORDER BY trained_at DESC LIMIT 1")
            if bt:
                acc = max(mm["accuracy"] for mm in bt["models"] if mm["name"] != "全押主場")
                base = next(mm["accuracy"] for mm in bt["models"] if mm["name"] == "全押主場")
                metrics["outcome_model_accuracy"] = round(acc, 4)
                metrics["outcome_baseline_accuracy"] = round(base, 4)
                metrics["outcome_backtest_games"] = bt["n_test"]
        except Exception:  # noqa: BLE001
            pass

        if games == 0:
            status = "maintenance"  # 尚未匯入任何賽事
    except Exception:  # noqa: BLE001 — info 端點不可拋錯，退化即可
        status = "maintenance"

    return {"status": status, "version": settings.app_version, "metrics": metrics}


@router.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
