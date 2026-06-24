"""官網 /stats 投手成績爬蟲（含本季 ERA 與進階指標 + 球員名）。

端點：POST /stats/recordallaction（與 getgamedatas 不同：token 走**表單欄位**
__RequestVerificationToken，form.serialize() 提交，回傳 HTML 片段）。
Position=02 為投手。回傳每列含 acnt(player_id)、名字、TeamNo，及 35 個 num 欄位。
"""

from __future__ import annotations

import logging
import re

from cpbl.db import conn

log = logging.getLogger("cpbl.stats")

BASE = "https://www.cpbl.com.tw"
PAGE = f"{BASE}/stats/recordall"
ACTION = f"{BASE}/stats/recordallaction"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')

STANDINGS = f"{BASE}/standings/season"
TEAMSCORE = f"{BASE}/team/teamscore"
TEAMSCORE_ACTION = f"{BASE}/team/teamscoreaction"
# 各隊 ClubNo（team_code 前 3 碼）；team_code = ClubNo + "011"
CLUB_NOS = ["AAA", "ACN", "ADD", "AEO", "AJL", "AKP"]

# teamscore 投手(Position=02) num 欄位 index（球員 cell 之後；官網 28 欄全集）
PIT_TS_IDX = {
    "g": 0, "gs": 1, "gr": 2, "cg": 3, "sho": 4, "w": 6, "l": 7, "sv": 8, "hld": 9,
    "ip": 10, "whip": 11, "era": 12, "pa": 13, "np": 14, "h": 15, "hr": 16,
    "bb": 17, "ibb": 18, "hbp": 19, "so": 20, "wp": 21, "bk": 22, "r": 23, "er": 24,
    "go": 25, "ao": 26, "goao": 27,
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


_TEAMSCORE_PATH = f"/team/teamscore?ClubNo={CLUB_NOS[0]}"


def _teamscore_token() -> str:
    from cpbl.ingest._browser import session
    m = _TOKEN_RE.search(session().page_html(_TEAMSCORE_PATH))
    if not m:
        raise RuntimeError("找不到 teamscore __RequestVerificationToken（官網可能改版）")
    return m.group(1)


def _teamscore_post(token: str, club: str, position: str, year: int, kind_code: str) -> str:
    from cpbl.ingest._browser import session
    form = {
        "__RequestVerificationToken": token, "ClubNo": club, "Year": str(year),
        "KindCode": kind_code, "Position": position, "DefendStation": "",
        "Sortby": "", "ExecAction": "Q", "IndexOfPages": "1",
    }
    status, html = session().post(_TEAMSCORE_PATH, "/team/teamscoreaction", form)
    if status != 200:
        raise RuntimeError(f"teamscoreaction HTTP {status}（反爬挑戰未過？）")
    return html


def fetch_pitching(year: int, kind_code: str = "A") -> list[tuple]:
    """逐隊抓 teamscore 投手(Position=02)全名單;K9 由 三振×9/局數 自算。"""
    rows: list[tuple] = []
    try:
        token = _teamscore_token()
        for club in CLUB_NOS:
            team_code = f"{club}011"
            html = _teamscore_post(token, club, "02", year, kind_code)
            for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
                mid = re.search(r"/team/person\?acnt=(\d+)", tr)
                if not mid:
                    continue
                nums = [n.strip() for n in re.findall(r'<td class="num">(.*?)</td>', tr, re.S)]
                if len(nums) < 28:
                    continue
                name_m = re.search(r'/team/person\?acnt=\d+"[^>]*>([^<]+)</a>', tr)

                def p(k: str) -> float | None:
                    return _num(nums[PIT_TS_IDX[k]])

                # 故四欄以全形括號呈現（如「（1）」），取其中數字
                ibb_m = re.search(r"\d+", nums[PIT_TS_IDX["ibb"]])
                ibb = int(ibb_m.group()) if ibb_m else None

                ip, so = p("ip"), p("so")
                k9 = (so * 9.0 / ip) if (so is not None and ip and ip > 0) else None
                rows.append((
                    year, mid.group(1),
                    name_m.group(1).strip() if name_m else None, team_code,
                    p("era"), ip, _int(p("g")), _int(p("gs")), _int(p("w")), _int(p("l")),
                    p("whip"), k9, None, None,  # fip/era_plus teamscore 無
                    _int(p("sv")), _int(p("hld")),
                    _int(p("so")), _int(p("cg")), _int(p("sho")), _int(p("pa")), _int(p("np")),
                    _int(p("h")), _int(p("hr")), _int(p("bb")), ibb, _int(p("hbp")),
                    _int(p("wp")), _int(p("bk")), _int(p("r")), _int(p("er")),
                    _int(p("go")), _int(p("ao")), p("goao"),
                ))
    finally:
        pass  # 瀏覽器 session 為單例，不在此關閉
    return rows


def upsert_pitching(records: list[tuple]) -> int:
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.pitching_current
                (year, player_id, name, team_code, era, ip, g, gs, w, l, whip, k9, fip, era_plus,
                 sv, hld, so, cg, sho, pa, np, h, hr, bb, ibb, hbp, wp, bk, r, er, go, ao, goao)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (year, player_id) DO UPDATE SET
                name=EXCLUDED.name, team_code=EXCLUDED.team_code, era=EXCLUDED.era, ip=EXCLUDED.ip,
                g=EXCLUDED.g, gs=EXCLUDED.gs, w=EXCLUDED.w, l=EXCLUDED.l,
                whip=EXCLUDED.whip, k9=EXCLUDED.k9, fip=EXCLUDED.fip, era_plus=EXCLUDED.era_plus,
                sv=EXCLUDED.sv, hld=EXCLUDED.hld, so=EXCLUDED.so, cg=EXCLUDED.cg, sho=EXCLUDED.sho,
                pa=EXCLUDED.pa, np=EXCLUDED.np, h=EXCLUDED.h, hr=EXCLUDED.hr, bb=EXCLUDED.bb,
                ibb=EXCLUDED.ibb, hbp=EXCLUDED.hbp, wp=EXCLUDED.wp, bk=EXCLUDED.bk, r=EXCLUDED.r,
                er=EXCLUDED.er, go=EXCLUDED.go, ao=EXCLUDED.ao, goao=EXCLUDED.goao
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


# ---------- 打者全名單（/team/teamscore Position=01，含 1 打席者）----------
# teamscore num 欄位 index（球員 cell 之後）
TS_IDX = {
    "g": 0, "pa": 1, "ab": 2, "rbi": 3, "r": 4, "h": 5, "b2": 7, "b3": 8, "hr": 9,
    "tb": 10, "so": 11, "sb": 12, "obp": 13, "slg": 14, "avg": 15, "gidp": 16,
    "sh": 17, "sf": 18, "bb": 19, "ibb": 20, "hbp": 21, "cs": 22,
    "go": 23, "ao": 24, "goao": 25, "ops": 27,
}


def fetch_batting(year: int, kind_code: str = "A") -> list[tuple]:
    """逐隊抓 teamscore 取得全部打者（含低出場）。teamscore 預設當季。"""
    rows: list[tuple] = []
    try:
        for club in CLUB_NOS:
            team_code = f"{club}011"
            from cpbl.ingest._browser import session
            html = session().page_html(f"/team/teamscore?ClubNo={club}")
            for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
                mid = re.search(r"/team/person\?acnt=(\d+)", tr)
                if not mid:
                    continue
                nums = [n.strip() for n in re.findall(r'<td class="num">(.*?)</td>', tr, re.S)]
                if len(nums) < 28:
                    continue
                name_m = re.search(r'/team/person\?acnt=\d+"[^>]*>([^<]+)</a>', tr)

                def b(k: str) -> float | None:
                    return _num(nums[TS_IDX[k]])

                # 故四欄為全形括號（如「（0）」），取其中數字
                ibb_m = re.search(r"\d+", nums[TS_IDX["ibb"]])
                ibb = int(ibb_m.group()) if ibb_m else None
                pa, so, bb = b("pa"), b("so"), b("bb")
                k_pct = round(so / pa * 100, 1) if (so is not None and pa) else None
                bb_pct = round(bb / pa * 100, 1) if (bb is not None and pa) else None

                rows.append((
                    year, mid.group(1),
                    name_m.group(1).strip() if name_m else None,
                    team_code,
                    _int(b("pa")), b("avg"), b("obp"), b("slg"), b("ops"),
                    _int(b("hr")), None, k_pct, bb_pct,  # teamscore 無 OPS+；K%/BB% 自算
                    _int(b("g")), _int(b("ab")), _int(b("r")), _int(b("h")),
                    _int(b("b2")), _int(b("b3")), _int(b("rbi")), _int(b("bb")),
                    _int(b("so")), _int(b("sb")), _int(b("cs")),
                    _int(b("tb")), _int(b("gidp")), _int(b("sh")), _int(b("sf")), ibb,
                    _int(b("hbp")), _int(b("go")), _int(b("ao")), b("goao"),
                ))
    finally:
        pass  # 瀏覽器 session 為單例，不在此關閉
    return rows


def upsert_batting(records: list[tuple]) -> int:
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.batting_current
                (year, player_id, name, team_code, pa, avg, obp, slg, ops, hr, ops_plus, k_pct, bb_pct,
                 g, ab, r, h, b2, b3, rbi, bb, so, sb, cs,
                 tb, gidp, sh, sf, ibb, hbp, go, ao, goao)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (year, player_id) DO UPDATE SET
                name=EXCLUDED.name, team_code=EXCLUDED.team_code, pa=EXCLUDED.pa, avg=EXCLUDED.avg,
                obp=EXCLUDED.obp, slg=EXCLUDED.slg, ops=EXCLUDED.ops, hr=EXCLUDED.hr,
                ops_plus=EXCLUDED.ops_plus, k_pct=EXCLUDED.k_pct, bb_pct=EXCLUDED.bb_pct,
                g=EXCLUDED.g, ab=EXCLUDED.ab, r=EXCLUDED.r, h=EXCLUDED.h, b2=EXCLUDED.b2,
                b3=EXCLUDED.b3, rbi=EXCLUDED.rbi, bb=EXCLUDED.bb, so=EXCLUDED.so,
                sb=EXCLUDED.sb, cs=EXCLUDED.cs,
                tb=EXCLUDED.tb, gidp=EXCLUDED.gidp, sh=EXCLUDED.sh, sf=EXCLUDED.sf, ibb=EXCLUDED.ibb,
                hbp=EXCLUDED.hbp, go=EXCLUDED.go, ao=EXCLUDED.ao, goao=EXCLUDED.goao
            """,
            records,
        )
    return len(records)


# ---------- 守備全名單（/team/teamscoreaction Position=03）----------
# nums: [0]=守備位置(文字) [1]=出賽 [2]=守備機會 [3]=刺殺 [4]=助殺 [5]=失誤 [6]=雙殺 … [11]=守備率

def fetch_fielding(year: int, kind_code: str = "A") -> list[tuple]:
    rows: list[tuple] = []
    try:
        token = _teamscore_token()
        for club in CLUB_NOS:
            team_code = f"{club}011"
            html = _teamscore_post(token, club, "03", year, kind_code)
            for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
                mid = re.search(r"/team/person\?acnt=(\d+)", tr)
                if not mid:
                    continue
                nums = [re.sub(r"<[^>]+>", "", n).strip()
                        for n in re.findall(r'<td class="num">(.*?)</td>', tr, re.S)]
                if len(nums) < 12 or not nums[0]:
                    continue
                name_m = re.search(r'/team/person\?acnt=\d+"[^>]*>([^<]+)</a>', tr)
                # 欄序：守位 出賽 守備機會 刺殺 助殺 失誤 雙殺 三殺 捕逸 盜壘阻殺 被盜成功 守備率
                rows.append((
                    year, mid.group(1), name_m.group(1).strip() if name_m else None, team_code,
                    nums[0],
                    _int(_num(nums[1])), _int(_num(nums[2])), _int(_num(nums[3])),
                    _int(_num(nums[4])), _int(_num(nums[5])), _int(_num(nums[6])),
                    _int(_num(nums[7])), _int(_num(nums[8])), _int(_num(nums[9])), _int(_num(nums[10])),
                    _num(nums[11]),
                ))
    finally:
        pass  # 瀏覽器 session 為單例，不在此關閉
    return rows


def upsert_fielding(records: list[tuple]) -> int:
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.fielding_current
                (year, player_id, name, team_code, pos, g, tc, po, a, e, dp, tp, pb, cs, sba, fpct)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (year, player_id, pos) DO UPDATE SET
                name=EXCLUDED.name, team_code=EXCLUDED.team_code, g=EXCLUDED.g, tc=EXCLUDED.tc,
                po=EXCLUDED.po, a=EXCLUDED.a, e=EXCLUDED.e, dp=EXCLUDED.dp,
                tp=EXCLUDED.tp, pb=EXCLUDED.pb, cs=EXCLUDED.cs, sba=EXCLUDED.sba, fpct=EXCLUDED.fpct
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
    try:
        from cpbl.ingest._browser import session
        s = session().page_html("/standings/season")
    finally:
        pass  # 瀏覽器 session 為單例，不在此關閉

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
    """投手 + 打者 + 守備 + 團隊（皆當季全名單）。"""
    out: dict = {"pitching": {}, "batting": 0, "fielding": 0, "team": 0}
    for year in range(start_year, end_year + 1):
        out["pitching"][year] = upsert_pitching(fetch_pitching(year))
        log.info("pitching %s done", year)
    out["batting"] = upsert_batting(fetch_batting(current_year))
    out["fielding"] = upsert_fielding(fetch_fielding(current_year))
    out["team"] = upsert_team(fetch_team(current_year))
    log.info("batting=%d fielding=%d team=%d (year %s)",
             out["batting"], out["fielding"], out["team"], current_year)
    return out
