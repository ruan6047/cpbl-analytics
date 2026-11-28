"""#469 規劃修訂 r2：``cpbl-champion-autofill``（VPS timer 在 ``prod_cpbl_api`` 內每日執行）。

鎖住四件事：⛔ 不呼叫 ``migrate()``；只有補了列才重建成員；任何錯誤 ⇒ 退出碼 1；殺開關不讀不寫。
本檔不連 DB（沿用 ``tests/test_championship_autofill.py`` 的假 cursor 與 #391 真實 2026 收官樣本）。
``--help`` 零副作用由 ``tests/test_cli_help_guard.py`` 依 pyproject 自動涵蓋。
"""

from __future__ import annotations

import ast
import inspect
import json
import sys
import tomllib
from contextlib import contextmanager
from pathlib import Path

import pytest

import cpbl.ingest.run_champion_autofill as cli
from cpbl.ingest import championships as ch
from tests.test_championship_autofill import NOW, REAL_MAJOR_2026, _Cur, _fake_conn

REPO_ROOT = Path(__file__).resolve().parents[1]


def _calls_named(tree: ast.AST, name: str) -> list[int]:
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            called = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            if called == name:
                hits.append(node.lineno)
    return hits


def _counting(closure=REAL_MAJOR_2026):
    reads = []

    def read():
        reads.append(1)
        return closure
    return read, reads


# =========================================================================== 不 migrate


def test_console_script_points_at_this_module():
    scripts = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["cpbl-champion-autofill"] == "cpbl.ingest.run_champion_autofill:main"


def test_entry_and_its_body_never_call_migrate():
    """靜態：入口模組與 ``run_champion_autofill`` 主體都沒有 migrate 呼叫，也沒有把它 import 進來。"""
    module_tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    body_tree = ast.parse(inspect.getsource(ch.run_champion_autofill))
    assert _calls_named(module_tree, "migrate") == []
    assert _calls_named(body_tree, "migrate") == []
    assert not hasattr(cli, "migrate")


def test_main_runs_end_to_end_without_reaching_migrate(monkeypatch, capsys):
    """行為：把 ``cpbl.db.migrate`` 換成會炸的 stub，整條入口照樣跑完（補列＋重建）。"""
    import cpbl.db

    def forbidden(*_a, **_k):
        raise AssertionError("cpbl-champion-autofill 不得呼叫 migrate()")

    monkeypatch.setattr(cpbl.db, "migrate", forbidden)
    cur = _Cur()
    _fake_conn(monkeypatch, cur)
    monkeypatch.setattr(ch, "read_major_closure", lambda: REAL_MAJOR_2026)
    monkeypatch.delenv(ch.AUTOFILL_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["cpbl-champion-autofill"])

    assert cli.main() is None

    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["action"] == "inserted" and out["year"] == 2026 and out["members"] == "rebuilt"
    assert any("TRUNCATE cpbl.championship_members" in s for s, _ in cur.sql)


# =========================================================================== 只有補了列才重建


def test_inserted_rebuilds_members_with_a_single_closure_read(monkeypatch):
    cur = _Cur()
    _fake_conn(monkeypatch, cur)
    read, reads = _counting()

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=read)

    assert code == 0 and out["action"] == "inserted" and out["members"] == "rebuilt"
    stmts = [s for s, _ in cur.sql]
    assert sum("TRUNCATE cpbl.championship_members" in s for s in stmts) == 1
    assert reads == [1]  # 成員重建沿用同一份收官判定，不重讀


@pytest.mark.parametrize(("cur_kwargs", "closure_status", "action"), [
    ({"champion_row": ("AAA011", "AAA011"), "manager_present": True}, "decided", "present"),
    ({"champion_row": ("ACN011", "ACN011")}, "decided", "present_conflict"),
    ({"decisive": None}, "decided", "no_decisive_game"),
    ({}, "undecided", "not_decided"),
])
def test_anything_but_inserted_never_rebuilds_members(monkeypatch, cur_kwargs, closure_status, action):
    from dataclasses import replace

    closure = REAL_MAJOR_2026 if closure_status == "decided" else replace(
        REAL_MAJOR_2026, status=closure_status, champion_team_code=None, decided_by=None)
    cur = _Cur(**cur_kwargs)
    _fake_conn(monkeypatch, cur)
    monkeypatch.setattr(ch, "_rebuild_members", lambda *_: pytest.fail("rebuilt members without insert"))

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=lambda: closure)

    assert code == 0 and out["action"] == action
    assert not any("TRUNCATE" in s for s, _ in cur.sql)


# =========================================================================== 錯誤 ⇒ 退出碼 1


def test_closure_read_failure_exits_one(monkeypatch):
    _fake_conn(monkeypatch, _Cur())

    def boom():
        raise RuntimeError("closure down")

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=boom)

    assert code == 1 and out == {"action": "error", "stage": "closure", "error": "RuntimeError", "manager": None}


# --------------------------------------------------------------------------- 交易邊界（審核第 1 輪 finding 1）


class _TxDB:
    """有交易語意的假庫：每次 ``conn()`` 是一筆交易，乾淨離開才 commit，拋錯就丟棄本交易的寫入。

    只模擬冠軍表與成員表是否「已提交」，以及在成員 INSERT 注入一次失敗（審核者的唯讀探針形狀：
    TRUNCATE 之後成員 INSERT 失敗）。"""

    def __init__(self, *, fail_member_inserts: int = 0):
        self.champion_committed = False
        self.members_committed: list[int] = []  # 已提交的成員重建年份
        self.fail_member_inserts = fail_member_inserts
        self.commits = self.rollbacks = 0

    def conn(self):
        db = self

        @contextmanager
        def tx():
            cur = _TxCur(db)
            try:
                yield _TxConn(cur)
            except BaseException:
                db.rollbacks += 1
                raise
            db.commits += 1
            if cur.champion_pending:
                db.champion_committed = True
            if cur.members_pending is not None:
                db.members_committed = cur.members_pending
        return tx()


class _TxConn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur


class _TxCur(_Cur):
    def __init__(self, db: _TxDB):
        super().__init__(champion_row=("AAA011", "AAA011") if db.champion_committed else None,
                         manager_present=db.champion_committed)
        self.db = db
        self.champion_pending = False
        self.members_pending: list[int] | None = None

    def execute(self, sql, params=None):
        text = sql.lstrip()
        if text.startswith("INSERT INTO cpbl.championship_members") and self.db.fail_member_inserts:
            self.db.fail_member_inserts -= 1
            raise RuntimeError("member insert failed")
        super().execute(sql, params)
        if text.startswith("INSERT INTO cpbl.championships ") and self.rowcount:
            self.champion_pending = True
        elif text.startswith("TRUNCATE cpbl.championship_members"):
            self.members_pending = []
        elif text.startswith("INSERT INTO cpbl.championship_members") and self.members_pending is not None:
            assert isinstance(params, dict)
            self.members_pending.append(params["year"])
        elif "FROM cpbl.championships" in sql and "verification_status = 'verified'" in sql:
            has = self.db.champion_committed or self.champion_pending
            self._all = [(2026, "AAA011", "AAA011", NOW)] if has else []


def _tx_db(monkeypatch, **kwargs) -> _TxDB:
    db = _TxDB(**kwargs)
    monkeypatch.setattr(ch, "conn", db.conn)
    return db


def test_members_rebuild_failure_rolls_back_the_champion_row_too(monkeypatch):
    """補列與成員重建同一筆交易（plan-r2 §7「單交易」）：成員失敗 ⇒ 冠軍列也不提交，退出碼 1。"""
    db = _tx_db(monkeypatch, fail_member_inserts=1)

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=lambda: REAL_MAJOR_2026)

    assert db.champion_committed is False, "成員重建失敗卻已提交冠軍列：隔日重試會回 present、永不重建"
    assert db.members_committed == []
    assert code == 1 and out["action"] == "error" and out["error"] == "RuntimeError" and out["stage"] == "members"
    assert db.rollbacks == 1


def test_retry_after_members_failure_inserts_and_rebuilds(monkeypatch):
    """審核者的重現：第一次成員失敗、第二次正常 ⇒ 第二次必須 inserted＋rebuilt（不是 present）。"""
    db = _tx_db(monkeypatch, fail_member_inserts=1)
    first = ch.run_champion_autofill(now=NOW, env={}, read_closure=lambda: REAL_MAJOR_2026)

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=lambda: REAL_MAJOR_2026)

    assert first[0] == 1
    assert code == 0 and out["action"] == "inserted" and out["members"] == "rebuilt"
    assert db.champion_committed is True and db.members_committed == [2026, 2026]  # 球員＋總教練各一句
    assert db.commits == 1, "冠軍補列與成員重建必須是同一筆提交"


def test_db_failure_during_autofill_exits_one(monkeypatch):
    @contextmanager
    def down():
        raise OSError("db unreachable")
        yield  # pragma: no cover

    monkeypatch.setattr(ch, "conn", down)

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=lambda: REAL_MAJOR_2026)

    assert code == 1 and out["action"] == "error" and out["error"] == "OSError" and out["stage"] == "autofill"


def test_main_prints_json_and_exits_one_on_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_champion_autofill",
                        lambda: (1, {"action": "error", "error": "RuntimeError", "manager": None}))
    monkeypatch.setattr(sys, "argv", ["cpbl-champion-autofill"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out.strip())["action"] == "error"


# =========================================================================== 殺開關


def test_kill_switch_reads_nothing_and_writes_nothing(monkeypatch):
    @contextmanager
    def no_db():
        pytest.fail("opened a DB connection while disabled")
        yield  # pragma: no cover

    monkeypatch.setattr(ch, "conn", no_db)

    code, out = ch.run_champion_autofill(
        now=NOW, env={ch.AUTOFILL_ENV: "off"},
        read_closure=lambda: pytest.fail("read closure while disabled"))

    assert code == 0 and out["action"] == "disabled"


def test_kill_switch_via_environment_through_main(monkeypatch, capsys):
    monkeypatch.setenv(ch.AUTOFILL_ENV, "off")
    monkeypatch.setattr(ch, "read_major_closure", lambda: pytest.fail("read closure while disabled"))

    @contextmanager
    def no_db():
        pytest.fail("opened a DB connection while disabled")
        yield  # pragma: no cover

    monkeypatch.setattr(ch, "conn", no_db)
    monkeypatch.setattr(sys, "argv", ["cpbl-champion-autofill"])

    assert cli.main() is None
    assert json.loads(capsys.readouterr().out.strip())["action"] == "disabled"
