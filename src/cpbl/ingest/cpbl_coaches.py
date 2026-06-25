"""現役教練團爬蟲（官網 /team/index 內嵌名單）。

每隊頁面 HTML 直接含教練 .item 區塊（pos/name/number），含一軍總教練。
無歷史、無勝率（官方無逐場執教歸屬資料）；僅現役，每季重爬覆蓋（同 current 系列）。
只爬 team_dim 現役球團。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date

from cpbl.db import conn

log = logging.getLogger("cpbl.coaches")

# .item 內：<div class="pos">…</div><div class="name">…</div><div class="number">…</div>
_ITEM_RE = re.compile(
    r'<div class="pos">([^<]*)</div>\s*'
    r'<div class="name">([^<]*)</div>\s*'
    r'<div class="number">([^<]*)</div>'
)


def _parse(html: str) -> list[tuple[str, str, str]]:
    """回傳 [(pos, name, uniform_no)]；過濾空名。"""
    out = []
    for pos, name, num in _ITEM_RE.findall(html):
        name = name.strip()
        if not name:
            continue
        out.append((pos.strip(), name, num.strip() or None))
    return out


def scrape_coaches(year: int | None = None) -> dict:
    """爬現役球團教練團，冪等覆蓋 cpbl.coaches。回傳各隊筆數。"""
    from cpbl.ingest._browser import session
    year = year or date.today().year
    s = session()
    with conn() as c:
        codes = [r[0] for r in c.execute(
            "SELECT team_code FROM cpbl.team_dim WHERE active=true ORDER BY team_code"
        ).fetchall()]
    out: dict[str, int] = {}
    for code in codes:
        time.sleep(0.8)
        try:
            html = s.page_html(f"/team/index?teamNo={code}")
        except Exception as e:  # noqa: BLE001 — 單隊失敗略過續抓
            log.warning("team index 失敗 code=%s: %s", code, e)
            continue
        coaches = _parse(html)
        if not coaches:
            log.warning("code=%s 解析不到教練（官網可能改版）", code)
            continue
        with conn() as c:  # 每隊一交易：先清該隊該年、再寫，容忍教練異動
            c.execute("DELETE FROM cpbl.coaches WHERE year=%s AND team_code=%s", (year, code))
            c.cursor().executemany(
                "INSERT INTO cpbl.coaches (year, team_code, name, pos, uniform_no) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (year, team_code, name) DO UPDATE "
                "SET pos=EXCLUDED.pos, uniform_no=EXCLUDED.uniform_no",
                [(year, code, name, pos, num) for pos, name, num in coaches],
            )
        out[code] = len(coaches)
        log.info("code=%s coaches=%d", code, len(coaches))
    return out
