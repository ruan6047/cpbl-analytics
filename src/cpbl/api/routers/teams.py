"""球隊/球團：隊史沿革、球團年表、球員名單、球場、特殊戰績。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _dicts
from cpbl.api.rows import _ERA_SPLIT
from cpbl.db import conn
from cpbl.franchises import FRANCHISE_MAP as _FRANCHISE
from cpbl.franchises import franchise_of as _franchise_of
from cpbl.models import special_records

router = APIRouter()


@router.get("/api/v1/teams")
def teams_dim(active: bool = Query(True)) -> dict:
    """球隊維度（canonical）：代碼/簡稱/全名/隊色/字母。供前端取代硬編 team meta。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT team_code, short, full_name, nickname, color, letter, league, active "
            "FROM cpbl.team_dim" + (" WHERE active=true" if active else "") + " ORDER BY team_code"
        )
        return {"items": _dicts(cur)}


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


# 現役 franchise → CPBL 前的前身（台灣大聯盟 TML 隊伍無 CPBL 資料，使用者定調放棄、不列）
_ORIGINS: dict[str, str] = {}


@router.get("/api/v1/teams/{code}/eras")
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


@router.get("/api/v1/franchises")
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


@router.get("/api/v1/teams/{code}/players")
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


@router.get("/api/v1/venues")
def venues_dim(season: int = Query(DEFAULT_SEASON)) -> dict:
    """球場維度：場地材質/室內/城市/容量 + 官網規格（座席/外野距離呎/大螢幕/地址）
    + 本季一軍使用統計（場次/場均觀眾/主隊）與歷年首末使用年。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT v.venue, v.full_name, v.turf, v.indoor, v.city, v.capacity,
                   v.infield_seats, v.outfield_seats, v.lf_dist, v.cf_dist, v.rf_dist,
                   v.big_screen, v.address,
                   s.games_played, s.avg_attendance, s.home_teams,
                   h.first_year, h.last_year
            FROM cpbl.venue_dim v
            LEFT JOIN (
                SELECT g.venue, count(*) AS games_played,
                       round(avg(d.attendance)) AS avg_attendance,
                       string_agg(DISTINCT g.home_team_name, '、') AS home_teams
                FROM cpbl.games g
                LEFT JOIN cpbl.game_detail d USING (year, kind_code, game_sno)
                WHERE g.year = %s AND g.kind_code = 'A'
                  AND g.home_score + g.away_score > 0
                GROUP BY g.venue
            ) s ON s.venue = v.venue
            LEFT JOIN (
                SELECT venue, min(year) AS first_year, max(year) AS last_year
                FROM cpbl.games WHERE kind_code = 'A' GROUP BY venue
            ) h ON h.venue = v.venue
            ORDER BY s.games_played DESC NULLS LAST, v.capacity DESC NULLS LAST
            """,
            (season,),
        )
        return {"season": season, "items": _dicts(cur)}


@router.get("/api/v1/special-records")
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


@router.get("/api/v1/teams/{code}/der")
def team_der_endpoint(code: str) -> dict:
    """球隊守備效率 DER（推算=零；純官方投球總計算術）逐年 + 年度名次/聯盟均值。

    DER = 1 − (H−HR)/(BF−BB−HBP−SO−HR)。franchise 含改名/轉賣前身（隊碼取前 3 碼對齊
    opendata team_id 空間）。
    """
    fc = _franchise_of(code)
    members = {c for c in (set(_FRANCHISE) | set(_FRANCHISE.values()) | {fc})
               if _franchise_of(c) == fc} | {fc}
    prefixes = sorted({m[:3] for m in members})
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "WITH r AS (SELECT year, team_id, der, "
            "  rank() OVER (PARTITION BY year ORDER BY der DESC) AS rnk, "
            "  count(*) OVER (PARTITION BY year) AS n, "
            "  round(avg(der) OVER (PARTITION BY year), 4) AS lg_der "
            "  FROM cpbl.team_der) "
            "SELECT year, team_id, der, rnk, n, lg_der FROM r "
            "WHERE team_id = ANY(%s) ORDER BY year DESC",
            (prefixes,))
        items = _dicts(cur)
    return {"team": code, "franchise": fc, "items": items}
