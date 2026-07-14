"""官方球隊登錄名單爬蟲（`/team/index?teamNo=`）。

「現役選手」以**球團登錄名單**為準，而非出賽推導——登錄了但整季未出賽的選手，
用 `*_current`（需有成績）或 gamelog（需出賽）都會漏掉。

頁面結構（2026-07 實測）：`TeamPlayersList` 下每個 `item` 有
`<a href="/team/person?Acnt=...">`（注意 **Acnt 大寫 A**）＋ `pos` / `name` / `number`。
教練列在同頁但**無 Acnt 連結**，故本解析天然只收球員。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date

from cpbl.db import conn

log = logging.getLogger("cpbl.roster")

_ITEM = re.compile(
    r'<div class="cont">\s*'
    r'<div class="pos">([^<]*)</div>\s*'
    r'<div class="name">\s*<a href="/team/person\?Acnt=(\d+)"[^>]*>([^<]*)</a>\s*</div>\s*'
    r'<div class="number">([^<]*)</div>',
    re.S,
)


def parse_roster(html: str) -> list[dict]:
    """解析登錄名單。教練無 Acnt 連結故不會被收進來。"""
    return [
        {"pos": pos.strip(), "player_id": acnt, "name": name.strip(), "uniform_no": no.strip()}
        for pos, acnt, name, no in _ITEM.findall(html)
    ]


def scrape_roster(year: int | None = None) -> dict:
    """爬六隊登錄名單，冪等覆蓋 cpbl.team_roster。回各隊人數。"""
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
        players = parse_roster(html)
        if not players:
            log.warning("code=%s 解析不到球員（官網可能改版）", code)
            continue
        with conn() as c:  # 每隊一交易：先清該隊該年再寫，容忍名單異動
            cur = c.cursor()
            cur.execute("DELETE FROM cpbl.team_roster WHERE year=%s AND team_code=%s", (year, code))
            for p in players:
                cur.execute(
                    "INSERT INTO cpbl.team_roster (year, team_code, player_id, name, pos, uniform_no) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (year, team_code, player_id) DO UPDATE "
                    "SET name=EXCLUDED.name, pos=EXCLUDED.pos, uniform_no=EXCLUDED.uniform_no, "
                    "updated_at=now()",
                    (year, code, p["player_id"], p["name"], p["pos"], p["uniform_no"]),
                )
        out[code] = len(players)
        log.info("%s 登錄名單 %d 人", code, len(players))
    return out
