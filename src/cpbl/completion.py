"""賽事完賽 [completion] 的最小共用契約。"""

from __future__ import annotations

from datetime import date


def is_completed(
    home_score: int | None,
    away_score: int | None,
    game_date: date,
    as_of: date,
) -> bool:
    """比分已產生且賽程日不晚於觀測日，才可視為完賽。"""
    return (home_score or 0) + (away_score or 0) > 0 and game_date <= as_of


def completed_games_sql(as_of_sql: str = "CURRENT_DATE") -> str:
    """回傳與 :func:`is_completed` 等價、可嵌入 ``cpbl.games`` 查詢的 SQL 條件。"""
    return f"home_score + away_score > 0 AND game_date <= {as_of_sql}"


if __name__ == "__main__":
    print(completed_games_sql())
