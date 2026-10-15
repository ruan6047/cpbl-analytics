"""#287 WP4a：摘要 insert-only 同步演練（opt-in；E10）。

本機端＝cpbl_test_287、「生產」目標＝cpbl_test_287_prod，皆在卡號容器 cpbl287-pg。傳輸走與生產同形狀的
「psql 讀 stdin 腳本」（生產為 ssh＋docker exec prod_pg psql；這裡是 docker exec cpbl287-pg psql），⛔ 不連真生產。
"""

from __future__ import annotations

import psycopg
import pytest
from team_comparison_287_support import (
    LOCAL_DB,
    PROD_DB,
    connector,
    isolated_dsn,
    mutated,
    psql_cmd,
    require_real_samples,
    reset_summary,
)

from cpbl.playoffs.team_comparison import builder, sync


@pytest.fixture
def env():
    local = isolated_dsn("CPBL287_TEST_DSN", LOCAL_DB)
    prod = isolated_dsn("CPBL287_PROD_TEST_DSN", PROD_DB)
    require_real_samples(local)
    lcmd = psql_cmd("CPBL287_LOCAL_PSQL", LOCAL_DB[2])
    pcmd = psql_cmd("CPBL287_PROD_PSQL", PROD_DB[2])
    reset_summary(local)
    reset_summary(prod)
    yield local, prod, lcmd, pcmd
    reset_summary(local)
    reset_summary(prod)


def _cli(action, lcmd, pcmd, capsys):
    rc = sync.main([action, "--local-psql", lcmd, "--target-psql", pcmd])
    out = capsys.readouterr()
    return rc, out.out, out.err


def _target_state(prod):
    with psycopg.connect(prod) as c:
        return (c.execute("SELECT count(*) FROM cpbl.team_comparison_build").fetchone()[0],
                c.execute("SELECT count(*) FROM cpbl.team_comparison_row").fetchone()[0],
                c.execute("SELECT year, build_id FROM cpbl.team_comparison_current ORDER BY 1").fetchall())


def test_first_write_rerun_noop_and_reconcile(env, capsys):
    local, prod, lcmd, pcmd = env
    rc, out, _ = _cli("plan", lcmd, pcmd, capsys)  # 本機無摘要 ⇒ 無變更、不寫
    assert rc == 0 and "TEAM_COMPARISON_SYNC_PLAN=no-change" in out
    for y in (2025, 2026):
        assert builder.run_build(connector(local), y).code == 0
    rc, out, _ = _cli("plan", lcmd, pcmd, capsys)
    assert rc == 0 and "TEAM_COMPARISON_SYNC_PLAN=insert-pending" in out
    assert _target_state(prod) == (0, 0, [])  # plan 唯讀
    rc, out, _ = _cli("apply", lcmd, pcmd, capsys)
    assert rc == 0 and "TEAM_COMPARISON_SYNC_RECONCILE=ok" in out
    builds, rows, cur = _target_state(prod)
    assert (builds, rows, len(cur)) == (2, 72, 2)
    rc, out, _ = _cli("apply", lcmd, pcmd, capsys)  # 重跑 no-op
    assert rc == 0 and "TEAM_COMPARISON_SYNC_PLAN=no-change（無變更，未寫入）" in out
    assert _target_state(prod) == (builds, rows, cur)


def test_pointer_switch_and_new_build_sync_keep_old_build(env, capsys):
    local, prod, lcmd, pcmd = env
    first = builder.run_build(connector(local), 2025)
    assert _cli("apply", lcmd, pcmd, capsys)[0] == 0
    with psycopg.connect(local) as c:
        acnt = c.execute("SELECT hitter_acnt FROM cpbl.batting_gamelog WHERE year = 2025 AND kind_code = 'A' "
                         "AND game_sno = 100 ORDER BY hitter_acnt LIMIT 1").fetchone()[0]
    sql = ("UPDATE cpbl.batting_gamelog SET at_bats = at_bats + %s WHERE year = 2025 AND kind_code = 'A' "
           "AND game_sno = 100 AND hitter_acnt = %s")
    with mutated(local, sql, (1, acnt), sql, (-1, acnt)):
        second = builder.run_build(connector(local), 2025)
        assert second.status == "promoted"
        rc, out, _ = _cli("apply", lcmd, pcmd, capsys)
        assert rc == 0 and "RECONCILE=ok" in out
        builds, _, cur = _target_state(prod)
        assert builds == 2 and cur == [(2025, second.plan.build_id)]
    # 回指（回復路徑）同樣經同步生效；舊 build 不刪
    assert builder.run_promote_existing(connector(local), 2025, first.plan.build_id).code == 0
    assert _cli("apply", lcmd, pcmd, capsys)[0] == 0
    assert _target_state(prod)[2] == [(2025, first.plan.build_id)]


def test_conflicting_content_is_rejected_without_write(env, capsys):
    local, prod, lcmd, pcmd = env
    assert builder.run_build(connector(local), 2025).code == 0
    assert _cli("apply", lcmd, pcmd, capsys)[0] == 0
    with psycopg.connect(prod, autocommit=True) as c:  # 只在隔離「生產」庫暫停觸發器製造衝突
        c.execute("ALTER TABLE cpbl.team_comparison_row DISABLE TRIGGER USER")
        c.execute("UPDATE cpbl.team_comparison_row SET bat_ab = bat_ab + 1 WHERE team_code = 'AJL011' "
                  "AND scope = 'season'")
        c.execute("ALTER TABLE cpbl.team_comparison_row ENABLE TRIGGER USER")
    before = _target_state(prod)
    for action in ("plan", "apply"):
        rc, _, err = _cli(action, lcmd, pcmd, capsys)
        assert rc == sync.EXIT_REJECT and "同 build_id 內容不同" in err
    assert _target_state(prod) == before
    rc, _, _ = _cli("reconcile", lcmd, pcmd, capsys)
    assert rc == sync.EXIT_RECONCILE


def test_target_only_build_is_rejected(env, capsys):
    local, prod, lcmd, pcmd = env
    # 在「生產」庫放一個本機沒有的 build（模擬生產端獨立 writer）
    assert builder.run_build(connector(local), 2026).code == 0
    assert _cli("apply", lcmd, pcmd, capsys)[0] == 0
    reset_summary(local)
    assert builder.run_build(connector(local), 2025).code == 0
    rc, _, err = _cli("plan", lcmd, pcmd, capsys)
    assert rc == sync.EXIT_REJECT and "目標有本機沒有的 build" in err


def test_column_drift_and_missing_target_tables(env, capsys):
    local, prod, lcmd, pcmd = env
    assert builder.run_build(connector(local), 2025).code == 0
    with psycopg.connect(local, autocommit=True) as c:
        c.execute("ALTER TABLE cpbl.team_comparison_row ADD COLUMN drift_probe INTEGER")
    try:
        rc, _, err = _cli("plan", lcmd, pcmd, capsys)
        assert rc == sync.EXIT_SELF_CHECK and "drift_probe" in err
    finally:
        with psycopg.connect(local, autocommit=True) as c:
            c.execute("ALTER TABLE cpbl.team_comparison_row DROP COLUMN drift_probe")
    with psycopg.connect(prod, autocommit=True) as c:
        c.execute("ALTER TABLE cpbl.team_comparison_row RENAME TO team_comparison_row_hidden")
    try:
        rc, _, err = _cli("plan", lcmd, pcmd, capsys)
        assert rc == sync.EXIT_NO_TABLE
    finally:
        with psycopg.connect(prod, autocommit=True) as c:
            c.execute("ALTER TABLE cpbl.team_comparison_row_hidden RENAME TO team_comparison_row")
    assert _cli("plan", lcmd, pcmd, capsys)[0] == 0


def test_local_self_check_detects_tampered_digest(env, capsys):
    local, prod, lcmd, pcmd = env
    assert builder.run_build(connector(local), 2025).code == 0
    with psycopg.connect(local, autocommit=True) as c:
        c.execute("ALTER TABLE cpbl.team_comparison_row DISABLE TRIGGER USER")
        c.execute("UPDATE cpbl.team_comparison_row SET bat_h = bat_h + 1 WHERE team_code = 'ACN011' "
                  "AND scope = 'season'")
        c.execute("ALTER TABLE cpbl.team_comparison_row ENABLE TRIGGER USER")
    rc, _, err = _cli("plan", lcmd, pcmd, capsys)
    assert rc == sync.EXIT_SELF_CHECK and "rows_digest" in err
    assert _target_state(prod) == (0, 0, [])
