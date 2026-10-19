"""#288 S07 WP-K3：季後賽第 1 區「逐場焦點」精簡數據讀取面（``playoffs-highlights/v1``）。

獨立於 S04 擁有的 ``routers/playoffs.py``（#285 掛點契約 §5：各卡加自己的 router）；只讀、不寫、不觸發爬取。
組裝在 :mod:`cpbl.playoffs.series_highlights`：只投影焦點規則要讀的欄位，規則本身在前端（與單場頁同一函式）。
讀取例外 ⇒ 503（同 #287／#289 端點），前端逐場焦點顯示「待更新」，不影響累計榜與轉折。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/api/v1/playoffs/highlights")
def playoffs_highlights(
    season: int = Query(DEFAULT_SEASON),
    series: str = Query(..., pattern="^(E|C)$"),
) -> dict:
    from cpbl.api.live_cache import get_public_live_snapshot
    from cpbl.models.umpire_call_tag import game_umpire_call
    from cpbl.playoffs.series_highlights import series_highlights

    try:
        # live_reader 與 overview 同一個：S02 context_version 含 live 來源狀態，不同就永遠版本不一致。
        # 判決標籤（#285 批次 G）由後端判定：注入 connect 時 series_highlights 不會自取，正式路徑必須明確傳入。
        return series_highlights(season, series, connect=conn, live_reader=get_public_live_snapshot,
                                 umpire_for=game_umpire_call)
    except Exception as exc:  # noqa: BLE001 — 讀取面獨立失敗降級；前端顯示待更新，不影響其他區
        log.exception("playoffs highlights failed for %s/%s", season, series)
        raise HTTPException(503, "逐場焦點暫時無法讀取") from exc
