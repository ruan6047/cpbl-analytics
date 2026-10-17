"""#316 opt-in PG17契約實測；每例rollback，只使用本卡隔離DB。"""

import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from roster_284_support import seed
from test_roster_role_package import package
from test_roster_roles_v2 import provenance

from cpbl import db
from cpbl.ingest import run_roster
from cpbl.ingest.run_roster import _official_text
from cpbl.rosters.canonical import revision_hash_v2
from cpbl.rosters.parser import parse
from cpbl.rosters.role_store import annotate_package, preview_package
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


def real_package(c):
    parsed = parse(_official_text(2026, "E", "ADD011")[0])
    _, h, _ = prepare(c, parsed)
    submit(c, parsed, h["membership_hash"], pasted_origin())
    doc = package()
    for team in doc["teams"]:
        head = c.execute("SELECT roster_id,membership_hash,source_hash FROM cpbl.series_roster "
                         "WHERE year=2026 AND kind_code='E' AND team_code=%s",
                         (team["team_code"],)).fetchone()
        team.update(roster_id=str(head[0]), membership_hash=head[1], source_hash=head[2])
        latest = c.execute("SELECT revision,revision_hash FROM cpbl.roster_annotation_revision "
                           "WHERE roster_id=%s ORDER BY revision DESC LIMIT 1", (head[0],)).fetchone()
        team.update(expected_latest_revision=latest[0], expected_latest_hash=latest[1])
    return doc


def test_two_team_atomic_append_idempotency_and_restore_v1(connection):
    c, _ = connection
    doc = real_package(c)
    assert all(t["status"] == "revised" for t in preview_package(c, doc)["teams"])
    result = annotate_package(c, doc, "a" * 64)
    c.execute("SET CONSTRAINTS ALL IMMEDIATE")
    c.execute("SET CONSTRAINTS ALL DEFERRED")
    assert all(t["annotation_version"] == 2 for t in result["teams"])
    assert all(t["status"] == "unchanged" for t in annotate_package(c, doc, "a" * 64)["teams"])
    for team in doc["teams"]:
        r = next(r for r in result["teams"] if r["roster_id"] == team["roster_id"])
        team.update(expected_latest_revision=r["annotation_version"], expected_latest_hash=r["revision_hash"])
    restored = annotate_package(c, doc, "a" * 64, {t["roster_id"]: 1 for t in doc["teams"]})
    c.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert all(t["annotation_version"] == 3 for t in restored["teams"])
    assert c.execute("SELECT count(*) FROM cpbl.roster_annotation_revision "
                     "WHERE revision=3 AND role_format_version=1 AND tactical_roles IS NULL "
                     "AND roster_id IN (SELECT roster_id FROM cpbl.series_roster WHERE kind_code='E')"
                     ).fetchone()[0] == 64


def test_second_team_conflict_rolls_back_first_team(connection):
    from cpbl.rosters.store import RosterError
    c, _ = connection
    doc = real_package(c)
    # 依roster_id固定鎖序，讓第二隊失敗，證明第一隊也未留下半套版本。
    doc["teams"].sort(key=lambda t: t["roster_id"])
    doc["teams"][1]["expected_latest_hash"] = "f" * 64
    with pytest.raises(RosterError, match="基準已變更"):
        annotate_package(c, doc, "a" * 64)
    assert c.execute("SELECT count(*) FROM cpbl.roster_annotation_revision WHERE revision=2 "
                     "AND roster_id IN (SELECT roster_id FROM cpbl.series_roster WHERE kind_code='E')"
                     ).fetchone()[0] == 0


def test_approval_and_member_mutation_rejected_before_write(connection):
    from cpbl.rosters.store import RosterError
    c, _ = connection
    doc = real_package(c)
    with pytest.raises(RosterError, match="核准表hash"):
        annotate_package(c, doc, "f" * 64)
    doc["teams"][0]["members"][0]["announced_name"] += "錯"
    with pytest.raises(RosterError, match="公告姓名"):
        annotate_package(c, doc, "a" * 64)
    assert c.execute("SELECT count(*) FROM cpbl.roster_annotation_revision WHERE revision=2 "
                     "AND roster_id IN (SELECT roster_id FROM cpbl.series_roster WHERE kind_code='E')"
                     ).fetchone()[0] == 0


def test_restore_v2_preserves_hash_and_full_provenance(connection):
    import copy
    c, _ = connection
    doc = real_package(c)
    first = annotate_package(c, doc, "a" * 64)
    newer = copy.deepcopy(doc)
    for team in newer["teams"]:
        old = next(t for t in first["teams"] if t["roster_id"] == team["roster_id"])
        team.update(expected_latest_revision=2, expected_latest_hash=old["revision_hash"])
        for m in team["members"]:
            for p in m["role_provenance"]["roles"].values():
                p["original_evidence"] += " 新證據"
    second = annotate_package(c, newer, "a" * 64)
    for team in newer["teams"]:
        old = next(t for t in second["teams"] if t["roster_id"] == team["roster_id"])
        team.update(expected_latest_revision=3, expected_latest_hash=old["revision_hash"])
    restored = annotate_package(c, newer, "a" * 64, {t["roster_id"]: 2 for t in doc["teams"]})
    c.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert {t["revision_hash"] for t in first["teams"]} == {t["revision_hash"] for t in restored["teams"]}
    assert all(t["annotation_version"] == 4 for t in restored["teams"])


def test_cli_v2_invalid_approval_zero_writes(connection, monkeypatch, tmp_path, capsys):
    import json
    from contextlib import contextmanager
    c, _ = connection
    doc = real_package(c)
    file = tmp_path / "roles.json"
    file.write_text(json.dumps(doc, ensure_ascii=False))
    @contextmanager
    def same_connection():
        yield c
    monkeypatch.setattr(db, "conn", same_connection)
    assert run_roster.run(["annotate", str(file), "--format", "roles-v2",
                           "--confirm-approval-hash", "f" * 64]) == 15
    assert "核准表hash" in capsys.readouterr().err
    assert c.execute("SELECT count(*) FROM cpbl.roster_annotation_revision WHERE revision=2 "
                     "AND roster_id IN (SELECT roster_id FROM cpbl.series_roster WHERE kind_code='E')"
                     ).fetchone()[0] == 0
