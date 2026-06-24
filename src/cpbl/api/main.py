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
from cpbl.models import matchup, outcome, special_records

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
    """單一球員的逐年打擊史（多隊年度合計，含 OBP/SLG/OPS）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT year, string_agg(DISTINCT team_name, '/') AS teams,
                   sum(g), sum(pa), sum(ab), sum(r), sum(h), sum(b2), sum(b3), sum(hr),
                   sum(rbi), sum(sb), sum(bb), sum(so), sum(tb), sum(hbp), sum(sf)
            FROM cpbl.batting_seasons WHERE player_id = %s
            GROUP BY year ORDER BY year
            """,
            (player_id,),
        )
        rows = cur.fetchall()
    seasons = []
    for y, teams, g, pa, ab, r, h, b2, b3, hr, rbi, sb, bb, so, tb, hbp, sf in rows:
        ab = ab or 0
        ob_den = ab + (bb or 0) + (hbp or 0) + (sf or 0)
        avg = round(h / ab, 3) if ab else None
        obp = round(((h or 0) + (bb or 0) + (hbp or 0)) / ob_den, 3) if ob_den else None
        slg = round((tb or 0) / ab, 3) if ab else None
        ops = round(obp + slg, 3) if obp is not None and slg is not None else None
        seasons.append({"year": y, "teams": teams, "g": g, "pa": pa, "ab": ab, "r": r,
                        "h": h, "b2": b2, "b3": b3, "hr": hr, "rbi": rbi, "sb": sb,
                        "bb": bb, "so": so, "avg": avg, "obp": obp, "slg": slg, "ops": ops})
    return {"player_id": player_id, "seasons": seasons}


@app.get("/api/v1/players/{player_id}/pitching")
def player_pitching(player_id: str) -> dict:
    """單一球員的逐年投球史（多隊年度合計，ip 以 .1/.2 棒球記法正確換算）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT year, string_agg(DISTINCT team_name, '/') AS teams,
                   sum(g), sum(gs), sum(w), sum(l), sum(sv), sum(hld),
                   sum(trunc(ip) + (ip - trunc(ip)) * 10 / 3.0) AS real_ip,
                   sum(so), sum(h), sum(bb), sum(er)
            FROM cpbl.pitching_seasons WHERE player_id = %s
            GROUP BY year ORDER BY year
            """,
            (player_id,),
        )
        rows = cur.fetchall()
    seasons = []
    for y, teams, g, gs, w, l, sv, hld, rip, so, h, bb, er in rows:
        rip = float(rip) if rip is not None else 0.0
        era = round((er or 0) * 9 / rip, 2) if rip else None
        whip = round(((bb or 0) + (h or 0)) / rip, 2) if rip else None
        k9 = round((so or 0) * 9 / rip, 2) if rip else None
        outs = round(rip * 3)  # 真實局數 → 棒球 .1/.2 記法（.1=⅓、.2=⅔）
        ip_disp = f"{outs // 3}.{outs % 3}"
        seasons.append({"year": y, "teams": teams, "g": g, "gs": gs, "w": w, "l": l,
                        "sv": sv, "hld": hld, "ip": ip_disp, "so": so,
                        "era": era, "whip": whip, "k9": k9})
    return {"player_id": player_id, "seasons": seasons}


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


def _real_ip(ip: Any) -> float:
    """.1/.2 棒球記法局數 → 真實局數（.1=⅓、.2=⅔）。"""
    if ip is None:
        return 0.0
    ip = float(ip)
    whole = int(ip)
    return whole + round((ip - whole) * 10) / 3


@app.get("/api/v1/players/{player_id}/season")
def player_season(player_id: str, season: int = Query(DEFAULT_SEASON)) -> dict:
    """球員本季成績（batting_current / pitching_current 完整列），供個人頁成績卡。
    OPS+/ERA+/FIP 官網不提供，於此用聯盟平均即時計算（park-neutral 標準公式）。"""
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
            row = b[0]
            cur.execute("SELECT sum(ab), sum(h), sum(bb), sum(hbp), sum(sf), sum(tb) "
                        "FROM cpbl.batting_current WHERE year = %s", (season,))
            ab, h, bb, hbp, sf, tb = (x or 0 for x in cur.fetchone())
            lg_obp = (h + bb + hbp) / (ab + bb + hbp + sf) if (ab + bb + hbp + sf) else None
            lg_slg = tb / ab if ab else None
            o, s_ = row.get("obp"), row.get("slg")
            if o is not None and s_ is not None and lg_obp and lg_slg:
                row["ops_plus"] = round(100 * (float(o) / lg_obp + float(s_) / lg_slg - 1))
            out["batting"] = row

        if p:
            row = p[0]
            cur.execute("SELECT ip, er, hr, bb, hbp, so FROM cpbl.pitching_current "
                        "WHERE year = %s AND ip IS NOT NULL", (season,))
            lr = cur.fetchall()
            lg_ip = sum(_real_ip(r[0]) for r in lr)
            lg_era = sum(r[1] or 0 for r in lr) * 9 / lg_ip if lg_ip else None
            fip_c = (lg_era - (13 * sum(r[2] or 0 for r in lr)
                              + 3 * sum((r[3] or 0) + (r[4] or 0) for r in lr)
                              - 2 * sum(r[5] or 0 for r in lr)) / lg_ip) if lg_ip and lg_era else None
            era, rip = row.get("era"), _real_ip(row.get("ip"))
            if lg_era and era is not None and float(era) > 0:
                row["era_plus"] = round(100 * lg_era / float(era))
            if rip and fip_c is not None:
                row["fip"] = round((13 * (row.get("hr") or 0)
                                    + 3 * ((row.get("bb") or 0) + (row.get("hbp") or 0))
                                    - 2 * (row.get("so") or 0)) / rip + fip_c, 2)
            out["pitching"] = row
    return out


@app.get("/api/v1/players/{player_id}/fielding")
def player_fielding(player_id: str, season: int = Query(DEFAULT_SEASON)) -> dict:
    """球員本季守備（fielding_current，逐守位）。供個人頁守備卡。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT pos, g, tc, po, a, e, dp, tp, pb, cs, sba, fpct
            FROM cpbl.fielding_current
            WHERE player_id = %s AND year = %s
            ORDER BY g DESC NULLS LAST, tc DESC NULLS LAST
            """,
            (player_id, season),
        )
        items = [
            {"pos": pos, "g": g, "tc": tc, "po": po, "a": a, "e": e, "dp": dp,
             "tp": tp, "pb": pb, "cs": cs, "sba": sba,
             "fpct": float(fpct) if fpct is not None else None}
            for pos, g, tc, po, a, e, dp, tp, pb, cs, sba, fpct in cur.fetchall()
        ]
    return {"player_id": player_id, "season": season, "items": items}


# ---------- 每場賽況 ----------

@app.get("/api/v1/games/recent")
def games_recent(
    limit: int = Query(40, ge=1, le=600),
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A"),
) -> dict:
    """某年某層級已完成比賽列表（供賽況/歷史賽事瀏覽）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT year, kind_code, game_sno, game_date,
                   away_team_name, away_team_code, away_score,
                   home_team_name, home_team_code, home_score
            FROM cpbl.games
            WHERE year = %s AND kind_code = %s AND home_score + away_score > 0
            ORDER BY game_date DESC, game_sno DESC
            LIMIT %s
            """,
            (season, kind_code, limit),
        )
        return {"season": season, "items": _dicts(cur)}


@app.get("/api/v1/games/{game_sno}/live")
def game_live(
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|C|E|D)$"),
) -> dict:
    """單場賽況：賽事資訊 + 逐局比分 + 逐打席事件流 + 雙方 box score + 關鍵球員。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT year, kind_code, game_sno, game_date, venue,
                   away_team_name, away_team_code, away_score,
                   home_team_name, home_team_code, home_score,
                   home_starter_id, away_starter_id, winning_pitcher_id,
                   losing_pitcher_id, closer_id, mvp_id
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
        cur.execute(
            "SELECT * FROM cpbl.batting_gamelog WHERE year=%s AND kind_code=%s AND game_sno=%s "
            "ORDER BY visiting_home_type, plate_appearances DESC NULLS LAST, at_bats DESC NULLS LAST",
            (season, kind_code, game_sno),
        )
        batting = _dicts(cur)
        cur.execute(
            "SELECT * FROM cpbl.pitching_gamelog WHERE year=%s AND kind_code=%s AND game_sno=%s "
            "ORDER BY visiting_home_type, inning_pitched_cnt DESC NULLS LAST",
            (season, kind_code, game_sno),
        )
        pitching = _dicts(cur)
        # 關鍵球員 id → 名字
        people: dict[str, str] = {}
        if g:
            ids = [g[0].get(k) for k in ("home_starter_id", "away_starter_id", "winning_pitcher_id",
                                         "losing_pitcher_id", "closer_id", "mvp_id")]
            ids = [i for i in ids if i]
            if ids:
                cur.execute("SELECT id, name FROM cpbl.players WHERE id = ANY(%s)", (ids,))
                people = {pid: nm for pid, nm in cur.fetchall()}
        # 兩隊本季戰績（W-L + 近 10 場），缺則不放
        records: dict[str, dict] = {}
        if g:
            ts = matchup.team_stats(season)
            for code in (g[0].get("away_team_code"), g[0].get("home_team_code")):
                if code in ts:
                    records[code] = {"w": ts[code]["w"], "l": ts[code]["l"], "form": ts[code]["last10"]}
        # 出賽打者本季打擊率（batting_current），缺則不放
        batter_avg: dict[str, float] = {}
        bids = sorted({str(r["hitter_acnt"]) for r in livelog if r.get("hitter_acnt")})
        if bids:
            cur.execute("SELECT player_id, avg FROM cpbl.batting_current WHERE player_id = ANY(%s)", (bids,))
            batter_avg = {pid: float(a) for pid, a in cur.fetchall() if a is not None}
        # 逐球 TrackMan（部分球場未設置 → 空陣列；前端以 (投手,打者,局) 比對當前打席）
        # 名稱欄位有編碼問題，故只取以 acnt 比對與數值欄位，不取 *_name。
        cur.execute(
            """
            SELECT pitcher_acnt, hitter_acnt, inning_seq, pitch_cnt, ball_cnt, strike_cnt,
                   auto_pitch_type, rel_speed, plate_loc_side, plate_loc_height, pitch_call
            FROM cpbl.pitch_tracking
            WHERE year=%s AND kind_code=%s AND game_sno=%s
            ORDER BY pitcher_acnt, pitch_cnt
            """,
            (season, kind_code, game_sno),
        )
        tracking = _dicts(cur)
    return {"game": g[0] if g else None, "scoreboard": scoreboard, "livelog": livelog,
            "batting": batting, "pitching": pitching, "people": people,
            "records": records, "batter_avg": batter_avg,
            "has_tracking": len(tracking) > 0, "tracking": tracking}


@app.get("/api/v1/players/{player_id}/advanced")
def player_advanced(player_id: str, season: int = Query(DEFAULT_SEASON)) -> dict:
    """官方進階數據（stats.cpbl）+ 官方 PR。batting=進攻、pitching=被打。"""
    out: dict[str, Any] = {"player_id": player_id, "season": season,
                           "batting": None, "pitching": None}
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT * FROM cpbl.advanced_stats WHERE acnt = %s AND year = %s",
                    (player_id, season))
        for row in _dicts(cur):
            out[row["role"]] = row
    return out


# 好球帶（公尺座標近似）：左右 ±0.25、上下 0.45~1.05
_SWING = "('InPlay','FoulBallNotFieldable','FoulBallFieldable','StrikeSwinging')"
_CONTACT = "('InPlay','FoulBallNotFieldable','FoulBallFieldable')"


def _batted_result(content: str | None) -> str:
    """從逐球 content 文字判斷擊球結果：hr/3b/2b/1b/out。
    content 在 DB 為雙重編碼（UTF-8 bytes 被當 latin-1 存），讀取時先還原。"""
    try:
        c = (content or "").encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        c = content or ""
    if "全壘打" in c:
        return "hr"
    if "三壘安打" in c:
        return "3b"
    if "二壘安打" in c:
        return "2b"
    if "一壘安打" in c or "內野安打" in c:
        return "1b"
    return "out"


def _zone_result(pitch_call: str | None, content: str | None) -> str:
    """單球進壘結果分類：take(未揮棒)/whiff(揮空)/foul(界外)/hit(安打)/out(出局)。"""
    if pitch_call == "StrikeSwinging":
        return "whiff"
    if pitch_call in ("FoulBallNotFieldable", "FoulBallFieldable"):
        return "foul"
    if pitch_call == "InPlay":
        return "hit" if _batted_result(content) in ("hr", "3b", "2b", "1b") else "out"
    return "take"


@app.get("/api/v1/players/{player_id}/discipline")
def player_discipline(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
    season: int = Query(DEFAULT_SEASON),
) -> dict:
    """好球帶紀律（自 pitch_tracking 計算）。batting=該打者面對；pitching=該投手誘導。
    含揮棒/揮空/接觸/CSW/追打/帶內揮棒/好球帶比例，及進壘點散布。"""
    col = "hitter_acnt" if role == "batting" else "pitcher_acnt"
    pct = lambda a, b: round(a / b * 100, 1) if b else None  # noqa: E731
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT
              count(*) loc,
              count(*) tot,
              count(*) FILTER (WHERE pitch_call IN {_SWING}) sw,
              count(*) FILTER (WHERE pitch_call = 'StrikeSwinging') wh,
              count(*) FILTER (WHERE pitch_call IN {_CONTACT}) ct,
              count(*) FILTER (WHERE pitch_call IN ('StrikeCalled','StrikeSwinging')) csw,
              count(*) FILTER (WHERE iz) zone,
              count(*) FILTER (WHERE iz AND sw0) zsw,
              count(*) FILTER (WHERE (NOT iz) AND sw0) osw,
              count(*) FILTER (WHERE NOT iz) ozone
            FROM (
              SELECT pitch_call,
                     (abs(plate_loc_side) <= 0.21 AND plate_loc_height BETWEEN 0.5 AND 1.0) iz,
                     (pitch_call IN {_SWING}) sw0
              FROM cpbl.pitch_tracking
              WHERE {col} = %s AND year = %s AND kind_code = 'A' AND plate_loc_side IS NOT NULL
            ) q
            """,
            (player_id, season),
        )
        loc, tot, sw, wh, ct, csw, zone, zsw, osw, ozone = cur.fetchone()
        summary = {
            "pitches": tot, "located": loc,
            "swing_pct": pct(sw, loc), "whiff_pct": pct(wh, sw), "contact_pct": pct(ct, sw),
            "csw_pct": pct(csw, loc), "zone_pct": pct(zone, loc),
            "z_swing_pct": pct(zsw, zone), "chase_pct": pct(osw, ozone),
        }
        cur.execute(
            f"""
            SELECT plate_loc_side, plate_loc_height, pitch_call, content, hit_exit_speed
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = 'A' AND plate_loc_side IS NOT NULL
            """,
            (player_id, season),
        )
        _swset = {"InPlay", "FoulBallNotFieldable", "FoulBallFieldable", "StrikeSwinging"}
        points = [{"x": float(s), "y": float(h),
                   "sw": pc in _swset, "wh": pc == "StrikeSwinging",
                   "result": _zone_result(pc, ct), "ev": float(ev) if ev is not None else None}
                  for s, h, pc, ct, ev in cur.fetchall()]
        cur.execute(
            f"""
            SELECT hit_direction, hit_distance, hit_exit_speed, content
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = 'A' AND pitch_call = 'InPlay'
              AND hit_distance IS NOT NULL AND hit_direction IS NOT NULL
            """,
            (player_id, season),
        )
        spray = [{"dir": float(d), "dist": float(dist),
                  "ev": float(ev) if ev is not None else None, "result": _batted_result(ct)}
                 for d, dist, ev, ct in cur.fetchall()]
        # 擊球仰角 × 初速（barrel 散點）：InPlay 且有 LA+EV
        cur.execute(
            f"""
            SELECT hit_launch_angle, hit_exit_speed, content
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = 'A' AND pitch_call = 'InPlay'
              AND hit_launch_angle IS NOT NULL AND hit_exit_speed IS NOT NULL
            """,
            (player_id, season),
        )
        batted = [{"la": float(la), "ev": float(ev), "result": _batted_result(ct)}
                  for la, ev, ct in cur.fetchall()]
        # 擊球品質（打者）／球質（投手）：逐球樣本衍生
        cur.execute(
            f"""
            SELECT round(avg(hit_launch_angle)::numeric, 1), round(max(hit_distance)::numeric, 1),
                   round(avg(hit_exit_speed)::numeric, 1), round(avg(extension)::numeric, 2),
                   round(avg(rel_height)::numeric, 2), round(avg(rel_speed)::numeric, 1)
            FROM cpbl.pitch_tracking WHERE {col} = %s AND year = %s AND kind_code = 'A'
            """,
            (player_id, season),
        )
        la, maxd, ev, ext, relh, rels = cur.fetchone()
        fl = lambda v: float(v) if v is not None else None  # noqa: E731
        quality = {"avg_launch_angle": fl(la), "max_hit_dist": fl(maxd), "avg_exit_speed": fl(ev),
                   "avg_extension": fl(ext), "avg_rel_height": fl(relh), "avg_speed": fl(rels)}
    return {"player_id": player_id, "role": role, "summary": summary,
            "quality": quality, "points": points, "spray": spray, "batted": batted}


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


@app.get("/api/v1/seasons")
def seasons(kind_code: str = Query("A")) -> dict:
    """有逐場資料的年份清單（供歷史年份選擇器）。"""
    with conn() as c:
        years = [r[0] for r in c.execute(
            "SELECT DISTINCT year FROM cpbl.games WHERE kind_code=%s AND home_score+away_score>0 "
            "ORDER BY year DESC", (kind_code,),
        ).fetchall()]
    return {"years": years}


@app.get("/api/v1/standings")
def official_standings(
    season: int = Query(DEFAULT_SEASON),
    season_code: int = Query(0, ge=0, le=2, description="0=全年 1=上半季 2=下半季"),
    kind_code: str = Query("A"),
) -> dict:
    """官方球隊戰績；歷史年份(無官方資料)退回由 games 即時算全年戰績（結果 only）。"""
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
    return {"season": season, "season_code": season_code, "items": items}


@app.get("/api/v1/standings-trend")
def standings_trend(
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A"),
) -> dict:
    """各隊逐日累積戰績走勢（勝-敗差，即高於 .500 的場數）。未出賽日沿用前值。"""
    with conn() as c:
        games = c.execute(
            "SELECT game_date, home_team_code, away_team_code, home_score, away_score "
            "FROM cpbl.games WHERE year=%s AND kind_code=%s AND home_score+away_score>0 "
            "ORDER BY game_date, game_sno",
            (season, kind_code),
        ).fetchall()
    by_date: dict = {}
    teams: set[str] = set()
    for gd, hc, ac, hs, as_ in games:
        by_date.setdefault(gd, []).append((hc, ac, hs, as_))
        teams.add(hc)
        teams.add(ac)
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
    return {"season": season, "teams": ordered, "points": points}


@app.get("/api/v1/teams")
def teams_dim(active: bool = Query(True)) -> dict:
    """球隊維度（canonical）：代碼/簡稱/全名/隊色/字母。供前端取代硬編 team meta。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT team_code, short, full_name, nickname, color, letter, league, active "
            "FROM cpbl.team_dim" + (" WHERE active=true" if active else "") + " ORDER BY team_code"
        )
        return {"items": _dicts(cur)}


# 改名/轉賣視為同一支球隊：歷史代碼 → 現役 franchise 代碼（依 games 年份範圍實證）
_FRANCHISE = {
    "ACC011": "ACN011",                                    # 兄弟象 → 中信兄弟
    "AEE011": "AEO011", "AEG011": "AEO011", "AEM011": "AEO011",  # 俊國→興農→義大→富邦
    "AJJ011": "AJL011", "AJK011": "AJL011",                # 第一金剛→La New/Lamigo→樂天
}


def _franchise_of(code: str) -> str:
    return _FRANCHISE.get(code, code)


# 單一代碼內的改名（games 隊名已正規化、無法區分，故權威定義年代）
_ERA_SPLIT = {
    "AJK011": [("La New熊", 2004, 2010), ("Lamigo桃猿", 2011, 2019)],
}
# 現役 franchise → CPBL 前的前身（台灣大聯盟 TML 隊伍無 CPBL 資料，使用者定調放棄、不列）
_ORIGINS: dict[str, str] = {}


@app.get("/api/v1/teams/{code}/eras")
def team_eras(code: str, kind_code: str = Query("A")) -> dict:
    """球隊沿革：franchise（改名/轉賣視為同隊）各時期全名+年代+戰績。

    全名取自 cpbl.teams（games 隊名為縮寫/正規化）；單代碼內改名(La New/Lamigo)依
    _ERA_SPLIT 權威年代；味全等同代碼斷層依年份缺口斷代。
    """
    fc = _franchise_of(code)
    members = sorted({c for c in (set(_FRANCHISE) | set(_FRANCHISE.values()) | {fc}) if _franchise_of(c) == fc})
    from collections import defaultdict
    with conn() as c:
        games = c.execute(
            "SELECT year, home_team_code, away_team_code, home_score, away_score "
            "FROM cpbl.games WHERE kind_code=%s AND home_score+away_score>0 "
            "AND (home_team_code = ANY(%s) OR away_team_code = ANY(%s))",
            (kind_code, members, members),
        ).fetchall()
        names = dict(c.execute("SELECT team_id, name FROM cpbl.teams").fetchall())  # 3 碼 → 全名
    rec: dict = defaultdict(lambda: {"w": 0, "l": 0, "t": 0})
    for y, hc, ac, hs, as_ in games:
        if hc in members:
            rec[(hc, y)]["w" if hs > as_ else "l" if as_ > hs else "t"] += 1
        if ac in members:
            rec[(ac, y)]["w" if as_ > hs else "l" if hs > as_ else "t"] += 1

    def _tally(m: str, run: list[int], name: str) -> dict:
        w = sum(rec[(m, y)]["w"] for y in run)
        lo = sum(rec[(m, y)]["l"] for y in run)
        t = sum(rec[(m, y)]["t"] for y in run)
        return {"code": m, "name": name, "from": run[0], "to": run[-1],
                "w": w, "l": lo, "t": t, "win_pct": round(w / (w + lo), 3) if w + lo else None}

    eras = []
    for m in members:
        ys = sorted(y for (cc, y) in rec if cc == m)
        if not ys:
            continue
        full = names.get(m[:3], m)
        if m in _ERA_SPLIT:
            for nm, a, b in _ERA_SPLIT[m]:
                run = [y for y in ys if a <= y <= b]
                if run:
                    eras.append(_tally(m, run, nm))
        else:  # 依年份缺口斷代（味全解散前/重組後）
            run = [ys[0]]
            for y in ys[1:] + [None]:
                if y is not None and y == run[-1] + 1:
                    run.append(y)
                else:
                    eras.append(_tally(m, run, full))
                    if y is not None:
                        run = [y]
    eras.sort(key=lambda e: e["from"])
    return {"franchise": fc, "origins": _ORIGINS.get(fc), "eras": eras}


@app.get("/api/v1/venues")
def venues_dim() -> dict:
    """球場維度：場地材質/室內/城市/容量。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT venue, full_name, turf, indoor, city, capacity FROM cpbl.venue_dim ORDER BY venue"
        )
        return {"items": _dicts(cur)}


@app.get("/api/v1/special-records")
def special_records_endpoint(
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A"),
) -> dict:
    """各隊特殊戰績（即時從逐場 + 逐局算）：場地/比分型/賽況軌跡/終局/賽程/對手先發/系列賽。"""
    sit = special_records.team_situational(season, kind_code)
    with conn() as c:
        names = dict(c.execute(
            "SELECT team_code, team_name FROM cpbl.team_standings "
            "WHERE year=%s AND kind_code=%s AND season_code=0",
            (season, kind_code),
        ).fetchall())
    items = [
        {"team_code": tc, "team_name": names.get(tc, tc), **r}
        for tc, r in sit.items()
    ]
    items.sort(key=lambda x: -(x["natural"][0] + x["artificial"][0]))
    return {"season": season, "items": items}


@app.get("/api/v1/players/{player_id}/arsenal")
def player_arsenal(
    player_id: str,
    role: str = Query("pitching", pattern="^(batting|pitching)$"),
    season: int = Query(DEFAULT_SEASON),
) -> dict:
    """球種應對：自 pitch_tracking 按球種彙總。pitching=投手配球、batting=打者面對。
    回每球種：球數、用球/面對%、均速、(投手)轉速、揮空%、(打者)擊球初速。"""
    col = "pitcher_acnt" if role == "pitching" else "hitter_acnt"
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT tagged_pitch_type, count(*) n, avg(rel_speed), avg(spin_rate),
                   count(*) FILTER (WHERE pitch_call = 'StrikeSwinging'),
                   count(*) FILTER (WHERE pitch_call IN {_SWING}),
                   avg(hit_exit_speed)
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = 'A' AND tagged_pitch_type IS NOT NULL
            GROUP BY tagged_pitch_type ORDER BY n DESC
            """,
            (player_id, season),
        )
        rows = cur.fetchall()
    total = sum(r[1] for r in rows) or 1
    fl = lambda v: round(float(v), 1) if v is not None else None  # noqa: E731
    items = [
        {"pitch_type": pt, "n": n, "usage": round(n / total * 100, 1),
         "avg_speed": fl(spd), "avg_spin": round(float(spin)) if spin is not None else None,
         "whiff_pct": round(wh / sw * 100, 1) if sw else None,
         "avg_ev": fl(ev)}
        for pt, n, spd, spin, wh, sw, ev in rows
    ]
    return {"player_id": player_id, "role": role, "items": items}


def _count_bucket(b: int, s: int) -> str:
    """球數情境分桶（互斥、依優先序）。"""
    if s == 2:
        return "兩好球"
    if b == 0 and s == 0:
        return "第一球"
    if s > b:
        return "投手領先"
    if b > s:
        return "打者領先"
    return "平球數"


@app.get("/api/v1/players/{player_id}/pitch-mix")
def player_pitch_mix(
    player_id: str,
    role: str = Query("pitching", pattern="^(batting|pitching)$"),
    season: int = Query(DEFAULT_SEASON),
) -> dict:
    """配球傾向：不同球數情境下的速球／變化球占比。pitching=投手配球、batting=打者面對。"""
    col = "pitcher_acnt" if role == "pitching" else "hitter_acnt"
    order = ["第一球", "打者領先", "平球數", "投手領先", "兩好球"]
    agg: dict[str, dict[str, int]] = {k: {"fastball": 0, "breakingball": 0} for k in order}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT ball_cnt, strike_cnt, tagged_pitch_type
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = 'A' AND tagged_pitch_type IS NOT NULL
              AND ball_cnt IS NOT NULL AND strike_cnt IS NOT NULL
            """,
            (player_id, season),
        )
        for b, s, pt in cur.fetchall():
            bk = _count_bucket(b, s)
            if pt in ("fastball", "breakingball"):
                agg[bk][pt] += 1
    items = []
    for k in order:
        n = agg[k]["fastball"] + agg[k]["breakingball"]
        if not n:
            continue
        items.append({"bucket": k, "n": n,
                      "fastball": round(agg[k]["fastball"] / n * 100, 1),
                      "breakingball": round(agg[k]["breakingball"] / n * 100, 1)})
    return {"player_id": player_id, "role": role, "items": items}


@app.get("/api/v1/players/{player_id}/trend")
def player_trend(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A"),
) -> dict:
    """逐場「累積季成績」趨勢：逐場依日期累積計數型，並現算 rate stat。
    比月份桶（最多 ~6 點）細，每場一點且隨賽季收斂到當季數字。"""
    with conn() as c:
        cur = c.cursor()
        if role == "batting":
            cur.execute(
                """
                SELECT g.game_date,
                    sum(b.at_bats)     OVER w AS ab,
                    sum(b.hits)        OVER w AS h,
                    sum(b.bb)          OVER w AS bb,
                    sum(b.hbp)         OVER w AS hbp,
                    sum(b.sac_fly)     OVER w AS sf,
                    sum(b.total_bases) OVER w AS tb,
                    sum(b.home_runs)   OVER w AS hr,
                    sum(b.rbi)         OVER w AS rbi
                FROM cpbl.batting_gamelog b
                JOIN cpbl.games g
                  ON g.year = b.year AND g.kind_code = b.kind_code AND g.game_sno = b.game_sno
                WHERE b.hitter_acnt = %s AND b.year = %s AND b.kind_code = %s
                WINDOW w AS (ORDER BY g.game_date, b.game_sno
                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                ORDER BY g.game_date, b.game_sno
                """,
                (player_id, season, kind_code),
            )
            items = []
            for i, (d, ab, h, bb, hbp, sf, tb, hr, rbi) in enumerate(cur.fetchall(), 1):
                ab = ab or 0
                pa_ob = ab + (bb or 0) + (hbp or 0) + (sf or 0)
                avg = h / ab if ab else None
                obp = ((h or 0) + (bb or 0) + (hbp or 0)) / pa_ob if pa_ob else None
                slg = (tb or 0) / ab if ab else None
                ops = (obp + slg) if obp is not None and slg is not None else None
                r3 = lambda v: round(v, 3) if v is not None else None  # noqa: E731
                items.append({
                    "name": f"{d.month}/{d.day}", "g": i,
                    "avg": r3(avg), "obp": r3(obp), "slg": r3(slg), "ops": r3(ops),
                    "hits": h, "home_runs": hr, "rbi": rbi,
                })
        else:
            cur.execute(
                """
                SELECT g.game_date,
                    sum(p.inning_pitched_cnt)  OVER w AS ipc,
                    sum(p.inning_pitched_div3) OVER w AS ip3,
                    sum(p.earned_runs)         OVER w AS er,
                    sum(p.so)                  OVER w AS so,
                    sum(p.hits)                OVER w AS h,
                    sum(p.bb)                  OVER w AS bb
                FROM cpbl.pitching_gamelog p
                JOIN cpbl.games g
                  ON g.year = p.year AND g.kind_code = p.kind_code AND g.game_sno = p.game_sno
                WHERE p.pitcher_acnt = %s AND p.year = %s AND p.kind_code = %s
                WINDOW w AS (ORDER BY g.game_date, p.game_sno
                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                ORDER BY g.game_date, p.game_sno
                """,
                (player_id, season, kind_code),
            )
            items = []
            for i, (d, ipc, ip3, er, so, h, bb) in enumerate(cur.fetchall(), 1):
                ip = (ipc or 0) + (ip3 or 0) / 3
                era = round((er or 0) * 9 / ip, 2) if ip else None
                whip = round(((bb or 0) + (h or 0)) / ip, 2) if ip else None
                items.append({
                    "name": f"{d.month}/{d.day}", "g": i,
                    "era": era, "whip": whip, "so": so, "hits": h, "bb": bb,
                })
    return {"player_id": player_id, "role": role, "items": items}
