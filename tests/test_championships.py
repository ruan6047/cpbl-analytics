"""總冠軍權威資料集的 coverage 與球團沿革回歸測試。"""

from __future__ import annotations

from datetime import UTC, datetime

from cpbl.franchises import franchise_of
from cpbl.ingest.championships import championship_coverage


def test_championship_coverage_is_complete_for_all_36_seasons():
    years = list(range(1990, 2026))
    verified_at = datetime(2026, 7, 14, tzinfo=UTC)

    assert championship_coverage(years, as_of=verified_at) == {
        "from_year": 1990,
        "through_year": 2025,
        "complete": True,
        "missing_years": [],
        "as_of": verified_at,
    }


def test_championship_coverage_fails_closed_when_a_season_is_missing():
    years = [year for year in range(1990, 2026) if year != 1994]

    coverage = championship_coverage(years, as_of=None)

    assert coverage["complete"] is False
    assert coverage["missing_years"] == [1994]
    assert coverage["as_of"] is None


def test_championship_coverage_ignores_years_outside_canonical_range():
    years = [1989, *range(1990, 2026), 2026]

    coverage = championship_coverage(years, as_of=None)

    assert coverage["complete"] is True
    assert coverage["missing_years"] == []


def test_historical_team_codes_map_to_canonical_franchises():
    assert franchise_of("ACC011") == "ACN011"  # 兄弟象 → 中信兄弟
    assert franchise_of("AEE011") == "AEO011"  # 俊國熊 → 富邦悍將
    assert franchise_of("AEG011") == "AEO011"  # 興農牛 → 富邦悍將
    assert franchise_of("AEM011") == "AEO011"  # 義大犀牛 → 富邦悍將
    assert franchise_of("AJJ011") == "AJL011"  # 第一金剛 → 樂天桃猿
    assert franchise_of("AJK011") == "AJL011"  # La New／Lamigo → 樂天桃猿
    assert franchise_of("AIL011") == "AII011"  # 米迪亞暴龍 → 誠泰 franchise


def test_unknown_or_stable_team_code_maps_to_itself():
    assert franchise_of("ADD011") == "ADD011"
    assert franchise_of("UNKNOWN") == "UNKNOWN"
