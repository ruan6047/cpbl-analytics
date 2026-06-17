"""以官方 teamscore 回填某一年的 season-level 彙總到 *_seasons（opendata 未涵蓋的年份，如 2025）。

teamscore 欄位與 *_seasons 幾乎一一對應（故四為全形括號需解析；team_id 用 team_code）。
冪等 UPSERT。僅補打者與投手季（ML 預測用）。
"""

from __future__ import annotations

import logging
import re

import httpx

from cpbl.db import conn
from cpbl.ingest.cpbl_stats import (
    CLUB_NOS,
    PIT_TS_IDX,
    TS_IDX,
    UA,
    _num,
    _teamscore_post,
    _teamscore_token,
)

log = logging.getLogger("cpbl.seasonbf")

CLUB_NAME = {"AAA": "味全龍", "ACN": "中信兄弟", "ADD": "統一7-ELEVEn獅",
             "AEO": "富邦悍將", "AJL": "樂天桃猿", "AKP": "台鋼雄鷹"}


def _int(v) -> int | None:
    return int(v) if v is not None else None


def _paren_int(cell: str) -> int | None:
    m = re.search(r"\d+", cell or "")
    return int(m.group()) if m else None


def _rows(html: str, idx: dict, n_min: int):
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        mid = re.search(r"/team/person\?acnt=(\d+)", tr)
        if not mid:
            continue
        nums = [n.strip() for n in re.findall(r'<td class="num">(.*?)</td>', tr, re.S)]
        if len(nums) < n_min:
            continue
        yield mid.group(1), nums


def backfill_batting_season(year: int) -> int:
    records = []
    client = httpx.Client(timeout=30.0, headers={"User-Agent": UA}, follow_redirects=True)
    try:
        token = _teamscore_token(client)
        for club in CLUB_NOS:
            tc, html = f"{club}011", _teamscore_post(client, token, club, "01", year, "A")

            for pid, nums in _rows(html, TS_IDX, 28):
                def b(k):
                    return _num(nums[TS_IDX[k]])
                records.append((
                    pid, year, tc, CLUB_NAME.get(club),
                    _int(b("g")), _int(b("pa")), _int(b("ab")), _int(b("rbi")), _int(b("r")), _int(b("h")),
                    _int(_num(nums[6])), _int(b("b2")), _int(b("b3")), _int(b("hr")), _int(b("tb")),
                    _int(b("so")), _int(b("sb")), _int(b("gidp")), _int(b("sh")), _int(b("sf")),
                    _int(b("bb")), _paren_int(nums[TS_IDX["ibb"]]), _int(b("hbp")), _int(b("cs")),
                    _int(b("go")), _int(b("ao")),
                ))
    finally:
        client.close()
    cols = ("player_id,year,team_id,team_name,g,pa,ab,rbi,r,h,b1,b2,b3,hr,tb,so,sb,gidp,sh,sf,"
            "bb,ibb,hbp,cs,go,fo")
    return _upsert("batting_seasons", cols, records)


def backfill_pitching_season(year: int) -> int:
    records = []
    client = httpx.Client(timeout=30.0, headers={"User-Agent": UA}, follow_redirects=True)
    try:
        token = _teamscore_token(client)
        for club in CLUB_NOS:
            tc, html = f"{club}011", _teamscore_post(client, token, club, "02", year, "A")

            for pid, nums in _rows(html, PIT_TS_IDX, 28):
                def p(k):
                    return _num(nums[PIT_TS_IDX[k]])
                records.append((
                    pid, year, tc, CLUB_NAME.get(club),
                    _int(p("g")), _int(p("gs")), _int(p("gr")), _int(p("cg")), _int(p("sho")),
                    _int(_num(nums[5])), _int(p("w")), _int(p("l")), _int(p("sv")), _int(p("hld")),
                    p("ip"), _int(p("pa")), _int(p("np")), _int(p("h")), _int(p("hr")),
                    _int(p("bb")), _paren_int(nums[PIT_TS_IDX["ibb"]]), _int(p("hbp")), _int(p("so")),
                    _int(p("wp")), _int(p("bk")), _int(p("r")), _int(p("er")), _int(p("go")), _int(p("ao")),
                ))
    finally:
        client.close()
    cols = ("player_id,year,team_id,team_name,g,gs,gr,cg,sho,nbb,w,l,sv,hld,ip,bf,np,h,hr,"
            "bb,ibb,hbp,so,wp,bk,r,er,go,fo")
    return _upsert("pitching_seasons", cols, records)


def _upsert(table: str, cols: str, records: list[tuple]) -> int:
    if not records:
        return 0
    col_list = [c.strip() for c in cols.split(",")]
    ph = "(" + ",".join(["%s"] * len(col_list)) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in col_list[3:])
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.{table} ({cols}) VALUES {ph} "
            f"ON CONFLICT (player_id, year, team_id) DO UPDATE SET {updates}",
            records,
        )
    return len(records)
