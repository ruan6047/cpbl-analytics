"""主審好壞球判決**分布**（推算，描述性）：逐球 TrackMan × 主審。

母體＝pitch_tracking 的 called 球（StrikeCalled/BallCalled，打者未出棒由主審判決）。
好球帶採**固定規則帶**（TrackMan 無逐打者帶頂/帶底）：本壘板半寬 0.216m + 球半徑
0.037m → |side| ≤ 0.253；高度 0.46–1.04m ± 球半徑 → 0.423–1.077（單位公尺）。

⚠️ NO-GO 邊界（PRODUCT_UX_BLUEPRINT §5.12–§5.13；ML-UMP1／ML-UMP2 研究結論）：
方向性裁判產品不成立（代理帶邊界稍動即全面翻轉），故本模組**只輸出中性、描述性
資料**——主審索引（出賽/覆蓋）與單場判決分布（逐球位置＋好/壞球）。**不輸出**聯盟
排行、準確率、誤判計數、偏隊／送分／勝負影響等方向性或評判語意；固定規則帶僅為單場
散點的**空間參考**，不作為對錯真值（不得以「代理帶一致率」改名保留）。
限制：pitch_tracking 為球場端設備、覆蓋不全（無設備場次無分布），2026 起才有。
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
       t.pitcher_name, t.hitter_name, t.ball_cnt, t.strike_cnt, t.out_cnt,
       t.plate_loc_side AS side, t.plate_loc_height AS height,
       (t.pitch_call = 'StrikeCalled') AS called_strike,
       (abs(t.plate_loc_side) <= %(hw)s AND t.plate_loc_height BETWEEN %(zb)s AND %(zt)s)
         AS in_zone
FROM cpbl.pitch_tracking t
WHERE t.year = %(season)s AND t.kind_code = %(kind)s
  AND t.pitch_call IN ('StrikeCalled', 'BallCalled')
  AND t.plate_loc_side IS NOT NULL AND t.plate_loc_height IS NOT NULL
"""


def _miss_m(side: float, height: float) -> float:
    """至好球帶邊界的最短歐氏距離（公尺；帶內為 0）。僅供 server 端追蹤異常過濾。"""
    dx = max(0.0, abs(side) - HALF_W)
    dy = max(0.0, Z_BOT - height, height - Z_TOP)
    return (dx * dx + dy * dy) ** 0.5


def _is_tracking_anomaly(side: float, height: float, called_strike: bool, in_zone: bool) -> bool:
    """離帶 >50cm 還被判好球＝TrackMan 軌跡錯誤（非主審問題），server 端剔除。"""
    return called_strike and not in_zone and _miss_m(side, height) > 0.5


@router.get("/api/v1/umpires")
def umpire_index(season: int = Query(DEFAULT_SEASON), kind_code: str = Query("A")) -> dict:
    """中性主審索引：本季主審執法場次與逐球追蹤覆蓋，供進入個人紀錄。

    刻意**無排行、無準確率、無評判**：依執法場次遞減排序＝工作量索引（非優劣）。
    coverage＝tracked_games／games，誠實揭露非隨機的設備缺口。
    """
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            WITH head AS (
              SELECT d.head_umpire AS umpire, g.game_sno,
                     (SELECT count(*) FROM cpbl.pitch_tracking t
                       WHERE t.year = g.year AND t.kind_code = g.kind_code
                         AND t.game_sno = g.game_sno
                         AND t.pitch_call IN ('StrikeCalled', 'BallCalled')) AS called
              FROM cpbl.game_detail d
              JOIN cpbl.games g ON g.year = d.year AND g.kind_code = d.kind_code
                               AND g.game_sno = d.game_sno
              WHERE d.year = %(season)s AND d.kind_code = %(kind)s
                AND d.head_umpire IS NOT NULL
                AND g.game_date <= CURRENT_DATE
            )
            SELECT umpire,
                   count(*) AS games,
                   count(*) FILTER (WHERE called > 0) AS tracked_games
            FROM head
            GROUP BY umpire
            ORDER BY games DESC, umpire
            """,
            {"season": season, "kind": kind_code})
        items = _dicts(cur)
    return {"season": season, "kind_code": kind_code, "items": items}


@router.get("/api/v1/games/{game_sno}/umpire")
def game_umpire_card(game_sno: int, season: int = Query(DEFAULT_SEASON),
                     kind_code: str = Query("A")) -> dict:
    """單場主審好壞球判決**分布**（描述性）：called 球逐球位置＋判決（好球／壞球）＋中性計數。

    **不含**對錯欄位、準確率、誤判計數或方向性評判。無 TrackMan 時 pitches 為空、由前端
    依器材可用性（no_equipment）與尚未發布（pending）分流退化，**不**顯示為零誤判／零影響。
    """
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT head_umpire FROM cpbl.game_detail "
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                    (season, kind_code, game_sno))
        r = cur.fetchone()
        umpire = r[0] if r else None
        cur.execute("SELECT game_date, venue, home_team_name, away_team_name, "
                    "home_score, away_score FROM cpbl.games "
                    "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                    (season, kind_code, game_sno))
        game = _dicts(cur)
        cur.execute(_CALLED + " AND t.game_sno = %(sno)s",
                    {"season": season, "kind": kind_code, "sno": game_sno,
                     "hw": HALF_W, "zb": Z_BOT, "zt": Z_TOP})
        rows = _dicts(cur)
    pitches = []
    strikes = 0
    for p in rows:
        if _is_tracking_anomaly(p["side"], p["height"], bool(p["called_strike"]), bool(p["in_zone"])):
            continue
        cs = bool(p["called_strike"])
        strikes += cs
        pitches.append({
            "side": p["side"], "height": p["height"], "called_strike": cs,
            "inning_seq": p["inning_seq"], "pitcher_name": p["pitcher_name"],
            "hitter_name": p["hitter_name"], "ball_cnt": p["ball_cnt"],
            "strike_cnt": p["strike_cnt"], "out_cnt": p["out_cnt"],
        })
    n = len(pitches)
    summary = {"umpire": umpire, "called": n,
               "called_strikes": strikes, "called_balls": n - strikes}
    return {"season": season, "game_sno": game_sno, "summary": summary,
            "game": game[0] if game else None,
            "zone": {"half_width": HALF_W, "bot": Z_BOT, "top": Z_TOP},
            "pitches": pitches}
