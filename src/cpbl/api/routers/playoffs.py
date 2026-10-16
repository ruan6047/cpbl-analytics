"""#285 S04：季後專頁公共封套 ``/api/v1/playoffs/overview``（第 1 區＋各區呼叫參數）。

只讀、不寫、不觸發爬取；組裝在 :mod:`cpbl.playoffs.overview`。各區讀取面（如 #289
``/api/v1/playoffs/watch``）各自獨立失敗，不經本端點。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/api/v1/playoffs/overview")
def playoffs_overview(
    season: int = Query(DEFAULT_SEASON),
    series: str | None = Query(None, pattern="^(E|C)$"),
) -> dict:
    from cpbl.api.live_cache import get_public_live_snapshot
    from cpbl.playoffs.overview import playoffs_overview as read

    try:
        return read(season, series=series, connect=conn, live_reader=get_public_live_snapshot)
    except Exception as exc:  # noqa: BLE001 — 前端顯示第 1 區讀取失敗，不回 500 堆疊
        log.exception("playoffs overview failed for %s/%s", season, series)
        raise HTTPException(503, "季後賽資料暫時無法讀取") from exc
