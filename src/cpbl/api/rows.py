"""跨路由共用的季成績列查詢：打者/投手原始計數、主守位、團隊進階。"""

from __future__ import annotations

from cpbl.api.helpers import DEFAULT_SEASON, _ip_real
from cpbl.db import conn

# 單一代碼內的改名（games 隊名已正規化、無法區分，故權威定義年代）。
# players 生涯效力區段與 teams 隊史沿革共用。
_ERA_SPLIT = {
    "AJK011": [("La New熊", 2004, 2010), ("Lamigo桃猿", 2011, 2019)],
}

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
