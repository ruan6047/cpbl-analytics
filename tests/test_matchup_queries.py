from __future__ import annotations

import pytest
from cpbl.api.matchups import (
    MatchupScope,
    aggregate_matchup_rows,
    build_matchup_order,
    resolve_matchup_scope,
)

from cpbl.franchises import franchise_prefixes


def test_career_scope_uses_only_official_career_rows():
    scope = resolve_matchup_scope("career", season=2026, from_year=None, to_year=None)

    assert scope == MatchupScope("career", 9999, 9999, "official_career")


def test_season_scope_never_falls_back_to_career_rows():
    scope = resolve_matchup_scope("season", season=2026, from_year=None, to_year=None)

    assert scope == MatchupScope("season", 2026, 2026, "annual")


def test_range_scope_requires_complete_ordered_bounds():
    with pytest.raises(ValueError, match="from_year 與 to_year"):
        resolve_matchup_scope("range", season=2026, from_year=2024, to_year=None)

    with pytest.raises(ValueError, match="from_year 不可大於 to_year"):
        resolve_matchup_scope("range", season=2026, from_year=2026, to_year=2024)

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


def test_historical_team_filter_expands_to_every_franchise_era():
    assert franchise_prefixes("AEO011") == {"AEE", "AEG", "AEM", "AEO"}
    assert franchise_prefixes("AEE") == {"AEE", "AEG", "AEM", "AEO"}
    assert franchise_prefixes("AKP011") == {"AKP"}


def test_sort_clause_is_whitelisted():
    assert build_matchup_order("plate_appearances", "desc") == (
        "plate_appearances DESC NULLS LAST, opp_name ASC"
    )
    assert build_matchup_order("recent_year", "asc") == "to_year ASC NULLS LAST, opp_name ASC"

    with pytest.raises(ValueError, match="不支援的排序欄位"):
        build_matchup_order("plate_appearances; DROP TABLE cpbl.games", "desc")
