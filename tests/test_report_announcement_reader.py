from cpbl.reports import readers


def cursor(exists):
    class Cursor:
        description = []

        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

        def fetchone(self):
            return ("cpbl.game_lineup_announcement_revisions" if exists else None,)

        def fetchall(self):
            return []

    return Cursor()


def test_missing_table_is_read_only_unknown_without_ddl_or_target_query():
    cur = cursor(False)
    assert readers.lineup_revisions(cur, 2026, [{"kind_code": "E", "game_sno": 4}]) == []
    assert len(cur.calls) == 1 and "to_regclass" in cur.calls[0][0]
    assert all("CREATE" not in sql and "INSERT" not in sql for sql, _ in cur.calls)


def test_existing_table_reads_one_parameterized_batch_of_exact_kind_candidates():
    cur = cursor(True)
    assert (
        readers.lineup_revisions(
            cur, 2026, [{"kind_code": "E", "game_sno": 4}, {"kind_code": "C", "game_sno": 1}]
        )
        == []
    )
    assert len(cur.calls) == 2 and cur.calls[1][1] == (2026, [4], [1])
    assert "SELECT" in cur.calls[1][0] and "%s" in cur.calls[1][0]


def test_other_year_and_empty_candidates_never_probe_new_table():
    cur = cursor(True)
    assert readers.lineup_revisions(cur, 2025, [{"kind_code": "E", "game_sno": 4}]) == []
    assert readers.lineup_revisions(cur, 2026, []) == [] and not cur.calls
