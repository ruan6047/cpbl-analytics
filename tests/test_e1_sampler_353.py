"""#353 E1 取樣工具（``docs/research/ISSUE-353/e1_sampler.sh``）的停止程序：只對帶本工具標記的行程送訊號。

E0 實測過：修正前的版本以行程群組 kill（``kill -- -<pid>``）停止取樣，某一路提早結束後 pid 被 postgres
backend 重用（backend 自己 setsid、自成群組），TERM 打到 backend、postmaster 整個重啟。正式站上
prod_pg 的 backend 同樣看得到 host pid。這裡逐行釘住：

1. ⛔ 沒有任何行程群組訊號（``kill -- -…``、``kill -TERM -…``、``killpg``）、⛔ 沒有 pkill／killall。
2. 每一個 ``kill`` 都在**同一行**先比對本工具的標記（遠端 ``E1S_TAG=$tag`` 完全相等、本機命令列含
   ``E1S_TAG=${tag}``），且只送給單一 ``"$p"``／``"$pid"``。
3. start 記下的 pid 只用來報告 ``skip_stale``，不被當成 kill 的對象。
4. DB 端只 terminate ``application_name`` 等於本次 tag 的 session。

行為證據（容器上的負控：修正前版本重現誤殺；修正後同情境只記 skip_stale）在
``~/.wf-evidence/cpbl-analytics/353/exec-2/``；macOS 沒有 /proc，這裡不跑行為測試。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "docs" / "research" / "ISSUE-353" / "e1_sampler.sh"


def _code_lines() -> list[str]:
    return [ln for ln in TOOL.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]


def test_syntax_is_valid() -> None:
    subprocess.run(["bash", "-n", str(TOOL)], check=True)


def test_no_process_group_or_pattern_kill_anywhere() -> None:
    code = "\n".join(_code_lines())
    for pattern in (r"kill\s+(-\w+\s+)*--\s+-", r"kill\s+-(TERM|KILL|INT|HUP|9|15)\s+-", r"killpg",
                    r"\bpkill\b", r"\bkillall\b", r"kill\s+(-\w+\s+)*-\\?\$"):
        assert not re.search(pattern, code), pattern


def test_every_kill_is_guarded_by_the_tool_marker_on_the_same_line() -> None:
    kills = [ln for ln in _code_lines() if re.search(r"(?<![\w-])kill\s", ln)]
    assert len(kills) == 2, kills  # 遠端 /proc 掃描一處、本機 remote 行程一處
    remote, local = kills
    assert re.search(r'grep -qx "E1S_TAG=\$tag" && kill -TERM "\$p"', remote), remote
    assert re.search(r'grep -qF -- "E1S_TAG=\$\{tag\}" && kill -TERM "\$pid"', local), local


def test_recorded_pids_are_only_reported_never_signalled() -> None:
    stale = next(ln for ln in _code_lines() if "skip_stale" in ln)
    assert "kill" not in stale, "start 記下的 pid 只能用來報告"
    assert '|| echo "skip_stale=' in stale


def test_every_remote_stream_carries_the_marker() -> None:
    src = TOOL.read_text(encoding="utf-8")
    assert 'remote "E1S_TAG=${tag} E1S_STREAM=$1 sh -s"' in src
    assert src.count("\n  rstream ") == 4, "psi／vmstat／proc／pg 四路都經 rstream 起（都帶標記）"


def test_db_side_terminates_only_this_runs_application_name() -> None:
    lines = [ln for ln in _code_lines() if "pg_terminate_backend" in ln]
    assert len(lines) == 1
    assert "WHERE application_name = '${tag}'" in lines[0]
    assert "export PGAPPNAME=${tag}" in TOOL.read_text(encoding="utf-8")
