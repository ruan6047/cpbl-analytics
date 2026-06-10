"""集中式設定（從環境變數 / .env 載入）。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://cpbl:cpbl@localhost:5433/cpbl"

    opendata_base_url: str = "https://raw.githubusercontent.com/ldkrsi/cpbl-opendata/master"
    opendata_start_year: int = 1990
    opendata_end_year: int = 2024

    artifact_dir: Path = Path("./artifacts")

    port: int = 4001
    app_version: str = "0.1.0"


settings = Settings()
