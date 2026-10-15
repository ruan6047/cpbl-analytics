"""#284 名單 insert-only 同步演練（opt-in；E18）。

本機端＝cpbl_test_284、「生產」目標＝cpbl_test_284_prod，皆在卡號容器 cpbl284-pg。
傳輸走與生產同形狀的「psql 讀 stdin 腳本」（生產為 ssh＋docker exec prod_pg psql；這裡是
docker exec cpbl284-pg psql），⛔ 不連真生產。需四個環境變數：
  CPBL284_TEST_DSN／CPBL284_PROD_TEST_DSN（psycopg 驗證查詢）
  CPBL284_LOCAL_PSQL／CPBL284_PROD_PSQL（例 "docker exec -i cpbl284-pg psql -U cpbl -d cpbl_test_284"）
"""

from __future__ import annotations

import os
import time

import psycopg
import pytest
from psycopg_pool import ConnectionPool
from roster_284_support import LOCAL_DB, PROD_DB, isolated_dsn, reset, seed

from cpbl import db
from cpbl.ingest.run_roster import _official_text
from cpbl.rosters import sync
from cpbl.rosters.parser import parse
from cpbl.rosters.store import annotate, pasted_origin, prepare, submit

TABLES = ("series_roster", "series_roster_member", "roster_annotation_revision")


def _psql(env: str, dbname: str) -> str:
    cmd = os.environ.get(env)
    if not cmd:
        pytest.skip(f"{env} 未設（#284 同步演練為 opt-in）")
    if "cpbl284-pg" not in cmd or f"-d {dbname}" not in cmd:
        pytest.fail(f"{env} 不在 #284 隔離資源（需 cpbl284-pg 與 -d {dbname}）", pytrace=False)
    return cmd


@pytest.fixture
def env(monkeypatch):
    local_dsn = isolated_dsn("CPBL284_TEST_DSN", LOCAL_DB)
    prod_dsn = isolated_dsn("CPBL284_PROD_TEST_DSN", PROD_DB)
    local_cmd = _psql("CPBL284_LOCAL_PSQL", LOCAL_DB[2])
    prod_cmd = _psql("CPBL284_PROD_PSQL", PROD_DB[2])
    with psycopg.connect(prod_dsn, autocommit=True) as c:
        assert c.execute("SELECT current_database()").fetchone()[0] == PROD_DB[2]
        c.execute("DROP SCHEMA IF EXISTS cpbl CASCADE")  # 生產尚無名單表的起點（只限隔離庫）
    with ConnectionPool(local_dsn, min_size=0, max_size=2, configure=db._configure) as p:
        monkeypatch.setattr(db, "_pool", p)
        db.migrate()
        with db.conn() as c:
            reset(c)
            seed(c)
        yield {"local_dsn": local_dsn, "prod_dsn": prod_dsn,
               "source": sync.PsqlTarget(local_cmd), "target": sync.PsqlTarget(prod_cmd),
               "argv": ["--local-psql", local_cmd, "--target-psql", prod_cmd]}


def _submit(team="ACN011", text=None):
    text = text or _official_text(2026, "E", team)[0]
    with db.conn() as c:
        _, h, _ = prepare(c, parse(text))
        return submit(c, parse(text), h["membership_hash"], pasted_origin())


def _migrate_prod(dsn, monkeypatch):
    with ConnectionPool(dsn, min_size=0, max_size=1, configure=db._configure) as p:
        saved = db._pool
        db._pool = p
        try:
            db.migrate()
        finally:
            db._pool = saved


def _prod_stats(dsn):
    time.sleep(1.2)  # 讓已結束的 psql backend 統計落地
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("SELECT pg_stat_clear_snapshot()")
        stats = {r[0]: r[1:] for r in c.execute(
            "SELECT relname, n_tup_ins, n_tup_upd, n_tup_del FROM pg_stat_user_tables "
            "WHERE schemaname='cpbl' AND relname = ANY(%s)", (list(TABLES),))}
        rows = c.execute(
            "SELECT year, kind_code, team_code, roster_id::text, membership_hash, source_hash, submitted_at "
            "FROM cpbl.series_roster ORDER BY 1,2,3").fetchall()
        revs = c.execute("SELECT roster_id::text, revision, count(*), min(revision_hash) "
                         "FROM cpbl.roster_annotation_revision GROUP BY 1,2 ORDER BY 1,2").fetchall()
    return stats, rows, revs


def test_e18_insert_only_sync_rehearsal(env, monkeypatch, capsys):
    a = _submit("ACN011")
    _submit("ADD011")

    # 1) 目標尚無名單表 → 69，不寫
    assert sync.main(["plan", *env["argv"]]) == sync.EXIT_NO_TABLE
    _migrate_prod(env["prod_dsn"], monkeypatch)

    # 2) 首次：待插入 → apply 整份插入＋對帳一致
    capsys.readouterr()
    assert sync.main(["plan", *env["argv"]]) == 0
    assert "ROSTER_SYNC_PLAN=insert-pending" in capsys.readouterr().out
    assert sync.main(["apply", *env["argv"]]) == 0
    out = capsys.readouterr().out
    assert "ROSTER_SYNC_RECONCILE=ok" in out and out.count("✓") == 2
    stats1, rows1, revs1 = _prod_stats(env["prod_dsn"])
    assert [r[3] for r in rows1 if r[2] == "ACN011"] == [a["roster_id"]]
    assert stats1["series_roster"] == (2, 0, 0) and stats1["series_roster_member"] == (64, 0, 0)

    # 3) 重跑：無變更、不寫
    assert sync.main(["plan", *env["argv"]]) == 0
    assert "ROSTER_SYNC_PLAN=no-change" in capsys.readouterr().out
    assert sync.main(["apply", *env["argv"]]) == 0
    assert "無變更，未寫入" in capsys.readouterr().out
    assert _prod_stats(env["prod_dsn"]) == (stats1, rows1, revs1)

    # 4) 本機角色修訂 → 只插新角色版，會員不動
    text = _official_text(2026, "E", "ACN011")[0].replace("羅戈 @id=0000005151", "羅戈 @id=0000005151 #輪值")
    with db.conn() as c:
        assert annotate(c, parse(text))["annotation_version"] == 2
    assert sync.main(["apply", *env["argv"]]) == 0
    capsys.readouterr()
    stats2, rows2, revs2 = _prod_stats(env["prod_dsn"])
    assert rows2 == rows1 and len(revs2) == len(revs1) + 1
    assert stats2["roster_annotation_revision"] == (96, 0, 0)

    # 5) 本機改為同 scope 異內容（重建隔離本機後以不同來源提交）→ 70 拒絕，目標零變動
    with db.conn() as c:
        reset(c)
        seed(c)
    _submit("ACN011", _official_text(2026, "E", "ACN011")[0].replace(
        "@source https://", "@source https://mirror."))
    assert sync.main(["apply", *env["argv"]]) == sync.EXIT_REJECT
    err = capsys.readouterr().err
    assert "2026/E/ACN011" in err and "source_url" in err
    assert "目標有本機沒有的名單" in err  # ADD011 只剩目標端
    assert _prod_stats(env["prod_dsn"]) == (stats2, rows2, revs2)
    assert all(s[1] == 0 and s[2] == 0 for s in stats2.values())  # 零 UPDATE／DELETE


def test_self_check_refuses_tampered_local_hash(env, monkeypatch):
    _submit("ACN011")
    _migrate_prod(env["prod_dsn"], monkeypatch)
    with db.conn() as c:  # 只在隔離本機以 replica 角色竄改存值（模擬損毀）
        c.execute("SET session_replication_role = replica")
        c.execute("UPDATE cpbl.series_roster SET membership_hash = repeat('0', 64)")
        c.execute("SET session_replication_role = origin")
    assert sync.main(["plan", *env["argv"]]) == sync.EXIT_SELF_CHECK
    stats, rows, _ = _prod_stats(env["prod_dsn"])
    assert rows == []


def test_in_transaction_conflict_recheck_blocks_race(env, monkeypatch):
    """比對之後、寫入之前目標被另一份同 scope 名單占用 → 交易內再查衝突，整筆不寫。"""
    _submit("ACN011")
    _migrate_prod(env["prod_dsn"], monkeypatch)
    local, remote, p = sync.run_plan(env["source"], env["target"])
    assert p.state == "insert-pending"
    env["target"].run(sync.apply_script(sync.payload(local, p)))  # 競寫者先寫入同 scope
    with pytest.raises(sync.SyncError) as exc:
        env["target"].run(sync.apply_script(sync.payload(local, p)))
    assert exc.value.code == sync.EXIT_TARGET and "ROSTER_SYNC_CONFLICT" in str(exc.value)
