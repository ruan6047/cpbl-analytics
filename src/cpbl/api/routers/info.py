"""子專案契約：/api/info（主站 InfoPoller，永不拋錯）+ /healthz。

#353 WP3：metrics 改為行程內快取。背景執行緒每 :data:`CACHE_TTL_SECONDS` 用**一條連線**重算一次，
請求只讀最近一次的結果；uvicorn lifespan startup 先算一次（預熱，見 ``cpbl.api.main``）。
為什麼：每次請求原本各借一次連線、依序跑 14 個查詢（含 splits／matchups 大表 count）——連線池被
每日鏈的等鎖查詢占滿時 ``/api/info`` 跟著等不到連線；部署後首請求還要付冷連線＋冷頁快取（研究 1／2）。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response

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


# 快取 TTL：主站 InfoPoller 每 5 分鐘輪詢，metrics 的陳舊時間必須遠小於它（規劃 r2 §2.3）。
# 60 秒的理由：容器 HEALTHCHECK 原本就每 30 秒打一次 /api/info（Dockerfile），即每分鐘 2 次全套
# 14 查詢；改成背景每 60 秒 1 次，DB 負載只降不增，而陳舊時間最多約 1 分鐘（＜ 5 分鐘的 1/5）。
CACHE_TTL_SECONDS = 60.0
# 陳舊上限：背景重算連續失敗、最後一份成功值已超過一個 InfoPoller 週期 ⇒ 不再宣稱 running，
# 退回 maintenance（metrics 照帶）。等於舊版「DB 失敗就 maintenance」的語意，只是晚 5 分鐘生效。
CACHE_MAX_STALE_SECONDS = 300.0
# 快取算出的時刻（epoch 秒）放在回應標頭，不放進 JSON（契約只有三鍵）。
# 讀者：scripts/refresh-cpbl-prod.sh 的 freshness 檢查，用它確認讀到的是同步之後才算的快取。
COMPUTED_AT_HEADER = "X-Cpbl-Info-Computed-At"
_THREAD_NAME = "cpbl-info-cache"

Scalar = Callable[..., Any]


def _scalar_on(c, sql: str, params: tuple = ()) -> Any:
    # 每個查詢各自一個（子）交易：refresh_log／model_versions 的獨立保護失敗時只回滾自己，
    # 不讓同一條連線上其後的查詢跟著 InFailedSqlTransaction。
    with c.transaction():
        cur = c.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


@contextmanager
def _open_scalar() -> Iterator[Scalar]:
    """借**一條**連線給整輪 metrics 使用（原本 14 個查詢各借還一次）。"""
    with conn() as c:
        yield lambda sql, params=(): _scalar_on(c, sql, params)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _wall() -> float:
    return time.time()


@dataclass(frozen=True)
class _Snapshot:
    computed_at: float           # epoch 秒（_wall）
    ok: bool                     # 這一輪沒有在 DB 讀取時拋錯
    status: str
    metrics: dict[str, Any]


def _collect(scalar: Scalar, metrics: dict[str, Any]) -> str:
    """算一輪 metrics 填進 ``metrics``、回傳 status；DB 錯誤往外拋（由 :func:`_compute` 轉成
    maintenance，已填的 metrics 照帶——與舊版「部分失敗仍回已算出的值」相同）。"""
    status = "running"
    season = DEFAULT_SEASON
    # 證據感知判準：0:0 真和局需外部證據才算完成（DATA-TIE-REMEDY1）
    completed_sql = completed_games_sql_with_evidence("games")
    games = scalar("SELECT count(*) FROM cpbl.games") or 0
    metrics["games_indexed"] = games
    metrics["seasons_covered"] = scalar("SELECT count(DISTINCT year) FROM cpbl.games") or 0
    metrics["current_season"] = season
    metrics["season_games_completed"] = scalar(
        f"SELECT count(*) FROM cpbl.games WHERE year = %s AND {completed_sql}", (season,)
    ) or 0
    metrics["teams_tracked"] = scalar(
        "SELECT count(*) FROM cpbl.team_current WHERE year = %s", (season,)
    ) or 0
    metrics["pitchers_tracked"] = scalar(
        "SELECT count(*) FROM cpbl.pitching_current WHERE year = %s", (season,)
    ) or 0
    metrics["batters_tracked"] = scalar(
        "SELECT count(*) FROM cpbl.batting_current WHERE year = %s", (season,)
    ) or 0
    metrics["matchups_indexed"] = scalar(
        "SELECT count(*) FROM cpbl.batter_pitcher_matchups"
    ) or 0
    metrics["player_splits_indexed"] = (
        (scalar("SELECT count(*) FROM cpbl.batting_splits") or 0)
        + (scalar("SELECT count(*) FROM cpbl.pitching_splits") or 0)
    )
    # 「今日待預測場次」＝排在今天且尚未有比分者。刻意**不**改用完成判準：
    # 母體限定當日，5 場歷史和局（2018–2025）不可能落入。
    #
    # 「今天」必須以**台北日**為準（DATA-TZ-BOUNDARY1／AUDIT1 C12）：DB timezone
    # 是 UTC，`CURRENT_DATE` 在台北 00:00–07:59 仍停在前一日，此處是全庫唯一的
    # **精確等值**日期界線，一偏移就整個指到錯誤的一天——該指標每日有 8 小時讀到
    # 昨天的場次數。上下界（<= / >=）頂多寬鬆或保守，等值沒有這種緩衝。
    metrics["predictions_today"] = scalar(
        "SELECT count(*) FROM cpbl.games "
        "WHERE year = %s AND home_score + away_score = 0 "
        f"AND game_date = {TAIPEI_TODAY_SQL}", (season,)
    ) or 0
    last_game = scalar(
        f"SELECT max(game_date) FROM cpbl.games WHERE {completed_sql}"
    )
    metrics["last_game_date"] = last_game.isoformat() if last_game else None
    try:  # refresh_log 可能尚未 migrate，獨立保護避免拖垮整個 info
        last_refresh = scalar("SELECT max(refreshed_at) FROM cpbl.refresh_log WHERE ok")
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
        last_sync = scalar(
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
                _utcnow() - last_sync.astimezone(UTC)
            ).total_seconds() / 3600.0
            metrics["prod_sync_age_hours"] = round(age_hours, 2)
            metrics["prod_sync_stalled"] = age_hours > PROD_SYNC_STALL_AFTER_HOURS
    except Exception:  # noqa: BLE001
        # 欄位整組不出現（不是填 False）：偵測器把「欄位缺席」判成 B_UNAVAILABLE，
        # 與「B 說一切正常」是兩個不同的訊號。填 False 會把不確定偽裝成健康。
        pass
    try:  # 賽事預測走查回測準確率（活的 ML 系統指標：模型 vs 全押主場）
        bt = scalar("SELECT cv_metrics FROM cpbl.model_versions WHERE task='outcome' "
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
    return status


def _compute() -> _Snapshot:
    """算一份快照；永不拋錯（info 端點不可拋錯，退化即可）。"""
    at = _wall()
    metrics: dict[str, Any] = {}
    try:
        with _open_scalar() as scalar:
            status = _collect(scalar, metrics)
        return _Snapshot(at, True, status, metrics)
    except Exception:  # noqa: BLE001
        return _Snapshot(at, False, "maintenance", metrics)


class _InfoCache:
    """單一快照＋背景重算執行緒。只有 :func:`start_cache`（lifespan）之後才啟用。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: _Snapshot | None = None
        self._active = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def get(self) -> _Snapshot | None:
        return self._snapshot

    @property
    def active(self) -> bool:
        return self._active

    def offer(self, snap: _Snapshot) -> None:
        """失敗的一輪不覆蓋上一份成功值；還沒有任何值時才收下（避免每個請求都打 DB）。"""
        with self._lock:
            if snap.ok or self._snapshot is None or not self._snapshot.ok:
                self._snapshot = snap

    def start(self, ttl: float) -> None:
        self.stop()
        self._active = True
        self._stop = threading.Event()
        self.offer(_compute())  # 預熱：startup 先算一次
        stop = self._stop

        def loop() -> None:
            while not stop.wait(ttl):
                _refresh()

        self._thread = threading.Thread(target=loop, name=_THREAD_NAME, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None
        self._active = False
        self._snapshot = None


_CACHE = _InfoCache()
_SYNC_COMPUTE = threading.Lock()


def _refresh() -> None:
    _CACHE.offer(_compute())


def start_cache() -> None:
    """uvicorn lifespan startup 呼叫：預熱一次並啟動背景重算。"""
    _CACHE.start(CACHE_TTL_SECONDS)


def stop_cache() -> None:
    _CACHE.stop()


def _render(snap: _Snapshot) -> dict:
    metrics = dict(snap.metrics)
    # prod_sync_* 的語意是「現在距上次同步」：age／stalled 每次請求依快取的 last_at 重算，
    # 不隨快取凍結（偵測器 B 讀它判停擺）。last_at 本身是 DB 值，照快取。
    last_at = metrics.get("prod_sync_last_at")
    if last_at is not None and "prod_sync_age_hours" in metrics:
        age_hours = (_utcnow() - datetime.fromisoformat(last_at).astimezone(UTC)).total_seconds() / 3600.0
        metrics["prod_sync_age_hours"] = round(age_hours, 2)
        metrics["prod_sync_stalled"] = age_hours > PROD_SYNC_STALL_AFTER_HOURS
    status = snap.status
    if _wall() - snap.computed_at > CACHE_MAX_STALE_SECONDS:
        status = "maintenance"
    return {"status": status, "version": settings.app_version, "metrics": metrics}


def _current() -> _Snapshot:
    snap = _CACHE.get()
    if snap is not None:
        return snap
    if not _CACHE.active:
        # 未經 lifespan（單測直接呼叫、腳本 import）：行為同舊版，每次即時算、不寫快取。
        return _compute()
    # lifespan 已啟用但還沒有任何快照（預熱前即被打到）：只讓一個請求去算。
    with _SYNC_COMPUTE:
        snap = _CACHE.get()
        if snap is None:
            snap = _compute()
            _CACHE.offer(snap)
        return snap


@router.get("/api/info")
def info(response: Response = None) -> dict:  # type: ignore[assignment]
    """主站 InfoPoller 契約。永遠回 200；metrics 展示這個 live 資料產品的狀態。"""
    try:
        snap = _current()
        body = _render(snap)
    except Exception:  # noqa: BLE001 — info 端點不可拋錯
        return {"status": "maintenance", "version": settings.app_version, "metrics": {}}
    if response is not None:
        response.headers[COMPUTED_AT_HEADER] = str(int(snap.computed_at))
    return body


@router.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
