"""投打對決查詢的資料範圍、聚合與排序規則。"""

from __future__ import annotations

import time as _time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from cpbl.models.matchup_insights import (
    Hyperparameters,
    PairSample,
    WobaLine,
    estimate_hyperparameters,
    merge_lines,
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


# ───────────────────── ML-MATCHUP1：洞察用全域彙總（universe） ─────────────────────
# 天敵候選／優勢對位需要三種聚合：聯盟事件分布（估 sigma²）、逐球員 baseline、
# 逐配對樣本（估 tau² 與收縮）。同一次 GROUP BY 掃描全部取得，並以
# (kind, from, to) 快取（資料日更、API 每日重啟或 TTL 到期即重算）。

_INSIGHT_EVENT_COLUMNS = (
    "at_bats",
    "singles",
    "doubles",
    "triples",
    "home_runs",
    "bb",
    "ibb",
    "hbp",
    "sac_fly",
)

_UNIVERSE_TTL_SECONDS = 3600
_universe_cache: dict[tuple[str, int, int], tuple[float, InsightUniverse]] = {}


@dataclass(frozen=True)
class InsightUniverse:
    """單一 (kind, 年度範圍) 的洞察母體：聯盟均值、球員總量與先驗。"""

    league: WobaLine
    league_mean: float
    hitter_totals: dict[str, WobaLine]
    pitcher_totals: dict[str, WobaLine]
    pairs: tuple[PairSample, ...]
    hyper: Hyperparameters


def _build_universe(rows: list[tuple]) -> InsightUniverse:
    pair_lines: dict[tuple[str, str], WobaLine] = {}
    hitter_lines: dict[str, list[WobaLine]] = defaultdict(list)
    pitcher_lines: dict[str, list[WobaLine]] = defaultdict(list)
    event_totals: dict[str, int] = defaultdict(int)
    for row in rows:
        hitter, pitcher, *counts = row
        record = dict(zip(_INSIGHT_EVENT_COLUMNS, counts, strict=True))
        line = woba_line(record)
        if line.opportunities <= 0:
            continue
        pair_lines[(hitter, pitcher)] = line
        hitter_lines[hitter].append(line)
        pitcher_lines[pitcher].append(line)
        ubb = max(int(record["bb"] or 0) - int(record["ibb"] or 0), 0)
        event_totals["ubb"] += ubb
        for key in ("hbp", "singles", "doubles", "triples", "home_runs"):
            event_totals[key] += int(record[key] or 0)
    if not pair_lines:
        raise ValueError("洞察母體為空：該範圍沒有可用對戰列")

    league = merge_lines(pair_lines.values())
    league_mean = league.weighted_sum / league.opportunities
    hitter_totals = {
        pid: merged
        for pid, lines in hitter_lines.items()
        if (merged := merge_lines(lines)).opportunities > 0
    }
    pitcher_totals = {
        pid: merged
        for pid, lines in pitcher_lines.items()
        if (merged := merge_lines(lines)).opportunities > 0
    }
    pairs = tuple(
        PairSample(hitter_id=h, pitcher_id=p, line=line)
        for (h, p), line in pair_lines.items()
    )
    sigma2 = per_opportunity_variance(league, event_totals)
    hyper = estimate_hyperparameters(
        pairs,
        hitter_totals=hitter_totals,
        pitcher_totals=pitcher_totals,
        league_mean=league_mean,
        sigma2=sigma2,
    )
    return InsightUniverse(
        league=league,
        league_mean=league_mean,
        hitter_totals=hitter_totals,
        pitcher_totals=pitcher_totals,
        pairs=pairs,
        hyper=hyper,
    )


def load_insight_universe(
    cur: Any, kind_code: str, from_year: int, to_year: int
) -> InsightUniverse:
    """讀取（或重用快取的）洞察母體；scope 邊界互斥，生涯與年度不混用。"""
    key = (kind_code, from_year, to_year)
    cached = _universe_cache.get(key)
    now = _time.monotonic()
    if cached and now - cached[0] < _UNIVERSE_TTL_SECONDS:
        return cached[1]
    cur.execute(
        """
        SELECT hitter_acnt, pitcher_acnt,
               sum(at_bats), sum(singles), sum(doubles), sum(triples),
               sum(home_runs), sum(bb), sum(ibb), sum(hbp), sum(sac_fly)
        FROM cpbl.batter_pitcher_matchups
        WHERE kind_code=%s AND year BETWEEN %s AND %s
        GROUP BY hitter_acnt, pitcher_acnt
        """,
        (kind_code, from_year, to_year),
    )
    universe = _build_universe(cur.fetchall())
    _universe_cache[key] = (now, universe)
    if len(_universe_cache) > 16:
        oldest = min(_universe_cache, key=lambda k: _universe_cache[k][0])
        _universe_cache.pop(oldest, None)
    return universe
