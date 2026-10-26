"""#342 只寫先發寫入器的 DB 契約測試（預設 skip；docs/AI_RUNBOOK.md §7.2 同法，在隔離 database 實跑）。

    docker exec cpbl-analytics-db-1 psql -U cpbl -d postgres -c "CREATE DATABASE cpbl_ingest_starter_watch1"
    DATABASE_URL=postgresql://cpbl:cpbl@localhost:5433/cpbl_ingest_starter_watch1 \\
      uv run python -c "from cpbl.db import migrate; print(len(migrate()),'migrations')"
    STARTER_WATCH_TEST_DATABASE_URL=postgresql://cpbl:cpbl@localhost:5433/cpbl_ingest_starter_watch1 \\
      uv run pytest tests/test_starter_watch_db.py -q

payload 取自 ``tests/fixtures/starter_watch_replay/revisions-2026.json``（真實）；種子列用既有 ``upsert_games``
寫入（等同 J1 當時寫進本機的狀態），之後只呼叫 :func:`starter_watch.write_starters`。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

URL = os.environ.get("STARTER_WATCH_TEST_DATABASE_URL")
DBNAME = "cpbl_ingest_starter_watch1"
pytestmark = pytest.mark.skipif(not URL, reason="STARTER_WATCH_TEST_DATABASE_URL 未設（DB 契約測試預設 skip）")

FIXTURE = Path(__file__).parent / "fixtures" / "starter_watch_replay" / "revisions-2026.json"
ROWS = json.loads(FIXTURE.read_text(encoding="utf-8"))["rows"]


def payloads(kind: str, sno: int) -> list[dict]:
    return [r["raw_payload"] for r in ROWS if r["kind_code"] == kind and r["game_sno"] == sno]


@pytest.fixture()
def db(monkeypatch):
    assert URL and URL.rsplit("/", 1)[-1] == DBNAME, f"只允許隔離 database {DBNAME}"
    from cpbl import db as cdb
    from cpbl.config import settings

    monkeypatch.setattr(settings, "database_url", URL)
    monkeypatch.setattr(cdb, "_pool", None)
    keys = [("C", 6), ("C", 7), ("A", 304), ("A", 326), ("A", 302)]
    with cdb.conn() as c:
        # fail closed：確認真的連到隔離 database 才清測試列（⛔ 不得落到本機正式 cpbl）。
        assert c.execute("SELECT current_database()").fetchone()[0] == DBNAME
        for kind, sno in keys:
            c.execute("DELETE FROM cpbl.game_schedule_status_revisions WHERE year = 2026 AND kind_code = %s "
                      "AND game_sno = %s", (kind, sno))
            c.execute("DELETE FROM cpbl.game_source_revisions WHERE year = 2026 AND kind_code = %s "
                      "AND game_sno = %s", (kind, sno))
            c.execute("DELETE FROM cpbl.games WHERE year = 2026 AND kind_code = %s AND game_sno = %s", (kind, sno))
    yield cdb
    if cdb._pool is not None:
        cdb._pool.close()


def _row(cdb, kind, sno):
    with cdb.conn() as c:
        return c.execute(
            """SELECT home_starter_id, away_starter_id, home_score, away_score, winning_pitcher_id,
                      losing_pitcher_id, closer_id, mvp_id, game_date, venue, present_status, delay_kind
               FROM cpbl.games WHERE year = 2026 AND kind_code = %s AND game_sno = %s""", (kind, sno)).fetchone()


def _revs(cdb, kind, sno) -> int:
    with cdb.conn() as c:
        return c.execute("SELECT count(*) FROM cpbl.game_schedule_status_revisions WHERE year = 2026 "
                         "AND kind_code = %s AND game_sno = %s", (kind, sno)).fetchone()[0]


def test_writes_only_starters_for_pregame_target(db):
    from cpbl.ingest import starter_watch as sw
    from cpbl.ingest.cpbl_site import upsert_games

    empty = [p for p in payloads("C", 6) if p["GameResult"] == "" and not p["HomePitcherAcnt"]][-1]
    pub = [p for p in payloads("C", 6) if p["GameResult"] == "" and p["HomePitcherAcnt"]][0]
    upsert_games([empty])                                      # 種子：J1 當時看到的無先發版
    before = _row(db, "C", 6)
    assert before[:2] == (None, None)
    out = sw.write_starters([pub], {"2026-C-6"})
    after = _row(db, "C", 6)
    assert out["games_updated"] == 1
    assert after[:2] == (pub["HomePitcherAcnt"], pub["VisitingPitcherAcnt"])
    assert after[2:] == before[2:], "先發以外的欄位一個都不變"
    assert _revs(db, "C", 6) == 2
    assert sw.local_starters(2026, ["2026-C-6", "2026-C-7"]) == {"2026-C-6"}
    sw.write_starters([pub], {"2026-C-6"})                     # 冪等
    assert _revs(db, "C", 6) == 2 and _row(db, "C", 6) == after


def test_never_creates_rows_or_clears_starters(db):
    from cpbl.ingest import starter_watch as sw
    from cpbl.ingest.cpbl_site import upsert_games

    pub = [p for p in payloads("C", 6) if p["GameResult"] == "" and p["HomePitcherAcnt"]][0]
    assert sw.write_starters([pub], {"2026-C-6"})["games_updated"] == 0, "本機沒有這一列 ⇒ 不新增"
    assert _row(db, "C", 6) is None
    upsert_games([pub])
    empty = [p for p in payloads("C", 6) if p["GameResult"] == "" and not p["HomePitcherAcnt"]][-1]
    sw.write_starters([empty], {"2026-C-6"})
    assert _row(db, "C", 6)[:2] == (pub["HomePitcherAcnt"], pub["VisitingPitcherAcnt"]), "只補不清"


@pytest.mark.parametrize("sno", [304, 326])
def test_started_or_reserved_rows_are_untouched(db, sno):
    """A-304 賽中部分比分、A-326 保留：既有 upsert_games 寫到最後一版後，只寫先發寫入器重放全部版本也不動任何欄。"""
    from cpbl.ingest import starter_watch as sw
    from cpbl.ingest.cpbl_site import upsert_games

    group = payloads("A", sno)
    upsert_games(group)
    before, revs = _row(db, "A", sno), _revs(db, "A", sno)
    for i in range(1, len(group) + 1):
        out = sw.write_starters(group[:i], {f"2026-A-{sno}"})
        seen = group[:i]
        if any(str(p["GameResult"]) in ("0", "2") or p["HomeScore"] or p["VisitingScore"] for p in seen):
            # 值相同的覆寫在終態看不出來，所以直接看寫入器有沒有動手（變異檢驗要能紅）
            assert out == {"games_updated": 0, "revisions": 0}, (sno, i, out)
    assert _row(db, "A", sno) == before and _revs(db, "A", sno) == revs
