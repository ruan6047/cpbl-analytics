"""官方進階與逐球追蹤：advanced、好球帶紀律、球種武器庫、配球傾向。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _batted_result, _dicts
from cpbl.db import conn
from cpbl.ingest.advanced_snapshot import gating_predicate

# 只讀最後成功晉升的完整快照（INGEST-ADV-RECONCILE1）；晉升前的 scope 保留 legacy 行為。
_ADV_GATE = gating_predicate("a", "player_stats")

router = APIRouter()

# 推算球種：優先 pitch_type_pred（軌跡導 IVB/HB → KMeans 分類，見 models/pitch_type.py），
# 缺值退回 tagged 二元弱標籤。所有逐球球種聚合/篩選共用此表達式，回中文標籤。
_PT_RAW = ("COALESCE(pitch_type_pred_v2, pitch_type_pred, CASE tagged_pitch_type "
           "WHEN 'fastball' THEN '速球' WHEN 'breakingball' THEN '變化球' END)")
# v2 臨界複合名（top1/top2）帶方向 → 同一對球種產生 A/B 與 B/A 兩種標籤（如 滑球/橫掃
# 與 橫掃/滑球），聚合時被拆成兩群。顯示層統一正規化為固定順序（成分依 _PT_ORD 排序）
# 的單一標注（UX-7A）；DB 原值不動，方向資訊仍在庫可逆。成分不在表者（速球/變化球）不含 '/'
# 不受影響；array_position 對未知成分回 NULL → 比較為 NULL → 走 ELSE 保留原值。
_PT_ORD = "ARRAY['四縫','伸卡','卡特','滑球','橫掃','曲球','變速','指叉']"
PT_EXPR = (
    f"(CASE WHEN strpos({_PT_RAW}, '/') > 0"
    f" AND array_position({_PT_ORD}, split_part({_PT_RAW}, '/', 1))"
    f" > array_position({_PT_ORD}, split_part({_PT_RAW}, '/', 2))"
    f" THEN split_part({_PT_RAW}, '/', 2) || '/' || split_part({_PT_RAW}, '/', 1)"
    f" ELSE {_PT_RAW} END)"
)


@router.get("/api/v1/players/{player_id}/advanced")
def player_advanced(player_id: str, season: int = Query(DEFAULT_SEASON),
                    kind_code: str = Query("A", pattern="^(A|D)$")) -> dict:
    """官方進階數據（stats.cpbl）+ 官方 PR。batting=進攻、pitching=被打。kind_code：A=一軍 D=二軍。"""
    out: dict[str, Any] = {"player_id": player_id, "season": season, "kind_code": kind_code,
                           "batting": None, "pitching": None}
    with conn() as c:
        cur = c.cursor()
        cur.execute(f"SELECT a.* FROM cpbl.advanced_stats a "
                    f"WHERE a.acnt = %s AND a.year = %s AND a.kind_code = %s AND {_ADV_GATE}",
                    (player_id, season, kind_code))
        for row in _dicts(cur):
            out[row["role"]] = row
    return out


# 好球帶（公尺座標近似）：左右 ±0.25、上下 0.45~1.05
_SWING = "('InPlay','FoulBallNotFieldable','FoulBallFieldable','StrikeSwinging')"
_CONTACT = "('InPlay','FoulBallNotFieldable','FoulBallFieldable')"


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


@router.get("/api/v1/players/{player_id}/movement")
def player_movement(
    player_id: str,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A", pattern="^(A|D)$"),
) -> dict:
    """球種位移（ML-PT2 Phase1）：逐球 IVB×HB 散點 + 本人/聯盟各球種平均（投手）。
    HB 符號隨慣用手翻轉 → 聯盟平均先把左投鏡像到右投視角再平均，
    回傳時依本人慣用手翻回，確保與本人散點同視角可比。IVB/速度/轉速不受慣用手影響。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT throws FROM cpbl.players WHERE id = %s", (player_id,))
        row = cur.fetchone()
        throws = row[0] if row else None
        lefty = throws == "左投"
        cur.execute(
            f"""
            SELECT {PT_EXPR} pt, hb_cm, ivb_cm
            FROM cpbl.pitch_tracking
            WHERE pitcher_acnt = %s AND year = %s AND kind_code = %s
              AND ivb_cm IS NOT NULL AND hb_cm IS NOT NULL AND {PT_EXPR} IS NOT NULL
            """,
            (player_id, season, kind_code),
        )
        points = [{"pt": pt, "hb": round(float(hb), 1), "ivb": round(float(ivb), 1)}
                  for pt, hb, ivb in cur.fetchall()]
        cur.execute(
            f"""
            SELECT {PT_EXPR} pt, count(*), avg(rel_speed), avg(spin_rate), avg(ivb_cm), avg(hb_cm)
            FROM cpbl.pitch_tracking
            WHERE pitcher_acnt = %s AND year = %s AND kind_code = %s AND {PT_EXPR} IS NOT NULL
            GROUP BY pt ORDER BY count(*) DESC
            """,
            (player_id, season, kind_code),
        )
        mine = cur.fetchall()
        cur.execute(
            f"""
            SELECT {PT_EXPR} pt, avg(rel_speed), avg(spin_rate), avg(ivb_cm),
                   avg(CASE WHEN pl.throws = '左投' THEN -t.hb_cm ELSE t.hb_cm END)
            FROM cpbl.pitch_tracking t JOIN cpbl.players pl ON pl.id = t.pitcher_acnt
            WHERE t.year = %s AND t.kind_code = %s AND {PT_EXPR} IS NOT NULL
            GROUP BY pt
            """,
            (season, kind_code),
        )
        lg = {r[0]: r for r in cur.fetchall()}
        # 出手點 2D（UX-7A）：rel_side×rel_height 逐球 + 各球種質心/重複性。
        # rel_side 實測慣例：右投均值 +0.56、左投 -0.55 → 正值＝持球臂側該側。
        # 顯示統一「＋＝臂側」：左投翻號，避免左右投圖形互為鏡像難比讀。
        side = "-rel_side" if lefty else "rel_side"
        cur.execute(
            f"""
            SELECT {PT_EXPR} pt, round(({side})::numeric, 2), round(rel_height::numeric, 2)
            FROM cpbl.pitch_tracking
            WHERE pitcher_acnt = %s AND year = %s AND kind_code = %s
              AND rel_side IS NOT NULL AND rel_height IS NOT NULL AND {PT_EXPR} IS NOT NULL
            """,
            (player_id, season, kind_code),
        )
        rel_points = [{"pt": pt, "x": float(x), "y": float(y)} for pt, x, y in cur.fetchall()]
        # 各球種質心＋重複性 spread（質心距離 RMS，cm）；樣本 <10 不給 spread（誠實缺席）。
        cur.execute(
            f"""
            SELECT {PT_EXPR} pt, count(*) n, avg({side}) sx, avg(rel_height) sy,
                   sqrt(var_pop({side}) + var_pop(rel_height)) * 100 spread
            FROM cpbl.pitch_tracking
            WHERE pitcher_acnt = %s AND year = %s AND kind_code = %s
              AND rel_side IS NOT NULL AND rel_height IS NOT NULL AND {PT_EXPR} IS NOT NULL
            GROUP BY pt ORDER BY n DESC
            """,
            (player_id, season, kind_code),
        )
        rel_rows = cur.fetchall()
    total = sum(r[1] for r in mine) or 1
    fl = lambda v, d=1: round(float(v), d) if v is not None else None  # noqa: E731
    spn = lambda v: round(float(v)) if v is not None else None  # noqa: E731
    summary = []
    for pt, n, spd, spin, ivb, hb in mine:
        lr = lg.get(pt)
        summary.append({
            "pt": pt, "n": n, "usage": round(n / total * 100, 1),
            "speed": fl(spd), "spin": spn(spin), "ivb": fl(ivb), "hb": fl(hb),
            "lg": {
                "speed": fl(lr[1]) if lr else None, "spin": spn(lr[2]) if lr else None,
                "ivb": fl(lr[3]) if lr else None,
                "hb": fl(-lr[4] if lefty else lr[4]) if lr and lr[4] is not None else None,
            },
        })
    rel_summary = [{"pt": pt, "n": n, "x": fl(sx, 2), "y": fl(sy, 2),
                    "spread_cm": fl(spread) if n >= 10 else None}
                   for pt, n, sx, sy, spread in rel_rows]
    # 跨球種出手一致性（tipping 風險指標）：各球種質心對加權總質心的 RMS 距離（cm）。
    # 質心夠穩（n≥10）的球種 <2 種時樣本不足 → None（前端顯「—」，勿以 0 誤導）。
    solid = [r for r in rel_summary if r["spread_cm"] is not None and r["x"] is not None]
    consistency_cm = None
    if len(solid) >= 2:
        tot_n = sum(r["n"] for r in solid)
        cx = sum(r["x"] * r["n"] for r in solid) / tot_n
        cy = sum(r["y"] * r["n"] for r in solid) / tot_n
        var = sum(((r["x"] - cx) ** 2 + (r["y"] - cy) ** 2) * r["n"] for r in solid) / tot_n
        consistency_cm = round(var ** 0.5 * 100, 1)
    return {"player_id": player_id, "throws": throws, "points": points, "summary": summary,
            "release": {"points": rel_points, "summary": rel_summary,
                        "consistency_cm": consistency_cm}}


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
