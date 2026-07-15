"""當季/歷史排行：打者、投手、守備 + 歷史紀錄室。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _ip_disp
from cpbl.api.rows import _batting_rows, _pitching_rows, _primary_positions
from cpbl.db import conn
from cpbl.ingest.championships import championship_coverage

router = APIRouter()


def _active_expr(alias: str) -> str:
    """現役＝**官方登錄名單**（team_roster）∪ 本季有成績。單用登錄名單會漏升降/離隊者，
    單用出賽會漏「登錄但整季未出賽」者（見記憶 player-name-authority）。

    `alias` 為外層 CTE 的別名；SQL 需帶 `%(y)s` 參數（當季）。
    """
    return (
        f"(EXISTS(SELECT 1 FROM cpbl.team_roster tr WHERE tr.player_id={alias}.player_id AND tr.year=%(y)s) "
        f" OR EXISTS(SELECT 1 FROM cpbl.batting_current bc WHERE bc.player_id={alias}.player_id) "
        f" OR EXISTS(SELECT 1 FROM cpbl.pitching_current pc WHERE pc.player_id={alias}.player_id)) active")


@router.get("/api/v1/records")
def records(kind_code: str = Query("A"), limit: int = Query(5, ge=1, le=50)) -> dict:
    """歷史紀錄室：比賽紀錄 + 單季之最 + 生涯排行（一軍；單季/生涯以官方歷年彙總，近兩季另計）。

    生涯榜為**並列排名**（同數值同名次），故回傳列數可能超過 `limit`。
    """
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

        active_expr = _active_expr("c")

        # **並列排名**：同數值給同名次（1,2,2,4）。舊版直接 LIMIT 會把同分者任意切掉——
        # 生涯榜同分很常見（如生涯 100 轟），切掉誰是隨機的，等於製造假排名。
        # 取法：先算 rank，再取 rank <= limit（故實際列數可能 > limit）。
        def career(table: str, col: str, lim: int) -> list[dict]:
            sql = (
                f"WITH c AS (SELECT player_id, sum({col}) v FROM cpbl.{table} GROUP BY player_id), "
                f"r AS (SELECT p.name, p.id pid, c.v val, {active_expr}, "
                f"       rank() OVER (ORDER BY c.v DESC) rk FROM c "
                f"       JOIN cpbl.players p ON p.id=c.player_id WHERE c.v > 0) "
                f"SELECT * FROM r WHERE rk <= %(n)s ORDER BY rk, name")
            cur.execute(sql, {"n": lim, "y": DEFAULT_SEASON})
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

        career_bat = {k: career("batting_seasons", k, limit) for k in ("hr", "h", "rbi", "sb")}
        career_pit = {k: career("pitching_seasons", k, limit) for k in ("w", "sv", "so")}

    return {"games": games, "season_batting": season_bat, "season_pitching": season_pit,
            "career_batting": career_bat, "career_pitching": career_pit}


@router.get("/api/v1/records/championships")
def championships(limit: int = Query(10, ge=1, le=50)) -> dict:
    """冠軍編：逐年冠亞軍＋奪冠總教練、球團王朝榜、球員冠軍次數榜。

    **紅線：`coverage` 必須隨回應附帶，且缺年時 `complete=false`**（看板依賴序：冠軍資料
    缺年屬資料正確性紅線，未補齊不得公開「歷史最多冠軍」結論）。前端在 `complete=false`
    時**不得**呈現累計排行為完整歷史結論——故此時 `franchise_ranking`／`player_ranking`
    直接不回傳，而非讓前端自行決定要不要顯示。

    冠軍教練來自 canonical `championship_managers`（非 `managers.championships`，該欄為維基
    來源、漏記 7 筆；見記憶 championship-managers-canonical）。
    """
    with conn() as c:
        cur = c.cursor()

        # 冠亞軍名稱取自 games 的**當年實際隊名**（era-accurate），不用 team_dim。
        # team_dim 只收現役 franchise 碼（AAA011…），歷史／已解散隊碼（三商 ABB011、
        # 時報 AFF011、Lamigo AJK011、義大 AEM011…）查不到 → 名稱為 null。games 每場
        # 都存當年 team_code+team_name，故 code→當年最常見名稱即為權威 era 名稱。
        cur.execute("""
            WITH tn AS (
              SELECT code, name FROM (
                SELECT code, name,
                       row_number() OVER (PARTITION BY code ORDER BY sum(cnt) DESC) rn
                FROM (
                  SELECT home_team_code code, home_team_name name, count(*) cnt
                  FROM cpbl.games WHERE home_team_code IS NOT NULL AND home_team_name IS NOT NULL
                  GROUP BY 1, 2
                  UNION ALL
                  SELECT away_team_code, away_team_name, count(*)
                  FROM cpbl.games WHERE away_team_code IS NOT NULL AND away_team_name IS NOT NULL
                  GROUP BY 1, 2
                ) g GROUP BY code, name
              ) r WHERE rn = 1
            )
            SELECT ch.year, ch.champion_team_code, tc.name AS champion,
                   ch.runner_up_team_code, tr.name AS runner_up,
                   ch.franchise_code, cm.manager_name, ch.source_url
            FROM cpbl.championships ch
            LEFT JOIN tn tc ON tc.code = ch.champion_team_code
            LEFT JOIN tn tr ON tr.code = ch.runner_up_team_code
            LEFT JOIN cpbl.championship_managers cm
                   ON cm.year = ch.year AND cm.verification_status = 'verified'
            WHERE ch.verification_status = 'verified'
            ORDER BY ch.year DESC
        """)
        cols = [d[0] for d in cur.description]
        seasons = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        cov = championship_coverage([s["year"] for s in seasons], as_of=None)
        cov["as_of"] = None
        out: dict = {"coverage": cov, "seasons": seasons}

        # 缺年 → fail-closed：不產出任何「歷史最多」的累計結論
        if not cov["complete"]:
            out["note"] = ("冠軍資料缺年（%s），依資料正確性紅線不產出累計排行"
                           % ", ".join(map(str, cov["missing_years"])))
            return out

        cur.execute("""
            WITH t AS (
              SELECT ch.franchise_code AS team_code, count(*) AS titles,
                     array_agg(ch.year ORDER BY ch.year) AS years
              FROM cpbl.championships ch WHERE ch.verification_status='verified'
              GROUP BY ch.franchise_code),
            r AS (
              SELECT t.team_code, d.short AS team, t.titles, t.years,
                     rank() OVER (ORDER BY t.titles DESC) AS rk
              FROM t LEFT JOIN cpbl.team_dim d ON d.team_code = t.team_code)
            SELECT * FROM r WHERE rk <= %(n)s ORDER BY rk, team_code
        """, {"n": limit})
        cols = [d[0] for d in cur.description]
        out["franchise_ranking"] = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        # 球員冠軍次數（championship_members role='player'；並列排名同上）
        cur.execute(f"""
            WITH m AS (
              SELECT cm.player_id, count(*) AS titles,
                     array_agg(cm.year ORDER BY cm.year) AS years
              FROM cpbl.championship_members cm WHERE cm.role='player'
              GROUP BY cm.player_id),
            r AS (
              SELECT p.name, p.id AS pid, m.titles, m.years, {_active_expr("m")},
                     rank() OVER (ORDER BY m.titles DESC) AS rk
              FROM m JOIN cpbl.players p ON p.id = m.player_id)
            SELECT * FROM r WHERE rk <= %(n)s ORDER BY rk, name
        """, {"n": limit, "y": DEFAULT_SEASON})
        cols = [d[0] for d in cur.description]
        out["player_ranking"] = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

    return out


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
