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
    monkeypatch.setattr(ch, "build_championships", lambda **_: pytest.fail("rebuilt members without insert"))

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=lambda: closure)

    assert code == 0 and out["action"] == action
    assert not any("TRUNCATE" in s for s, _ in cur.sql)


# =========================================================================== 錯誤 ⇒ 退出碼 1


def test_closure_read_failure_exits_one(monkeypatch):
    _fake_conn(monkeypatch, _Cur())

    def boom():
        raise RuntimeError("closure down")

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=boom)

    assert code == 1 and out == {"action": "error", "error": "RuntimeError", "manager": None}


def test_members_rebuild_failure_after_insert_exits_one(monkeypatch):
    _fake_conn(monkeypatch, _Cur())

    def boom(**_):
        raise RuntimeError("truncate failed")

    monkeypatch.setattr(ch, "build_championships", boom)

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=lambda: REAL_MAJOR_2026)

    assert code == 1
    assert out["action"] == "inserted" and out["members"] == "error" and out["members_error"] == "RuntimeError"


def test_db_failure_during_autofill_exits_one(monkeypatch):
    @contextmanager
    def down():
        raise OSError("db unreachable")
        yield  # pragma: no cover

    monkeypatch.setattr(ch, "conn", down)

    code, out = ch.run_champion_autofill(now=NOW, env={}, read_closure=lambda: REAL_MAJOR_2026)

    assert code == 1 and out["action"] == "error" and out["error"] == "OSError"


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
