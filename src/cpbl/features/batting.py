"""打擊成績預測的特徵工程。

從 cpbl.batting_seasons 建出「以前 1~3 季 + 年齡」預測「目標季 rate stat」的
訓練集。處理：同年多隊合併、缺年（非連續球季）、年齡計算、聯盟年度均值。

預測目標為 rate stat（AVG / OBP / SLG / OPS），不含計數型（需另建上場時間模型）。
"""

from __future__ import annotations

from dataclasses import dataclass

from cpbl.db import conn

# 預測目標季最低 PA（過濾掉樣本太少的雜訊球員）
MIN_TARGET_PA = 100
# 作為特徵的前一季最低 AB（至少要有一季可參考）
MIN_PRIOR_AB = 30

# 各 rate stat 的 (分子, 分母) 計算方式
STAT_DEFS = {
    "avg": lambda s: (s["h"], s["ab"]),
    "obp": lambda s: (s["h"] + s["bb"] + s["hbp"], s["ab"] + s["bb"] + s["hbp"] + s["sf"]),
    "slg": lambda s: (s["tb"], s["ab"]),
}
HEADLINE_STATS = ["avg", "obp", "slg", "ops"]  # ops = obp + slg


@dataclass
class SeasonAgg:
    pa: int
    ab: int
    h: int
    b2: int
    b3: int
    hr: int
    tb: int
    bb: int
    hbp: int
    sf: int
    so: int


def _rate(num: float, den: float) -> float | None:
    return num / den if den and den > 0 else None


def _safe(v) -> int:
    return int(v) if v is not None else 0


def _load_aggregates() -> tuple[dict[tuple[str, int], SeasonAgg], dict[str, int]]:
    """回傳 {(player_id, year): SeasonAgg} 與 {player_id: birth_year}。"""
    aggs: dict[tuple[str, int], SeasonAgg] = {}
    births: dict[str, int] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT player_id, year,
                   SUM(pa), SUM(ab), SUM(h), SUM(b2), SUM(b3), SUM(hr),
                   SUM(tb), SUM(bb), SUM(hbp), SUM(sf), SUM(so)
            FROM cpbl.batting_seasons
            GROUP BY player_id, year
            """
        )
        for row in cur.fetchall():
            pid, year = row[0], row[1]
            aggs[(pid, year)] = SeasonAgg(*[_safe(v) for v in row[2:]])

        cur.execute("SELECT id, EXTRACT(YEAR FROM birthday)::int FROM cpbl.players WHERE birthday IS NOT NULL")
        for pid, by in cur.fetchall():
            births[pid] = by
    return aggs, births


def _league_rates(aggs: dict[tuple[str, int], SeasonAgg]) -> dict[int, dict[str, float]]:
    """每年聯盟整體 rate（regression-to-mean 用）。"""
    by_year: dict[int, list[SeasonAgg]] = {}
    for (_, year), s in aggs.items():
        by_year.setdefault(year, []).append(s)
    out: dict[int, dict[str, float]] = {}
    for year, seasons in by_year.items():
        tot = {k: sum(getattr(s, k) for s in seasons) for k in
               ("pa", "ab", "h", "tb", "bb", "hbp", "sf")}
        lg = {}
        for stat, fn in STAT_DEFS.items():
            num, den = fn(tot)
            lg[stat] = _rate(num, den) or 0.0
        out[year] = lg
    return out


def build_batting_dataset() -> list[dict]:
    """建出訓練列：每列 = 一位球員的一個目標季 + 其前 1~3 季特徵。"""
    aggs, births = _load_aggregates()
    rows: list[dict] = []

    for (pid, year), target in aggs.items():
        if target.pa < MIN_TARGET_PA or target.ab <= 0:
            continue
        prior = [aggs.get((pid, year - k)) for k in (1, 2, 3)]
        if prior[0] is None or prior[0].ab < MIN_PRIOR_AB:
            continue  # 至少要有前一季可參考

        row: dict = {"player_id": pid, "target_year": year}
        row["age"] = (year - births[pid]) if pid in births else None

        # 目標 rate（actual）
        for stat, fn in STAT_DEFS.items():
            num, den = fn(target.__dict__)
            row[f"y_{stat}"] = _rate(num, den)
        row["y_ops"] = (
            (row["y_obp"] or 0) + (row["y_slg"] or 0) if row["y_obp"] and row["y_slg"] else None
        )

        # lag 特徵：前 1~3 季的 rate 與 PA（缺季為 None → ML 視為缺值）
        for i, p in enumerate(prior, start=1):
            row[f"pa_lag{i}"] = p.pa if p else None
            for stat, fn in STAT_DEFS.items():
                if p:
                    num, den = fn(p.__dict__)
                    row[f"{stat}_lag{i}"] = _rate(num, den)
                else:
                    row[f"{stat}_lag{i}"] = None

        # 回歸均值用：前一季的聯盟 rate（避免用到目標季資訊造成洩漏）
        rows.append(row)

    return rows


def get_league_rates() -> dict[int, dict[str, float]]:
    aggs, _ = _load_aggregates()
    return _league_rates(aggs)
