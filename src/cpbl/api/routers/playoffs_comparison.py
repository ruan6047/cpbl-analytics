"""#287 S06：季後賽第 2 區「隊伍表現」三範圍比較讀取面（``playoffs-comparison/v1``）。

獨立於 S04 擁有的 ``routers/playoffs.py``（#285 掛點契約 §2、§5）；只讀、不寫、不觸發建置或爬取。
組裝在 :mod:`cpbl.playoffs.team_comparison.reader`：單一 REPEATABLE READ READ ONLY 交易，GET 不讀 A gamelog、
不重建；背景摘要缺 ⇒ 200＋``summary_missing``，⛔ 不回退全季重建。讀取例外 ⇒ 503（同第 4 區），
前端顯示第 2 區錯誤態，不影響其他區。回應即 payload 本體，⛔ 不再包外層封套。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/api/v1/playoffs/comparison")
def playoffs_comparison(
    season: int = Query(DEFAULT_SEASON),
    series: str = Query(..., pattern="^(E|C)$"),
) -> dict:
    from cpbl.api.live_cache import get_public_live_snapshot
    from cpbl.playoffs.team_comparison.reader import comparison_payload

    try:
        # live_reader 與 overview／watch 同一個：S02 context_version 含 live 來源狀態，不同就永遠版本不一致。
        return comparison_payload(season, series, connect=conn, live_reader=get_public_live_snapshot)
    except Exception as exc:  # noqa: BLE001 — 讀取面獨立失敗降級；前端顯示錯誤態，不影響其他區
        log.exception("playoffs comparison failed for %s/%s", season, series)
        raise HTTPException(503, "第 2 區資料暫時無法讀取") from exc
