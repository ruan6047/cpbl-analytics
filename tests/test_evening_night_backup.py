"""#365 S4（驗收 f）：晚間鏈每晚首次同步前備份一次（P-EVENING-BACKUP；需求方裁定 #343 6361011713 第 2 項、
6361069621）。

兩層：
* 純函式（``backup_plan``／``apply_backup_record``）：沿用條件與入帳。
* 端到端：跑**真的** ``refresh-cpbl-prod.sh``（RESULTS_ONLY 與 BOXPA_ONLY 兩個早退模式；假 ssh／docker／uv，
  ``VPS`` 指向 ``.invalid``，沿 tests/test_prod_sync_revision_seq.py 與 tests/test_boxpa_sync_mode.py 的 harness），
  假 ``backup-prod-db.sh`` 每次被呼叫就在計數檔記一行、並在 BACKUP_DIR 寫一個真檔案（sha256 才算得出來）；
  兩次同步之間用真的 Python 入帳與決策（``apply_backup_record`` → ``backup_plan``）銜接，與
  ``postseason-evening.sh`` 的順序相同。時刻取 2026 真實比賽夜（09-27 A 夜、10-21 C4 夜）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpbl.ingest import postseason_evening as pe
from tests.test_boxpa_sync_mode import _DOCKER, _SSH, _UV
from tests.test_boxpa_sync_mode import _write_exec as _write_exec_boxpa
from tests.test_prod_sync_revision_seq import FAKE_LOCAL_SEQ, FAKE_PROD_MAX, _build_harness

ROOT = Path(__file__).resolve().parents[1]
REFRESH = ROOT / "scripts" / "refresh-cpbl-prod.sh"
EVENING = ROOT / "scripts" / "postseason-evening.sh"
TPE = ZoneInfo("Asia/Taipei")


def tpe(m, d, hh, mm) -> datetime:
    return datetime(2026, m, d, hh, mm, tzinfo=TPE)


# =========================================================== 純函式

def _state_with(path: Path, night: str) -> dict:
    return {**pe.empty_state(), "night_backup": {"night": night, "path": str(path),
                                                 "sha256": pe.file_sha256(path), "at": "x"}}


def test_backup_plan_reuses_only_a_verified_backup_of_the_same_night(tmp_path):
    dump = tmp_path / "cpbl-20260927.sql.gz"
    dump.write_bytes(b"night 09-27 dump")
    state = _state_with(dump, "2026-09-27")
    assert pe.backup_plan(state, tpe(9, 27, 22, 0)) == ("reuse", pe.file_sha256(dump), str(dump))
    assert pe.backup_plan(state, tpe(9, 28, 0, 40))[0] == "reuse", "跨過 24:00 仍是同一晚"
    assert pe.backup_plan(state, tpe(9, 28, 21, 0))[0] == "backup", "下一晚重備"
    assert pe.backup_plan(state, tpe(9, 28, 10, 30))[0] == "backup", "09:45–12:00 不屬任何一晚：一律重備"
    assert pe.backup_plan(state, tpe(9, 27, 22, 0), per_sync=True)[0] == "backup", "回退旗標：每次都備"
    assert pe.backup_plan(pe.empty_state(), tpe(9, 27, 22, 0))[0] == "backup"
    dump.write_bytes(b"night 09-27 dumP")          # 改一個位元組
    assert pe.backup_plan(state, tpe(9, 27, 22, 0))[0] == "backup"
    dump.unlink()
    assert pe.backup_plan(state, tpe(9, 27, 22, 0))[0] == "backup"


def test_backup_record_is_applied_only_for_a_completed_new_backup(tmp_path):
    record = tmp_path / "record.txt"
    state = pe.empty_state()
    assert pe.apply_backup_record(state, tpe(10, 21, 22, 22), record) is None, "沒有紀錄（備份驗證前失敗）"
    assert state.get("night_backup") is None
    sha = "a" * 64
    record.write_text(f"new {sha} /Users/x/Library/Application Support/cpbl/backups-postseason-evening/c.sql.gz\n")
    assert pe.apply_backup_record(state, tpe(10, 21, 22, 22), record) == "new"
    assert state["night_backup"]["night"] == "2026-10-21"
    assert state["night_backup"]["path"].endswith("Application Support/cpbl/backups-postseason-evening/c.sql.gz")
    record.write_text(f"reuse {sha} /elsewhere.sql.gz\n")
    pe.apply_backup_record(state, tpe(10, 21, 22, 44), record)
    assert state["night_backup"]["path"].endswith("c.sql.gz"), "沿用不改寫 night_backup"
    assert [u["mode"] for u in state["backup_uses"]] == ["new", "reuse"]
    record.write_text("new nothex /x\n")
    assert pe.apply_backup_record(state, tpe(10, 21, 23, 0), record) is None, "格式不符不入帳"
    fresh = pe.empty_state()
    record.write_text(f"new {sha} /x.sql.gz\n")
    pe.apply_backup_record(fresh, tpe(10, 22, 10, 30), record)
    assert fresh.get("night_backup") is None, "09:45–12:00 的備份不屬任何一晚，不記"


# =========================================================== 端到端：真 refresh-cpbl-prod.sh

_BACKUP_STUB = """#!/bin/sh
echo call >> "$STUB_BACKUP_COUNT"
[ -n "$STUB_BACKUP_FAIL" ] && { echo 'FATAL: stub 備份驗證失敗' >&2; exit 1; }
mkdir -p "$BACKUP_DIR"
n=$(wc -l < "$STUB_BACKUP_COUNT" | tr -d ' ')
f="$BACKUP_DIR/cpbl-stub-$n.sql.gz"
printf 'stub dump %s\\n' "$n" > "$f"
echo "$f"
"""


class Night:
    """同一組備份目錄、計數檔與晚間狀態，依序跑兩種早退模式的同步。"""

    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.backup_dir = (tmp_path / "evening-backups").resolve()
        self.count = tmp_path / "backup-count.txt"
        self.count.touch()
        self.state = pe.empty_state()
        self.runs = 0

    @property
    def calls(self) -> int:
        return len(self.count.read_text().splitlines())

    def _env(self, harness_bin: Path, record: Path, reuse: tuple[str, str, str], **extra) -> dict:
        mode, sha, path = reuse
        env = {"PATH": f"{harness_bin}:/usr/bin:/bin", "HOME": str(self.tmp / "home"),
               "TMPDIR": str(self.tmp / "tmp"), "VPS": "stub@harness.invalid",
               "LOCAL_DB": "stub-nonexistent-container", "DEPLOY_PATH": "/nonexistent/stub-deploy",
               "API_INFO_URL": "http://127.0.0.1:1/api/info", "SKIP_SCRAPE": "1",
               "BACKUP_DIR": str(self.backup_dir), "BACKUP_KEEP": "3", "BACKUP_RECORD": str(record),
               "REUSE_VERIFIED_BACKUP": path if mode == "reuse" else "",
               "REUSE_VERIFIED_BACKUP_SHA256": sha if mode == "reuse" else "",
               "STUB_BACKUP_COUNT": str(self.count), **extra}
        return {k: v for k, v in env.items() if v is not None}

    def sync(self, mode: str, now: datetime, **extra):
        """一次同步：backup-plan → refresh（RESULTS／BOXPA）→ 入帳。回 (result, plan)。"""
        self.runs += 1
        work = self.tmp / f"run{self.runs}"
        (self.tmp / "tmp").mkdir(exist_ok=True)
        record = work / "record.txt"
        plan = pe.backup_plan(self.state, now)
        script = REFRESH
        if mode == "results":
            harness = _build_harness(work)
            os.unlink(harness["repo"] / "scripts" / REFRESH.name)
            os.symlink(script, harness["repo"] / "scripts" / REFRESH.name)
            _write_exec_boxpa(harness["repo"] / "scripts" / "backup-prod-db.sh", _BACKUP_STUB)
            env = self._env(harness["bin"], record, plan, POSTSEASON_RESULTS_ONLY="1",
                            STUB_LOG_DIR=str(harness["log"]), STUB_HELPER_DIR=str(harness["helpers"]),
                            STUB_LOCAL_SEQ=json.dumps(FAKE_LOCAL_SEQ), STUB_PROD_MAX=json.dumps(FAKE_PROD_MAX),
                            **extra)
            repo = harness["repo"]
        else:
            fake_bin, repo = work / "bin", work / "repo"
            (repo / "scripts").mkdir(parents=True, exist_ok=True)
            _write_exec_boxpa(fake_bin / "docker", f"#!{sys.executable}\n{_DOCKER}")
            _write_exec_boxpa(fake_bin / "ssh", f"#!{sys.executable}\n{_SSH}")
            _write_exec_boxpa(fake_bin / "uv", f"#!{sys.executable}\n{_UV}")
            _write_exec_boxpa(repo / "scripts" / "backup-prod-db.sh", _BACKUP_STUB)
            os.symlink(script, repo / "scripts" / REFRESH.name)
            env = self._env(fake_bin, record, plan, POSTSEASON_BOXPA_ONLY="1", POSTSEASON_BOXPA_GAMES="2026-A-355",
                            STUB_LOG_DIR=str(work / "calls"), STUB_SRC=str(ROOT / "src"), STUB_PY=sys.executable,
                            STUB_KEYS_SQL="(year, kind_code, game_sno) IN ((2026,'A',355))",
                            STUB_PA_GAMES="2026-A-355", BOXPA_MANIFEST=str(work / "manifest.json"), **extra)
        result = subprocess.run(["/bin/bash", str(repo / "scripts" / REFRESH.name)], env=env, text=True,
                                capture_output=True, stdin=subprocess.DEVNULL, check=False)
        pe.apply_backup_record(self.state, now, record)
        return result, plan


def test_two_syncs_on_the_same_night_back_up_once(tmp_path):
    """① 同一晚兩次同步（結果同步＋box／PA 同步）→ 備份 1 次；第二次 log 有「沿用 night_backup=」。"""
    night = Night(tmp_path)
    first, plan1 = night.sync("results", tpe(9, 27, 21, 5))
    assert first.returncode == 0, first.stdout + first.stderr
    assert plan1[0] == "backup" and night.calls == 1
    second, plan2 = night.sync("boxpa", tpe(9, 27, 21, 30))
    assert second.returncode == 0, second.stdout + second.stderr
    assert plan2[0] == "reuse" and night.calls == 1
    assert f"沿用 night_backup={night.state['night_backup']['path']}" in second.stdout
    assert [u["mode"] for u in night.state["backup_uses"]] == ["new", "reuse"]
    third, _ = night.sync("results", tpe(9, 28, 0, 40))          # 跨過 24:00 的 F+60 同步，仍是同一晚
    assert third.returncode == 0 and night.calls == 1


def test_next_night_backs_up_again(tmp_path):
    """② 跨夜（09-27 23:00 → 09-28 21:00）→ 第二晚重備，計數 2。"""
    night = Night(tmp_path)
    night.sync("results", tpe(9, 27, 23, 0))
    result, plan = night.sync("results", tpe(9, 28, 21, 0))
    assert result.returncode == 0 and plan[0] == "backup" and night.calls == 2
    assert night.state["night_backup"]["night"] == "2026-09-28"


@pytest.mark.parametrize("damage", ["deleted", "one_byte"])
def test_missing_or_tampered_night_backup_is_redone(tmp_path, damage):
    """③ night_backup 檔案被刪、或 sha256 改一個位元組 → 重備（決策端與 refresh 端各自都會擋）。"""
    night = Night(tmp_path)
    night.sync("results", tpe(10, 21, 22, 22))
    dump = Path(night.state["night_backup"]["path"])
    if damage == "deleted":
        dump.unlink()
    else:
        data = bytearray(dump.read_bytes())
        data[0] ^= 1
        dump.write_bytes(bytes(data))
    result, plan = night.sync("boxpa", tpe(10, 21, 22, 44))
    assert result.returncode == 0, result.stdout + result.stderr
    assert plan[0] == "backup" and night.calls == 2


def test_refresh_rechecks_sha_in_the_same_process(tmp_path):
    """③ 最後一道在 refresh：決策端判 reuse 之後、同步之前檔案被改 → refresh 自己重驗不符就重備。"""
    night = Night(tmp_path)
    night.sync("results", tpe(10, 21, 22, 22))
    dump = Path(night.state["night_backup"]["path"])
    real_plan = pe.backup_plan

    def plan_then_tamper(state, now, **kw):
        out = real_plan(state, now, **kw)
        dump.write_bytes(dump.read_bytes() + b"x")      # 決策之後才被改
        return out

    pe.backup_plan = plan_then_tamper
    try:
        result, plan = night.sync("boxpa", tpe(10, 21, 22, 44))
    finally:
        pe.backup_plan = real_plan
    assert plan[0] == "reuse", "前提：決策端當下判可沿用"
    assert result.returncode == 0 and night.calls == 2, "refresh 端重驗 sha256 不符 → 重備"
    assert "night_backup 不可沿用" in result.stdout


def test_reuse_outside_this_backup_dir_is_refused(tmp_path):
    """③ 位置：沿用的檔案必須位於本次 BACKUP_DIR（例：同晚有人用別的目錄手動回補）。"""
    night = Night(tmp_path)
    night.sync("results", tpe(10, 21, 22, 22))
    other = tmp_path / "elsewhere" / "cpbl.sql.gz"
    other.parent.mkdir()
    other.write_bytes(Path(night.state["night_backup"]["path"]).read_bytes())
    night.state["night_backup"]["path"] = str(other)
    result, plan = night.sync("results", tpe(10, 21, 23, 0))
    assert plan[0] == "reuse" and result.returncode == 0 and night.calls == 2


def test_first_backup_failure_is_not_recorded_and_next_sync_backs_up(tmp_path):
    """④ 首次備份樁 exit 非 0 → refresh 中止（未同步）、無 BACKUP_RECORD、狀態不記 night_backup，
    下一次決策仍印 backup。"""
    night = Night(tmp_path)
    failed, plan = night.sync("results", tpe(9, 27, 21, 5), STUB_BACKUP_FAIL="1")
    assert failed.returncode != 0 and plan[0] == "backup" and night.calls == 1
    assert "季後晚間：三表" not in failed.stdout, "備份失敗不得放行同步"
    assert night.state.get("night_backup") is None
    assert pe.backup_plan(night.state, tpe(9, 27, 21, 10))[0] == "backup"
    ok, _ = night.sync("results", tpe(9, 27, 21, 10))
    assert ok.returncode == 0 and night.calls == 2


def test_daily_guard_window_sync_always_backs_up(tmp_path):
    """09:45–12:00 的同步（night_of 為 None）一律重備——fail closed，不是新規則。"""
    night = Night(tmp_path)
    night.sync("results", tpe(10, 21, 22, 22))
    result, plan = night.sync("results", tpe(10, 22, 10, 30))
    assert plan[0] == "backup" and result.returncode == 0 and night.calls == 2


def test_per_sync_flag_backs_up_every_time(tmp_path, monkeypatch, capsys):
    """回退開關（P-EVENING-BACKUP）：旗標檔存在 → backup-plan 一律印 backup（CLI 層）。"""
    dump = tmp_path / "evening-backups" / "cpbl.sql.gz"
    dump.parent.mkdir()
    dump.write_bytes(b"dump")
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state_with(dump, "2026-10-21")), encoding="utf-8")
    monkeypatch.setenv("POSTSEASON_STATE", str(state_path))
    monkeypatch.setenv("POSTSEASON_BACKUP_PER_SYNC_FLAG", str(tmp_path / "per-sync.enabled"))
    monkeypatch.setattr(pe, "_now", lambda: tpe(10, 21, 22, 44))
    assert pe.main(["backup-plan"]) == 0
    assert capsys.readouterr().out.strip() == f"reuse {pe.file_sha256(dump)} {dump}"
    (tmp_path / "per-sync.enabled").touch()
    assert pe.main(["backup-plan"]) == 0
    assert capsys.readouterr().out.strip() == "backup"


# =========================================================== 晚間 wrapper 的接線

_UV_WIRING = """#!/bin/sh
mkdir -p "$STUB_CALLS"
printf '%s | BACKUP_RECORD=%s\\n' "$*" "${POSTSEASON_BACKUP_RECORD:-}" >> "$STUB_CALLS/uv.txt"
case "$*" in
  *" plan") echo sync ;;
  *" backup-plan") echo "$STUB_BACKUP_PLAN" ;;
  *"record-sync --code 0") cat "$POSTSEASON_BACKUP_RECORD" > "$STUB_CALLS/record-seen.txt"; echo synced ;;
  *" finish") echo ok ;;
esac
"""

_SYNC_WIRING = """#!/bin/sh
{
  printf 'REUSE_VERIFIED_BACKUP=%s\\n' "${REUSE_VERIFIED_BACKUP:-}"
  printf 'REUSE_VERIFIED_BACKUP_SHA256=%s\\n' "${REUSE_VERIFIED_BACKUP_SHA256:-}"
  printf 'BACKUP_RECORD=%s\\n' "${BACKUP_RECORD:-}"
} > "$STUB_CALLS/sync.txt"
printf 'reuse %s %s\\n' "${REUSE_VERIFIED_BACKUP_SHA256}" "${REUSE_VERIFIED_BACKUP}" > "$BACKUP_RECORD"
"""


@pytest.mark.parametrize("plan_line", [
    "reuse " + "b" * 64 + " /Users/x/Library/Application Support/cpbl-analytics/backups-postseason-evening/c.sql.gz",
    "backup",
])
def test_evening_wrapper_passes_reuse_and_record_to_refresh_and_record_sync(tmp_path, plan_line):
    repo, fake_bin, calls = tmp_path / "repo", tmp_path / "bin", tmp_path / "calls"
    (repo / "scripts").mkdir(parents=True)
    fake_bin.mkdir()
    (repo / "scripts" / EVENING.name).write_text(EVENING.read_text(encoding="utf-8"), encoding="utf-8")
    for name, body in (("uv", _UV_WIRING), ("launchctl", "#!/bin/sh\nexit 0\n")):
        _write_exec_boxpa(fake_bin / name, body)
    _write_exec_boxpa(repo / "scripts" / "refresh-cpbl-prod.sh", _SYNC_WIRING)
    env = {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(tmp_path / "home"), "STUB_CALLS": str(calls),
           "STUB_BACKUP_PLAN": plan_line, "REFRESH_LOCK_DIR": str(tmp_path / "lock"),
           "POSTSEASON_BACKUP_DIR": str(tmp_path / "evening-backups")}
    result = subprocess.run(["/bin/bash", str(repo / "scripts" / EVENING.name)], cwd=repo, env=env, text=True,
                            capture_output=True, stdin=subprocess.DEVNULL, check=False)
    assert result.returncode == 0, result.stderr
    sync = dict(line.split("=", 1) for line in (calls / "sync.txt").read_text().splitlines())
    if plan_line == "backup":
        assert sync["REUSE_VERIFIED_BACKUP"] == "" and sync["REUSE_VERIFIED_BACKUP_SHA256"] == ""
    else:
        _, sha, path = plan_line.split(" ", 2)
        assert (sync["REUSE_VERIFIED_BACKUP"], sync["REUSE_VERIFIED_BACKUP_SHA256"]) == (path, sha), "路徑含空白也完整"
    record = sync["BACKUP_RECORD"]
    assert record.endswith(".txt") and "/logs/postseason-backup-record-" in record
    uv = (calls / "uv.txt").read_text()
    assert f"record-sync --code 0 | BACKUP_RECORD={record}" in uv, "record-sync 讀同一個紀錄檔"
    assert (calls / "record-seen.txt").exists()
    assert not Path(record).exists(), "入帳後刪掉暫存紀錄"


# =========================================================== 審核 F3：結果鏈 idle、只有 box／PA 同步時也寫 refresh_log

def _finish_env(tmp_path, monkeypatch, state: dict):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setenv("POSTSEASON_STATE", str(path))
    monkeypatch.setenv("POSTSEASON_STATUS", str(tmp_path / "last.json"))
    monkeypatch.setattr(pe, "_now", lambda: tpe(10, 21, 22, 46))
    return path


def _boxpa_only_state() -> dict:
    """10-21 C4 夜的形狀：結果鏈這次 idle，box／PA 同步沿用當晚備份且對帳通過。"""
    return {**pe.empty_state(),
            "last_run": {"at": "2026-10-21T14:44:00+00:00", "action": "idle", "reason": "no_events"},
            "boxpa_last": {"at": "2026-10-21T14:46:00+00:00", "action": "sync", "games": ["2026-C-4"], "code": 0,
                           "outcome": "ok"},
            "backup_uses": [{"at": "2026-10-21T14:44:30+00:00", "mode": "reuse",
                             "path": "/x/backups-postseason-evening/cpbl-20261021.sql.gz"}]}


def test_boxpa_only_sync_writes_refresh_log_then_clears_uses(tmp_path, monkeypatch, capsys):
    path = _finish_env(tmp_path, monkeypatch, _boxpa_only_state())
    calls = []
    monkeypatch.setattr(pe, "log_local_refresh",
                        lambda state, ok, note: calls.append((ok, note, list(state["backup_uses"]))))
    assert pe.main(["finish"]) == 0 and capsys.readouterr().out.strip() == "ok"
    assert len(calls) == 1
    ok, note, uses = calls[0]
    assert ok is True and note is None and uses[0]["mode"] == "reuse"
    assert json.loads(path.read_text())["backup_uses"] == [], "寫進 refresh_log 之後才清空"
    status = json.loads((tmp_path / "last.json").read_text())
    assert status["backup_uses"][0]["path"].endswith("cpbl-20261021.sql.gz")


def test_refresh_log_failure_keeps_uses_for_the_next_finish(tmp_path, monkeypatch):
    path = _finish_env(tmp_path, monkeypatch, _boxpa_only_state())

    def broken(state, ok, note):
        raise RuntimeError("PoolTimeout")

    monkeypatch.setattr(pe, "log_local_refresh", broken)
    assert pe.main(["finish"]) == 0
    assert len(json.loads(path.read_text())["backup_uses"]) == 1, "沒寫進資料庫紀錄就不清空"


def test_idle_wake_without_backup_use_writes_no_refresh_log(tmp_path, monkeypatch):
    """負控：結果鏈 idle、這次沒有任何同步用到備份 → 不寫 refresh_log（不因舊的 boxpa_last 重寫）。"""
    _finish_env(tmp_path, monkeypatch, {**_boxpa_only_state(), "backup_uses": []})
    calls = []
    monkeypatch.setattr(pe, "log_local_refresh", lambda *a: calls.append(a))
    assert pe.main(["finish"]) == 0 and calls == []


def test_boxpa_only_failed_sync_is_logged_as_not_ok(tmp_path, monkeypatch):
    state = _boxpa_only_state()
    state["boxpa_last"] = {**state["boxpa_last"], "code": 68, "outcome": "retry"}
    _finish_env(tmp_path, monkeypatch, state)
    calls = []
    monkeypatch.setattr(pe, "log_local_refresh", lambda state, ok, note: calls.append((ok, note)))
    assert pe.main(["finish"]) == 0 and calls == [(False, "boxpa_retry")]
