"""投打對決查詢的資料範圍、聚合與排序規則。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

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
        return MatchupScope(scope, CAREER_YEAR, CAREER_YEAR, "official_career")
    if scope == "season":
        return MatchupScope(scope, season, season, "annual")
    if scope != "range":
        raise ValueError(f"不支援的資料範圍：{scope}")
    if from_year is None or to_year is None:
        raise ValueError("range scope 必須同時提供 from_year 與 to_year")
    if from_year > to_year:
        raise ValueError("from_year 不可大於 to_year")
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
        for field in ("opp_name", "opp_team_code", "hitter_name", "pitcher_name"):
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
        # 官網未提供跨年可加總的揮空分子／分母；多列時不可平均百分比。
        item["whiff_pct"] = latest.get("whiff_pct") if len(members) == 1 else None
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


def build_matchup_order(sort: str, order: str) -> str:
    """只允許固定欄位與方向進入 ORDER BY。"""
    column = _SORT_COLUMNS.get(sort)
    if column is None:
        raise ValueError(f"不支援的排序欄位：{sort}")
    direction = order.upper()
    if direction not in {"ASC", "DESC"}:
        raise ValueError(f"不支援的排序方向：{order}")
    return f"{column} {direction} NULLS LAST, opp_name ASC"
