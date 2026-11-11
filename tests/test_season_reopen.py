"""#392 WP1／WP2：開季切回工具 ``cpbl.season_reopen``（計畫、寫入、正式站單表步驟、flag、一條指令）。

收官值取自 #391 真實樣本（``tests/test_season_close.py``）；本檔不連 DB，真 PostgreSQL 契約見 ``tests/test_season_reopen_db.py``。
"""

from __future__ import annotations

import io
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from cpbl import season_close as sc
from cpbl import season_reopen as sr
from tests.test_season_close_reopen import REAL_FARM_2026, REAL_MAJOR_2026

# =========================================================================== season_reopen：計畫


def test_plan_rows_only_for_closed_leagues():
    pure = {"major": REAL_MAJOR_2026, "farm": REAL_FARM_2026}
    assert sr.apply_rows(pure) == (("farm", 2026), ("major", 2026))
    tie = replace(REAL_FARM_2026, closed=False, status="undecided_tie")
    assert sr.apply_rows({"major": REAL_MAJOR_2026, "farm": tie}) == (("major", 2026),)


def test_plan_rows_empty_mid_season_so_nothing_is_written():
    mid = {"major": replace(REAL_MAJOR_2026, closed=False, status="undecided"),
           "farm": replace(REAL_FARM_2026, closed=False, status="undecided")}
    assert sr.apply_rows(mid) == ()


def test_rows_text_round_trip_and_rejects_garbage():
    assert sr.format_rows((("farm", 2026), ("major", 2026))) == "farm:2026,major:2026"
    assert sr.parse_rows("major:2026,farm:2026") == (("farm", 2026), ("major", 2026))
    for bad in ("", "major", "major:26", "A:2026", "major:2026;DROP", "major:2026,major:2026", "major:3026"):
        with pytest.raises(ValueError):
            sr.parse_rows(bad)


def test_revoke_rows_are_each_leagues_latest_season():
    assert sr.revoke_rows({"major": 2026, "farm": 2026}) == (("farm", 2026), ("major", 2026))
    assert sr.revoke_rows({"major": 2026, "farm": None}) == (("major", 2026),)


# =========================================================================== season_reopen：寫入只碰切回表


def _tables(sql: str) -> set[str]:
    import re

    return set(re.findall(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(?!SET\b)([A-Za-z_][\w.]*)", sql, re.I))


@pytest.mark.parametrize("action", ["apply", "revoke"])
def test_write_sql_only_touches_season_reopen_table(action):
    rows = (("farm", 2026), ("major", 2026))
    sql, params = sr.write_sql(action, rows)
    assert _tables(sql) <= {sc.REOPEN_TABLE}, _tables(sql)
    assert "cpbl.games" not in sql and "DELETE" not in sql.upper()
    assert params == ["farm", 2026, "major", 2026]
    script = sr.remote_write_script(action, rows)
    assert _tables(script) <= {sc.REOPEN_TABLE}
    assert "cpbl.games" not in script and "DELETE" not in script.upper()
    assert "'farm'" in script and "2026" in script


def test_write_local_sends_one_statement_with_params():
    seen = []

    class _C:
        def execute(self, sql, params=None):
            seen.append((sql, params))

    sr.write_local(_C(), "apply", (("major", 2026),))
    assert len(seen) == 1 and seen[0][1] == ["major", 2026]
    assert "ON CONFLICT (league, season) DO UPDATE" in seen[0][0]


def test_remote_literals_are_whitelisted():
    with pytest.raises(ValueError):
        sr.remote_write_script("apply", (("major'; --", 2026),))
    with pytest.raises(ValueError):
        sr.remote_write_script("drop", (("major", 2026),))


# =========================================================================== season_reopen：遠端（正式站）步驟


class _Target:
    """假 psql 目標：依腳本內容回應（存在檢查／寫入／讀回）。"""

    def __init__(self, *, table=True, status=None, fail_on=None):
        self.table, self.status, self.fail_on, self.scripts = table, status, fail_on, []

    def run(self, script: str) -> str:
        self.scripts.append(script)
        if self.fail_on and self.fail_on in script:
            raise sr.RemoteError(sr.EXIT_TARGET, "fixture failure")
        if "to_regclass" in script:
            return "t\n" if self.table else "f\n"
        if "AS status" in script:
            return "\n".join(self.status) + "\n"
        return ""


def test_remote_apply_checks_table_writes_then_reads_back():
    t = _Target(status=["farm|2026|active", "major|2026|active"])
    assert sr.remote(t, "apply", (("farm", 2026), ("major", 2026))) == 0
    assert ["to_regclass" in t.scripts[0], "INSERT INTO" in t.scripts[1], "AS status" in t.scripts[2]] == [True] * 3
    assert "BEGIN TRANSACTION READ ONLY" in t.scripts[0] and "BEGIN TRANSACTION READ ONLY" in t.scripts[2]


def test_remote_missing_table_is_69_and_writes_nothing():
    t = _Target(table=False)
    with pytest.raises(sr.RemoteError) as e:
        sr.remote(t, "apply", (("major", 2026),))
    assert e.value.code == sr.EXIT_NO_TABLE and len(t.scripts) == 1


def test_remote_readback_mismatch_is_71():
    t = _Target(status=["major|2026|revoked"])
    with pytest.raises(sr.RemoteError) as e:
        sr.remote(t, "apply", (("major", 2026),))
    assert e.value.code == sr.EXIT_READBACK


def test_remote_revoke_accepts_revoked_or_absent():
    t = _Target(status=["farm|2026|absent", "major|2026|revoked"])
    assert sr.remote(t, "revoke", (("farm", 2026), ("major", 2026))) == 0
    assert "UPDATE cpbl.season_reopen" in t.scripts[1]


def test_remote_cli_maps_errors_to_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(sr, "PsqlTarget", lambda _cmd: _Target(table=False))
    assert sr.main(["remote", "--action", "apply", "--rows", "major:2026", "--target-psql", "x"]) == sr.EXIT_NO_TABLE
    assert sr.main(["remote", "--action", "apply", "--rows", "major:26", "--target-psql", "x"]) == sr.EXIT_USAGE


# =========================================================================== 兩個先發 flag


@pytest.fixture()
def flags(tmp_path, monkeypatch):
    from cpbl.ingest import starter_checkpoints, starter_watch

    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setenv(starter_watch.FLAG_ENV, str(logs / "starter-watch.enabled"))
    monkeypatch.setenv("POSTSEASON_STARTER_FLAG", str(logs / "postseason-starter-checkpoints.enabled"))
    return logs, starter_watch, starter_checkpoints


def test_flags_paused_are_renamed_back_and_read_as_enabled(flags):
    logs, sw, sc_ = flags
    (logs / "starter-watch.enabled.paused-20261028").write_text("w")
    (logs / "postseason-starter-checkpoints.enabled.paused-20261028").write_text("c")
    assert not sw.flag_path().exists() and not sc_.flag_path().exists()
    report = sr.restore_flags()
    assert sw.flag_path().exists() and sc_.flag_path().exists()
    assert sw.flag_path().read_text() == "w", "改名而不是新建（保留原檔）"
    assert [r.action for r in report] == ["renamed", "renamed"]
    assert not list(logs.glob("*.paused-*"))


def test_flags_already_enabled_are_left_alone(flags):
    logs, sw, sc_ = flags
    sw.flag_path().write_text("keep")
    sc_.flag_path().write_text("keep")
    (logs / "starter-watch.enabled.paused-20261028").write_text("old")
    report = sr.restore_flags()
    assert [r.action for r in report] == ["unchanged", "unchanged"]
    assert sw.flag_path().read_text() == "keep" and (logs / "starter-watch.enabled.paused-20261028").exists()


def test_flags_missing_everything_are_created(flags):
    _logs, sw, sc_ = flags
    report = sr.restore_flags()
    assert [r.action for r in report] == ["created", "created"]
    assert sw.flag_path().exists() and sc_.flag_path().exists()


def test_flags_pick_the_latest_paused_copy(flags):
    logs, sw, _ = flags
    (logs / "starter-watch.enabled.paused-20251028").write_text("old")
    (logs / "starter-watch.enabled.paused-20261028").write_text("new")
    sr.restore_flags()
    assert sw.flag_path().read_text() == "new"
    assert (logs / "starter-watch.enabled.paused-20251028").exists()


# =========================================================================== 一條指令：步驟順序與停止


class _World:
    """一條指令的全部外部步驟替身：只記順序與參數，⛔ 不碰 DB／ssh／網路。"""

    def __init__(self, *, pure=None, latest=None, prod_rc=0, local_fail=False, after=None, summary=None,
                 fetch_fail=False):
        self.calls: list = []
        self.pure = pure or {"major": REAL_MAJOR_2026, "farm": REAL_FARM_2026}
        self.latest = latest or {"major": 2026, "farm": 2026}
        self.prod_rc, self.local_fail, self.fetch_fail = prod_rc, local_fail, fetch_fail
        self.after = after
        self.summary = summary

    def deps(self) -> sr.Deps:
        return sr.Deps(
            closure=self._closure, latest=lambda: dict(self.latest), prod=self._prod, local=self._local,
            flags=self._flags, fetch=self._fetch, out=io.StringIO())

    def _closure(self, *, reopen: bool):
        self.calls.append(("closure", reopen))
        if reopen and self.after is not None:
            return self.after
        return self.pure

    def _prod(self, action, rows):
        self.calls.append(("prod", action, sr.format_rows(rows)))
        return self.prod_rc

    def _local(self, action, rows):
        self.calls.append(("local", action, sr.format_rows(rows)))
        if self.local_fail:
            raise RuntimeError("fixture local failure")

    def _flags(self):
        self.calls.append(("flags",))
        return [sr.FlagResult("x", "renamed", "a", "b")]

    def _fetch(self):
        self.calls.append(("fetch",))
        if self.fetch_fail:
            raise OSError("fixture fetch failure")
        return self.summary


def _reopened_after():
    return {lg: replace(c, closed=False, override=sc.OVERRIDE_REOPENED)
            for lg, c in {"major": REAL_MAJOR_2026, "farm": REAL_FARM_2026}.items()}


def _summary(closed: bool, override=None):
    return {"season_close": {"major": {"closed": closed, "override": override}}}


def test_apply_runs_prod_then_local_then_flags_then_verifies():
    w = _World(after=_reopened_after(), summary=_summary(False, "reopened"))
    assert sr.run_apply(w.deps()) == 0
    assert [c[0] for c in w.calls] == ["closure", "prod", "local", "flags", "closure", "fetch"]
    assert w.calls[0] == ("closure", False), "計畫用純推導（忽略切回紀錄與 env）"
    assert w.calls[1] == ("prod", "apply", "farm:2026,major:2026")


def test_apply_stops_at_prod_failure_and_skips_everything_after():
    w = _World(prod_rc=69)
    deps = w.deps()
    assert sr.run_apply(deps) == 69
    assert [c[0] for c in w.calls] == ["closure", "prod"]
    assert "已完成：計畫" in deps.out.getvalue()


def test_apply_stops_at_local_failure_before_flags():
    w = _World(local_fail=True)
    deps = w.deps()
    assert sr.run_apply(deps) == sr.EXIT_LOCAL
    assert [c[0] for c in w.calls] == ["closure", "prod", "local"]
    assert "已完成：計畫、正式站" in deps.out.getvalue()


def test_apply_mid_season_writes_nothing():
    mid = {"major": replace(REAL_MAJOR_2026, closed=False, status="undecided"),
           "farm": replace(REAL_FARM_2026, closed=False, status="undecided")}
    w = _World(pure=mid)
    deps = w.deps()
    assert sr.run_apply(deps) == 0
    assert w.calls == [("closure", False)]
    assert "未寫入任何紀錄" in deps.out.getvalue()


def test_apply_verify_failure_is_reported_nonzero():
    w = _World(after={"major": REAL_MAJOR_2026, "farm": REAL_FARM_2026}, summary=_summary(True))
    assert sr.run_apply(w.deps()) == sr.EXIT_VERIFY
    w = _World(after=_reopened_after(), fetch_fail=True)
    assert sr.run_apply(w.deps()) == sr.EXIT_VERIFY
    w = _World(after=_reopened_after(), summary=_summary(True))
    assert sr.run_apply(w.deps()) == sr.EXIT_VERIFY


def test_plan_prints_and_touches_nothing():
    w = _World()
    deps = w.deps()
    assert sr.run_plan(deps) == 0
    assert w.calls == [("closure", False)]
    assert "farm:2026,major:2026" in deps.out.getvalue()


def test_revoke_runs_prod_then_local_and_leaves_flags_alone():
    w = _World(after={"major": REAL_MAJOR_2026, "farm": REAL_FARM_2026}, summary=_summary(True))
    deps = w.deps()
    assert sr.run_revoke(deps) == 0
    assert [c[0] for c in w.calls] == ["prod", "local", "closure", "closure", "fetch"]
    assert w.calls[0] == ("prod", "revoke", "farm:2026,major:2026")
    assert "flags" not in [c[0] for c in w.calls]
    assert "starter-watch.enabled" in deps.out.getvalue(), "印出 flag 的人工撤回方式"


def test_revoke_stops_at_prod_failure():
    w = _World(prod_rc=72)
    assert sr.run_revoke(w.deps()) == 72
    assert [c[0] for c in w.calls] == ["prod"]


def test_cli_refuses_outside_repo_root(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert sr.main(["apply"]) == sr.EXIT_USAGE
    assert "repo 根目錄" in capsys.readouterr().err


def test_cli_help_has_no_side_effects(monkeypatch, capsys):
    monkeypatch.setattr(sr, "default_deps", lambda *a, **k: pytest.fail("--help 不得建立任何依賴"))
    with pytest.raises(SystemExit) as e:
        sr.main(["--help"])
    assert e.value.code == 0
    assert "apply" in capsys.readouterr().out


def test_prod_step_invokes_refresh_script_single_table_mode(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, env, check):
        seen["argv"], seen["env"] = argv, env
        return type("P", (), {"returncode": 0})()

    monkeypatch.setattr(sr.subprocess, "run", fake_run)
    rc = sr.prod_step(tmp_path, "/abs/backups", "apply", (("major", 2026),))
    assert rc == 0
    assert seen["argv"] == ["bash", str(tmp_path / "scripts" / "refresh-cpbl-prod.sh")]
    env = seen["env"]
    assert (env["SEASON_REOPEN_ONLY"], env["SKIP_SCRAPE"], env["SEASON_REOPEN_ACTION"],
            env["SEASON_REOPEN_ROWS"], env["BACKUP_DIR"]) == ("1", "1", "apply", "major:2026", "/abs/backups")
    for k in ("WITH_DETAIL", "LINEUP_ONLY", "ROSTER_ONLY", "DAILY_DAY_TYPE"):
        assert k not in env


def test_json_shape_of_plan_report():
    pure = {"major": REAL_MAJOR_2026, "farm": REAL_FARM_2026}
    body = sr.plan_report(pure, sr.apply_rows(pure))
    assert json.loads(json.dumps(body))["rows"] == "farm:2026,major:2026"


def test_module_constant_paths_exist():
    assert Path(sr.__file__).name == "season_reopen.py"
    assert os.path.basename(sr.REFRESH_SCRIPT) == "refresh-cpbl-prod.sh"
