"""完賽語意的回歸測試：比分是已開賽證據，不是完賽證據。"""

from datetime import date

import pytest

from cpbl.completion import completed_games_sql, is_completed


@pytest.mark.parametrize(
    ("home_score", "away_score", "game_date", "as_of", "expected"),
    [
        (5, 4, date(2026, 7, 16), date(2026, 7, 19), True),   # 一般完賽
        (None, None, date(2026, 7, 19), date(2026, 7, 19), False),  # 當日未開打
        (0, 0, date(2026, 7, 18), date(2026, 7, 19), False),  # 延賽
        # 2026 二軍真實保留賽匿名化 snapshot：帶中止比分、續賽日仍在未來。
        (5, 4, date(2026, 8, 8), date(2026, 7, 19), False),
        # 同一保留賽於續完日寫回最終比分後，應重新納入 completed。
        (7, 4, date(2026, 8, 8), date(2026, 8, 8), True),
        (3, 2, date(2026, 7, 19), date(2026, 7, 19), True),  # 日期邊界
    ],
)
def test_completion_requires_score_and_date_not_after_as_of(
    home_score: int | None,
    away_score: int | None,
    game_date: date,
    as_of: date,
    expected: bool,
) -> None:
    assert is_completed(home_score, away_score, game_date, as_of) is expected


def test_completion_sql_uses_the_same_score_and_as_of_contract() -> None:
    assert completed_games_sql("CURRENT_DATE") == (
        "home_score + away_score > 0 AND game_date <= CURRENT_DATE"
    )
