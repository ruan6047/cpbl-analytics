"""官網 /stats 投手成績爬蟲（含本季 ERA 與進階指標 + 球員名）。

端點：POST /stats/recordallaction（與 getgamedatas 不同：token 走**表單欄位**
__RequestVerificationToken，form.serialize() 提交，回傳 HTML 片段）。
Position=02 為投手。回傳每列含 acnt(player_id)、名字、TeamNo，及 35 個 num 欄位。
"""

from __future__ import annotations

import logging
import re

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.stats")

BASE = "https://www.cpbl.com.tw"
PAGE = f"{BASE}/stats/recordall"
ACTION = f"{BASE}/stats/recordallaction"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')

STANDINGS = f"{BASE}/standings/season"

# num 欄位 index（player cell 之後，對照官網表頭順序）
PITCH_IDX = {
    "era": 0, "g": 1, "gs": 2, "w": 6, "l": 7, "ip": 12,
    "whip": 23, "k9": 27, "fip": 33, "era_plus": 34,
}
BAT_IDX = {
    "avg": 0, "pa": 2, "hr": 10, "obp": 22, "slg": 23, "ops": 24,
    "ops_plus": 27, "k_pct": 28, "bb_pct": 29,
}


def _num(v: str | None) -> float | None:
    if v is None:
        return None
    v = re.sub(r"[\s,]", "", v)
    try:
        return float(v)
    except ValueError:
        return None


def _int(v: float | None) -> int | None:
    return int(v) if v is not None else None


def fetch_pitching(year: int, kind_code: str = "A") -> list[tuple]:
    client = httpx.Client(timeout=30.0, headers={"User-Agent": UA}, follow_redirects=True)
    try:
        page = client.get(PAGE).text
        m = _TOKEN_RE.search(page)
        if not m:
            raise RuntimeError("找不到 __RequestVerificationToken（stats 頁結構可能已改版）")
        form = {
            "__RequestVerificationToken": m.group(1),
            "Year": str(year), "KindCode": kind_code, "Position": "02",
            "DefenceType": "99", "Sortby": "", "ExecAction": "Q",
            "IndexOfPages": "1", "PageSize": "500", "Online": "",
        }
        html = client.post(
            ACTION, data=form,
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": PAGE},
        ).text
    finally:
        client.close()
    return _parse(html, year)


def _parse(html: str, year: int) -> list[tuple]:
    rows: list[tuple] = []
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        mid = re.search(r"acnt=(\d+)", tr)
        if not mid:
            continue
        nums = [n.strip() for n in re.findall(r'<td class="num">(.*?)</td>', tr, re.S)]
        if len(nums) < 35:
            continue
        name_m = re.search(r'/team/person\?acnt=\d+"[^>]*>([^<]+)</a>', tr)
        team_m = re.search(r"TeamNo=([A-Z0-9]+)", tr)

        def g(k: str) -> float | None:
            return _num(nums[PITCH_IDX[k]])

        rows.append((
            year, mid.group(1),
            name_m.group(1).strip() if name_m else None,
            team_m.group(1) if team_m else None,
            g("era"), g("ip"), _int(g("g")), _int(g("gs")), _int(g("w")), _int(g("l")),
            g("whip"), g("k9"), g("fip"), g("era_plus"),
        ))
    return rows


def upsert_pitching(records: list[tuple]) -> int:
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.pitching_current
                (year, player_id, name, team_code, era, ip, g, gs, w, l, whip, k9, fip, era_plus)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (year, player_id) DO UPDATE SET
                name=EXCLUDED.name, team_code=EXCLUDED.team_code, era=EXCLUDED.era, ip=EXCLUDED.ip,
                g=EXCLUDED.g, gs=EXCLUDED.gs, w=EXCLUDED.w, l=EXCLUDED.l,
                whip=EXCLUDED.whip, k9=EXCLUDED.k9, fip=EXCLUDED.fip, era_plus=EXCLUDED.era_plus
            """,
            records,
        )
    return len(records)


def scrape_pitching(start_year: int, end_year: int) -> dict[int, int]:
    totals: dict[int, int] = {}
    for year in range(start_year, end_year + 1):
        recs = fetch_pitching(year)
        n = upsert_pitching(recs)
        totals[year] = n
        log.info("pitching %s: %d pitchers", year, n)
    return totals


# ---------- 打者進階（Position=01）----------

def fetch_batting(year: int, kind_code: str = "A") -> list[tuple]:
    client = httpx.Client(timeout=30.0, headers={"User-Agent": UA}, follow_redirects=True)
    try:
        page = client.get(PAGE).text
        m = _TOKEN_RE.search(page)
        if not m:
            raise RuntimeError("找不到 __RequestVerificationToken")
        form = {
            "__RequestVerificationToken": m.group(1),
            "Year": str(year), "KindCode": kind_code, "Position": "01",
            "DefenceType": "99", "Sortby": "", "ExecAction": "Q",
            "IndexOfPages": "1", "PageSize": "500", "Online": "",
        }
        html = client.post(
            ACTION, data=form,
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": PAGE},
        ).text
    finally:
        client.close()

    rows: list[tuple] = []
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        mid = re.search(r"acnt=(\d+)", tr)
        if not mid:
            continue
        nums = [n.strip() for n in re.findall(r'<td class="num">(.*?)</td>', tr, re.S)]
        if len(nums) < 30:
            continue
        name_m = re.search(r'/team/person\?acnt=\d+"[^>]*>([^<]+)</a>', tr)
        team_m = re.search(r"TeamNo=([A-Z0-9]+)", tr)

        def b(k: str) -> float | None:
            return _num(nums[BAT_IDX[k]])

        rows.append((
            year, mid.group(1),
            name_m.group(1).strip() if name_m else None,
            team_m.group(1) if team_m else None,
            _int(b("pa")), b("avg"), b("obp"), b("slg"), b("ops"),
            _int(b("hr")), b("ops_plus"), b("k_pct"), b("bb_pct"),
        ))
    return rows


def upsert_batting(records: list[tuple]) -> int:
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.batting_current
                (year, player_id, name, team_code, pa, avg, obp, slg, ops, hr, ops_plus, k_pct, bb_pct)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (year, player_id) DO UPDATE SET
                name=EXCLUDED.name, team_code=EXCLUDED.team_code, pa=EXCLUDED.pa, avg=EXCLUDED.avg,
                obp=EXCLUDED.obp, slg=EXCLUDED.slg, ops=EXCLUDED.ops, hr=EXCLUDED.hr,
                ops_plus=EXCLUDED.ops_plus, k_pct=EXCLUDED.k_pct, bb_pct=EXCLUDED.bb_pct
            """,
            records,
        )
    return len(records)


# ---------- 團隊數據（standings/season，server-rendered）----------

def _team_rows(table: str) -> dict[str, list[str]]:
    """從一張團隊表抽 {team_code: [num 值...]}。"""
    out: dict[str, list[str]] = {}
    for tr in re.findall(r"<tr>(.*?)</tr>", table, re.S):
        m = re.search(r'TeamNo=([A-Z0-9]+)">([^<]+)</a>', tr)
        if not m:
            continue
        nums = [re.sub(r"<[^>]+>|&nbsp;", "", n).strip()
                for n in re.findall(r'<td class="num">(.*?)</td>', tr, re.S)]
        out[m.group(1)] = nums
    return out


def fetch_team(year: int) -> list[tuple]:
    """目前以 GET 取當季團隊數據（standings/season 預設當年）。"""
    client = httpx.Client(timeout=30.0, headers={"User-Agent": UA}, follow_redirects=True)
    try:
        s = client.get(STANDINGS).text
    finally:
        client.close()

    tables = re.findall(r"<table.*?</table>", s, re.S)
    bat_tbl = next((t for t in tables if "打擊率" in t and "上壘率" in t), "")
    pit_tbl = next((t for t in tables if "防禦率" in t and "每局被上壘率" in t), "")
    names = {m.group(1): m.group(2) for m in re.finditer(r'TeamNo=([A-Z0-9]+)">([^<]+)</a>', bat_tbl)}
    bat, pit = _team_rows(bat_tbl), _team_rows(pit_tbl)

    rows: list[tuple] = []
    for code in names:
        bv, pv = bat.get(code, []), pit.get(code, [])
        if len(bv) < 13 or len(pv) < 13:
            continue
        obp, slg = _num(bv[10]), _num(bv[11])
        rows.append((
            year, code, names[code],
            _num(bv[12]), obp, slg,
            (obp + slg) if obp is not None and slg is not None else None,
            _int(_num(bv[5])), _num(pv[12]), _num(pv[11]),
        ))
    return rows


def upsert_team(records: list[tuple]) -> int:
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.team_current
                (year, team_code, name, bat_avg, bat_obp, bat_slg, bat_ops, bat_hr, pit_era, pit_whip)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (year, team_code) DO UPDATE SET
                name=EXCLUDED.name, bat_avg=EXCLUDED.bat_avg, bat_obp=EXCLUDED.bat_obp,
                bat_slg=EXCLUDED.bat_slg, bat_ops=EXCLUDED.bat_ops, bat_hr=EXCLUDED.bat_hr,
                pit_era=EXCLUDED.pit_era, pit_whip=EXCLUDED.pit_whip
            """,
            records,
        )
    return len(records)


def scrape_all(start_year: int, end_year: int, current_year: int) -> dict:
    """投手（含歷史）+ 打者 + 團隊。打者/團隊僅當季。"""
    out: dict = {"pitching": {}, "batting": 0, "team": 0}
    for year in range(start_year, end_year + 1):
        out["pitching"][year] = upsert_pitching(fetch_pitching(year))
        log.info("pitching %s done", year)
    out["batting"] = upsert_batting(fetch_batting(current_year))
    out["team"] = upsert_team(fetch_team(current_year))
    log.info("batting=%d team=%d (year %s)", out["batting"], out["team"], current_year)
    return out
