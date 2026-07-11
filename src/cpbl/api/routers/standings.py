"""戰績：即時彙整榜、官方戰績（含上下半季/勝差）、戰績走勢。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _dicts
from cpbl.api.rows import _team_advanced
from cpbl.db import conn
from cpbl.models import matchup

router = APIRouter()


def _team_advanced_from_seasons(season: int) -> dict[str, dict]:
    """歷史年度 team_current 缺值時，從季彙總回推團隊 OPS/ERA/WHIP。"""
    bat: dict[str, dict] = {}
    pit: dict[str, dict] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT team_id, sum(ab), sum(h), sum(tb), sum(bb), sum(hbp), sum(sf) "
            "FROM cpbl.batting_seasons WHERE year=%s GROUP BY team_id",
            (season,),
        )
        for tid, ab, h, tb, bb, hbp, sf in cur.fetchall():
            ab = int(ab or 0)
            if ab <= 0:
                continue
            h = int(h or 0)
            tb = int(tb or 0)
            bb = int(bb or 0)
            hbp = int(hbp or 0)
            sf = int(sf or 0)
            den = ab + bb + hbp + sf
            obp = ((h + bb + hbp) / den) if den else None
            slg = tb / ab
            ops = (obp + slg) if obp is not None else None
            code = str(tid)[:3]
            bat[code] = {"ops": round(ops, 3) if ops is not None else None}
        cur.execute(
            "SELECT team_id, "
            "sum(floor(ip)+(ip-floor(ip))*10/3.0), sum(er), sum(h), sum(bb) "
            "FROM cpbl.pitching_seasons WHERE year=%s GROUP BY team_id",
            (season,),
        )
        for tid, ip, er, h, bb in cur.fetchall():
            rip = float(ip or 0)
            if rip <= 0:
                continue
            code = str(tid)[:3]
            pit[code] = {
                "era": round((float(er or 0) * 9) / rip, 2),
                "whip": round((float(h or 0) + float(bb or 0)) / rip, 2),
            }
    teams = set(bat) | set(pit)
    return {t: {**bat.get(t, {}), **pit.get(t, {})} for t in teams}


@router.get("/api/v1/season/standings")
def season_standings(season: int = Query(DEFAULT_SEASON)) -> dict:
    """本季戰績榜（games 即時彙整 + team_current 團隊進階：OPS/ERA/WHIP）。"""
    stats = matchup.team_stats(season)
    adv = _team_advanced(season)
    if not adv:
        adv = _team_advanced_from_seasons(season)
    rows = [
        {
            "code": c, "name": v["name"], "w": v["w"], "l": v["l"], "g": v["g"],
            "win_pct": round(v["win_pct"], 3),
            "rs_pg": round(v["rs_pg"], 2), "ra_pg": round(v["ra_pg"], 2),
            "run_diff": round(v["rs_pg"] - v["ra_pg"], 2),
            "form": v["last10"],
            "ops": (adv.get(c) or adv.get(c[:3]) or {}).get("ops"),
            "era": (adv.get(c) or adv.get(c[:3]) or {}).get("era"),
            "whip": (adv.get(c) or adv.get(c[:3]) or {}).get("whip"),
        }
        for c, v in stats.items()
    ]
    rows.sort(key=lambda r: (r["win_pct"], r["run_diff"]), reverse=True)
    return {"season": season, "standings": rows}


@router.get("/api/v1/postseason-summary")
def postseason_summary(season: int = Query(DEFAULT_SEASON)) -> dict:
    """年度季後賽摘要（挑戰賽/台灣大賽）與系列大比分。"""
    with conn() as c:
        rows = c.execute(
            "SELECT kind_code, home_team_code, home_team_name, away_team_code, away_team_name, "
            "home_score, away_score, game_date "
            "FROM cpbl.games "
            "WHERE year=%s AND kind_code IN ('E','C') AND home_score+away_score>0 "
            "ORDER BY game_date, game_sno",
            (season,),
        ).fetchall()
    series: dict = {}
    for kc, hc, hn, ac, an, hs, as_, gd in rows:
        key = (kc, tuple(sorted((hc, ac))))
        if key not in series:
            series[key] = {"kind_code": kc, "teams": {
                hc: {"name": hn, "wins": 0},
                ac: {"name": an, "wins": 0},
            }, "games": []}
        if hs > as_:
            series[key]["teams"][hc]["wins"] += 1
        elif as_ > hs:
            series[key]["teams"][ac]["wins"] += 1
        # 逐場小比分（依日期序，勝隊由 game 端算）
        series[key]["games"].append({
            "game_no": len(series[key]["games"]) + 1,
            "date": gd.isoformat() if gd else None,
            "home_code": hc, "home_name": hn, "home_score": hs,
            "away_code": ac, "away_name": an, "away_score": as_,
        })
    out = []
    kind_name = {"E": "季後挑戰賽", "C": "台灣大賽"}
    for s in series.values():
        teams = list(s["teams"].items())
        teams.sort(key=lambda x: (-x[1]["wins"], x[0]))
        (c1, t1), (c2, t2) = teams
        out.append({
            "kind_code": s["kind_code"],
            "kind_name": kind_name.get(s["kind_code"], s["kind_code"]),
            "team1_code": c1, "team1_name": t1["name"], "team1_wins": t1["wins"],
            "team2_code": c2, "team2_name": t2["name"], "team2_wins": t2["wins"],
            "games": s["games"],
        })
    out.sort(key=lambda x: x["kind_code"], reverse=True)  # E 再 C
    return {"season": season, "series": out}
def _computed_standings(season: int, kind_code: str, season_code: int = 0) -> list[dict]:
    """歷史年份無官方 team_standings → 由 games 逐場結果即時算戰績（全年/半季）。"""
    from collections import defaultdict
    seg_sql = " AND game_season_code=%s" if season_code in (1, 2) else ""
    params: tuple = (season, kind_code, str(season_code)) if season_code in (1, 2) else (season, kind_code)
    with conn() as c:
        games = c.execute(
            "SELECT home_team_code, home_team_name, away_team_code, away_team_name, home_score, away_score "
            f"FROM cpbl.games WHERE year=%s AND kind_code=%s AND home_score+away_score>0{seg_sql}",
            params,
        ).fetchall()
    rec: dict = defaultdict(lambda: {
        "name": None, "w": 0, "l": 0, "t": 0, "rs": 0, "ra": 0,
        "hw": 0, "hl": 0, "ht": 0, "aw": 0, "al": 0, "at": 0,
        "h2h": defaultdict(lambda: [0, 0, 0]),
    })
    for hc, hn, ac, an, hs, as_ in games:
        h, a = rec[hc], rec[ac]
        h["name"], a["name"] = hn, an
        h["rs"] += hs; h["ra"] += as_; a["rs"] += as_; a["ra"] += hs
        if hs > as_:
            h["w"] += 1; h["hw"] += 1; a["l"] += 1; a["al"] += 1
            h["h2h"][ac][0] += 1; a["h2h"][hc][1] += 1
        elif as_ > hs:
            a["w"] += 1; a["aw"] += 1; h["l"] += 1; h["hl"] += 1
            a["h2h"][hc][0] += 1; h["h2h"][ac][1] += 1
        else:
            h["t"] += 1; h["ht"] += 1; a["t"] += 1; a["at"] += 1
            h["h2h"][ac][2] += 1; a["h2h"][hc][2] += 1
    items = []
    for tc, r in rec.items():
        dec = r["w"] + r["l"]
        items.append({
            "team_code": tc, "team_name": r["name"], "g": r["w"] + r["l"] + r["t"],
            "w": r["w"], "t": r["t"], "l": r["l"],
            "win_pct": round(r["w"] / dec, 3) if dec else None,
            "run_diff": r["rs"] - r["ra"],
            "home_record": f'{r["hw"]}-{r["ht"]}-{r["hl"]}', "away_record": f'{r["aw"]}-{r["at"]}-{r["al"]}',
            "elim": None, "streak": None, "last10": None,
            "h2h": {opp: f"{v[0]}-{v[2]}-{v[1]}" for opp, v in r["h2h"].items()},
        })
    items.sort(key=lambda x: (x["win_pct"] or 0, x["run_diff"]), reverse=True)
    lead_w, lead_l = (items[0]["w"], items[0]["l"]) if items else (0, 0)
    for i, it in enumerate(items, 1):
        it["rank"] = i
        it["gb"] = round(((lead_w - it["w"]) + (it["l"] - lead_l)) / 2, 1)
    return items


@router.get("/api/v1/seasons")
def seasons(kind_code: str = Query("A")) -> dict:
    """有逐場資料的年份清單（供歷史年份選擇器）。"""
    with conn() as c:
        years = [r[0] for r in c.execute(
            "SELECT DISTINCT year FROM cpbl.games WHERE kind_code=%s AND home_score+away_score>0 "
            "ORDER BY year DESC", (kind_code,),
        ).fetchall()]
    return {"years": years}


def _half_progress(season: int, game_season_code: str, kind_code: str) -> dict[str, int]:
    """回傳 {team_code: 該半季剩餘未打場數}。供半季冠軍/提前封王判定。"""
    with conn() as c:
        rows = c.execute(
            """
            SELECT tc, count(*) FILTER (WHERE NOT done) AS remaining FROM (
                SELECT home_team_code AS tc, home_score + away_score > 0 AS done
                  FROM cpbl.games WHERE year=%s AND kind_code=%s AND game_season_code=%s
                UNION ALL
                SELECT away_team_code, home_score + away_score > 0
                  FROM cpbl.games WHERE year=%s AND kind_code=%s AND game_season_code=%s
            ) x GROUP BY tc
            """,
            (season, kind_code, game_season_code, season, kind_code, game_season_code),
        ).fetchall()
    return {tc: rem for tc, rem in rows}


def _annotate_half_champion(items: list[dict], remaining: dict[str, int]) -> dict:
    """標記半季冠軍：全部完賽 → 定案冠軍；未完賽但領先隊勝場已無人能追平 → 提前封王。

    以勝場數為準（半季賽程各隊固定同量，clinch 時領先隊亦為勝率首位）；在領先隊
    `is_champion` 上做記號，回傳 {finalized, clinched, champion_code}。
    """
    finalized = sum(remaining.values()) == 0
    leader = items[0]
    lw = leader.get("w") or 0
    clinched = all(
        lw > (it.get("w") or 0) + remaining.get(it["team_code"], 0)
        for it in items[1:]
    )
    champion_code = leader["team_code"] if (finalized or clinched) else None
    if champion_code:
        leader["is_champion"] = True
    return {"finalized": finalized, "clinched": clinched, "champion_code": champion_code}


@router.get("/api/v1/standings")
def official_standings(
    season: int = Query(DEFAULT_SEASON),
    season_code: int = Query(0, ge=0, le=2, description="0=全年 1=上半季 2=下半季"),
    kind_code: str = Query("A"),
) -> dict:
    """官方球隊戰績；歷史年份(無官方資料)退回由 games 即時算全年/半季戰績（結果 only）。

    半季（season_code 1/2）另回傳 `half`：是否完賽、是否提前封王、半季冠軍隊代碼。
    """
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT * FROM cpbl.team_standings WHERE year=%s AND kind_code=%s AND season_code=%s "
            "ORDER BY rank",
            (season, kind_code, season_code),
        )
        items = _dicts(cur)
    if not items:
        items = _computed_standings(season, kind_code, season_code)  # 歷史退回 games 即時算
    half = None
    if season_code in (1, 2) and items:
        half = _annotate_half_champion(items, _half_progress(season, str(season_code), kind_code))
    return {"season": season, "season_code": season_code, "items": items, "half": half}


@router.get("/api/v1/standings-trend")
def standings_trend(
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A"),
) -> dict:
    """各隊逐日累積戰績走勢（勝-敗差，即高於 .500 的場數）。未出賽日沿用前值。"""
    with conn() as c:
        games = c.execute(
            "SELECT game_date, home_team_code, away_team_code, home_score, away_score, "
            "home_team_name, away_team_name "
            "FROM cpbl.games WHERE year=%s AND kind_code=%s AND home_score+away_score>0 "
            "ORDER BY game_date, game_sno",
            (season, kind_code),
        ).fetchall()
    by_date: dict = {}
    teams: set[str] = set()
    names: dict[str, str] = {}  # code → 該年隊名（era 名）
    for gd, hc, ac, hs, as_, hn, an in games:
        by_date.setdefault(gd, []).append((hc, ac, hs, as_))
        teams.add(hc)
        teams.add(ac)
        names[hc], names[ac] = hn, an
    wl: dict[str, int] = dict.fromkeys(teams, 0)
    points: list[dict] = []
    for gd in sorted(by_date):
        for hc, ac, hs, as_ in by_date[gd]:
            if hs > as_:
                wl[hc] += 1
                wl[ac] -= 1
            elif as_ > hs:
                wl[hc] -= 1
                wl[ac] += 1
        points.append({"date": gd.strftime("%m-%d"), **wl})
    ordered = sorted(teams, key=lambda t: -wl[t])
    return {"season": season, "teams": ordered, "names": names, "points": points}
