"""官方球隊戰績爬蟲（standings/seasonaction，含上下半季）。

回傳 HTML 表格；每列 16 cell：排名+隊名 / 出賽 / 勝-和-敗 / 勝率 / 勝差 / 淘汰指數 /
對戰各隊×6 / 主場 / 客場 / 連勝敗 / 近十場。SeasonCode：0全年 1上半 2下半。冪等 UPSERT。
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.standings")

BASE = "https://www.cpbl.com.tw"
PAGE = f"{BASE}/standings/season"
ACTION = f"{BASE}/standings/seasonaction"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TOKEN_RE = re.compile(r"RequestVerificationToken:\s*'([^']+)'")

# H2H 欄位固定順序（對應表頭）→ team_code
H2H_ORDER = ["AAA011", "AEO011", "AKP011", "ADD011", "AJL011", "ACN011"]
NAME_CODE = {"味全龍": "AAA011", "中信兄弟": "ACN011", "統一7-ELEVEn獅": "ADD011",
             "富邦悍將": "AEO011", "樂天桃猿": "AJL011", "台鋼雄鷹": "AKP011"}
_TXT = re.compile(r"<[^>]+>")


def _clean(html: str) -> str:
    return re.sub(r"\s+", "", _TXT.sub("", html)).replace("\xa0", "")


def _wtl(s: str) -> tuple[int | None, int | None, int | None]:
    m = re.match(r"(\d+)-(\d+)-(\d+)", s or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (None, None, None)


def fetch_standings(year: int, season_code: int, kind_code: str = "A") -> list[tuple]:
    client = httpx.Client(timeout=30.0, headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"},
                          follow_redirects=True)
    try:
        token = _TOKEN_RE.search(client.get(PAGE).text).group(1)
        html = client.post(ACTION, data={"Year": str(year), "KindCode": kind_code,
                                         "SeasonCode": str(season_code)},
                           headers={"RequestVerificationToken": token}).text
    finally:
        client.close()
    first = html[: html.find("</table>") + 8]  # 只取第一張（戰績）表
    records = []
    for tr in re.findall(r"<tr>(.*?)</tr>", first, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 16:
            continue
        name = next((n for n in NAME_CODE if n in tr), None)
        if not name:
            continue
        code = NAME_CODE[name]
        rank_m = re.search(r'rank">(\d+)', tds[0])
        g = _clean(tds[1])
        w, t, l = _wtl(_clean(tds[2]))
        wp = _clean(tds[3])
        gb_raw = _clean(tds[4])
        h2h = {H2H_ORDER[i]: _clean(tds[6 + i]) for i in range(6)
               if H2H_ORDER[i] != code and re.match(r"\d+-\d+-\d+", _clean(tds[6 + i]))}
        records.append((
            year, kind_code, season_code, code, name,
            int(rank_m.group(1)) if rank_m else None, int(g) if g.isdigit() else None,
            w, t, l, float(wp) if re.match(r"[0-9.]+$", wp) else None,
            0.0 if gb_raw in ("-", "") else (float(gb_raw) if re.match(r"[0-9.]+$", gb_raw) else None),
            _clean(tds[5]) or None, _clean(tds[12]) or None, _clean(tds[13]) or None,
            _clean(tds[14]) or None, _clean(tds[15]) or None, json.dumps(h2h, ensure_ascii=False),
        ))
    return records


_COLS = ("year,kind_code,season_code,team_code,team_name,rank,g,w,t,l,win_pct,gb,elim,"
         "home_record,away_record,streak,last10,h2h")


def upsert_standings(records: list[tuple]) -> int:
    if not records:
        return 0
    cols = [c.strip() for c in _COLS.split(",")]
    ph = "(" + ",".join(["%s"] * (len(cols) - 1) + ["%s::jsonb"]) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols[4:]) + ", updated_at=now()"
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.team_standings ({_COLS}) VALUES {ph} "
            f"ON CONFLICT (year, kind_code, season_code, team_code) DO UPDATE SET {updates}",
            records,
        )
    return len(records)


def scrape_standings(year: int, kind_code: str = "A") -> dict:
    """抓全年(0)+上半(1)+下半(2)。回傳 {season_code: 隊數}。"""
    out = {}
    for sc in (0, 1, 2):
        try:
            n = upsert_standings(fetch_standings(year, sc, kind_code))
            out[sc] = n
            log.info("standings %s SeasonCode=%s: %d 隊", year, sc, n)
        except Exception as e:  # noqa: BLE001
            log.warning("SeasonCode=%s 略過：%s", sc, e)
    return out
