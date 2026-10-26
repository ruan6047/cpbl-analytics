"""#353 WP1：``refresh-cpbl-prod.sh`` 的 ``sync_pa_build`` 接線（跑真腳本＋假 ssh／docker／uv，零 DB 零網路）。

payload 的內容與守衛由 ``tests/test_pa_incremental_353.py`` 驗；這裡只驗殼層的順序與成敗：
payload 檔原樣以單交易送出、空 payload 不送、對帳不等 fail-closed（不寫 refresh 標記）、
全量模式只能人工指定、任何路徑都不再 TRUNCATE PA 五表、同步前後印時戳。
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

PA_MARKER = "-- stub pa payload 353"

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
elif "cpbl.ingest.pa_incremental" in argv and "payload" in argv:
    out = argv[argv.index("--out") + 1]
    Path(out).write_text(os.environ.get("STUB_PA_PAYLOAD", ""), encoding="utf-8")
    rc = int(os.environ.get("STUB_PA_PAYLOAD_RC", "0"))
    if rc:
        Path(out).write_text("", encoding="utf-8")
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
        "STUB_PA_PAYLOAD": f"SET LOCAL lock_timeout = '10s';\n{PA_MARKER}\n",
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


def test_payload_file_is_sent_once_in_a_single_transaction_then_reconciled(tmp_path: Path) -> None:
    result, ssh, uv = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    sent = [c for c in ssh if PA_MARKER in c["stdin"]]
    assert len(sent) == 1
    assert "--single-transaction" in sent[0]["argv"][-1] and "ON_ERROR_STOP=1" in sent[0]["argv"][-1]
    payload_calls, reconcile_calls = _pa_uv(uv, "payload"), _pa_uv(uv, "reconcile")
    assert len(payload_calls) == 1 and len(reconcile_calls) == 1
    assert "--full" not in payload_calls[0], "日常路徑不得帶全量旗標"
    assert uv.index(payload_calls[0]) < uv.index(reconcile_calls[0])
    assert "PA 同步開始" in result.stdout and "PA 同步結束" in result.stdout, "WP1-7：同步前後時戳"
    assert not any("TRUNCATE cpbl.game_recap" in c["stdin"] for c in ssh)
    assert not list((tmp_path / "tmp").glob("cpbl-pa-sync.*")), "成功後不留 payload"


def test_empty_payload_sends_nothing_but_still_reconciles(tmp_path: Path) -> None:
    result, ssh, uv = _run(tmp_path, STUB_PA_PAYLOAD="")
    assert result.returncode == 0, result.stderr
    assert not any(PA_MARKER in c["stdin"] for c in ssh)
    assert "沒有要替換的場" in result.stdout
    assert len(_pa_uv(uv, "reconcile")) == 1


def test_reconcile_mismatch_stops_the_chain_before_the_refresh_marker(tmp_path: Path) -> None:
    result, ssh, _ = _run(tmp_path, STUB_PA_RECONCILE_RC="68")
    assert result.returncode == 68
    assert "全族對帳未通過" in result.stderr and "PA_FULL_RESYNC" in result.stderr
    assert not any("refresh_log" in " ".join(c["argv"]) for c in ssh), "對帳不等不得寫成功標記"
    assert not any("cpbl-train-outcome" in " ".join(c["argv"]) for c in ssh), "對帳不等不得進第 4 步"


def test_payload_guard_failure_sends_nothing(tmp_path: Path) -> None:
    result, ssh, uv = _run(tmp_path, STUB_PA_PAYLOAD_RC="67")
    assert result.returncode == 67
    assert not any(PA_MARKER in c["stdin"] for c in ssh)
    assert _pa_uv(uv, "reconcile") == []


def test_full_resync_is_manual_only_and_passes_the_flag(tmp_path: Path) -> None:
    result, _, uv = _run(tmp_path / "manual", PA_FULL_RESYNC="1")
    assert result.returncode == 0, result.stderr
    assert "--full" in _pa_uv(uv, "payload")[0]
    assert "全量" in result.stdout


def test_full_resync_refused_from_the_daily_chain_before_any_remote_call(tmp_path: Path) -> None:
    for name, extra in (("daily", {"PA_FULL_RESYNC": "1", "DAILY_DAY_TYPE": "sync_only"}),
                        ("no-detail", {"PA_FULL_RESYNC": "1", "WITH_DETAIL": None}),
                        ("bad-value", {"PA_FULL_RESYNC": "yes"})):
        result, ssh, uv = _run(tmp_path / name, **extra)
        assert result.returncode == 64, (name, result.stderr)
        assert ssh == [], f"{name}：未備份、未寫入"
        assert _pa_uv(uv, "payload") == []


def test_no_path_in_the_script_truncates_the_pa_family() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert "TRUNCATE cpbl.game_recap" not in code
    body = source.split("sync_pa_build() {\n", 1)[1].split("\n}\n", 1)[0]
    assert "_stage " not in body and "TRUNCATE" not in body
    assert '< "$payload"' in body and "} | ssh" not in body, "payload 先落地成檔，不以管線直送"


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


@pytest.mark.parametrize(("extra", "rc"), [({"STUB_PA_RECONCILE_RC": "68"}, 68), ({"STUB_PA_PAYLOAD_RC": "67"}, 67)])
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
    assert any(PA_MARKER in c["stdin"] for c in ssh), "後續同步必須照常執行"
    argv = _sentinel_calls(uv)[0]
    assert argv[argv.index("--out") + 1].startswith(str(tmp_path / "tmp")), "紀錄改寫 TMPDIR"
