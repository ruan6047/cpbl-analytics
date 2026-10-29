"""#353 WP1：``refresh-cpbl-prod.sh`` 的 ``sync_pa_build`` 接線（跑真腳本＋假 ssh／docker／uv，零 DB 零網路）。

payload 的內容、分批、限速與失敗即停由 ``tests/test_pa_incremental_353.py``／``tests/test_pa_batched_353.py``
驗；這裡只驗殼層的順序與成敗：r4 起 payload 由 ``pa_incremental apply`` 逐批以單交易送出（shell 不再自己
ssh 送 payload）、任一批失敗即停且不對帳、對帳不等 fail-closed（不寫 refresh 標記）、全量模式只能人工指定、
任何路徑都不再 TRUNCATE PA 五表、同步前後印時戳、本機端 ssh 連線重用有開有關。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_prod_sync_revision_seq import (
    FAKE_LOCAL_SEQ,
    FAKE_PROD_MAX,
    SCRIPT,
    _build_harness,
    _write_exec,
)

APPLY_OK = "PA_BATCHES_COMMITTED=1/1"

_UV_STUB = '''\
import json, os, sys
from pathlib import Path

argv = sys.argv[1:]
log = Path(os.environ["STUB_LOG_DIR"]) / "uv"
log.mkdir(parents=True, exist_ok=True)
(log / ("%03d.json" % len(list(log.glob("*.json"))))).write_text(json.dumps(argv), encoding="utf-8")
joined = " ".join(argv)
if "cpbl.completion" in joined:
    print("home_score + away_score > 0")
elif "cpbl.ingest.pa_incremental" in argv and "apply" in argv:
    workdir = Path(argv[argv.index("--workdir") + 1])
    assert workdir.is_dir(), workdir
    rc = int(os.environ.get("STUB_PA_APPLY_RC", "0"))
    if rc:
        (workdir / "pa-batch-0002-of-0004.sql").write_text("-- kept\\n", encoding="utf-8")
        print(f"✗ PA_BATCH_FAILED 2/4 rc={rc} committed=1/4", file=sys.stderr)
    else:
        print(os.environ.get("STUB_PA_APPLY_OUT", "PA_BATCHES_COMMITTED=1/1"))
    raise SystemExit(rc)
elif any(a.endswith("prod_availability.py") for a in argv):
    # #353 WP4a 哨兵樁：等到停止檔出現（≤10s）才結束，記下是否被 EXIT trap 正常停下。
    import time
    stop = Path(argv[argv.index("--stop-file") + 1])
    for _ in range(100):
        if stop.exists():
            break
        time.sleep(0.1)
    (Path(os.environ["STUB_LOG_DIR"]) / "sentinel-stopped").write_text(
        "stopped" if stop.exists() else "timeout", encoding="utf-8")
elif "cpbl.ingest.pa_incremental" in argv and "reconcile" in argv:
    print('PA_RECONCILE={"ok": true}')
    raise SystemExit(int(os.environ.get("STUB_PA_RECONCILE_RC", "0")))
else:
    print("stub uv " + joined)
'''


def _run(tmp_path: Path, *, logs_is_file: bool = False,
         **env_extra: str | None) -> tuple[subprocess.CompletedProcess, list[dict], list[list[str]]]:
    harness = _build_harness(tmp_path)
    if logs_is_file:  # 讓 mkdir -p "$REPO_DIR/logs" 失敗（審核 1 第 3 項的情境）
        (harness["repo"] / "logs").write_text("not a directory", encoding="utf-8")
    _write_exec(harness["bin"] / "uv", f"#!{sys.executable}\n{_UV_STUB}")
    (tmp_path / "tmp").mkdir(exist_ok=True)
    env = {
        "PATH": f"{harness['bin']}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"),
        "STUB_LOG_DIR": str(harness["log"]),
        "STUB_HELPER_DIR": str(harness["helpers"]),
        "STUB_LOCAL_SEQ": json.dumps(FAKE_LOCAL_SEQ),
        "STUB_PROD_MAX": json.dumps(FAKE_PROD_MAX),
        "VPS": "stub@harness.invalid",
        "LOCAL_DB": "stub-nonexistent-container",
        "DEPLOY_PATH": "/nonexistent/stub-deploy",
        "API_INFO_URL": "http://127.0.0.1:1/api/info",
        "SKIP_SCRAPE": "1",
        "WITH_DETAIL": "1",
    }
    for k, v in env_extra.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    result = subprocess.run(["/bin/bash", str(harness["repo"] / "scripts" / SCRIPT.name)], env=env,
                            text=True, capture_output=True, stdin=subprocess.DEVNULL, check=False)
    ssh_dir, uv_dir = harness["log"] / "ssh", harness["log"] / "uv"
    ssh = [json.loads(p.read_text()) for p in sorted(ssh_dir.glob("*.json"))] if ssh_dir.is_dir() else []
    uv = [json.loads(p.read_text()) for p in sorted(uv_dir.glob("*.json"))] if uv_dir.is_dir() else []
    return result, ssh, uv


def _pa_uv(uv: list[list[str]], command: str) -> list[list[str]]:
    return [a for a in uv if "cpbl.ingest.pa_incremental" in a and command in a]


def test_apply_sends_in_single_transactions_then_reconciles_once(tmp_path: Path) -> None:
    result, ssh, uv = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    apply_calls, reconcile_calls = _pa_uv(uv, "apply"), _pa_uv(uv, "reconcile")
    assert len(apply_calls) == 1 and len(reconcile_calls) == 1
    argv = apply_calls[0]
    sender = argv[argv.index("--apply-psql") + 1]
    assert "--single-transaction" in sender and "ON_ERROR_STOP=1" in sender, "每批＝一個交易"
    assert "--single-transaction" not in argv[argv.index("--target-psql") + 1], "唯讀查詢端不帶交易旗標"
    assert "--full" not in argv, "日常路徑不得帶全量旗標"
    assert uv.index(apply_calls[0]) < uv.index(reconcile_calls[0])
    assert APPLY_OK in result.stdout
    assert "PA 同步開始" in result.stdout and "PA 同步結束" in result.stdout, "WP1-7：同步前後時戳"
    assert not any("TRUNCATE cpbl.game_recap" in c["stdin"] for c in ssh)
    assert not list((tmp_path / "tmp").glob("cpbl-pa-sync.*")), "成功後不留 payload 目錄"


def test_ssh_connection_reuse_is_opened_used_and_closed(tmp_path: Path) -> None:
    """r4 §6 第 3 項：本機端 ControlMaster；查詢與送出都走同一個 ControlPath，結束時 -O exit。"""
    result, ssh, uv = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    masters = [c for c in ssh if "ControlMaster=yes" in c["argv"]]
    assert len(masters) == 1 and "-fN" in masters[0]["argv"]
    path_opt = next(a for a in masters[0]["argv"] if a.startswith("ControlPath="))
    argv = _pa_uv(uv, "apply")[0]
    for flag in ("--target-psql", "--apply-psql"):
        assert f"-o {path_opt}" in argv[argv.index(flag) + 1], flag
    closes = [c for c in ssh if "-O" in c["argv"] and "exit" in c["argv"]]
    assert len(closes) == 1 and f"{path_opt}" in " ".join(closes[0]["argv"])
    assert ssh.index(masters[0]) < ssh.index(closes[0])
    ctl_dir = path_opt.split("=", 1)[1].rsplit("/", 1)[0]
    assert not Path(ctl_dir).exists(), "ControlPath 目錄已清掉"


def test_empty_difference_sends_nothing_but_still_reconciles(tmp_path: Path) -> None:
    result, ssh, uv = _run(tmp_path, STUB_PA_APPLY_OUT="PA_INCREMENTAL_GAMES=0")
    assert result.returncode == 0, result.stderr
    assert "PA_INCREMENTAL_GAMES=0" in result.stdout
    assert len(_pa_uv(uv, "reconcile")) == 1


def test_reconcile_mismatch_stops_the_chain_before_the_refresh_marker(tmp_path: Path) -> None:
    result, ssh, _ = _run(tmp_path, STUB_PA_RECONCILE_RC="68")
    assert result.returncode == 68
    assert "全族對帳未通過" in result.stderr and "PA_FULL_RESYNC" in result.stderr
    assert not any("refresh_log" in " ".join(c["argv"]) for c in ssh), "對帳不等不得寫成功標記"
    assert not any("cpbl-train-outcome" in " ".join(c["argv"]) for c in ssh), "對帳不等不得進第 4 步"


@pytest.mark.parametrize("rc", [67, 72, 74])
def test_batch_failure_stops_without_reconcile_and_keeps_the_failed_payload(tmp_path: Path, rc: int) -> None:
    result, ssh, uv = _run(tmp_path, STUB_PA_APPLY_RC=str(rc))
    assert result.returncode == rc
    assert _pa_uv(uv, "reconcile") == [], "中途失敗不做對帳"
    assert "PA_BATCH_FAILED 2/4" in result.stderr and "後續批未送" in result.stderr
    assert not any("refresh_log" in " ".join(c["argv"]) for c in ssh)
    kept = list((tmp_path / "tmp").glob("cpbl-pa-sync.*/pa-batch-*.sql"))
    assert len(kept) == 1, "失敗批 payload 保留供查"
    assert any("-O" in c["argv"] and "exit" in c["argv"] for c in ssh), "失敗也關掉連線重用"


def test_full_resync_is_manual_only_and_passes_the_flag(tmp_path: Path) -> None:
    result, _, uv = _run(tmp_path / "manual", PA_FULL_RESYNC="1")
    assert result.returncode == 0, result.stderr
    assert "--full" in _pa_uv(uv, "apply")[0]
    assert "全量" in result.stdout


def test_full_resync_refused_from_the_daily_chain_before_any_remote_call(tmp_path: Path) -> None:
    for name, extra in (("daily", {"PA_FULL_RESYNC": "1", "DAILY_DAY_TYPE": "sync_only"}),
                        ("no-detail", {"PA_FULL_RESYNC": "1", "WITH_DETAIL": None}),
                        ("bad-value", {"PA_FULL_RESYNC": "yes"})):
        result, ssh, uv = _run(tmp_path / name, **extra)
        assert result.returncode == 64, (name, result.stderr)
        assert ssh == [], f"{name}：未備份、未寫入"
        assert _pa_uv(uv, "apply") == []


def test_no_path_in_the_script_truncates_the_pa_family() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert "TRUNCATE cpbl.game_recap" not in code
    body = source.split("sync_pa_build() {\n", 1)[1].split("\n}\n", 1)[0]
    assert "_stage " not in body and "TRUNCATE" not in body
    assert "pa_incremental apply" in body and "--apply-psql" in body, "payload 由 apply 逐批落地、斷言後送出"
    assert '< "$payload"' not in body and "} | ssh" not in body, "shell 不再自己送一份全量 payload"


def test_fix1_invariants_are_rewritten_not_deleted() -> None:
    """審核重點 3：FIX1 不變量（id 鏡像、prod 不是 writer、不得用 id 當衝突鍵）改寫成新機制版本。"""
    source = SCRIPT.read_text(encoding="utf-8")
    block = source.split("# canonical PA build 家族同步", 1)[1].split("sync_pa_build() {", 1)[0]
    for phrase in ("id 值直接鏡像本機", "prod 從不獨立寫入這五張表", "不得改回以 id 當衝突鍵",
                   "2026-08-03", "ACCESS EXCLUSIVE", "全族對帳"):
        assert phrase in block, phrase


def test_pa_incremental_module_never_parses_with_the_evening_guard() -> None:
    """每日增量的鍵來源是簽章比對，⛔ 不經、也不放寬晚間鏈 parse_games（A|E|C、≤7 場）。"""
    src = (Path(SCRIPT).parents[1] / "src" / "cpbl" / "ingest" / "pa_incremental.py").read_text(encoding="utf-8")
    assert "parse_games" not in src.split('"""', 2)[2]
    assert os.path.exists(SCRIPT)


# --------------------------------------------------------------------------- WP4a 哨兵接線


def _sentinel_calls(uv: list[list[str]]) -> list[list[str]]:
    return [a for a in uv if any(x.endswith("prod_availability.py") for x in a)]


def test_sentinel_runs_once_per_full_chain_and_is_stopped_by_the_exit_trap(tmp_path: Path) -> None:
    result, _, uv = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    calls = _sentinel_calls(uv)
    assert len(calls) == 1
    argv = calls[0]
    assert argv[argv.index("--base-url") + 1] == "http://127.0.0.1:1", "base 由 API_INFO_URL 去掉 /api/info"
    assert argv[argv.index("--env-file") + 1].endswith("/.env")
    assert "/logs/availability-sentinel-" in argv[argv.index("--out") + 1]
    assert (tmp_path / "calls" / "sentinel-stopped").read_text() == "stopped"


@pytest.mark.parametrize(("extra", "rc"), [({"STUB_PA_RECONCILE_RC": "68"}, 68), ({"STUB_PA_APPLY_RC": "67"}, 67)])
def test_sentinel_never_changes_the_chain_exit_code(tmp_path: Path, extra, rc) -> None:
    result, _, uv = _run(tmp_path, **extra)
    assert result.returncode == rc
    assert len(_sentinel_calls(uv)) == 1
    assert (tmp_path / "calls" / "sentinel-stopped").read_text() == "stopped"


def test_sentinel_starts_before_the_first_production_touch() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index("\nstart_availability_sentinel || ")
    assert source.index("trap _on_exit EXIT\nstart_availability_sentinel || ") < start
    assert start < source.index('echo "==> 2/4 備份 production 資料庫')
    assert source.count("\nstart_availability_sentinel || ") == 1, "只在完整鏈啟動"
    for mode in ("LINEUP_ONLY", "ROSTER_ONLY", "POSTSEASON_RESULTS_ONLY", "POSTSEASON_BOXPA_ONLY",
                 "TEAM_COMPARISON_ONLY"):
        assert source.index(f'if [ -n "${{{mode}:-}}" ]') < start or mode not in source


def test_sentinel_setup_failure_never_changes_the_chain_result(tmp_path: Path) -> None:
    """審核 1 第 3 項：哨兵啟動準備（mkdir）失敗時，每日鏈照跑完、退出碼不變。"""
    result, ssh, uv = _run(tmp_path, logs_is_file=True)
    assert result.returncode == 0, result.stderr
    assert "logs 目錄建立失敗" in result.stderr
    assert len(_pa_uv(uv, "apply")) == 1 and len(_pa_uv(uv, "reconcile")) == 1, "後續同步必須照常執行"
    argv = _sentinel_calls(uv)[0]
    assert argv[argv.index("--out") + 1].startswith(str(tmp_path / "tmp")), "紀錄改寫 TMPDIR"
