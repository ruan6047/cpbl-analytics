"""#288 S07 WP-AWARDS DB 層：只在**自行擁有的隔離 Postgres**（``CPBL_ISOLATED_TEST_DSN``）執行。

比照 ``test_playoffs_overview_isolated.py``：未設 DSN 即 skip；該庫已有 ``cpbl`` schema 即拒跑；結束時 DROP
自建 schema。⛔ 絕不在共用本機庫或正式庫建表寫列。所有獎項內容都是合成值（官方尚未公布）。

驗只有真 SQL 才看得出來的事：

1. migration 078 冪等：同一庫連跑兩次不報錯、不重複。
2. 匯入 CLI：dry-run 不留列；寫入、同內容冪等、改內容追加 revision；缺官方 URL 與重複 revision 拒收（退出碼）。
3. 不可變：UPDATE／DELETE／TRUNCATE 拒絕；得主不能掛在 not_published。
4. 同步語意：用 ``refresh-cpbl-prod.sh`` 的 sync_table **同一句** upsert（從腳本解析欄位清單）重送同值＝no-op；
   同鍵不同值＝被觸發器擋下；腳本清單與表欄位完全一致（漏欄守衛會放行）。
5. 讀端：只取最新 revision、共同得主依序；overview 在表不存在時退化（見 summary isolated 測試）。
"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import pytest

from cpbl.ingest import run_import_series_awards as cli
from cpbl.playoffs import series_awards as sa

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "migrations" / "078_series_award_revisions.sql").read_text(encoding="utf-8")
SCRIPT = (ROOT / "scripts" / "refresh-cpbl-prod.sh").read_text(encoding="utf-8")
URL = "https://www.cpbl.com.tw/news/view?id=999"


@pytest.fixture(scope="module")
def dsn():
    value = os.environ.get("CPBL_ISOLATED_TEST_DSN")
    if not value:
        pytest.skip("未設 CPBL_ISOLATED_TEST_DSN（自行擁有的隔離 Postgres）")
    import psycopg

    with psycopg.connect(value, autocommit=True) as c:
        if c.execute("SELECT to_regnamespace('cpbl')").fetchone()[0] is not None:
            pytest.fail("隔離庫已有 cpbl schema：拒絕在疑似真實資料庫上建表寫列")
        c.execute("CREATE SCHEMA cpbl; CREATE TABLE cpbl.team_dim (team_code text PRIMARY KEY)")
        try:
            c.execute("INSERT INTO cpbl.team_dim VALUES ('ACN011'), ('AAA011')")
            c.execute(MIGRATION)
            c.execute(MIGRATION)          # 1. 冪等：第二次照跑
            yield value
        finally:
            c.execute("DROP SCHEMA cpbl CASCADE")


@contextmanager
def _connect(dsn):
    import psycopg

    with psycopg.connect(dsn) as c:
        yield c


def _write(tmp_path, payload, *args, dsn):
    f = tmp_path / "in.json"
    f.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return cli.run([str(f), *args], connect=lambda: _connect(dsn))


def _count(dsn, sql="SELECT count(*) FROM cpbl.series_award_revision"):
    with _connect(dsn) as c:
        return c.execute(sql).fetchone()[0]


def payload(**kw):
    base = {"year": 2026, "kind_code": "C", "status": "published", "source_url": URL,
            "checked_at": "2026-10-26T21:00:00+08:00",
            "awards": [{"award_name": "測試最有價值球員", "award_type": "series_mvp",
                        "winners": [{"winner_name": "乙", "player_id": "0000000002", "team_code": "ACN011"},
                                    {"winner_name": "甲"}]},
                       {"award_name": "測試其他獎", "award_type": "other",
                        "winners": [{"winner_name": "丙", "team_code": "AAA011"}]}]}
    base.update(kw)
    return base


def test_migration_is_idempotent_and_creates_both_tables(dsn):
    with _connect(dsn) as c:
        names = {r[0] for r in c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='cpbl' AND tablename LIKE 'series_award_%'")}
        trig = {r[0] for r in c.execute(
            "SELECT tgname FROM pg_trigger WHERE tgname LIKE 'series_award_%' AND NOT tgisinternal")}
        c.execute(MIGRATION)              # 第三次：在已有資料前後都可重跑
    assert names == {"series_award_revision", "series_award_winner"}
    assert len(trig) == 5


def test_cli_dry_run_write_idempotent_append_and_rejections(dsn, tmp_path, capsys):
    assert _write(tmp_path, payload(), "--dry-run", dsn=dsn) == 0
    assert _count(dsn) == 0                                         # dry-run 不留列
    assert "dry-run" in capsys.readouterr().out

    assert _write(tmp_path, payload(), dsn=dsn) == 0                # created revision 1
    assert _write(tmp_path, payload(checked_at="2026-10-27T09:00:00+08:00"), dsn=dsn) == 0   # 同內容
    assert "unchanged revision 1" in capsys.readouterr().out
    assert _count(dsn) == 1

    assert _write(tmp_path, payload(source_url=None), dsn=dsn) == cli.EXIT_INVALID          # 缺官方 URL
    assert _write(tmp_path, payload(source_url="https://example.com/x"), dsn=dsn) == cli.EXIT_INVALID
    assert _write(tmp_path, payload(revision=1), dsn=dsn) == cli.EXIT_DUPLICATE             # 重複 revision
    assert _count(dsn) == 1

    changed = payload(awards=[{"award_name": "測試最有價值球員", "award_type": "series_mvp",
                               "winners": [{"winner_name": "甲"}, {"winner_name": "乙", "player_id": "0000000002"}]}])
    assert _write(tmp_path, changed, dsn=dsn) == 0                  # 內容不同（共同得主順序）⇒ revision 2
    assert _count(dsn) == 2
    assert _write(tmp_path, payload(status="not_published", awards=[], kind_code="E"), dsn=dsn) == 0

    with _connect(dsn) as c:
        latest = sa.read_latest(c.cursor(), 2026)
    assert latest["C"]["revision"] == 2
    assert [w["winner_name"] for w in latest["C"]["winners"]] == ["甲", "乙"]     # 依官方順序
    assert latest["E"]["status"] == "not_published" and latest["E"]["winners"] == []
    out = sa.awards_json(latest, "C")
    assert out["status"] == "published" and [w["name"] for w in out["awards"][0]["winners"]] == ["甲", "乙"]
    assert sa.awards_json(latest, "E")["status"] == "not_published"


def test_rows_are_immutable_and_winners_need_published(dsn):
    import psycopg

    with _connect(dsn) as c:
        if not c.execute("SELECT 1 FROM cpbl.series_award_revision LIMIT 1").fetchone():
            pytest.skip("依賴上一個測試寫入的列")
    for sql in ("UPDATE cpbl.series_award_revision SET status='published' WHERE kind_code='E'",
                "DELETE FROM cpbl.series_award_revision WHERE kind_code='E'",
                "UPDATE cpbl.series_award_winner SET winner_name='x'",
                "DELETE FROM cpbl.series_award_winner",
                "TRUNCATE cpbl.series_award_winner",
                "TRUNCATE cpbl.series_award_revision CASCADE"):
        with _connect(dsn) as c, pytest.raises(psycopg.errors.RestrictViolation):
            c.execute(sql)
    with _connect(dsn) as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute("INSERT INTO cpbl.series_award_winner VALUES (2026,'E',1,1,1,'x','other',NULL,'x',NULL)")
    with _connect(dsn) as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute("INSERT INTO cpbl.series_award_revision (year,kind_code,revision,status,source_url,source_sha256,"
                  "checked_at) VALUES (2026,'C',9,'published','http://www.cpbl.com.tw/x',repeat('a',64),now())")


def _sync_spec(table: str) -> tuple[str, list[str]]:
    m = re.search(rf'^sync_table {table} "([^"]+)" (.+)$', SCRIPT, re.M)
    assert m, f"refresh-cpbl-prod.sh 沒有 {table} 的 sync_table 行"
    return m.group(1), m.group(2).split()


@pytest.mark.parametrize("table", ["series_award_revision", "series_award_winner"])
def test_sync_table_list_matches_columns_and_upsert_is_noop_or_loud(dsn, table):
    import psycopg

    pk, cols = _sync_spec(table)
    with _connect(dsn) as c:
        actual = [r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='cpbl' AND table_name=%s "
            "ORDER BY ordinal_position", (table,))]
    assert sorted(pk.split(",") + cols) == sorted(actual)            # 漏欄守衛（sync_table）會放行

    set_clause = ",".join(f"{x}=EXCLUDED.{x}" for x in cols)
    tgt = ",".join(f"tgt.{x}" for x in cols)
    new = ",".join(f"EXCLUDED.{x}" for x in cols)
    upsert = (f"INSERT INTO cpbl.{table} AS tgt SELECT * FROM _stg ON CONFLICT ({pk}) DO UPDATE SET {set_clause} "
              f"WHERE ROW({tgt}) IS DISTINCT FROM ROW({new})")
    with _connect(dsn) as c:   # 重送同值：no-op（觸發器不會被觸發）
        c.execute(f"CREATE TEMP TABLE _stg (LIKE cpbl.{table} INCLUDING DEFAULTS) ON COMMIT DROP")
        c.execute(f"INSERT INTO _stg SELECT * FROM cpbl.{table}")
        n = c.execute("SELECT count(*) FROM _stg").fetchone()[0]
        assert n >= 1
        assert c.execute(upsert).rowcount == 0
    col = "source_sha256" if table == "series_award_revision" else "winner_name"
    val = "'" + "b" * 64 + "'" if col == "source_sha256" else "'改過'"
    with _connect(dsn) as c, pytest.raises(psycopg.errors.RestrictViolation):   # 同鍵不同值：大聲失敗
        c.execute(f"CREATE TEMP TABLE _stg (LIKE cpbl.{table} INCLUDING DEFAULTS) ON COMMIT DROP")
        c.execute(f"INSERT INTO _stg SELECT * FROM cpbl.{table}")
        c.execute(f"UPDATE _stg SET {col} = {val}")
        c.execute(upsert)
