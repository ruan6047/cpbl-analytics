"""子專案契約：/api/info（主站 InfoPoller，永不拋錯）+ /healthz。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.completion import TAIPEI_TODAY_SQL, completed_games_sql_with_evidence
from cpbl.config import settings
from cpbl.db import conn

router = APIRouter()

# 生產同步停擺門檻（OPS-SCHEDULE-FAILURE-BLIND1／#132，偵測器 B）。
#
# ⚠️ **刻意不與首頁 freshness 徽章的 `STALE_AFTER_HOURS = 24` 統一**
# （`cpbl/api/routers/daily.py`）。兩者服務不同對象：
#   · 徽章是給球迷看的資料新鮮度——軟、寧可早提醒，誤報的代價只是多看一眼。
#   · 本欄是給機器判「排程停擺」的——硬、不可誤報，誤報會讓告警被關掉，
#     而被關掉的告警正是本卡在修的病。
#
# 為什麼是 36 而不是 24：實測 2026-07-19…08-14 的 27 次排程，25 個連續成功間隔中有
# 13 個超過 24h；扣掉跨越真實失敗的 2 筆，**仍有 11 個是系統一切正常時的 >24h 間隔**，
# 各開出 3 至 129 分鐘的誤報窗口。正常成功間隔的觀測上界是 26.16h
# （08-06 11:06:12 → 08-07 13:15:40）。成因是起跑時刻有 launchd 抖動（實測
# 10:10:00–10:16:38）而耗時分布極寬（4 分鐘 – 287 分鐘），而 marker 寫在**結束時**。
#
# ⚠️ 26.16h 是 27 次排程的**觀測上界**，不是耗時分布的理論上界。36h = 觀測上界 + 約 10h
# 餘裕，且明顯小於「錯過整整一個週期」的 48h。這是取捨不是保證。
PROD_SYNC_STALL_AFTER_HOURS = 36


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
        try:
            # 偵測器 B（#132）：本機 watchdog 與被監控對象共用故障域——機器沒開時
            # watchdog 也沒開，看不到自己缺席。生產側是唯一在那個故障域之外的地方。
            #
            # 讀者是本機的 com.cpbl.schedule-watchdog，它每日執行時順便讀這裡。
            # ⚠️ **B 不涵蓋當下告警**：訊號會遲到到下次開機／下次排程執行（需求方
            # 2026-08-15 裁定二，明確接受此代價——「機器沒開」的意思本來就是你不在，
            # solo 操作無 on-call，一天內知道與即時知道的差別遠小於維護一條新告警
            # 管道的成本，而告警管道本身也會壞而沒人發現，那正是本卡在修的病）。
            #
            # 生產庫的 refresh_log 只有同步腳本寫的 prod-sync 列（該表不在
            # refresh-cpbl-prod.sh 的 sync_table 清單內，本機列不會混入）。
            # marker 寫在同步成功之後，故同步失敗當天不會有列——B 因此也涵蓋
            # 「本機有跑但同步一直失敗」，不只「機器沒開」。
            last_sync = _scalar(
                "SELECT max(refreshed_at) FROM cpbl.refresh_log WHERE scope = 'prod-sync' AND ok"
            )
            metrics["prod_sync_stall_after_h"] = PROD_SYNC_STALL_AFTER_HOURS
            metrics["prod_sync_last_at"] = last_sync.isoformat() if last_sync else None
            if last_sync is None:
                # 從沒同步過＝停擺（fail closed）。「查不到」不得讀成「沒問題」。
                metrics["prod_sync_age_hours"] = None
                metrics["prod_sync_stalled"] = True
            else:
                age_hours = (
                    datetime.now(UTC) - last_sync.astimezone(UTC)
                ).total_seconds() / 3600.0
                metrics["prod_sync_age_hours"] = round(age_hours, 2)
                metrics["prod_sync_stalled"] = age_hours > PROD_SYNC_STALL_AFTER_HOURS
        except Exception:  # noqa: BLE001
            # 欄位整組不出現（不是填 False）：偵測器把「欄位缺席」判成 B_UNAVAILABLE，
            # 與「B 說一切正常」是兩個不同的訊號。填 False 會把不確定偽裝成健康。
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
