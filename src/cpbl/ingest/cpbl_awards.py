"""球員年度獎項爬蟲（官網 /stats/yearaward 五分類，1990 起）。

官網主站有 HiNet CDN JS 挑戰 → 走 _browser（Playwright）token 流程，POST
/stats/yearawardaction（Award=01~05）一次取全年度表。winner cell 直接連
/team/person?acnt=<player_id>，故抽 acnt 即 player_id，無需名比對。

只在本機（台灣 IP）可跑；一次性抓 + 手動刷新。各分類欄位不一，以「cell 內是否含
acnt 連結」自動判別獎項欄（值欄/守位欄無連結自然略過），對位 header 取獎項名。
"""

from __future__ import annotations

import logging
import re

from cpbl.db import conn

log = logging.getLogger("cpbl.awards")

PAGE = "/stats/yearaward"
ACTION = "/stats/yearawardaction"
CATEGORIES = {"01": "打擊", "02": "投手", "03": "金手套", "04": "最佳十人", "05": "其他"}
_TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')


def _cells(row: str) -> list[str]:
    return re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)


def _parse(html: str, category: str) -> list[tuple[str, int, str, str]]:
    """回傳 [(player_id, year, category, award)]。對位 header；獎項欄＝cell 含 acnt 連結。"""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    if not rows:
        return []
    header = [re.sub(r"<[^>]+>", "", c).strip() for c in _cells(rows[0])]
    out = []
    for row in rows[1:]:
        cells = _cells(row)
        if not cells:
            continue
        ym = re.search(r"\d{4}", re.sub(r"<[^>]+>", "", cells[0]))
        if not ym:
            continue
        year = int(ym.group())
        for i, cell in enumerate(cells):
            if i == 0 or i >= len(header):
                continue
            award = header[i]
            for acnt in re.findall(r"/team/person\?acnt=(\d+)", cell):
                out.append((acnt, year, category, award))
    return out


def scrape_awards() -> dict:
    from cpbl.ingest._browser import session
    s = session()
    m = _TOKEN_RE.search(s.page_html(PAGE))
    if not m:
        raise RuntimeError("找不到 yearaward __RequestVerificationToken（官網可能改版）")
    token = m.group(1)

    recs: list[tuple[str, int, str, str]] = []
    for code, cat in CATEGORIES.items():
        form = {"__RequestVerificationToken": token, "Award": code, "ExecAction": "Q", "IndexOfPages": "1"}
        status, html = s.post(PAGE, ACTION, form)
        if status != 200:
            log.warning("分類 %s（%s）HTTP %s", code, cat, status); continue
        rows = _parse(html, cat)
        recs += rows
        log.info("分類 %s（%s）：%d 筆得獎", code, cat, len(rows))

    if recs:
        recs = list({r for r in recs})  # 去重
        with conn() as c:
            cur = c.cursor()
            cur.execute("TRUNCATE cpbl.player_awards")
            cur.executemany(
                "INSERT INTO cpbl.player_awards (player_id, year, category, award) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (player_id, year, category, award) DO NOTHING", recs)
    players = len({r[0] for r in recs})
    log.info("年度獎項：%d 筆 / %d 位球員", len(recs), players)
    return {"records": len(recs), "players": players}
