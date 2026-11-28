"""#469：冠軍補列 SQL 在真 PostgreSQL（CI 資料基底 ``tests/ci_base.py``）上的契約。

只在主 DSN 是已載入的 CI 基底時跑（``ci_base.active()``）；⛔ 本機正式庫或其他庫一律 skip。
全部在單一交易內做、結束 ROLLBACK，基底不留任何列。

驗假 cursor 驗不到的事：
1. 欄位名／型別／CHECK（``verified`` 須帶 ``verified_at``）／FK（``championship_managers`` → ``championships``）真的吃得下。
2. 亞軍取自真實決勝場列（基底收了 2026/C/6：主 味全、客 中信兄弟）。
3. 第二次呼叫不改任何列；1990–2025 既有列逐欄不變。
4. ``read_major_closure`` 在真 schema 上讀得出一軍判定（不拋錯；值不斷言，基底不保證收齊判定所需的戰績）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import ci_base
import pytest

from cpbl.ingest import championships as ch
from tests import test_season_close as real391

NOW = datetime(2026, 11, 29, 3, 10, tzinfo=UTC)
REAL_MAJOR_2026 = real391.major(real391.major_games())
HISTORY_SQL = "SELECT * FROM cpbl.championships WHERE year BETWEEN 1990 AND 2025 ORDER BY year"


@pytest.fixture()
def cur():
    if not ci_base.active():
        pytest.skip("主 DSN 不是 CI 資料基底：冠軍補列的寫入契約只在拋棄式基底上跑")
    import psycopg

    from cpbl.config import settings

    with psycopg.connect(settings.database_url) as c:
        try:
            yield c.cursor()
        finally:
            c.rollback()


def test_autofill_sql_inserts_once_and_never_touches_history(cur):
    cur.execute("SELECT count(*) FROM cpbl.championships WHERE year = 2026")
    if cur.fetchone()[0]:
        pytest.skip("基底已有 2026 冠軍列（重產基底後請改用尚無冠軍列的年份）")
    cur.execute(HISTORY_SQL)
    before = cur.fetchall()
    assert len(before) == 36
    cur.execute("INSERT INTO cpbl.coaches (year, team_code, name, pos) VALUES (2026, 'AAA011', '葉君璋', %s)",
                (ch.HEAD_COACH_POS,))

    first = ch.ensure_season_champion(cur, REAL_MAJOR_2026, now=NOW, env={})
    second = ch.ensure_season_champion(cur, REAL_MAJOR_2026, now=NOW, env={})

    assert (first["action"], first["manager"]) == ("inserted", "inserted")
    assert (second["action"], second["manager"]) == ("present", "present")
    cur.execute("SELECT champion_team_code, runner_up_team_code, franchise_code, source_url, "
                "verification_status, verified_at FROM cpbl.championships WHERE year = 2026")
    assert cur.fetchall() == [("AAA011", "ACN011", "AAA011",
                               "https://www.cpbl.com.tw/box?year=2026&KindCode=C&gameSno=6", "verified", NOW)]
    cur.execute("SELECT manager_name, franchise_code, source_url, verification_status, verified_at "
                "FROM cpbl.championship_managers WHERE year = 2026")
    assert cur.fetchall() == [("葉君璋", "AAA011", "https://www.cpbl.com.tw/team/index?teamNo=AAA011",
                               "verified", NOW)]
    cur.execute(HISTORY_SQL)
    assert cur.fetchall() == before


def test_read_major_closure_runs_on_real_schema():
    if not ci_base.active():
        pytest.skip("主 DSN 不是 CI 資料基底")

    closure = ch.read_major_closure()

    assert closure.league == "major"
    assert ch.coverage_through_year(closure) >= ch.CANONICAL_THROUGH_YEAR
