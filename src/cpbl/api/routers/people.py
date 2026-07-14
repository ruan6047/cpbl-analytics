"""個人頁（無 acnt 身分）：純教練 / 裁判（UX-7C，Person Hub 甲案雙軌）。

有 acnt 的人走 /players/{id}（canonical 不動）；本 router 服務無 acnt 個體，
以「kind + 中文名」定址（kind 隔離同名；教練 ~25、裁判 ~30，規模可控）。
裁判記分卡沿 umpires router 的固定規則帶與剔除規則（單一事實來源：常數共用）。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _dicts
from cpbl.api.routers.umpires import _CALLED, HALF_W, Z_BOT, Z_TOP
from cpbl.db import conn

router = APIRouter()


@router.get("/api/v1/people/coach/{name}")
def coach_profile(name: str) -> dict:
    """教練個人資料：歷年職務（coaches）＋總教練 era 戰績（managers）。
    若名字唯一對應到球員 acnt，附 player_id 供前端連回球員頁（多對應＝歧義，不附）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT c.year, c.team_code, t.short AS team_name, c.pos, c.uniform_no "
            "FROM cpbl.coaches c LEFT JOIN cpbl.team_dim t ON t.team_code = c.team_code "
            "WHERE c.name = %s ORDER BY c.year DESC, c.team_code",
            (name,),
        )
        roles = _dicts(cur)
        cur.execute(
            "SELECT m.team_code, t.short AS team_name, m.era_name, m.from_year, m.to_year, "
            "       m.g, m.w, m.l, m.t AS ties, m.win_pct, m.postseason, m.championships "
            "FROM cpbl.managers m LEFT JOIN cpbl.team_dim t ON t.team_code = m.team_code "
            "WHERE m.name = %s ORDER BY m.from_year",
            (name,),
        )
        manager_eras = _dicts(cur)
        cur.execute(
            "SELECT phase, league, team_raw, team_code, pos, from_year, to_year, needs_review "
            "FROM cpbl.coach_history "
            "WHERE name = %s "
            "ORDER BY from_year DESC NULLS LAST, to_year DESC NULLS LAST, id DESC",
            (name,),
        )
        history = _dicts(cur)
        # 同名守門：唯一對應才附 player_id（嚴禁腦補歸戶）
        cur.execute("SELECT id FROM cpbl.players WHERE name = %s", (name,))
        ids = [r[0] for r in cur.fetchall()]
    return {
        "name": name,
        "roles": roles,
        "manager_eras": manager_eras,
        "history": history,
        "player_id": ids[0] if len(ids) == 1 else None,
        "player_ambiguous": len(ids) > 1,
    }


@router.get("/api/v1/people/umpire/{name}")
def umpire_profile(name: str, season: int = Query(DEFAULT_SEASON),
                   kind_code: str = Query("A")) -> dict:
    """裁判個人頁：各崗位執法場次＋主審記分卡（僅 TrackMan 場，推算）＋近期主審場列表。
    樣本誠實：追蹤場數（tracked_games）隨摘要回傳，前端須帶樣本數呈現。"""
    with conn() as c:
        cur = c.cursor()
        # 各崗位執法場次（全季、不限 TrackMan）
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE head_umpire = %(n)s)  AS head,
                   count(*) FILTER (WHERE first_umpire = %(n)s)  AS first,
                   count(*) FILTER (WHERE second_umpire = %(n)s) AS second,
                   count(*) FILTER (WHERE third_umpire = %(n)s)  AS third,
                   count(*) FILTER (WHERE left_umpire = %(n)s OR right_umpire = %(n)s) AS lines
            FROM cpbl.game_detail d
            JOIN cpbl.games g ON g.year = d.year AND g.kind_code = d.kind_code
                             AND g.game_sno = d.game_sno
            WHERE d.year = %(season)s AND d.kind_code = %(kind)s
            """,
            {"n": name, "season": season, "kind": kind_code},
        )
        positions = _dicts(cur)[0]
        # 主審記分卡摘要（沿 umpires router 母體/剔除規則）
        cur.execute(
            f"""
            WITH called AS ({_CALLED}),
            judged AS (
              SELECT c2.*, (c2.called_strike = c2.in_zone) AS correct
              FROM called c2
              JOIN cpbl.game_detail d ON d.year = %(season)s AND d.kind_code = %(kind)s
                                     AND d.game_sno = c2.game_sno
              WHERE d.head_umpire = %(n)s
                AND NOT (c2.called_strike AND NOT c2.in_zone
                         AND (abs(c2.side) > %(hw)s + 0.5
                              OR c2.height < %(zb)s - 0.5 OR c2.height > %(zt)s + 0.5)))
            SELECT count(DISTINCT game_sno) AS tracked_games,
                   count(*) AS called,
                   round(100.0 * count(*) FILTER (WHERE correct) / nullif(count(*), 0), 1) AS acc,
                   round(100.0 * count(*) FILTER (WHERE correct AND in_zone)
                         / nullif(count(*) FILTER (WHERE in_zone), 0), 1) AS strike_acc,
                   round(100.0 * count(*) FILTER (WHERE correct AND NOT in_zone)
                         / nullif(count(*) FILTER (WHERE NOT in_zone), 0), 1) AS ball_acc
            FROM judged
            """,
            {"n": name, "season": season, "kind": kind_code,
             "hw": HALF_W, "zb": Z_BOT, "zt": Z_TOP},
        )
        scorecard = _dicts(cur)[0]
        # 近期主審場（含比分；有無 TrackMan 由前端以 called>0 判斷 → 這裡直接附 called 數）
        cur.execute(
            """
            SELECT g.game_sno, g.game_date, g.venue,
                   g.away_team_name, g.away_team_code, g.away_score,
                   g.home_team_name, g.home_team_code, g.home_score,
                   (SELECT count(*) FROM cpbl.pitch_tracking t
                     WHERE t.year = g.year AND t.kind_code = g.kind_code
                       AND t.game_sno = g.game_sno
                       AND t.pitch_call IN ('StrikeCalled','BallCalled')) AS called
            FROM cpbl.game_detail d
            JOIN cpbl.games g ON g.year = d.year AND g.kind_code = d.kind_code
                             AND g.game_sno = d.game_sno
            WHERE d.year = %(season)s AND d.kind_code = %(kind)s AND d.head_umpire = %(n)s
              AND g.home_score + g.away_score > 0
            ORDER BY g.game_date DESC LIMIT 15
            """,
            {"n": name, "season": season, "kind": kind_code},
        )
        recent = _dicts(cur)
    return {"name": name, "season": season, "positions": positions,
            "scorecard": scorecard, "recent_games": recent}
