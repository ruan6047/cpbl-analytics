"""投手成績預測的特徵工程（鏡射 features/batting.py）。

從 cpbl.pitching_seasons 建「前 1~3 季 + 年齡」預測「目標季 rate stat」的訓練集。
處理：同年多隊合併、缺年、年齡、聯盟年度均值、**ip 棒球記法**（.1=⅓、.2=⅔，
先轉出局數 outs 再算 rate——直接把 .1 當十進位會讓所有 rate 偏 ~3-4%）。

預測目標：ERA / WHIP / K9 / BB9（rate；分母統一為 outs，加權/回歸均值在計數層）。
計數型（W/SV 總數）需上場時間模型，不在此範圍。
"""

from __future__ import annotations

from dataclasses import dataclass

from cpbl.db import conn

# 目標季最低出局數（40 IP；rate 噪音門檻）／作為特徵的前一季最低出局數（20 IP）
MIN_TARGET_OUTS = 120
MIN_PRIOR_OUTS = 60

# 各 rate stat 的 (分子, 分母)；分母統一 outs，分子預先乘 27（per 9 局）或 3（per 局）
# 使 rate = num/den 直接等於慣用口徑：era=ER*9/IP、whip=(H+BB)/IP、k9=SO*9/IP。
STAT_DEFS = {
    "era": lambda s: (s["er"] * 27, s["outs"]),
    "whip": lambda s: ((s["h"] + s["bb"]) * 3, s["outs"]),
    "k9": lambda s: (s["so"] * 27, s["outs"]),
    "bb9": lambda s: (s["bb"] * 27, s["outs"]),
}
HEADLINE_STATS = ["era", "whip", "k9", "bb9"]
# 低值為佳的 stat（年齡曲線方向要反轉）
LOWER_BETTER = {"era", "whip", "bb9"}


@dataclass
class SeasonAgg:
    outs: int
    bf: int
    g: int
    gs: int
    h: int
    hr: int
    bb: int
    hbp: int
    so: int
    r: int
    er: int


def _rate(num: float, den: float) -> float | None:
    return num / den if den and den > 0 else None


def _safe(v) -> int:
    return int(v) if v is not None else 0


def ip_to_outs(ip: float | None) -> int:
    """棒球記法局數 → 出局數（123.2 → 371）。"""
    if ip is None:
        return 0
    whole = int(ip)
    frac = round((float(ip) - whole) * 10)
    return whole * 3 + frac


def _load_aggregates() -> tuple[dict[tuple[str, int], SeasonAgg], dict[str, int]]:
    """回傳 {(player_id, year): SeasonAgg} 與 {player_id: birth_year}。

    同年多隊：ip 逐列轉 outs 再加總（先 SUM(ip) 會把兩個 .2 加成 .4 毀掉記法）。
    """
    aggs: dict[tuple[str, int], SeasonAgg] = {}
    births: dict[str, int] = {}
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            """
            SELECT player_id, year, ip, bf, g, gs, h, hr, bb, hbp, so, r, er
            FROM cpbl.pitching_seasons
            """
        )
        for pid, year, ip, *rest in cur.fetchall():
            vals = [ip_to_outs(ip), *[_safe(v) for v in rest]]
            key = (pid, year)
            if key in aggs:
                prev = aggs[key]
                vals = [a + b for a, b in zip(vals, prev.__dict__.values(), strict=True)]
            aggs[key] = SeasonAgg(*vals)

        cur.execute(
            "SELECT id, EXTRACT(YEAR FROM birthday)::int FROM cpbl.players "
            "WHERE birthday IS NOT NULL")
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
               ("outs", "h", "bb", "so", "er")}
        lg = {}
        for stat, fn in STAT_DEFS.items():
            num, den = fn(tot)
            lg[stat] = _rate(num, den) or 0.0
        out[year] = lg
    return out


def build_pitching_dataset() -> list[dict]:
    """訓練列：每列 = 一位投手的一個目標季 + 前 1~3 季特徵。"""
    aggs, births = _load_aggregates()
    rows: list[dict] = []

    for (pid, year), target in aggs.items():
        if target.outs < MIN_TARGET_OUTS:
            continue
        prior = [aggs.get((pid, year - k)) for k in (1, 2, 3)]
        if prior[0] is None or prior[0].outs < MIN_PRIOR_OUTS:
            continue

        row: dict = {"player_id": pid, "target_year": year}
        row["age"] = (year - births[pid]) if pid in births else None

        for stat, fn in STAT_DEFS.items():
            num, den = fn(target.__dict__)
            row[f"y_{stat}"] = _rate(num, den)

        # lag 特徵：rate + outs（上場量）+ 先發比重（角色轉換訊號，LGBM 專用）
        for i, p in enumerate(prior, start=1):
            row[f"outs_lag{i}"] = p.outs if p else None
            row[f"gs_share_lag{i}"] = (p.gs / p.g) if p and p.g else None
            for stat, fn in STAT_DEFS.items():
                if p:
                    num, den = fn(p.__dict__)
                    row[f"{stat}_lag{i}"] = _rate(num, den)
                else:
                    row[f"{stat}_lag{i}"] = None
        rows.append(row)

    return rows
