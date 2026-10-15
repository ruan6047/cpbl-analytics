"""#292 A1 E4：``POSTSEASON_RESULTS_ONLY`` 的實際提交邊界演練（PLAN plan-3 §1 F11、§9 E4）。

跑**真的** ``scripts/refresh-cpbl-prod.sh``（symlink 進假 repo），沿用
``tests/test_prod_sync_revision_seq.py`` 的零 DB／零網路 harness，再把 ``ssh``／``docker``／
``backup-prod-db.sh``／``python3`` 換成可在指定邊界注入失敗的樁。``ssh`` 樁對每份 psql payload
記錄退出碼：回 0 的那份＝該表在 production 端「已提交」（各表各自 ``--single-transaction``）。

三類邊界（逐一核對 production 端實際已寫的表）：

1. 任何寫入之前：參數／目錄（64）、本機 freshness 基準（65）、已驗證備份失敗 ⇒ 四表都未寫。
2. 第 k 張表失敗（k＝1～4；該表的寫入前檢查或該表交易本身）⇒ 前 k−1 張已提交、第 k 張起未寫。
3. 提交後 data-only 對帳不等（68）⇒ 四表都已寫。

每種退出碼再經晚間鏈 ``record_sync``：68 ⇒ 停止當晚（blocked），其餘非零 ⇒ halted；
並掛到該次 #292 先發時點紀錄的 ``sync_code``。⛔ 不改 ``refresh-cpbl-prod.sh``（本卡禁改）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpbl.ingest import postseason_evening as pe
from cpbl.ingest import starter_checkpoints as sc
from tests.test_prod_sync_revision_seq import (
    _DOCKER_STUB,
    FAKE_LOCAL_SEQ,
    FAKE_PROD_MAX,
    _build_harness,
    _write_exec,
)

ORDER = ("games", "game_schedule_status_revisions", "game_source_revisions",
         "official_change_signals")

# 在既有 docker 樁之前插入注入點（其餘行為原樣沿用既有樁）。
_DOCKER_INJECT = '''\
import json, os, re, sys
argv = sys.argv[1:]
joined = " ".join(argv)
m = re.search(r"table_name='(\\w+)'", joined)
if m and "information_schema.columns" in joined:
    if m.group(1) == os.environ.get("STUB_EXTRA_COLUMN_TABLE"):
        sys.path.insert(0, os.environ["STUB_HELPER_DIR"])
        from stub_helpers import log_call
        log_call("docker", argv, "")
        print("column_added_without_sync_list")
        raise SystemExit(0)
m = re.search(r"pg_get_serial_sequence\\('cpbl\\.(\\w+)'", joined)
if m and m.group(1) == os.environ.get("STUB_SEQUENCE_MISSING_TABLE"):
    print("")
    raise SystemExit(0)
if "max(game_date)" in joined and os.environ.get("STUB_FRESHNESS_EMPTY") == "1":
    print("|0")
    raise SystemExit(0)
if "pg_dump" in argv and argv[argv.index("-t") + 1].split(".", 1)[1] == os.environ.get("STUB_INJECT_SETVAL_TABLE"):
    os.environ["STUB_INJECT_SETVAL"] = "1"
'''

_SSH_STUB = '''\
import json, os, re, sys
from pathlib import Path
argv = sys.argv[1:]
stdin = "" if "-n" in argv else sys.stdin.read()
rc = 0
fail = os.environ.get("STUB_PSQL_FAIL_TABLE")
if fail and ("INSERT INTO cpbl.%s " % fail) in stdin:
    rc = 3   # psql ON_ERROR_STOP：該表 --single-transaction 整份回滾
out = Path(os.environ["STUB_LOG_DIR"]) / "ssh"
out.mkdir(parents=True, exist_ok=True)
(out / ("%03d.json" % len(list(out.glob("*.json"))))).write_text(
    json.dumps({"argv": argv, "stdin": stdin, "rc": rc}), encoding="utf-8")
m = re.search(r"max\\(id\\), 0\\) FROM cpbl\\.(\\w+)", argv[-1] if argv else "")
if m:
    print(json.loads(os.environ["STUB_PROD_MAX"]).get(m.group(1), 0))
raise SystemExit(rc)
'''


def run_boundary(tmp_path: Path, **inject: str) -> tuple[int, list[str], str]:
    """跑一次 POSTSEASON_RESULTS_ONLY；回 (退出碼, production 端已提交的表, stderr)。"""
    harness = _build_harness(tmp_path)
    _write_exec(harness["bin"] / "docker",
                f"#!{sys.executable}\n{_DOCKER_INJECT}\n{_DOCKER_STUB}")
    _write_exec(harness["bin"] / "ssh", f"#!{sys.executable}\n{_SSH_STUB}")
    backup = harness["repo"] / "scripts" / "backup-prod-db.sh"
    backup.unlink()
    _write_exec(backup, "#!/bin/sh\nexit 1\n" if inject.pop("BACKUP_FAIL", None)
                else "#!/bin/sh\necho /fixture/evening-backup.sql.gz\n")
    if inject.pop("VERIFY_MISMATCH", None):
        _write_exec(harness["bin"] / "python3", "#!/bin/sh\ncat > /dev/null\nexit 3\n")
    prod_max = dict(FAKE_PROD_MAX)
    if (t := inject.pop("TELEMETRY_FAIL_TABLE", None)):
        prod_max[t] = "not-a-number"
    (tmp_path / "tmp").mkdir(exist_ok=True)
    env = {
        "PATH": f"{harness['bin']}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"), "STUB_LOG_DIR": str(harness["log"]),
        "STUB_HELPER_DIR": str(harness["helpers"]),
        "STUB_LOCAL_SEQ": json.dumps(FAKE_LOCAL_SEQ), "STUB_PROD_MAX": json.dumps(prod_max),
        "VPS": "stub@harness.invalid", "LOCAL_DB": "stub-nonexistent-container",
        "DEPLOY_PATH": "/nonexistent/stub-deploy", "API_INFO_URL": "http://127.0.0.1:1/api/info",
        "POSTSEASON_RESULTS_ONLY": "1", "SKIP_SCRAPE": "1",
        "BACKUP_DIR": str(tmp_path / "evening-backups"), "BACKUP_KEEP": "3",
        **inject,
    }
    if env.get("BACKUP_DIR") == "":
        del env["BACKUP_DIR"]
    result = subprocess.run(["/bin/bash", str(harness["repo"] / "scripts" / "refresh-cpbl-prod.sh")],
                            env=env, text=True, capture_output=True, stdin=subprocess.DEVNULL,
                            check=False)
    ssh_dir = harness["log"] / "ssh"
    calls = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(ssh_dir.glob("*.json"))] \
        if ssh_dir.is_dir() else []
    committed = [t for t in ORDER for c in calls
                 if f"INSERT INTO cpbl.{t} " in c["stdin"] and c["rc"] == 0]
    return result.returncode, committed, result.stderr


G, SR, SRC, SIG = ORDER
# (名稱, 注入, 預期退出碼, 預期 production 已提交的表)
SCENARIOS = [
    ("ok", {}, 0, [G, SR, SRC, SIG]),
    # 類 1：任何寫入之前
    ("pre_write:param_backup_dir_missing", {"BACKUP_DIR": ""}, 64, []),
    ("pre_write:freshness_baseline", {"STUB_FRESHNESS_EMPTY": "1"}, 65, []),
    ("pre_write:verified_backup_failed", {"BACKUP_FAIL": "1"}, 1, []),
    # 類 2：第 k 張表（寫入前檢查／交易本身）
    ("k1_games:column_guard", {"STUB_EXTRA_COLUMN_TABLE": G}, 1, []),
    ("k1_games:transaction", {"STUB_PSQL_FAIL_TABLE": G}, 3, []),
    ("k2_schedule_rev:serial_sequence", {"STUB_SEQUENCE_MISSING_TABLE": SR}, 66, [G]),
    ("k2_schedule_rev:payload_assert", {"STUB_INJECT_SETVAL_TABLE": SR}, 67, [G]),
    ("k2_schedule_rev:seq_telemetry", {"TELEMETRY_FAIL_TABLE": SR}, 1, [G]),
    ("k2_schedule_rev:transaction", {"STUB_PSQL_FAIL_TABLE": SR}, 3, [G]),
    ("k3_source_rev:serial_sequence", {"STUB_SEQUENCE_MISSING_TABLE": SRC}, 66, [G, SR]),
    ("k3_source_rev:payload_assert", {"STUB_INJECT_SETVAL_TABLE": SRC}, 67, [G, SR]),
    ("k3_source_rev:seq_telemetry", {"TELEMETRY_FAIL_TABLE": SRC}, 1, [G, SR]),
    ("k3_source_rev:transaction", {"STUB_PSQL_FAIL_TABLE": SRC}, 3, [G, SR]),
    ("k4_signals:column_guard", {"STUB_EXTRA_COLUMN_TABLE": SIG}, 1, [G, SR, SRC]),
    ("k4_signals:transaction", {"STUB_PSQL_FAIL_TABLE": SIG}, 3, [G, SR, SRC]),
    # 類 3：提交後對帳
    ("post_commit:reconcile_mismatch", {"VERIFY_MISMATCH": "1"}, 68, [G, SR, SRC, SIG]),
]


@pytest.mark.parametrize("name,inject,code,committed", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_commit_boundary_matches_plan(tmp_path, name, inject, code, committed):
    rc, got, stderr = run_boundary(tmp_path, **inject)
    assert (rc, got) == (code, committed), f"{name}: rc={rc} committed={got}\n{stderr[-800:]}"


@pytest.mark.parametrize("code,expected", [(0, "synced"), (68, "blocked")]
                         + [(c, "halted") for c in (1, 3, 64, 65, 66, 67)])
def test_evening_chain_disposition_and_checkpoint_sync_code(code, expected):
    """同一組退出碼經晚間鏈入帳：68 只停當晚、其餘非零 halted；先發時點紀錄帶上該次 sync_code。"""
    tpe = ZoneInfo("Asia/Taipei")
    now = datetime(2026, 10, 17, 16, 36, tzinfo=tpe)
    state = pe.empty_state()
    rid = "2026-C-1|S-30|x"
    state["starter_checkpoints"] = {rid: {
        "key": "2026-C-1", "point": "S-30", "phase": "pregame", "done": True,
        "outcome": "changed", "sync_code": None,
        "attempts": [{"at": pe._iso(now), "outcome": "changed", "challenge": False,
                      "sync_code": None}]}}
    assert pe.record_sync(state, now, code) == expected
    sc.record_sync(state["starter_checkpoints"], [rid], code)
    assert state["starter_checkpoints"][rid]["sync_code"] == code
    assert bool(state.get("halted")) is (expected == "halted")
    assert bool(state.get("sync_blocked_at")) is (expected == "blocked")
