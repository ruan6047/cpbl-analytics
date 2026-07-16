"""投打對決查詢的資料範圍、聚合與排序規則。"""

from __future__ import annotations

import time as _time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from cpbl.models.matchup_insights import (
    _WOBA_WEIGHTS,
    Hyperparameters,
    PairContext,
    PairKey,
    PairSample,
    WobaLine,
    estimate_hyperparameters,
    merge_lines,
    pair_context,
    per_opportunity_variance,
    woba_line,
)

CAREER_YEAR = 9999


@dataclass(frozen=True)
class MatchupScope:
    name: str
    from_year: int
    to_year: int
    source: str


def resolve_matchup_scope(
    scope: str,
    season: int,
    from_year: int | None,
    to_year: int | None,
) -> MatchupScope:
    """把 API 範圍轉成互斥年度條件；年度查詢永不偷用 9999 生涯列。"""
    if scope == "career":
        if from_year is not None or to_year is not None:
            raise ValueError("career scope 不接受年度範圍")
        return MatchupScope(scope, CAREER_YEAR, CAREER_YEAR, "official_career")
    if scope == "season":
        if from_year is not None or to_year is not None:
            raise ValueError("season scope 不接受 from_year 或 to_year")
        if season >= CAREER_YEAR:
            raise ValueError("season 不可使用保留的生涯年度 9999")
        return MatchupScope(scope, season, season, "annual")
    if scope != "range":
        raise ValueError(f"不支援的資料範圍：{scope}")
    if from_year is None or to_year is None:
        raise ValueError("range scope 必須同時提供 from_year 與 to_year")
    if from_year > to_year:
        raise ValueError("from_year 不可大於 to_year")
    if to_year >= CAREER_YEAR:
        raise ValueError("range 不可包含保留的生涯年度 9999")
    return MatchupScope(scope, from_year, to_year, "annual_aggregate")


_COUNT_FIELDS = (
    "plate_appearances",
    "at_bats",
    "hits",
    "rbi",
    "singles",
    "doubles",
    "triples",
    "home_runs",
    "total_bases",
    "sac_hit",
    "sac_fly",
    "bb",
    "ibb",
    "hbp",
    "so",
    "ground_out",
    "fly_out",
)


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def aggregate_matchup_rows(
    rows: Iterable[dict[str, Any]],
    group_keys: tuple[str, ...] = ("opp_id",),
) -> list[dict[str, Any]]:
    """先加總原始計數再重算 rate，避免直接平均逐年 AVG／OPS。"""
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key) for key in group_keys)].append(row)

    items: list[dict[str, Any]] = []
    for members in grouped.values():
        ordered = sorted(members, key=lambda row: row.get("year") or 0)
        latest = ordered[-1]
        item = {key: latest.get(key) for key in group_keys}
        for field in (
            "opp_name",
            "opp_team_code",
            "opp_team",
            "hitter_name",
            "pitcher_name",
            "hitter_team_code",
            "pitcher_team_code",
        ):
            if field in latest:
                item[field] = latest.get(field)
        for field in _COUNT_FIELDS:
            item[field] = sum((row.get(field) or 0) for row in members)

        ab = item["at_bats"]
        hits = item["hits"]
        bb = item["bb"]
        hbp = item["hbp"]
        sf = item["sac_fly"]
        item["avg"] = _rate(hits, ab)
        item["obp"] = _rate(hits + bb + hbp, ab + bb + hbp + sf)
        item["slg"] = _rate(item["total_bases"], ab)
        item["ops"] = (
            round(item["obp"] + item["slg"], 4)
            if item["obp"] is not None and item["slg"] is not None
            else None
        )
        item["source_rows"] = len(members)
        item["from_year"] = ordered[0].get("year")
        item["to_year"] = latest.get("year")
        item["goao"] = _rate(item["ground_out"], item["fly_out"])
        # 官網未提供跨年可加總的比例分子／分母；多列時不可平均百分比。
        for field in (
            "strike_pct",
            "ball_pct",
            "swing_pct",
            "first_pitch_swing_pct",
            "whiff_pct",
            "gb_pct",
            "ld_pct",
            "fb_pct",
        ):
            item[field] = latest.get(field) if len(members) == 1 else None
        items.append(item)
    return items


_SORT_COLUMNS = {
    "plate_appearances": "plate_appearances",
    "avg": "avg",
    "ops": "ops",
    "home_runs": "home_runs",
    "so": "so",
    "recent_year": "to_year",
}


def sort_matchup_items(
    items: Iterable[dict[str, Any]],
    sort: str,
    order: str,
) -> list[dict[str, Any]]:
    """以固定欄位排序聚合結果；None 無論方向一律排最後。"""
    column = _SORT_COLUMNS.get(sort)
    if column is None:
        raise ValueError(f"不支援的排序欄位：{sort}")
    if order not in {"asc", "desc"}:
        raise ValueError(f"不支援的排序方向：{order}")
    present, missing = [], []
    for item in items:
        (missing if item.get(column) is None else present).append(item)
    present.sort(key=lambda item: item.get("opp_name") or "")
    present.sort(key=lambda item: item[column], reverse=order == "desc")
    missing.sort(key=lambda item: item.get("opp_name") or "")
    return present + missing


# ───────────────────── ML-MATCHUP1：洞察用官方 baseline universe ─────────────────────
# 審核紅線：baseline 與 league_mean 不得取自對戰爬蟲子集（只含本季登錄打者，母體
# 隨名單漂移）。改由**官方完整季彙總**（batting_seasons/pitching_seasons + current）
# 計算，涵蓋全史 933 打者／1242 投手、可由官方數字驗證。對戰爬蟲樣本只提供「該配對
# 的觀察 rate」與「主角覆蓋率」；覆蓋不足時 fail-closed，不輸出方向性結論。
#
# 投手官方季表只有總安打 h（無 1B/2B/3B 細分），以聯盟非全壘打長打比例拆分（HR 精確、
# 長打分佈屬 BABIP 噪音，用聯盟比例是可驗證近似）。投手 wOBA 分母 ≈ BF − IBB。

_CAREER_BOUNDS = (1990, 2026)
_UNIVERSE_TTL_SECONDS = 3600
_universe_cache: dict[tuple[str, int, int], tuple[float, InsightUniverse]] = {}

_BATTING_OFFICIAL_SQL = """
WITH src AS (
  SELECT player_id, year AS yr, ab, h, b2, b3, hr, bb, ibb, hbp, sf
  FROM cpbl.batting_seasons
  UNION ALL
  SELECT player_id, 2026 AS yr, ab, h, b2, b3, hr, bb, ibb, hbp, sf
  FROM cpbl.batting_current
)
SELECT player_id, sum(ab), sum(h), sum(b2), sum(b3), sum(hr),
       sum(bb), sum(ibb), sum(hbp), sum(sf)
FROM src WHERE yr BETWEEN %(lo)s AND %(hi)s GROUP BY player_id
"""

_PITCHING_OFFICIAL_SQL = """
WITH src AS (
  SELECT player_id, year AS yr, bf, h, hr, bb, ibb, hbp
  FROM cpbl.pitching_seasons
  UNION ALL
  SELECT player_id, 2026 AS yr, pa AS bf, h, hr, bb, ibb, hbp
  FROM cpbl.pitching_current WHERE year = 2026
)
SELECT player_id, sum(bf), sum(h), sum(hr), sum(bb), sum(ibb), sum(hbp)
FROM src WHERE yr BETWEEN %(lo)s AND %(hi)s GROUP BY player_id
"""

_MATCHUP_PAIR_SQL = """
SELECT hitter_acnt, pitcher_acnt,
       sum(at_bats), sum(singles), sum(doubles), sum(triples),
       sum(home_runs), sum(bb), sum(ibb), sum(hbp), sum(sac_fly)
FROM cpbl.batter_pitcher_matchups
WHERE kind_code=%(kind)s AND year BETWEEN %(from_year)s AND %(to_year)s
GROUP BY hitter_acnt, pitcher_acnt
"""

_PAIR_EVENT_COLUMNS = (
    "at_bats", "singles", "doubles", "triples", "home_runs",
    "bb", "ibb", "hbp", "sac_fly",
)


@dataclass(frozen=True)
class InsightUniverse:
    """單一 (kind, 年度範圍) 的洞察母體。

    baseline 與 league_mean 來自官方完整季表（可驗證）；pairs／contexts 來自對戰
    爬蟲樣本（contexts 為 leave-pair-out 期望與剩餘機會數）；hitter_opps／
    pitcher_opps 為官方生涯機會數（覆蓋率分母）。hyper=None 代表 tau² 無法
    可靠估計（可用配對不足），呼叫端必須 fail-closed，不得輸出方向性排行。
    """

    bat_league_mean: float
    pit_league_mean: float
    sigma2: float
    hitter_baselines: dict[str, WobaLine]
    pitcher_baselines: dict[str, WobaLine]
    hitter_opps: dict[str, int]
    pitcher_opps: dict[str, int]
    pairs: tuple[PairSample, ...]
    contexts: dict[PairKey, PairContext]
    hyper: Hyperparameters | None


def _batter_line(row: tuple) -> WobaLine:
    _pid, ab, h, b2, b3, hr, bb, ibb, hbp, sf = (int(v or 0) for v in row)
    b1 = max(h - b2 - b3 - hr, 0)
    return woba_line({
        "at_bats": ab, "singles": b1, "doubles": b2, "triples": b3,
        "home_runs": hr, "bb": bb, "ibb": ibb, "hbp": hbp, "sac_fly": sf,
    })


def _league_hit_split(batter_rows: list[tuple]) -> tuple[float, float, float]:
    """聯盟非全壘打安打的 1B:2B:3B 比例，用於拆分投手總安打。"""
    b1 = b2 = b3 = 0
    for row in batter_rows:
        _pid, _ab, h, d2, d3, hr, *_ = (int(v or 0) for v in row)
        b1 += max(h - d2 - d3 - hr, 0)
        b2 += d2
        b3 += d3
    total = b1 + b2 + b3
    if total <= 0:
        return 1.0, 0.0, 0.0
    return b1 / total, b2 / total, b3 / total


def _pitcher_line(row: tuple, split: tuple[float, float, float]) -> WobaLine:
    _pid, bf, h, hr, bb, ibb, hbp = (int(v or 0) for v in row)
    nonhr = max(h - hr, 0)
    p1, p2, p3 = split
    weighted = (
        _WOBA_WEIGHTS["singles"] * nonhr * p1
        + _WOBA_WEIGHTS["doubles"] * nonhr * p2
        + _WOBA_WEIGHTS["triples"] * nonhr * p3
        + _WOBA_WEIGHTS["home_runs"] * hr
        + _WOBA_WEIGHTS["ubb"] * max(bb - ibb, 0)
        + _WOBA_WEIGHTS["hbp"] * hbp
    )
    opportunities = max(bf - ibb, 0)  # 近似 wOBA 分母（排除故意四壞）
    return WobaLine(weighted, opportunities)


def _build_universe(
    batter_rows: list[tuple], pitcher_rows: list[tuple], pair_rows: list[tuple]
) -> InsightUniverse:
    if not batter_rows or not pitcher_rows:
        raise ValueError("官方 baseline 母體為空：該範圍無官方季彙總")
    split = _league_hit_split(batter_rows)

    hitter_baselines = {
        row[0]: line
        for row in batter_rows
        if (line := _batter_line(row)).opportunities > 0
    }
    pitcher_baselines = {
        row[0]: line
        for row in pitcher_rows
        if (line := _pitcher_line(row, split)).opportunities > 0
    }
    bat_league = merge_lines(hitter_baselines.values())
    pit_league = merge_lines(pitcher_baselines.values())
    bat_league_mean = bat_league.weighted_sum / bat_league.opportunities
    pit_league_mean = pit_league.weighted_sum / pit_league.opportunities

    # sigma²：聯盟每機會 wOBA 值變異，取自官方打者事件分布（完整可驗證）。
    event_totals: dict[str, int] = defaultdict(int)
    for row in batter_rows:
        _pid, ab, h, b2, b3, hr, bb, ibb, hbp, sf = (int(v or 0) for v in row)
        event_totals["singles"] += max(h - b2 - b3 - hr, 0)
        event_totals["doubles"] += b2
        event_totals["triples"] += b3
        event_totals["home_runs"] += hr
        event_totals["ubb"] += max(bb - ibb, 0)
        event_totals["hbp"] += hbp
    sigma2 = per_opportunity_variance(bat_league, event_totals)

    hitter_opps = {pid: line.opportunities for pid, line in hitter_baselines.items()}
    pitcher_opps = {pid: line.opportunities for pid, line in pitcher_baselines.items()}

    pairs: list[PairSample] = []
    contexts: dict[PairKey, PairContext] = {}
    for row in pair_rows:
        hitter, pitcher, *counts = row
        line = woba_line(dict(zip(_PAIR_EVENT_COLUMNS, counts, strict=True)))
        if line.opportunities <= 0:
            continue
        pairs.append(PairSample(hitter_id=hitter, pitcher_id=pitcher, line=line))
        h_base = hitter_baselines.get(hitter)
        p_base = pitcher_baselines.get(pitcher)
        if h_base is None or p_base is None:
            continue
        ctx = pair_context(
            line,
            h_base,
            p_base,
            bat_league_mean=bat_league_mean,
            pit_league_mean=pit_league_mean,
        )
        if ctx is not None:
            contexts[(hitter, pitcher)] = ctx

    try:
        hyper: Hyperparameters | None = estimate_hyperparameters(
            pairs, contexts=contexts, sigma2=sigma2
        )
    except ValueError:
        # 可用配對不足、tau² 不可靠估計：hyper=None，呼叫端必須 fail-closed，
        # 嚴禁退回任意常數先驗（第二輪審核 P1-2：tau²=sigma² 等效先驗僅 1 機會，
        # 會讓 1 PA 對手拿到 0.99 credibility）。
        hyper = None

    return InsightUniverse(
        bat_league_mean=bat_league_mean,
        pit_league_mean=pit_league_mean,
        sigma2=sigma2,
        hitter_baselines=hitter_baselines,
        pitcher_baselines=pitcher_baselines,
        hitter_opps=hitter_opps,
        pitcher_opps=pitcher_opps,
        pairs=tuple(pairs),
        contexts=contexts,
        hyper=hyper,
    )


def load_insight_universe(
    cur: Any, kind_code: str, from_year: int, to_year: int
) -> InsightUniverse:
    """讀取（或重用快取的）洞察母體；baseline 取官方完整季表，scope 邊界互斥。"""
    key = (kind_code, from_year, to_year)
    cached = _universe_cache.get(key)
    now = _time.monotonic()
    if cached and now - cached[0] < _UNIVERSE_TTL_SECONDS:
        return cached[1]
    lo, hi = _CAREER_BOUNDS if from_year >= 9999 else (from_year, to_year)
    cur.execute(_BATTING_OFFICIAL_SQL, {"lo": lo, "hi": hi})
    batter_rows = cur.fetchall()
    cur.execute(_PITCHING_OFFICIAL_SQL, {"lo": lo, "hi": hi})
    pitcher_rows = cur.fetchall()
    cur.execute(
        _MATCHUP_PAIR_SQL,
        {"kind": kind_code, "from_year": from_year, "to_year": to_year},
    )
    pair_rows = cur.fetchall()
    universe = _build_universe(batter_rows, pitcher_rows, pair_rows)
    _universe_cache[key] = (now, universe)
    if len(_universe_cache) > 16:
        oldest = min(_universe_cache, key=lambda k: _universe_cache[k][0])
        _universe_cache.pop(oldest, None)
    return universe
