"""FastAPI 服務：子專案契約 /api/info + 本季數據 + 賽果預測端點。

/api/info 是主站 InfoPoller 每 5 分鐘輪詢的端點，metrics 展示這個 live 資料
產品的狀態：收錄場次、本季完成數、投打/團隊涵蓋、今日預測數、資料新鮮度。
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from cpbl import __version__
from cpbl.config import settings
from cpbl.db import conn
from cpbl.features.outcome import CANDIDATE_FEATURES, FEATURE_DESC
from cpbl.models import matchup, outcome

DEFAULT_SEASON = _date.today().year

app = FastAPI(title="CPBL Analytics", version=__version__)

# 公開唯讀 API；dev 時前端跨埠(:3000→:4001)需 CORS。prod 同源(經 nginx)不受影響。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _parse_features(features: str) -> list[str]:
    return [f.strip() for f in features.split(",") if f.strip()]


def _scalar(sql: str, params: tuple = ()) -> Any:
    with conn() as c:
        cur = c.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


@app.get("/api/info")
def info() -> dict:
    """主站 InfoPoller 契約。永遠回 200；metrics 展示這個 live 資料產品的狀態。"""
    metrics: dict[str, Any] = {}
    status = "running"
    try:
        season = DEFAULT_SEASON
        games = _scalar("SELECT count(*) FROM cpbl.games") or 0
        metrics["games_indexed"] = games
        metrics["seasons_covered"] = _scalar("SELECT count(DISTINCT year) FROM cpbl.games") or 0
        metrics["current_season"] = season
        metrics["season_games_completed"] = _scalar(
            "SELECT count(*) FROM cpbl.games WHERE year = %s AND home_score + away_score > 0", (season,)
        ) or 0
        metrics["teams_tracked"] = _scalar(
            "SELECT count(*) FROM cpbl.team_current WHERE year = %s", (season,)
        ) or 0
        metrics["pitchers_tracked"] = _scalar(
            "SELECT count(*) FROM cpbl.pitching_current WHERE year = %s", (season,)
        ) or 0
        metrics["batters_tracked"] = _scalar(
            "SELECT count(*) FROM cpbl.batting_current WHERE year = %s", (season,)
        ) or 0
        metrics["matchups_indexed"] = _scalar(
            "SELECT count(*) FROM cpbl.batter_pitcher_matchups"
        ) or 0
        metrics["player_splits_indexed"] = (
            (_scalar("SELECT count(*) FROM cpbl.batting_splits") or 0)
            + (_scalar("SELECT count(*) FROM cpbl.pitching_splits") or 0)
        )
        metrics["predictions_today"] = _scalar(
            "SELECT count(*) FROM cpbl.games "
            "WHERE year = %s AND home_score + away_score = 0 AND game_date = CURRENT_DATE", (season,)
        ) or 0
        last_game = _scalar(
            "SELECT max(game_date) FROM cpbl.games WHERE home_score + away_score > 0"
        )
        metrics["last_game_date"] = last_game.isoformat() if last_game else None
        try:  # refresh_log 可能尚未 migrate，獨立保護避免拖垮整個 info
            last_refresh = _scalar("SELECT max(refreshed_at) FROM cpbl.refresh_log WHERE ok")
            metrics["last_refresh"] = last_refresh.isoformat() if last_refresh else None
        except Exception:  # noqa: BLE001
            metrics["last_refresh"] = None

        if games == 0:
            status = "maintenance"  # 尚未匯入任何賽事
    except Exception:  # noqa: BLE001 — info 端點不可拋錯，退化即可
        status = "maintenance"

    return {"status": status, "version": settings.app_version, "metrics": metrics}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/v1/projections/batting")
def batting_projections(
    year: int | None = Query(None, description="目標季；省略則取最新一版的最大目標季"),
    stat: str = Query("ops", pattern="^(avg|obp|slg|ops)$"),
    limit: int = Query(25, ge=1, le=200),
) -> dict:
    """最新模型版本的打擊投影排行。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT id FROM cpbl.model_versions ORDER BY trained_at DESC LIMIT 1")
        mv = cur.fetchone()
        if not mv:
            return {"model_version": None, "items": []}
        model_version = mv[0]

        if year is None:
            cur.execute(
                "SELECT max(target_year) FROM cpbl.projections WHERE model_version = %s AND actual IS NULL",
                (model_version,),
            )
            r = cur.fetchone()
            year = r[0] if r and r[0] else None

        cur.execute(
            """
            SELECT pr.player_id, p.name, pr.predicted, pr.actual
            FROM cpbl.projections pr
            JOIN cpbl.players p ON p.id = pr.player_id
            WHERE pr.model_version = %s AND pr.stat = %s AND pr.target_year = %s
            ORDER BY pr.predicted DESC
            LIMIT %s
            """,
            (model_version, stat, year, limit),
        )
        items = [
            {"player_id": pid, "name": name, "predicted": round(pred, 4),
             "actual": round(act, 4) if act is not None else None}
            for pid, name, pred, act in cur.fetchall()
        ]
    return {"model_version": model_version, "stat": stat, "target_year": year, "items": items}


@app.get("/api/v1/season/batting-leaders")
def batting_leaders(
    season: int = Query(DEFAULT_SEASON),
    sort: str = Query("ops", pattern="^(ops|avg|obp|slg|hr|rbi|r|h|sb|bb|so)$"),
    min_pa: int = Query(30, ge=0, description="最低打席（排行用；0=全名單）"),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """本季打者排行（batting_current，全名單;預設過濾低打席避免雜訊）。"""
    def f(v):
        return float(v) if v is not None else None

    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT b.player_id, b.name, t.name, b.g, b.pa, b.ab, b.r, b.h, b.b2, b.b3,
                   b.hr, b.rbi, b.bb, b.so, b.sb, b.cs, b.avg, b.obp, b.slg, b.ops,
                   b.tb, b.ibb, b.hbp, b.sf, b.sh, b.gidp, b.k_pct, b.bb_pct
            FROM cpbl.batting_current b
            LEFT JOIN cpbl.team_current t ON t.team_code = b.team_code AND t.year = b.year
            WHERE b.year = %s AND b.{sort} IS NOT NULL AND COALESCE(b.pa, 0) >= %s
            ORDER BY b.{sort} DESC NULLS LAST
            LIMIT %s
            """,
            (season, min_pa, limit),
        )
        items = [
            {"player_id": r[0], "name": r[1], "team": r[2], "g": r[3], "pa": r[4], "ab": r[5],
             "r": r[6], "h": r[7], "b2": r[8], "b3": r[9], "hr": r[10], "rbi": r[11], "bb": r[12],
             "so": r[13], "sb": r[14], "cs": r[15], "avg": f(r[16]), "obp": f(r[17]),
             "slg": f(r[18]), "ops": f(r[19]), "tb": r[20], "ibb": r[21], "hbp": r[22], "sf": r[23],
             "sh": r[24], "gidp": r[25], "k_pct": f(r[26]), "bb_pct": f(r[27])}
            for r in cur.fetchall()
        ]
    return {"season": season, "sort": sort, "items": items}


@app.get("/api/v1/season/pitching-leaders")
def pitching_leaders(
    season: int = Query(DEFAULT_SEASON),
    sort: str = Query("era", pattern="^(era|whip|w|sv|hld|k9|gs|ip)$"),
    min_ip: float = Query(20, ge=0, description="最低投球局數"),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """本季投手排行（pitching_current 全名單）。ERA/WHIP 越低越前。"""
    direction = "ASC" if sort in ("era", "whip") else "DESC"
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT p.player_id, p.name, t.name, p.g, p.gs, p.cg, p.sho, p.w, p.l, p.sv, p.hld,
                   p.ip, p.era, p.whip, p.k9, p.pa, p.np, p.h, p.hr, p.bb, p.ibb, p.hbp, p.so,
                   p.wp, p.bk, p.r, p.er, p.go, p.ao, p.goao
            FROM cpbl.pitching_current p
            LEFT JOIN cpbl.team_current t ON t.team_code = p.team_code AND t.year = p.year
            WHERE p.year = %s AND p.{sort} IS NOT NULL AND COALESCE(p.ip, 0) >= %s
            ORDER BY p.{sort} {direction} NULLS LAST
            LIMIT %s
            """,
            (season, min_ip, limit),
        )
        fl = lambda v: float(v) if v is not None else None  # noqa: E731
        items = [
            {"player_id": r[0], "name": r[1], "team": r[2], "g": r[3], "gs": r[4], "cg": r[5],
             "sho": r[6], "w": r[7], "l": r[8], "sv": r[9], "hld": r[10],
             "ip": fl(r[11]), "era": fl(r[12]), "whip": fl(r[13]),
             "k9": round(float(r[14]), 2) if r[14] is not None else None,
             "pa": r[15], "np": r[16], "h": r[17], "hr": r[18], "bb": r[19], "ibb": r[20],
             "hbp": r[21], "so": r[22], "wp": r[23], "bk": r[24], "r": r[25], "er": r[26],
             "go": r[27], "ao": r[28], "goao": fl(r[29])}
            for r in cur.fetchall()
        ]
    return {"season": season, "sort": sort, "items": items}


@app.get("/api/v1/season/fielding")
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


@app.get("/api/v1/outcome/features")
def outcome_features() -> dict:
    """賽果預測的候選特徵清單（含說明，給前端 checkbox + tooltip）。"""
    return {
        "features": [
            {"key": k, "label": label, "desc": FEATURE_DESC.get(k, "")}
            for k, label in CANDIDATE_FEATURES
        ]
    }


@app.get("/api/v1/outcome/evaluate")
def outcome_evaluate(features: str = Query(..., description="逗號分隔的特徵 key")) -> dict:
    """用選定特徵子集即時 fit + 時間切分回測。"""
    try:
        return outcome.evaluate(_parse_features(features))
    except ValueError as e:
        return {"error": str(e)}


@app.get("/api/v1/outcome/teams")
def outcome_teams(season: int = Query(DEFAULT_SEASON)) -> dict:
    """當季球隊清單（給任選兩隊模擬的下拉選單）。"""
    return {"season": season, "teams": matchup.list_teams(season)}


def _team_advanced(season: int) -> dict[str, dict]:
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT team_code, bat_ops, bat_hr, pit_era, pit_whip FROM cpbl.team_current WHERE year = %s",
            (season,),
        )
        return {
            code: {"ops": float(ops) if ops is not None else None,
                   "hr": hr,
                   "era": float(era) if era is not None else None,
                   "whip": float(whip) if whip is not None else None}
            for code, ops, hr, era, whip in cur.fetchall()
        }


@app.get("/api/v1/season/standings")
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


@app.get("/api/v1/outcome/matchups")
def outcome_matchups(
    features: str = Query(..., description="逗號分隔的變因 key"),
    season: int = Query(DEFAULT_SEASON),
    limit: int = Query(20, ge=1, le=60),
) -> dict:
    """今日起未開打賽事的對戰卡（含雙方真實數字 + 預設權重 + 標準化值 z）。"""
    try:
        return matchup.upcoming(_parse_features(features), season, limit)
    except ValueError as e:
        return {"error": str(e)}


@app.get("/api/v1/outcome/simulate")
def outcome_simulate(
    home: str = Query(..., description="主隊 team_code"),
    away: str = Query(..., description="客隊 team_code"),
    features: str = Query(...),
    season: int = Query(DEFAULT_SEASON),
) -> dict:
    """任選兩隊的假想對戰卡（用當季到當日統計）。"""
    try:
        return matchup.simulate(home, away, _parse_features(features), season)
    except ValueError as e:
        return {"error": str(e)}


@app.get("/api/v1/players/{player_id}/batting")
def player_batting(player_id: str) -> dict:
    """單一球員的逐年打擊史。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT id, name, bats, throws, birthday FROM cpbl.players WHERE id = %s", (player_id,))
        p = cur.fetchone()
        if not p:
            return {"player": None, "seasons": []}
        cur.execute(
            """
            SELECT year, sum(g), sum(pa), sum(ab), sum(h), sum(hr), sum(rbi), sum(bb), sum(so),
                   round(sum(h)::numeric / NULLIF(sum(ab),0), 3) AS avg
            FROM cpbl.batting_seasons WHERE player_id = %s
            GROUP BY year ORDER BY year
            """,
            (player_id,),
        )
        seasons = [
            {"year": y, "g": g, "pa": pa, "ab": ab, "h": h, "hr": hr, "rbi": rbi,
             "bb": bb, "so": so, "avg": float(avg) if avg is not None else None}
            for y, g, pa, ab, h, hr, rbi, bb, so, avg in cur.fetchall()
        ]
    return {
        "player": {"id": p[0], "name": p[1], "bats": p[2], "throws": p[3],
                   "birthday": p[4].isoformat() if p[4] else None},
        "seasons": seasons,
    }


# ---------- 對戰各隊 / 分項 / 投打對決 ----------

def _dicts(cur) -> list[dict]:
    """cursor → list[dict]，欄名取自 cursor.description；real 已是 float。"""
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


@app.get("/api/v1/players/roster")
def roster(season: int = Query(DEFAULT_SEASON)) -> dict:
    """本季登錄打者/投手名單（投打對決與細項頁的選單來源）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT b.player_id, b.name, t.name FROM cpbl.batting_current b
            LEFT JOIN cpbl.team_current t ON t.team_code = b.team_code AND t.year = b.year
            WHERE b.year = %s ORDER BY b.name
            """, (season,),
        )
        batters = [{"id": i, "name": n, "team": tm} for i, n, tm in cur.fetchall()]
        cur.execute(
            """
            SELECT p.player_id, p.name, t.name FROM cpbl.pitching_current p
            LEFT JOIN cpbl.team_current t ON t.team_code = p.team_code AND t.year = p.year
            WHERE p.year = %s ORDER BY p.name
            """, (season,),
        )
        pitchers = [{"id": i, "name": n, "team": tm} for i, n, tm in cur.fetchall()]
    return {"season": season, "batters": batters, "pitchers": pitchers}


@app.get("/api/v1/matchups")
def matchups(
    hitter: str = Query(..., description="打者 player_id"),
    pitcher: str = Query(..., description="投手 player_id"),
) -> dict:
    """單組打者 vs 投手的生涯對戰（A/C/E 各一列）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT * FROM cpbl.batter_pitcher_matchups WHERE hitter_acnt = %s AND pitcher_acnt = %s "
            "ORDER BY kind_code",
            (hitter, pitcher),
        )
        return {"hitter": hitter, "pitcher": pitcher, "items": _dicts(cur)}


@app.get("/api/v1/players/{player_id}/vs-team")
def player_vs_team(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
) -> dict:
    """選手對戰各隊成績（本季 A 例行賽）。role=batting/pitching。"""
    table = "batting_vs_team" if role == "batting" else "pitching_vs_team"
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"SELECT * FROM cpbl.{table} WHERE acnt = %s ORDER BY total_games DESC NULLS LAST",
            (player_id,),
        )
        return {"player_id": player_id, "role": role, "items": _dicts(cur)}


# 多賽別合併時要加總的計數欄位（比率欄不加總，之後重算）
_BSPLIT_SUM = ["plate_appearances", "at_bats", "hits", "rbi", "singles", "doubles", "triples",
               "home_runs", "total_bases", "sac_hit", "sac_fly", "bb", "ibb", "hbp", "so",
               "ground_outs", "fly_outs"]
_PSPLIT_SUM = ["wins", "loses", "starts", "complete_games", "shutouts", "save_ok",
               "inning_pitched_cnt", "inning_pitched_div3", "plate_appearances", "pitch_cnt",
               "strikes", "balls", "hits", "home_runs", "sac_hit", "sac_fly", "bb", "ibb", "hbp",
               "so", "wild_pitch", "balk", "runs", "earned_runs"]


def _round(x: float | None, n: int) -> float | None:
    return round(x, n) if x is not None else None


def _merge_splits(rows: list[dict], role: str) -> list[dict]:
    """跨賽別合併：依 (item_group_code, item_index) 加總計數欄位，再重算比率。"""
    sum_cols = _BSPLIT_SUM if role == "batting" else _PSPLIT_SUM
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in rows:
        key = (r["item_group_code"], r["item_index"])
        g = groups.get(key)
        if g is None:
            groups[key] = dict(r)
            order.append(key)
        else:
            for col in sum_cols:
                g[col] = (g.get(col) or 0) + (r.get(col) or 0)

    out: list[dict] = []
    for key in order:
        g = groups[key]
        if role == "batting":
            ab, h = g.get("at_bats") or 0, g.get("hits") or 0
            bb, hbp, sf = g.get("bb") or 0, g.get("hbp") or 0, g.get("sac_fly") or 0
            tb, go, fo = g.get("total_bases") or 0, g.get("ground_outs"), g.get("fly_outs")
            obp_den = ab + bb + hbp + sf
            g["avg"] = _round(h / ab, 3) if ab else None
            g["obp"] = _round((h + bb + hbp) / obp_den, 4) if obp_den else None
            g["slg"] = _round(tb / ab, 4) if ab else None
            g["ops"] = _round((g["obp"] or 0) + (g["slg"] or 0), 4) if ab else None
            g["goao"] = _round(go / fo, 2) if fo else None
        else:
            outs = (g.get("inning_pitched_cnt") or 0) * 3 + (g.get("inning_pitched_div3") or 0)
            g["inning_pitched_cnt"], g["inning_pitched_div3"] = outs // 3, outs % 3
        out.append(g)
    return out


@app.get("/api/v1/players/{player_id}/splits")
def player_splits(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
    year: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", description="賽別，可逗號多選如 A,C,E（多選時加總計數並重算比率）"),
) -> dict:
    """選手分項成績（主客/左右/壘上/局數/月份…）。year=9999 為生涯累計；
    kind_code 可多選，多選時跨賽別合併（計數相加、比率重算）。"""
    kinds = [k for k in (s.strip() for s in kind_code.split(",")) if k in ("A", "C", "E")] or ["A"]
    table = "batting_splits" if role == "batting" else "pitching_splits"
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"SELECT * FROM cpbl.{table} WHERE acnt = %s AND year = %s AND kind_code = ANY(%s) "
            "ORDER BY item_group_code, item_index",
            (player_id, year, kinds),
        )
        rows = _dicts(cur)
    items = rows if len(kinds) == 1 else _merge_splits(rows, role)
    return {"player_id": player_id, "role": role, "year": year,
            "kind_code": ",".join(kinds), "items": items}


@app.get("/api/v1/players/{player_id}/profile")
def player_profile(player_id: str, season: int = Query(DEFAULT_SEASON)) -> dict:
    """球員基本資料 + 角色（本季是否登錄為打者/投手），供個人頁標頭。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT b.player_id, b.name, t.name FROM cpbl.batting_current b
            LEFT JOIN cpbl.team_current t ON t.team_code = b.team_code AND t.year = b.year
            WHERE b.player_id = %s AND b.year = %s
            """, (player_id, season),
        )
        bat = cur.fetchone()
        cur.execute(
            """
            SELECT p.player_id, p.name, t.name FROM cpbl.pitching_current p
            LEFT JOIN cpbl.team_current t ON t.team_code = p.team_code AND t.year = p.year
            WHERE p.player_id = %s AND p.year = %s
            """, (player_id, season),
        )
        pit = cur.fetchone()
        cur.execute("SELECT name, bats, throws FROM cpbl.players WHERE id = %s", (player_id,))
        meta = cur.fetchone()
    if not bat and not pit and not meta:
        return {"player": None}
    name = (bat[1] if bat else None) or (pit[1] if pit else None) or (meta[0] if meta else None)
    team = (bat[2] if bat else None) or (pit[2] if pit else None)
    return {
        "player": {
            "id": player_id, "name": name, "team": team,
            "is_batter": bat is not None, "is_pitcher": pit is not None,
            "bats": meta[1] if meta else None, "throws": meta[2] if meta else None,
        }
    }


@app.get("/api/v1/players/{player_id}/matchups")
def player_matchups(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
    kind_code: str = Query("A", pattern="^(A|C|E)$"),
    season: int = Query(DEFAULT_SEASON),
) -> dict:
    """某球員的全部投打對決（role=batting：對戰各投手；pitching：對戰各打者）。
    對手球隊名以本季 team_current 對照；同隊不可能對戰故天然排除。"""
    self_col, opp_col = ("hitter_acnt", "pitcher") if role == "batting" else ("pitcher_acnt", "hitter")
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT m.{opp_col}_acnt AS opp_id, m.{opp_col}_name AS opp_name, t.name AS opp_team,
                   m.plate_appearances, m.at_bats, m.hits, m.home_runs, m.rbi, m.bb, m.so,
                   m.avg, m.obp, m.slg, m.ops, m.whiff_pct
            FROM cpbl.batter_pitcher_matchups m
            LEFT JOIN cpbl.team_current t ON t.team_code = m.{opp_col}_team_no AND t.year = %s
            WHERE m.{self_col} = %s AND m.kind_code = %s
            ORDER BY m.plate_appearances DESC NULLS LAST
            """,
            (season, player_id, kind_code),
        )
        return {"player_id": player_id, "role": role, "kind_code": kind_code, "items": _dicts(cur)}


@app.get("/api/v1/players/{player_id}/season")
def player_season(player_id: str, season: int = Query(DEFAULT_SEASON)) -> dict:
    """球員本季成績（batting_current / pitching_current 完整列），供個人頁成績卡。"""
    out: dict[str, Any] = {"player_id": player_id, "season": season, "batting": None, "pitching": None}
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT * FROM cpbl.batting_current WHERE player_id = %s AND year = %s",
                    (player_id, season))
        b = _dicts(cur)
        cur.execute("SELECT * FROM cpbl.pitching_current WHERE player_id = %s AND year = %s",
                    (player_id, season))
        p = _dicts(cur)
    if b:
        out["batting"] = b[0]
    if p:
        out["pitching"] = p[0]
    return out


# ---------- 每場賽況 ----------

@app.get("/api/v1/games/recent")
def games_recent(
    limit: int = Query(40, ge=1, le=200),
    season: int = Query(DEFAULT_SEASON),
) -> dict:
    """近期已完成比賽列表（供賽況頁選擇）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT year, kind_code, game_sno, game_date,
                   away_team_name, away_team_code, away_score,
                   home_team_name, home_team_code, home_score
            FROM cpbl.games
            WHERE year = %s AND home_score + away_score > 0
            ORDER BY game_date DESC, game_sno DESC
            LIMIT %s
            """,
            (season, limit),
        )
        return {"season": season, "items": _dicts(cur)}


@app.get("/api/v1/games/{game_sno}/live")
def game_live(
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|C|E)$"),
) -> dict:
    """單場賽況：賽事資訊 + 逐局比分 + 逐打席事件流。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT year, kind_code, game_sno, game_date, venue,
                   away_team_name, away_team_code, away_score,
                   home_team_name, home_team_code, home_score
            FROM cpbl.games WHERE year = %s AND kind_code = %s AND game_sno = %s
            """,
            (season, kind_code, game_sno),
        )
        g = _dicts(cur)
        cur.execute(
            "SELECT * FROM cpbl.game_scoreboard WHERE year=%s AND kind_code=%s AND game_sno=%s "
            "ORDER BY visiting_home_type, inning_seq",
            (season, kind_code, game_sno),
        )
        scoreboard = _dicts(cur)
        cur.execute(
            "SELECT * FROM cpbl.game_livelog WHERE year=%s AND kind_code=%s AND game_sno=%s "
            "ORDER BY main_event_no",
            (season, kind_code, game_sno),
        )
        livelog = _dicts(cur)
    return {"game": g[0] if g else None, "scoreboard": scoreboard, "livelog": livelog}
