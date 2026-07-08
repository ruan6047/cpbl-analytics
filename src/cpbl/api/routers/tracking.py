"""官方進階與逐球追蹤：advanced、好球帶紀律、球種武器庫、配球傾向。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _dicts
from cpbl.db import conn

router = APIRouter()

# 推算球種：優先 pitch_type_pred（軌跡導 IVB/HB → KMeans 分類，見 models/pitch_type.py），
# 缺值退回 tagged 二元弱標籤。所有逐球球種聚合/篩選共用此表達式，回中文標籤。
PT_EXPR = ("COALESCE(pitch_type_pred, CASE tagged_pitch_type "
           "WHEN 'fastball' THEN '速球' WHEN 'breakingball' THEN '變化球' END)")


@router.get("/api/v1/players/{player_id}/advanced")
def player_advanced(player_id: str, season: int = Query(DEFAULT_SEASON),
                    kind_code: str = Query("A", pattern="^(A|D)$")) -> dict:
    """官方進階數據（stats.cpbl）+ 官方 PR。batting=進攻、pitching=被打。kind_code：A=一軍 D=二軍。"""
    out: dict[str, Any] = {"player_id": player_id, "season": season, "kind_code": kind_code,
                           "batting": None, "pitching": None}
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT * FROM cpbl.advanced_stats WHERE acnt = %s AND year = %s AND kind_code = %s",
                    (player_id, season, kind_code))
        for row in _dicts(cur):
            out[row["role"]] = row
    return out


# 好球帶（公尺座標近似）：左右 ±0.25、上下 0.45~1.05
_SWING = "('InPlay','FoulBallNotFieldable','FoulBallFieldable','StrikeSwinging')"
_CONTACT = "('InPlay','FoulBallNotFieldable','FoulBallFieldable')"


def _batted_result(content: str | None) -> str:
    """從逐球 content 文字判斷擊球結果：hr/3b/2b/1b/out。
    content 在 DB 為雙重編碼（UTF-8 bytes 被當 latin-1 存），讀取時先還原。"""
    try:
        c = (content or "").encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        c = content or ""
    if "全壘打" in c:
        return "hr"
    if "三壘安打" in c:
        return "3b"
    if "二壘安打" in c:
        return "2b"
    if "一壘安打" in c or "內野安打" in c:
        return "1b"
    return "out"


def _zone_result(pitch_call: str | None, content: str | None) -> str:
    """單球進壘結果分類：take(未揮棒)/whiff(揮空)/foul(界外)/hit(安打)/out(出局)。"""
    if pitch_call == "StrikeSwinging":
        return "whiff"
    if pitch_call in ("FoulBallNotFieldable", "FoulBallFieldable"):
        return "foul"
    if pitch_call == "InPlay":
        return "hit" if _batted_result(content) in ("hr", "3b", "2b", "1b") else "out"
    return "take"


@router.get("/api/v1/players/{player_id}/discipline")
def player_discipline(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|D)$"),
) -> dict:
    """好球帶紀律（自 pitch_tracking 計算）。batting=該打者面對；pitching=該投手誘導。
    含揮棒/揮空/接觸/CSW/追打/帶內揮棒/好球帶比例，及進壘點散布。kind_code：A=一軍 D=二軍。"""
    col = "hitter_acnt" if role == "batting" else "pitcher_acnt"
    pct = lambda a, b: round(a / b * 100, 1) if b else None  # noqa: E731
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT
              count(*) loc,
              count(*) tot,
              count(*) FILTER (WHERE pitch_call IN {_SWING}) sw,
              count(*) FILTER (WHERE pitch_call = 'StrikeSwinging') wh,
              count(*) FILTER (WHERE pitch_call IN {_CONTACT}) ct,
              count(*) FILTER (WHERE pitch_call IN ('StrikeCalled','StrikeSwinging')) csw,
              count(*) FILTER (WHERE iz) zone,
              count(*) FILTER (WHERE iz AND sw0) zsw,
              count(*) FILTER (WHERE (NOT iz) AND sw0) osw,
              count(*) FILTER (WHERE NOT iz) ozone
            FROM (
              SELECT pitch_call,
                     (abs(plate_loc_side) <= 0.21 AND plate_loc_height BETWEEN 0.5 AND 1.0) iz,
                     (pitch_call IN {_SWING}) sw0
              FROM cpbl.pitch_tracking
              WHERE {col} = %s AND year = %s AND kind_code = %s AND plate_loc_side IS NOT NULL
            ) q
            """,
            (player_id, season, kind_code),
        )
        loc, tot, sw, wh, ct, csw, zone, zsw, osw, ozone = cur.fetchone()
        summary = {
            "pitches": tot, "located": loc,
            "swing_pct": pct(sw, loc), "whiff_pct": pct(wh, sw), "contact_pct": pct(ct, sw),
            "csw_pct": pct(csw, loc), "zone_pct": pct(zone, loc),
            "z_swing_pct": pct(zsw, zone), "chase_pct": pct(osw, ozone),
        }
        cur.execute(
            f"""
            SELECT plate_loc_side, plate_loc_height, pitch_call, content, hit_exit_speed, hit_launch_angle,
                   {PT_EXPR}
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND plate_loc_side IS NOT NULL
            """,
            (player_id, season, kind_code),
        )
        _swset = {"InPlay", "FoulBallNotFieldable", "FoulBallFieldable", "StrikeSwinging"}
        points = [{"x": float(s), "y": float(h),
                   "sw": pc in _swset, "wh": pc == "StrikeSwinging",
                   "result": _zone_result(pc, ct), "ev": float(ev) if ev is not None else None,
                   "la": float(la) if la is not None else None, "pt": pt}
                  for s, h, pc, ct, ev, la, pt in cur.fetchall()]
        cur.execute(
            f"""
            SELECT hit_direction, hit_distance, hit_exit_speed, content, {PT_EXPR}, hit_launch_angle
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND pitch_call = 'InPlay'
              AND hit_distance IS NOT NULL AND hit_direction IS NOT NULL
            """,
            (player_id, season, kind_code),
        )
        spray = [{"dir": float(d), "dist": float(dist),
                  "ev": float(ev) if ev is not None else None, "result": _batted_result(ct), "pt": pt,
                  "la": float(la) if la is not None else None}
                 for d, dist, ev, ct, pt, la in cur.fetchall()]
        # 擊球仰角 × 初速（barrel 散點）：InPlay 且有 LA+EV
        cur.execute(
            f"""
            SELECT hit_launch_angle, hit_exit_speed, content
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND pitch_call = 'InPlay'
              AND hit_launch_angle IS NOT NULL AND hit_exit_speed IS NOT NULL
            """,
            (player_id, season, kind_code),
        )
        batted = [{"la": float(la), "ev": float(ev), "result": _batted_result(ct)}
                  for la, ev, ct in cur.fetchall()]
        # 擊球品質（打者）／球質（投手）：逐球樣本衍生
        cur.execute(
            f"""
            SELECT round(avg(hit_launch_angle)::numeric, 1), round(max(hit_distance)::numeric, 1),
                   round(avg(hit_exit_speed)::numeric, 1), round(avg(extension)::numeric, 2),
                   round(avg(rel_height)::numeric, 2), round(avg(rel_speed)::numeric, 1)
            FROM cpbl.pitch_tracking WHERE {col} = %s AND year = %s AND kind_code = %s
            """,
            (player_id, season, kind_code),
        )
        la, maxd, ev, ext, relh, rels = cur.fetchone()
        fl = lambda v: float(v) if v is not None else None  # noqa: E731
        _q = lambda la, maxd, ev, ext, relh, rels: {  # noqa: E731
            "avg_launch_angle": fl(la), "max_hit_dist": fl(maxd), "avg_exit_speed": fl(ev),
            "avg_extension": fl(ext), "avg_rel_height": fl(relh), "avg_speed": fl(rels)}
        quality = _q(la, maxd, ev, ext, relh, rels)
        # 依推算球種拆的球質/擊球品質，供前端球種鏡頭切換（速球/指叉/卡特/滑球/曲球）
        cur.execute(
            f"""
            SELECT {PT_EXPR} pt,
                   round(avg(hit_launch_angle)::numeric, 1), round(max(hit_distance)::numeric, 1),
                   round(avg(hit_exit_speed)::numeric, 1), round(avg(extension)::numeric, 2),
                   round(avg(rel_height)::numeric, 2), round(avg(rel_speed)::numeric, 1)
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND {PT_EXPR} IS NOT NULL
            GROUP BY pt
            """,
            (player_id, season, kind_code),
        )
        quality_by_pt = {row[0]: _q(*row[1:]) for row in cur.fetchall()}
    return {"player_id": player_id, "role": role, "summary": summary,
            "quality": quality, "quality_by_pt": quality_by_pt,
            "points": points, "spray": spray, "batted": batted}
@router.get("/api/v1/players/{player_id}/arsenal")
def player_arsenal(
    player_id: str,
    role: str = Query("pitching", pattern="^(batting|pitching)$"),
    season: int = Query(DEFAULT_SEASON),
) -> dict:
    """球種應對：自 pitch_tracking 按推算球種彙總。pitching=投手配球、batting=打者面對。
    回每球種：球數、用球/面對%、均速、(投手)轉速、揮空%、(打者)擊球初速。球種為推算（見 PT_EXPR）。"""
    col = "pitcher_acnt" if role == "pitching" else "hitter_acnt"
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT {PT_EXPR} pt, count(*) n, avg(rel_speed), avg(spin_rate),
                   count(*) FILTER (WHERE pitch_call = 'StrikeSwinging'),
                   count(*) FILTER (WHERE pitch_call IN {_SWING}),
                   avg(hit_exit_speed)
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = 'A' AND {PT_EXPR} IS NOT NULL
            GROUP BY pt ORDER BY n DESC
            """,
            (player_id, season),
        )
        rows = cur.fetchall()
    total = sum(r[1] for r in rows) or 1
    fl = lambda v: round(float(v), 1) if v is not None else None  # noqa: E731
    items = [
        {"pitch_type": pt, "n": n, "usage": round(n / total * 100, 1),
         "avg_speed": fl(spd), "avg_spin": round(float(spin)) if spin is not None else None,
         "whiff_pct": round(wh / sw * 100, 1) if sw else None,
         "avg_ev": fl(ev)}
        for pt, n, spd, spin, wh, sw, ev in rows
    ]
    return {"player_id": player_id, "role": role, "items": items}


def _count_bucket(b: int, s: int) -> str:
    """球數情境分桶（互斥、依優先序）。"""
    if s == 2:
        return "兩好球"
    if b == 0 and s == 0:
        return "第一球"
    if s > b:
        return "投手領先"
    if b > s:
        return "打者領先"
    return "平球數"


@router.get("/api/v1/players/{player_id}/pitch-mix")
def player_pitch_mix(
    player_id: str,
    role: str = Query("pitching", pattern="^(batting|pitching)$"),
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|D)$"),
) -> dict:
    """配球傾向：不同球數情境下各推算球種占比。pitching=投手配球、batting=打者面對。kind_code：A=一軍 D=二軍。"""
    col = "pitcher_acnt" if role == "pitching" else "hitter_acnt"
    order = ["第一球", "打者領先", "平球數", "投手領先", "兩好球"]
    agg: dict[str, dict[str, int]] = {k: {} for k in order}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            f"""
            SELECT ball_cnt, strike_cnt, {PT_EXPR} pt
            FROM cpbl.pitch_tracking
            WHERE {col} = %s AND year = %s AND kind_code = %s AND {PT_EXPR} IS NOT NULL
              AND ball_cnt IS NOT NULL AND strike_cnt IS NOT NULL
            """,
            (player_id, season, kind_code),
        )
        for b, s, pt in cur.fetchall():
            bk = _count_bucket(b, s)
            agg[bk][pt] = agg[bk].get(pt, 0) + 1
    items = []
    for k in order:
        n = sum(agg[k].values())
        if not n:
            continue
        mix = [{"pitch_type": pt, "pct": round(c / n * 100, 1)}
               for pt, c in sorted(agg[k].items(), key=lambda x: -x[1])]
        items.append({"bucket": k, "n": n, "mix": mix})
    return {"player_id": player_id, "role": role, "items": items}
