"""傘審記分卡 [Umpire Scorecard]（推算）：逐球 TrackMan × 主審。

母體＝pitch_tracking 的 called 球（StrikeCalled/BallCalled，打者未出棒由主審判決）。
好球帶採**固定規則帶**（TrackMan 無逐打者帶頂/帶底）：本壘板半寬 0.216m + 球半徑
0.037m → |side| ≤ 0.253；高度 0.46–1.04m ± 球半徑 → 0.423–1.077（單位公尺）。
限制：pitch_tracking 為球場端設備、覆蓋不全（無設備場次無報告）、2026 起才有。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _dicts
from cpbl.db import conn

router = APIRouter()

HALF_W = 0.253
Z_BOT, Z_TOP = 0.423, 1.077

_CALLED = """
SELECT t.game_sno, t.pitcher_acnt, t.hitter_acnt, t.inning_seq,
       t.plate_loc_side AS side, t.plate_loc_height AS height,
       (t.pitch_call = 'StrikeCalled') AS called_strike,
       (abs(t.plate_loc_side) <= %(hw)s AND t.plate_loc_height BETWEEN %(zb)s AND %(zt)s)
         AS in_zone
FROM cpbl.pitch_tracking t
WHERE t.year = %(season)s AND t.kind_code = %(kind)s
  AND t.pitch_call IN ('StrikeCalled', 'BallCalled')
  AND t.plate_loc_side IS NOT NULL AND t.plate_loc_height IS NOT NULL
"""


def _miss_cm(side: float, height: float) -> float:
    """至好球帶邊界的最短距離（公分；帶內為 0）。"""
    dx = max(0.0, abs(side) - HALF_W)
    dy = max(0.0, Z_BOT - height, height - Z_TOP)
    return round((dx * dx + dy * dy) ** 0.5 * 100, 1)


@router.get("/api/v1/umpires")
def umpire_leaderboard(season: int = Query(DEFAULT_SEASON), kind_code: str = Query("A")) -> dict:
    """主審季排行：好壞球判決準確率（僅含有 TrackMan 的場次；推算）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            WITH called AS ({_CALLED}),
            judged AS (
              SELECT d.head_umpire, c2.*,
                     (c2.called_strike = c2.in_zone) AS correct
              FROM called c2
              JOIN cpbl.game_detail d ON d.year = %(season)s AND d.kind_code = %(kind)s
                                     AND d.game_sno = c2.game_sno
              WHERE d.head_umpire IS NOT NULL)
            SELECT head_umpire AS umpire,
                   count(DISTINCT game_sno) AS games,
                   count(*) AS called,
                   round(100.0 * count(*) FILTER (WHERE correct) / count(*), 1) AS acc,
                   round(100.0 * count(*) FILTER (WHERE correct AND in_zone)
                         / nullif(count(*) FILTER (WHERE in_zone), 0), 1) AS strike_acc,
                   round(100.0 * count(*) FILTER (WHERE correct AND NOT in_zone)
                         / nullif(count(*) FILTER (WHERE NOT in_zone), 0), 1) AS ball_acc
            FROM judged GROUP BY head_umpire
            HAVING count(DISTINCT game_sno) >= 2
            ORDER BY acc DESC
            """,
            {"season": season, "kind": kind_code, "hw": HALF_W, "zb": Z_BOT, "zt": Z_TOP})
        items = _dicts(cur)
    return {"season": season, "zone": {"half_width": HALF_W, "bot": Z_BOT, "top": Z_TOP},
            "items": items}


@router.get("/api/v1/games/{game_sno}/umpire")
def game_umpire_card(game_sno: int, season: int = Query(DEFAULT_SEASON),
                     kind_code: str = Query("A")) -> dict:
    """單場主審記分卡：called 球逐球（位置/判決/對錯）+ 摘要。無 TrackMan 回空。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT head_umpire FROM cpbl.game_detail "
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                    (season, kind_code, game_sno))
        r = cur.fetchone()
        umpire = r[0] if r else None
        cur.execute(_CALLED + " AND t.game_sno = %(sno)s",
                    {"season": season, "kind": kind_code, "sno": game_sno,
                     "hw": HALF_W, "zb": Z_BOT, "zt": Z_TOP})
        pitches = _dicts(cur)
    for p in pitches:
        p["correct"] = bool(p["called_strike"]) == bool(p["in_zone"])
        p["miss_cm"] = 0.0 if p["correct"] else (
            _miss_cm(p["side"], p["height"]) if not p["in_zone"] else 0.0)
    n = len(pitches)
    ok = sum(1 for p in pitches if p["correct"])
    misses = [p for p in pitches if not p["correct"]]
    summary = {
        "umpire": umpire, "called": n,
        "acc": round(100 * ok / n, 1) if n else None,
        "missed": len(misses),
        "avg_miss_cm": round(sum(_miss_cm(p["side"], p["height"]) for p in misses
                                 if not p["in_zone"]) / max(1, len([p for p in misses if not p["in_zone"]])), 1)
        if misses else 0.0,
    }
    return {"season": season, "game_sno": game_sno, "summary": summary,
            "zone": {"half_width": HALF_W, "bot": Z_BOT, "top": Z_TOP},
            "pitches": pitches}
