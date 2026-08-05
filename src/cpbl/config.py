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

    port: int = 4001
    app_version: str = "0.1.0"


settings = Settings()
