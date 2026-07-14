"""總冠軍權威資料集的 coverage 與球團沿革回歸測試。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from cpbl.franchises import franchise_of
from cpbl.ingest.championships import championship_coverage

_MIGRATION = Path(__file__).parents[1] / "migrations" / "052_championships.sql"
_SEED_ROW = re.compile(
    r"\((\d{4}), '([^']+)', (?:'([^']+)'|NULL)\s*,\s*'([^']+)', "
    r"'([^']+)', 'verified'",
)


def _seed_rows() -> dict[int, tuple[str, str | None, str, str]]:
    sql = _MIGRATION.read_text(encoding="utf-8")
    return {
        int(year): (champion, runner_up or None, franchise, source_url)
        for year, champion, runner_up, franchise, source_url in _SEED_ROW.findall(sql)
    }


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


def test_canonical_seed_has_every_season_once_with_official_sources():
    rows = _seed_rows()

    assert sorted(rows) == list(range(1990, 2026))
    assert len(rows) == 36
    assert all(source.startswith("https://www.cpbl.com.tw/") for *_, source in rows.values())
    assert all(franchise_of(champion) == franchise for champion, _, franchise, _ in rows.values())


def test_direct_champions_have_no_fabricated_runner_up_and_cite_official_news():
    rows = _seed_rows()

    assert rows[1992] == (
        "ACC011",
        None,
        "ACN011",
        "https://www.cpbl.com.tw/xmdoc/cont?sid=0L132508224704611366",
    )
    assert rows[1994] == rows[1992]
    assert rows[1995] == (
        "ADD011",
        None,
        "ADD011",
        "https://www.cpbl.com.tw/xmdoc/cont?sid=0L132509713020586356",
    )
