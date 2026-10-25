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
# #355 WP-S：box 有送的那次，同一支程序在 box／PA 之後、reconcile 之前送目標場來源觀測紀錄。
REV = "game_source_revisions"
REV_SOURCES_SQL = "source IN ('livelog','scoreboard')"
CORRECTIVE_SETVAL = ("SELECT setval(pg_get_serial_sequence('cpbl.game_source_revisions', 'id'), "
                     "GREATEST(COALESCE((SELECT max(id) FROM cpbl.game_source_revisions), 0), 1), "
                     "(SELECT count(*) FROM cpbl.game_source_revisions) > 0);")

_LOG = '''
import json, os, sys
from pathlib import Path
def log_call(kind, argv, stdin_text):
    out = Path(os.environ["STUB_LOG_DIR"]) / kind
    out.mkdir(parents=True, exist_ok=True)
    i = len(list(out.glob("*.json")))
    (out / ("%03d.json" % i)).write_text(json.dumps({"argv": argv, "stdin": stdin_text}), encoding="utf-8")
    # #355：跨 docker／ssh／uv 的全域呼叫次序（E1 驗「revision 在 box／PA 之後、reconcile 之前」）。
    with open(Path(os.environ["STUB_LOG_DIR"]) / "order.txt", "a", encoding="utf-8") as f:
        f.write("%s/%03d\\n" % (kind, i))
'''

# 假 docker：sync_table 的欄位守衛查詢回空（＝沒有漏欄）；COPY (SELECT …) TO STDOUT 回一列假資料。
_DOCKER = _LOG + '''
argv = sys.argv[1:]
stdin = sys.stdin.read() if "-i" in argv else ""
log_call("docker", argv, stdin)
# #355 E2：來源觀測紀錄的本機讀取改交給真 PostgreSQL（拋棄式 database；預設不設＝照舊回假列）。
real = os.environ.get("STUB_REV_REAL_PSQL")
if real and "FROM cpbl.game_source_revisions " in stdin:
    import subprocess
    proc = subprocess.run(json.loads(real), input=stdin, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    raise SystemExit(proc.returncode)
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
rc = os.environ.get("STUB_REV_SSH_RC")
if rc and "INSERT INTO cpbl.game_source_revisions" in stdin:
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
    assert inserts == [*BOX_TABLES, *PA_TABLES, REV], inserts   # #355：box 有送 → 末尾帶來源觀測紀錄
    # box：本機讀取一律帶目標鍵條件、不 pg_dump 整表。
    reads = [c["stdin"] for c in calls("docker") if "COPY (SELECT" in c["stdin"]]
    assert len(reads) == len(BOX_TABLES) + len(PA_TABLES) + 1   # ＋1＝#355 目標場來源觀測紀錄
    # box／PA 各表讀取的目標鍵條件照舊逐字；#355 來源觀測紀錄那一筆另加來源條件（逐字斷言見 E1）。
    assert all(f"WHERE {TARGET_SQL}) TO STDOUT" in r for r in reads if f"FROM cpbl.{REV} " not in r), reads
    assert sum(f"FROM cpbl.{REV} WHERE {REV_SOURCES_SQL} AND {TARGET_SQL}) TO STDOUT" in r for r in reads) == 1
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
                      "game_features", "game_lineup_announcement_revisions", "pg_catalog.setval"):
        assert forbidden not in joined, forbidden
    # setval 守衛收窄（需求方核定 #355 issuecomment-6371878740 第 2 項）：原「BOXPA payload 一律無 setval」
    # 改為「只有 game_source_revisions 那一份 payload 可有，且恰一行、逐字等於矯正形式」；其他表仍零 setval。
    setvals = [(i, line) for i, c in enumerate(calls("ssh")) for line in c["stdin"].splitlines()
               if "setval" in line.lower()]
    assert [line for _, line in setvals] == [CORRECTIVE_SETVAL], setvals
    (i,) = [i for i, _ in setvals]
    assert f"INSERT INTO cpbl.{REV} " in calls("ssh")[i]["stdin"], "setval 只准出現在來源觀測紀錄那一份"
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
    for fn in ("sync_table", "_sync_table_scoped", "sync_box_tables", "sync_box_source_revisions",
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
    ("box", [*BOX_TABLES, REV]),          # #355：送 box 的那次帶目標場來源觀測紀錄
    ("pa", list(PA_TABLES)),               # 只送 PA：不送來源觀測紀錄
    ("box,pa", [*BOX_TABLES, *PA_TABLES, REV]),
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
            if "game_source_revisions" in sql:   # #355：兩邊都沒有來源觀測紀錄（相同）
                return []
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
    assert inserts == [*BOX_TABLES, *PA_TABLES, REV], inserts
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


# =========================================================================== #355 WP-S
# box／PA 上正式站的那一次同步，順帶送目標場的來源觀測紀錄（game_source_revisions：livelog、scoreboard），
# 讓 `/api/v1/games/{sno}/status` 的 play_by_play_availability 在該次同步結束時已是 available，
# 不再等 F+60 那輪結果同步（PLAN-1 方案 B、§5 E1／E3／E10）。

_ORDER_KEYS = ("A", "E", "C")


def _key_case(kind: str) -> tuple[str, str]:
    sno = {"A": 355, "E": 4, "C": 4}[kind]
    return f"2026-{kind}-{sno}", f"(year, kind_code, game_sno) IN ((2026,'{kind}',{sno}))"


def _order(tmp_path: Path) -> list[str]:
    p = tmp_path / "calls" / "order.txt"
    return p.read_text(encoding="utf-8").split() if p.exists() else []


@pytest.mark.parametrize("kind", _ORDER_KEYS)
@pytest.mark.parametrize("parts", ["box,pa", "box"])
def test_e1_box_sync_carries_target_source_revisions_before_reconcile(tmp_path, kind, parts):
    """E1：送 box 的那次（box,pa／box），同一支程序依序送 box 七表、（PA）、目標場 game_source_revisions，
    再 reconcile；本機讀取只取目標鍵 × livelog／scoreboard；恰一行矯正 setval、無原生 setval、無整表 pg_dump。
    A／E／C 三種場鍵同一條路徑（keys_sql 與賽別無關；A 能進 BOXPA 是 #366 的正規式）。"""
    key, key_sql = _key_case(kind)
    result, calls, _ = _run(tmp_path, POSTSEASON_BOXPA_GAMES=key, POSTSEASON_BOXPA_PARTS=parts,
                            STUB_KEYS_SQL=key_sql, STUB_PA_GAMES=key)
    assert result.returncode == 0, result.stdout + result.stderr
    ssh = calls("ssh")
    payloads = [c["stdin"] for c in ssh if c["stdin"]]
    inserts = [m for p in payloads for m in re.findall(r"^INSERT INTO cpbl\.(\w+)", p, re.M)]
    want = [*BOX_TABLES, *(PA_TABLES if "pa" in parts else ()), REV]
    assert inserts == want, inserts
    # 本機讀取：目標鍵 × 兩個來源，COPY (SELECT …) TO STDOUT（不 pg_dump 整表）。
    (rev_read,) = [c["stdin"] for c in calls("docker") if f"FROM cpbl.{REV} " in c["stdin"]]
    assert f"COPY (SELECT * FROM cpbl.{REV} WHERE {REV_SOURCES_SQL} AND {key_sql}) TO STDOUT;" in rev_read
    assert not any("pg_dump" in c["argv"] for c in calls("docker"))
    # payload：恰一個 COPY 段、恰一行矯正 setval（在 COPY 結束之後、INSERT 之前）、無原生 setval、無 DELETE。
    (i_rev,) = [i for i, c in enumerate(ssh) if f"INSERT INTO cpbl.{REV} " in c["stdin"]]
    rev = ssh[i_rev]["stdin"].splitlines()
    assert sum(line.startswith("COPY ") for line in rev) == 1
    setvals = [n for n, line in enumerate(rev) if "setval" in line.lower()]
    assert len(setvals) == 1 and rev[setvals[0]] == CORRECTIVE_SETVAL
    copy_end = max(n for n, line in enumerate(rev) if line == "\\.")
    insert = next(n for n, line in enumerate(rev) if line.startswith(f"INSERT INTO cpbl.{REV} "))
    assert copy_end < setvals[0] < insert
    joined = "\n".join(rev)
    assert "pg_catalog.setval" not in joined and "CASCADE" not in joined
    assert not re.search(r"^(DELETE|TRUNCATE|DROP|ALTER)\b", joined, re.M | re.I)
    # 不搬 id：INSERT 只選顯式欄（不含 id），內容唯一鍵衝突時整欄鏡像。
    assert rev[insert].startswith(f"INSERT INTO cpbl.{REV} (year,kind_code,game_sno,source,source_version,")
    assert " id," not in rev[insert] and "(id" not in rev[insert]
    assert "ON CONFLICT (year,kind_code,game_sno,source,source_version) DO UPDATE SET" in rev[insert]
    # 次序：revision 那一次 ssh 在 box／PA 的所有 ssh 之後，且在 reconcile 之前。
    order = _order(tmp_path)
    ssh_ids = [x for x in order if x.startswith("ssh/")]
    rev_id = f"ssh/{i_rev:03d}"
    assert ssh_ids[-1] == rev_id, "來源觀測紀錄是本次最後一筆 production 寫入"
    rec_ids = [f"uv/{n:03d}" for n, c in enumerate(calls("uv")) if "reconcile" in c["argv"]]
    assert len(rec_ids) == 1 and order.index(rev_id) < order.index(rec_ids[0])


@pytest.mark.parametrize("kind", _ORDER_KEYS)
def test_e1_pa_only_sync_does_not_send_source_revisions(tmp_path, kind):
    """E1：只送 PA 的那次不送來源觀測紀錄（box 未在本次送達，不得先宣稱來源已到）。"""
    key, key_sql = _key_case(kind)
    result, calls, _ = _run(tmp_path, POSTSEASON_BOXPA_GAMES=key, POSTSEASON_BOXPA_PARTS="pa",
                            STUB_KEYS_SQL=key_sql, STUB_PA_GAMES=key)
    assert result.returncode == 0, result.stderr
    assert not any(REV in c["stdin"] for c in calls("ssh"))
    assert not any(REV in c["stdin"] for c in calls("docker"))


@pytest.mark.parametrize(("rc", "exit_code"), [("255", 72), ("3", 74)])
def test_e1_source_revision_failure_codes_and_partial_commit_window(tmp_path, rc, exit_code):
    """revision 那步 ssh 連線失敗 → 72（晚間鏈可重送一次）；production psql 錯誤 → 74（halted）。
    F1（審核 6371825157）殘餘風險：box／PA 已在前面各自提交，revision 失敗不撤回它們——這次程序結束時
    仍是「box 已到、紀錄未到」的窗口；不進 reconcile、不寫 manifest，由既有重送／停止語意處理（E4）。"""
    result, calls, _ = _run(tmp_path, STUB_REV_SSH_RC=rc)
    assert result.returncode == exit_code, result.stdout + result.stderr
    sent = [m for c in calls("ssh") for m in re.findall(r"^INSERT INTO cpbl\.(\w+)", c["stdin"], re.M)]
    assert sent == [*BOX_TABLES, *PA_TABLES, REV], "box／PA 已送出（部分提交），revision 那份已嘗試"
    assert not any("reconcile" in c["argv"] for c in calls("uv")), "revision 未送達就不 reconcile"
    assert not (tmp_path / "manifest.json").exists()


def test_e1_source_revision_column_list_matches_the_results_chain():
    """同源：BOXPA 段送 game_source_revisions 的欄位清單與 sync_postseason_results 逐字相同（各寫一份會漂）。"""
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"sync_revision_table game_source_revisions \\\n\s*\"([^\"]+)\" \\\n((?:[^\n]*\\\n)*[^\n]*)\n", text)
    assert m, "sync_postseason_results 的 game_source_revisions 清單"
    results_pk, results_cols = m.group(1), m.group(2).replace("\\", " ").split()
    body = re.search(r"^sync_box_source_revisions\(\) \{[^\n]*\n(.*?)^\}", text, re.S | re.M)
    assert body, "sync_box_source_revisions"
    pk = re.search(r'local pk="([^"]+)"', body.group(1)).group(1)
    cols = re.search(r'local cols="([^"]+)"', body.group(1)).group(1).split(",")
    assert pk == results_pk and cols == results_cols


# ------------------------------------------------------------------ E3：reconcile 加查來源觀測紀錄

class _RevDb:
    """reconcile 的假 Psql：box／PA 列數一律相同；來源觀測紀錄當前列由 ``revs`` 決定。"""

    def __init__(self, revs):
        self.revs = revs
        self.sql: list[str] = []

    def read(self, sql):
        from cpbl.ingest import boxpa_sync as bs
        self.sql.append(sql)
        if "build_id::text" in sql:
            return [["2026-C-4", "b1"]]
        if "game_source_revisions" in sql:
            return [["2026-C-4", s, *v] for s, v in self.revs.items()]
        return [[t, "2026-C-4", "5"] for t in (*bs.BOX_TABLES, *bs.PA_TABLES)]


_LIVE = ("v-live-3", "available", "1792911762.123456")
_SB = ("v-sb-2", "available", "1792911760.5")


@pytest.mark.parametrize(("prod_revs", "expect"), [
    ({"livelog": _LIVE, "scoreboard": _SB}, True),                 # 相同 → box_ok True
    ({"scoreboard": _SB}, False),                                   # prod 缺 livelog（G4 窗口形狀）
    ({}, False),                                                    # prod 兩個來源都沒有
    ({"livelog": ("v-live-2", *_LIVE[1:]), "scoreboard": _SB}, False),   # 版本不同
    ({"livelog": (_LIVE[0], "missing", _LIVE[2]), "scoreboard": _SB}, False),  # outcome 不同
    ({"livelog": (*_LIVE[:2], "1792911700.0"), "scoreboard": _SB}, False),     # last_seen_at 不同
])
def test_e3_reconcile_box_ok_requires_target_source_revisions_to_match(prod_revs, expect):
    from cpbl.ingest import boxpa_sync as bs

    keys = bs.parse_games("2026-C-4")
    local = _RevDb({"livelog": _LIVE, "scoreboard": _SB})
    m = bs.reconcile(local, _RevDb(prod_revs), keys, ["2026-C-4"], ["box", "pa"])
    g = m["games"]["2026-C-4"]
    assert g["box_ok"] is expect and m["ok"] is expect
    assert g["pa_ok"] is True, "來源觀測紀錄只併進 box 的對帳結果，不影響 PA"
    assert set(g["box_revisions"]) == {"livelog", "scoreboard"}
    q = next(s for s in local.sql if "game_source_revisions" in s)
    assert "source IN ('livelog','scoreboard')" in q and bs.keys_sql(keys) in q


def test_e3_reconcile_does_not_judge_source_revisions_when_box_not_sent():
    from cpbl.ingest import boxpa_sync as bs

    keys = bs.parse_games("2026-C-4")
    local, prod = _RevDb({"livelog": _LIVE}), _RevDb({})
    m = bs.reconcile(local, prod, keys, ["2026-C-4"], ["pa"])
    g = m["games"]["2026-C-4"]
    assert g["box_ok"] is None and m["ok"] is True, "沒送 box：來源觀測紀錄不判（也不查）"
    assert not any("game_source_revisions" in s for s in local.sql + prod.sql)
