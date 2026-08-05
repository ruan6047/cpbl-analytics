"""TEAM-STYLE1 球隊球風軸計算（共用模組；唯讀、描述性）。

軸定義、z-score normalization 與資料載入自 ``scripts/team_style_vectors.py``
抽出（UX-TEAM-STYLE1 設計約束 6「計算單一來源」）：研究腳本與 API 皆 import
本模組，軸計算式以 TEAM-STYLE1 凍結 spec（50c23be；
docs/research/TEAM-STYLE1_RESULTS.md §0）為準，**不得重算、變造或另創口徑**。

程式碼為逐字搬移（等價性以研究腳本重跑 artifact 逐位一致為證），僅函式
可見性改為 public；任何軸定義變更都必須回到研究卡，不在此模組動手。
"""

from __future__ import annotations

import math
from collections import defaultdict

YEAR_FROM = 2018
YEAR_TO = 2026
STABILITY_YEARS = tuple(range(2018, 2026))  # 2026 進行中，排除於穩定性檢定
FRANCHISE_MAP = {"AJK011": "AJL011"}  # Lamigo → 樂天，同一 franchise（預註冊）

AXES = ("speed", "smallball", "power", "discipline", "starter_ip", "pitch_k", "defense")

AXIS_LABELS = {
    "speed": "速度戰",
    "smallball": "短打戰術",
    "power": "長打火力",
    "discipline": "選球紀律",
    "starter_ip": "先發吃局",
    "pitch_k": "三振型投手",
    "defense": "守備效率",
}

BAT_KEYS = ("pa", "ab", "h", "singles", "tb", "sh", "sf", "bb", "hbp", "so", "sb", "cs")
PIT_KEYS = ("outs", "starter_outs", "pa_against", "h_a", "hr_a", "bb_a", "hbp_a", "so_a")


# ---------------------------------------------------------------------------
# 純函式（單元測試對象）
# ---------------------------------------------------------------------------

def zscores(values: list[float]) -> list[float]:
    """季內聯盟 z-score：母體標準差（ddof=0）；std=0 時全 0（spec §0.3）。"""
    n = len(values)
    if n == 0:
        return []
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(var)
    if std == 0:
        return [0.0] * n
    return [(v - mean) / std for v in values]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson 相關係數；任一側零變異或 n<3 回 None。"""
    n = len(xs)
    if n != len(ys) or n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return sxy / math.sqrt(sxx * syy)


def split_half(n_games: int) -> tuple[int, int]:
    """分半切點：前 n//2 場為 H1、其餘為 H2（spec §0.4；奇數場 H2 多一場）。"""
    return n_games // 2, n_games - n_games // 2


def batting_axes_raw(agg: dict[str, int]) -> dict[str, float | None]:
    """打擊側原始軸值（spec §0.2 #1–#4 成分）；分母 0 回 None。"""
    sba_den = agg["singles"] + agg["bb"] + agg["hbp"]
    return {
        "sba_rate": (agg["sb"] + agg["cs"]) / sba_den if sba_den else None,
        "sh_rate": agg["sh"] / agg["pa"] if agg["pa"] else None,
        "iso": (agg["tb"] - agg["h"]) / agg["ab"] if agg["ab"] else None,
        "bb_rate": agg["bb"] / agg["pa"] if agg["pa"] else None,
        "k_rate": agg["so"] / agg["pa"] if agg["pa"] else None,
    }


def pitching_axes_raw(agg: dict[str, int]) -> dict[str, float | None]:
    """投手／守備側原始軸值（spec §0.2 #5–#7）；分母 0 回 None。"""
    bip = agg["pa_against"] - agg["bb_a"] - agg["hbp_a"] - agg["so_a"] - agg["hr_a"]
    return {
        "starter_share": agg["starter_outs"] / agg["outs"] if agg["outs"] else None,
        "kpct": agg["so_a"] / agg["pa_against"] if agg["pa_against"] else None,
        "der": 1 - (agg["h_a"] - agg["hr_a"]) / bip if bip > 0 else None,
    }


def season_axis_z(raw_by_team: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """單一球季（或同季同半）的 7 軸 z 值。

    輸入：team_code → 原始成分 dict（batting_axes_raw ∪ pitching_axes_raw）。
    複合軸 discipline = mean(z(bb_rate), −z(k_rate)) 後再重新 z 化（spec §0.3）。
    """
    teams = sorted(raw_by_team)

    def _z(component: str, negate: bool = False) -> dict[str, float]:
        vals = [raw_by_team[t][component] for t in teams]
        zs = zscores([-v if negate else v for v in vals])
        return dict(zip(teams, zs, strict=True))

    speed = _z("sba_rate")
    smallball = _z("sh_rate")
    power = _z("iso")
    bb_z = _z("bb_rate")
    k_z = _z("k_rate", negate=True)
    disc_mean = [(bb_z[t] + k_z[t]) / 2 for t in teams]
    discipline = dict(zip(teams, zscores(disc_mean), strict=True))
    starter = _z("starter_share")
    pitch_k = _z("kpct")
    defense = _z("der")

    return {
        t: {
            "speed": speed[t], "smallball": smallball[t], "power": power[t],
            "discipline": discipline[t], "starter_ip": starter[t],
            "pitch_k": pitch_k[t], "defense": defense[t],
        }
        for t in teams
    }


def rank_desc(z_by_team: dict[str, float], team: str) -> int:
    """該季某軸的名次（z 由高至低，1 = 最高）。"""
    ordered = sorted(z_by_team.values(), reverse=True)
    return ordered.index(z_by_team[team]) + 1


def aggregate_games(games: list[dict]) -> dict[str, int]:
    """把逐場計數列加總成隊季（或任意場次子集）總計。"""
    keys = BAT_KEYS + PIT_KEYS
    return {k: sum(g.get(k, 0) for g in games) for k in keys}


def raw_axes(agg: dict[str, int]) -> dict[str, float | None]:
    """隊季總計 → 全部原始軸成分（打擊 ∪ 投手）。"""
    return {**batting_axes_raw(agg), **pitching_axes_raw(agg)}


# ---------------------------------------------------------------------------
# 資料載入（唯讀 SELECT）
# ---------------------------------------------------------------------------

def completed_a_filter() -> str:
    # 證據感知完成判準：0:0 真和局需外部完賽證據（DATA-TIE-REMEDY1）。
    from cpbl.completion import completed_games_sql_with_evidence

    return ("g.kind_code = 'A' AND g.year BETWEEN %s AND %s AND "
            f"{completed_games_sql_with_evidence('g')}")


def load_team_games(c) -> dict[tuple[int, str], list[dict]]:
    """每隊每場（打擊＋投手合併）計數；回傳 (year, team_code) → 依日期排序的場列表。"""
    team_expr = ("CASE WHEN x.visiting_home_type = '2' THEN g.home_team_code "
                 "ELSE g.away_team_code END")
    bat_sql = f"""
        SELECT g.year, {team_expr.replace('x.', 'bg.')} AS team_code,
               g.game_sno, g.game_date, g.game_season_code,
               sum(COALESCE(bg.plate_appearances,0)), sum(COALESCE(bg.at_bats,0)),
               sum(COALESCE(bg.hits,0)), sum(COALESCE(bg.singles,0)),
               sum(COALESCE(bg.total_bases,0)), sum(COALESCE(bg.sac_hit,0)),
               sum(COALESCE(bg.sac_fly,0)), sum(COALESCE(bg.bb,0)),
               sum(COALESCE(bg.hbp,0)), sum(COALESCE(bg.so,0)),
               sum(COALESCE(bg.sb,0)), sum(COALESCE(bg.cs,0))
        FROM cpbl.batting_gamelog bg
        JOIN cpbl.games g ON g.year = bg.year AND g.kind_code = bg.kind_code
                         AND g.game_sno = bg.game_sno
        WHERE {completed_a_filter()}
        GROUP BY 1, 2, 3, 4, 5
    """
    pit_sql = f"""
        SELECT g.year, {team_expr.replace('x.', 'pg.')} AS team_code,
               g.game_sno, g.game_date,
               sum(COALESCE(pg.inning_pitched_cnt,0) * 3 + COALESCE(pg.inning_pitched_div3,0)),
               sum(COALESCE(pg.inning_pitched_cnt,0) * 3 + COALESCE(pg.inning_pitched_div3,0))
                   FILTER (WHERE pg.role_type = '先發'),
               sum(COALESCE(pg.plate_appearances,0)), sum(COALESCE(pg.hits,0)),
               sum(COALESCE(pg.home_runs,0)), sum(COALESCE(pg.bb,0)),
               sum(COALESCE(pg.hbp,0)), sum(COALESCE(pg.so,0))
        FROM cpbl.pitching_gamelog pg
        JOIN cpbl.games g ON g.year = pg.year AND g.kind_code = pg.kind_code
                         AND g.game_sno = pg.game_sno
        WHERE {completed_a_filter()}
        GROUP BY 1, 2, 3, 4
    """
    params = (YEAR_FROM, YEAR_TO)
    games: dict[tuple[int, str, int], dict] = {}
    for year, team, sno, gdate, season_code, *vals in c.execute(bat_sql, params).fetchall():
        rec = games.setdefault((year, team, sno), {"game_date": gdate})
        rec["season_code"] = season_code
        rec.update(dict(zip(BAT_KEYS, (int(v) for v in vals), strict=True)))
    for year, team, sno, gdate, *vals in c.execute(pit_sql, params).fetchall():
        rec = games.setdefault((year, team, sno), {"game_date": gdate})
        rec.update(dict(zip(PIT_KEYS, (int(v or 0) for v in vals), strict=True)))

    by_team: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for (year, team, sno), rec in games.items():
        rec["game_sno"] = sno
        by_team[(year, team)].append(rec)
    for recs in by_team.values():
        recs.sort(key=lambda r: (r["game_date"], r["game_sno"]))
    return dict(by_team)


def load_team_names(c) -> dict[tuple[int, str], str]:
    sql = f"""
        SELECT DISTINCT g.year, g.home_team_code, g.home_team_name
        FROM cpbl.games g WHERE {completed_a_filter()}
        UNION
        SELECT DISTINCT g.year, g.away_team_code, g.away_team_name
        FROM cpbl.games g WHERE {completed_a_filter()}
    """
    params = (YEAR_FROM, YEAR_TO)
    return {(y, code): name for y, code, name in c.execute(sql, params + params).fetchall()}
