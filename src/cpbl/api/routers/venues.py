"""球場數據特色（VENUE-PARK1）：park factor／滾飛比／選手極端表現。

方法論（紅線，改公式前先讀）：
- **Park factor＝主客對照法**（matched-team expected）：對球場 v、賽季 s、統計項 X，
  observed = v 場所有「隊-場」的 X 合計；expected = 各該隊同季「非 v 球場」場均 X × 該隊
  在 v 的場數；PF = observed / expected。期望值用同一批球隊自己在其他球場的率當基準，
  控制「哪些球隊常在此打球」的組成偏差——不与聯盟平均比（會被強弱隊主場用量差干擾）。
- **跨季合併**：分季算 observed/expected 再加總相除（季內配對，抵銷聯盟環境逐年漂移），
  不是各季 PF 取平均（小樣本比值會爆）。
- **誠實揭露**：一律回傳場數樣本；單季 < MIN_SEASON_GAMES、合併 < MIN_POOLED_GAMES 掛
  low_sample。不做 shrinkage——描述性頁面以「原始比值＋明示樣本」優先於模型化平滑。
- **資料下限 2018**：gamelog/livelog 起始年，1990–2017 無法歸因球場（R 理論上可回推，
  為口徑一致同樣從 2018 起）。選手極端表現用官方生涯分項（year=9999），涵蓋 2018 前。
- 球場別名歸一：桃園（2018–2021 場名）＝樂天桃園、亞太副場＝亞太副（同座球場）。
  splits 端已在 ingest 對映（splits_calc.VENUE_OFFICIAL），games 端在本檔 SQL CASE。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn
from cpbl.ingest.splits_calc import VENUE_OFFICIAL

router = APIRouter()

DATA_FROM_YEAR = 2018        # 逐場歸因下限（gamelog/livelog 起始年）
MIN_SEASON_GAMES = 30        # 單季低樣本門檻（場）
MIN_POOLED_GAMES = 60        # 跨季合併低樣本門檻（場）
MIN_VENUE_PA = 100           # 打者生涯在該球場最低 PA
MIN_VENUE_OUTS = 90          # 投手生涯在該球場最低出局數（=30 IP）

FACTOR_STATS = ("r", "hr", "xbh", "h", "bb", "so")

# games.venue 歷史別名 → 現行短名（同座球場；splits 端對映見 splits_calc）
_NORM_VENUE = ("CASE g.venue WHEN '桃園' THEN '樂天桃園' "
               "WHEN '亞太副場' THEN '亞太副' ELSE g.venue END")

# 每「隊-場」一列（每場 2 列）：得分自 games、打擊事件自 gamelog 合計。
# tv=隊×季×球場小計、ty=隊×季總計；expected 由 (ty−tv)/(n_else) 場均 × tv.n 還原，
# 等價於逐列 lateral 但 O(隊×球場) 而非 O(列²)。
_FACTORS_SQL = f"""
WITH gt AS (
    SELECT g.year, {_NORM_VENUE} AS venue, t.team, t.r::numeric AS r,
           COALESCE(bg.hr, 0)::numeric AS hr, COALESCE(bg.xbh, 0)::numeric AS xbh,
           COALESCE(bg.h, 0)::numeric AS h, COALESCE(bg.bb, 0)::numeric AS bb,
           COALESCE(bg.so, 0)::numeric AS so
    FROM cpbl.games g
    CROSS JOIN LATERAL (VALUES
        (g.home_team_code, g.home_score, '2'),
        (g.away_team_code, g.away_score, '1')) AS t(team, r, vht)
    LEFT JOIN LATERAL (
        SELECT sum(b.home_runs) AS hr, sum(b.doubles + b.triples) AS xbh,
               sum(b.hits) AS h, sum(b.bb) AS bb, sum(b.so) AS so
        FROM cpbl.batting_gamelog b
        WHERE b.year = g.year AND b.kind_code = g.kind_code
          AND b.game_sno = g.game_sno AND b.visiting_home_type = t.vht
    ) bg ON true
    WHERE g.kind_code = 'A' AND g.year BETWEEN %(fy)s AND %(ty)s
      AND g.home_score + g.away_score > 0
),
tv AS (
    SELECT year, team, venue, count(*) AS n,
           sum(r) AS r, sum(hr) AS hr, sum(xbh) AS xbh,
           sum(h) AS h, sum(bb) AS bb, sum(so) AS so
    FROM gt GROUP BY 1, 2, 3
),
ty AS (
    SELECT year, team, sum(n) AS n,
           sum(r) AS r, sum(hr) AS hr, sum(xbh) AS xbh,
           sum(h) AS h, sum(bb) AS bb, sum(so) AS so
    FROM tv GROUP BY 1, 2
)
SELECT tv.year, tv.team, tv.n,
       tv.r, tv.hr, tv.xbh, tv.h, tv.bb, tv.so,
       ty.n - tv.n AS n_else,
       ty.r - tv.r AS r_else, ty.hr - tv.hr AS hr_else,
       ty.xbh - tv.xbh AS xbh_else, ty.h - tv.h AS h_else,
       ty.bb - tv.bb AS bb_else, ty.so - tv.so AS so_else
FROM tv JOIN ty USING (year, team)
WHERE tv.venue = %(venue)s
ORDER BY tv.year, tv.team
"""

# 球場打擊環境：splits 球場 family（item_group_code='9'）全選手合計。
# item_name 過濾為可選（帶 → 單一球場；不帶 → 全球場＝聯盟基準）。
_VENUE_ENV_SQL = """
SELECT b.year,
       sum(b.plate_appearances) AS pa, sum(b.at_bats) AS ab, sum(b.hits) AS h,
       sum(b.home_runs) AS hr, sum(b.doubles) AS d2, sum(b.triples) AS d3,
       sum(b.total_bases) AS tb, sum(b.bb) AS bb, sum(b.hbp) AS hbp,
       sum(b.so) AS so, sum(b.sac_fly) AS sf,
       sum(b.ground_outs) AS go, sum(b.fly_outs) AS fo
FROM cpbl.batting_splits b
WHERE b.kind_code = 'A' AND b.item_group_code = '9'
  AND b.year BETWEEN %(fy)s AND %(ty)s {item_filter}
GROUP BY b.year ORDER BY b.year
"""

# 選手生涯（官方 9999，涵蓋 2018 前）在該球場 vs 自身生涯總體（主客 family 合計）
_BAT_EXTREME_SQL = """
WITH v AS (
    SELECT acnt, plate_appearances AS pa, home_runs AS hr, avg, ops
    FROM cpbl.batting_splits
    WHERE year = 9999 AND kind_code = 'A' AND item_group_code = '9'
      AND item_name = %(item)s AND plate_appearances >= %(min_pa)s
),
tot AS (
    SELECT acnt, sum(plate_appearances) AS pa, sum(at_bats) AS ab, sum(hits) AS h,
           sum(total_bases) AS tb, sum(bb) AS bb, sum(hbp) AS hbp, sum(sac_fly) AS sf
    FROM cpbl.batting_splits
    WHERE year = 9999 AND kind_code = 'A' AND item_group_code = '1'
    GROUP BY acnt
)
SELECT v.acnt, p.name, v.pa, v.hr, v.avg, v.ops,
       tot.pa AS c_pa, tot.ab AS c_ab, tot.h AS c_h,
       tot.tb AS c_tb, tot.bb AS c_bb, tot.hbp AS c_hbp, tot.sf AS c_sf
FROM v JOIN tot USING (acnt) JOIN cpbl.players p ON p.id = v.acnt
"""

_PIT_EXTREME_SQL = """
WITH v AS (
    SELECT acnt, inning_pitched_cnt * 3 + inning_pitched_div3 AS outs,
           plate_appearances AS bf, so, earned_runs AS er
    FROM cpbl.pitching_splits
    WHERE year = 9999 AND kind_code = 'A' AND item_group_code = '10'
      AND item_name = %(item)s
      AND inning_pitched_cnt * 3 + inning_pitched_div3 >= %(min_outs)s
),
tot AS (
    SELECT acnt, sum(inning_pitched_cnt * 3 + inning_pitched_div3) AS outs,
           sum(earned_runs) AS er
    FROM cpbl.pitching_splits
    WHERE year = 9999 AND kind_code = 'A' AND item_group_code = '1'
    GROUP BY acnt
)
SELECT v.acnt, p.name, v.outs, v.bf, v.so, v.er,
       tot.outs AS c_outs, tot.er AS c_er
FROM v JOIN tot USING (acnt) JOIN cpbl.players p ON p.id = v.acnt
"""


def _rt(num: float, den: float, nd: int = 3) -> float | None:
    return round(num / den, nd) if den else None


def _aggregate_factors(rows: list[tuple]) -> dict[str, Any]:
    """把 _FACTORS_SQL 的隊×季小計聚合成逐季＋合併 PF。純函式（供無 DB 測試）。

    每列：(year, team, n, r..so ×6, n_else, r_else..so_else ×6)。
    expected 貢獻 = n × stat_else / n_else；n_else=0（該隊該季只在此場打）無法估
    基準 → 整隊-季列排除並記 excluded_team_games，不硬湊。
    """
    seasons: dict[int, dict[str, float]] = {}
    excluded = 0
    for row in rows:
        # SQL sum() 回 numeric（psycopg → Decimal），統一轉 float/int 再算
        year, _team, n = row[0], row[1], int(row[2])
        obs = dict(zip(FACTOR_STATS, row[3:9], strict=True))
        n_else = int(row[9])
        els = dict(zip(FACTOR_STATS, row[10:16], strict=True))
        s = seasons.setdefault(year, {"team_games": 0.0, **{f"obs_{k}": 0.0 for k in FACTOR_STATS},
                                      **{f"exp_{k}": 0.0 for k in FACTOR_STATS}})
        if not n_else:
            excluded += n
            continue
        s["team_games"] += n
        for k in FACTOR_STATS:
            s[f"obs_{k}"] += float(obs[k])
            s[f"exp_{k}"] += n * float(els[k]) / n_else
    out_seasons = []
    pooled = {"games": 0.0, **{f"obs_{k}": 0.0 for k in FACTOR_STATS},
              **{f"exp_{k}": 0.0 for k in FACTOR_STATS}}
    for year in sorted(seasons):
        s = seasons[year]
        games = s["team_games"] / 2   # 每場 2 隊列
        entry: dict[str, Any] = {"year": year, "games": round(games, 1),
                                 "low_sample": games < MIN_SEASON_GAMES, "factors": {}}
        for k in FACTOR_STATS:
            entry["factors"][k] = {"observed": round(s[f"obs_{k}"], 1),
                                   "expected": round(s[f"exp_{k}"], 1),
                                   "pf": _rt(s[f"obs_{k}"], s[f"exp_{k}"])}
            pooled[f"obs_{k}"] += s[f"obs_{k}"]
            pooled[f"exp_{k}"] += s[f"exp_{k}"]
        pooled["games"] += games
        out_seasons.append(entry)
    pooled_out: dict[str, Any] = {"games": round(pooled["games"], 1),
                                  "low_sample": pooled["games"] < MIN_POOLED_GAMES,
                                  "factors": {}}
    for k in FACTOR_STATS:
        pooled_out["factors"][k] = {"observed": round(pooled[f"obs_{k}"], 1),
                                    "expected": round(pooled[f"exp_{k}"], 1),
                                    "pf": _rt(pooled[f"obs_{k}"], pooled[f"exp_{k}"])}
    return {"seasons": out_seasons, "pooled": pooled_out,
            "excluded_team_games": excluded}


def _canon(venue: str) -> str:
    """歷史別名 → 現行短名；未知球場原樣（由查無資料自然回空）。"""
    return {"桃園": "樂天桃園", "亞太副場": "亞太副"}.get(venue, venue)


@router.get("/api/v1/venues/{venue}/factors")
def venue_factors(venue: str,
                  from_year: int = Query(DATA_FROM_YEAR, ge=DATA_FROM_YEAR),
                  to_year: int = Query(DEFAULT_SEASON)) -> dict:
    """球場 park factor（主客對照法）：R/HR/XBH/H/BB/SO 逐季＋合併。

    PF>1＝該球場放大該事件。一律附 games 樣本與 low_sample 旗標；
    資料自 2018 起（逐場歸因下限），一軍例行賽（kind A）。
    """
    v = _canon(venue)
    with conn() as c:
        rows = c.execute(_FACTORS_SQL, {"fy": from_year, "ty": to_year,
                                        "venue": v}).fetchall()
    if not rows:
        raise HTTPException(404, f"查無球場 {venue}（{from_year}–{to_year} 無一軍場次）")
    agg = _aggregate_factors(rows)
    return {"venue": v, "kind_code": "A", "from_year": from_year, "to_year": to_year,
            "method": "matched-team",
            "method_note": ("主客對照法：期望值＝同季各隊在其他球場的場均，"
                            "控制球隊組成；PF＝實際/期望。樣本小心解讀。"),
            "data_floor_note": f"逐場資料自 {DATA_FROM_YEAR} 年起，更早年份無法歸因球場。",
            **agg}


@router.get("/api/v1/venues/{venue}/stats")
def venue_stats(venue: str,
                from_year: int = Query(DATA_FROM_YEAR, ge=DATA_FROM_YEAR),
                to_year: int = Query(DEFAULT_SEASON)) -> dict:
    """球場打擊環境逐年：AVG/OBP/SLG/OPS、HR/SO/BB 率、滾飛出局比 GO/AO＋聯盟同年基準。

    來源＝splits 球場 family 全選手合計（2018+ 重算；kind A）。
    GO/AO 為官方口徑「滾地/飛球型非安打擊球」比，非全擊球 GB/FB。
    """
    item = VENUE_OFFICIAL.get(_canon(venue), _canon(venue))
    params = {"fy": from_year, "ty": to_year, "item": item}
    with conn() as c:
        vr = c.execute(_VENUE_ENV_SQL.format(item_filter="AND b.item_name = %(item)s"),
                       params).fetchall()
        lg = c.execute(_VENUE_ENV_SQL.format(item_filter=""), params).fetchall()
    if not vr:
        raise HTTPException(404, f"查無球場 {venue} 的分項資料")

    def _line(r: tuple) -> dict:
        (year, pa, ab, h, hr, d2, d3, tb, bb, hbp, so, sf, go, fo) = r
        obp_den = (ab or 0) + (bb or 0) + (hbp or 0) + (sf or 0)
        return {"year": year, "pa": pa, "ab": ab, "h": h, "hr": hr,
                "doubles": d2, "triples": d3,
                "avg": _rt(h or 0, ab or 0), "obp": _rt((h or 0) + (bb or 0) + (hbp or 0), obp_den),
                "slg": _rt(tb or 0, ab or 0),
                "ops": (_rt((h or 0) + (bb or 0) + (hbp or 0), obp_den, 4) or 0)
                       + (_rt(tb or 0, ab or 0, 4) or 0) if ab else None,
                "hr_pct": _rt(100 * (hr or 0), pa or 0, 1),
                "so_pct": _rt(100 * (so or 0), pa or 0, 1),
                "bb_pct": _rt(100 * (bb or 0), pa or 0, 1),
                "go": go, "fo": fo, "go_ao": _rt(go or 0, fo or 0, 2)}

    return {"venue": _canon(venue), "item_name": item, "kind_code": "A",
            "seasons": [_line(r) for r in vr],
            "league": [_line(r) for r in lg],
            "note": ("GO/AO＝滾地/飛球型非安打擊球比（官方口徑，含失誤上壘與犧打）；"
                     "聯盟列＝同年全球場合計，供對照。")}


@router.get("/api/v1/venues/{venue}/players")
def venue_players(venue: str, role: str = Query("batting", pattern="^(batting|pitching)$"),
                  min_pa: int = Query(MIN_VENUE_PA, ge=30),
                  min_outs: int = Query(MIN_VENUE_OUTS, ge=30),
                  limit: int = Query(8, ge=1, le=30)) -> dict:
    """在該球場生涯表現與自身生涯基準差距最大的選手（兩端各 limit 名）。

    資料＝官方生涯分項（year=9999，涵蓋 2018 以前）。打者比 OPS 差、投手比 ERA 差；
    一律附球場樣本（PA/IP）與生涯基準，差距為描述性統計、非能力推論。
    """
    item = VENUE_OFFICIAL.get(_canon(venue), _canon(venue))
    with conn() as c:
        if role == "batting":
            rows = c.execute(_BAT_EXTREME_SQL, {"item": item, "min_pa": min_pa}).fetchall()
        else:
            rows = c.execute(_PIT_EXTREME_SQL, {"item": item, "min_outs": min_outs}).fetchall()

    items = []
    if role == "batting":
        for (acnt, name, pa, hr, avg, ops,
             c_pa, c_ab, c_h, c_tb, c_bb, c_hbp, c_sf) in rows:
            den = (c_ab or 0) + (c_bb or 0) + (c_hbp or 0) + (c_sf or 0)
            c_obp = _rt((c_h or 0) + (c_bb or 0) + (c_hbp or 0), den, 4)
            c_slg = _rt(c_tb or 0, c_ab or 0, 4)
            if ops is None or c_obp is None or c_slg is None:
                continue
            c_ops = round(c_obp + c_slg, 4)
            items.append({"player_id": acnt, "name": name,
                          "venue_pa": pa, "venue_avg": avg, "venue_ops": ops,
                          "venue_hr": hr,
                          "career_pa": c_pa, "career_ops": c_ops,
                          "delta_ops": round(ops - c_ops, 4)})
        items.sort(key=lambda x: -x["delta_ops"])
    else:
        for (acnt, name, outs, bf, so, er, c_outs, c_er) in rows:
            if not outs or not c_outs:
                continue
            era = _rt((er or 0) * 27, outs, 2)
            c_era = _rt((c_er or 0) * 27, c_outs, 2)
            items.append({"player_id": acnt, "name": name,
                          "venue_ip": round(outs / 3, 1), "venue_era": era,
                          "venue_k_pct": _rt(100 * (so or 0), bf or 0, 1),
                          "career_ip": round(c_outs / 3, 1), "career_era": c_era,
                          "delta_era": round(era - c_era, 2)})
        items.sort(key=lambda x: x["delta_era"])   # 越負＝該場防禦率越好

    return {"venue": _canon(venue), "item_name": item, "role": role,
            "thresholds": {"min_pa": min_pa, "min_outs": min_outs},
            "best": items[:limit], "worst": items[::-1][:limit],
            "note": ("生涯口徑（官方分項 year=9999，含 2018 以前）。差距＝該球場減自身生涯，"
                     "描述性統計；樣本以 PA/IP 欄自行檢視。")}
