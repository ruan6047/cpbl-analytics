"""賽況：月曆、近期賽事、單場 live（逐局/逐打席/狀態板）。"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _dicts
from cpbl.db import conn
from cpbl.models import matchup, pitcher_decisions

router = APIRouter()


@router.get("/api/v1/games/calendar")
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


@router.get("/api/v1/games/recent")
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


@router.get("/api/v1/games/{game_sno}/live")
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
                    "third_umpire, left_umpire, right_umpire, weather_code, weather_desc "
                    "FROM cpbl.game_detail "
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s", (season, kind_code, game_sno))
        gd = _dicts(cur)
    # 投手角色：W/L/HLD 官方（game_result/relief_point）、SV 依規則 9.19 自 livelog 推算
    # （官方逐場無 save 旗標；2026 全季驗證與官方季累計 SV 一致率 63/64 投手）
    decisions = pitcher_decisions.game_decisions(season, kind_code, game_sno)
    return {"game": g[0] if g else None, "scoreboard": scoreboard, "livelog": livelog,
            "batting": batting, "pitching": pitching, "people": people,
            "records": records, "batter_avg": batter_avg, "detail": gd[0] if gd else None,
            "decisions": decisions,
            "has_tracking": len(tracking) > 0, "tracking": tracking}


# ---- 能力值卡（遊戲風雷達圖）：以全史生涯 rate 對全聯盟母體求百分位 [PR] ----
# 不抄任何遊戲數字；每軸 = 我們自算的客觀指標相對「所有合格生涯球員」的 percent_rank。
# 等級 S–G 純由 PR 換算，方便一眼讀懂（教育用途，呼應 /predict）。


# ---------- 逐打席勝率（WP；推算） ----------
@lru_cache(maxsize=4)
def _wp_tables(span: str, kind: str):
    """快取 run_dist + WE 求解器（表小、跨 request 重用；重建後重啟 API 生效）。"""
    from cpbl.models.winprob import _load_dist, _we_solver
    dist = _load_dist(span, kind)
    we_top, we_bot = _we_solver(dist[("1", "___", 0)], dist[("2", "___", 0)])
    return dist, we_top, we_bot


@router.get("/api/v1/games/{game_sno}/winprob")
def game_winprob(
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|C|E|D)$"),
) -> dict:
    """逐打席主隊勝率（推算）：自建 run_dist × WE 邊界 DP（span 2018-2025 一軍）。

    每打席一點（打席開始時的局面 WP）；完賽補終點 1/0/0.5。中性隊伍 + 主場優勢，
    不含先發/戰力差 → 開局 ≈ 聯盟主場基準 0.528。
    """
    from cpbl.models.winprob import wp_state
    span = "2018-2025"
    try:
        dist, we_top, we_bot = _wp_tables(span, "A")
    except RuntimeError:
        return {"items": [], "note": "win_expectancy 未建置"}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT main_event_no, inning_seq, visiting_home_type, batting_order, out_cnt, "
            "is_change_player, hitter_acnt, hitter_name, first_base, second_base, third_base, "
            "visiting_score, home_score FROM cpbl.game_livelog "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s ORDER BY main_event_no",
            (season, kind_code, game_sno))
        events = _dicts(cur)
        cur.execute("SELECT home_score, away_score FROM cpbl.games "
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                    (season, kind_code, game_sno))
        fin = cur.fetchone()
    events.sort(key=lambda r: int(r["main_event_no"]))
    items, seen = [], set()
    pv = ph = 0
    for e in events:
        pre_v, pre_h = pv, ph
        pv = e["visiting_score"] if e.get("visiting_score") is not None else pv
        ph = e["home_score"] if e.get("home_score") is not None else ph
        if e.get("is_change_player") or not e.get("hitter_acnt"):
            continue
        pa_key = (e["inning_seq"], str(e["visiting_home_type"]),
                  e.get("batting_order"), e["hitter_acnt"])
        if pa_key in seen:
            continue
        seen.add(pa_key)
        bases = (("1" if e.get("first_base") else "_")
                 + ("2" if e.get("second_base") else "_")
                 + ("3" if e.get("third_base") else "_"))
        wp = wp_state(dist, we_top, we_bot, int(e["inning_seq"]),
                      str(e["visiting_home_type"]), pre_h - pre_v,
                      bases, int(e.get("out_cnt") or 0))
        items.append({"evt": e["main_event_no"], "inning": e["inning_seq"],
                      "half": str(e["visiting_home_type"]), "hitter": e.get("hitter_name"),
                      "away": pre_v, "home": pre_h, "wp": round(wp, 4)})
    completed = bool(fin and (fin[0] or 0) + (fin[1] or 0) > 0)
    if completed and items:
        final_wp = 1.0 if fin[0] > fin[1] else (0.0 if fin[0] < fin[1] else 0.5)
        items.append({"evt": None, "inning": None, "half": None, "hitter": None,
                      "away": fin[1], "home": fin[0], "wp": final_wp})
    return {"span": span, "completed": completed, "items": items}


# ---------- 生涯里程碑（本場達成） ----------
# 生涯前值 = seasons(歷年) + gamelog(本季本場之前，依日期再 sno 排序)；跨關卡=精確判定。
# 逐場僅 2018+：更早年份回空（不猜）。僅一軍例行（生涯數據慣例）。
_B_MARKS = [("hits", "安", 500), ("home_runs", "轟", 50), ("rbi", "打點", 500),
            ("sb", "盜壘", 100)]
_MILESTONE_G = 500  # 出賽場次關卡


@lru_cache(maxsize=4)
def _season_decisions(season: int, kind_code: str) -> dict[str, list[tuple[str, int, str]]]:
    """{pitcher_acnt: [(game_date, game_sno, 'W'|'L'|'SV'|'HLD'), ...]} 全季逐場 decisions（快取，
    只在 process 內首次請求該季/kind 時算一次；SV 需逐場 livelog 重建，量體才需快取）。"""
    from collections import defaultdict
    out: dict[str, list] = defaultdict(list)
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT game_sno, game_date, home_score, away_score FROM cpbl.games "
                    "WHERE year=%s AND kind_code=%s AND home_score+away_score>0 "
                    "ORDER BY game_date, game_sno", (season, kind_code))
        games = cur.fetchall()
        for sno, gdate, hs, aws in games:
            cur.execute("SELECT * FROM cpbl.game_livelog WHERE year=%s AND kind_code=%s AND game_sno=%s",
                        (season, kind_code, sno))
            livelog = _dicts(cur)
            cur.execute("SELECT * FROM cpbl.pitching_gamelog WHERE year=%s AND kind_code=%s AND game_sno=%s",
                        (season, kind_code, sno))
            pitching = _dicts(cur)
            for acnt, d in pitcher_decisions.decide(livelog, pitching, hs, aws).items():
                out[acnt].append((str(gdate), sno, d))
    return dict(out)


@router.get("/api/v1/games/{game_sno}/milestones")
def game_milestones(
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|C|E|D)$"),
) -> dict:
    """本場達成的生涯里程碑（安×500/轟×50/打點×500/盜×100/出賽×500；投手 K×500/出賽×500/勝投×50）。"""
    if kind_code != "A" or season < 2018:
        return {"items": []}
    items: list[dict] = []
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT game_date, winning_pitcher_id FROM cpbl.games "
                    "WHERE year=%s AND kind_code='A' AND game_sno=%s", (season, game_sno))
        row = cur.fetchone()
        if not row or not row[0]:
            return {"items": []}
        gdate, win_pid = row
        # 打者：本場貢獻 + 生涯前值
        cur.execute(
            """
            WITH this AS (
              SELECT hitter_acnt pid, hitter_name name, coalesce(hits,0) hits,
                     coalesce(home_runs,0) home_runs, coalesce(rbi,0) rbi, coalesce(sb,0) sb
              FROM cpbl.batting_gamelog WHERE year=%(y)s AND kind_code='A' AND game_sno=%(sno)s
            ), hist AS (
              SELECT player_id pid, sum(coalesce(h,0)) hits, sum(coalesce(hr,0)) home_runs,
                     sum(coalesce(rbi,0)) rbi, sum(coalesce(sb,0)) sb, sum(coalesce(g,0)) g
              FROM cpbl.batting_seasons WHERE year < %(y)s GROUP BY player_id
            ), cur_season AS (
              SELECT bg.hitter_acnt pid, count(*) g, sum(coalesce(bg.hits,0)) hits,
                     sum(coalesce(bg.home_runs,0)) home_runs, sum(coalesce(bg.rbi,0)) rbi,
                     sum(coalesce(bg.sb,0)) sb
              FROM cpbl.batting_gamelog bg
              JOIN cpbl.games g ON g.year=bg.year AND g.kind_code=bg.kind_code AND g.game_sno=bg.game_sno
              WHERE bg.year=%(y)s AND bg.kind_code='A'
                AND (g.game_date < %(d)s OR (g.game_date = %(d)s AND g.game_sno < %(sno)s))
              GROUP BY bg.hitter_acnt
            )
            SELECT t.pid, t.name, t.hits, t.home_runs, t.rbi, t.sb,
                   coalesce(h.hits,0)+coalesce(cs.hits,0), coalesce(h.home_runs,0)+coalesce(cs.home_runs,0),
                   coalesce(h.rbi,0)+coalesce(cs.rbi,0), coalesce(h.sb,0)+coalesce(cs.sb,0),
                   coalesce(h.g,0)+coalesce(cs.g,0)
            FROM this t LEFT JOIN hist h ON h.pid=t.pid LEFT JOIN cur_season cs ON cs.pid=t.pid
            """,
            {"y": season, "sno": game_sno, "d": gdate})
        for _pid, name, th, thr, trbi, tsb, ph, phr, prbi, psb, pg in cur.fetchall():
            for (this_v, pre_v, label, step) in [
                    (th, ph, "安", 500), (thr, phr, "轟", 50),
                    (trbi, prbi, "打點", 500), (tsb, psb, "盜壘", 100)]:
                if this_v and pre_v == 0:
                    items.append({"player": name, "text": f"生涯首{label}"})
                elif this_v and (pre_v + this_v) // step > pre_v // step:
                    mark = ((pre_v + this_v) // step) * step
                    items.append({"player": name, "text": f"生涯第 {mark} {label}"})
            if pg == 0:
                items.append({"player": name, "text": "一軍初登場"})
            elif (pg + 1) % _MILESTONE_G == 0:
                items.append({"player": name, "text": f"生涯第 {pg + 1} 場出賽"})
        # 投手：K / 局數（取代出賽）/ 勝投 / 中繼(HLD) / 後援(SV)
        # ip 欄為棒球記法 X.1=X⅓／X.2=X⅔，非小數，逐列轉出局數再加總（直接加小數會錯進位）。
        cur.execute(
            """
            WITH this AS (
              SELECT pitcher_acnt pid, pitcher_name name, coalesce(so,0) so,
                     coalesce(inning_pitched_cnt,0)*3 + coalesce(inning_pitched_div3,0) outs
              FROM cpbl.pitching_gamelog WHERE year=%(y)s AND kind_code='A' AND game_sno=%(sno)s
            ), hist AS (
              SELECT player_id pid, sum(coalesce(so,0)) so, sum(coalesce(w,0)) w,
                     sum(coalesce(sv,0)) sv, sum(coalesce(hld,0)) hld,
                     sum(floor(coalesce(ip,0))*3 + round((coalesce(ip,0)-floor(coalesce(ip,0)))*10)) outs
              FROM cpbl.pitching_seasons WHERE year < %(y)s GROUP BY player_id
            ), cur_season AS (
              SELECT pg.pitcher_acnt pid, sum(coalesce(pg.so,0)) so,
                     sum(coalesce(pg.inning_pitched_cnt,0)*3 + coalesce(pg.inning_pitched_div3,0)) outs
              FROM cpbl.pitching_gamelog pg
              JOIN cpbl.games g ON g.year=pg.year AND g.kind_code=pg.kind_code AND g.game_sno=pg.game_sno
              WHERE pg.year=%(y)s AND pg.kind_code='A'
                AND (g.game_date < %(d)s OR (g.game_date = %(d)s AND g.game_sno < %(sno)s))
              GROUP BY pg.pitcher_acnt
            ), cur_w AS (
              SELECT winning_pitcher_id pid, count(*) w FROM cpbl.games
              WHERE year=%(y)s AND kind_code='A' AND winning_pitcher_id IS NOT NULL
                AND (game_date < %(d)s OR (game_date = %(d)s AND game_sno < %(sno)s))
              GROUP BY winning_pitcher_id
            )
            SELECT t.pid, t.name, t.so, t.outs,
                   coalesce(h.so,0)+coalesce(cs.so,0),
                   coalesce(h.w,0)+coalesce(cw.w,0),
                   coalesce(h.outs,0)+coalesce(cs.outs,0), coalesce(h.sv,0), coalesce(h.hld,0)
            FROM this t LEFT JOIN hist h ON h.pid=t.pid
            LEFT JOIN cur_season cs ON cs.pid=t.pid LEFT JOIN cur_w cw ON cw.pid=t.pid
            """,
            {"y": season, "sno": game_sno, "d": gdate})
        season_dec = _season_decisions(season, "A") if kind_code == "A" else {}
        for pid, name, tso, this_outs, pso, pw, prior_outs, hist_sv, hist_hld in cur.fetchall():
            if tso and (pso + tso) // 500 > pso // 500:
                items.append({"player": name, "text": f"生涯第 {((pso + tso) // 500) * 500} 次三振"})
            total_outs = prior_outs + this_outs
            if this_outs and total_outs // 1500 > prior_outs // 1500:   # 1500 出局＝500 局
                items.append({"player": name, "text": f"生涯第 {(total_outs // 1500) * 500} 局"})
            elif prior_outs == 0 and this_outs:
                items.append({"player": name, "text": "一軍初登板"})
            if win_pid and str(pid) == str(win_pid):
                if pw == 0:
                    items.append({"player": name, "text": "生涯首勝"})
                elif (pw + 1) % 50 == 0:
                    items.append({"player": name, "text": f"生涯第 {pw + 1} 勝"})
            # 中繼(HLD)/後援(SV) ×50：本季逐場 decisions 快取（同套邏輯已用於本場決勝標記）
            games_this_p = season_dec.get(str(pid), [])
            prior_games = [d for d in games_this_p if (d[0], d[1]) < (str(gdate), game_sno)]
            today_dec = next((d[2] for d in games_this_p
                              if d[0] == str(gdate) and d[1] == game_sno), None)
            for label, step, code, hist_v in (("中繼", 50, "HLD", hist_hld), ("後援", 50, "SV", hist_sv)):
                if today_dec != code:
                    continue
                pre_total = hist_v + sum(1 for d in prior_games if d[2] == code)
                if pre_total == 0:
                    items.append({"player": name, "text": f"生涯首次{label}"})
                elif (pre_total + 1) % step == 0:
                    items.append({"player": name, "text": f"生涯第 {pre_total + 1} 次{label}"})
    return {"items": items}
