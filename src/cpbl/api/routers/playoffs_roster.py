"""#286 S05：季後賽第 3 區「系列賽 32 人資格名單」讀取面（``playoffs-roster/v1``）。

獨立於 S04 擁有的 ``routers/playoffs.py``（#285 掛點契約 §2、§5）；只讀、不寫、不觸發爬取或重建。
組裝在 :mod:`cpbl.playoffs.roster_reader`：單一 REPEATABLE READ READ ONLY 交易，查詢次數與名單人數無關。
讀取例外 ⇒ 503（同第 4 區），前端顯示第 3 區錯誤態，不影響其他區。回應即 payload 本體。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/api/v1/playoffs/roster")
def playoffs_roster(
    season: int = Query(DEFAULT_SEASON),
    series: str = Query(..., pattern="^(E|C)$"),
) -> dict:
    from cpbl.api.live_cache import get_public_live_snapshot
    from cpbl.playoffs.roster_reader import playoffs_roster as read

    try:
        return read(season, series, connect=conn, live_reader=get_public_live_snapshot)
    except Exception as exc:  # noqa: BLE001 — 讀取面獨立失敗降級；前端顯示錯誤態，不影響其他區
        log.exception("playoffs roster failed for %s/%s", season, series)
        raise HTTPException(503, "第 3 區資料暫時無法讀取") from exc


@router.get("/api/v1/playoffs/roster/player")
def playoffs_roster_player(
    season: int = Query(DEFAULT_SEASON),
    series: str = Query(..., pattern="^(E|C)$"),
    player_id: str = Query(..., pattern="^[0-9]{10}$"),
) -> dict:
    """按需詳情（抽屜）：能力卡＋本季走勢，帶與摘要同源的 ``context_version``（契約 §2.2）。"""
    from cpbl.api.live_cache import get_public_live_snapshot
    from cpbl.playoffs.roster_reader import NotInRoster
    from cpbl.playoffs.roster_reader import playoffs_roster_player as read

    try:
        return read(season, series, player_id, connect=conn, live_reader=get_public_live_snapshot)
    except NotInRoster as exc:
        raise HTTPException(404, "不在該系列名單") from exc
    except Exception as exc:  # noqa: BLE001 — 抽屜獨立失敗；不影響第 3 區摘要
        log.exception("playoffs roster player failed for %s/%s/%s", season, series, player_id)
        raise HTTPException(503, "球員詳情暫時無法讀取") from exc
