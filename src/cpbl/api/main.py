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
        metrics["predictions_today"] = _scalar(
            "SELECT count(*) FROM cpbl.games "
            "WHERE year = %s AND home_score + away_score = 0 AND game_date = CURRENT_DATE", (season,)
        ) or 0
        last_game = _scalar(
            "SELECT max(game_date) FROM cpbl.games WHERE home_score + away_score > 0"
        )
        metrics["last_game_date"] = last_game.isoformat() if last_game else None

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
    sort: str = Query("ops", pattern="^(ops|avg|obp|slg|hr|ops_plus)$"),
    min_pa: int = Query(30, ge=0, description="最低打席（排行用；0=全名單）"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """本季打者排行（batting_current，全名單;預設過濾低打席避免雜訊）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT b.player_id, b.name, t.name, b.pa, b.avg, b.obp, b.slg, b.ops,
                   b.hr, b.ops_plus, b.k_pct, b.bb_pct
            FROM cpbl.batting_current b
            LEFT JOIN cpbl.team_current t ON t.team_code = b.team_code AND t.year = b.year
            WHERE b.year = %s AND b.{sort} IS NOT NULL AND COALESCE(b.pa, 0) >= %s
            ORDER BY b.{sort} DESC
            LIMIT %s
            """,
            (season, min_pa, limit),
        )
        items = [
            {"player_id": pid, "name": name, "team": team, "pa": pa,
             "avg": float(avg) if avg is not None else None,
             "obp": float(obp) if obp is not None else None,
             "slg": float(slg) if slg is not None else None,
             "ops": float(ops) if ops is not None else None,
             "hr": hr,
             "ops_plus": float(opsp) if opsp is not None else None,
             "k_pct": float(kp) if kp is not None else None,
             "bb_pct": float(bbp) if bbp is not None else None}
            for pid, name, team, pa, avg, obp, slg, ops, hr, opsp, kp, bbp in cur.fetchall()
        ]
    return {"season": season, "sort": sort, "items": items}


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
