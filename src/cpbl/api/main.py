"""FastAPI 服務：子專案契約 /api/info + 本季數據 + 賽果預測端點。

/api/info 是主站 InfoPoller 每 5 分鐘輪詢的端點，metrics 展示這個 live 資料
產品的狀態：收錄場次、本季完成數、投打/團隊涵蓋、今日預測數、資料新鮮度。
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from cpbl import __version__, imports
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
        try:  # 賽事預測走查回測準確率（活的 ML 系統指標：模型 vs 全押主場）
            bt = _scalar("SELECT cv_metrics FROM cpbl.model_versions WHERE task='outcome' "
                         "ORDER BY trained_at DESC LIMIT 1")
            if bt:
                acc = max(mm["accuracy"] for mm in bt["models"] if mm["name"] != "全押主場")
                base = next(mm["accuracy"] for mm in bt["models"] if mm["name"] == "全押主場")
                metrics["outcome_model_accuracy"] = round(acc, 4)
                metrics["outcome_baseline_accuracy"] = round(base, 4)
                metrics["outcome_backtest_games"] = bt["n_test"]
        except Exception:  # noqa: BLE001
            pass

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
        cur.execute("SELECT id FROM cpbl.model_versions WHERE task = 'batting_projection' ORDER BY trained_at DESC LIMIT 1")
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


# 打者季成績原始計數欄序（各來源統一成此順序）
_BAT_COLS = ("player_id", "name", "team", "g", "pa", "ab", "r", "h", "b2", "b3", "hr", "rbi",
             "bb", "so", "sb", "cs", "tb", "ibb", "hbp", "sf", "sh", "gidp")


def _batting_rows(year: int, kind: str) -> list[dict]:
    """打者季成績原始計數，依年份/層級選來源：當季一軍→batting_current、2018+→gamelog、<2018 一軍→opendata。"""
    with conn() as c:
        if kind == "A" and year == DEFAULT_SEASON:
            rows = c.execute(
                "SELECT b.player_id, b.name, t.name, b.g,b.pa,b.ab,b.r,b.h,b.b2,b.b3,b.hr,b.rbi,"
                "b.bb,b.so,b.sb,b.cs,b.tb,b.ibb,b.hbp,b.sf,b.sh,b.gidp "
                "FROM cpbl.batting_current b LEFT JOIN cpbl.team_current t "
                "ON t.team_code=b.team_code AND t.year=b.year WHERE b.year=%s", (year,)).fetchall()
        elif year >= 2018:  # 逐場彙整（含二軍）；隊伍由 games + visiting_home_type 推
            rows = c.execute(
                "WITH agg AS (SELECT hitter_acnt acnt, max(hitter_name) nm, count(DISTINCT game_sno) g, "
                " sum(plate_appearances) pa, sum(at_bats) ab, sum(runs) r, sum(hits) h, sum(doubles) b2, "
                " sum(triples) b3, sum(home_runs) hr, sum(rbi) rbi, sum(bb) bb, sum(so) so, sum(sb) sb, "
                " sum(cs) cs, sum(total_bases) tb, sum(ibb) ibb, sum(hbp) hbp, sum(sac_fly) sf, "
                " sum(sac_hit) sh, sum(gidp) gidp FROM cpbl.batting_gamelog WHERE year=%s AND kind_code=%s "
                " GROUP BY hitter_acnt), "
                "tm AS (SELECT DISTINCT ON (bg.hitter_acnt) bg.hitter_acnt acnt, "
                " CASE WHEN bg.visiting_home_type='2' THEN g.home_team_name ELSE g.away_team_name END nm "
                " FROM cpbl.batting_gamelog bg JOIN cpbl.games g ON g.year=bg.year AND g.kind_code=bg.kind_code "
                " AND g.game_sno=bg.game_sno WHERE bg.year=%s AND bg.kind_code=%s ORDER BY bg.hitter_acnt, bg.game_sno) "
                "SELECT a.acnt, a.nm, tm.nm, a.g,a.pa,a.ab,a.r,a.h,a.b2,a.b3,a.hr,a.rbi,a.bb,a.so,a.sb,a.cs,"
                "a.tb,a.ibb,a.hbp,a.sf,a.sh,a.gidp FROM agg a LEFT JOIN tm ON tm.acnt=a.acnt",
                (year, kind, year, kind)).fetchall()
        else:  # opendata 逐年（一軍；同年多隊加總）
            rows = c.execute(
                "SELECT s.player_id, max(p.name), max(s.team_name), sum(s.g),sum(s.pa),sum(s.ab),sum(s.r),"
                "sum(s.h),sum(s.b2),sum(s.b3),sum(s.hr),sum(s.rbi),sum(s.bb),sum(s.so),sum(s.sb),sum(s.cs),"
                "sum(s.tb),sum(s.ibb),sum(s.hbp),sum(s.sf),sum(s.sh),sum(s.gidp) "
                "FROM cpbl.batting_seasons s LEFT JOIN cpbl.players p ON p.id=s.player_id "
                "WHERE s.year=%s GROUP BY s.player_id", (year,)).fetchall()
    return [dict(zip(_BAT_COLS, r, strict=False)) for r in rows]


# 守位正規化：fielding_current 用中文長名、fielding_seasons 用英文碼 → 統一短名
_POS_CANON = {
    "P": "投手", "投手": "投手", "C": "捕手", "捕手": "捕手",
    "1B": "一壘", "一壘手": "一壘", "2B": "二壘", "二壘手": "二壘",
    "3B": "三壘", "三壘手": "三壘", "SS": "游擊", "游擊手": "游擊",
    "LF": "左外野", "左外野手": "左外野", "CF": "中外野", "中外野手": "中外野",
    "RF": "右外野", "右外野手": "右外野",
}


def _primary_positions(year: int, kind: str) -> dict[str, str]:
    """每位球員該季主守位/指定打擊（出賽最多者）。當季一軍→fielding_current，其餘→fielding_seasons。
    DH 不上守備 → 以「打擊出賽 − 守備總出賽」推算指定打擊場數納入比較（僅當季一軍有打擊資料）。"""
    with conn() as c:
        if kind == "A" and year == DEFAULT_SEASON:
            rows = c.execute("SELECT player_id, pos, g FROM cpbl.fielding_current WHERE year=%s", (year,)).fetchall()
            batg = dict(c.execute("SELECT player_id, coalesce(g,0) FROM cpbl.batting_current WHERE year=%s",
                                  (year,)).fetchall())
        else:
            rows = c.execute("SELECT player_id, pos, g FROM cpbl.fielding_seasons WHERE year=%s", (year,)).fetchall()
            batg = {}
    by_player: dict[str, dict[str, int]] = {}
    fld_total: dict[str, int] = {}
    for pid, pos, g in rows:
        cp = _POS_CANON.get(pos)
        if not cp or cp == "投手":
            continue
        by_player.setdefault(pid, {})[cp] = by_player.setdefault(pid, {}).get(cp, 0) + (g or 0)
        fld_total[pid] = fld_total.get(pid, 0) + (g or 0)
    for pid, bg in batg.items():
        dh = max(0, (bg or 0) - fld_total.get(pid, 0))
        if dh > 0:
            by_player.setdefault(pid, {})["指定打擊"] = dh
    return {pid: max(d, key=d.get) for pid, d in by_player.items() if d}


def _roster_level(cur, player_id: str, season: int) -> dict | None:
    """判定本季「目前登錄層級」。回 {level, first_days, farm_days} 或 None(本季無活動)。

    官網 /player/trans 只給升降『事件』、無季初基準 → 用首事件反推季初狀態（升一軍前必在二軍、
    反之）；逐區間累加天數。完全無升降事件者退回出賽(gamelog A/D)判定。as_of=今天（季中即時）。

    `level` 反映『現在』的層級（最後一次升降事件後的狀態），非累計天數多者——季中才升上一軍
    的板凳球員(如升一軍後 current 名單有他)即應為一軍，即使季初累計二軍天數暫時較多。
    first_days/farm_days 仍回傳供顯示各層級累計天數。
    """
    cur.execute("SELECT min(game_date), max(game_date) FROM cpbl.games "
                "WHERE kind_code='A' AND extract(year FROM game_date)=%s", (season,))
    g0, g1 = cur.fetchone()
    if not g0:
        return None
    as_of = min(_date.today(), g1) if g1 else _date.today()
    if as_of < g0:
        as_of = g0

    cur.execute("SELECT trans_date, kind_code FROM cpbl.player_transactions "
                "WHERE acnt=%s AND year=%s ORDER BY trans_date, kind_code", (player_id, season))
    events = cur.fetchall()

    # 本季是否在各層級出賽（gamelog；一軍另含 current 名單）
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM cpbl.batting_gamelog WHERE hitter_acnt=%(p)s AND year=%(y)s AND kind_code='A') "
        "  OR EXISTS(SELECT 1 FROM cpbl.pitching_gamelog WHERE pitcher_acnt=%(p)s AND year=%(y)s AND kind_code='A') "
        "  OR EXISTS(SELECT 1 FROM cpbl.batting_current WHERE player_id=%(p)s AND year=%(y)s) "
        "  OR EXISTS(SELECT 1 FROM cpbl.pitching_current WHERE player_id=%(p)s AND year=%(y)s), "
        "EXISTS(SELECT 1 FROM cpbl.batting_gamelog WHERE hitter_acnt=%(p)s AND year=%(y)s AND kind_code='D') "
        "  OR EXISTS(SELECT 1 FROM cpbl.pitching_gamelog WHERE pitcher_acnt=%(p)s AND year=%(y)s AND kind_code='D')",
        {"p": player_id, "y": season})
    appeared_a, appeared_d = cur.fetchone()

    if not events and not appeared_a and not appeared_d:
        return None                          # 本季完全無活動（退役/教練/未登錄）

    first_days = farm_days = 0
    if events:
        # 首事件反推季初層級：首筆為升一軍(01)→季初在二軍；為降二軍(02)→季初在一軍
        level_first = events[0][1] != "01"   # True=一軍
        prev, prev_first = g0, level_first
        for tdate, kc in events:
            d = max(0, (tdate - prev).days)
            if prev_first:
                first_days += d
            else:
                farm_days += d
            prev, prev_first = tdate, (kc == "01")
        d = max(0, (as_of - prev).days)
        (first_days, farm_days) = (first_days + d, farm_days) if prev_first else (first_days, farm_days + d)
        current_first = prev_first           # 最後一次事件後的層級＝現在層級
    else:
        # 無升降事件：整季單一層級，依出賽歸屬
        total = (as_of - g0).days
        if appeared_a and not appeared_d:
            first_days = total
        elif appeared_d and not appeared_a:
            farm_days = total
        else:                                # 兩級都有出賽卻無升降事件（罕見）→ 依出賽場數多者
            cur.execute(
                "SELECT (SELECT count(DISTINCT game_sno) FROM cpbl.batting_gamelog "
                "        WHERE hitter_acnt=%(p)s AND year=%(y)s AND kind_code='A') "
                "     + (SELECT count(DISTINCT game_sno) FROM cpbl.pitching_gamelog "
                "        WHERE pitcher_acnt=%(p)s AND year=%(y)s AND kind_code='A'), "
                "       (SELECT count(DISTINCT game_sno) FROM cpbl.batting_gamelog "
                "        WHERE hitter_acnt=%(p)s AND year=%(y)s AND kind_code='D') "
                "     + (SELECT count(DISTINCT game_sno) FROM cpbl.pitching_gamelog "
                "        WHERE pitcher_acnt=%(p)s AND year=%(y)s AND kind_code='D')",
                {"p": player_id, "y": season})
            ga, gd = cur.fetchone()
            if (gd or 0) > (ga or 0):
                farm_days = total
            else:
                first_days = total
        current_first = first_days >= farm_days   # 無事件時單一層級，即現在層級

    # level＝現在登錄層級（非累計天數多者）：季中升上一軍的板凳球員即為一軍
    level = "一軍" if current_first else "二軍"
    return {"level": level, "first_days": first_days, "farm_days": farm_days}


@app.get("/api/v1/records")
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


@app.get("/api/v1/season/batting-leaders")
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


def _ip_real(ip: float | None) -> float | None:
    """.1/.2 局數記法 → 真實局數（如 180.2 → 180⅔）。"""
    if ip is None:
        return None
    whole = int(ip)
    return whole + round((ip - whole) * 10) / 3.0


def _ip_disp(real: float | None) -> float | None:
    """真實局數 → .1/.2 棒球記法顯示（如 180⅔ → 180.2）。"""
    if real is None:
        return None
    real = float(real)
    whole = int(real + 1e-9)
    outs = round((real - whole) * 3)
    if outs >= 3:
        whole, outs = whole + 1, 0
    return round(whole + outs / 10, 1)


_PIT_COLS = ("player_id", "name", "team", "g", "gs", "cg", "sho", "w", "l", "sv", "hld",
             "ip", "h", "hr", "bb", "ibb", "hbp", "so", "r", "er")


def _pitching_rows(year: int, kind: str) -> list[dict]:
    """投手季成績（ip 已轉真實局數），來源同打者三選一。"""
    with conn() as c:
        if kind == "A" and year == DEFAULT_SEASON:
            raw = c.execute(
                "SELECT p.player_id,p.name,t.name,p.g,p.gs,p.cg,p.sho,p.w,p.l,p.sv,p.hld,p.ip,"
                "p.h,p.hr,p.bb,p.ibb,p.hbp,p.so,p.r,p.er FROM cpbl.pitching_current p "
                "LEFT JOIN cpbl.team_current t ON t.team_code=p.team_code AND t.year=p.year WHERE p.year=%s",
                (year,)).fetchall()
            out = [dict(zip(_PIT_COLS, r, strict=False)) for r in raw]
            for d in out:
                d["ip"] = _ip_real(d["ip"])
            return out
        if year >= 2018:  # 逐場彙整（含二軍）
            raw = c.execute(
                "WITH agg AS (SELECT pitcher_acnt acnt, max(pitcher_name) nm, count(DISTINCT game_sno) g, "
                " count(*) FILTER (WHERE role_type='先發') gs, sum(is_complete_game::int) cg, "
                " sum(is_shutout::int) sho, count(*) FILTER (WHERE game_result='勝') w, "
                " count(*) FILTER (WHERE game_result='敗') l, "
                " sum(inning_pitched_cnt)+sum(inning_pitched_div3)/3.0 ip, sum(hits) h, sum(home_runs) hr, "
                " sum(bb) bb, sum(ibb) ibb, sum(hbp) hbp, sum(so) so, sum(runs) r, sum(earned_runs) er "
                " FROM cpbl.pitching_gamelog WHERE year=%s AND kind_code=%s GROUP BY pitcher_acnt), "
                "tm AS (SELECT DISTINCT ON (pg.pitcher_acnt) pg.pitcher_acnt acnt, "
                " CASE WHEN pg.visiting_home_type='2' THEN g.home_team_name ELSE g.away_team_name END nm "
                " FROM cpbl.pitching_gamelog pg JOIN cpbl.games g ON g.year=pg.year AND g.kind_code=pg.kind_code "
                " AND g.game_sno=pg.game_sno WHERE pg.year=%s AND pg.kind_code=%s ORDER BY pg.pitcher_acnt, pg.game_sno) "
                "SELECT a.acnt,a.nm,tm.nm,a.g,a.gs,a.cg,a.sho,a.w,a.l,NULL,NULL,a.ip,a.h,a.hr,a.bb,a.ibb,a.hbp,a.so,a.r,a.er "
                "FROM agg a LEFT JOIN tm ON tm.acnt=a.acnt", (year, kind, year, kind)).fetchall()
            return [dict(zip(_PIT_COLS, r, strict=False)) for r in raw]
        # opendata 逐年（一軍；ip 先轉真實局再加總，多隊合計）
        raw = c.execute(
            "SELECT s.player_id, max(p.name), max(s.team_name), sum(s.g),sum(s.gs),sum(s.cg),sum(s.sho),"
            "sum(s.w),sum(s.l),sum(s.sv),sum(s.hld),"
            "sum(floor(s.ip)+round((s.ip-floor(s.ip))*10)/3.0), sum(s.h),sum(s.hr),sum(s.bb),sum(s.ibb),"
            "sum(s.hbp),sum(s.so),sum(s.r),sum(s.er) "
            "FROM cpbl.pitching_seasons s LEFT JOIN cpbl.players p ON p.id=s.player_id "
            "WHERE s.year=%s GROUP BY s.player_id", (year,)).fetchall()
        return [dict(zip(_PIT_COLS, r, strict=False)) for r in raw]


@app.get("/api/v1/season/pitching-leaders")
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
    """賽果預測的候選特徵清單（含說明/群組/相依，給前端分群 + tooltip + 共線軟提醒）。"""
    from cpbl.features.outcome import FEATURE_CORR, FEATURE_GROUP
    return {
        "features": [
            {"key": k, "label": label, "desc": FEATURE_DESC.get(k, ""),
             "group": FEATURE_GROUP.get(k, "其他"), "corr": FEATURE_CORR.get(k)}
            for k, label in CANDIDATE_FEATURES
        ]
    }


@app.get("/api/v1/outcome/backtest")
def outcome_backtest() -> dict:
    """全特徵走查回測對照（LightGBM vs 邏輯回歸 vs 全押主場），由離線 cpbl-train-outcome
    持久化於 model_versions(task='outcome')。前端「模型回測」面板用此誠實展示模型價值。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT id, trained_at, cv_metrics FROM cpbl.model_versions "
            "WHERE task = 'outcome' ORDER BY trained_at DESC LIMIT 1"
        )
        row = cur.fetchone()
    if not row:
        return {"available": False}
    vid, trained_at, m = row
    return {"available": True, "version": vid,
            "trained_at": trained_at.isoformat() if trained_at else None, **m}


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


def _career_teams(cur, player_id: str) -> list[dict]:
    """生涯效力球隊（轉隊紀錄）：(年, 隊代碼前 3 碼) → era 全名的連續年代區段。

    team_id 前 3 碼即 franchise-era（俊國/興農/義大/富邦各自獨立），cpbl.teams 給權威
    全名；2025+ 用 gamelog × games 反查當時隊代碼（visiting_home_type='2' 為主隊）。
    AJK 同代碼內 La New/Lamigo 依 _ERA_SPLIT 細分。回傳供前端 eraBadge(name, code) 上色。
    """
    from collections import defaultdict
    cur.execute(
        "WITH yt AS ("
        "  SELECT DISTINCT year, substring(team_id,1,3) code FROM cpbl.batting_seasons WHERE player_id=%(p)s"
        "  UNION SELECT DISTINCT year, substring(team_id,1,3) FROM cpbl.pitching_seasons WHERE player_id=%(p)s"
        "  UNION SELECT DISTINCT g.year, substring(CASE WHEN bg.visiting_home_type='2' THEN g.home_team_code "
        "    ELSE g.away_team_code END,1,3) FROM cpbl.batting_gamelog bg JOIN cpbl.games g "
        "    ON g.year=bg.year AND g.kind_code=bg.kind_code AND g.game_sno=bg.game_sno "
        "    WHERE bg.hitter_acnt=%(p)s AND bg.year>=2025 AND bg.kind_code='A'"
        "  UNION SELECT DISTINCT g.year, substring(CASE WHEN pg.visiting_home_type='2' THEN g.home_team_code "
        "    ELSE g.away_team_code END,1,3) FROM cpbl.pitching_gamelog pg JOIN cpbl.games g "
        "    ON g.year=pg.year AND g.kind_code=pg.kind_code AND g.game_sno=pg.game_sno "
        "    WHERE pg.pitcher_acnt=%(p)s AND pg.year>=2025 AND pg.kind_code='A')"
        "SELECT year, code FROM yt WHERE code IS NOT NULL ORDER BY year, code",
        {"p": player_id})
    years_by_code: dict[str, set[int]] = defaultdict(set)
    for y, code in cur.fetchall():
        years_by_code[code].add(y)
    cur.execute("SELECT team_id, name FROM cpbl.teams")
    names = dict(cur.fetchall())  # 3 碼 → 全名
    stints: list[dict] = []
    for code, ys in years_by_code.items():
        ys_sorted = sorted(ys)
        run = [ys_sorted[0]]
        for y in ys_sorted[1:] + [None]:  # 連續年代收斂成區段；非連續→新段（離隊再回鍋）
            if y is not None and y == run[-1] + 1:
                run.append(y)
                continue
            full = f"{code}011"  # 現役隊以 6 碼 code 供 eraBadge 取色
            if full in _ERA_SPLIT:  # 同代碼內改名（La New / Lamigo）依權威年代細分
                for nm, a, b in _ERA_SPLIT[full]:
                    sub = [x for x in run if a <= x <= b]
                    if sub:
                        stints.append({"code": full, "name": nm, "from": sub[0], "to": sub[-1]})
            else:
                stints.append({"code": full, "name": names.get(code, code), "from": run[0], "to": run[-1]})
            if y is not None:
                run = [y]
    stints.sort(key=lambda s: (s["from"], s["to"]))
    return stints


@app.get("/api/v1/players/{player_id}/career")
def player_career(player_id: str) -> dict:
    """球員生涯：累計成績、最佳單季、里程碑日期、史上排名脈絡（打者）+ 效力球隊。"""
    from collections import defaultdict
    with conn() as c:
        cur = c.cursor()
        teams = _career_teams(cur, player_id)
        cur.execute(
            "SELECT league, team, from_year FROM cpbl.overseas WHERE player_id=%s ORDER BY from_year",
            (player_id,))
        overseas = [{"league": lg, "team": tm, "year": yr} for lg, tm, yr in cur.fetchall()]
        cur.execute(
            "SELECT year, category, award FROM cpbl.player_awards WHERE player_id=%s ORDER BY year",
            (player_id,))
        awards = [{"year": y, "category": cat, "award": aw} for y, cat, aw in cur.fetchall()]
        # 年度總冠軍（隊伍榮銜，個人獎項表沒有）：由官網 games 推導 → championship_members
        # （該年一軍有成績的球員＋總教練；見 ingest/championships.py）
        cur.execute(
            "SELECT year FROM cpbl.championship_members WHERE player_id=%s ORDER BY year",
            (player_id,))
        _cy = [y for (y,) in cur.fetchall()]
        championships = {"count": len(_cy), "years": _cy} if _cy else None
        # 維基補充：教練經歷（球團職務）+ 國際賽獎牌
        cur.execute(
            "SELECT phase, team_raw, role, from_year, to_year FROM cpbl.wiki_tenures "
            "WHERE player_id=%s AND phase IN ('coach','other') ORDER BY seq", (player_id,))
        _tn = cur.fetchall()
        coach_tenures = [{"team": tm, "role": ro, "from": fr, "to": to}
                         for ph, tm, ro, fr, to in _tn if ph == "coach"]
        exec_tenures = [{"team": tm, "role": ro, "from": fr, "to": to}
                        for ph, tm, ro, fr, to in _tn if ph == "other"]
        cur.execute(
            "SELECT color, competition, event, year FROM cpbl.wiki_medals "
            "WHERE player_id=%s ORDER BY year NULLS LAST, seq", (player_id,))
        medals = [{"color": co, "competition": cp, "event": ev, "year": yr}
                  for co, cp, ev, yr in cur.fetchall()]
        # 逐年（opendata ≤2024 + 2025/2026 由 gamelog 補；同年多隊加總）
        cur.execute(
            "SELECT year, sum(g),sum(pa),sum(ab),sum(h),sum(b2),sum(b3),sum(hr),sum(rbi),sum(sb),"
            "sum(bb),sum(hbp),sum(sf),sum(tb),sum(so) FROM cpbl.batting_seasons WHERE player_id=%s GROUP BY year",
            (player_id,))
        per: dict = {r[0]: list(r[1:]) for r in cur.fetchall()}
        cur.execute(
            "SELECT year, count(DISTINCT game_sno),sum(plate_appearances),sum(at_bats),sum(hits),"
            "sum(doubles),sum(triples),sum(home_runs),sum(rbi),sum(sb),sum(bb),sum(hbp),sum(sac_fly),"
            "sum(total_bases),sum(so) FROM cpbl.batting_gamelog WHERE hitter_acnt=%s AND kind_code='A' "
            "AND year>=2025 GROUP BY year", (player_id,))
        for r in cur.fetchall():
            per[r[0]] = list(r[1:])  # 2025+ 以 gamelog 為準
        # 投手生涯（pitching_seasons；與逐年投球史同源，ip .1/.2 換算成真實局數）
        cur.execute(
            "SELECT year, sum(g),sum(gs),sum(w),sum(l),sum(sv),sum(hld),"
            "sum(trunc(ip)+(ip-trunc(ip))*10/3.0) AS rip,sum(so),sum(h),sum(bb),sum(er) "
            "FROM cpbl.pitching_seasons WHERE player_id=%s GROUP BY year", (player_id,))
        pper: dict = {r[0]: [float(x) if x is not None else 0.0 for x in r[1:]] for r in cur.fetchall()}
        pcareer = pbests = prk = None
        if pper:
            cur.execute(
                "WITH cr AS (SELECT player_id, sum(w) w, sum(sv) sv, sum(so) so FROM cpbl.pitching_seasons GROUP BY player_id) "
                "SELECT (SELECT count(*)+1 FROM cr b WHERE b.w>a.w),(SELECT count(*)+1 FROM cr b WHERE b.sv>a.sv),"
                "(SELECT count(*)+1 FROM cr b WHERE b.so>a.so) FROM cr a WHERE a.player_id=%s", (player_id,))
            prk = cur.fetchone()
            pt: dict = defaultdict(float)
            for vals in pper.values():
                for k, v in zip(["g", "gs", "w", "l", "sv", "hld", "rip", "so", "h", "bb", "er"], vals, strict=False):
                    pt[k] += v
            rip = pt["rip"]
            outs = round(rip * 3)
            _wl = pt["w"] + pt["l"]
            pcareer = {"seasons": len(pper), "g": int(pt["g"]), "gs": int(pt["gs"]),
                       "w": int(pt["w"]), "l": int(pt["l"]), "sv": int(pt["sv"]), "hld": int(pt["hld"]),
                       "so": int(pt["so"]), "h": int(pt["h"]), "bb": int(pt["bb"]), "er": int(pt["er"]),
                       "ip": f"{outs // 3}.{outs % 3}",
                       "winpct": round(pt["w"] / _wl, 3) if _wl else None,
                       "era": round(pt["er"] * 9 / rip, 2) if rip else None,
                       "whip": round((pt["bb"] + pt["h"]) / rip, 2) if rip else None,
                       "k9": round(pt["so"] * 9 / rip, 2) if rip else None,
                       "kbb": round(pt["so"] / pt["bb"], 2) if pt["bb"] else None}

            def _pmax(idx: int):
                cand = [(y, v) for y, v in pper.items() if v[idx]]
                if not cand:
                    return None
                y, v = max(cand, key=lambda x: x[1][idx])
                return {"year": y, "value": int(v[idx])}
            _pera = None
            for y, v in pper.items():
                r = v[6]
                if r < 30:  # 單季 ≥30 局才列入最佳 ERA
                    continue
                e = v[10] * 9 / r
                if _pera is None or e < _pera["value"]:
                    _pera = {"year": y, "value": round(e, 2)}
            pbests = {"w": _pmax(2), "sv": _pmax(4), "so": _pmax(7), "era": _pera}
        _pit_extra = {"pitching": pcareer, "best_p": pbests,
                      "rank_p": {"w": prk[0], "sv": prk[1], "so": prk[2]} if prk else None,
                      "championships": championships}
        if not per:
            return {"player_id": player_id, "batting": None, "teams": teams,
                    "overseas": overseas, "awards": awards,
                    "coach_tenures": coach_tenures, "exec_tenures": exec_tenures, "medals": medals,
                    **_pit_extra}
        # 里程碑日期（gamelog 2018+）
        cur.execute(
            "SELECT min(g.game_date) FILTER (WHERE bg.hits>0), min(g.game_date) FILTER (WHERE bg.home_runs>0) "
            "FROM cpbl.batting_gamelog bg JOIN cpbl.games g ON g.year=bg.year AND g.kind_code=bg.kind_code "
            "AND g.game_sno=bg.game_sno WHERE bg.hitter_acnt=%s", (player_id,))
        first_h, first_hr = cur.fetchone()
        # 史上排名脈絡（opendata 生涯累計；近兩季另計）
        cur.execute(
            "WITH cr AS (SELECT player_id, sum(hr) hr, sum(h) h, sum(sb) sb FROM cpbl.batting_seasons GROUP BY player_id) "
            "SELECT (SELECT count(*)+1 FROM cr b WHERE b.hr>a.hr), (SELECT count(*)+1 FROM cr b WHERE b.h>a.h), "
            "(SELECT count(*)+1 FROM cr b WHERE b.sb>a.sb) FROM cr a WHERE a.player_id=%s", (player_id,))
        rk = cur.fetchone()
    keys = ["g", "pa", "ab", "h", "b2", "b3", "hr", "rbi", "sb", "bb", "hbp", "sf", "tb", "so"]
    tot = defaultdict(int)
    for vals in per.values():
        for k, v in zip(keys, vals, strict=False):
            tot[k] += v or 0
    ab, h, bb, hbp, sf, tb = (tot[k] for k in ("ab", "h", "bb", "hbp", "sf", "tb"))
    od = ab + bb + hbp + sf
    career = {**{k: tot[k] for k in keys},
              "avg": round(h / ab, 3) if ab else None,
              "obp": round((h + bb + hbp) / od, 3) if od else None,
              "slg": round(tb / ab, 3) if ab else None,
              "ops": round((h + bb + hbp) / od + tb / ab, 3) if ab and od else None,
              "seasons": len(per)}
    # 最佳單季：HR/打點/盜壘最多、AVG/OPS 最佳（≥100 打席）
    def best(idx: int, *, rate: bool = False, minpa: int = 100):
        cand = [(y, v) for y, v in per.items() if v[idx] is not None and (not rate or (v[1] or 0) >= minpa)]
        if not cand:
            return None
        if rate:  # avg = h/ab, ops 另算
            return None
        y, v = max(cand, key=lambda x: x[1][idx])
        return {"year": y, "value": v[idx]}

    def best_rate(kind: str):
        out = None
        for y, v in per.items():
            ab_, h_, bb_, hbp_, sf_, tb_, pa_ = v[2], v[3], v[9], v[10], v[11], v[12], v[1]
            if (pa_ or 0) < 100 or not ab_:
                continue
            val = (h_ / ab_) if kind == "avg" else ((h_ + bb_ + hbp_) / (ab_ + bb_ + hbp_ + sf_) + tb_ / ab_)
            if out is None or val > out["value"]:
                out = {"year": y, "value": round(val, 3)}
        return out
    bests = {"hr": best(6), "rbi": best(7), "sb": best(8), "avg": best_rate("avg"), "ops": best_rate("ops")}
    return {
        "player_id": player_id, "batting": career, "best": bests, "teams": teams,
        "overseas": overseas, "awards": awards,
        "coach_tenures": coach_tenures, "exec_tenures": exec_tenures, "medals": medals,
        "milestones": {"first_hit": str(first_h) if first_h else None,
                       "first_hr": str(first_hr) if first_hr else None},
        "rank": {"hr": rk[0], "h": rk[1], "sb": rk[2]} if rk else None,
        **_pit_extra,
    }


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
        cur.execute("SELECT name, bats, throws, country, birthday, height_cm, weight_kg, "
                    "debut, education, birthplace, draft FROM cpbl.players WHERE id = %s", (player_id,))
        meta = cur.fetchone()
        # 曾用名（改名）：gamelog 逐場記錄當時名字，取與現名不同者
        cur.execute(
            "SELECT DISTINCT nm FROM ("
            "  SELECT hitter_name nm FROM cpbl.batting_gamelog WHERE hitter_acnt=%s "
            "  UNION SELECT pitcher_name FROM cpbl.pitching_gamelog WHERE pitcher_acnt=%s) x "
            "WHERE nm IS NOT NULL", (player_id, player_id),
        )
        all_names = {r[0] for r in cur.fetchall()}
        # 投手類型（現役取本季、否則生涯）：先發=先發佔半數以上、後援=救援>中繼、餘=中繼
        cur.execute("SELECT g, gs, sv, hld FROM cpbl.pitching_current WHERE player_id=%s AND year=%s",
                    (player_id, season))
        prow = cur.fetchone()
        if not prow or not prow[0]:
            cur.execute("SELECT sum(g), sum(gs), sum(sv), sum(hld) FROM cpbl.pitching_seasons "
                        "WHERE player_id=%s", (player_id,))
            prow = cur.fetchone()
        pitcher_role = None
        if prow and prow[0]:
            g, gs, sv, hld = (x or 0 for x in prow)
            pitcher_role = "先發" if gs * 2 >= g else ("後援" if sv > hld else "中繼")
        # 打者主守位：本季各守位出賽 + 指定打擊（DH 不上守備，故以「打擊出賽 − 守備總出賽」推算），
        # 取出賽最多者。本季無打擊也無守備（退役/歷史）才退回生涯 fielding_seasons。
        # 守位字串中／英碼經 _POS_CANON 統一短名。
        cur.execute("SELECT pos, g FROM cpbl.fielding_current WHERE player_id=%s AND year=%s",
                    (player_id, season))
        season_pos: dict[str, int] = {}
        fld_g = 0
        for pos, fg in cur.fetchall():
            cp = _POS_CANON.get(pos)
            if cp and cp != "投手":
                season_pos[cp] = season_pos.get(cp, 0) + (fg or 0)
                fld_g += (fg or 0)
        cur.execute("SELECT coalesce(g, 0) FROM cpbl.batting_current WHERE player_id=%s AND year=%s",
                    (player_id, season))
        br = cur.fetchone()
        dh_g = max(0, (br[0] if br else 0) - fld_g)
        if dh_g > 0:
            season_pos["指定打擊"] = dh_g
        if season_pos:
            primary_position = max(season_pos, key=season_pos.get)
        else:
            cur.execute("SELECT pos, sum(g) FROM cpbl.fielding_seasons WHERE player_id=%s "
                        "GROUP BY pos", (player_id,))
            primary_position, best_g = None, -1
            for pos, fg in cur.fetchall():
                cp = _POS_CANON.get(pos)
                if cp and cp != "投手" and (fg or 0) > best_g:
                    primary_position, best_g = cp, (fg or 0)
        # 生涯曾任打者／投手（歷年彙總存在性）：退役/教練本季不在名單，前端據此推導 role tab。
        cur.execute("SELECT EXISTS(SELECT 1 FROM cpbl.batting_seasons WHERE player_id=%s), "
                    "EXISTS(SELECT 1 FROM cpbl.pitching_seasons WHERE player_id=%s)",
                    (player_id, player_id))
        was_batter, was_pitcher = cur.fetchone()
        # 二軍本季是否有打/投出賽（gamelog kind=D）：二軍-only 球員一軍 current 為空，
        # 前端需據此補 role tab，且判定其非「退役」。
        cur.execute("SELECT EXISTS(SELECT 1 FROM cpbl.batting_gamelog WHERE hitter_acnt=%(p)s AND year=%(y)s AND kind_code='D'), "
                    "EXISTS(SELECT 1 FROM cpbl.pitching_gamelog WHERE pitcher_acnt=%(p)s AND year=%(y)s AND kind_code='D')",
                    {"p": player_id, "y": season})
        farm_batter, farm_pitcher = cur.fetchone()
        # 本季主要登錄層級（一軍/二軍；None=本季無活動）：由升降事件重建登錄天數判定。
        roster = _roster_level(cur, player_id, season)
    if not bat and not pit and not meta:
        return {"player": None}
    name = (bat[1] if bat else None) or (pit[1] if pit else None) or (meta[0] if meta else None)
    team = (bat[2] if bat else None) or (pit[2] if pit else None)
    former = sorted(n for n in all_names if n and n != name)
    country = meta[3] if meta else None
    status = imports.classify(player_id, country)
    return {
        "player": {
            "id": player_id, "name": name, "team": team,
            "is_batter": bat is not None, "is_pitcher": pit is not None,
            "was_batter": bool(was_batter), "was_pitcher": bool(was_pitcher),
            "farm_batter": bool(farm_batter), "farm_pitcher": bool(farm_pitcher),
            "roster_level": roster["level"] if roster else None,
            "roster_days": {"first": roster["first_days"], "farm": roster["farm_days"]} if roster else None,
            "bats": meta[1] if meta else None, "throws": meta[2] if meta else None,
            "former_names": former, "pitcher_role": pitcher_role,
            "primary_position": primary_position,
            "country": country,
            "import_status": status,
            "import_label": imports.LABELS[status] if status != "local" else None,
            "birthday": (meta[4].isoformat() if meta and meta[4] else None),
            "height_cm": meta[5] if meta else None,
            "weight_kg": meta[6] if meta else None,
            "debut": meta[7] if meta else None,
            "education": meta[8] if meta else None,
            "birthplace": meta[9] if meta else None,
            "draft": meta[10] if meta else None,
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


def _farm_season(player_id: str, season: int) -> dict:
    """二軍本季成績（gamelog kind=D 彙整）：供二軍選手成績卡。rate 由原始計數即時算；
    OPS+/ERA+/FIP 無二軍聯盟基準故留空（前端顯示 —）。欄位對齊一軍卡。"""
    out: dict[str, Any] = {"player_id": player_id, "season": season, "batting": None, "pitching": None}
    b = next((r for r in _batting_rows(season, "D") if r["player_id"] == player_id), None)
    p = next((r for r in _pitching_rows(season, "D") if r["player_id"] == player_id), None)
    if b:
        ab, h, bb, hbp, sf, tb = (b.get(k) or 0 for k in ("ab", "h", "bb", "hbp", "sf", "tb"))
        den = ab + bb + hbp + sf
        b["avg"] = round(h / ab, 3) if ab else None
        b["obp"] = round((h + bb + hbp) / den, 3) if den else None
        b["slg"] = round(tb / ab, 3) if ab else None
        b["ops"] = round((b["obp"] or 0) + (b["slg"] or 0), 3) if ab else None
        out["batting"] = b
    if p:
        rip = _real_ip(p.get("ip"))
        er, hh, bbp, so = (p.get(k) or 0 for k in ("er", "h", "bb", "so"))
        p["era"] = round(er * 9 / rip, 2) if rip else None
        p["whip"] = round((hh + bbp) / rip, 2) if rip else None
        p["k9"] = round(so * 9 / rip, 2) if rip else None
        out["pitching"] = p
    return out


@app.get("/api/v1/players/{player_id}/season")
def player_season(player_id: str, season: int = Query(DEFAULT_SEASON),
                  kind: str = Query("A", pattern="^(A|D)$")) -> dict:
    """球員本季成績（kind=A 一軍 batting_current/pitching_current；kind=D 二軍 gamelog 彙整）。
    供個人頁成績卡；二軍選手預設採計二軍、可切換看一軍。
    OPS+/ERA+/FIP 官網不提供，一軍於此用聯盟平均即時計算（park-neutral 標準公式）。"""
    if kind == "D":
        return _farm_season(player_id, season)
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


# 守備位置碼：fielding_seasons 用英文(1B/C/P…)、fielding_current 用中文 → 統一成中文
_POS_ZH = {"1B": "一壘手", "2B": "二壘手", "3B": "三壘手", "SS": "游擊手", "C": "捕手",
           "P": "投手", "LF": "左外野手", "CF": "中外野手", "RF": "右外野手"}


@app.get("/api/v1/players/{player_id}/fielding")
def player_fielding(player_id: str, season: int = Query(DEFAULT_SEASON),
                    scope: str = Query("season", pattern="^(season|career)$"),
                    kind_code: str = Query("A", pattern="^(A|D)$")) -> dict:
    """球員守備逐守位。scope=season 本季(fielding_current，依 kind_code 分一/二軍)；career 生涯
    （fielding_seasons 1990–2024 + fielding_current 2025+ 一軍，守位碼對齊後彙總，重算 fpct）。"""
    with conn() as c:
        cur = c.cursor()
        if scope == "career":
            cur.execute(
                """
                WITH u AS (
                    -- fielding_seasons 守位為英文碼(LF/1B)、fielding_current 為中文(左外野手)；
                    -- 統一轉中文再彙總，避免同守位分裂成兩列（重複 key）。
                    SELECT year, CASE pos
                             WHEN '1B' THEN '一壘手' WHEN '2B' THEN '二壘手' WHEN '3B' THEN '三壘手'
                             WHEN 'SS' THEN '游擊手' WHEN 'C' THEN '捕手' WHEN 'P' THEN '投手'
                             WHEN 'LF' THEN '左外野手' WHEN 'CF' THEN '中外野手' WHEN 'RF' THEN '右外野手'
                             ELSE pos END AS pos,
                           g, tc, po, a, e, dp, tp, pb, cs, sb AS sba
                    FROM cpbl.fielding_seasons WHERE player_id = %s
                    UNION ALL
                    SELECT year, pos, g, tc, po, a, e, dp, tp, pb, cs, sba
                    FROM cpbl.fielding_current WHERE player_id = %s AND kind_code = 'A'
                )
                SELECT pos, sum(g), sum(tc), sum(po), sum(a), sum(e), sum(dp),
                       sum(tp), sum(pb), sum(cs), sum(sba), (SELECT min(year) FROM u) AS fy
                FROM u GROUP BY pos ORDER BY sum(g) DESC NULLS LAST
                """,
                (player_id, player_id),
            )
            items, from_year = [], None
            for pos, g, tc, po, a, e, dp, tp, pb, cs, sba, fy in cur.fetchall():
                from_year = fy
                den = (po or 0) + (a or 0) + (e or 0)
                items.append({"pos": _POS_ZH.get(pos, pos), "g": g, "tc": tc, "po": po, "a": a,
                              "e": e, "dp": dp, "tp": tp, "pb": pb, "cs": cs, "sba": sba,
                              "fpct": round(((po or 0) + (a or 0)) / den, 3) if den else None})
            return {"player_id": player_id, "scope": "career", "from_year": from_year, "items": items}
        cur.execute(
            """
            SELECT pos, g, tc, po, a, e, dp, tp, pb, cs, sba, fpct
            FROM cpbl.fielding_current
            WHERE player_id = %s AND year = %s AND kind_code = %s
            ORDER BY g DESC NULLS LAST, tc DESC NULLS LAST
            """,
            (player_id, season, kind_code),
        )
        items = [
            {"pos": pos, "g": g, "tc": tc, "po": po, "a": a, "e": e, "dp": dp,
             "tp": tp, "pb": pb, "cs": cs, "sba": sba,
             "fpct": float(fpct) if fpct is not None else None}
            for pos, g, tc, po, a, e, dp, tp, pb, cs, sba, fpct in cur.fetchall()
        ]
    return {"player_id": player_id, "season": season, "scope": "season", "items": items}


# ---------- 每場賽況 ----------

@app.get("/api/v1/games/calendar")
def games_calendar(
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A"),
) -> dict:
    """整季所有場次（已完成 + 未開打）供月曆呈現。每筆帶比分/狀態/勝敗投/先發/
    球場/觀眾/時長/延賽備註。completed 由 home_score+away_score>0 判定。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT g.year, g.kind_code, g.game_sno, g.game_date, g.venue, g.present_status,
                   g.away_team_name, g.away_team_code, g.away_score,
                   g.home_team_name, g.home_team_code, g.home_score,
                   wp.name AS win_pitcher, lp.name AS lose_pitcher, mv.name AS mvp,
                   hs.name AS home_starter, aws.name AS away_starter,
                   d.attendance, d.game_time, g.delay_kind, g.orig_date
            FROM cpbl.games g
            LEFT JOIN cpbl.players wp ON wp.id = g.winning_pitcher_id
            LEFT JOIN cpbl.players lp ON lp.id = g.losing_pitcher_id
            LEFT JOIN cpbl.players mv ON mv.id = g.mvp_id
            LEFT JOIN cpbl.players hs ON hs.id = g.home_starter_id
            LEFT JOIN cpbl.players aws ON aws.id = g.away_starter_id
            LEFT JOIN cpbl.game_detail d
                   ON d.year=g.year AND d.kind_code=g.kind_code AND d.game_sno=g.game_sno
            WHERE g.year = %s AND g.kind_code = %s
            ORDER BY g.game_date ASC, g.game_sno ASC
            """,
            (season, kind_code),
        )
        return {"season": season, "items": _dicts(cur)}


@app.get("/api/v1/games/recent")
def games_recent(
    limit: int = Query(40, ge=1, le=600),
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A"),
) -> dict:
    """某年某層級已完成比賽列表（供球隊頁近期戰績等）。"""
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
                   losing_pitcher_id, closer_id, mvp_id, delay_kind, orig_date,
                   present_status
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
        cur.execute("SELECT attendance, game_time, head_umpire, first_umpire, second_umpire, "
                    "third_umpire, left_umpire, right_umpire FROM cpbl.game_detail "
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s", (season, kind_code, game_sno))
        gd = _dicts(cur)
    return {"game": g[0] if g else None, "scoreboard": scoreboard, "livelog": livelog,
            "batting": batting, "pitching": pitching, "people": people,
            "records": records, "batter_avg": batter_avg, "detail": gd[0] if gd else None,
            "has_tracking": len(tracking) > 0, "tracking": tracking}


# ---- 能力值卡（遊戲風雷達圖）：以全史生涯 rate 對全聯盟母體求百分位 [PR] ----
# 不抄任何遊戲數字；每軸 = 我們自算的客觀指標相對「所有合格生涯球員」的 percent_rank。
# 等級 S–G 純由 PR 換算，方便一眼讀懂（教育用途，呼應 /predict）。
def _grade(pr: float) -> str:
    for t, g in ((90, "S"), (80, "A"), (65, "B"), (50, "C"), (35, "D"), (20, "E"), (10, "F")):
        if pr >= t:
            return g
    return "G"


# 軸定義：(key, 中文標, 顯示格式, 來源指標說明)。順序＝SQL 輸出順序。
_ABILITY_AXES = {
    "batting": [
        ("contact", "控制", "pct", "接觸率 (PA-SO)/PA"),
        ("power", "力量", "f3", "純長打率 ISO"),
        ("eye", "選球", "pct", "保送率 BB%"),
        ("speed", "速度", "f2", "每場盜壘＋三壘打 (SB+3B)/G"),
        ("defense", "守備", "f2", "守位內守備範圍／捕手阻殺率"),
    ],
    "pitching": [
        # 「武器」＝出局方式特色軸：取該投手最突出者（三振/滾地/飛球），標籤與數值動態。
        ("weapon", "武器", "f2", "出局武器（三振 K9／滾地 GO/AO／飛球 AO/GO，取最突出者）"),
        ("control", "控球", "f2", "每9局保送 BB/9"),
        ("hr_suppress", "抑長打", "f2", "每9局被全壘打 HR/9"),
        ("command", "壓制", "f2", "防禦率 ERA"),
        ("stamina", "續航", "f2", "先發 IP/G／後援登板數"),
    ],
}

# 各軸『綜合組成』：(來源, 鍵, 標籤, 基礎權重)。trad=傳統(SQL 算的軸 PR)；adv=進階官方 _pr
# （已定向為高=好，免反轉）。進階僅本季有、覆蓋稀疏 → 缺項自動移除並重正規化權重（無進階
# 即退回純傳統單指標）。
_COMPOSITE = {
    "batting": {
        "contact": [("trad", "contact", "接觸率", 0.45), ("adv", "whiffp_pr", "揮空抑制", 0.55)],
        "power": [("trad", "power", "ISO", 0.30), ("adv", "ev_pr", "擊球initial速", 0.25),
                  ("adv", "hardhitp_pr", "強擊球%", 0.25), ("adv", "brlp_pr", "Barrel%", 0.20)],
        "eye": [("trad", "eye", "保送率", 0.5), ("adv", "chasep_pr", "追打抑制", 0.5)],
        "speed": [("trad", "speed", "盜壘＋三壘打", 1.0)],
        "defense": [("trad", "defense", "守備範圍/阻殺", 1.0)],
    },
    "pitching": {
        "weapon": [("trad", "weapon", "武器", 1.0)],   # 標籤動態（三振/滾地/飛球）
        "control": [("trad", "control", "BB/9", 0.5), ("adv", "bbp_pr", "保送抑制", 0.25),
                    ("adv", "chasep_pr", "誘揮", 0.25)],
        "hr_suppress": [("trad", "hr_suppress", "HR/9", 0.4), ("adv", "brlp_pr", "Barrel抑制", 0.3),
                        ("adv", "hardhitp_pr", "強擊抑制", 0.3)],
        "command": [("trad", "command", "ERA", 0.5), ("adv", "woba_pr", "被 wOBA", 0.5)],
        "stamina": [("trad", "stamina", "續航", 1.0)],
    },
}

# 門檻：生涯較嚴、本季較鬆（本季賽程未過半）。
_ABILITY_MIN = {"batting": {"career": 300, "season": 50}, "pitching": {"career": 100, "season": 20}}


def _bat_ability_sql(scope: str) -> str:
    """打者能力 SQL：career=逐年彙總(AB≥300)，season=本季(AB≥50)。

    守備改用『守位內守備範圍 (PO+A)/G』並於同守位內取百分位（反映範圍而非僅不失誤；
    取主守位＝場次最多者），故守備 PR 由 fld 先算好，主 pr CTE 不再全域重排。
    """
    # 守備：野手＝守位內守備範圍 (PO+A)/G；捕手＝阻殺率 cs/(cs+被盜)。兩表欄位/守位碼不同。
    if scope == "career":
        base = ("SELECT player_id, sum(ab) ab, sum(h) h, sum(b2) b2, sum(b3) b3, sum(hr) hr,"
                " sum(bb) bb, sum(hbp) hbp, sum(sf) sf, sum(pa) pa, sum(sb) sb, sum(so) so, sum(g) g"
                " FROM cpbl.batting_seasons GROUP BY player_id HAVING sum(ab) >= %(min)s")
        fld_src, catcher, sba_col, fld_min = "cpbl.fielding_seasons", "'C'", "sb", 30
    else:
        base = ("SELECT player_id, ab, h, b2, b3, hr, bb, hbp, sf, pa, sb, so, g"
                " FROM cpbl.batting_current WHERE year=%(yr)s AND ab >= %(min)s")
        fld_src, catcher, sba_col, fld_min = (
            "(SELECT * FROM cpbl.fielding_current WHERE year=%(yr)s) fc", "'捕手'", "sba", 8)
    return f"""
        WITH base AS ({base}),
        pos_rf AS (
            SELECT player_id, pos, sum(g) g,
                CASE WHEN pos = {catcher} AND sum(cs)+sum({sba_col}) > 0
                     THEN sum(cs)::float/(sum(cs)+sum({sba_col}))
                     ELSE (sum(po)+sum(a))::float/NULLIF(sum(g),0) END rf
            FROM {fld_src} GROUP BY player_id, pos HAVING sum(g) >= {fld_min}
        ), pos_pr AS (
            SELECT player_id, pos, g, rf,
                   percent_rank() OVER (PARTITION BY pos ORDER BY rf) rf_pr
            FROM pos_rf
        ), fld AS (   -- 取主守位（場次最多）：守備值、守位內百分位、是否捕手
            SELECT DISTINCT ON (player_id) player_id, rf AS defense, rf_pr AS defense_pr,
                   (pos = {catcher}) AS is_catcher
            FROM pos_pr ORDER BY player_id, g DESC
        ), rate AS (
            SELECT b.player_id,
                (pa - so)::float/NULLIF(pa,0) contact,
                (b2+2*b3+3*hr)::float/NULLIF(ab,0) power,
                bb::float/NULLIF(pa,0) eye,
                (sb+b3)::float/NULLIF(g,0) speed,
                f.defense, f.defense_pr, f.is_catcher,
                (h+bb+hbp)::float/NULLIF(ab+bb+hbp+sf,0)+(h+b2+2*b3+3*hr)::float/NULLIF(ab,0) ops
            FROM base b LEFT JOIN fld f USING (player_id)
        ), pr AS (
            SELECT player_id, contact, power, eye, speed, defense, defense_pr, is_catcher,
                percent_rank() OVER (ORDER BY contact) contact_pr,
                percent_rank() OVER (ORDER BY power) power_pr,
                percent_rank() OVER (ORDER BY eye) eye_pr,
                percent_rank() OVER (ORDER BY speed) speed_pr,
                percent_rank() OVER (ORDER BY ops) ops_pr
            FROM rate
        ), ov AS (   -- 總評重排：以打擊產能 OPS 為主(權重3，已綜合接觸/力量/選球，強打不被低接觸拖累)
            -- + 速度/守備為輔(各1)，再取全聯盟百分位（守備缺→中性 0.5）。
            SELECT *, percent_rank() OVER (ORDER BY
                3 * ops_pr + speed_pr + COALESCE(defense_pr, 0.5)) ov_pr
            FROM pr
        ) SELECT contact, power, eye, speed, defense,
                 contact_pr, power_pr, eye_pr, speed_pr, defense_pr, is_catcher, ov_pr
          FROM ov WHERE player_id = %(pid)s
    """


def _pit_ability_sql(scope: str) -> str:
    """投手能力 SQL：career=逐年彙總(IP≥100)，season=本季(IP≥20)。越低越好者 DESC 反轉。

    續航：先發＝每場局數 IP/G、後援＝登板數 G（後援按設計只投 1 局，用 IP/G 不公平）；
    且 stamina 百分位在『同類型（先發/後援）』內計算。is_starter＝先發場數佔半數以上。
    """
    ip_expr = "floor(ip) + (ip - floor(ip))*10/3.0"
    if scope == "career":
        base = (f"SELECT player_id, sum({ip_expr}) ip, sum(so) so, sum(bb) bb, sum(hr) hr,"
                " sum(er) er, sum(g) g, sum(gs) gs, sum(go)::float/NULLIF(sum(fo),0) gb"
                f" FROM cpbl.pitching_seasons GROUP BY player_id HAVING sum({ip_expr}) >= %(min)s")
    else:
        base = (f"SELECT player_id, ({ip_expr}) ip, so, bb, hr, er, g, gs, goao gb"
                f" FROM cpbl.pitching_current WHERE year=%(yr)s AND ({ip_expr}) >= %(min)s")
    return f"""
        WITH base AS ({base}),
        rate AS (
            SELECT player_id, so*9.0/NULLIF(ip,0) k, gb,
                CASE WHEN gb > 0 THEN 1.0/gb END fb,   -- 飛球傾向 AO/GO（gb=GO/AO 之倒數）
                bb*9.0/NULLIF(ip,0) control, hr*9.0/NULLIF(ip,0) hr_suppress,
                er*9.0/NULLIF(ip,0) command, (gs*2 >= g) AS is_starter,
                CASE WHEN gs*2 >= g THEN ip/NULLIF(g,0) ELSE g::float END stamina
            FROM base
        ), prx AS (
            SELECT *, percent_rank() OVER (ORDER BY k) k_pr,
                percent_rank() OVER (ORDER BY gb) gb_pr,
                percent_rank() OVER (ORDER BY fb) fb_pr,
                percent_rank() OVER (ORDER BY control DESC) control_pr,
                percent_rank() OVER (ORDER BY hr_suppress DESC) hr_suppress_pr,
                percent_rank() OVER (ORDER BY command DESC) command_pr,
                percent_rank() OVER (PARTITION BY is_starter ORDER BY stamina) stamina_pr
            FROM rate
        ), pr AS (   -- 武器＝三振/滾地/飛球中 PR 最高者（最突出的出局方式）
            SELECT *,
                GREATEST(k_pr, COALESCE(gb_pr,0), COALESCE(fb_pr,0)) weapon_pr,
                CASE WHEN k_pr >= COALESCE(gb_pr,0) AND k_pr >= COALESCE(fb_pr,0) THEN '三振'
                     WHEN COALESCE(gb_pr,0) >= COALESCE(fb_pr,0) THEN '滾地' ELSE '飛球' END weapon_type,
                CASE WHEN k_pr >= COALESCE(gb_pr,0) AND k_pr >= COALESCE(fb_pr,0) THEN k
                     WHEN COALESCE(gb_pr,0) >= COALESCE(fb_pr,0) THEN gb ELSE fb END weapon_val
            FROM prx
        ), ov AS (   -- 總評重排：以壓制 ERA 為主(權重3，bottom-line 防失分) + 其餘為輔，再全聯盟百分位
            SELECT *, percent_rank() OVER (ORDER BY
                3 * command_pr + weapon_pr + control_pr + hr_suppress_pr + stamina_pr) ov_pr
            FROM pr
        ) SELECT weapon_val, control, hr_suppress, command, stamina,
                 weapon_pr, control_pr, hr_suppress_pr, command_pr, stamina_pr,
                 is_starter, ov_pr, weapon_type
          FROM ov WHERE player_id = %(pid)s
    """


def _ability_card(cur, player_id: str, role: str, scope: str, year: int) -> dict:
    axes_def = _ABILITY_AXES[role]
    sql = _bat_ability_sql(scope) if role == "batting" else _pit_ability_sql(scope)
    cur.execute(sql, {"pid": player_id, "yr": year, "min": _ABILITY_MIN[role][scope]})
    row = cur.fetchone()
    if not row:
        return {"available": False, "role": role, "scope": scope}
    n = len(axes_def)
    values, prs = row[:n], row[n:2 * n]
    flag = row[2 * n] if len(row) > 2 * n else None      # 打者=是否捕手 / 投手=是否先發
    ov_pr = row[2 * n + 1] if len(row) > 2 * n + 1 else None  # 整體表現的全聯盟重排百分位
    weapon_type = row[2 * n + 2] if len(row) > 2 * n + 2 else None  # 投手武器型（三振/滾地/飛球）
    # 傳統各軸 PR（percent_rank 0~1 → 0~100）；None=該軸無資料（如 DH 無守備）。
    trad_pr = {axes_def[i][0]: (None if values[i] is None else round(float(prs[i]) * 100))
               for i in range(n)}

    # 進階官方 PR（僅本季、足量打席才採；已定向高=好）。覆蓋稀疏故多數球員為空。
    adv: dict[str, int] = {}
    if scope == "season":
        cur.execute(
            "SELECT pa, woba_pr, iso_pr, ev_pr, hardhitp_pr, brlp_pr, kp_pr, bbp_pr, whiffp_pr, chasep_pr "
            "FROM cpbl.advanced_stats WHERE acnt=%s AND year=%s AND role=%s AND kind_code='A'",
            (player_id, year, role))
        ar = cur.fetchone()
        if ar and (ar[0] or 0) >= 30:
            for col, v in zip(["woba_pr", "iso_pr", "ev_pr", "hardhitp_pr", "brlp_pr",
                               "kp_pr", "bbp_pr", "whiffp_pr", "chasep_pr"], ar[1:], strict=True):
                if v is not None:
                    adv[col] = int(v)

    axes = []
    for key, label, _fmt, _src in axes_def:
        ax_label = weapon_type if (key == "weapon" and weapon_type) else label  # 武器軸動態標籤
        comps = []
        for src, ck, clabel, w in _COMPOSITE[role][key]:
            pr = trad_pr.get(ck) if src == "trad" else adv.get(ck)
            if src == "trad" and key == "defense" and flag:
                clabel = "阻殺率"          # 捕手守備組成標籤特化
            if src == "trad" and key == "stamina" and flag is False:
                clabel = "登板數"          # 後援續航
            if src == "trad" and key == "weapon" and weapon_type:
                clabel = weapon_type       # 武器＝三振/滾地/飛球
            if pr is not None:
                comps.append({"label": clabel, "weight": w, "pr": pr})
        if not comps:
            axes.append({"key": key, "label": ax_label, "pr": None, "grade": None, "components": []})
            continue
        tot = sum(c["weight"] for c in comps)
        final = round(sum(c["pr"] * c["weight"] for c in comps) / tot)
        for c in comps:                    # 權重正規化為百分比供 tooltip 顯示
            c["weight"] = round(c["weight"] / tot * 100)
        axes.append({"key": key, "label": ax_label, "pr": final,
                     "grade": _grade(final), "components": comps})

    # 總評＝整體表現在全聯盟的『重排百分位』：把每位合格球員的各軸 PR 加總後再 percent_rank，
    # 故最強者→PR100→S、自然拉開分級（不像各軸平均會壓在中間害大家都 B/C）。
    rated = [a["pr"] for a in axes if a["pr"] is not None]
    overall = (round(float(ov_pr) * 100) if ov_pr is not None
               else (round(sum(rated) / len(rated)) if rated else 0))
    if role == "batting":
        power_pr = next((a["pr"] for a in axes if a["key"] == "power" and a["pr"] is not None), None)
        # 總評融入『力量軸』（已綜合官方 Barrel%/強擊球/初速＝擊球品質）：SQL 重排只看 OPS 結果，
        # 會低估「紮實接觸但結果衰運(低 BABIP)」的重砲手（如朱育賢 Barrel96 卻 OPS 中庸）。以
        # xStats 精神用擊球品質拉抬，無進階者力量軸退回 ISO 故仍合理（守住紅線：非抄計數型 HR/RBI）。
        # 只『拉抬』不『懲罰』：取 max，速度/守備型不會被低力量拖累。
        if ov_pr is not None and power_pr is not None:
            overall = max(overall, round(0.6 * overall + 0.4 * power_pr))
        # DH（無守備數據）守備軸改以打擊火力呈現——「DH 用強棒守備」，免雷達 0 凹陷誤看成弱點。
        if power_pr is not None:
            for a in axes:
                if a["key"] == "defense" and a["pr"] is None:
                    a["label"], a["pr"], a["grade"] = "指打", power_pr, _grade(power_pr)
                    a["components"] = [{"label": "打擊火力（代守備）", "weight": 100, "pr": power_pr}]
    # 特色標籤（彰顯球員類型，不合軸）。
    # 打者：取進攻工具中最突出者；多項 ≥80 → 全能。
    # 投手：取最突出的出局方式（weapon_type＝三振/滾地/飛球，後端 SQL 已算）。
    signature = None
    if role == "batting":
        names = {"power": "強打", "contact": "巧打", "eye": "選球", "speed": "快腿"}
        off = {a["key"]: a["pr"] for a in axes
               if a["key"] in names and a["pr"] is not None}
        if off:
            strong = [names[k] for k, v in off.items() if v >= 80]
            top = max(off, key=off.get)
            signature = "全能" if len(strong) >= 3 else "·".join(strong[:2]) if strong else names[top]
    elif role == "pitching":
        signature = weapon_type
    return {"available": True, "role": role, "scope": scope, "axes": axes,
            "has_advanced": bool(adv), "signature": signature,
            "overall": {"pr": overall, "grade": _grade(overall)}}


@app.get("/api/v1/players/{player_id}/ability-card")
def player_ability_card(player_id: str, season: int = Query(DEFAULT_SEASON)) -> dict:
    """遊戲風能力值卡：打者/投手雷達，含生涯與本季兩種尺度（rate 的全聯盟百分位）。"""
    with conn() as c:
        cur = c.cursor()
        out: dict = {"player_id": player_id}
        for role in ("batting", "pitching"):
            out[role] = {"career": _ability_card(cur, player_id, role, "career", season),
                         "season": _ability_card(cur, player_id, role, "season", season)}
        return out


@app.get("/api/v1/players/{player_id}/advanced")
def player_advanced(player_id: str, season: int = Query(DEFAULT_SEASON),
                    kind_code: str = Query("A", pattern="^(A|D)$")) -> dict:
    """官方進階數據（stats.cpbl）+ 官方 PR。batting=進攻、pitching=被打。kind_code：A=一軍 D=二軍。"""
    out: dict[str, Any] = {"player_id": player_id, "season": season, "kind_code": kind_code,
                           "batting": None, "pitching": None}
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT * FROM cpbl.advanced_stats WHERE acnt = %s AND year = %s AND kind_code = %s",
                    (player_id, season, kind_code))
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
    kind_code: str = Query("A", pattern="^(A|D)$"),
) -> dict:
    """好球帶紀律（自 pitch_tracking 計算）。batting=該打者面對；pitching=該投手誘導。
    含揮棒/揮空/接觸/CSW/追打/帶內揮棒/好球帶比例，及進壘點散布。kind_code：A=一軍 D=二軍。"""
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
              WHERE {col} = %s AND year = %s AND kind_code = %s AND plate_loc_side IS NOT NULL
            ) q
            """,
            (player_id, season, kind_code),
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
            SELECT plate_loc_side, plate_loc_height, pitch_call, content, hit_exit_speed, hit_launch_angle,
                   tagged_pitch_type
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND plate_loc_side IS NOT NULL
            """,
            (player_id, season, kind_code),
        )
        _swset = {"InPlay", "FoulBallNotFieldable", "FoulBallFieldable", "StrikeSwinging"}
        points = [{"x": float(s), "y": float(h),
                   "sw": pc in _swset, "wh": pc == "StrikeSwinging",
                   "result": _zone_result(pc, ct), "ev": float(ev) if ev is not None else None,
                   "la": float(la) if la is not None else None, "pt": pt}
                  for s, h, pc, ct, ev, la, pt in cur.fetchall()]
        cur.execute(
            f"""
            SELECT hit_direction, hit_distance, hit_exit_speed, content, tagged_pitch_type, hit_launch_angle
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND pitch_call = 'InPlay'
              AND hit_distance IS NOT NULL AND hit_direction IS NOT NULL
            """,
            (player_id, season, kind_code),
        )
        spray = [{"dir": float(d), "dist": float(dist),
                  "ev": float(ev) if ev is not None else None, "result": _batted_result(ct), "pt": pt,
                  "la": float(la) if la is not None else None}
                 for d, dist, ev, ct, pt, la in cur.fetchall()]
        # 擊球仰角 × 初速（barrel 散點）：InPlay 且有 LA+EV
        cur.execute(
            f"""
            SELECT hit_launch_angle, hit_exit_speed, content
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND pitch_call = 'InPlay'
              AND hit_launch_angle IS NOT NULL AND hit_exit_speed IS NOT NULL
            """,
            (player_id, season, kind_code),
        )
        batted = [{"la": float(la), "ev": float(ev), "result": _batted_result(ct)}
                  for la, ev, ct in cur.fetchall()]
        # 擊球品質（打者）／球質（投手）：逐球樣本衍生
        cur.execute(
            f"""
            SELECT round(avg(hit_launch_angle)::numeric, 1), round(max(hit_distance)::numeric, 1),
                   round(avg(hit_exit_speed)::numeric, 1), round(avg(extension)::numeric, 2),
                   round(avg(rel_height)::numeric, 2), round(avg(rel_speed)::numeric, 1)
            FROM cpbl.pitch_tracking WHERE {col} = %s AND year = %s AND kind_code = %s
            """,
            (player_id, season, kind_code),
        )
        la, maxd, ev, ext, relh, rels = cur.fetchone()
        fl = lambda v: float(v) if v is not None else None  # noqa: E731
        _q = lambda la, maxd, ev, ext, relh, rels: {  # noqa: E731
            "avg_launch_angle": fl(la), "max_hit_dist": fl(maxd), "avg_exit_speed": fl(ev),
            "avg_extension": fl(ext), "avg_rel_height": fl(relh), "avg_speed": fl(rels)}
        quality = _q(la, maxd, ev, ext, relh, rels)
        # 依球種拆的球質/擊球品質，供前端球種鏡頭切換（tagged_pitch_type：fastball/breakingball）
        cur.execute(
            f"""
            SELECT tagged_pitch_type,
                   round(avg(hit_launch_angle)::numeric, 1), round(max(hit_distance)::numeric, 1),
                   round(avg(hit_exit_speed)::numeric, 1), round(avg(extension)::numeric, 2),
                   round(avg(rel_height)::numeric, 2), round(avg(rel_speed)::numeric, 1)
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND tagged_pitch_type IS NOT NULL
            GROUP BY tagged_pitch_type
            """,
            (player_id, season, kind_code),
        )
        quality_by_pt = {row[0]: _q(*row[1:]) for row in cur.fetchall()}
    return {"player_id": player_id, "role": role, "summary": summary,
            "quality": quality, "quality_by_pt": quality_by_pt,
            "points": points, "spray": spray, "batted": batted}


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


@app.get("/api/v1/standings")
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


@app.get("/api/v1/standings-trend")
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
    "AIL011": "AII011",                                    # 誠泰Cobras → 米迪亞暴龍（同血脈，2008 解散）
}


def _franchise_of(code: str) -> str:
    return _FRANCHISE.get(code, code)


def _franchise_year_record(cur, fc: str, kind_code: str = "A") -> dict[int, dict]:
    """franchise 跨年代各 era 隊碼合併的逐年一軍 W/L/T（kind A 故自動排除二軍）。

    供總教練戰績以 DB 重算（維基數據常滯後當季）。回 {year: {w,l,t}}。
    """
    members = sorted({c for c in (set(_FRANCHISE) | set(_FRANCHISE.values()) | {fc})
                      if _franchise_of(c) == fc})
    cur.execute(
        "SELECT year, home_team_code, home_score, away_score FROM cpbl.games "
        "WHERE kind_code=%s AND home_score+away_score>0 "
        "AND (home_team_code = ANY(%s) OR away_team_code = ANY(%s))",
        (kind_code, members, members))
    rec: dict[int, dict] = {}
    for y, hc, hs, as_ in cur.fetchall():
        d = rec.setdefault(y, {"w": 0, "l": 0, "t": 0})
        won = (hs > as_) if hc in members else (as_ > hs)
        tie = hs == as_
        d["t" if tie else "w" if won else "l"] += 1
    return rec


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
            "AND (home_team_code = ANY(%s) OR away_team_code = ANY(%s)) ORDER BY year, game_sno",
            (kind_code, members, members),
        ).fetchall()
        names = dict(c.execute("SELECT team_id, name FROM cpbl.teams").fetchall())  # 3 碼 → 全名
    rec: dict = defaultdict(lambda: {"w": 0, "l": 0, "t": 0})
    seq: list[str] = []  # franchise 逐場結果（時序）算最長連勝/連敗
    for y, hc, ac, hs, as_ in games:
        if hc in members:
            res = "W" if hs > as_ else "L" if as_ > hs else "T"
            rec[(hc, y)][res.lower() if res != "T" else "t"] += 1
            seq.append(res)
        elif ac in members:
            res = "W" if as_ > hs else "L" if hs > as_ else "T"
            rec[(ac, y)][res.lower() if res != "T" else "t"] += 1
            seq.append(res)

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

    # 隊史總戰績
    tw = sum(e["w"] for e in eras)
    tl = sum(e["l"] for e in eras)
    tt = sum(e["t"] for e in eras)
    total = {"w": tw, "l": tl, "t": tt, "win_pct": round(tw / (tw + tl), 3) if tw + tl else None}
    # 最長連勝 / 連敗（時序）
    mw = ml = cw = cl = 0
    for res in seq:
        cw = cw + 1 if res == "W" else 0
        cl = cl + 1 if res == "L" else 0
        mw, ml = max(mw, cw), max(ml, cl)

    # 單季之最（最佳/最差賽季；至少 30 決勝場）
    def _era_name(year: int) -> str:
        return next((e["name"] for e in eras if e["from"] <= year <= e["to"]), fc)
    seasons = [{"year": y, "name": _era_name(y), "w": v["w"], "l": v["l"], "t": v["t"],
                "win_pct": round(v["w"] / (v["w"] + v["l"]), 3)}
               for (cc, y), v in rec.items() if v["w"] + v["l"] >= 30]
    best = max(seasons, key=lambda s: s["win_pct"], default=None)
    worst = min(seasons, key=lambda s: s["win_pct"], default=None)
    return {"franchise": fc, "origins": _ORIGINS.get(fc), "eras": eras, "total": total,
            "longest_win_streak": mw, "longest_lose_streak": ml,
            "best_season": best, "worst_season": worst}


@app.get("/api/v1/franchises")
def franchises() -> dict:
    """所有 franchise（現役 + 已解散）索引：年代、隊史總戰績、era 名單。供歷史球隊入口。"""
    from collections import defaultdict
    with conn() as c:
        games = c.execute(
            "SELECT year, home_team_code, away_team_code, home_score, away_score "
            "FROM cpbl.games WHERE kind_code='A' AND home_score+away_score>0"
        ).fetchall()
        names3 = dict(c.execute("SELECT team_id, name FROM cpbl.teams").fetchall())
        active = {r[0] for r in c.execute("SELECT team_code FROM cpbl.team_dim WHERE active=true").fetchall()}
    rec: dict = defaultdict(lambda: {"w": 0, "l": 0, "t": 0})
    for y, hc, ac, hs, as_ in games:
        rec[(hc, y)]["w" if hs > as_ else "l" if as_ > hs else "t"] += 1
        rec[(ac, y)]["w" if as_ > hs else "l" if hs > as_ else "t"] += 1
    fr: dict = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "years": set(), "members": set()})
    for (code, y), v in rec.items():
        f = fr[_franchise_of(code)]
        f["w"] += v["w"]; f["l"] += v["l"]; f["t"] += v["t"]
        f["years"].add(y); f["members"].add(code)
    items = []
    for fc, f in fr.items():
        ys = sorted(f["years"])
        eras: list[dict] = []
        for m in sorted(f["members"]):
            myears = sorted(y for (cc, y) in rec if cc == m)
            if not myears:
                continue
            code6 = f"{m[:3]}011"
            if m in _ERA_SPLIT:  # 同代碼內改名（La New / Lamigo）
                for nm, a, b in _ERA_SPLIT[m]:
                    run = [y for y in myears if a <= y <= b]
                    if run:
                        eras.append({"code": code6, "name": nm, "from": run[0], "to": run[-1]})
            else:  # 依年份缺口斷代（味全解散前/重組後）
                run = [myears[0]]
                for y in myears[1:] + [None]:
                    if y is not None and y == run[-1] + 1:
                        run.append(y)
                    else:
                        eras.append({"code": code6, "name": names3.get(m[:3], m), "from": run[0], "to": run[-1]})
                        if y is not None:
                            run = [y]
        eras.sort(key=lambda e: e["from"])
        w, lo, t = f["w"], f["l"], f["t"]
        items.append({
            "code": fc, "name": names3.get(fc[:3], fc), "active": fc in active,
            "from": ys[0], "to": ys[-1], "w": w, "l": lo, "t": t,
            "win_pct": round(w / (w + lo), 3) if w + lo else None, "eras": eras,
        })
    items.sort(key=lambda x: (not x["active"], x["from"]))
    return {"items": items}


@app.get("/api/v1/teams/{code}/players")
def team_players(code: str) -> dict:
    """franchise 歷代球員（OB 入口）：曾效力者依生涯出賽數排序，標注現役。

    members 取 3 碼前綴對齊 batting_seasons.team_id（3 碼/6 碼並存），故誠泰→米迪亞、
    俊國→興農→義大→富邦 等同 franchise 歷代球員一併列入。現役 = 本季登錄打/投。
    """
    fc = _franchise_of(code)
    members3 = sorted({c[:3] for c in (set(_FRANCHISE) | set(_FRANCHISE.values()) | {fc}) if _franchise_of(c) == fc})
    with conn() as c:
        cur = c.cursor()
        active = {r[0] for r in cur.execute(
            "SELECT player_id FROM cpbl.batting_current "
            "UNION SELECT player_id FROM cpbl.pitching_current"
        ).fetchall()}
        cur.execute(
            "SELECT bs.player_id, p.name, sum(bs.g), sum(bs.h), sum(bs.hr), sum(bs.rbi), "
            "min(bs.year), max(bs.year) FROM cpbl.batting_seasons bs "
            "LEFT JOIN cpbl.players p ON p.id = bs.player_id "
            "WHERE substring(bs.team_id, 1, 3) = ANY(%s) "
            "GROUP BY bs.player_id, p.name ORDER BY sum(bs.g) DESC NULLS LAST LIMIT 50",
            (members3,))
        batters = [
            {"player_id": pid, "name": nm or pid, "g": g, "h": h, "hr": hr, "rbi": rbi,
             "from": y0, "to": y1, "active": pid in active}
            for pid, nm, g, h, hr, rbi, y0, y1 in cur.fetchall()
        ]
        cur.execute(
            "SELECT ps.player_id, p.name, sum(ps.g), sum(ps.w), sum(ps.sv), sum(ps.so), "
            "min(ps.year), max(ps.year) FROM cpbl.pitching_seasons ps "
            "LEFT JOIN cpbl.players p ON p.id = ps.player_id "
            "WHERE substring(ps.team_id, 1, 3) = ANY(%s) "
            "GROUP BY ps.player_id, p.name ORDER BY sum(ps.g) DESC NULLS LAST LIMIT 50",
            (members3,))
        pitchers = [
            {"player_id": pid, "name": nm or pid, "g": g, "w": w, "sv": sv, "so": so,
             "from": y0, "to": y1, "active": pid in active}
            for pid, nm, g, w, sv, so, y0, y1 in cur.fetchall()
        ]
        # 現役教練團（最新一季；僅現役球團有，依角色排序：總教練優先）
        cur.execute(
            "SELECT pos, name, uniform_no FROM cpbl.coaches "
            "WHERE team_code=%s AND year=(SELECT max(year) FROM cpbl.coaches WHERE team_code=%s) "
            "ORDER BY (pos LIKE '%%總教練%%') DESC, pos, uniform_no", (code, code))
        coaches = [{"pos": p, "name": n, "uniform_no": u} for p, n, u in cur.fetchall()]
        # 教練若為中職前球員（生涯有打/投紀錄）且同名唯一 → 附 player_id 供連結球員頁
        if coaches:
            names = list({c["name"] for c in coaches})
            cur.execute(
                "SELECT name, max(id) FROM cpbl.players p WHERE name = ANY(%s) "
                "AND (EXISTS(SELECT 1 FROM cpbl.batting_seasons b WHERE b.player_id=p.id) "
                "  OR EXISTS(SELECT 1 FROM cpbl.pitching_seasons s WHERE s.player_id=p.id)) "
                "GROUP BY name HAVING count(*)=1", (names,))
            pid_of = {n: pid for n, pid in cur.fetchall()}
            for c in coaches:
                c["player_id"] = pid_of.get(c["name"])
        # 現役名單：一軍 current + 二軍 D-gamelog（022 farm 代碼）。已解散隊自然回空。
        yr = DEFAULT_SEASON
        cur.execute("SELECT player_id, name FROM cpbl.batting_current WHERE team_code=%s AND year=%s "
                    "ORDER BY name", (code, yr))
        first_batters = [{"player_id": p, "name": n} for p, n in cur.fetchall()]
        cur.execute("SELECT player_id, name FROM cpbl.pitching_current WHERE team_code=%s AND year=%s "
                    "ORDER BY name", (code, yr))
        first_pitchers = [{"player_id": p, "name": n} for p, n in cur.fetchall()]
        first_ids = {p["player_id"] for p in first_batters} | {p["player_id"] for p in first_pitchers}
        farm_code = f"{code[:3]}022"
        cur.execute(
            "SELECT acnt, max(nm) FROM ("
            "  SELECT bg.hitter_acnt acnt, bg.hitter_name nm FROM cpbl.batting_gamelog bg "
            "    JOIN cpbl.games g ON g.year=bg.year AND g.kind_code=bg.kind_code AND g.game_sno=bg.game_sno "
            "    WHERE bg.year=%s AND bg.kind_code='D' "
            "      AND (CASE WHEN bg.visiting_home_type='2' THEN g.home_team_code ELSE g.away_team_code END)=%s "
            "  UNION ALL "
            "  SELECT pg.pitcher_acnt, pg.pitcher_name FROM cpbl.pitching_gamelog pg "
            "    JOIN cpbl.games g ON g.year=pg.year AND g.kind_code=pg.kind_code AND g.game_sno=pg.game_sno "
            "    WHERE pg.year=%s AND pg.kind_code='D' "
            "      AND (CASE WHEN pg.visiting_home_type='2' THEN g.home_team_code ELSE g.away_team_code END)=%s "
            ") x GROUP BY acnt ORDER BY max(nm)", (yr, farm_code, yr, farm_code))
        farm = [{"player_id": p, "name": n} for p, n in cur.fetchall() if p not in first_ids]
        roster = {"first_batters": first_batters, "first_pitchers": first_pitchers, "farm": farm}
        # 歷任總教練（維基；franchise 代碼）。同名前球員唯一者附 player_id 供連結。
        cur.execute(
            "SELECT era_name, name, from_year, to_year, w, l, t, win_pct, postseason, championships "
            "FROM cpbl.managers WHERE team_code=%s ORDER BY from_year, name", (fc,))
        managers = [{"era": e, "name": n, "from": fy, "to": ty, "w": w, "l": l, "t": t,
                     "win_pct": wp, "postseason": po, "championships": ch}
                    for e, n, fy, ty, w, l, t, wp, po, ch in cur.fetchall()]
        # 官網 coaches 的現任一軍總教練（權威；維基歷任表常滯後當季/換帥）
        head = next((c["name"] for c in coaches if "總教練" in c["pos"] or "監督" in c["pos"]), None)
        if managers:
            mnames = list({m["name"] for m in managers} | ({head} if head else set()))
            cur.execute(
                "SELECT name, max(id) FROM cpbl.players p WHERE name = ANY(%s) "
                "AND (EXISTS(SELECT 1 FROM cpbl.batting_seasons b WHERE b.player_id=p.id) "
                "  OR EXISTS(SELECT 1 FROM cpbl.pitching_seasons s WHERE s.player_id=p.id)) "
                "GROUP BY name HAVING count(*)=1", (mnames,))
            mpid = {n: pid for n, pid in cur.fetchall()}
            for m in managers:
                m["player_id"] = mpid.get(m["name"])
            # 戰績以 DB 重算（維基常滯後當季）：僅當該總教練任期每一年都是該隊「唯一」
            # 總教練（無換帥/代理）才採用——有 split 的年份無法由比賽逐場掛帥，保留維基拆分。
            from collections import defaultdict as _dd
            yr_cnt: dict[int, int] = _dd(int)
            for m in managers:
                if m["from"] and m["to"]:
                    for y in range(m["from"], m["to"] + 1):
                        yr_cnt[y] += 1
            fyr = _franchise_year_record(cur, fc, "A")
            for m in managers:
                m["source"] = "wiki"
                if not (m["from"] and m["to"]):
                    continue
                yrs = range(m["from"], m["to"] + 1)
                if not all(yr_cnt[y] == 1 for y in yrs):
                    continue   # 有 split 年 → 保留維基
                w = sum(fyr.get(y, {}).get("w", 0) for y in yrs)
                lo = sum(fyr.get(y, {}).get("l", 0) for y in yrs)
                t = sum(fyr.get(y, {}).get("t", 0) for y in yrs)
                if w + lo > 0:   # 有 DB 一軍資料才覆寫（早年無 games 不動）
                    m["w"], m["l"], m["t"] = w, lo, t
                    m["g"] = w + lo + t
                    m["win_pct"] = round(w / (w + lo), 3)
                    m["source"] = "db"
            # 當季補丁：維基歷任表常缺當季。以官網現任總教練為準，若其維基列尚未涵蓋
            # 當季（to < 當季），把當季 franchise 一軍 DB 戰績加上（當季尚無換帥故 solo，
            # 其原總和已正確至 to_year，僅補當季）；若現任未在維基表（換帥）則新增當季列。
            cur_year = max(fyr) if fyr else None
            cur_rec = fyr.get(cur_year) if cur_year else None
            if head and cur_rec and cur_rec["w"] + cur_rec["l"] > 0:
                rows = [m for m in managers if m["name"] == head]
                latest = max(rows, key=lambda m: m["to"] or 0) if rows else None
                if latest and (latest["to"] or 0) >= cur_year:
                    pass   # 維基已涵蓋當季（如味全葉君璋 to=2026）
                elif latest:
                    latest["w"] += cur_rec["w"]; latest["l"] += cur_rec["l"]; latest["t"] += cur_rec["t"]
                    latest["to"] = cur_year
                    latest["g"] = latest["w"] + latest["l"] + latest["t"]
                    latest["win_pct"] = (round(latest["w"] / (latest["w"] + latest["l"]), 3)
                                         if latest["w"] + latest["l"] else None)
                    latest["source"] = "db"
                else:   # 現任不在維基歷任表（換帥）→ 新增當季列
                    managers.append({
                        "era": managers[-1]["era"] if managers else "", "name": head,
                        "from": cur_year, "to": cur_year, "w": cur_rec["w"], "l": cur_rec["l"],
                        "t": cur_rec["t"], "g": cur_rec["w"] + cur_rec["l"] + cur_rec["t"],
                        "win_pct": (round(cur_rec["w"] / (cur_rec["w"] + cur_rec["l"]), 3)
                                    if cur_rec["w"] + cur_rec["l"] else None),
                        "postseason": 0, "championships": 0,
                        "player_id": mpid.get(head), "source": "db"})
        # 退休背號（維基；球迷/球團 holder_type 非 player → 不附球員連結）
        cur.execute(
            "SELECT number, holder_type, player_id, holder_name, status, note "
            "FROM cpbl.retired_numbers WHERE team_code=%s "
            "ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, number", (fc,))
        retired = [{"number": num, "holder_type": ht, "player_id": pid, "holder": hn,
                    "status": st, "note": note}
                   for num, ht, pid, hn, st, note in cur.fetchall()]
    return {"code": fc, "batters": batters, "pitchers": pitchers, "coaches": coaches,
            "roster": roster, "managers": managers, "retired": retired}


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
    kind_code: str = Query("A", pattern="^(A|D)$"),
) -> dict:
    """配球傾向：不同球數情境下的速球／變化球占比。pitching=投手配球、batting=打者面對。kind_code：A=一軍 D=二軍。"""
    col = "pitcher_acnt" if role == "pitching" else "hitter_acnt"
    order = ["第一球", "打者領先", "平球數", "投手領先", "兩好球"]
    agg: dict[str, dict[str, int]] = {k: {"fastball": 0, "breakingball": 0} for k in order}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT ball_cnt, strike_cnt, tagged_pitch_type
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND tagged_pitch_type IS NOT NULL
              AND ball_cnt IS NOT NULL AND strike_cnt IS NOT NULL
            """,
            (player_id, season, kind_code),
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
    """逐場趨勢：rate 型用「近 N 場滾動」（累積 rate 會收斂拉平、看不出冷熱手），
    計數型維持累積配速線；另附滾動 OPS+/ERA+（季聯盟基準；100=聯盟均值，一軍才有）。"""
    n_roll = 15  # 滾動視窗場數（rate/OPS+/ERA+ 用；資料充足時最能表現近況）
    r3 = lambda v: round(v, 3) if v is not None else None  # noqa: E731
    with conn() as c:
        cur = c.cursor()
        if role == "batting":
            lg_obp = lg_slg = None
            if kind_code == "A":  # OPS+ 聯盟基準（僅一軍有）
                cur.execute("SELECT sum(ab), sum(h), sum(bb), sum(hbp), sum(sf), sum(tb) "
                            "FROM cpbl.batting_current WHERE year = %s", (season,))
                lab, lh, lbb, lhbp, lsf, ltb = (x or 0 for x in cur.fetchone())
                lg_obp = (lh + lbb + lhbp) / (lab + lbb + lhbp + lsf) if (lab + lbb + lhbp + lsf) else None
                lg_slg = ltb / lab if lab else None
            cur.execute(
                f"""
                SELECT g.game_date,
                    b.hits AS h_c, b.home_runs AS hr_c, b.rbi AS rbi_c,  -- 計數型：逐場值(柱狀)
                    sum(b.at_bats)     OVER roll AS ab_r,
                    sum(b.hits)        OVER roll AS h_r,
                    sum(b.bb)          OVER roll AS bb_r,
                    sum(b.hbp)         OVER roll AS hbp_r,
                    sum(b.sac_fly)     OVER roll AS sf_r,
                    sum(b.total_bases) OVER roll AS tb_r
                FROM cpbl.batting_gamelog b
                JOIN cpbl.games g
                  ON g.year = b.year AND g.kind_code = b.kind_code AND g.game_sno = b.game_sno
                WHERE b.hitter_acnt = %s AND b.year = %s AND b.kind_code = %s
                WINDOW roll AS (ORDER BY g.game_date, b.game_sno
                                ROWS BETWEEN {n_roll - 1} PRECEDING AND CURRENT ROW)
                ORDER BY g.game_date, b.game_sno
                """,
                (player_id, season, kind_code),
            )
            items = []
            for i, (d, h_c, hr_c, rbi_c, ab, h, bb, hbp, sf, tb) in enumerate(cur.fetchall(), 1):
                ab = ab or 0
                pa_ob = ab + (bb or 0) + (hbp or 0) + (sf or 0)
                small = ab < 30  # 滾動樣本太小(早季未滿窗)→ rate 過度波動,不輸出免尖刺
                obp = None if small else (((h or 0) + (bb or 0) + (hbp or 0)) / pa_ob if pa_ob else None)
                slg = None if small else ((tb or 0) / ab if ab else None)
                ops = (obp + slg) if obp is not None and slg is not None else None
                ops_plus = (round(100 * (obp / lg_obp + slg / lg_slg - 1))
                            if obp is not None and slg is not None and lg_obp and lg_slg else None)
                items.append({
                    "name": f"{d.month}/{d.day}", "g": i, "date": d.isoformat(),
                    "avg": None if small else r3(h / ab if ab else None),
                    "obp": r3(obp), "slg": r3(slg), "ops": r3(ops),
                    "ops_plus": ops_plus, "hits": h_c, "home_runs": hr_c, "rbi": rbi_c,
                })
        else:
            lg_era = None
            if kind_code == "A":  # ERA+ 聯盟基準
                cur.execute("SELECT ip, er FROM cpbl.pitching_current WHERE year = %s AND ip IS NOT NULL", (season,))
                lr = cur.fetchall()
                lg_ip = sum(_real_ip(r[0]) for r in lr)
                lg_era = sum(r[1] or 0 for r in lr) * 9 / lg_ip if lg_ip else None
            cur.execute(
                f"""
                SELECT g.game_date,
                    p.so AS so_c, p.hits AS h_c, p.bb AS bb_c,  -- 計數型：單場值(柱狀)
                    sum(p.inning_pitched_cnt)  OVER roll AS ipc,
                    sum(p.inning_pitched_div3) OVER roll AS ip3,
                    sum(p.earned_runs)         OVER roll AS er,
                    sum(p.hits)                OVER roll AS h_r,
                    sum(p.bb)                  OVER roll AS bb_r
                FROM cpbl.pitching_gamelog p
                JOIN cpbl.games g
                  ON g.year = p.year AND g.kind_code = p.kind_code AND g.game_sno = p.game_sno
                WHERE p.pitcher_acnt = %s AND p.year = %s AND p.kind_code = %s
                WINDOW roll AS (ORDER BY g.game_date, p.game_sno
                                ROWS BETWEEN {n_roll - 1} PRECEDING AND CURRENT ROW)
                ORDER BY g.game_date, p.game_sno
                """,
                (player_id, season, kind_code),
            )
            items = []
            for i, (d, so_c, h_c, bb_c, ipc, ip3, er, h_r, bb_r) in enumerate(cur.fetchall(), 1):
                ip = (ipc or 0) + (ip3 or 0) / 3
                small = ip < 10  # 滾動局數太小(早季未滿窗)→ rate 過度波動,不輸出
                era = None if small or not ip else round((er or 0) * 9 / ip, 2)
                whip = None if small or not ip else round(((bb_r or 0) + (h_r or 0)) / ip, 2)
                era_plus = round(100 * lg_era / era) if lg_era and era and era > 0 else None
                items.append({
                    "name": f"{d.month}/{d.day}", "g": i, "date": d.isoformat(),
                    "era": era, "whip": whip, "era_plus": era_plus,
                    "so": so_c, "hits": h_c, "bb": bb_c,
                })
    return {"player_id": player_id, "role": role, "items": items, "roll": n_roll}


@app.get("/api/v1/players/{player_id}/trend-career")
def player_trend_career(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
    kind_code: str = Query("A"),
    bucket: str = Query("half", pattern="^(month|half|third|week)$"),
) -> dict:
    """生涯「時段分項」趨勢：把跨年份的同一時段合併為一點（所有 3 月上、3 月下…），
    看選手各時段強弱/是否慢熱、作為下時段參考。bucket 控制粒度：月/半月/旬/週。
    rate=該時段生涯合計率、OPS+/ERA+ 用生涯聯盟基準；計數型=生涯合計（柱狀）。樣本過小之 rate 略。"""
    r3 = lambda v: round(v, 3) if v is not None else None  # noqa: E731
    # 子月份索引 SQL（白名單，非使用者字串直插）+ 標籤
    _SUB = {"month": "0", "half": "((extract(day FROM g.game_date)::int > 15))::int",
            "third": "least((extract(day FROM g.game_date)::int - 1) / 10, 2)",
            "week": "least((extract(day FROM g.game_date)::int - 1) / 7, 4)"}
    sub_sql = _SUB[bucket]

    def _label(m: int, s: int) -> str:
        if bucket == "month":
            return f"{m}月"
        if bucket == "half":
            return f"{m}月{'下' if s else '上'}"
        if bucket == "third":
            return f"{m}月{['上旬', '中旬', '下旬'][s]}"
        return f"{m}月W{s + 1}"
    with conn() as c:
        cur = c.cursor()
        if role == "batting":
            cur.execute("SELECT sum(at_bats), sum(hits), sum(bb), sum(hbp), sum(sac_fly), sum(total_bases) "
                        "FROM cpbl.batting_gamelog WHERE kind_code = %s", (kind_code,))
            lab, lh, lbb, lhbp, lsf, ltb = (x or 0 for x in cur.fetchone())
            lden = lab + lbb + lhbp + lsf
            lg_obp = (lh + lbb + lhbp) / lden if lden else None
            lg_slg = ltb / lab if lab else None
            cur.execute(
                f"""
                SELECT extract(month FROM g.game_date)::int AS m, {sub_sql} AS sub,
                    sum(b.at_bats), sum(b.hits), sum(b.bb), sum(b.hbp), sum(b.sac_fly),
                    sum(b.total_bases), sum(b.home_runs), sum(b.rbi), count(DISTINCT b.year)
                FROM cpbl.batting_gamelog b
                JOIN cpbl.games g ON g.year = b.year AND g.kind_code = b.kind_code AND g.game_sno = b.game_sno
                WHERE b.hitter_acnt = %s AND b.kind_code = %s
                GROUP BY 1, 2 ORDER BY 1, 2
                """,
                (player_id, kind_code),
            )
            items = []
            for m, sub, ab, h, bb, hbp, sf, tb, hr, rbi, yrs in cur.fetchall():
                ab = ab or 0
                den = ab + (bb or 0) + (hbp or 0) + (sf or 0)
                small = ab < 15  # 該時段生涯樣本太小 → rate 不輸出
                obp = None if small else (((h or 0) + (bb or 0) + (hbp or 0)) / den if den else None)
                slg = None if small else ((tb or 0) / ab if ab else None)
                ops = (obp + slg) if obp is not None and slg is not None else None
                ops_plus = (round(100 * (obp / lg_obp + slg / lg_slg - 1))
                            if obp is not None and slg is not None and lg_obp and lg_slg else None)
                items.append({
                    "name": _label(m, sub), "years": yrs,
                    "avg": None if small else r3(h / ab if ab else None),
                    "obp": r3(obp), "slg": r3(slg), "ops": r3(ops), "ops_plus": ops_plus,
                    "hits": h, "home_runs": hr, "rbi": rbi,
                })
        else:
            cur.execute("SELECT sum(inning_pitched_cnt), sum(inning_pitched_div3), sum(earned_runs) "
                        "FROM cpbl.pitching_gamelog WHERE kind_code = %s", (kind_code,))
            lipc, lip3, ler = (x or 0 for x in cur.fetchone())
            lgip = lipc + lip3 / 3
            lg_era = ler * 9 / lgip if lgip else None
            cur.execute(
                f"""
                SELECT extract(month FROM g.game_date)::int AS m, {sub_sql} AS sub,
                    sum(p.inning_pitched_cnt), sum(p.inning_pitched_div3), sum(p.earned_runs),
                    sum(p.so), sum(p.hits), sum(p.bb), count(DISTINCT p.year)
                FROM cpbl.pitching_gamelog p
                JOIN cpbl.games g ON g.year = p.year AND g.kind_code = p.kind_code AND g.game_sno = p.game_sno
                WHERE p.pitcher_acnt = %s AND p.kind_code = %s
                GROUP BY 1, 2 ORDER BY 1, 2
                """,
                (player_id, kind_code),
            )
            items = []
            for m, sub, ipc, ip3, er, so, h, bb, yrs in cur.fetchall():
                ip = (ipc or 0) + (ip3 or 0) / 3
                small = ip < 8  # 該時段生涯局數太小
                era = None if small or not ip else round((er or 0) * 9 / ip, 2)
                whip = None if small or not ip else round(((bb or 0) + (h or 0)) / ip, 2)
                era_plus = round(100 * lg_era / era) if lg_era and era and era > 0 else None
                items.append({
                    "name": _label(m, sub), "years": yrs,
                    "era": era, "whip": whip, "era_plus": era_plus,
                    "so": so, "hits": h, "bb": bb,
                })
    return {"player_id": player_id, "role": role, "items": items}
