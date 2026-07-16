from pathlib import Path

_COACH_HISTORY_MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "053_coach_history.sql"
)


def test_coach_history_indexes_are_guarded_when_compatibility_view_exists():
    sql = _COACH_HISTORY_MIGRATION.read_text(encoding="utf-8")

    guard_start = sql.index("IF relation_kind IN ('r', 'p') THEN")
    first_index = sql.index("CREATE INDEX IF NOT EXISTS idx_coach_history_name")
    second_index = sql.index("CREATE INDEX IF NOT EXISTS idx_coach_history_player")
    guard_end = sql.index("END IF;", second_index)

    assert guard_start < first_index < second_index < guard_end
