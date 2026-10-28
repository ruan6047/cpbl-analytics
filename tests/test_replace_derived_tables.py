"""#383 段 2 P-B 整表替換腳本的純函式測試（不連 DB；DATABASE_URL 指向不存在的 127.0.0.1:1）。

守的是三件事，任何一件被拿掉都要轉紅：
1. 寫入交易 BEGIN 後的第一個語句是 current_database() 守衛，且比對的是 --expect-db；
2. 交易內對 11 表逐表斷言列數＋md5，md5 字面值就是 manifest 的值；
3. 送出前形狀守衛會拒絕缺守衛、缺斷言、多出禁止語句的 payload。
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("replace_derived_tables", ROOT / "docs" / "research" / "ISSUE-383" / "replace_derived_tables.py")
pb = importlib.util.module_from_spec(_spec)
sys.modules["replace_derived_tables"] = pb
_spec.loader.exec_module(pb)


def _manifest_and_copies() -> tuple[dict, dict[str, bytes]]:
    tables, copies = {}, {}
    for i, t in enumerate(pb.TABLES):
        body = f"{2018 + i}\tA\t{i}.5\n{2019 + i}\tA\t\\\\N-literal\n".encode()
        copies[t] = body
        tables[t] = {
            "cols": ["year", "kind_code", "v"],
            "pk": ["year", "kind_code"],
            "rows": 2,
            "md5": hashlib.md5(t.encode()).hexdigest(),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
    return {"tables": tables}, copies


def _sql_text(expect_db: str = "cpbl_383s2") -> str:
    m, c = _manifest_and_copies()
    return pb.build_apply_sql(m, c, expect_db).decode()


def test_eleven_tables_match_plan():
    assert pb.TABLES == (
        "fielding_innings", "catcher_runs", "batter_traits", "pitcher_traits",
        "run_expectancy", "sabr_run_values", "batter_wsb", "batter_re24", "pitcher_re24",
        "run_dist", "win_expectancy",
    )


def test_guard_is_first_statement_and_compares_expect_db():
    lines = [x for x in _sql_text("cpbl_xyz").split("\n") if x and not x.startswith("\\")]
    assert lines[0] == "BEGIN;"
    assert lines[1] == "DO $pbguard$ BEGIN"
    assert lines[2] == "  IF current_database() <> 'cpbl_xyz' THEN"
    assert "RAISE EXCEPTION 'PB-GUARD" in lines[3]


def test_every_table_has_rows_and_md5_assertion_with_manifest_values():
    m, _ = _manifest_and_copies()
    sql = _sql_text()
    body = sql.split("DO $pbassert$", 1)[1].split("END $pbassert$;", 1)[0]
    for t in pb.TABLES:
        want = f"  IF n <> 2 OR h <> '{m['tables'][t]['md5']}' THEN"
        assert want in body.split("\n"), t
        # 斷言的 digest 是同一個產生器、針對同一張表
        assert pb.table_digest_sql(t, ["year", "kind_code", "v"], ["year", "kind_code"]) + " INTO n, h;" in body
        assert f"RAISE EXCEPTION 'PB-ASSERT {t}:" in body


def test_assertion_runs_after_all_copies_and_before_commit():
    sql = _sql_text()
    last_copy_end = sql.rindex("\n\\.\n")
    assert last_copy_end < sql.index("DO $pbassert$") < sql.rindex("COMMIT;")


def test_delete_then_copy_per_table_in_one_transaction():
    sql = _sql_text()
    assert sql.count("BEGIN;\n") == 1 and sql.count("COMMIT;") == 1
    pos = [sql.index(f"DELETE FROM cpbl.{t};\nCOPY cpbl.{t} (year, kind_code, v) FROM stdin;\n") for t in pb.TABLES]
    assert pos == sorted(pos)
    assert "LOCK TABLE cpbl.fielding_innings" in sql


def test_shape_guard_accepts_generated_payload():
    m, c = _manifest_and_copies()
    assert pb.check_payload_shape(pb.build_apply_sql(m, c, "cpbl_383s2")) == []


@pytest.mark.parametrize(
    ("mutate", "expect"),
    [
        (lambda s: s.replace("DO $pbguard$ BEGIN\n", "", 1), "庫名守衛"),
        (lambda s: re.sub(r"  IF current_database\(\) <> [^\n]*\n", "", s), "缺庫名比對"),
        (lambda s: s.replace("DO $pbassert$ DECLARE n bigint; h text; BEGIN\n", "", 1), "缺交易內斷言"),
        (lambda s: re.sub(r"  IF n <> 2 OR h <> '[0-9a-f]{32}' THEN\n", "  IF n <> 2 THEN\n", s, count=1), "md5 斷言數"),
        (lambda s: s.replace("COMMIT;\n", "TRUNCATE cpbl.run_dist;\nCOMMIT;\n"), "禁止語句"),
        (lambda s: s.replace("DELETE FROM cpbl.run_dist;\n", ""), "DELETE 形狀"),
    ],
)
def test_shape_guard_rejects_mutations(mutate, expect):
    why = pb.check_payload_shape(mutate(_sql_text()).encode())
    assert any(expect in w for w in why), why


def test_validate_manifest_rejects_sha_mismatch_and_missing_table():
    m, c = _manifest_and_copies()
    c["run_dist"] = c["run_dist"] + b"9\tA\t1\n"
    with pytest.raises(pb.PayloadError, match="sha256"):
        pb.validate_manifest(m, c)
    m, c = _manifest_and_copies()
    del m["tables"]["win_expectancy"]
    with pytest.raises(pb.PayloadError, match="表集合"):
        pb.validate_manifest(m, c)


def test_validate_manifest_rejects_terminator_line_and_bad_ident():
    m, c = _manifest_and_copies()
    c["run_dist"] = b"\\.\n\\.\n"
    m["tables"]["run_dist"]["sha256"] = hashlib.sha256(c["run_dist"]).hexdigest()
    with pytest.raises(pb.PayloadError, match="終止符"):
        pb.validate_manifest(m, c)
    m, c = _manifest_and_copies()
    m["tables"]["run_dist"]["cols"] = ["year; DROP TABLE x", "kind_code", "v"]
    with pytest.raises(pb.PayloadError, match="識別字"):
        pb.validate_manifest(m, c)


def test_export_stream_roundtrip_splits_tables():
    meta = {t: {"cols": ["year", "kind_code", "v"], "pk": ["year", "kind_code"]} for t in pb.TABLES}
    sql = pb.build_export_sql(meta)
    assert sql.index("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;") < sql.index("COPY (SELECT")
    # psql 單引號內反斜線成對，才會印出 `\.PB-TABLE `
    assert "\\echo '\\\\.PB-TABLE fielding_innings'" in sql
    assert max(sql.index(f"'PB-DIGEST|{t}|'") for t in pb.TABLES) < sql.index("\\echo")
    stream = b"PB-DB|cpbl_383s2|2026-10-28\n"
    stream += b"".join(f"PB-DIGEST|{t}|2|{'a' * 32}\n".encode() for t in pb.TABLES)
    for i, t in enumerate(pb.TABLES):
        stream += f"\\.PB-TABLE {t}\n".encode()
        stream += f"{i}\tA\t\\\\x\n{i}\tB\t\\N\n".encode()
    stream += b"\\.PB-TABLE __END__\n"
    db, digests, copies = pb.parse_export_stream(stream)
    assert db == "cpbl_383s2"
    assert set(digests) == set(copies) == set(pb.TABLES)
    assert copies["run_dist"] == b"9\tA\t\\\\x\n9\tB\t\\N\n"


def test_export_stream_without_end_marker_fails_closed():
    with pytest.raises(pb.PayloadError, match="中途結束"):
        pb.parse_export_stream(b"\\.PB-TABLE run_dist\n1\tA\n")


def test_target_argv_readonly_and_prod_db_from_env():
    ro = pb.target_argv("local:cpbl_383s2", write=False)
    assert ro[:4] == ["docker", "exec", "-i", pb.LOCAL_CONTAINER]
    assert "SET default_transaction_read_only = on" in ro and ro[-1] == "cpbl_383s2"
    rw = pb.target_argv("local:cpbl_383s2", write=True)
    assert "SET default_transaction_read_only = on" not in rw
    prod = pb.target_argv("prod", write=True)
    assert prod[:3] == ["ssh", "-o", "BatchMode=yes"] and '-d "$DB_NAME"' in prod[-1]
    with pytest.raises(pb.PayloadError):
        pb.target_argv("local:cpbl; rm -rf /", write=False)
    with pytest.raises(pb.PayloadError):
        pb.target_argv("cpbl", write=False)
