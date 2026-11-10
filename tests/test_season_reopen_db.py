"""#392 切回紀錄的真 PostgreSQL 契約測試（預設 skip；``docs/AI_RUNBOOK.md`` §7.2 同法，只在隔離 database 實跑）。

為什麼需要真 PG：讀取 SQL 或 ``to_regclass`` 守衛寫錯會讓 ``league_closure`` 拋錯，所有消費端 fail-open 成
「未收官」——等於靜默恢復爬 www、首頁失去球季結束。假 cursor 證不了 SQL 有效。

    docker exec cpbl-analytics-db-1 psql -U cpbl -d postgres -c "CREATE DATABASE cpbl_season_reopen392"
    DATABASE_URL=postgresql://cpbl:cpbl@localhost:5433/cpbl_season_reopen392 \\
      uv run python -c "from cpbl.db import migrate; print(len(migrate()),'migrations')"
    SEASON_REOPEN_TEST_DATABASE_URL=postgresql://cpbl:cpbl@localhost:5433/cpbl_season_reopen392 \\
      DATABASE_URL=postgresql://invalid:1/none uv run pytest tests/test_season_reopen_db.py -q
    docker exec cpbl-analytics-db-1 psql -U cpbl -d postgres -c "DROP DATABASE cpbl_season_reopen392"

正式站路徑（``remote``）以同一份 psql 腳本對隔離庫實跑：目標指令＝``docker exec -i <容器> psql … -d <隔離庫>``。
本檔不呼叫 ``migrate()``（隔離庫事先 migrate 一次）。
"""

from __future__ import annotations

import io
import os

import pytest

URL = os.environ.get("SEASON_REOPEN_TEST_DATABASE_URL")
DBNAME = "cpbl_season_reopen392"
CONTAINER = os.environ.get("SEASON_REOPEN_TEST_CONTAINER", "cpbl-analytics-db-1")
pytestmark = pytest.mark.skipif(not URL, reason="SEASON_REOPEN_TEST_DATABASE_URL 未設（DB 契約測試預設 skip）")

ROWS = (("farm", 2026), ("major", 2026))


@pytest.fixture()
def db(monkeypatch):
    assert URL and URL.rsplit("/", 1)[-1] == DBNAME, f"只允許隔離 database {DBNAME}"
    from cpbl import db as cdb
    from cpbl.config import settings

    monkeypatch.setattr(settings, "database_url", URL)
    monkeypatch.setattr(cdb, "_pool", None)
    with cdb.conn() as c:
        # fail closed：確認真的連到隔離 database 才清測試列（⛔ 不得落到本機正式 cpbl）。
        assert c.execute("SELECT current_database()").fetchone()[0] == DBNAME
        assert c.execute("SELECT to_regclass('cpbl.season_reopen') IS NOT NULL").fetchone()[0], "隔離庫須先 migrate"
        c.execute("DELETE FROM cpbl.season_reopen")  # 只在隔離庫：每支測試從空表開始
    yield cdb
    if cdb._pool is not None:
        cdb._pool.close()
    monkeypatch.setattr(cdb, "_pool", None)


def _rows(cdb):
    with cdb.conn() as c:
        return c.execute("SELECT league, season, reopened_at, revoked_at FROM cpbl.season_reopen "
                         "ORDER BY league, season").fetchall()


def test_missing_table_reads_as_no_records(db):
    """部署先於 migration：表不存在時 ``read_reopened`` 回空集合、不拋錯（DROP 在外層交易內，結束即回滾）。"""
    from cpbl import season_close as sc

    with db.conn() as c:
        tx = c.transaction(force_rollback=True)
        with tx:
            c.execute("DROP TABLE cpbl.season_reopen")
            with c.transaction():
                cur = c.cursor()
                assert sc.read_reopened(cur) == frozenset()
        assert c.execute("SELECT to_regclass('cpbl.season_reopen') IS NOT NULL").fetchone()[0], "DROP 已回滾"


def test_league_closure_runs_its_real_sql_with_reopen_reading(db):
    """完整讀取路徑（READ ONLY 交易＋to_regclass＋切回紀錄＋最新球季）在真 PG 上可執行。隔離庫沒有 games ⇒ no_data。"""
    from cpbl import season_close as sc
    from cpbl import season_reopen as sr

    with db.conn() as c:
        sr.write_local(c, "apply", ROWS)
    out = sc.league_closure(env={})
    assert {lg: (c.closed, c.status) for lg, c in out.items()} == {"major": (False, "no_data"),
                                                                     "farm": (False, "no_data")}
    with db.conn() as c, c.transaction():
        cur = c.cursor()
        cur.execute("SET TRANSACTION READ ONLY")
        assert sc.read_reopened(cur) == frozenset(ROWS)


def test_local_apply_is_idempotent_then_revoke_then_reapply(db):
    from cpbl import season_close as sc
    from cpbl import season_reopen as sr

    with db.conn() as c:
        sr.write_local(c, "apply", ROWS)
    first = _rows(db)
    with db.conn() as c:
        sr.write_local(c, "apply", ROWS)
    assert _rows(db) == first, "已有效的紀錄重跑不變（保留第一次的 reopened_at）"
    assert [(r[0], r[1], r[3]) for r in first] == [("farm", 2026, None), ("major", 2026, None)]

    with db.conn() as c:
        sr.write_local(c, "revoke", ROWS)
    revoked = _rows(db)
    assert len(revoked) == 2 and all(r[3] is not None for r in revoked), "作廢＝填 revoked_at，列保留"
    with db.conn() as c, c.transaction():
        assert sc.read_reopened(c.cursor()) == frozenset()

    with db.conn() as c:
        sr.write_local(c, "apply", (("major", 2026),))
    again = {(r[0], r[1]): r for r in _rows(db)}
    assert again[("major", 2026)][3] is None and again[("major", 2026)][2] >= first[1][2]
    assert again[("farm", 2026)][3] is not None


def test_remote_psql_scripts_against_real_postgres(db):
    """正式站單表步驟的同一份 psql 腳本（存在檢查／寫入／讀回）對隔離庫實跑。"""
    from cpbl import season_reopen as sr

    target = sr.PsqlTarget(f"docker exec -i {CONTAINER} psql -U cpbl -d {DBNAME}")
    assert target.argv[-1] == DBNAME
    out = io.StringIO()
    assert sr.remote(target, "apply", ROWS, out=out) == 0
    assert "status=farm:2026=active,major:2026=active" in out.getvalue()
    assert sr.remote(target, "apply", ROWS, out=io.StringIO()) == 0
    out = io.StringIO()
    assert sr.remote(target, "revoke", ROWS, out=out) == 0
    assert "status=farm:2026=revoked,major:2026=revoked" in out.getvalue()
    out = io.StringIO()
    assert sr.remote(target, "revoke", (("farm", 2025),), out=out) == 0, "沒有的列作廢＝absent，冪等不報錯"
    assert "farm:2025=absent" in out.getvalue()
    assert [(r[0], r[1]) for r in _rows(db)] == list(ROWS)
