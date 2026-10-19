"""#293 S12 WP3：晚間鏈「目標場 box／PA 階段」的狀態機與編排。

純函式部分以**真實** 2026 E4 本機事實（``tests/fixtures/postseason_sources_2026_real.json``）為底，
把「現在」放在 E4 賽事日晚上；需要「box 尚未到／PA 晚到」時只改與情境直接相關的欄位
（列數歸零、拿掉 published），測試名稱寫明。這些是狀態機的情境驗證，⛔ 不是真實當晚事件的證據
（真實當晚證據由 WP5 取得）。

編排部分沿 ``tests/test_postseason_evening_sync.py`` 的假 uv／假 refresh 手法：零 DB、零網路、零排程。
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpbl import postseason_sources as ps
from cpbl.ingest import postseason_evening as pe

TPE = ZoneInfo("Asia/Taipei")
ROOT = Path(__file__).resolve().parents[1]
EVENING = ROOT / "scripts" / "postseason-evening.sh"
FIXTURE = ROOT / "tests" / "fixtures" / "postseason_sources_2026_real.json"
KEY = "2026-E-4"


def tpe(m, d, hh, mm):
    return datetime(2026, m, d, hh, mm, tzinfo=TPE)


def real_e4() -> ps.LocalFacts:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))["games"][KEY]
    return ps.facts_from_json(raw)


LOCAL = {KEY: pe.LocalGame(2026, "E", 4, "2026-10-12", "ADD011", "ACN011", "洲際", True)}


def box_missing(f: ps.LocalFacts) -> ps.LocalFacts:
    """box 尚未抓到的時點：真實 E4 的 livelog／scoreboard 列數歸零、尚無 published。"""
    return dataclasses.replace(f, box_counts={**f.box_counts, "game_livelog": 0, "game_scoreboard": 0},
                               published_build=None, published_at=None)


def no_pa(f: ps.LocalFacts) -> ps.LocalFacts:
    return dataclasses.replace(f, published_build=None, published_at=None)


def manifest(f: ps.LocalFacts, at: str, *, box_ok=True, pa_ok: bool | None = True) -> dict:
    return {"at": at, "ok": bool(box_ok) and pa_ok is not False, "games": {KEY: {
        "box_ok": box_ok, "pa_ok": pa_ok, "pa_sent": pa_ok is not None,
        "box": {t: {"local": n, "prod": n} for t, n in f.box_counts.items()},
        "pa": {t: {"local": n, "prod": n} for t, n in f.pa_counts.items()},
        "published_build_local": f.published_build, "published_build_prod": f.published_build}}}


LAST_PARTS: dict[str, list[str]] = {}


def step(state, now, facts):
    recs = pe.boxpa_refresh(state, now, LOCAL, {KEY: facts})
    action, keys, parts = pe.boxpa_plan(state, now, recs)
    LAST_PARTS["parts"] = parts
    return action, keys


def record_sync(state, now, facts, code, m=None, elapsed=30.0):
    """照上一次 boxpa_plan 給的 parts 入帳（＝shell 真的交給 scoped 同步的來源）。"""
    pe.boxpa_refresh(state, now, LOCAL, {KEY: facts})
    out = pe.boxpa_record_sync(state, now, [KEY], code, m, elapsed, LAST_PARTS.get("parts") or ["box", "pa"])
    pe.boxpa_refresh(state, now, LOCAL, {KEY: facts})
    return out


# ------------------------------------------------------------------ 選場與時窗

def test_window_is_taipei_today_or_yesterday_before_daily_guard():
    assert pe.boxpa_window("2026-10-12", tpe(10, 12, 21, 0))
    assert pe.boxpa_window("2026-10-12", tpe(10, 13, 0, 30)), "跨 24:00 照常處理（沒有鐘點截止）"
    assert pe.boxpa_window("2026-10-12", tpe(10, 13, 9, 44))
    assert not pe.boxpa_window("2026-10-12", tpe(10, 13, 9, 45)), "讓位 10:10 起交給每日鏈"
    assert not pe.boxpa_window("2026-10-11", tpe(10, 12, 21, 0))


def test_not_completed_game_is_never_a_target():
    state = pe.empty_state()
    local = {KEY: dataclasses.replace(LOCAL[KEY], completed=False)}
    assert pe.boxpa_refresh(state, tpe(10, 12, 21, 0), local, {}) == {}
    assert state.get("boxpa", {}) == {}


# ------------------------------------------------------------------ final 先到 → box 明細 www

def test_final_first_box_missing_requests_detail_with_3_attempt_and_20_minute_limits():
    state, f = pe.empty_state(), box_missing(real_e4())
    t0 = tpe(10, 12, 21, 30)
    assert step(state, t0, f) == ("detail", [KEY])
    pe.boxpa_record_detail(state, t0, [KEY], [])
    assert step(state, tpe(10, 12, 21, 49), f) == ("idle", []), "未滿 20 分鐘不再連 www"
    t1 = tpe(10, 12, 21, 50)
    assert step(state, t1, f) == ("detail", [KEY])
    pe.boxpa_record_detail(state, t1, [KEY], [])
    t2 = tpe(10, 12, 22, 10)
    assert step(state, t2, f) == ("detail", [KEY])
    pe.boxpa_record_detail(state, t2, [KEY], [])
    assert step(state, tpe(10, 12, 22, 40), f) == ("idle", [])
    rec = state["boxpa"][KEY]
    assert (rec["state"], rec["reason"]) == ("unreached", "www_detail_incomplete_after_max_attempts")
    assert len(rec["detail_attempts"]) == 3


def test_challenge_failures_shared_with_results_chain_stop_detail_tonight():
    state, f = pe.empty_state(), box_missing(real_e4())
    state["challenge_failures"] = [pe._iso(tpe(10, 12, 20, 0))]   # 結果鏈稍早已被挑戰一次
    t0 = tpe(10, 12, 21, 30)
    assert step(state, t0, f)[0] == "detail"
    pe.boxpa_record_detail(state, t0, [KEY], [{"kind": "E", "error": "反爬挑戰 token 失敗"}])
    assert state["www_blocked_at"], "第二次挑戰即停當晚"
    assert step(state, tpe(10, 12, 22, 0), f) == ("idle", [])


def test_c2_detail_shares_kind_cooldown_ledger_with_results_and_starter_checkpoints():
    """需求方裁定 C2（#293 issuecomment-6186074916）：同賽別任兩次 www 冷啟動間隔 ≥20 分鐘，不論是
    結果鏈、#292 先發時點或 box 明細發的——三者讀寫同一本 ``www_requests``（``kind_cooled``）。"""
    state, f = pe.empty_state(), box_missing(real_e4())
    t0 = tpe(10, 12, 21, 30)
    pe.record_scrape(state, t0, errors=[], changed=True, stats_has_c=False, local_c_rows=0,
                     kinds=("E",))                        # 結果鏈剛抓過 E（getgamedatas）
    assert step(state, tpe(10, 12, 21, 31), f) == ("idle", []), "結果鏈 www 後 20 分鐘內不抓明細"
    assert step(state, tpe(10, 12, 21, 50), f) == ("detail", [KEY])
    t1 = tpe(10, 12, 21, 50)
    pe.boxpa_record_detail(state, t1, [KEY], [])
    assert state["www_requests"]["E"] == pe._iso(t1), "明細也寫進共用帳本"
    assert not pe.kind_cooled(state, "E", tpe(10, 12, 22, 9)), "結果鏈／先發時點同樣要等明細後 20 分鐘"
    assert pe.kind_cooled(state, "E", tpe(10, 12, 22, 10))
    assert pe.kind_cooled(state, "C", tpe(10, 12, 21, 51)), "不同賽別互不連坐"


# ------------------------------------------------------------------ box 到齊 → 同步；PA 晚到

def test_box_then_pa_late_two_syncs_then_delivered_same_night():
    state, full = pe.empty_state(), real_e4()
    f = no_pa(full)
    t0 = tpe(10, 12, 22, 0)
    assert step(state, t0, f) == ("sync", [KEY])
    assert record_sync(state, t0, f, 0, manifest(f, "2026-10-12T22:01:00+08:00", pa_ok=None)) == "ok"
    src = state["boxpa"][KEY]["sources"]
    assert src["box"]["status"] == "delivered" and src["box"]["same_night"] is True
    assert (src["pa"]["status"], src["pa"]["reason"]) == ("pending_update", "no_local_published_build")
    assert step(state, tpe(10, 12, 22, 5), f) == ("build", [KEY]), "PA 未 published：先 build，不重送 box"
    t1 = tpe(10, 12, 22, 30)                       # PA 晚到：本機 published 出現
    assert step(state, t1, full) == ("sync", [KEY])
    assert record_sync(state, t1, full, 0, manifest(full, "2026-10-12T22:31:00+08:00")) == "ok"
    assert step(state, tpe(10, 12, 22, 35), full) == ("idle", [])
    rec = state["boxpa"][KEY]
    assert rec["state"] == "delivered"
    assert rec["sources"]["pa"]["same_night"] is True and rec["sources"]["final"]["status"] == "delivered"


def test_f2_same_night_new_published_pa_after_delivery_is_resent_once():
    """#293 審核席 1 F2：已 delivered 的場，同晚出現新的本機 published PA → 重新打開、只送 PA；
    PA 額度（首送＋1 次）用完後再有新版就不再送（交隔日 10:10）。"""
    state, f = pe.empty_state(), real_e4()
    t0 = tpe(10, 12, 22, 0)
    assert step(state, t0, f) == ("sync", [KEY]) and LAST_PARTS["parts"] == ["box", "pa"]
    record_sync(state, t0, f, 0, manifest(f, "2026-10-12T22:01:00+08:00"))
    assert step(state, tpe(10, 12, 22, 5), f) == ("idle", []) and state["boxpa"][KEY]["state"] == "delivered"
    v2 = dataclasses.replace(f, published_build="11111111-1111-1111-1111-111111111111",
                             published_at="2026-10-12T22:20:00+08:00")
    t1 = tpe(10, 12, 22, 30)
    assert step(state, t1, v2) == ("sync", [KEY]) and LAST_PARTS["parts"] == ["pa"]
    assert (state["boxpa"][KEY]["state"], state["boxpa"][KEY]["reason"]) == ("open", "reopened_source_changed")
    record_sync(state, t1, v2, 0, manifest(v2, "2026-10-12T22:31:00+08:00"))
    rec = state["boxpa"][KEY]
    assert rec["sources"]["pa"]["status"] == "delivered" and rec["sources"]["box"]["status"] == "delivered"
    assert [s["sources"] for s in rec["sends"]] == [["box", "pa"], ["pa"]]
    v3 = dataclasses.replace(v2, published_build="22222222-2222-2222-2222-222222222222")
    assert step(state, tpe(10, 12, 22, 40), v3) == ("build", [KEY]), "已同步 2 次：只 build、不再送"


def test_r1_pa_built_in_the_same_wake_goes_out_with_box_in_one_sync():
    """#293 再審 R1：plan 當下本機尚無 published（box 剛到齊）→ shell 先跑 PA build → 再 plan →
    同一次同步送 box＋pa。正常路徑每場只需 1 次 production 同步。"""
    state, full = pe.empty_state(), real_e4()
    nopa = no_pa(full)
    t0 = tpe(10, 12, 22, 0)
    assert step(state, t0, nopa) == ("sync", [KEY]) and LAST_PARTS["parts"] == ["box"], "build 前的 plan"
    # shell：boxpa-prepare（PA build 產出 published）→ 再 plan，這次的 parts 才交給 scoped 同步
    assert step(state, t0, full) == ("sync", [KEY]) and LAST_PARTS["parts"] == ["box", "pa"]
    record_sync(state, t0, full, 0, manifest(full, "2026-10-12T22:01:00+08:00"))
    assert step(state, tpe(10, 12, 22, 5), full) == ("idle", [])
    rec = state["boxpa"][KEY]
    assert rec["state"] == "delivered" and len(pe.boxpa_syncs(rec)) == 1
    assert rec["sources"]["box"]["same_night"] is True and rec["sources"]["pa"]["same_night"] is True


def test_build_only_when_nothing_else_needs_sending():
    """box 已送達、PA 仍未 published：plan 回 build（shell 只跑 PA build，不同步）。"""
    state, full = pe.empty_state(), real_e4()
    f = no_pa(full)
    t0 = tpe(10, 12, 22, 0)
    step(state, t0, f)
    record_sync(state, t0, f, 0, manifest(f, "2026-10-12T22:01:00+08:00", pa_ok=None))
    assert step(state, tpe(10, 12, 22, 5), f) == ("build", [KEY])
    assert len(pe.boxpa_syncs(state["boxpa"][KEY])) == 1


def test_quota_is_two_syncs_per_game_and_a_resend_sends_only_undelivered_sources():
    """需求方裁定 6196379928（以場計）：每場每晚最多 2 次 production 同步；重送只送未到的來源。"""
    state, full = pe.empty_state(), real_e4()
    f = no_pa(full)
    t0 = tpe(10, 12, 22, 0)
    assert step(state, t0, f) == ("sync", [KEY]) and LAST_PARTS["parts"] == ["box"]
    record_sync(state, t0, f, 68, manifest(f, "2026-10-12T22:01:00+08:00", box_ok=False, pa_ok=None))
    t1 = tpe(10, 12, 22, 5)
    assert step(state, t1, full) == ("sync", [KEY]), "第 2 次（重送）"
    assert LAST_PARTS["parts"] == ["box", "pa"], "重送只送未到的來源：box 對帳不等、PA 尚未送"
    record_sync(state, t1, full, 0, manifest(full, "2026-10-12T22:06:00+08:00"))
    rec = state["boxpa"][KEY]
    assert len(pe.boxpa_syncs(rec)) == 2
    grown = dataclasses.replace(full, box_counts={**full.box_counts, "game_livelog": 356})
    assert step(state, tpe(10, 12, 22, 30), grown) == ("build", [KEY]), "兩次已用完：只 build、不再有第 3 次同步"
    assert len(pe.boxpa_syncs(rec)) == 2


def test_f3_delivered_source_is_not_resent_with_a_later_source():
    """#293 審核席 1 F3（以場計之後的形狀）：box 已送達、PA 晚到時，第 2 次同步只送 PA。"""
    state, full = pe.empty_state(), real_e4()
    f = no_pa(full)
    t0 = tpe(10, 12, 22, 0)
    assert step(state, t0, f) == ("sync", [KEY]) and LAST_PARTS["parts"] == ["box"]
    record_sync(state, t0, f, 0, manifest(f, "2026-10-12T22:01:00+08:00", pa_ok=None))
    t1 = tpe(10, 12, 22, 30)
    assert step(state, t1, full) == ("sync", [KEY]) and LAST_PARTS["parts"] == ["pa"]
    record_sync(state, t1, full, 0, manifest(full, "2026-10-12T22:31:00+08:00"))
    rec = state["boxpa"][KEY]
    assert [x["sources"] for x in rec["sends"]] == [["box"], ["pa"]]
    assert rec["manifest"]["box_at"] == "2026-10-12T22:01:00+08:00", "沒送 box 的那次不覆寫 box 對帳時刻"


def test_delivery_after_midnight_is_recorded_as_not_same_night():
    state, f = pe.empty_state(), real_e4()
    t0 = tpe(10, 13, 0, 20)
    assert step(state, t0, f) == ("sync", [KEY])
    record_sync(state, t0, f, 0, manifest(f, "2026-10-13T00:21:00+08:00"))
    src = state["boxpa"][KEY]["sources"]
    assert src["box"]["status"] == "delivered" and src["box"]["same_night"] is False


def test_reconcile_mismatch_resends_once_then_conflict_without_halting():
    state, f = pe.empty_state(), real_e4()
    bad = manifest(f, "2026-10-12T22:01:00+08:00", box_ok=False, pa_ok=False)
    t0 = tpe(10, 12, 22, 0)
    assert step(state, t0, f) == ("sync", [KEY])
    assert record_sync(state, t0, f, 68, bad) == "retry"
    t1 = tpe(10, 12, 22, 5)
    assert step(state, t1, f) == ("sync", [KEY]), "同來源重送一次"
    assert record_sync(state, t1, f, 68, bad) == "retry"
    assert step(state, tpe(10, 12, 22, 10), f) == ("idle", [])
    rec = state["boxpa"][KEY]
    assert rec["state"] == "conflict" and rec["sources"]["box"]["status"] == "delivered_conflict"
    assert not state.get("halted"), "對帳不等只停該場 box／PA，不擋結果鏈"


def test_transient_ssh_failure_twice_is_unreached():
    state, f = pe.empty_state(), real_e4()
    for t in (tpe(10, 12, 22, 0), tpe(10, 12, 22, 5)):
        assert step(state, t, f) == ("sync", [KEY])
        record_sync(state, t, f, 72, None)
    rec = state["boxpa"][KEY]
    assert (rec["state"], rec["reason"]) == ("unreached", "sync_transient_failure_after_resend")


def test_prod_not_final_yet_does_not_consume_an_attempt():
    state, f = pe.empty_state(), real_e4()
    for t in (tpe(10, 12, 22, 0), tpe(10, 12, 22, 5), tpe(10, 12, 22, 10)):
        assert step(state, t, f) == ("sync", [KEY])
        assert record_sync(state, t, f, 73, None) == "waiting"
    assert pe.boxpa_sends(state["boxpa"][KEY], "box") == []


@pytest.mark.parametrize(("code", "elapsed", "reason"), [
    (74, 30.0, "boxpa_sync_exit_74"), (67, 30.0, "boxpa_sync_exit_67"), (1, 30.0, "boxpa_sync_exit_1"),
    (0, 1201.0, "boxpa_sync_over_1200s"),
])
def test_psql_schema_backup_errors_and_over_20_minutes_halt(code, elapsed, reason):
    state, f = pe.empty_state(), real_e4()
    t0 = tpe(10, 12, 22, 0)
    step(state, t0, f)
    assert record_sync(state, t0, f, code, None, elapsed) == "halted"
    assert state["halted"]["reason"] == reason
    assert step(state, tpe(10, 12, 22, 5), f) == ("idle", [])


def test_yields_to_daily_chain_then_hands_off_open_games():
    state, f = pe.empty_state(), box_missing(real_e4())
    step(state, tpe(10, 12, 21, 0), f)
    assert step(state, tpe(10, 13, 9, 50), f) == ("idle", []), "讓位 10:10"
    pe.boxpa_refresh(state, tpe(10, 13, 10, 20), LOCAL, {KEY: f})
    rec = state["boxpa"][KEY]
    assert (rec["state"], rec["reason"]) == ("unreached", "handed_to_daily_chain")
    assert rec["sources"]["box"]["same_night"] is False


def test_official_correction_is_terminal_for_tonight_and_not_resent():
    state, f = pe.empty_state(), dataclasses.replace(real_e4(), reconciliation_outstanding=1)
    t0 = tpe(10, 12, 22, 0)
    assert step(state, t0, f) == ("sync", [KEY])
    record_sync(state, t0, f, 0, manifest(f, "2026-10-12T22:01:00+08:00"))
    assert step(state, tpe(10, 12, 22, 5), f) == ("idle", [])
    rec = state["boxpa"][KEY]
    assert rec["state"] == "correction_pending", "更正待同步：不得記成已送達（fix-4）"
    assert rec["sources"]["pa"]["reason"] == "official_correction_pending", "如實記官方更正待收尾"


# ------------------------------------------------------------------ 不在遠端執行新碼（§9.1）

def test_evening_chain_never_reaches_remote_except_through_refresh_modes():
    """WP3 守衛：晚間鏈本身不 ssh、不碰 prod_cpbl_api；遠端只經 refresh-cpbl-prod.sh 的兩個早退模式。"""
    sh = EVENING.read_text(encoding="utf-8")
    # 只看可執行行：去掉 usage heredoc 與註解（說明文字裡寫「不呼叫 prod_cpbl_api」不算呼叫）。
    sh_code = re.sub(r"usage\(\) \{\n  cat <<'EOF'\n.*?\nEOF\n\}", "", sh, flags=re.S)
    sh_code = "\n".join(line for line in sh_code.splitlines() if not line.lstrip().startswith("#"))
    py = (ROOT / "src" / "cpbl" / "ingest" / "postseason_evening.py").read_text(encoding="utf-8")
    py_code = "\n".join(line for line in py.splitlines() if not line.lstrip().startswith("#"))
    for text in (sh_code, py_code):
        assert "prod_cpbl_api" not in text and "prod_pg" not in text
        assert not re.search(r"^\s*ssh\b", text, re.M)
    assert "usage()" in sh and "usage()" not in sh_code
    assert sh_code.count('bash "$REPO_DIR/scripts/refresh-cpbl-prod.sh"') == 2
    assert "POSTSEASON_RESULTS_ONLY=1 SKIP_SCRAPE=1" in sh and "POSTSEASON_BOXPA_ONLY=1 SKIP_SCRAPE=1" in sh


# ------------------------------------------------------------------ 編排（假 uv／假 refresh）

_UV = """#!/bin/sh
mkdir -p "$STUB_CALLS"
printf '%s\\n' "$*" >> "$STUB_CALLS/uv.txt"
case "$*" in
  *" plan") echo "$STUB_PLAN" ;;
  *" scrape") echo unchanged ;;
  *" sync-due") echo no ;;
  *"boxpa-plan --dry") echo "$STUB_BOXPA" ;;
  *"boxpa-plan") echo "$STUB_BOXPA" ;;
  *"boxpa-detail"*) echo ok ;;
  *"boxpa-prepare"*) echo '{"games": 1}' ;;
  *"boxpa-record"*) echo "${STUB_BOXPA_RECORD:-ok}" ;;
  *"record-sync --code 0") echo synced ;;
  *" finish") echo ok ;;
esac
"""

_REFRESH = """#!/bin/sh
{
  printf 'POSTSEASON_RESULTS_ONLY=%s\\n' "${POSTSEASON_RESULTS_ONLY:-}"
  printf 'POSTSEASON_BOXPA_ONLY=%s\\n' "${POSTSEASON_BOXPA_ONLY:-}"
  printf 'SKIP_SCRAPE=%s\\n' "${SKIP_SCRAPE:-}"
  printf 'POSTSEASON_BOXPA_GAMES=%s\\n' "${POSTSEASON_BOXPA_GAMES:-}"
  printf 'POSTSEASON_BOXPA_PARTS=%s\\n' "${POSTSEASON_BOXPA_PARTS:-}"
  printf 'BACKUP_DIR=%s\\n' "${BACKUP_DIR:-}"
  printf 'BOXPA_MANIFEST=%s\\n' "${BOXPA_MANIFEST:-}"
} >> "$STUB_CALLS/refresh.txt"
exit "${STUB_REFRESH_EXIT:-0}"
"""


def _evening(tmp_path: Path, *, plan="idle", boxpa="idle", stage=None, trigger="manual",
             record="ok", lock_pid=None):
    repo, fake_bin, calls = tmp_path / "repo", tmp_path / "bin", tmp_path / "calls"
    (repo / "scripts").mkdir(parents=True)
    fake_bin.mkdir()
    shutil.copy2(EVENING, repo / "scripts" / EVENING.name)
    for name, body in (("uv", _UV), ("launchctl",
                       '#!/bin/sh\nmkdir -p "$STUB_CALLS"\nprintf \'%s\\n\' "$*" >> "$STUB_CALLS/launchctl.txt"\n')):
        (fake_bin / name).write_text(body, encoding="utf-8")
        (fake_bin / name).chmod(0o755)
    (repo / "scripts" / "refresh-cpbl-prod.sh").write_text(_REFRESH, encoding="utf-8")
    lock = tmp_path / "lock"
    if lock_pid is not None:
        lock.mkdir()
        (lock / "pid").write_text(f"{lock_pid}\n")
    env = {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(tmp_path / "home"), "STUB_CALLS": str(calls),
           "STUB_PLAN": plan, "STUB_BOXPA": boxpa, "STUB_BOXPA_RECORD": record,
           "REFRESH_LOCK_DIR": str(lock), "REFRESH_TRIGGER": trigger,
           "POSTSEASON_BACKUP_DIR": str(tmp_path / "evening-backups")}
    if stage:
        env["POSTSEASON_EVENING_STAGE"] = stage
    result = subprocess.run(["/bin/bash", str(repo / "scripts" / EVENING.name)], cwd=repo, env=env,
                            text=True, capture_output=True, stdin=subprocess.DEVNULL, check=False)

    def read(name):
        p = calls / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    return result, read, lock


def test_both_idle_takes_no_lock_and_calls_no_refresh(tmp_path):
    result, read, lock = _evening(tmp_path)
    assert result.returncode == 0
    assert "boxpa-plan --dry" in read("uv.txt")
    assert not read("refresh.txt") and not lock.exists()


def test_boxpa_sync_without_results_event_runs_scoped_mode_with_evening_backup_dir(tmp_path):
    result, read, lock = _evening(tmp_path, boxpa="sync 2026-C-2 box,pa")
    assert result.returncode == 0, result.stderr
    sync = dict(line.split("=", 1) for line in read("refresh.txt").splitlines())
    assert sync["POSTSEASON_BOXPA_ONLY"] == "1" and sync["SKIP_SCRAPE"] == "1"
    assert sync["POSTSEASON_RESULTS_ONLY"] == ""
    assert sync["POSTSEASON_BOXPA_GAMES"] == "2026-C-2"
    assert sync["BACKUP_DIR"] == str(tmp_path / "evening-backups")
    assert re.fullmatch(r".*/logs/postseason-boxpa-manifest-\d{8}-\d{6}\.json", sync["BOXPA_MANIFEST"])
    uv = read("uv.txt")
    assert sync["POSTSEASON_BOXPA_PARTS"] == "box,pa"
    assert "boxpa-record --games 2026-C-2 --code 0" in uv
    lines_ = uv.splitlines()
    i_prep = next(i for i, x in enumerate(lines_) if x.endswith("boxpa-prepare"))
    i_last_plan = max(i for i, x in enumerate(lines_) if x.endswith("boxpa-plan"))
    i_rec = next(i for i, x in enumerate(lines_) if "boxpa-record" in x)
    assert i_prep < i_last_plan < i_rec, "R1：PA build 在決定 parts 的那次 plan 之前"
    assert "--parts box,pa" in uv
    assert " plan" in uv and uv.rstrip().endswith("finish")
    assert "--group scrape" not in uv, "box 已到齊時不連 www"
    assert not lock.exists()


def test_shell_passes_only_planned_parts_to_scoped_sync(tmp_path):
    """F3：boxpa-plan 說只送 pa，shell 就只把 pa 交給 scoped 同步並以 --parts pa 入帳。"""
    result, read, _ = _evening(tmp_path, boxpa="sync 2026-C-2 pa")
    assert result.returncode == 0, result.stderr
    sync = dict(line.split("=", 1) for line in read("refresh.txt").splitlines())
    assert sync["POSTSEASON_BOXPA_PARTS"] == "pa"
    assert "boxpa-record --games 2026-C-2 --code 0" in read("uv.txt") and "--parts pa" in read("uv.txt")
    no_parts, read2, _ = _evening(tmp_path / "np", boxpa="sync 2026-C-2")
    assert no_parts.returncode == 0 and not read2("refresh.txt"), "沒有 parts 就不同步"


def test_boxpa_detail_uses_scrape_group_then_replans(tmp_path):
    result, read, _ = _evening(tmp_path, boxpa="detail 2026-C-2")
    assert result.returncode == 0, result.stderr
    uv = read("uv.txt")
    assert "run --group scrape python -m cpbl.ingest.postseason_evening boxpa-detail --games 2026-C-2" in uv
    assert uv.count("boxpa-plan") == 3, "預檢＋鎖內一次＋明細後再判一次"


def test_boxpa_halt_boots_out_under_launchd(tmp_path):
    result, read, lock = _evening(tmp_path, boxpa="sync 2026-C-2 box,pa", record="halted", trigger="launchd")
    assert result.returncode == 69
    assert re.search(r"^bootout gui/\d+/com\.cpbl\.postseason-evening$", read("launchctl.txt"), re.M)
    assert not lock.exists()


def test_stage_boxpa_skips_results_plan(tmp_path):
    result, read, _ = _evening(tmp_path, plan="scrape", boxpa="sync 2026-C-2 box,pa", stage="boxpa")
    assert result.returncode == 0, result.stderr
    uv = read("uv.txt")
    assert not re.search(r"(^| )plan$", uv, re.M) and " scrape" not in uv.replace("--group scrape", "")
    assert "POSTSEASON_RESULTS_ONLY=1" not in read("refresh.txt")


def test_invalid_stage_is_64_and_busy_lock_is_75(tmp_path):
    bad, _, _ = _evening(tmp_path / "a", stage="all-plus")
    assert bad.returncode == 64
    busy, read, lock = _evening(tmp_path / "b", boxpa="sync 2026-C-2 box,pa", lock_pid=os.getpid())
    assert busy.returncode == 75 and lock.is_dir() and not read("refresh.txt")


def test_precheck_build_takes_lock_and_runs_pa_build_without_syncing(tmp_path):
    """fix-4 B1：結果鏈 idle、box／PA 預檢回 build → 必須進鎖跑 boxpa-prepare（本機 PA builder），⛔ 不同步。"""
    result, read, lock = _evening(tmp_path, boxpa="build 2026-C-2", stage="boxpa")
    assert result.returncode == 0, result.stderr
    uv = read("uv.txt")
    assert "boxpa-plan --dry" in uv and any(x.endswith("boxpa-prepare") for x in uv.splitlines())
    assert not read("refresh.txt"), "build 不得觸發 production 同步"
    assert uv.rstrip().endswith("finish") and not lock.exists()
    all_mode, read2, _ = _evening(tmp_path / "all", boxpa="build 2026-C-2")
    assert all_mode.returncode == 0 and any(x.endswith("boxpa-prepare") for x in read2("uv.txt").splitlines())
