"""#284 隔離 DB 演練（opt-in；E02、E05–E13、E15–E17、E20）。

只連本卡隔離資源：`CPBL284_TEST_DSN`＝容器 cpbl284-pg（127.0.0.1:55284）的 cpbl_test_284；
未設＝skip（⛔ skip 不算通過），設錯＝fail。每個測試先 reset＋灌 fixture 種子。
樣本＝official_population 2026 E 真實 64 人；變異是對真實樣本的單點改動，⛔ 不自造 32 人。
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime

import psycopg
import pytest
from psycopg_pool import ConnectionPool
from roster_284_support import LOCAL_DB, fixture, isolated_dsn, reset, seed

from cpbl import db
from cpbl.ingest import run_roster
from cpbl.ingest.run_roster import _official_text
from cpbl.reports.official_population import load as load_official
from cpbl.rosters.parser import parse
from cpbl.rosters.store import (
    ELIGIBILITY_NOTE,
    EXIT_CONFLICT,
    EXIT_DRAFT,
    EXIT_VIOLATION,
    RosterError,
    annotate,
    pasted_origin,
    prepare,
    read_roster,
    submit,
)


@pytest.fixture(scope="module")
def dsn():
    return isolated_dsn("CPBL284_TEST_DSN", LOCAL_DB)


@pytest.fixture
def pool(dsn, monkeypatch):
    with ConnectionPool(dsn, min_size=0, max_size=4, timeout=5, configure=db._configure) as p:
        monkeypatch.setattr(db, "_pool", p)
        with db.conn() as c:
            assert c.execute("SELECT current_database()").fetchone()[0] == LOCAL_DB[2]
        db.migrate()
        with db.conn() as c:
            reset(c)
            seed(c)
        yield p


def text(team="ACN011"):
    return _official_text(2026, "E", team)[0]


def hash_of(t):
    with db.conn() as c:
        _, h, _ = prepare(c, parse(t))
    return h["membership_hash"]


def do_submit(t, origin=None):
    with db.conn() as c:
        return submit(c, parse(t), hash_of(t), origin or pasted_origin())


def counts():
    with db.conn() as c:
        return tuple(c.execute(f"SELECT count(*) FROM cpbl.{t}").fetchone()[0]
                     for t in ("series_roster", "series_roster_member", "roster_annotation_revision"))


# ------------------------------------------------------------------ E16


def test_e16_migrate_twice_idempotent(pool):
    first = db.migrate()
    second = db.migrate()
    assert first == second and first[-1] == "076_series_rosters.sql"
    with db.conn() as c:
        tables = {r[0] for r in c.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='cpbl' "
            "AND table_name IN ('series_roster','series_roster_member','roster_annotation_revision')")}
    assert len(tables) == 3


# ------------------------------------------------------------------ E02


def test_e02_31_and_33_rejected_zero_writes(pool, capsys, tmp_path):
    lines = text().splitlines()
    i = next(n for n, ln in enumerate(lines) if "@id=" in ln)
    f31 = tmp_path / "r31.txt"
    f31.write_text("\n".join(lines[:i] + lines[i + 1:]), encoding="utf-8")
    members = {m["player_id"] for r in load_official(2026, "E") for m in r["members"]}
    extra = next(r for r in fixture()["team_roster"] if r[1] == "ACN011" and r[2] not in members)
    f33 = tmp_path / "r33.txt"
    f33.write_text(text().replace("[外野手]\n", f"[外野手]\n{extra[3]} @id={extra[2]}\n"), encoding="utf-8")
    assert run_roster.run(["preview", str(f31)]) == EXIT_VIOLATION
    assert "人數 31 ≠ 32" in capsys.readouterr().out
    assert run_roster.run(["preview", str(f33)]) == EXIT_VIOLATION
    assert "人數 33 ≠ 32" in capsys.readouterr().out
    for f in (f31, f33):
        assert run_roster.run(["submit", str(f), "--confirm-hash", "0" * 64]) == EXIT_VIOLATION
    assert counts() == (0, 0, 0)


# ------------------------------------------------------------------ E05／E06


def test_e05_same_name_draft_then_explicit_id_resolves(pool, tmp_path, capsys):
    with db.conn() as c:  # 佐證變異：真實同名 0000000108 加一列 2026/ACN011 佐證
        c.execute("INSERT INTO cpbl.team_roster (year, team_code, player_id, name) "
                  "VALUES (2026, 'ACN011', '0000000108', '勝騎士')")
    f = tmp_path / "same.txt"
    f.write_text(text().replace("勝騎士 @id=0000005604", "勝騎士"), encoding="utf-8")
    assert run_roster.run(["preview", str(f)]) == EXIT_DRAFT
    out = capsys.readouterr().out
    assert "同名多重命中 2 人" in out and "候選 0000000108" in out and "候選 0000005604" in out
    f.write_text(text(), encoding="utf-8")
    assert run_roster.run(["preview", str(f)]) == 0
    assert counts() == (0, 0, 0)


def test_e06_id_name_conflict(pool, tmp_path, capsys):
    f = tmp_path / "conflict.txt"
    f.write_text(text().replace("勝騎士 @id=0000005604", "喬登 @id=0000005604"), encoding="utf-8")
    assert run_roster.run(["preview", str(f)]) == EXIT_DRAFT
    assert "ID/name 不符" in capsys.readouterr().out


# ------------------------------------------------------------------ E07


def test_e07_no_a_games_still_submits_and_shows_none_not_zero(pool, capsys):
    pid = "0000007293"  # 鍾允華（ADD011，有 team_roster 佐證）
    with db.conn() as c:
        c.execute("DELETE FROM cpbl.pitching_gamelog WHERE pitcher_acnt=%s AND year=2026 AND kind_code='A'", (pid,))
        c.execute("DELETE FROM cpbl.batting_gamelog WHERE hitter_acnt=%s AND year=2026 AND kind_code='A'", (pid,))
    result = do_submit(text("ADD011"))
    assert result["status"] == "created"
    with db.conn() as c, c.cursor() as cur:
        r = read_roster(cur, 2026, "E", "ADD011")
    assert len(r["members"]) == 32
    row = next(m for m in r["members"] if m["player_id"] == pid)
    assert row["a_games"] is None
    assert run_roster.run(["show", "--year", "2026", "--series", "E", "--team", "ADD011"]) == 0
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if pid in ln)
    assert "本季A出賽=無" in line
    assert any("本季A出賽=" in ln and "本季A出賽=無" not in ln for ln in out.splitlines())


# ------------------------------------------------------------------ E08


def test_e08_import_limit_real_and_variants(pool):
    with db.conn() as c:
        prep, _, _ = prepare(c, parse(text("ADD011")))
    assert prep.status == "ready" and len(prep.import_check["verified_imports"]) == 3
    with db.conn() as c:
        c.execute("UPDATE cpbl.players SET country='美國' WHERE id='0000006716'")
    with pytest.raises(RosterError) as exc:
        do_submit(text("ADD011"))
    assert exc.value.code == EXIT_VIOLATION and "已核洋將 4 人" in str(exc.value)
    assert counts() == (0, 0, 0)
    with db.conn() as c:
        c.execute("UPDATE cpbl.players SET country=NULL WHERE id='0000006716'")
    result = do_submit(text("ADD011"))
    with db.conn() as c:
        ic = c.execute("SELECT import_check FROM cpbl.series_roster WHERE roster_id=%s",
                       (result["roster_id"],)).fetchone()[0]
    assert ic["complete"] is False and ic["unknown"] == [{"player_id": "0000006716", "name": "張翔"}]


# ------------------------------------------------------------------ E09／E10 雙連線競爭


def _race(dsn, text_a, text_b):
    """A 提交但不 commit；B 同時提交應卡在唯一鍵上等待；A commit 後 B 才返回。"""
    results, errors = {}, {}
    a = psycopg.connect(dsn)
    b = psycopg.connect(dsn)
    watcher = psycopg.connect(dsn, autocommit=True)
    try:
        results["a"] = submit(a, parse(text_a), hash_of(text_a), pasted_origin())
        b_pid = b.info.backend_pid

        def run_b():
            try:
                results["b"] = submit(b, parse(text_b), hash_of(text_b), pasted_origin())
                b.commit()
            except RosterError as exc:
                b.rollback()
                errors["b"] = exc

        t = threading.Thread(target=run_b)
        t.start()
        waited = False
        for _ in range(100):
            row = watcher.execute(
                "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (b_pid,)).fetchone()
            if row and row[0] == "Lock":
                waited = True
                break
            time.sleep(0.05)
        a.commit()
        t.join(10)
        return results, errors, waited
    finally:
        a.close()
        b.close()
        watcher.close()


def test_e09_concurrent_same_content_one_roster(pool, dsn):
    results, errors, waited = _race(dsn, text(), text())
    assert waited, "第二連線應確實等待第一連線的唯一鍵"
    assert not errors
    assert results["a"]["status"] == "created" and results["b"]["status"] == "idempotent"
    assert results["a"]["roster_id"] == results["b"]["roster_id"]
    assert counts() == (1, 32, 32)


def test_e10_concurrent_different_content_one_wins(pool, dsn):
    other = text().replace("@source https://", "@source https://mirror.")
    results, errors, waited = _race(dsn, text(), other)
    assert waited
    assert results["a"]["status"] == "created" and "b" not in results
    assert errors["b"].code == EXIT_CONFLICT
    assert "source_url" in errors["b"].detail["diff"]["source_changes"]
    assert counts() == (1, 32, 32)


# ------------------------------------------------------------------ E11


def test_e11_idempotent_variants_and_rejections(pool):
    first = do_submit(text())
    with db.conn() as c:
        sub_at = c.execute("SELECT submitted_at FROM cpbl.series_roster").fetchone()[0]
    lines = text().splitlines()
    head, body = lines[:5], lines[5:]
    pitchers = [ln for ln in body if "@id=" in ln][:15]
    shuffled = "\n".join(head + ["", "  [投手]  "] + [f"  {p}  " for p in reversed(pitchers)]
                         + [""] + body[body.index("[捕手]"):])
    roles = text().replace("羅戈 @id=0000005151", "羅戈 @id=0000005151 #輪值")
    for variant in (shuffled, roles):
        again = do_submit(variant)
        assert again["status"] == "idempotent" and again["roster_id"] == first["roster_id"]
        assert again["submitted_at"] == first["submitted_at"]
    assert "annotate" in do_submit(roles).get("notice", "")
    mutations = {
        "source_changes": text().replace("@source https://", "@source https://mirror."),
        "published": text().replace("@published 2026-10-08", "@published 2026-10-09"),
        "position_changes": text().replace("[捕手]\n", "[捕手]\n羅戈 @id=0000005151\n").replace(
            "羅戈 @id=0000005151\n鄭浩均", "鄭浩均", 1),
    }
    for key, variant in mutations.items():
        with pytest.raises(RosterError) as exc:
            do_submit(variant)
        assert exc.value.code == EXIT_CONFLICT, key
    members = {m["player_id"] for r in load_official(2026, "E") for m in r["members"]}
    extra = next(r for r in fixture()["team_roster"] if r[1] == "ACN011" and r[2] not in members)
    swap = text().replace("岳政華 @id=0000005571", f"{extra[3]} @id={extra[2]}")
    with pytest.raises(RosterError) as exc:
        do_submit(swap)
    diff = exc.value.detail["diff"]
    assert diff["added_ids"] == [extra[2]] and diff["removed_ids"] == ["0000005571"]
    with db.conn() as c:
        assert c.execute("SELECT submitted_at FROM cpbl.series_roster").fetchone()[0] == sub_at
    assert counts() == (1, 32, 32)


# ------------------------------------------------------------------ E12／E13


def test_e12_no_roles_revision1_all_unclassified(pool):
    r = do_submit(text())
    with db.conn() as c:
        roles = c.execute("SELECT DISTINCT revision, tactical_role FROM cpbl.roster_annotation_revision "
                          "WHERE roster_id=%s", (r["roster_id"],)).fetchall()
    assert roles == [(1, "unclassified")]


def test_e13_annotate_new_revision_keeps_membership_and_history(pool, tmp_path):
    r = do_submit(text())
    snap = "SELECT roster_id, membership_hash, source_hash, submitted_at FROM cpbl.series_roster"
    rev1 = ("SELECT player_id, tactical_role, revision_hash, changed_at FROM cpbl.roster_annotation_revision "
            "WHERE revision=1 ORDER BY player_id")
    with db.conn() as c:
        before_head, before_rev1 = c.execute(snap).fetchall(), c.execute(rev1).fetchall()
    annotated = (text().replace("羅戈 @id=0000005151", "羅戈 @id=0000005151 #輪值")
                 .replace("江坤宇 @id=0000004636", "江坤宇 @id=0000004636 #主力"))
    with db.conn() as c:
        out = annotate(c, parse(annotated))
    assert out["status"] == "revised" and out["annotation_version"] == 2
    with db.conn() as c:
        assert annotate(c, parse(annotated))["status"] == "unchanged"
        assert c.execute(snap).fetchall() == before_head
        assert c.execute(rev1).fetchall() == before_rev1
        roles = dict(c.execute("SELECT player_id, tactical_role FROM cpbl.roster_annotation_revision "
                               "WHERE revision=2").fetchall())
    assert roles["0000005151"] == "輪值" and roles["0000004636"] == "主力" and len(roles) == 32
    f = tmp_path / "bad.txt"
    for bad in (text().replace("羅戈 @id=0000005151", "羅戈 @id=0000005151 #主力"),
                text().replace("江坤宇 @id=0000004636", "江坤宇 @id=0000004636 #輪值"),
                text().replace("江坤宇 @id=0000004636", "江坤宇 @id=0000004636 #主力 #代打")):
        f.write_text(bad, encoding="utf-8")
        assert run_roster.run(["annotate", str(f)]) == 10
    members = {m["player_id"] for r_ in load_official(2026, "E") for m in r_["members"]}
    extra = next(x for x in fixture()["team_roster"] if x[1] == "ACN011" and x[2] not in members)
    f.write_text(text().replace("岳政華 @id=0000005571", f"{extra[3]} @id={extra[2]}"), encoding="utf-8")
    assert run_roster.run(["annotate", str(f)]) == 15
    with db.conn() as c:
        assert c.execute(snap).fetchall() == before_head
        assert c.execute("SELECT max(revision) FROM cpbl.roster_annotation_revision").fetchone()[0] == 2
    assert r["roster_id"] == str(before_head[0][0])


# ------------------------------------------------------------------ E15


def test_e15_eligibility_only_no_starter_or_availability(pool, capsys):
    do_submit(text())
    with db.conn() as c:
        cols = [r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='cpbl' "
            "AND table_name IN ('series_roster','series_roster_member','roster_annotation_revision')")]
        with c.cursor() as cur:
            r = read_roster(cur, 2026, "E", "ACN011")
    banned = ("start", "avail", "lineup", "active", "injur", "registered")
    assert not [c for c in cols if any(b in c for b in banned)]
    keys = set(r) | set(r["head"]) | set(r["members"][0])
    assert not [k for k in keys if any(b in k for b in banned)]
    assert r["note"] == ELIGIBILITY_NOTE
    assert run_roster.run(["show", "--year", "2026", "--series", "E", "--team", "ACN011"]) == 0
    assert ELIGIBILITY_NOTE in capsys.readouterr().out


# ------------------------------------------------------------------ E17


def test_e17_immutability_and_deferred_32(pool):
    r = do_submit(text())
    rid = r["roster_id"]
    attacks = [
        "UPDATE cpbl.series_roster SET source_url='x' WHERE roster_id=%(r)s",
        "DELETE FROM cpbl.series_roster WHERE roster_id=%(r)s",
        "TRUNCATE cpbl.series_roster CASCADE",
        "UPDATE cpbl.series_roster_member SET announced_name='x' WHERE roster_id=%(r)s",
        "DELETE FROM cpbl.series_roster_member WHERE roster_id=%(r)s",
        "TRUNCATE cpbl.series_roster_member CASCADE",
        "UPDATE cpbl.roster_annotation_revision SET tactical_role='主力' WHERE roster_id=%(r)s",
        "DELETE FROM cpbl.roster_annotation_revision WHERE roster_id=%(r)s",
        "TRUNCATE cpbl.roster_annotation_revision",
        # sync_table 形狀的 UPSERT 打到既有名單
        "INSERT INTO cpbl.series_roster SELECT * FROM cpbl.series_roster WHERE roster_id=%(r)s "
        "ON CONFLICT (year, kind_code, team_code) DO UPDATE SET source_url=EXCLUDED.source_url",
        "INSERT INTO cpbl.series_roster_member SELECT * FROM cpbl.series_roster_member WHERE roster_id=%(r)s "
        "ON CONFLICT (roster_id, player_id) DO UPDATE SET announced_name=EXCLUDED.announced_name",
    ]
    for sql in attacks:
        with pytest.raises(psycopg.Error) as exc, db.conn() as c:
            c.execute(sql, {"r": rid})
        assert "不可變" in str(exc.value), sql
    # 事後補插第 33 名會員（不是 UPDATE）→ 提交時延遲約束擋下
    with pytest.raises(psycopg.Error) as exc, db.conn() as c:
        c.execute("INSERT INTO cpbl.series_roster_member VALUES (%s, '0000000108', '投手', '勝騎士')", (rid,))
    assert "≠ 32" in str(exc.value)
    # 只插 31 名會員的交易 → 提交時被擋
    with pytest.raises(psycopg.Error) as exc, db.conn() as c:
        c.execute(
            "INSERT INTO cpbl.series_roster SELECT gen_random_uuid(), year, 'C', team_code, source_url, "
            "published_date, published_precision, observed_at, observation_basis, identity_verified_at, "
            "input_origin, raw_text, hash_version, membership_hash, source_hash, import_check, now() "
            "FROM cpbl.series_roster WHERE roster_id=%(r)s RETURNING roster_id", {"r": rid})
        new_id = c.execute("SELECT roster_id FROM cpbl.series_roster WHERE kind_code='C'").fetchone()[0]
        c.execute("INSERT INTO cpbl.series_roster_member SELECT %s, player_id, official_position, "
                  "announced_name FROM cpbl.series_roster_member WHERE roster_id=%s LIMIT 31", (new_id, rid))
    assert "≠ 32" in str(exc.value)
    assert counts() == (1, 32, 32)


# ------------------------------------------------------------------ E20


def test_e20_official_population_import_matches_records(pool, capsys):
    for rec in load_official(2026, "E"):
        team = rec["team_code"]
        assert run_roster.run(["import-official-population", "--year", "2026", "--series", "E",
                               "--team", team, "--json"]) == 0
        h = json.loads(capsys.readouterr().out)["hashes"]["membership_hash"]
        assert run_roster.run(["import-official-population", "--year", "2026", "--series", "E",
                               "--team", team, "--confirm-hash", h]) == 0
        capsys.readouterr()
        with db.conn() as c, c.cursor() as cur:
            r = read_roster(cur, 2026, "E", team)
        head = r["head"]
        assert head["input_origin"] == "official_population_v1"
        assert head["source_url"] == rec["source_url"]
        assert head["published_date"].isoformat() == rec["published_date"]
        assert head["observation_basis"] == rec["observation_basis"]
        assert head["observed_at"] == datetime.fromisoformat(rec["observed_at"].replace("Z", "+00:00"))
        assert head["identity_verified_at"] == datetime.fromisoformat(rec["identity_verified_at"])
        assert head["membership_hash"] == h
        got = {(m["player_id"], m["announced_name"], m["official_position"]) for m in r["members"]}
        want = {(m["player_id"], m["name"], m["official_role"]) for m in rec["members"]}
        assert got == want and len(got) == 32
    assert counts() == (2, 64, 64)
