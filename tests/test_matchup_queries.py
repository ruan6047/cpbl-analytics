from __future__ import annotations

import pytest

from cpbl.api.matchups import (
    MatchupScope,
    aggregate_matchup_rows,
    resolve_matchup_scope,
    sort_matchup_items,
)
from cpbl.api.routers.players import _search_roster
from cpbl.franchises import franchise_prefixes


def test_career_scope_uses_only_official_career_rows():
    scope = resolve_matchup_scope("career", season=2026, from_year=None, to_year=None)

    assert scope == MatchupScope("career", 9999, 9999, "official_career")

    with pytest.raises(ValueError, match="career scope 不接受年度範圍"):
        resolve_matchup_scope("career", season=2026, from_year=2024, to_year=2025)


def test_season_scope_never_falls_back_to_career_rows():
    scope = resolve_matchup_scope("season", season=2026, from_year=None, to_year=None)

    assert scope == MatchupScope("season", 2026, 2026, "annual")

    with pytest.raises(ValueError, match="9999"):
        resolve_matchup_scope("season", season=9999, from_year=None, to_year=None)


def test_range_scope_requires_complete_ordered_bounds():
    with pytest.raises(ValueError, match="from_year 與 to_year"):
        resolve_matchup_scope("range", season=2026, from_year=2024, to_year=None)

    with pytest.raises(ValueError, match="from_year 不可大於 to_year"):
        resolve_matchup_scope("range", season=2026, from_year=2026, to_year=2024)

    with pytest.raises(ValueError, match="9999"):
        resolve_matchup_scope("range", season=2026, from_year=2024, to_year=9999)

    assert resolve_matchup_scope("range", 2026, 2022, 2025) == MatchupScope(
        "range", 2022, 2025, "annual_aggregate"
    )


def test_aggregate_matchup_rows_sums_counts_before_recalculating_rates():
    rows = [
        {
            "opp_id": "p1",
            "opp_name": "投手甲",
            "opp_team_code": "AEE011",
            "year": 2024,
            "plate_appearances": 12,
            "at_bats": 10,
            "hits": 2,
            "home_runs": 0,
            "total_bases": 2,
            "bb": 1,
            "hbp": 0,
            "sac_fly": 1,
            "so": 3,
        },
        {
            "opp_id": "p1",
            "opp_name": "投手甲",
            "opp_team_code": "AEO011",
            "year": 2025,
            "plate_appearances": 11,
            "at_bats": 10,
            "hits": 5,
            "home_runs": 1,
            "total_bases": 8,
            "bb": 1,
            "hbp": 0,
            "sac_fly": 0,
            "so": 1,
        },
    ]

    item = aggregate_matchup_rows(rows)[0]

    assert item["source_rows"] == 2
    assert item["from_year"] == 2024
    assert item["to_year"] == 2025
    assert item["opp_team_code"] == "AEO011"
    assert item["plate_appearances"] == 23
    assert item["at_bats"] == 20
    assert item["hits"] == 7
    assert item["avg"] == 0.35
    assert item["obp"] == pytest.approx(round(9 / 23, 4))
    assert item["slg"] == 0.5
    assert item["ops"] == pytest.approx(round(round(9 / 23, 4) + 0.5, 4))
    assert item["whiff_pct"] is None


def test_historical_team_filter_expands_to_every_franchise_era():
    assert franchise_prefixes("AEO011") == {"AEE", "AEG", "AEM", "AEO"}
    assert franchise_prefixes("AEE") == {"AEE", "AEG", "AEM", "AEO"}
    assert franchise_prefixes("AKP011") == {"AKP"}


def test_sort_fields_are_whitelisted_and_nulls_stay_last():
    items = [
        {"opp_name": "乙", "plate_appearances": None, "to_year": 2025},
        {"opp_name": "丙", "plate_appearances": 8, "to_year": 2024},
        {"opp_name": "甲", "plate_appearances": 12, "to_year": 2026},
    ]

    assert [row["opp_name"] for row in sort_matchup_items(items, "plate_appearances", "desc")] == [
        "甲",
        "丙",
        "乙",
    ]
    assert [row["opp_name"] for row in sort_matchup_items(items, "recent_year", "asc")] == [
        "丙",
        "乙",
        "甲",
    ]

    with pytest.raises(ValueError, match="不支援的排序欄位"):
        sort_matchup_items(items, "plate_appearances; DROP TABLE cpbl.games", "desc")


def test_roster_sql_does_not_include_python_lint_comment():
    class Cursor:
        description = [("id",), ("name",), ("team_code",), ("team",)]

        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchall(self):
            return []

    cur = Cursor()
    _search_roster(cur, "batting", 2026, "陳", 3)

    assert not cur.sql.lstrip().startswith("#")
    assert "# noqa" not in cur.sql
    assert cur.params == [2026, "%陳%", "%陳%", 3]
