"""從 ldkrsi/cpbl-opendata（MIT）回填歷史資料到 cpbl schema。

冪等：全部以 ON CONFLICT UPSERT，可重複執行。各年度 CSV 欄位會變動
（如 IBB 2021 才加入），故以 csv.DictReader + 容缺欄位的方式解析。
"""

from __future__ import annotations

import csv
import io
import logging
import re

import httpx

from cpbl.config import settings
from cpbl.db import conn

log = logging.getLogger("cpbl.ingest")

_THROWS = re.compile(r"(左投|右投)")
_BATS = re.compile(r"(左打|右打|左右開弓|兩打)")


def _to_int(v: str | None) -> int | None:
    if v is None:
        return None
    v = v.strip()
    if v == "" or v == "-":
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _to_float(v: str | None) -> float | None:
    if v is None:
        return None
    v = v.strip()
    if v == "" or v == "-":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _fetch_csv(client: httpx.Client, path: str) -> list[dict[str, str]] | None:
    """下載一個 CSV；404（該年度不存在）回 None。"""
    url = f"{settings.opendata_base_url}/{path}"
    resp = client.get(url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


# ---------- 各資料表載入 ----------


def load_players(client: httpx.Client) -> int:
    rows = _fetch_csv(client, "players.csv") or []
    records = []
    for r in rows:
        hand = (r.get("Handedness") or "").strip() or None
        throws = _THROWS.search(hand).group(1) if hand and _THROWS.search(hand) else None
        bats = _BATS.search(hand).group(1) if hand and _BATS.search(hand) else None
        records.append(
            (
                r["ID"],
                r.get("Name", "").strip(),
                hand,
                bats,
                throws,
                (r.get("Birthday") or "").replace("/", "-") or None,
                (r.get("Country") or "").strip() or None,
                (r.get("Full Name") or "").strip() or None,
            )
        )
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.players (id, name, handedness, bats, throws, birthday, country, full_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, handedness=EXCLUDED.handedness, bats=EXCLUDED.bats,
                throws=EXCLUDED.throws, birthday=EXCLUDED.birthday,
                country=EXCLUDED.country, full_name=EXCLUDED.full_name
            """,
            records,
        )
    return len(records)


def load_standings(client: httpx.Client) -> int:
    rows = _fetch_csv(client, "CPBL/standings.csv") or []
    records = []
    teams: dict[str, tuple] = {}
    for r in rows:
        year = _to_int(r.get("Year"))
        tid = (r.get("Team ID") or "").strip()
        if not tid or year is None:
            continue
        old_id = (r.get("Old ID") or "").strip() or None
        name = (r.get("Team") or "").strip()
        nick = (r.get("Team Nickname") or "").strip() or None
        records.append(
            (year, tid, old_id, name, nick, _to_int(r.get("Win")), _to_int(r.get("Lose")), _to_int(r.get("Tie")))
        )
        teams[tid] = (tid, old_id, name, nick)  # 以最後（最新年度）為準

    with conn() as c:
        cur = c.cursor()
        cur.executemany(
            """
            INSERT INTO cpbl.teams (team_id, old_id, name, nickname)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (team_id) DO UPDATE SET
                old_id=EXCLUDED.old_id, name=EXCLUDED.name, nickname=EXCLUDED.nickname
            """,
            list(teams.values()),
        )
        cur.executemany(
            """
            INSERT INTO cpbl.standings (year, team_id, old_id, team, nickname, win, lose, tie)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (year, team_id) DO UPDATE SET
                old_id=EXCLUDED.old_id, team=EXCLUDED.team, nickname=EXCLUDED.nickname,
                win=EXCLUDED.win, lose=EXCLUDED.lose, tie=EXCLUDED.tie
            """,
            records,
        )
    return len(records)


def load_battings(client: httpx.Client, year: int) -> int:
    rows = _fetch_csv(client, f"CPBL/battings/{year}.csv")
    if rows is None:
        return 0
    cols = ["G", "PA", "AB", "RBI", "R", "H", "1B", "2B", "3B", "HR", "TB", "SO",
            "SB", "GIDP", "SH", "SF", "BB", "IBB", "HBP", "CS", "GO", "FO"]
    records = []
    for r in rows:
        pid = (r.get("ID") or "").strip()
        tid = (r.get("Team ID") or "").strip()
        if not pid or not tid:
            continue
        vals = [_to_int(r.get(c)) for c in cols]
        records.append((pid, year, tid, (r.get("Team Name") or "").strip() or None, *vals))
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.batting_seasons
                (player_id, year, team_id, team_name,
                 g, pa, ab, rbi, r, h, b1, b2, b3, hr, tb, so,
                 sb, gidp, sh, sf, bb, ibb, hbp, cs, go, fo)
            VALUES (%s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id, year, team_id) DO UPDATE SET
                team_name=EXCLUDED.team_name, g=EXCLUDED.g, pa=EXCLUDED.pa, ab=EXCLUDED.ab,
                rbi=EXCLUDED.rbi, r=EXCLUDED.r, h=EXCLUDED.h, b1=EXCLUDED.b1, b2=EXCLUDED.b2,
                b3=EXCLUDED.b3, hr=EXCLUDED.hr, tb=EXCLUDED.tb, so=EXCLUDED.so, sb=EXCLUDED.sb,
                gidp=EXCLUDED.gidp, sh=EXCLUDED.sh, sf=EXCLUDED.sf, bb=EXCLUDED.bb,
                ibb=EXCLUDED.ibb, hbp=EXCLUDED.hbp, cs=EXCLUDED.cs, go=EXCLUDED.go, fo=EXCLUDED.fo
            """,
            records,
        )
    return len(records)


def load_pitchings(client: httpx.Client, year: int) -> int:
    rows = _fetch_csv(client, f"CPBL/pitchings/{year}.csv")
    if rows is None:
        return 0
    int_cols = ["G", "GS", "GR", "CG", "SHO", "NBB", "W", "L", "SV", "HLD", "BF", "NP",
                "H", "HR", "BB", "IBB", "HBP", "SO", "WP", "BK", "R", "ER", "GO", "FO"]
    records = []
    for r in rows:
        pid = (r.get("ID") or "").strip()
        tid = (r.get("Team ID") or "").strip()
        if not pid or not tid:
            continue
        records.append(
            (
                pid, year, tid, (r.get("Team Name") or "").strip() or None,
                _to_int(r.get("G")), _to_int(r.get("GS")), _to_int(r.get("GR")),
                _to_int(r.get("CG")), _to_int(r.get("SHO")), _to_int(r.get("NBB")),
                _to_int(r.get("W")), _to_int(r.get("L")), _to_int(r.get("SV")), _to_int(r.get("HLD")),
                _to_float(r.get("IP")), _to_int(r.get("BF")), _to_int(r.get("NP")),
                _to_int(r.get("H")), _to_int(r.get("HR")), _to_int(r.get("BB")), _to_int(r.get("IBB")),
                _to_int(r.get("HBP")), _to_int(r.get("SO")), _to_int(r.get("WP")), _to_int(r.get("BK")),
                _to_int(r.get("R")), _to_int(r.get("ER")), _to_int(r.get("GO")), _to_int(r.get("FO")),
            )
        )
        _ = int_cols  # 文件化欄位順序
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.pitching_seasons
                (player_id, year, team_id, team_name,
                 g, gs, gr, cg, sho, nbb, w, l, sv, hld,
                 ip, bf, np, h, hr, bb, ibb, hbp, so, wp, bk, r, er, go, fo)
            VALUES (%s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id, year, team_id) DO UPDATE SET
                team_name=EXCLUDED.team_name, g=EXCLUDED.g, gs=EXCLUDED.gs, gr=EXCLUDED.gr,
                cg=EXCLUDED.cg, sho=EXCLUDED.sho, nbb=EXCLUDED.nbb, w=EXCLUDED.w, l=EXCLUDED.l,
                sv=EXCLUDED.sv, hld=EXCLUDED.hld, ip=EXCLUDED.ip, bf=EXCLUDED.bf, np=EXCLUDED.np,
                h=EXCLUDED.h, hr=EXCLUDED.hr, bb=EXCLUDED.bb, ibb=EXCLUDED.ibb, hbp=EXCLUDED.hbp,
                so=EXCLUDED.so, wp=EXCLUDED.wp, bk=EXCLUDED.bk, r=EXCLUDED.r, er=EXCLUDED.er,
                go=EXCLUDED.go, fo=EXCLUDED.fo
            """,
            records,
        )
    return len(records)


def load_fieldings(client: httpx.Client, year: int) -> int:
    rows = _fetch_csv(client, f"CPBL/fieldings/{year}.csv")
    if rows is None:
        return 0
    records = []
    for r in rows:
        pid = (r.get("ID") or "").strip()
        tid = (r.get("Team ID") or "").strip()
        pos = (r.get("POS") or "").strip()
        if not pid or not tid or not pos:
            continue
        records.append(
            (
                pid, year, tid, (r.get("Team Name") or "").strip() or None, pos,
                _to_int(r.get("G")), _to_int(r.get("TC")), _to_int(r.get("PO")), _to_int(r.get("A")),
                _to_int(r.get("E")), _to_int(r.get("DP")), _to_int(r.get("TP")), _to_int(r.get("PB")),
                _to_int(r.get("CS")), _to_int(r.get("SB")),
            )
        )
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.fielding_seasons
                (player_id, year, team_id, team_name, pos,
                 g, tc, po, a, e, dp, tp, pb, cs, sb)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id, year, team_id, pos) DO UPDATE SET
                team_name=EXCLUDED.team_name, g=EXCLUDED.g, tc=EXCLUDED.tc, po=EXCLUDED.po,
                a=EXCLUDED.a, e=EXCLUDED.e, dp=EXCLUDED.dp, tp=EXCLUDED.tp, pb=EXCLUDED.pb,
                cs=EXCLUDED.cs, sb=EXCLUDED.sb
            """,
            records,
        )
    return len(records)


def backfill() -> dict[str, int]:
    """完整回填：players + standings + 各年度 battings/pitchings/fieldings。"""
    totals = {"players": 0, "standings": 0, "battings": 0, "pitchings": 0, "fieldings": 0}
    with httpx.Client(timeout=30.0) as client:
        log.info("loading players + standings")
        totals["players"] = load_players(client)
        totals["standings"] = load_standings(client)
        for year in range(settings.opendata_start_year, settings.opendata_end_year + 1):
            b = load_battings(client, year)
            p = load_pitchings(client, year)
            f = load_fieldings(client, year)
            totals["battings"] += b
            totals["pitchings"] += p
            totals["fieldings"] += f
            log.info("year %s: batting=%d pitching=%d fielding=%d", year, b, p, f)
    return totals
