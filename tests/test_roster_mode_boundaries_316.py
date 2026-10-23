"""#316 放行回歸：純替身比較兩個既有模式與固定 main 基準；不連線、不寫 DB。"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_prod_sync_revision_seq import (
    FAKE_LOCAL_SEQ,
    FAKE_PROD_MAX,
    _build_harness,
    _write_exec,
)

ROOT = Path(__file__).parents[1]
BASE = "67269ad93339be6c775ac3ef473d53840aa71fb2"
SCRIPT = ROOT / "scripts/refresh-cpbl-prod.sh"


def _baseline():
    return subprocess.check_output(
        ["git", "show", f"{BASE}:scripts/refresh-cpbl-prod.sh"], cwd=ROOT
    )


def _outside_roster(data):
    start = data.index(b'if [ -n "${ROSTER_ONLY:-}" ]; then\n')
    end = data.index(b'if [ -n "${LINEUP_ONLY:-}" ]; then\n', start)
    # Include the exact prefix/header/help/global guards and suffix, with no whitespace normalization.
    return data[:start], data[end:]


# ROSTER_ONLY 區塊以外的位元組，以內容雜湊釘住「放行基準 BASE（67269ad9）＋ #293（PR #307）」的版本
# （需求方裁定 #293 issuecomment-6230423989：#293 在本卡調整比對基準，保護不減）。
# ⛔ 不改成「只比對 ROSTER_ONLY 區塊」：那會丟掉區塊以外的保護（減弱）。
# ⛔ 不釘某個分支 commit 的 SHA：合併方式若不是 merge commit，那個 SHA 不會留在 main 的歷史裡。
# 保護強度與原本相同：區塊以外任何一個位元組改變都會紅。日後有卡要合法改區塊以外，須在該卡更新這兩個值並說明。
# LINEUP_ONLY／POSTSEASON_RESULTS_ONLY 的行為仍由下方測試對 BASE 逐項比對（未改）。
# #344（需求方裁定 #344 issuecomment-6356772769：只改基準，保護不減）：區塊之後新增 mirror_table 與
# 五表同步呼叫，「區塊之後」基準由 0c0143d8…（57789 bytes）更新為下值；區塊之前未變。
OUTSIDE_ROSTER_SHA256 = (
    "8bb65a65c9d990f0ddb7c52b0a71f333074a81c347892dfb66972a50cc76ae90",   # 區塊之前（16517 bytes）
    "fd65aafa5627e94e358b4b689323dad9158155353ccbb1448e03ed8b29c24f94",   # 區塊之後（62063 bytes）
)
# #316 的成果（ROSTER_ONLY 區塊本身）以 main 上合併後的版本為準：#293 不得改動它。
ROSTER_RESULT = "a473695dfca536e365b08c44aa2e85374e8f3e69"


def _roster_block(data):
    start = data.index(b'if [ -n "${ROSTER_ONLY:-}" ]; then\n')
    end = data.index(b'if [ -n "${LINEUP_ONLY:-}" ]; then\n', start)
    return data[start:end]


def test_refresh_bytes_outside_roster_only_are_identical_to_release_base():
    current = SCRIPT.read_bytes()
    prefix, suffix = _outside_roster(current)
    got = (hashlib.sha256(prefix).hexdigest(), hashlib.sha256(suffix).hexdigest())
    assert got == OUTSIDE_ROSTER_SHA256, "ROSTER_ONLY 區塊以外的位元組與放行基準（BASE＋#293）不同"
    roster_result = subprocess.check_output(
        ["git", "show", f"{ROSTER_RESULT}:scripts/refresh-cpbl-prod.sh"], cwd=ROOT)
    assert _roster_block(current) == _roster_block(roster_result), "ROSTER_ONLY 區塊與 #316 合併結果不同"


def _run(tmp_path, script_bytes, mode, scopes, failure):
    h = _build_harness(tmp_path)
    script = h["repo"] / "scripts/refresh-cpbl-prod.sh"
    script.unlink()
    script.write_bytes(script_bytes)
    audit = tmp_path / "ordered.jsonl"
    for name in ("docker", "ssh", "uv", "curl"):
        stub = h["bin"] / name
        original = stub.with_name(name + "-stub")
        stub.rename(original)
        _write_exec(stub, f'''#!{sys.executable}
import json, os, sys
with open(os.environ["BOUNDARY_AUDIT"], "a") as f:
    f.write(json.dumps([{name!r}, *sys.argv[1:]]) + "\\n")
os.execv({str(original)!r}, [{str(original)!r}, *sys.argv[1:]])
''')
    _write_exec(h["repo"] / "scripts/backup-prod-db.sh", f'''#!{sys.executable}
import json, os, sys
with open(os.environ["BOUNDARY_AUDIT"], "a") as f:
    f.write(json.dumps(["backup", os.environ.get("BACKUP_DIR"), os.environ.get("BACKUP_KEEP")]) + "\\n")
if os.environ["BOUNDARY_FAILURE"] == "backup": sys.exit(9)
print("/fixture-backup.sql.gz")
''')
    py = h["bin"] / "python3"
    _write_exec(py, f'''#!{sys.executable}
import json, os, sys
if len(sys.argv) > 1 and sys.argv[1].endswith("verify_refresh_info.py"):
    with open(os.environ["BOUNDARY_AUDIT"], "a") as f:
        f.write(json.dumps(["verify", *sys.argv[2:]]) + "\\n")
    sys.stdin.read()
    sys.exit(3 if os.environ["BOUNDARY_FAILURE"] == "verify" else 0)
os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
''')
    env = {
        "PATH": f"{h['bin']}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "STUB_LOG_DIR": str(h["log"]), "STUB_HELPER_DIR": str(h["helpers"]),
        "STUB_LOCAL_SEQ": json.dumps(FAKE_LOCAL_SEQ), "STUB_PROD_MAX": json.dumps(FAKE_PROD_MAX),
        "VPS": "boundary.invalid", "LOCAL_DB": "boundary-db.invalid",
        "DEPLOY_PATH": "/fixture-deploy", "API_INFO_URL": "https://boundary.invalid/info",
        "BACKUP_DIR": str(tmp_path / "backup"), "BACKUP_KEEP": "3",
        "SKIP_SCRAPE": "1", mode: "1", "BOUNDARY_AUDIT": str(audit),
        "BOUNDARY_FAILURE": failure,
    }
    if scopes is not None:
        env["ROSTER_SCOPES"] = scopes
    result = subprocess.run(["/bin/bash", str(script)], env=env, capture_output=True,
                            text=True, timeout=20, stdin=subprocess.DEVNULL)
    ordered = audit.read_text() if audit.exists() else ""
    # Pipeline peers start concurrently: retain stage order while canonicalizing only
    # adjacent pg_dump/ssh and curl/verifier peers (never reorder sequential stages).
    actions = [json.loads(line) for line in ordered.splitlines()]
    for i in range(len(actions) - 1):
        left, right = actions[i:i + 2]
        names = {left[0], right[0]}
        dump_pair = names == {"docker", "ssh"} and "pg_dump" in str(left + right)
        if dump_pair or names == {"curl", "verify"}:
            actions[i:i + 2] = sorted([left, right], key=lambda call: call[0])
    ordered = "".join(json.dumps(a) + "\n" for a in actions)
    payloads = [json.loads(p.read_text()) for p in sorted((h["log"] / "ssh").glob("*.json"))]
    def normalize(value):
        return value.replace(str(tmp_path), "<fixture>")
    return result.returncode, normalize(ordered), payloads, result.stdout, result.stderr


@pytest.mark.parametrize("mode", ["LINEUP_ONLY", "POSTSEASON_RESULTS_ONLY"])
@pytest.mark.parametrize("scopes", [None, "2026:C:AAA011,2026:C:ACN011", "invalid scope"])
@pytest.mark.parametrize("failure", ["none", "backup", "verify"])
def test_existing_modes_match_base_commands_payload_order_and_exit(tmp_path, mode, scopes, failure):
    base = _run(tmp_path / "base", _baseline(), mode, scopes, failure)
    current = _run(tmp_path / "current", SCRIPT.read_bytes(), mode, scopes, failure)
    assert current == base
    expected = 9 if failure == "backup" else 68 if failure == "verify" and mode == "POSTSEASON_RESULTS_ONLY" else 0
    assert current[0] == expected, current[3:]
    actions = [json.loads(line) for line in current[1].splitlines()]
    names = [a[0] for a in actions]
    assert "backup" in names
    if failure == "backup":
        assert "ssh" not in names
    else:
        assert names.index("backup") < names.index("ssh")
        payload = "\n".join(p["stdin"] for p in current[2])
        tables = set(re.findall(r"INSERT INTO cpbl\.(\w+)", payload))
        if mode == "LINEUP_ONLY":
            assert tables == {"game_lineup_announcement_revisions"}
            assert "verify" not in names
            assert any("db.migrate" in str(a) for a in actions)
        else:
            assert tables == {"games", "game_schedule_status_revisions", "game_source_revisions", "official_change_signals"}
            assert "verify" in names
            assert not any("db.migrate" in str(a) for a in actions)
    assert not any(word in str(actions) for word in ("cpbl.rosters.sync", "cpbl-scrape", "cpbl-build-features", "cpbl-train", "refresh_log"))
