"""官網「球員異動」爬蟲（POST /player/trans）→ cpbl.player_transactions。

與 getgamedatas 的 header-token AJAX 不同：/player/trans 是傳統 ASP.NET MVC 表單，
token 走 **hidden input** `__RequestVerificationToken`（放在 POST body）。實測契約：

1. GET /player/trans → 取 session cookie + 抽 hidden token。
2. POST /player/trans，body = Year + Month + ClubNo + KindCode + Keyword + __RequestVerificationToken；
   省略 Month/ClubNo/Keyword → 回該年「全年、全隊」事件；回 **HTML 表格**（非 JSON）。
3. 結果表欄位：異動日期 | 球員(含 ?acnt=) | 球隊 | 異動原因。
   ⚠ 同一日期只在該日第一列顯示，其餘列日期欄空白 → 需向下繼承。

只存層級變動事件 01 升一軍 / 02 降二軍（重建一/二軍登錄天數所需）。
官網反爬需 Playwright（同其他主站爬蟲），故只在本機跑。冪等 UPSERT。
"""

from __future__ import annotations

import logging
import re

from cpbl.db import conn

log = logging.getLogger("cpbl.trans")

PATH = "/player/trans"
_TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_ACNT_RE = re.compile(r"[Aa]cnt=([0-9]+)")
_DATE_RE = re.compile(r"\d{4}/\d{2}/\d{2}")

# 層級變動事件（只這兩種影響一/二軍登錄）
LEVEL_KINDS = {"01": "升一軍", "02": "降二軍"}


def _cell_text(td: str) -> str:
    return _TAG_RE.sub("", td).replace("&nbsp;", " ").strip()


def _parse(html: str, year: int, kind_code: str, reason: str) -> list[tuple]:
    """解析結果表 → (year, acnt, trans_date, kind_code, name, team, reason)。日期向下繼承。"""
    out, cur_date = [], None
    for tr in _TR_RE.findall(html):
        tds = _TD_RE.findall(tr)
        if len(tds) < 3:
            continue
        cells = [_cell_text(t) for t in tds]
        acnt_m = _ACNT_RE.search(tr)
        if not acnt_m:                       # 表頭或非資料列
            continue
        # 第一欄可能是日期（同日多筆只首列有）→ 有則更新繼承值
        if cells and _DATE_RE.fullmatch(cells[0]):
            cur_date = cells[0].replace("/", "-")
            name, team = cells[1], cells[2] if len(cells) > 2 else None
        else:                                # 日期欄空白：球員/球隊往前移一欄
            name, team = cells[0], cells[1] if len(cells) > 1 else None
        if not cur_date:
            continue
        out.append((year, acnt_m.group(1), cur_date, kind_code, name, team, reason))
    return out


def _upsert(records: list[tuple]) -> int:
    if not records:
        return 0
    with conn() as c:
        c.cursor().executemany(
            "INSERT INTO cpbl.player_transactions "
            "(year, acnt, trans_date, kind_code, name, team_name, reason) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (year, acnt, trans_date, kind_code) DO UPDATE SET "
            "name=EXCLUDED.name, team_name=EXCLUDED.team_name, reason=EXCLUDED.reason, updated_at=now()",
            records)
    return len(records)


def scrape_transactions(years: list[int]) -> dict[int, int]:
    """爬指定年度的升一軍/降二軍事件 → player_transactions。回 {year: 寫入列數}。"""
    from cpbl.ingest._browser import session
    s = session()
    out: dict[int, int] = {}
    for year in years:
        html = s.page_html(PATH, require=_TOKEN_RE)
        tok = _TOKEN_RE.search(html)
        if not tok:
            raise RuntimeError("抽不到 __RequestVerificationToken（官網改版？）")
        token = tok.group(1)
        n = 0
        for kc, reason in LEVEL_KINDS.items():
            form = {"Year": str(year), "Month": "", "ClubNo": "", "KindCode": kc,
                    "Keyword": "", "__RequestVerificationToken": token}
            status, text = s.post(PATH, PATH, form)
            if status != 200:
                log.warning("year=%s kind=%s 非 200：%s", year, kc, status)
                continue
            n += _upsert(_parse(text, year, kc, reason))
        out[year] = n
        log.info("year=%s 異動事件寫入 %d 列", year, n)
    return out
