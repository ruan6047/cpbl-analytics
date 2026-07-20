"""賽況：月曆、近期賽事、單場 live（逐局/逐打席/狀態板）。"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _batted_result, _dicts, kinds_of
from cpbl.db import conn
from cpbl.models import matchup, pitcher_decisions

router = APIRouter()


def _official_status(schedule_rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    """以官網已觀測 raw vocabulary 判定；未證實的值一律 unknown。"""
    if not schedule_rows:
        return "unknown", None
    active = [row for row in schedule_rows if row.get("raw_present_status") == 1]
    pool = active or schedule_rows
    selected = max(
        pool,
        key=lambda row: (
            row.get("raw_game_date") or date.min,
            row.get("last_seen_at") or row.get("fetched_at"),
        ),
    )
    present = selected.get("raw_present_status")
    result = str(selected.get("raw_game_result") or "")
    if present == 1 and result == "0":
        return "final", selected
    if present == 1 and result == "":
        return "scheduled", selected
    if present == 0 and result == "1":
        return "postponed", selected
    return "unknown", selected


def _source_view(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "outcome": "unknown", "row_count": 0, "error_code": None,
            "fetched_at": None, "last_seen_at": None,
        }
    return {
        "outcome": row.get("outcome"),
        "row_count": row.get("row_count", 0),
        "error_code": row.get("error_code"),
        "fetched_at": row.get("fetched_at"),
        "last_seen_at": row.get("last_seen_at"),
    }


def _build_game_status(
    schedule_rows: list[dict[str, Any]],
    source_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    official, selected = _official_status(schedule_rows)
    scoreboard = source_rows.get("scoreboard")
    livelog = source_rows.get("livelog")
    advanced = source_rows.get("advanced")

    if official in {"scheduled", "postponed", "cancelled"}:
        play_by_play = "not_applicable"
    elif livelog and livelog.get("outcome") == "available":
        play_by_play = "available"
    elif livelog and livelog.get("outcome") == "error":
        play_by_play = "source_error"
    elif official == "final" and (
        livelog is None or (scoreboard and scoreboard.get("outcome") == "available")
    ):
        play_by_play = "pending_refresh"
    else:
        play_by_play = "source_missing"

    advanced_detail = (advanced or {}).get("detail") or {}
    if advanced and advanced.get("outcome") == "error":
        advanced_status = "source_error"
    elif advanced and advanced.get("outcome") == "available" and advanced_detail.get(
        "game_level_complete"
    ) is True:
        advanced_status = "available"
    elif official == "final" and advanced and advanced.get("outcome") == "missing":
        advanced_status = "pending"
    else:
        advanced_status = "unknown"

    source_times = {
        source: _source_view(source_rows.get(source))
        for source in ("schedule", "scoreboard", "livelog", "advanced")
    }
    observed = [
        row.get("last_seen_at") or row.get("fetched_at")
        for row in [*schedule_rows, *source_rows.values()]
        if row.get("last_seen_at") or row.get("fetched_at")
    ]
    raw = None if selected is None else {
        "present_status": selected.get("raw_present_status"),
        "game_result": selected.get("raw_game_result"),
        "game_date": selected.get("raw_game_date"),
        "pre_exe_date": selected.get("raw_pre_exe_date"),
    }
    return {
        "official_game_status": {
            "status": official,
            "observed_at": None if selected is None else selected.get("last_seen_at"),
            "raw": raw,
        },
        "play_by_play_availability": {
            "status": play_by_play,
            "observed_at": None if livelog is None else livelog.get("last_seen_at"),
        },
        "advanced_freshness": {
            "status": advanced_status,
            "as_of": None if advanced is None else advanced.get("last_seen_at"),
        },
        "source_times": source_times,
        "refreshed_at": max(observed) if observed else None,
        "external_owners": {
            "tracking_availability": "GAME-RECAP-PA1",
            "wp_availability": "GAME-RECAP-WP-API1",
        },
    }


@router.get("/api/v1/games/{game_sno}/status")
def game_status(
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|C|E|D)$"),
) -> dict:
    """單場官方 raw 狀態與各來源 freshness；證據不足時 fail closed。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT raw_present_status, raw_game_result, raw_game_date, raw_pre_exe_date,
                   fetched_at, last_seen_at
            FROM cpbl.game_schedule_status_revisions
            WHERE year=%s AND kind_code=%s AND game_sno=%s
            ORDER BY last_seen_at DESC, fetched_at DESC, id DESC
            """,
            (season, kind_code, game_sno),
        )
        schedule_rows = _dicts(cur)
        cur.execute(
            """
            SELECT DISTINCT ON (source)
                   source, outcome, row_count, error_code, detail, fetched_at, last_seen_at
            FROM cpbl.game_source_revisions
            WHERE year=%s AND kind_code=%s AND game_sno=%s
            ORDER BY source, last_seen_at DESC, fetched_at DESC, id DESC
            """,
            (season, kind_code, game_sno),
        )
        source_rows = {row["source"]: row for row in _dicts(cur)}
    return {
        "season": season,
        "kind_code": kind_code,
        "game_sno": game_sno,
        **_build_game_status(schedule_rows, source_rows),
    }


@router.get("/api/v1/games/calendar")
def games_calendar(
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A"),
) -> dict:
    """整季所有場次（已完成 + 未開打，含季後賽）供月曆呈現。每筆帶比分/狀態/勝敗投/先發/
    球場/觀眾/時長/延賽備註。completed 由 home_score+away_score>0 判定。"""
    kinds = kinds_of(kind_code)
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
            WHERE g.year = %s AND g.kind_code = ANY(%s)
            ORDER BY g.game_date ASC, g.kind_code ASC, g.game_sno ASC
            """,
            (season, kinds),
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
                   COALESCE(pitch_type_pred_v2, pitch_type_pred) AS pitch_type_pred, tagged_pitch_type, rel_speed, plate_loc_side, plate_loc_height, pitch_call
            FROM cpbl.pitch_tracking
            WHERE year=%s AND kind_code=%s AND game_sno=%s
            ORDER BY pitcher_acnt, pitch_cnt
            """,
            (season, kind_code, game_sno),
        )
        tracking = _dicts(cur)
        # 擊球落點（分析 tab spray chart）：InPlay 且有方向/距離；result 由 content 分類（單一事實來源）
        spray: list[dict] = []
        if tracking:
            cur.execute(
                """
                SELECT hitter_acnt, hit_direction, hit_distance, hit_exit_speed, hit_launch_angle, content
                FROM cpbl.pitch_tracking
                WHERE year=%s AND kind_code=%s AND game_sno=%s
                  AND pitch_call='InPlay' AND hit_distance IS NOT NULL AND hit_direction IS NOT NULL
                """,
                (season, kind_code, game_sno),
            )
            spray = [{"hitter_acnt": ha, "dir": float(d), "dist": float(dist),
                      "ev": float(ev) if ev is not None else None,
                      "la": float(la) if la is not None else None,
                      "result": _batted_result(ct)}
                     for ha, d, dist, ev, la, ct in cur.fetchall()]
        cur.execute("SELECT attendance, game_time, head_umpire, first_umpire, second_umpire, "
                    "third_umpire, left_umpire, right_umpire, weather_code, weather_desc "
                    "FROM cpbl.game_detail "
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s", (season, kind_code, game_sno))
        gd = _dicts(cur)
    # 投手角色：W/L/HLD 官方（game_result/relief_point）、SV 依規則 9.19 自 livelog 推算
    # （官方逐場無 save 旗標；2026 全季驗證與官方季累計 SV 一致率 63/64 投手）
    decisions = pitcher_decisions.game_decisions(season, kind_code, game_sno)
    decision_counts = None
    if g and kind_code == "A":
        gg = g[0]
        hold_acnts = [a for a, d in decisions.items() if d == "HLD"]
        decision_counts = _decision_counts(
            season, game_sno, gg.get("game_date"),
            gg.get("winning_pitcher_id"), gg.get("losing_pitcher_id"),
            gg.get("closer_id"), gg.get("mvp_id"), hold_acnts)
    return {"game": g[0] if g else None, "scoreboard": scoreboard, "livelog": livelog,
            "batting": batting, "pitching": pitching, "people": people,
            "records": records, "batter_avg": batter_avg, "detail": gd[0] if gd else None,
            "decisions": decisions, "decision_counts": decision_counts,
            "has_tracking": len(tracking) > 0, "tracking": tracking, "spray": spray}


def _decision_counts(season: int, game_sno: int, gdate,
                     win_pid, lose_pid, closer_pid, mvp_pid,
                     hold_acnts: list[str]) -> dict | None:
    """決勝資訊的本季累計次數（box score 慣例：含本場、(game_date,game_sno) ≤ 本場，leakage-safe）。
    勝/敗/救援/MVP 直接數 games 表對應 id 欄（closer_id 唯救援場才落庫，與逐場 SV 判定一致）；
    中繼無 game_result 旗標，改數 pitching_gamelog.relief_point>0（中繼點）。僅 kind A 有意義。"""
    if not gdate:
        return None
    p = {"y": season, "sno": game_sno, "d": gdate}
    with conn() as c:
        cur = c.cursor()

        def _games_cnt(sql: str, pid) -> int | None:
            if not pid:
                return None
            cur.execute(sql, {**p, "pid": pid})
            return cur.fetchone()[0]

        _le = "(game_date < %(d)s OR (game_date = %(d)s AND game_sno <= %(sno)s))"
        base = "SELECT count(*) FROM cpbl.games WHERE year=%(y)s AND kind_code='A' AND "
        win = _games_cnt(base + f"winning_pitcher_id=%(pid)s AND {_le}", win_pid)
        loss = _games_cnt(base + f"losing_pitcher_id=%(pid)s AND {_le}", lose_pid)
        save = _games_cnt(base + f"closer_id=%(pid)s AND {_le}", closer_pid)
        mvp = _games_cnt(base + f"mvp_id=%(pid)s AND {_le}", mvp_pid)
        holds: dict[str, int] = {}
        for acnt in hold_acnts:
            cur.execute(
                "SELECT count(*) FROM cpbl.pitching_gamelog pg "
                "JOIN cpbl.games g ON g.year=pg.year AND g.kind_code=pg.kind_code "
                "AND g.game_sno=pg.game_sno "
                "WHERE pg.year=%(y)s AND pg.kind_code='A' AND pg.pitcher_acnt=%(a)s "
                "AND coalesce(pg.relief_point,0)>0 "
                "AND (g.game_date < %(d)s OR (g.game_date = %(d)s AND g.game_sno <= %(sno)s))",
                {**p, "a": acnt})
            holds[acnt] = cur.fetchone()[0]
    return {"win": win, "loss": loss, "save": save, "mvp": mvp, "hold": holds}


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


# ── 中職史上紀錄（生涯累計型）偵測 ──
# 只做累計型（安/轟/打點/盜壘、三振/勝/救援/中繼）：seasons 表自 1990（聯盟元年）全史覆蓋，
# 判定可精確。單場型紀錄（單場最多安等）不做——gamelog 僅 2018+，看不到早年，無法誠實宣稱。
def _top2(totals: dict[str, int]) -> tuple[str | None, int, int]:
    """(最高者pid, 最高值, 次高值)。並列最高時次高=同值 → 超越共同保持人仍判「打破」。"""
    top_pid, top_v, second_v = None, 0, 0
    for pid, v in totals.items():
        if v > top_v:
            top_pid, top_v, second_v = pid, v, top_v
        elif v > second_v:
            second_v = v
    return top_pid, top_v, second_v


def _other_max(t2: tuple[str | None, int, int], pid) -> int:
    """排除自己後的史上最高值（自己是保持人時取次高）。"""
    top_pid, top_v, second_v = t2
    return second_v if str(top_pid) == str(pid) else top_v


def _record_text(pre: int, this: int, other_max: int, label: str, unit: str) -> str | None:
    """該場開打前 pre、本場貢獻 this、他人最高 other_max → 打破/追平/刷新 文案（無則 None）。"""
    if not this:
        return None
    post = pre + this
    if post < other_max:
        return None
    if pre > other_max:          # 已是唯一保持人：每一次都在改寫自己的紀錄
        return f"刷新中職{label}紀錄（第 {post} {unit}）"
    if post == other_max:
        return f"追平中職{label}紀錄（{post} {unit}）"
    return f"打破中職{label}紀錄（第 {post} {unit}）"


@router.get("/api/v1/games/{game_sno}/milestones")
def game_milestones(
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|C|E|D)$"),
) -> dict:
    """本場達成的生涯里程碑（安×500/轟×50/打點×500/盜×100/出賽×500；投手 K×500/出賽×500/勝投×50）
    ＋中職史上紀錄（生涯累計 8 項的打破/追平/刷新，置頂；單場型紀錄因 gamelog 僅 2018+ 不做）。"""
    if kind_code != "A" or season < 2018:
        return {"items": []}
    items: list[dict] = []
    rec_items: list[dict] = []   # 中職史上紀錄（打破/追平/刷新），排序置頂
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
        bat_rows = cur.fetchall()
        # 全聯盟打者生涯累計（截至該場開打前）→ 各項 top2，供史上紀錄判定
        cur.execute(
            """
            WITH hist AS (
              SELECT player_id pid, sum(coalesce(h,0)) h, sum(coalesce(hr,0)) hr,
                     sum(coalesce(rbi,0)) rbi, sum(coalesce(sb,0)) sb
              FROM cpbl.batting_seasons WHERE year < %(y)s GROUP BY player_id
            ), cur_s AS (
              SELECT bg.hitter_acnt pid, sum(coalesce(bg.hits,0)) h,
                     sum(coalesce(bg.home_runs,0)) hr, sum(coalesce(bg.rbi,0)) rbi,
                     sum(coalesce(bg.sb,0)) sb
              FROM cpbl.batting_gamelog bg
              JOIN cpbl.games g ON g.year=bg.year AND g.kind_code=bg.kind_code AND g.game_sno=bg.game_sno
              WHERE bg.year=%(y)s AND bg.kind_code='A'
                AND (g.game_date < %(d)s OR (g.game_date = %(d)s AND g.game_sno < %(sno)s))
              GROUP BY bg.hitter_acnt
            )
            SELECT coalesce(h.pid, c.pid),
                   coalesce(h.h,0)+coalesce(c.h,0), coalesce(h.hr,0)+coalesce(c.hr,0),
                   coalesce(h.rbi,0)+coalesce(c.rbi,0), coalesce(h.sb,0)+coalesce(c.sb,0)
            FROM hist h FULL OUTER JOIN cur_s c ON c.pid = h.pid
            """,
            {"y": season, "sno": game_sno, "d": gdate})
        bat_all = cur.fetchall()
        bat_top2 = [_top2({str(r[0]): int(r[i]) for r in bat_all}) for i in (1, 2, 3, 4)]
        for _pid, name, th, thr, trbi, tsb, ph, phr, prbi, psb, pg in bat_rows:
            for j, (this_v, pre_v, label, step, rlabel, unit) in enumerate([
                    (th, ph, "安", 500, "安打", "安"), (thr, phr, "轟", 50, "全壘打", "轟"),
                    (trbi, prbi, "打點", 500, "打點", "打點"), (tsb, psb, "盜壘", 100, "盜壘", "盜壘")]):
                rec = _record_text(pre_v, this_v, _other_max(bat_top2[j], _pid), rlabel, unit)
                if rec:
                    rec_items.append({"player": name, "text": rec})
                    continue   # 紀錄文案已含累計數字，同項整數關卡不重複標
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
        pit_rows = cur.fetchall()
        season_dec = _season_decisions(season, "A") if kind_code == "A" else {}
        # 全聯盟投手生涯累計（截至該場開打前）→ 各項 top2，供史上紀錄判定。
        # SV/HLD 本季增量與里程碑同源（season_dec 重建 / relief_point），與 hist 欄位口徑一致。
        pp = {"y": season, "sno": game_sno, "d": gdate}
        cur.execute(
            "SELECT player_id, sum(coalesce(so,0)), sum(coalesce(w,0)), "
            "sum(coalesce(sv,0)), sum(coalesce(hld,0)) "
            "FROM cpbl.pitching_seasons WHERE year < %(y)s GROUP BY player_id", pp)
        pit_hist = {str(r[0]): (int(r[1]), int(r[2]), int(r[3]), int(r[4])) for r in cur.fetchall()}
        cur.execute(
            "SELECT pg.pitcher_acnt, sum(coalesce(pg.so,0)) FROM cpbl.pitching_gamelog pg "
            "JOIN cpbl.games g ON g.year=pg.year AND g.kind_code=pg.kind_code AND g.game_sno=pg.game_sno "
            "WHERE pg.year=%(y)s AND pg.kind_code='A' "
            "AND (g.game_date < %(d)s OR (g.game_date = %(d)s AND g.game_sno < %(sno)s)) "
            "GROUP BY pg.pitcher_acnt", pp)
        cur_so = {str(r[0]): int(r[1]) for r in cur.fetchall()}
        cur.execute(
            "SELECT winning_pitcher_id, count(*) FROM cpbl.games "
            "WHERE year=%(y)s AND kind_code='A' AND winning_pitcher_id IS NOT NULL "
            "AND (game_date < %(d)s OR (game_date = %(d)s AND game_sno < %(sno)s)) "
            "GROUP BY winning_pitcher_id", pp)
        cur_w = {str(r[0]): int(r[1]) for r in cur.fetchall()}

        def _dec_prior(acnt: str, code: str) -> int:
            return sum(1 for d in season_dec.get(acnt, [])
                       if d[2] == code and (d[0], d[1]) < (str(gdate), game_sno))

        pit_pids = set(pit_hist) | set(cur_so) | set(cur_w) | set(season_dec)
        tot: dict[str, dict[str, int]] = {"so": {}, "w": {}, "sv": {}, "hld": {}}
        for pid2 in pit_pids:
            h4 = pit_hist.get(pid2, (0, 0, 0, 0))
            tot["so"][pid2] = h4[0] + cur_so.get(pid2, 0)
            tot["w"][pid2] = h4[1] + cur_w.get(pid2, 0)
            tot["sv"][pid2] = h4[2] + _dec_prior(pid2, "SV")
            tot["hld"][pid2] = h4[3] + _dec_prior(pid2, "HLD")
        pit_top2 = {k: _top2(v) for k, v in tot.items()}

        for pid, name, tso, this_outs, pso, pw, prior_outs, hist_sv, hist_hld in pit_rows:
            rec = _record_text(pso, tso, _other_max(pit_top2["so"], pid), "三振", "次三振")
            if rec:
                rec_items.append({"player": name, "text": rec})
            elif tso and (pso + tso) // 500 > pso // 500:
                items.append({"player": name, "text": f"生涯第 {((pso + tso) // 500) * 500} 次三振"})
            total_outs = prior_outs + this_outs
            if this_outs and total_outs // 1500 > prior_outs // 1500:   # 1500 出局＝500 局
                items.append({"player": name, "text": f"生涯第 {(total_outs // 1500) * 500} 局"})
            elif prior_outs == 0 and this_outs:
                items.append({"player": name, "text": "一軍初登板"})
            if win_pid and str(pid) == str(win_pid):
                rec = _record_text(pw, 1, _other_max(pit_top2["w"], pid), "勝投", "勝")
                if rec:
                    rec_items.append({"player": name, "text": rec})
                elif pw == 0:
                    items.append({"player": name, "text": "生涯首勝"})
                elif (pw + 1) % 50 == 0:
                    items.append({"player": name, "text": f"生涯第 {pw + 1} 勝"})
            # 中繼(HLD)/後援(SV) ×50：本季逐場 decisions 快取（同套邏輯已用於本場決勝標記）
            games_this_p = season_dec.get(str(pid), [])
            prior_games = [d for d in games_this_p if (d[0], d[1]) < (str(gdate), game_sno)]
            today_dec = next((d[2] for d in games_this_p
                              if d[0] == str(gdate) and d[1] == game_sno), None)
            for label, step, code, hist_v, rkey, rlabel, runit in (
                    ("中繼", 50, "HLD", hist_hld, "hld", "中繼", "次中繼"),
                    ("後援", 50, "SV", hist_sv, "sv", "救援", "次救援")):
                if today_dec != code:
                    continue
                pre_total = hist_v + sum(1 for d in prior_games if d[2] == code)
                rec = _record_text(pre_total, 1, _other_max(pit_top2[rkey], pid), rlabel, runit)
                if rec:
                    rec_items.append({"player": name, "text": rec})
                elif pre_total == 0:
                    items.append({"player": name, "text": f"生涯首次{label}"})
                elif (pre_total + 1) % step == 0:
                    items.append({"player": name, "text": f"生涯第 {pre_total + 1} 次{label}"})
    return {"items": rec_items + items}
