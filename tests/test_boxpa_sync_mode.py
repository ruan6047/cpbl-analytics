"""#293 S12 WP2：`refresh-cpbl-prod.sh` 的 POSTSEASON_BOXPA_ONLY 模式（季後目標場 box／PA scoped 同步）。

跑**真腳本**（symlink 到假 repo）＋假 `ssh`／`docker`／`uv`／`python3`／備份腳本，`VPS` 指向
`.invalid`、`LOCAL_DB` 不存在——零 DB、零網路（沿用 `tests/test_prod_sync_revision_seq.py` 的手法）。
`uv run python -m cpbl.ingest.boxpa_sync pa-payload` 交給**真模組**跑（本機 psql 由假 docker 回應），
所以 PA payload 的形狀是真產生器的輸出；precheck／reconcile 由假 uv 依情境回固定結果。

證明的是：
* 只送目標場鍵：box 七表的本機讀取一律帶目標鍵條件、PA payload 只 DELETE 目標鍵；
* ⛔ 無 TRUNCATE／CASCADE、⛔ 不呼叫 `prod_cpbl_api`（不 migrate、不訓練）、⛔ 不寫 refresh 標記；
* box 七表的欄位清單與完整鏈（WITH_DETAIL）**同源**：SET 子句逐字相同、清單在檔內只寫一次；
* 參數守衛、production 未完賽時不備份不寫、ssh 連線失敗回 72、production psql 錯誤回 74。

`prod_cpbl_api` 守衛的變異證明（需求方裁定 6183934991）見
`test_boxpa_mode_never_calls_prod_cpbl_api` 的 docstring；變異只在執行工作樹暫時進行、不提交。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh-cpbl-prod.sh"
BOX_TABLES = ("game_detail", "game_scoreboard", "game_livelog", "pitch_tracking",
              "pitching_game_flags", "batting_gamelog", "pitching_gamelog")
PA_TABLES = ("game_recap_source_revisions", "game_recap_builds", "game_plate_appearances",
             "game_pa_events", "game_pa_pitch_mappings")
TARGET = "2026-C-2"
TARGET_SQL = "(year, kind_code, game_sno) IN ((2026,'C',2))"

_LOG = '''
import json, os, sys
from pathlib import Path
def log_call(kind, argv, stdin_text):
    out = Path(os.environ["STUB_LOG_DIR"]) / kind
    out.mkdir(parents=True, exist_ok=True)
    i = len(list(out.glob("*.json")))
    (out / ("%03d.json" % i)).write_text(json.dumps({"argv": argv, "stdin": stdin_text}), encoding="utf-8")
'''

# 假 docker：sync_table 的欄位守衛查詢回空（＝沒有漏欄）；COPY (SELECT …) TO STDOUT 回一列假資料。
_DOCKER = _LOG + '''
argv = sys.argv[1:]
stdin = sys.stdin.read() if "-i" in argv else ""
log_call("docker", argv, stdin)
if "COPY (SELECT * FROM cpbl." in stdin:
    sys.stdout.write("2026\\tC\\t2\\tstub\\n")
'''

# 假 ssh：記錄後依情境結束碼（PA payload 那一次可指定失敗碼）。
_SSH = _LOG + '''
argv = sys.argv[1:]
stdin = sys.stdin.read()
log_call("ssh", argv, stdin)
rc = os.environ.get("STUB_PA_SSH_RC")
if rc and "DELETE FROM cpbl.game_pa_pitch_mappings" in stdin:
    raise SystemExit(int(rc))
'''

# 假 uv：boxpa_sync pa-payload 交給真模組；precheck／reconcile 依情境回固定輸出。
_UV = _LOG + '''
import subprocess
argv = sys.argv[1:]
log_call("uv", argv, "")
if "cpbl.ingest.boxpa_sync" in argv:
    cmd = argv[argv.index("cpbl.ingest.boxpa_sync") + 1]
    if cmd == "pa-payload":
        env = {**os.environ, "PYTHONPATH": os.environ["STUB_SRC"]}
        raise SystemExit(subprocess.run([os.environ["STUB_PY"], "-m", "cpbl.ingest.boxpa_sync",
                                         *argv[argv.index("cpbl.ingest.boxpa_sync") + 1:]], env=env).returncode)
    if cmd == "precheck":
        rc = int(os.environ.get("STUB_PRECHECK_RC", "0"))
        if rc:
            print("✗ stub precheck", file=sys.stderr)
            raise SystemExit(rc)
        print("BOXPA_KEYS_SQL=" + os.environ["STUB_KEYS_SQL"])
        print("BOXPA_PA_GAMES=" + os.environ.get("STUB_PA_GAMES", "2026-C-2"))
        raise SystemExit(0)
    if cmd == "reconcile":
        out = argv[argv.index("--out") + 1]
        Path(out).write_text(json.dumps({"ok": True, "stub": True}), encoding="utf-8")
        raise SystemExit(int(os.environ.get("STUB_RECONCILE_RC", "0")))
print("stub uv " + " ".join(argv))
'''


def _write_exec(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run(tmp_path: Path, script: Path = SCRIPT, **env_overrides):
    fake_bin, repo, logdir = tmp_path / "bin", tmp_path / "repo", tmp_path / "calls"
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    _write_exec(fake_bin / "docker", f"#!{sys.executable}\n{_DOCKER}")
    _write_exec(fake_bin / "ssh", f"#!{sys.executable}\n{_SSH}")
    _write_exec(fake_bin / "uv", f"#!{sys.executable}\n{_UV}")
    backup_log = tmp_path / "backup-env.txt"
    _write_exec(repo / "scripts" / "backup-prod-db.sh",
                f"#!/bin/sh\nprintf 'BACKUP_DIR=%s\\nBACKUP_KEEP=%s\\n' \"$BACKUP_DIR\" \"$BACKUP_KEEP\" > {backup_log}\n"
                "echo /fixture/boxpa-backup.sql.gz\n")
    os.symlink(script, repo / "scripts" / SCRIPT.name)
    (tmp_path / "tmp").mkdir(exist_ok=True)
    env = {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"),
        "STUB_LOG_DIR": str(logdir),
        "STUB_SRC": str(ROOT / "src"),
        "STUB_PY": sys.executable,
        "STUB_KEYS_SQL": TARGET_SQL,
        "VPS": "stub@harness.invalid",
        "LOCAL_DB": "stub-nonexistent-container",
        "DEPLOY_PATH": "/nonexistent/stub-deploy",
        "API_INFO_URL": "http://127.0.0.1:1/api/info",
        "POSTSEASON_BOXPA_ONLY": "1",
        "SKIP_SCRAPE": "1",
        "POSTSEASON_BOXPA_GAMES": TARGET,
        "BACKUP_DIR": str(tmp_path / "boxpa-backups"),
        "BOXPA_MANIFEST": str(tmp_path / "manifest.json"),
        **env_overrides,
    }
    env = {k: v for k, v in env.items() if v is not None}
    result = subprocess.run(["/bin/bash", str(repo / "scripts" / SCRIPT.name)], env=env, text=True,
                            capture_output=True, stdin=subprocess.DEVNULL, check=False)

    def calls(kind: str) -> list[dict]:
        d = logdir / kind
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d.is_dir() else []

    return result, calls, backup_log


@pytest.fixture(scope="module")
def boxpa_run(tmp_path_factory):
    result, calls, backup_log = _run(tmp_path_factory.mktemp("boxpa"))
    assert result.returncode == 0, result.stdout + result.stderr
    return result, calls, backup_log


def test_boxpa_mode_sends_only_target_keys_box_upserts_and_one_pa_replacement(boxpa_run):
    result, calls, backup_log = boxpa_run
    payloads = [c["stdin"] for c in calls("ssh") if c["stdin"]]
    inserts = [m for p in payloads for m in re.findall(r"^INSERT INTO cpbl\.(\w+)", p, re.M)]
    assert inserts == [*BOX_TABLES, *PA_TABLES], inserts
    # box：本機讀取一律帶目標鍵條件、不 pg_dump 整表。
    reads = [c["stdin"] for c in calls("docker") if "COPY (SELECT" in c["stdin"]]
    assert len(reads) == len(BOX_TABLES) + len(PA_TABLES)
    assert all(f"WHERE {TARGET_SQL}) TO STDOUT" in r for r in reads), reads
    assert not any("pg_dump" in c["argv"] for c in calls("docker")), "目標場模式不得整表 pg_dump"
    # PA：恰一份 payload，只 DELETE 目標鍵，子→父。
    (pa,) = [p for p in payloads if "DELETE FROM" in p]
    deletes = re.findall(r"^DELETE FROM cpbl\.(\w+) WHERE (.*);$", pa, re.M)
    assert [t for t, _ in deletes] == list(reversed(PA_TABLES))
    assert {w for _, w in deletes} == {TARGET_SQL}
    for p in payloads:
        if p is not pa:
            assert "DELETE" not in p, "box 只 upsert、不 DELETE（同每日鏈語意）"
    # 備份走獨立目錄，在任何寫入之前。
    assert f"BACKUP_DIR={backup_log.parent / 'boxpa-backups'}" in backup_log.read_text()
    assert "季後目標場 box／PA：完成" in result.stdout


def test_boxpa_mode_has_no_truncate_cascade_migrate_train_or_refresh_marker(boxpa_run):
    result, calls, _ = boxpa_run
    joined = "\n".join(c["stdin"] + " ".join(c["argv"]) for c in calls("ssh"))
    for forbidden in ("TRUNCATE", "CASCADE", "db.migrate", "cpbl-train", "refresh_log",
                      "game_features", "game_lineup_announcement_revisions", "setval"):
        assert forbidden not in joined, forbidden
    assert "cpbl-build-features" not in result.stdout and "cpbl-train" not in result.stdout
    assert "寫入 production refresh 成功標記" not in result.stdout


def test_boxpa_mode_never_calls_prod_cpbl_api(boxpa_run):
    """§9.1「不需 bump／Deploy」的前提：新模式⛔ 不在 production 容器執行任何 repo 碼。

    兩層：(1) 執行期——每一次 ssh 的 argv 與 stdin 都不含 ``prod_cpbl_api``；(2) 靜態——
    POSTSEASON_BOXPA_ONLY 段與它呼叫的函式本文不含 ``prod_cpbl_api``／``docker exec prod_cpbl``。

    變異證明（需求方裁定 6183934991；不提交）：在 POSTSEASON_BOXPA_ONLY 段的 ``sync_box_tables``
    前暫時塞一行 ``ssh -o BatchMode=yes "$VPS" 'docker exec prod_cpbl_api python -c "print(1)"'``，
    本測試必須變紅；紅／綠輸出原文存於 ``~/.wf-evidence/cpbl-analytics/293/exec-1/``。
    """
    _, calls, _ = boxpa_run
    for c in calls("ssh"):
        assert "prod_cpbl_api" not in " ".join(c["argv"]) + c["stdin"], c["argv"]
    body = _boxpa_mode_text()
    assert "prod_cpbl_api" not in body
    assert "prod_cpbl" not in body.replace("prod_pg", "")


def _boxpa_mode_text() -> str:
    """POSTSEASON_BOXPA_ONLY 早退段＋它呼叫的同步函式本文（靜態守衛用）。"""
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index('if [ -n "${POSTSEASON_BOXPA_ONLY:-}" ]; then\n  if [ -z "${POSTSEASON_BOXPA_GAMES')
    end = text.index("\nfi\n", start)
    parts = [text[start:end]]
    for fn in ("sync_table", "_sync_table_scoped", "sync_box_tables",
               *(f"sync_box_{t}" for t in BOX_TABLES)):
        m = re.search(rf"^{fn}\(\) {{[^\n]*\n(.*?)^}}", text, re.S | re.M)
        assert m, fn
        parts.append(m.group(1))
    return "\n".join(parts)


def test_box_column_lists_are_shared_with_the_full_chain(boxpa_run, tmp_path):
    """欄位清單同源：每張 box 表的 sync_table 清單在檔內只寫一次，且目標場模式與完整鏈（WITH_DETAIL）
    送出的 ON CONFLICT … SET 子句逐字相同。"""
    text = SCRIPT.read_text(encoding="utf-8")
    for t in BOX_TABLES:
        assert len(re.findall(rf"^\s*sync_table {t} ", text, re.M)) == 1, t
    _, scoped_calls, _ = boxpa_run

    from tests.test_prod_sync_revision_seq import _run_refresh
    full, full_calls = _run_refresh(tmp_path / "full")
    assert full.returncode == 0, full.stderr

    def set_clauses(payloads: list[str]) -> dict[str, str]:
        out = {}
        for p in payloads:
            for t, rest in re.findall(r"^INSERT INTO cpbl\.(\w+) AS tgt SELECT \* FROM _stg (ON CONFLICT .*)$", p, re.M):
                out[t] = rest
        return out

    scoped = set_clauses([c["stdin"] for c in scoped_calls("ssh")])
    whole = set_clauses([c["stdin"] for c in full_calls])
    for t in BOX_TABLES:
        assert scoped[t] == whole[t], t


@pytest.mark.parametrize("env", [
    {"SKIP_SCRAPE": None},
    {"WITH_DETAIL": "1"},
    {"POSTSEASON_RESULTS_ONLY": "1"},
    {"ROSTER_ONLY": "1"},
    {"LINEUP_ONLY": "1"},
    {"TEAM_COMPARISON_ONLY": "1"},
    {"POSTSEASON_BOXPA_ONLY": "yes"},
    {"POSTSEASON_BOXPA_GAMES": None},
    {"POSTSEASON_BOXPA_GAMES": "2026-D-2"},   # #365：A 已是晚間賽別；D 仍拒（負控）
    {"POSTSEASON_BOXPA_GAMES": "2026-C-2;DROP"},
    {"BOXPA_MANIFEST": None},
    {"BOXPA_MANIFEST": "relative/manifest.json"},
    {"BACKUP_DIR": None},
    {"BACKUP_DIR": "relative/dir"},
    {"BACKUP_DIR": "{HOME}/Library/Application Support/cpbl-analytics/backups/"},
])
def test_boxpa_mode_refuses_bad_parameters_without_touching_anything(tmp_path, env):
    env = {k: (v.replace("{HOME}", str(tmp_path / "home")) if v else v) for k, v in env.items()}
    if (env.get("BACKUP_DIR") or "").endswith("backups/"):
        Path(env["BACKUP_DIR"]).mkdir(parents=True)
    result, calls, backup_log = _run(tmp_path, **env)
    assert result.returncode == 64, (env, result.stdout, result.stderr)
    assert calls("ssh") == [] and not backup_log.exists()


def test_not_final_in_prod_stops_before_backup_and_writes(tmp_path):
    result, calls, backup_log = _run(tmp_path, STUB_PRECHECK_RC="73")
    assert result.returncode == 73
    assert calls("ssh") == [] and not backup_log.exists()


def test_ssh_connection_failure_on_pa_is_72_and_other_psql_errors_are_74(tmp_path):
    r255, _, _ = _run(tmp_path / "a", STUB_PA_SSH_RC="255")
    assert r255.returncode == 72, r255.stderr
    r3, _, _ = _run(tmp_path / "b", STUB_PA_SSH_RC="3")
    assert r3.returncode == 74, r3.stderr


def test_no_local_published_build_leaves_prod_pa_untouched(tmp_path):
    result, calls, _ = _run(tmp_path, STUB_PA_GAMES="")
    assert result.returncode == 0, result.stderr
    joined = "\n".join(c["stdin"] for c in calls("ssh"))
    assert "DELETE" not in joined and "game_recap_builds" not in joined
    assert "本次沒有可送的場" in result.stdout


def test_reconcile_mismatch_exits_68(tmp_path):
    result, _, _ = _run(tmp_path, STUB_RECONCILE_RC="68")
    assert result.returncode == 68


@pytest.mark.parametrize(("parts", "expected"), [
    ("box", list(BOX_TABLES)),
    ("pa", list(PA_TABLES)),
    ("box,pa", [*BOX_TABLES, *PA_TABLES]),
])
def test_parts_limit_what_is_actually_sent(tmp_path, parts, expected):
    """#293 審核席 1 F3：scoped 模式只送 POSTSEASON_BOXPA_PARTS 指定的來源——額度用完的來源不隨整組再送。"""
    result, calls, _ = _run(tmp_path, POSTSEASON_BOXPA_PARTS=parts)
    assert result.returncode == 0, result.stderr
    payloads = [c["stdin"] for c in calls("ssh") if c["stdin"]]
    inserts = [m for p in payloads for m in re.findall(r"^INSERT INTO cpbl\.(\w+)", p, re.M)]
    assert inserts == expected
    reconcile = [c["argv"] for c in calls("uv") if "reconcile" in c["argv"]]
    assert reconcile and reconcile[0][reconcile[0].index("--parts") + 1] == parts


@pytest.mark.parametrize("bad", ["", "pa,box", "box;pa", "all"])
def test_parts_must_be_box_pa_or_both(tmp_path, bad):
    result, calls, backup_log = _run(tmp_path, POSTSEASON_BOXPA_PARTS=bad)
    if bad == "":
        assert result.returncode == 0, "空值＝預設 box,pa"
        return
    assert result.returncode == 64 and calls("ssh") == [] and not backup_log.exists()


def test_reconcile_judges_only_the_parts_sent():
    from cpbl.ingest import boxpa_sync as bs

    class Db:
        def __init__(self, box_rows):
            self.box_rows = box_rows

        def read(self, sql):
            if "build_id::text" in sql:
                return [["2026-C-2", "b1"]]
            rows = []
            for t in (*bs.BOX_TABLES, *bs.PA_TABLES):
                rows.append([t, "2026-C-2", str(self.box_rows if t in bs.BOX_TABLES else 5)])
            return rows

    keys = bs.parse_games("2026-C-2")
    m = bs.reconcile(Db(10), Db(9), keys, ["2026-C-2"], ["pa"])
    g = m["games"]["2026-C-2"]
    assert g["box_ok"] is None and g["pa_ok"] is True and m["ok"] is True, "沒送 box：box 不等不判 68"
    m2 = bs.reconcile(Db(10), Db(9), keys, ["2026-C-2"], ["box", "pa"])
    assert m2["games"]["2026-C-2"]["box_ok"] is False and m2["ok"] is False


def test_o5_external_scope_variable_cannot_shrink_the_full_chain(tmp_path):
    """#293 審核席 2 O5（需求方裁定 6195565578 追加證據）：外部環境帶入 SYNC_SCOPE_KEYS_SQL 跑整鏈
    （SKIP_SCRAPE=1 WITH_DETAIL=1，同 scrape-daily.sh），box 七表仍必須整表 pg_dump、不得變成目標鍵 COPY。"""
    from tests.test_prod_sync_revision_seq import _run_refresh

    result, ssh_calls = _run_refresh(tmp_path, SYNC_SCOPE_KEYS_SQL=TARGET_SQL)
    assert result.returncode == 0, result.stderr
    docker = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((tmp_path / "calls" / "docker").glob("*.json"))]
    dumped = {c["argv"][c["argv"].index("-t") + 1] for c in docker if "pg_dump" in c["argv"]}
    for t in BOX_TABLES:
        assert f"cpbl.{t}" in dumped, f"{t} 必須整表 pg_dump"
    assert "（目標場）" not in result.stdout
    payloads = [c["stdin"] for c in ssh_calls]
    # #353 WP1：整鏈 PA 改逐場增量（鍵由簽章比對產生），外部 SYNC_SCOPE_KEYS_SQL 同樣不得滲入；
    # 且不論哪條路徑都不再 TRUNCATE PA 五表。
    assert not any("TRUNCATE cpbl.game_recap" in p for p in payloads)
    uv = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((tmp_path / "calls" / "uv").glob("*.json"))] \
        if (tmp_path / "calls" / "uv").is_dir() else []
    assert not any(TARGET_SQL in " ".join(c["argv"]) for c in uv)
    assert "PA 同步開始" in result.stdout, "整鏈仍須執行 sync_pa_build"


def test_a_game_key_is_accepted_and_defaults_to_box_and_pa(tmp_path):
    """#365 (d)：晚間鏈涵蓋一軍 A——``POSTSEASON_BOXPA_GAMES=2026-A-355``（2026-09-27 真實場）不回 64，
    未給 ``POSTSEASON_BOXPA_PARTS`` 時預設 box,pa：box 七表與 PA 五表同一次送（與 E／C 同一送達單位）。
    D 的負控見 ``test_boxpa_mode_refuses_bad_parameters_without_touching_anything``（``2026-D-2`` 仍回 64）。"""
    from cpbl.ingest import boxpa_sync

    assert [(k.year, k.kind_code, k.game_sno) for k in boxpa_sync.parse_games("2026-A-355")] == [(2026, "A", 355)]
    with pytest.raises(boxpa_sync.SyncError):
        boxpa_sync.parse_games("2026-D-229")
    a_sql = "(year, kind_code, game_sno) IN ((2026,'A',355))"
    result, calls, backup_log = _run(tmp_path, POSTSEASON_BOXPA_GAMES="2026-A-355", POSTSEASON_BOXPA_PARTS=None,
                                     STUB_KEYS_SQL=a_sql, STUB_PA_GAMES="2026-A-355")
    assert result.returncode == 0, result.stdout + result.stderr
    payloads = [c["stdin"] for c in calls("ssh") if c["stdin"]]
    inserts = [m for p in payloads for m in re.findall(r"^INSERT INTO cpbl\.(\w+)", p, re.M)]
    assert inserts == [*BOX_TABLES, *PA_TABLES], inserts
    (pa,) = [p for p in payloads if "DELETE FROM" in p]
    assert {w for _, w in re.findall(r"^DELETE FROM cpbl\.(\w+) WHERE (.*);$", pa, re.M)} == {a_sql}
    precheck = [c["argv"] for c in calls("uv") if "precheck" in c["argv"]]
    assert precheck and "2026-A-355" in precheck[0]
    assert backup_log.exists()


def test_shell_refuses_a_d_key_before_any_python_step(tmp_path):
    """#365 (d) 負控（shell 層）：D 場鍵在 refresh-cpbl-prod.sh 的正規式就回 64，⛔ 不進任何 uv／Python 步驟。
    上一條參數表的 2026-D-2 即使 shell 放行，也會被 Python ``parse_games`` 擋成 64——那條測不出 shell 這一層。"""
    result, calls, backup_log = _run(tmp_path, POSTSEASON_BOXPA_GAMES="2026-D-229")
    assert result.returncode == 64
    assert "YYYY-A|E|C-SNO" in result.stderr
    assert calls("uv") == [] and calls("ssh") == [] and not backup_log.exists()
