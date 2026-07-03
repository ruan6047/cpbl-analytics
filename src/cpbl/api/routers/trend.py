"""球員時段趨勢：本季逐場滾動與生涯跨年合併。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON, _real_ip
from cpbl.db import conn

router = APIRouter()


@router.get("/api/v1/players/{player_id}/trend")
def player_trend(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query("A"),
) -> dict:
    """逐場趨勢：rate 型用「近 N 場滾動」（累積 rate 會收斂拉平、看不出冷熱手），
    計數型維持累積配速線；另附滾動 OPS+/ERA+（季聯盟基準；100=聯盟均值，一軍才有）。"""
    n_roll = 15  # 滾動視窗場數（rate/OPS+/ERA+ 用；資料充足時最能表現近況）
    r3 = lambda v: round(v, 3) if v is not None else None  # noqa: E731
    with conn() as c:
        cur = c.cursor()
        if role == "batting":
            lg_obp = lg_slg = None
            if kind_code == "A":  # OPS+ 聯盟基準（僅一軍有）
                cur.execute("SELECT sum(ab), sum(h), sum(bb), sum(hbp), sum(sf), sum(tb) "
                            "FROM cpbl.batting_current WHERE year = %s", (season,))
                lab, lh, lbb, lhbp, lsf, ltb = (x or 0 for x in cur.fetchone())
                lg_obp = (lh + lbb + lhbp) / (lab + lbb + lhbp + lsf) if (lab + lbb + lhbp + lsf) else None
                lg_slg = ltb / lab if lab else None
            cur.execute(
                f"""
                SELECT g.game_date,
                    b.hits AS h_c, b.home_runs AS hr_c, b.rbi AS rbi_c,  -- 計數型：逐場值(柱狀)
                    sum(b.at_bats)     OVER roll AS ab_r,
                    sum(b.hits)        OVER roll AS h_r,
                    sum(b.bb)          OVER roll AS bb_r,
                    sum(b.hbp)         OVER roll AS hbp_r,
                    sum(b.sac_fly)     OVER roll AS sf_r,
                    sum(b.total_bases) OVER roll AS tb_r
                FROM cpbl.batting_gamelog b
                JOIN cpbl.games g
                  ON g.year = b.year AND g.kind_code = b.kind_code AND g.game_sno = b.game_sno
                WHERE b.hitter_acnt = %s AND b.year = %s AND b.kind_code = %s
                WINDOW roll AS (ORDER BY g.game_date, b.game_sno
                                ROWS BETWEEN {n_roll - 1} PRECEDING AND CURRENT ROW)
                ORDER BY g.game_date, b.game_sno
                """,
                (player_id, season, kind_code),
            )
            items = []
            for i, (d, h_c, hr_c, rbi_c, ab, h, bb, hbp, sf, tb) in enumerate(cur.fetchall(), 1):
                ab = ab or 0
                pa_ob = ab + (bb or 0) + (hbp or 0) + (sf or 0)
                small = ab < 30  # 滾動樣本太小(早季未滿窗)→ rate 過度波動,不輸出免尖刺
                obp = None if small else (((h or 0) + (bb or 0) + (hbp or 0)) / pa_ob if pa_ob else None)
                slg = None if small else ((tb or 0) / ab if ab else None)
                ops = (obp + slg) if obp is not None and slg is not None else None
                ops_plus = (round(100 * (obp / lg_obp + slg / lg_slg - 1))
                            if obp is not None and slg is not None and lg_obp and lg_slg else None)
                items.append({
                    "name": f"{d.month}/{d.day}", "g": i, "date": d.isoformat(),
                    "avg": None if small else r3(h / ab if ab else None),
                    "obp": r3(obp), "slg": r3(slg), "ops": r3(ops),
                    "ops_plus": ops_plus, "hits": h_c, "home_runs": hr_c, "rbi": rbi_c,
                })
        else:
            lg_era = None
            if kind_code == "A":  # ERA+ 聯盟基準
                cur.execute("SELECT ip, er FROM cpbl.pitching_current WHERE year = %s AND ip IS NOT NULL", (season,))
                lr = cur.fetchall()
                lg_ip = sum(_real_ip(r[0]) for r in lr)
                lg_era = sum(r[1] or 0 for r in lr) * 9 / lg_ip if lg_ip else None
            cur.execute(
                f"""
                SELECT g.game_date,
                    p.so AS so_c, p.hits AS h_c, p.bb AS bb_c,  -- 計數型：單場值(柱狀)
                    sum(p.inning_pitched_cnt)  OVER roll AS ipc,
                    sum(p.inning_pitched_div3) OVER roll AS ip3,
                    sum(p.earned_runs)         OVER roll AS er,
                    sum(p.hits)                OVER roll AS h_r,
                    sum(p.bb)                  OVER roll AS bb_r
                FROM cpbl.pitching_gamelog p
                JOIN cpbl.games g
                  ON g.year = p.year AND g.kind_code = p.kind_code AND g.game_sno = p.game_sno
                WHERE p.pitcher_acnt = %s AND p.year = %s AND p.kind_code = %s
                WINDOW roll AS (ORDER BY g.game_date, p.game_sno
                                ROWS BETWEEN {n_roll - 1} PRECEDING AND CURRENT ROW)
                ORDER BY g.game_date, p.game_sno
                """,
                (player_id, season, kind_code),
            )
            items = []
            for i, (d, so_c, h_c, bb_c, ipc, ip3, er, h_r, bb_r) in enumerate(cur.fetchall(), 1):
                ip = (ipc or 0) + (ip3 or 0) / 3
                small = ip < 10  # 滾動局數太小(早季未滿窗)→ rate 過度波動,不輸出
                era = None if small or not ip else round((er or 0) * 9 / ip, 2)
                whip = None if small or not ip else round(((bb_r or 0) + (h_r or 0)) / ip, 2)
                era_plus = round(100 * lg_era / era) if lg_era and era and era > 0 else None
                items.append({
                    "name": f"{d.month}/{d.day}", "g": i, "date": d.isoformat(),
                    "era": era, "whip": whip, "era_plus": era_plus,
                    "so": so_c, "hits": h_c, "bb": bb_c,
                })
    return {"player_id": player_id, "role": role, "items": items, "roll": n_roll}


@router.get("/api/v1/players/{player_id}/trend-career")
def player_trend_career(
    player_id: str,
    role: str = Query("batting", pattern="^(batting|pitching)$"),
    kind_code: str = Query("A"),
    bucket: str = Query("half", pattern="^(month|half|third|week)$"),
) -> dict:
    """生涯「時段分項」趨勢：把跨年份的同一時段合併為一點（所有 3 月上、3 月下…），
    看選手各時段強弱/是否慢熱、作為下時段參考。bucket 控制粒度：月/半月/旬/週。
    rate=該時段生涯合計率、OPS+/ERA+ 用生涯聯盟基準；計數型=生涯合計（柱狀）。樣本過小之 rate 略。"""
    r3 = lambda v: round(v, 3) if v is not None else None  # noqa: E731
    # 子月份索引 SQL（白名單，非使用者字串直插）+ 標籤
    _SUB = {"month": "0", "half": "((extract(day FROM g.game_date)::int > 15))::int",
            "third": "least((extract(day FROM g.game_date)::int - 1) / 10, 2)",
            "week": "least((extract(day FROM g.game_date)::int - 1) / 7, 4)"}
    sub_sql = _SUB[bucket]

    def _label(m: int, s: int) -> str:
        if bucket == "month":
            return f"{m}月"
        if bucket == "half":
            return f"{m}月{'下' if s else '上'}"
        if bucket == "third":
            return f"{m}月{['上旬', '中旬', '下旬'][s]}"
        return f"{m}月W{s + 1}"
    with conn() as c:
        cur = c.cursor()
        if role == "batting":
            cur.execute("SELECT sum(at_bats), sum(hits), sum(bb), sum(hbp), sum(sac_fly), sum(total_bases) "
                        "FROM cpbl.batting_gamelog WHERE kind_code = %s", (kind_code,))
            lab, lh, lbb, lhbp, lsf, ltb = (x or 0 for x in cur.fetchone())
            lden = lab + lbb + lhbp + lsf
            lg_obp = (lh + lbb + lhbp) / lden if lden else None
            lg_slg = ltb / lab if lab else None
            cur.execute(
                f"""
                SELECT extract(month FROM g.game_date)::int AS m, {sub_sql} AS sub,
                    sum(b.at_bats), sum(b.hits), sum(b.bb), sum(b.hbp), sum(b.sac_fly),
                    sum(b.total_bases), sum(b.home_runs), sum(b.rbi), count(DISTINCT b.year)
                FROM cpbl.batting_gamelog b
                JOIN cpbl.games g ON g.year = b.year AND g.kind_code = b.kind_code AND g.game_sno = b.game_sno
                WHERE b.hitter_acnt = %s AND b.kind_code = %s
                GROUP BY 1, 2 ORDER BY 1, 2
                """,
                (player_id, kind_code),
            )
            items = []
            for m, sub, ab, h, bb, hbp, sf, tb, hr, rbi, yrs in cur.fetchall():
                ab = ab or 0
                den = ab + (bb or 0) + (hbp or 0) + (sf or 0)
                small = ab < 15  # 該時段生涯樣本太小 → rate 不輸出
                obp = None if small else (((h or 0) + (bb or 0) + (hbp or 0)) / den if den else None)
                slg = None if small else ((tb or 0) / ab if ab else None)
                ops = (obp + slg) if obp is not None and slg is not None else None
                ops_plus = (round(100 * (obp / lg_obp + slg / lg_slg - 1))
                            if obp is not None and slg is not None and lg_obp and lg_slg else None)
                items.append({
                    "name": _label(m, sub), "years": yrs,
                    "avg": None if small else r3(h / ab if ab else None),
                    "obp": r3(obp), "slg": r3(slg), "ops": r3(ops), "ops_plus": ops_plus,
                    "hits": h, "home_runs": hr, "rbi": rbi,
                })
        else:
            cur.execute("SELECT sum(inning_pitched_cnt), sum(inning_pitched_div3), sum(earned_runs) "
                        "FROM cpbl.pitching_gamelog WHERE kind_code = %s", (kind_code,))
            lipc, lip3, ler = (x or 0 for x in cur.fetchone())
            lgip = lipc + lip3 / 3
            lg_era = ler * 9 / lgip if lgip else None
            cur.execute(
                f"""
                SELECT extract(month FROM g.game_date)::int AS m, {sub_sql} AS sub,
                    sum(p.inning_pitched_cnt), sum(p.inning_pitched_div3), sum(p.earned_runs),
                    sum(p.so), sum(p.hits), sum(p.bb), count(DISTINCT p.year)
                FROM cpbl.pitching_gamelog p
                JOIN cpbl.games g ON g.year = p.year AND g.kind_code = p.kind_code AND g.game_sno = p.game_sno
                WHERE p.pitcher_acnt = %s AND p.kind_code = %s
                GROUP BY 1, 2 ORDER BY 1, 2
                """,
                (player_id, kind_code),
            )
            items = []
            for m, sub, ipc, ip3, er, so, h, bb, yrs in cur.fetchall():
                ip = (ipc or 0) + (ip3 or 0) / 3
                small = ip < 8  # 該時段生涯局數太小
                era = None if small or not ip else round((er or 0) * 9 / ip, 2)
                whip = None if small or not ip else round(((bb or 0) + (h or 0)) / ip, 2)
                era_plus = round(100 * lg_era / era) if lg_era and era and era > 0 else None
                items.append({
                    "name": _label(m, sub), "years": yrs,
                    "era": era, "whip": whip, "era_plus": era_plus,
                    "so": so, "hits": h, "bb": bb,
                })
    return {"player_id": player_id, "role": role, "items": items}
