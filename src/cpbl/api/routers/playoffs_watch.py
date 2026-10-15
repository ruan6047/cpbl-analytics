"""#289 S08：季後賽第 4 區 watch 讀取面（4A 近期使用負荷＋原始官方公告事實＋4B 未發布占位）。

獨立於 S04 擁有的 ``routers/playoffs.py``；只讀、不寫、不觸發爬取。計算在 :mod:`cpbl.playoffs`。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/api/v1/playoffs/watch")
def playoffs_watch(
    season: int = Query(DEFAULT_SEASON),
    series: str = Query(..., pattern="^(E|C)$"),
    game: int | None = Query(None, ge=1),
) -> dict:
    from cpbl.api.live_cache import get_public_live_snapshot
    from cpbl.playoffs.watch_reader import playoffs_watch as read

    try:
        return read(season, series, game=game, connect=conn, live_reader=get_public_live_snapshot)
    except Exception as exc:  # noqa: BLE001 — 讀取面獨立失敗降級；前端顯示錯誤態，不影響其他區
        log.exception("playoffs watch failed for %s/%s/%s", season, series, game)
        raise HTTPException(503, "第 4 區資料暫時無法讀取") from exc
