"""Precision tests for the same guard reached by the daily and evening entry points."""

import re
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.test_prod_sync_revision_seq import _run_refresh


@pytest.mark.parametrize("mode", ["daily", "evening"])
@pytest.mark.parametrize(("trigger", "marker", "filtered"), [
    ("launchd", True, True),
    ("manual", True, False),
    ("launchd", False, False),
])
def test_schedule_guard_preserves_other_writers(tmp_path, mode, trigger, marker, filtered):
    env = {"REFRESH_TRIGGER": trigger, "STUB_TRACE_FRESHNESS": "1"}
    if mode == "evening":
        env.update(POSTSEASON_RESULTS_ONLY="1", BACKUP_DIR=str(tmp_path / "night-backups"))
    result, calls = _run_refresh(
        tmp_path, with_detail=mode == "daily", external_game_features=True,
        external_a_schedule=marker, **env,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    year = datetime.now(ZoneInfo("Asia/Taipei")).year
    owned = f"year = {year} AND kind_code = 'A'"
    writes = {}
    for name in ("games", "game_schedule_status_revisions", "game_source_revisions", "official_change_signals"):
        writes[name], = [call["stdin"] for call in calls if re.search(rf"^INSERT INTO cpbl\.{name}\s", call["stdin"], re.M)]
    source_scope = f"{owned} AND source = 'schedule'"
    for table in ("games", "game_schedule_status_revisions", "game_source_revisions"):
        expect = source_scope if table == "game_source_revisions" else owned
        payload = writes[table]
        assert ("WHERE NOT (" + expect + ")") in payload if filtered else "WHERE NOT (" not in payload
        assert not re.search(r"^(DELETE|TRUNCATE) ", payload, re.M)
        if filtered and table != "games":
            assert payload.index("LOCK TABLE") < payload.index("SELECT setval")
        if filtered:
            where = re.search(r"WHERE NOT \(([^\n]+)\)", payload)[0].split(" ON CONFLICT", 1)[0]
            where = where[:where.rindex(")") + 1]
            with sqlite3.connect(":memory:") as db:
                db.execute("CREATE TABLE staged(year, kind_code, source)")
                db.executemany("INSERT INTO staged VALUES(?,?,?)", [
                    (year, "A", "schedule"), (year, "A", "scoreboard"),
                    (year, "D", "schedule"), (year - 1, "A", "schedule"),
                ])
                kept = db.execute(f"SELECT rowid FROM staged {where} ORDER BY rowid").fetchall()
                assert kept == ([(2,), (3,), (4,)] if table == "game_source_revisions" else [(3,), (4,)])
    assert "WHERE NOT (" not in writes["official_change_signals"]
    assert any(f"FROM cpbl.games g WHERE {owned}" in " ".join(call["argv"]) for call in calls) is filtered
    expected_date, expected_count = ("2026-08-15", 305) if filtered else ("2026-08-14", 300)
    verification = [line for line in result.stdout.splitlines() if line.startswith("stub freshness ")]
    assert len(verification) == (2 if mode == "daily" else 1)
    assert all(f"--expected-last-game-date {expected_date}" in line
               and f"--expected-season-games-completed {expected_count}" in line for line in verification)
    if mode == "daily":
        assert any("INSERT INTO cpbl.game_features " in c["stdin"] for c in calls) is (trigger == "manual")
