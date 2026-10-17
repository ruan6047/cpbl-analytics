"""#316 opt-in PG17契約實測；每例rollback，只使用本卡隔離DB。"""

import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from roster_284_support import seed
from test_roster_roles_v2 import provenance

from cpbl import db
from cpbl.ingest.run_roster import _official_text
from cpbl.rosters.canonical import revision_hash_v2
from cpbl.rosters.parser import parse
from cpbl.rosters.store import pasted_origin, prepare, submit


@pytest.fixture(scope="module")
def isolated_pool():
    dsn = os.environ.get("CPBL316_TEST_DSN")
    if not dsn:
        pytest.skip("CPBL316_TEST_DSN未設；skip不算實測")
    d = conninfo_to_dict(dsn)
    assert (d.get("host"), d.get("port"), d.get("dbname")) == (
        "127.0.0.1", "55316", "cpbl_316_test")
    with ConnectionPool(dsn, min_size=0, max_size=2, configure=db._configure) as pool:
        old = db._pool
        db._pool = pool
        try:
            db.migrate()
            yield pool
        finally:
            db._pool = old


@pytest.fixture
def connection(isolated_pool):
    with db.conn() as c:
        assert c.execute("SELECT current_database()").fetchone()[0] == "cpbl_316_test"
        seed(c)
        parsed = parse(_official_text(2026, "E", "ACN011")[0])
        _, h, _ = prepare(c, parsed)
        result = submit(c, parsed, h["membership_hash"], pasted_origin())
        c.execute("SET CONSTRAINTS ALL IMMEDIATE")
        c.execute("SET CONSTRAINTS ALL DEFERRED")
        try:
            yield c, result["roster_id"]
        finally:
            c.rollback()


def insert_v2(c, rid, mutate=lambda rows: rows):
    members = c.execute("SELECT player_id,official_position FROM cpbl.series_roster_member "
                        "WHERE roster_id=%s ORDER BY player_id", (rid,)).fetchall()
    rows = [(pid, ["先發", "長中繼"] if pos == "投手" else ["主力"],
             provenance(["先發", "長中繼"] if pos == "投手" else ["主力"]))
            for pid, pos in members]
    h = revision_hash_v2(rows)
    rows = mutate(rows)
    with c.cursor() as cur:
        cur.executemany(
            "INSERT INTO cpbl.roster_annotation_revision "
            "(roster_id,revision,player_id,tactical_role,revision_hash,role_format_version,"
            "tactical_roles,role_provenance) VALUES (%s,2,%s,'unclassified',%s,2,%s,%s)",
            [(rid, pid, h, roles, Jsonb(p)) for pid, roles, p in rows])
    c.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_v2_append_preserves_v1_and_immutable_guard(connection):
    c, rid = connection
    before = c.execute("SELECT * FROM cpbl.roster_annotation_revision WHERE roster_id=%s "
                       "AND revision=1 ORDER BY player_id", (rid,)).fetchall()
    insert_v2(c, rid)
    after = c.execute("SELECT * FROM cpbl.roster_annotation_revision WHERE roster_id=%s "
                      "AND revision=1 ORDER BY player_id", (rid,)).fetchall()
    assert before == after
    with pytest.raises(psycopg.errors.RestrictViolation), c.transaction():
        c.execute("UPDATE cpbl.roster_annotation_revision SET tactical_role='主力' WHERE roster_id=%s", (rid,))


@pytest.mark.parametrize("roles,p", [(None, None), ([], {}), (["先發", "先發"], {}),
                                    (["先發", None], {}), (["輪值"], {}), (["先發"], None)])
def test_sql_validator_fails_closed(connection, roles, p):
    c, _ = connection
    assert c.execute("SELECT cpbl.roster_roles_v2_valid(%s::text[],%s::jsonb)",
                     (roles, Jsonb(p))).fetchone()[0] is False


def test_official_position_constraint_rejects_cross_role(connection):
    c, rid = connection
    def cross(rows):
        return [(pid, ["工具人"], provenance(["工具人"])) for pid, _, _ in rows]
    with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
        insert_v2(c, rid, cross)


def test_mixed_approval_sources_rejected(connection):
    c, rid = connection
    def mixed(rows):
        rows[0][2]["approval_table_sha256"] = "c" * 64
        return rows
    with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
        insert_v2(c, rid, mixed)


@pytest.mark.parametrize("key", ["origin", "source_ids", "original_basis", "original_evidence"])
def test_sql_provenance_json_null_rejected(connection, key):
    c, _ = connection
    p = provenance(["先發"])
    p["roles"]["先發"][key] = None
    assert c.execute("SELECT cpbl.roster_roles_v2_valid(%s::text[],%s::jsonb)",
                     (["先發"], Jsonb(p))).fetchone()[0] is False
