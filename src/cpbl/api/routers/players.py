"""球員頁核心：逐年/生涯/本季成績、名冊、對戰、分項、守備、profile。"""

from __future__ import annotations

from datetime import date as _date
from typing import Any

from fastapi import APIRouter, Query

from cpbl import imports
from cpbl.api.helpers import DEFAULT_SEASON, _dicts, _real_ip, _round
from cpbl.api.rows import _ERA_SPLIT, _POS_CANON, _batting_rows, _pitching_rows
from cpbl.db import conn

router = APIRouter()


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

    # 調度豁免（ruan6047 2026-07-12）：現登錄二軍、但本季有一軍出賽且「最後一次下二軍後」
    # 二軍出賽 ≤1 場 → 視為一軍。投手/洋將常因輪值調度紙上降二軍（例：羅戈 7/8 一軍先發、
    # 7/9 降、二軍 0 出賽），分類應反映實際出賽層級而非登錄面。真降二軍者下放初期同樣
    # 0 出賽會暫顯一軍，但一在二軍出賽第 2 場即轉二軍（自然收斂，免猜天數門檻）。
    if not current_first and appeared_a and events:
        last_down = max(t for t, kc in events if kc != "01")
        cur.execute(
            "SELECT (SELECT count(DISTINCT b.game_sno) FROM cpbl.batting_gamelog b "
            "        JOIN cpbl.games g ON g.year=b.year AND g.kind_code=b.kind_code AND g.game_sno=b.game_sno "
            "        WHERE b.hitter_acnt=%(p)s AND b.year=%(y)s AND b.kind_code='D' AND g.game_date>=%(d)s) "
            "     + (SELECT count(DISTINCT pg.game_sno) FROM cpbl.pitching_gamelog pg "
            "        JOIN cpbl.games g ON g.year=pg.year AND g.kind_code=pg.kind_code AND g.game_sno=pg.game_sno "
            "        WHERE pg.pitcher_acnt=%(p)s AND pg.year=%(y)s AND pg.kind_code='D' AND g.game_date>=%(d)s)",
            {"p": player_id, "y": season, "d": last_down})
        if (cur.fetchone()[0] or 0) <= 1:
            current_first = True

    # level＝現在登錄層級（非累計天數多者）：季中升上一軍的板凳球員即為一軍
    level = "一軍" if current_first else "二軍"
    return {"level": level, "first_days": first_days, "farm_days": farm_days}
@router.get("/api/v1/players/{player_id}/batting")
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


@router.get("/api/v1/players/{player_id}/career")
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
        # 維基補充獎項：只取非中職者（舊聯盟/台灣大賽/國際賽/日韓職——官網 yearaward 沒有；
        # 中職部分官方 player_awards 較準故排除避免重複）
        cur.execute(
            "SELECT award, years, note FROM cpbl.wiki_awards "
            "WHERE player_id=%s AND award NOT LIKE '%%中華職棒%%' ORDER BY seq", (player_id,))
        wiki_awards = [{"award": aw, "years": ys or [], "note": nt}
                       for aw, ys, nt in cur.fetchall()]
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
                    "overseas": overseas, "awards": awards, "wiki_awards": wiki_awards,
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
        "overseas": overseas, "awards": awards, "wiki_awards": wiki_awards,
        "coach_tenures": coach_tenures, "exec_tenures": exec_tenures, "medals": medals,
        "milestones": {"first_hit": str(first_h) if first_h else None,
                       "first_hr": str(first_hr) if first_hr else None},
        "rank": {"hr": rk[0], "h": rk[1], "sb": rk[2]} if rk else None,
        **_pit_extra,
    }


@router.get("/api/v1/players/{player_id}/pitching")
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
@router.get("/api/v1/players/roster")
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


@router.get("/api/v1/matchups")
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


@router.get("/api/v1/players/{player_id}/traits")
def player_traits(player_id: str, season: int = Query(DEFAULT_SEASON),
                  role: str = Query("batting", pattern="^(batting|pitching)$")) -> dict:
    """選手特性（livelog 推算）：P/PA 耗球、滾飛比、方向傾向、兩好球後表現 + 聯盟均值。"""
    table = "batter_traits" if role == "batting" else "pitcher_traits"
    pa_col = "pa" if role == "batting" else "bf"
    with conn() as c:
        cur = c.cursor()
        cur.execute(  # noqa: S608 — table 白名單如上
            f"SELECT * FROM cpbl.{table} WHERE player_id=%s AND year=%s AND kind_code='A'",
            (player_id, season))
        rows = _dicts(cur)
        cur.execute(  # 聯盟均值（有效樣本：打者 100 PA / 投手 100 BF）
            f"SELECT round(avg(p_pa)::numeric, 2), "  # noqa: S608
            f"round(avg(go::numeric / nullif(fo, 0)), 2), "
            f"round(avg(100.0 * two_strike_k / nullif(two_strike_pa, 0)), 1) "
            f"FROM cpbl.{table} WHERE year=%s AND kind_code='A' AND {pa_col} >= 100",
            (season,))
        lg = cur.fetchone()
    me = rows[0] if rows else None
    if me:
        me["go_fo"] = round(me["go"] / me["fo"], 2) if me.get("fo") else None
        if me.get("two_strike_pa"):
            me["two_strike_k_pct"] = round(100 * me["two_strike_k"] / me["two_strike_pa"], 1)
    return {"season": season, "role": role, "traits": me,
            "league": {"p_pa": float(lg[0]) if lg and lg[0] is not None else None,
                       "go_fo": float(lg[1]) if lg and lg[1] is not None else None,
                       "two_strike_k_pct": float(lg[2]) if lg and lg[2] is not None else None}}


@router.get("/api/v1/players/{player_id}/vs-team")
def player_vs_team(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
    year: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|D)$"),
) -> dict:
    """選手對戰各隊成績。role=batting/pitching；kind_code=A/D（D 為重算解鎖，
    官方源無二軍對戰）。預設值＝原行為（本季 A）。"""
    table = "batting_vs_team" if role == "batting" else "pitching_vs_team"
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"SELECT * FROM cpbl.{table} WHERE acnt = %s AND year = %s AND kind_code = %s "
            "ORDER BY total_games DESC NULLS LAST",
            (player_id, year, kind_code),
        )
        return {"player_id": player_id, "role": role, "year": year,
                "kind_code": kind_code, "items": _dicts(cur)}


# 多賽別合併時要加總的計數欄位（比率欄不加總，之後重算）
_BSPLIT_SUM = ["plate_appearances", "at_bats", "hits", "rbi", "singles", "doubles", "triples",
               "home_runs", "total_bases", "sac_hit", "sac_fly", "bb", "ibb", "hbp", "so",
               "ground_outs", "fly_outs"]
_PSPLIT_SUM = ["wins", "loses", "starts", "complete_games", "shutouts", "save_ok",
               "inning_pitched_cnt", "inning_pitched_div3", "plate_appearances", "pitch_cnt",
               "strikes", "balls", "hits", "home_runs", "sac_hit", "sac_fly", "bb", "ibb", "hbp",
               "so", "wild_pitch", "balk", "runs", "earned_runs"]
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


@router.get("/api/v1/players/{player_id}/splits")
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


@router.get("/api/v1/players/{player_id}/profile")
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


@router.get("/api/v1/players/{player_id}/matchups")
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


@router.get("/api/v1/players/{player_id}/season")
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


@router.get("/api/v1/players/{player_id}/fielding")
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


# ---------- 進階指標（sabr 推算） ----------
@router.get("/api/v1/players/{player_id}/sabr")
def player_sabr(player_id: str,
                role: str = Query("batting", pattern="^(batting|pitching)$")) -> dict:
    """進階指標（livelog/RE 矩陣推算，一軍）：打者 RE24+wSB、投手 RE24、捕手 RA9+阻殺。

    RE24 2018+（rank 為該年 PA≥200 / BF≥200 合格者名次）；wSB 全史 1990+（官方 SB/CS×在地係數）。
    捕手 RA/9 = 接捕時失分×27/接捕出局數（含非自責，故非 cERA）；阻殺率 = CS/(CS+被盜)。
    """
    out: dict[str, Any] = {"player_id": player_id, "role": role}
    with conn() as c:
        cur = c.cursor()
        if role == "batting":
            cur.execute(
                "WITH q AS (SELECT year, player_id, "
                "  rank() OVER (PARTITION BY year ORDER BY re24 DESC) AS rnk, "
                "  count(*) OVER (PARTITION BY year) AS n "
                "  FROM cpbl.batter_re24 WHERE kind_code='A' AND pa >= 200) "
                "SELECT b.year, b.pa, b.re24, q.rnk, q.n, w.sb, w.cs, w.wsb "
                "FROM cpbl.batter_re24 b "
                "LEFT JOIN q ON q.year=b.year AND q.player_id=b.player_id "
                "LEFT JOIN cpbl.batter_wsb w ON w.year=b.year AND w.player_id=b.player_id "
                "WHERE b.kind_code='A' AND b.player_id=%s "
                "UNION ALL "
                "SELECT w.year, NULL, NULL, NULL, NULL, w.sb, w.cs, w.wsb "
                "FROM cpbl.batter_wsb w WHERE w.player_id=%s AND w.year NOT IN "
                "  (SELECT year FROM cpbl.batter_re24 WHERE kind_code='A' AND player_id=%s) "
                "ORDER BY 1 DESC",
                (player_id, player_id, player_id))
            out["years"] = _dicts(cur)
            cur.execute(
                "SELECT cr.year, cr.runs, cr.games, fi.outs, "
                "  round(cr.runs*27.0/nullif(fi.outs,0), 2) AS ra9, f.cs, f.sba "
                "FROM cpbl.catcher_runs cr "
                "JOIN cpbl.fielding_innings fi ON fi.year=cr.year AND fi.kind_code=cr.kind_code "
                "  AND fi.player_id=cr.player_id AND fi.pos='C' "
                "LEFT JOIN cpbl.fielding_current f ON f.year=cr.year AND f.kind_code='A' "
                "  AND f.player_id=cr.player_id AND f.pos='捕手' "
                "WHERE cr.kind_code='A' AND cr.player_id=%s AND fi.outs >= 150 "
                "ORDER BY cr.year DESC", (player_id,))
            catcher = _dicts(cur)
            for r in catcher:  # 阻殺率：CS/(CS+被盜)；官方欄缺值年不算
                att = (r.get("cs") or 0) + (r.get("sba") or 0)
                r["cs_pct"] = round(100.0 * r["cs"] / att, 1) if r.get("cs") is not None and att else None
            if catcher:
                out["catcher"] = catcher
        else:
            cur.execute(
                "WITH q AS (SELECT year, player_id, "
                "  rank() OVER (PARTITION BY year ORDER BY re24 ASC) AS rnk, "
                "  count(*) OVER (PARTITION BY year) AS n "
                "  FROM cpbl.pitcher_re24 WHERE kind_code='A' AND bf >= 200) "
                "SELECT r.year, r.bf, r.re24, q.rnk, q.n FROM cpbl.pitcher_re24 r "
                "LEFT JOIN q ON q.year=r.year AND q.player_id=r.player_id "
                "WHERE r.kind_code='A' AND r.player_id=%s ORDER BY r.year DESC",
                (player_id,))
            out["years"] = _dicts(cur)
    return out
