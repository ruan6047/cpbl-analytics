"""戰績：即時彙整榜、官方戰績（含上下半季/勝差）、戰績走勢。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _dicts
from cpbl.api.rows import _team_advanced
from cpbl.db import conn
from cpbl.models import matchup

router = APIRouter()


@router.get("/api/v1/season/standings")
def season_standings(season: int = Query(DEFAULT_SEASON)) -> dict:
    """本季戰績榜（games 即時彙整 + team_current 團隊進階：OPS/ERA/WHIP）。"""
    stats = matchup.team_stats(season)
    adv = _team_advanced(season)
    rows = [
        {
            "code": c, "name": v["name"], "w": v["w"], "l": v["l"], "g": v["g"],
            "win_pct": round(v["win_pct"], 3),
            "rs_pg": round(v["rs_pg"], 2), "ra_pg": round(v["ra_pg"], 2),
            "run_diff": round(v["rs_pg"] - v["ra_pg"], 2),
            "form": v["last10"],
            "ops": adv.get(c, {}).get("ops"),
            "era": adv.get(c, {}).get("era"),
            "whip": adv.get(c, {}).get("whip"),
        }
        for c, v in stats.items()
    ]
    rows.sort(key=lambda r: (r["win_pct"], r["run_diff"]), reverse=True)
    return {"season": season, "standings": rows}
def _computed_standings(season: int, kind_code: str) -> list[dict]:
    """歷史年份無官方 team_standings → 由 games 逐場結果即時算全年戰績（結果 only）。"""
    from collections import defaultdict
    with conn() as c:
        games = c.execute(
            "SELECT home_team_code, home_team_name, away_team_code, away_team_name, home_score, away_score "
            "FROM cpbl.games WHERE year=%s AND kind_code=%s AND home_score+away_score>0",
            (season, kind_code),
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
    """官方球隊戰績；歷史年份(無官方資料)退回由 games 即時算全年戰績（結果 only）。

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
    if not items and season_code == 0:
        items = _computed_standings(season, kind_code)  # 歷史退回 games 即時算
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
