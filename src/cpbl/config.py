"""集中式設定（從環境變數 / .env 載入）。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://cpbl:cpbl@localhost:5433/cpbl"

    # 逐球 TrackMan 的 refresh 抓取維度（INGEST-GAME-TM-REFACTOR1-G4 Phase A）。
    # game=單場 API（預設，一場一請求、不受名冊異動漏損）；pitcher=逐投手 logs（回退路徑）。
    # 型別刻意用 Literal：這是回滾控制桿，值打錯必須在啟動時就炸開，
    # 不能靜默落回預設值而讓「已回退」的宣稱不成立。此 flag 僅存活至本卡結案（Phase B 移除）。
    pitch_ingest: Literal["game", "pitcher"] = Field(
        default="game",
        validation_alias=AliasChoices("CPBL_PITCH_INGEST", "pitch_ingest"),
    )

    opendata_base_url: str = "https://raw.githubusercontent.com/ldkrsi/cpbl-opendata/master"
    opendata_start_year: int = 1990
    opendata_end_year: int = 2024

    artifact_dir: Path = Path("./artifacts")

    redis_url: str | None = None
    live_game_worker_enabled: bool = False
    live_game_cache_prefix: str = "cpbl:live"
    live_game_snapshot_ttl_seconds: int = 172_800
    live_game_lock_ttl_seconds: int = 300
    live_game_max_games_per_cycle: int = 8
    live_game_stale_after_seconds: int = 45
    # #332：worker 同程序就緒證據（latest.json＋worker.sock）。容器內 /tmp 隨容器生命週期，
    # 即「同實例」界線；目錄須為 worker euid 擁有且 0700，否則證據停用＝讀取端 unknown。
    live_worker_readiness_dir: Path = Path("/tmp/cpbl-live-readiness")
    # #237 Phase B：2026+ 季後賽別（逗號分隔，只接受 E、C）。預設空＝維持原本行為：
    # live worker 只追 A、每日鏈只抓 A／D。值打錯在入口解析時就炸開，不靜默落回預設。
    live_game_postseason_kinds: str = ""
    refresh_postseason_kinds: str = ""

    # #353 WP2：只在 API 行程（uvicorn lifespan）套用的讀端逾時；migrate／訓練／ingest 不受影響。
    # 上限：單一請求最壞＝借池等待＋單一語句（lock 等待含在語句內）＝1.0＋3.5＝4.5s ＜ 驗收 5s。
    #   規劃 r2 的例值（借池 3s＋statement 4s）最壞 7s，超過門檻，故 2026-10-26 改小。
    # 下限依據（不是 P3）：正式站 nginx 格式沒有 $request_time（2026-10-26 唯讀確認），P3 無從量；
    #   改用研究 2 的正式站實測——每日鏈 CPU／換頁最重的非 PA 段，/api/info 依序 14 個查詢合計最慢
    #   4.626181s，單一語句不超過此值的一部分。⚠️ 其他端點平常的單一語句耗時未量；可經環境變數
    #   調高或設 0 關閉 session 逾時（調整需重新部署）。
    api_db_pool_timeout_seconds: float = 1.0
    api_db_statement_timeout_ms: int = 3500
    api_db_lock_timeout_ms: int = 2000

    port: int = 4001
    app_version: str = "0.1.0"


def parse_postseason_kinds(raw: str | None) -> tuple[str, ...]:
    """``"E,C"`` → ``("E", "C")``；空字串 → ``()``。E、C 以外（含小寫、重複）一律 ValueError。"""
    kinds = tuple(part.strip() for part in (raw or "").split(",") if part.strip())
    bad = [k for k in kinds if k not in ("E", "C")]
    if bad or len(set(kinds)) != len(kinds):
        raise ValueError(f"postseason kinds 只接受不重複的 E、C：{raw!r}")
    return kinds


settings = Settings()
