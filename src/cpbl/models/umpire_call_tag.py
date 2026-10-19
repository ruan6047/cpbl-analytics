"""本場焦點「判決標籤」（#285 批次 G，plan-8 r1；需求方 6260009450、6260092225）。

看球感受的賽事標籤，**不是裁判分析**：ML-UMP1／2 的 NO-GO 結論不變（不得據此宣稱判決偏向任何一隊）。
判定放在後端（需求方 G-Q2）：逐打席 ΔWP 只能由後端解算器算，單場頁 ``/facts`` 與 /playoffs 逐場焦點共用本模組，
結果一定一致；前端 ``buildHighlights`` 只排字（隊碼 → 識象／猿夢／獅捨／邦忙／成全／鷹明）。

規則：
- 母體＝DB canonical（已發布 build）打席中 |ΔWP| ≥ 0.10 者（ΔWP＝``pa_facts.wp_swings`` 的 ``delta``，
  與 ``/facts`` ``key_plays`` 同一套解算器）；不限數量。
- 判決球＝``pitch_call`` 為 ``StrikeCalled``／``BallCalled``（揮棒、擊球、``BallinDirt``、故意四壞都不算）。
- 好球帶＝逐打者身高比例帶（``umpire_impact.height_scaled_proxy_zone``）＋球半徑（``BALL_RADIUS_M``），
  容差 1 吋（需求方 G-Q1：2.54 cm）：判好球而球心在「帶＋球半徑」外超過 1 吋 ⇒ 守備方得利；
  判壞球而球心在「帶＋球半徑」內超過 1 吋 ⇒ 打擊方得利。
- 只有單方得利才回該隊；兩隊都有、或都沒有 ⇒ 不出。
- 資料不足一律整場不出（需求方「資料不足就不顯示」）：非權威源（provisional）、沒有 WP 或任一 ready 打席
  缺 WP、合格打席缺逐球（``tracking_availability != 'available'``）、判決球缺落點、打者缺身高、0 個合格打席。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cpbl.api.helpers import _dicts
from cpbl.models.umpire_impact import (
    BALL_RADIUS_M,
    height_scaled_proxy_zone,
    signed_edge_distance_cm,
)

WP_MIN_ABS = 0.10
TOLERANCE_CM = 2.54
CALLED = ("StrikeCalled", "BallCalled")

TRACKING_SQL = """
    SELECT pa.pa_index, pa.tracking_availability
      FROM cpbl.game_plate_appearances pa
      JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
     WHERE pa.year = %(year)s AND pa.kind_code = %(kind)s AND pa.game_sno = %(sno)s AND pa.pa_index = ANY(%(idx)s)
"""

CALLED_PITCHES_SQL = """
    SELECT pa.pa_index, pt.pitch_call, pt.plate_loc_side, pt.plate_loc_height, pt.hitter_acnt, p.height_cm
      FROM cpbl.game_recap_builds b
      JOIN cpbl.game_pa_pitch_mappings m ON m.build_id = b.build_id AND m.mapping_state = 'mapped'
      JOIN cpbl.game_plate_appearances pa ON pa.pa_row_id = m.pa_row_id AND pa.build_id = b.build_id
      JOIN cpbl.pitch_tracking pt ON pt.year = m.year AND pt.kind_code = m.kind_code AND pt.game_sno = m.game_sno
           AND pt.pitcher_acnt = m.pitcher_acnt AND pt.pitch_cnt = m.pitch_cnt
      LEFT JOIN cpbl.players p ON p.id = pt.hitter_acnt
     WHERE b.year = %(year)s AND b.kind_code = %(kind)s AND b.game_sno = %(sno)s AND b.state = 'published'
       AND pa.pa_index = ANY(%(idx)s) AND pt.pitch_call = ANY(%(calls)s)
     ORDER BY pa.pa_index, pt.pitch_cnt
"""


def _none(reason: str) -> dict:
    return {"team_code": None, "reason": reason}


def called_beneficiary(call: str, side: float, height: float, height_cm: int) -> str | None:
    """單一判決球：``fielding``（判好球但在帶＋球半徑外 >1 吋）／``batting``（判壞球但在內 >1 吋）／None。"""
    zone = height_scaled_proxy_zone(height_cm)
    effective_cm = signed_edge_distance_cm(side, height, zone) + BALL_RADIUS_M * 100.0   # 帶＋球半徑：內正外負
    if call == "StrikeCalled" and effective_cm < -TOLERANCE_CM:
        return "fielding"
    if call == "BallCalled" and effective_cm > TOLERANCE_CM:
        return "batting"
    return None


def umpire_call_tag(qualifying: list[dict], tracking: dict[int, Any], pitches: Iterable[dict], *,
                    away: str, home: str) -> dict:
    """純函式。``qualifying``＝合格打席 ``[{pa_index, half}]``（half "1"＝客隊進攻）；``tracking``＝pa_index →
    tracking_availability；``pitches``＝合格打席內的判決球（含 ``height_cm``）。回 ``{team_code, reason}``。"""
    if not qualifying:
        return _none("no_qualifying_pa")
    if any(tracking.get(q["pa_index"]) != "available" for q in qualifying):
        return _none("tracking_unavailable")
    half_of = {q["pa_index"]: str(q["half"]) for q in qualifying}
    winners: set[str] = set()
    for p in pitches:
        if p.get("plate_loc_side") is None or p.get("plate_loc_height") is None:
            return _none("pitch_location_missing")
        if not p.get("height_cm"):
            return _none("batter_height_missing")
        who = called_beneficiary(p["pitch_call"], float(p["plate_loc_side"]), float(p["plate_loc_height"]),
                                 int(p["height_cm"]))
        if who is None:
            continue
        batting, fielding = (away, home) if half_of[p["pa_index"]] == "1" else (home, away)
        winners.add(fielding if who == "fielding" else batting)
    if len(winners) == 1:
        return {"team_code": next(iter(winners)), "reason": None}
    return _none("both_sides" if winners else "no_mismatch")


def qualifying_pas(facts: list[dict], swings: dict[int, dict]) -> list[dict] | None:
    """|ΔWP| ≥ 0.10 的打席；任一 ready 打席缺 WP ⇒ None（整場不處理）。"""
    if any(f.get("state") == "ready" and f.get("pa_index") not in swings for f in facts):
        return None
    return [{"pa_index": f["pa_index"], "half": f.get("half")} for f in facts
            if f.get("pa_index") in swings and abs(swings[f["pa_index"]]["delta"]) >= WP_MIN_ABS]


def compute_from_facts(cur, *, season: int, kind_code: str, game_sno: int, facts: list[dict],
                       swings: dict[int, dict], wp_reason: str | None, game: dict) -> dict:
    """權威源（DB canonical）路徑：呼叫端已算好事實流與 ΔWP；本函式只再讀逐球與身高（同一游標）。"""
    if wp_reason is not None or not swings:
        return _none(wp_reason or "winprob_unavailable")
    qual = qualifying_pas(facts, swings)
    if qual is None:
        return _none("wp_unavailable_pa")
    if not qual:
        return _none("no_qualifying_pa")
    params = {"year": season, "kind": kind_code, "sno": game_sno, "idx": [q["pa_index"] for q in qual]}
    cur.execute(TRACKING_SQL, params)
    tracking = {r["pa_index"]: r["tracking_availability"] for r in _dicts(cur)}
    cur.execute(CALLED_PITCHES_SQL, {**params, "calls": list(CALLED)})
    pitches = _dicts(cur)
    return umpire_call_tag(qual, tracking, pitches, away=str(game.get("away_team_code") or ""),
                           home=str(game.get("home_team_code") or ""))


def game_umpire_call(season: int, kind_code: str, game_sno: int) -> dict:
    """單場判決標籤（自開連線；/playoffs 逐場焦點用）。與 ``/facts`` 同一條權威源路徑。"""
    from cpbl.models.pa_facts import build_game_facts

    payload = build_game_facts(season, kind_code, game_sno, snapshot=None)
    return payload.get("umpire_call") or _none("not_authoritative")
