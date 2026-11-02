"""當季球隊累計統計 `team_stats`：戰績榜（routers/standings）與月曆（routers/games）共用。

原本是舊互動探索器「單場對戰卡」模組（對戰卡、預設權重訓練、任選兩隊模擬）。探索器前端於
DEP-PREDICT-LEGACY1 下線、後端五支端點於 #405 移除後，只剩 `team_stats` 仍被活碼使用，其餘已刪
（原碼對照 `git show 0ffd401 -- src/cpbl/models/matchup.py`）。得失分口徑（kind='A'、score>0、
和局計入分母、無 date 過濾）是戰績榜 `_team_scoped_metrics` 的對帳基準，⛔ 不要順手改。
"""

from __future__ import annotations

from datetime import date

from cpbl.completion import completed_games_sql_with_evidence
from cpbl.db import conn

# 完成場判準（證據感知）：0:0 真和局需外部完賽證據才算完成場（DATA-TIE-REMEDY1）。
_DONE = completed_games_sql_with_evidence("games")


# ---------- 球隊當季到當日統計 ----------

def _prior_winpct(season: int) -> dict[str, float]:
    """{team_code: 上一季(一軍例行賽)最終勝率}；季初冷啟動的戰力先驗。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT team, sum(w)::float / NULLIF(sum(w + l), 0) FROM (
                SELECT home_team_code AS team,
                       count(*) FILTER (WHERE home_score > away_score) w,
                       count(*) FILTER (WHERE home_score < away_score) l
                FROM cpbl.games WHERE kind_code='A' AND year=%s AND {_DONE}
                GROUP BY home_team_code
                UNION ALL
                SELECT away_team_code,
                       count(*) FILTER (WHERE away_score > home_score),
                       count(*) FILTER (WHERE away_score < home_score)
                FROM cpbl.games WHERE kind_code='A' AND year=%s AND {_DONE}
                GROUP BY away_team_code
            ) t GROUP BY team
            """,
            (season - 1, season - 1),
        )
        return {code: float(wp) for code, wp in cur.fetchall() if wp is not None}


def _prior_team(season: int) -> tuple[dict[str, dict], dict]:
    """({team_code: 上季團隊 ops/slg/era/whip}, 聯盟均值)。缺資料的隊由呼叫端用聯盟均值墊。"""
    bat: dict[str, dict] = {}
    pit: dict[str, dict] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT team_id, sum(ab), sum(h), sum(tb), sum(bb), sum(hbp), sum(sf) "
                    "FROM cpbl.batting_seasons WHERE year=%s GROUP BY team_id", (season - 1,))
        for t, ab, h, tb, bb, hbp, sf in cur.fetchall():
            ab = ab or 0
            if ab <= 0:
                continue
            bb, hbp, sf, tb, h = bb or 0, hbp or 0, sf or 0, tb or 0, h or 0
            den = ab + bb + hbp + sf
            slg = tb / ab
            bat[t[:3]] = {"prior_ops": float(((h + bb + hbp) / den if den else 0) + slg),
                          "prior_slg": float(slg)}
        cur.execute("SELECT team_id, sum(floor(ip)+(ip-floor(ip))*10/3.0), sum(er), sum(h), sum(bb) "
                    "FROM cpbl.pitching_seasons WHERE year=%s GROUP BY team_id", (season - 1,))
        for t, ip, er, h, bb in cur.fetchall():
            if not ip or ip <= 0:
                continue
            pit[t[:3]] = {"prior_era": float((er or 0) * 9 / ip),
                          "prior_whip": float(((h or 0) + (bb or 0)) / ip)}

    def _avg(d: dict, k: str) -> float:
        vs = [v[k] for v in d.values() if k in v]
        return sum(vs) / len(vs) if vs else 0.0
    la = {"prior_ops": _avg(bat, "prior_ops"), "prior_slg": _avg(bat, "prior_slg"),
          "prior_era": _avg(pit, "prior_era"), "prior_whip": _avg(pit, "prior_whip")}
    out = {t: {**la, **bat.get(t, {}), **pit.get(t, {})} for t in set(bat) | set(pit)}
    return out, la


def team_stats(season: int) -> dict[str, dict]:
    """回傳 {team_code: {name, w, l, win_pct, rs_pg, ra_pg, form, prior_wp, rest_days,
    prior_ops/slg/era/whip}}（當季完成場次累計 + 上季團隊打擊/投手先驗）。"""
    prior = _prior_winpct(season)
    prior_tm, prior_la = _prior_team(season)
    # 當季團隊打擊（到此）：用 team_current 的本季彙總 bat_ops/bat_avg。
    now_tm: dict[str, dict] = {}
    with conn() as c:
        for code, ops, avg in c.execute(
            "SELECT team_code, bat_ops, bat_avg FROM cpbl.team_current WHERE year=%s", (season,)).fetchall():
            now_tm[code] = {"now_ops": float(ops) if ops is not None else 0.0,
                            "now_avg": float(avg) if avg is not None else 0.0}
    now_la = {"now_ops": (sum(v["now_ops"] for v in now_tm.values()) / len(now_tm)) if now_tm else 0.0,
              "now_avg": (sum(v["now_avg"] for v in now_tm.values()) / len(now_tm)) if now_tm else 0.0}
    # 當季壘間/守備細項累計（per-game 在輸出時除以場數）。
    extra: dict[str, dict] = {}

    def _bump(code, key, val):
        extra.setdefault(code, {"sb": 0, "cs": 0, "wp": 0, "err": 0})[key] = val or 0
    with conn() as c:
        cur = c.cursor()
        for code, sb, cs in cur.execute("SELECT team_code, sum(sb), sum(cs) FROM cpbl.batting_current "
                                        "WHERE year=%s GROUP BY team_code", (season,)).fetchall():
            _bump(code, "sb", sb); _bump(code, "cs", cs)
        for code, wp in cur.execute("SELECT team_code, sum(wp) FROM cpbl.pitching_current "
                                    "WHERE year=%s GROUP BY team_code", (season,)).fetchall():
            _bump(code, "wp", wp)
        for code, e in cur.execute("SELECT team_code, sum(e) FROM cpbl.fielding_current "
                                   "WHERE year=%s GROUP BY team_code", (season,)).fetchall():
            _bump(code, "err", e)
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT game_date, home_team_code, home_team_name, away_team_code, away_team_name,
                   home_score, away_score
            FROM cpbl.games
            WHERE year = %s AND kind_code = 'A' AND {_DONE}
            ORDER BY game_date, game_sno
            """,
            (season,),
        )
        rows = cur.fetchall()

    st: dict[str, dict] = {}

    def ensure(code, name):
        if code not in st:
            st[code] = {"name": name, "w": 0, "l": 0, "rf": 0, "ra": 0, "g": 0, "last10": [], "last_date": None}
        elif name:
            st[code]["name"] = name

    for d, hc, hn, ac, an, hs, as_ in rows:
        ensure(hc, hn); ensure(ac, an)
        st[hc]["rf"] += hs; st[hc]["ra"] += as_; st[hc]["g"] += 1; st[hc]["last_date"] = d
        st[ac]["rf"] += as_; st[ac]["ra"] += hs; st[ac]["g"] += 1; st[ac]["last_date"] = d
        if hs > as_:
            st[hc]["w"] += 1; st[ac]["l"] += 1
            st[hc]["last10"].append(1); st[ac]["last10"].append(0)
        elif hs < as_:
            st[hc]["l"] += 1; st[ac]["w"] += 1
            st[hc]["last10"].append(0); st[ac]["last10"].append(1)

    today = date.today()
    out: dict[str, dict] = {}
    for code, s in st.items():
        gp = s["w"] + s["l"]
        last10 = s["last10"][-10:]
        rest = min((today - s["last_date"]).days, 7) if s["last_date"] else 0.0
        ec = extra.get(code, {"sb": 0, "cs": 0, "wp": 0, "err": 0})
        gd = s["g"] or 1
        out[code] = {
            "name": s["name"], "w": s["w"], "l": s["l"], "g": s["g"],
            "win_pct": s["w"] / gp if gp else 0.5,
            "prior_wp": prior.get(code, 0.5),
            "rest_days": float(rest),
            "rs_pg": s["rf"] / s["g"] if s["g"] else 0.0,
            "ra_pg": s["ra"] / s["g"] if s["g"] else 0.0,
            "form": sum(last10) / len(last10) if last10 else 0.5,
            "last10": f"{sum(last10)}-{len(last10) - sum(last10)}",
            **prior_tm.get(code[:3], prior_la),
            **now_tm.get(code, now_la),
            "now_sb": ((ec["sb"] - ec["cs"]) / gd), "now_wp": (ec["wp"] / gd), "now_err": (ec["err"] / gd),
        }
    return out
