"""當季/歷史排行：打者、投手、守備 + 歷史紀錄室。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _ip_disp
from cpbl.api.rows import _batting_rows, _pitching_rows, _primary_positions
from cpbl.db import conn

router = APIRouter()


@router.get("/api/v1/records")
def records(kind_code: str = Query("A")) -> dict:
    """歷史紀錄室：比賽紀錄 + 單季之最 + 生涯排行（一軍；單季/生涯以官方歷年彙總，近兩季另計）。"""
    with conn() as c:
        cur = c.cursor()

        def game_rec(order: str) -> dict | None:
            cur.execute(
                f"SELECT year, game_date, home_team_name, away_team_name, home_score, away_score "
                f"FROM cpbl.games WHERE kind_code=%s AND home_score+away_score>0 ORDER BY {order} LIMIT 1",
                (kind_code,))
            r = cur.fetchone()
            if not r:
                return None
            return {"year": r[0], "date": str(r[1]), "home": r[2], "away": r[3], "hs": r[4], "as": r[5]}

        games = {
            "max_margin": game_rec("abs(home_score-away_score) DESC, game_date"),
            "max_team_runs": game_rec("greatest(home_score,away_score) DESC, game_date"),
            "max_combined": game_rec("home_score+away_score DESC, game_date"),
        }

        def top(sql: str, n: int = 1) -> list[dict]:
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()[:n]]

        ssb = ("WITH s AS (SELECT player_id, year, sum(hr) hr, sum(h) h, sum(rbi) rbi, sum(sb) sb, "
               "sum(ab) ab, sum(pa) pa, sum(tb) tb, sum(bb) bb, sum(hbp) hbp, sum(sf) sf "
               "FROM cpbl.batting_seasons GROUP BY player_id, year) "
               "SELECT p.name, p.id pid, s.year, {expr} val FROM s JOIN cpbl.players p ON p.id=s.player_id "
               "{where} ORDER BY val DESC LIMIT 1")
        season_bat = {
            "hr": top(ssb.format(expr="s.hr", where="")),
            "rbi": top(ssb.format(expr="s.rbi", where="")),
            "sb": top(ssb.format(expr="s.sb", where="")),
            "avg": top(ssb.format(expr="round(s.h::numeric/nullif(s.ab,0),3)", where="WHERE s.pa>=400")),
        }
        ssp = ("WITH s AS (SELECT player_id, year, sum(w) w, sum(sv) sv, sum(so) so "
               "FROM cpbl.pitching_seasons GROUP BY player_id, year) "
               "SELECT p.name, p.id pid, s.year, s.{col} val FROM s JOIN cpbl.players p ON p.id=s.player_id "
               "ORDER BY val DESC LIMIT 1")
        season_pit = {k: top(ssp.format(col=k)) for k in ("w", "sv", "so")}

        # 現役 = 本季登錄打/投；生涯排行標注供前端區分現役/退役
        active_expr = ("(EXISTS(SELECT 1 FROM cpbl.batting_current bc WHERE bc.player_id=c.player_id) "
                       "OR EXISTS(SELECT 1 FROM cpbl.pitching_current pc WHERE pc.player_id=c.player_id)) active")
        cb = ("WITH c AS (SELECT player_id, sum({col}) v FROM cpbl.batting_seasons GROUP BY player_id) "
              "SELECT p.name, p.id pid, c.v val, " + active_expr +
              " FROM c JOIN cpbl.players p ON p.id=c.player_id ORDER BY v DESC LIMIT 5")
        career_bat = {k: top(cb.format(col=k), 5) for k in ("hr", "h", "rbi", "sb")}
        cp = ("WITH c AS (SELECT player_id, sum({col}) v FROM cpbl.pitching_seasons GROUP BY player_id) "
              "SELECT p.name, p.id pid, c.v val, " + active_expr +
              " FROM c JOIN cpbl.players p ON p.id=c.player_id ORDER BY v DESC LIMIT 5")
        career_pit = {k: top(cp.format(col=k), 5) for k in ("w", "sv", "so")}

    return {"games": games, "season_batting": season_bat, "season_pitching": season_pit,
            "career_batting": career_bat, "career_pitching": career_pit}


@router.get("/api/v1/season/batting-leaders")
def batting_leaders(
    season: int = Query(DEFAULT_SEASON),
    sort: str = Query("ops", pattern="^(ops|avg|obp|slg|hr|rbi|r|h|sb|bb|so)$"),
    min_pa: int = Query(30, ge=0, description="最低打席（排行用；0=全名單）"),
    limit: int = Query(50, ge=1, le=500),
    kind_code: str = Query("A"),
) -> dict:
    """打者排行：當季一軍/歷史/二軍。rate(avg/obp/slg/ops/k%/bb%)統一由原始計數計算。"""
    pos_map = _primary_positions(season, kind_code)
    items = []
    for r in _batting_rows(season, kind_code):
        r["pos"] = pos_map.get(r["player_id"])
        ab, h, bb, hbp, sf, tb, pa = (r.get(k) or 0 for k in ("ab", "h", "bb", "hbp", "sf", "tb", "pa"))
        if pa < min_pa:
            continue
        obp_den = ab + bb + hbp + sf
        r["avg"] = round(h / ab, 3) if ab else None
        r["obp"] = round((h + bb + hbp) / obp_den, 3) if obp_den else None
        r["slg"] = round(tb / ab, 3) if ab else None
        r["ops"] = round((r["obp"] or 0) + (r["slg"] or 0), 3) if ab else None
        r["k_pct"] = round((r.get("so") or 0) / pa * 100, 1) if pa else None
        r["bb_pct"] = round(bb / pa * 100, 1) if pa else None
        items.append(r)
    items.sort(key=lambda x: (x.get(sort) is not None, x.get(sort) or 0), reverse=True)
    return {"season": season, "sort": sort, "items": items[:limit]}
@router.get("/api/v1/season/pitching-leaders")
def pitching_leaders(
    season: int = Query(DEFAULT_SEASON),
    sort: str = Query("era", pattern="^(era|whip|w|sv|hld|k9|gs|ip)$"),
    min_ip: float = Query(20, ge=0, description="最低投球局數"),
    limit: int = Query(50, ge=1, le=500),
    kind_code: str = Query("A"),
) -> dict:
    """投手排行：當季一軍/歷史/二軍。ERA/WHIP/K9 由原始計數+真實局數計算（越低越前的 era/whip 反向排）。"""
    items = []
    for r in _pitching_rows(season, kind_code):
        ip = r.get("ip")
        if ip is None:
            continue
        ip = float(ip)
        if ip < min_ip:
            continue
        er, h, bb, so = (r.get(k) or 0 for k in ("er", "h", "bb", "so"))
        r["ip"] = _ip_disp(ip)  # 顯示用 .1/.2 記法（era/whip/k9 仍用真實局數 ip）
        r["era"] = round(er * 9 / ip, 2) if ip else None
        r["whip"] = round((h + bb) / ip, 2) if ip else None
        r["k9"] = round(so * 9 / ip, 2) if ip else None
        items.append(r)
    asc = sort in ("era", "whip")  # era/whip 越低越前
    present = sorted((x for x in items if x.get(sort) is not None), key=lambda x: x[sort], reverse=not asc)
    absent = [x for x in items if x.get(sort) is None]
    return {"season": season, "sort": sort, "items": (present + absent)[:limit]}


@router.get("/api/v1/season/fielding")
def fielding(
    season: int = Query(DEFAULT_SEASON),
    pos: str | None = Query(None, description="守備位置；省略則全部"),
    sort: str = Query("tc", pattern="^(tc|po|a|e|dp|fpct|g)$"),
    limit: int = Query(60, ge=1, le=1000),
) -> dict:
    """本季守備數據（fielding_current）。可依守備位置篩選。"""
    direction = "ASC" if sort == "e" else "DESC"
    where = "f.year = %s" + ("" if pos is None else " AND f.pos = %s")
    params: tuple = (season,) if pos is None else (season, pos)
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT DISTINCT pos FROM cpbl.fielding_current WHERE year = %s ORDER BY pos", (season,))
        positions = [r[0] for r in cur.fetchall()]
        cur.execute(
            f"""
            SELECT f.player_id, f.name, t.name, f.pos, f.g, f.tc, f.po, f.a, f.e, f.dp, f.fpct
            FROM cpbl.fielding_current f
            LEFT JOIN cpbl.team_current t ON t.team_code = f.team_code AND t.year = f.year
            WHERE {where} AND f.{sort} IS NOT NULL
            ORDER BY f.{sort} {direction} NULLS LAST
            LIMIT %s
            """,
            (*params, limit),
        )
        items = [
            {"player_id": pid, "name": name, "team": team, "pos": p, "g": g, "tc": tc,
             "po": po, "a": a, "e": e, "dp": dp,
             "fpct": float(fpct) if fpct is not None else None}
            for pid, name, team, p, g, tc, po, a, e, dp, fpct in cur.fetchall()
        ]
    return {"season": season, "positions": positions, "pos": pos, "sort": sort, "items": items}
