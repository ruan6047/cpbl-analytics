"""`refresh-cpbl-prod.sh` 的 remote_train：trainer 失敗碼必須傳遞回本機。

為什麼要測：ssh 回傳的是**遠端命令串最後一個指令**的 exit code。遠端登入 shell 通常沒有
pipefail，所以 `docker exec ... | grep -v httpx | tail -N` 永遠回 tail 的 0——trainer
crash 會被當成功，refresh 繼續往下寫成功標記，留下「舊 artifact 消費新特徵分布」的錯配
（ML-OUTCOME-SIMPLE-LEAK2 紅線 5）。

測法：把腳本裡的 `remote_train` 函式**原樣抽出來**跑（不複製實作），並以 `/bin/sh -c` 假
ssh 模擬「遠端是 POSIX sh、沒有 pipefail」——即產生原始缺陷的那個環境。
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "refresh-cpbl-prod.sh"


def _remote_train_definition() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^remote_train\(\) \{.*?^\}", text, re.S | re.M)
    assert match, "refresh-cpbl-prod.sh 找不到 remote_train 函式定義"
    return match.group(0)


def _run(tmp_path: Path, remote_command: str) -> subprocess.CompletedProcess[str]:
    """以假 ssh 執行抽出的 remote_train。假 ssh 把第 4 個參數當遠端命令串交給 /bin/sh。"""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    ssh = fake_bin / "ssh"
    ssh.write_text('#!/bin/sh\nexec /bin/sh -c "$4"\n', encoding="utf-8")
    ssh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    script = (
        'VPS="fake-host"\n'
        f"{_remote_train_definition()}\n"
        f"remote_train {remote_command!r} 7\n"
    )
    return subprocess.run(
        ["/bin/bash", "-c", script], env=env, text=True, capture_output=True, check=False,
    )


def test_trainer_failure_code_reaches_the_local_script(tmp_path: Path) -> None:
    """trainer 非零離開 ⇒ remote_train 非零；否則 set -e 不會中止、成功標記照寫。"""
    result = _run(tmp_path, "sh -c 'echo 進行中; echo 爆了 >&2; exit 42'")

    assert result.returncode == 42


def test_trainer_success_survives_grep_filtering_out_every_line(tmp_path: Path) -> None:
    """全部輸出都被 grep -v httpx 濾掉時 grep 回 1；不得因此把成功的訓練判成失敗。

    這是「直接加 set -o pipefail」會踩到的假失敗，故意留一條測試釘住。
    """
    result = _run(tmp_path, "sh -c 'echo httpx: GET /x; echo httpx: GET /y; exit 0'")

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_output_is_still_filtered_and_tailed(tmp_path: Path) -> None:
    result = _run(tmp_path, "sh -c 'echo httpx: noise; echo gate=PASS; exit 0'")

    assert result.returncode == 0
    assert "gate=PASS" in result.stdout
    assert "httpx" not in result.stdout
