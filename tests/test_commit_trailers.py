"""執行分支的 commit 必須帶完整 trailer 集合（canonical AI_WORKFLOW §6）。

**為什麼是測試而不是人工檢查**：trailer 契約原本靠「執行者記得寫＋查核者記得驗」，
兩層在同一天的兩張卡上都失守——GAME-RECAP-WP-STRENGTH1 iteration 4（缺 Planned-by、
空行斷開 trailer 區塊）與 UX-PREGAME-SOURCE-GUARD1 iteration 1（派工範本漏 Planned-by，
Coordinator 還在 handoff 宣稱「已驗證完整」，實際只驗了「能被解析」）。每次都燒掉
一整輪查核來抓機器兩秒可查的事。

檢查範圍：**當前 HEAD 相對 origin/main 的新 commit**（執行分支模式）。在 main 上
（無新 commit）自動跳過——歷史 commit 不回溯補做。merge commit 另要求 Reviewed-by。

必要集合以 `git interpret-trailers --parse` 的輸出為準（不是 grep 字串）——iteration 4
的教訓正是「字串存在但空行使其不被解析為 trailer」。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = ("Requested-by", "Implemented-by", "Co-Authored-By")
# Planned-by 對 T2+ 實作 commit 為必要；docs/chore 類（含 control-plane 投影）豁免。
PLANNED_BY_EXEMPT_PREFIXES = ("chore(control-plane)", "docs(tasks)", "chore(tasks)")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True, check=True).stdout


def _new_commits() -> list[str]:
    """HEAD 相對 origin/main 的新 commit（在 main 或 origin/main 缺席時回空）。"""
    probe = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet",
                            "origin/main"], capture_output=True, text=True)
    if probe.returncode != 0:
        return []
    return [s for s in _git("rev-list", "origin/main..HEAD").split() if s]


def _parsed_trailers(sha: str) -> dict[str, str]:
    body = _git("log", "-1", "--format=%B", sha)
    parsed = subprocess.run(["git", "interpret-trailers", "--parse"],
                            input=body, capture_output=True, text=True, check=True).stdout
    out: dict[str, str] = {}
    for line in parsed.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip()
    return out


def test_new_commits_carry_the_required_trailer_set():
    commits = _new_commits()
    if not commits:
        pytest.skip("在 main 上或無新 commit——本守衛只驗執行分支的新 commit")
    problems: list[str] = []
    for sha in commits:
        subject = _git("log", "-1", "--format=%s", sha).strip()
        is_merge = len(_git("log", "-1", "--format=%P", sha).split()) > 1
        trailers = _parsed_trailers(sha)
        required: list[str] = list(REQUIRED)
        if is_merge:
            required.append("Reviewed-by")
        if not is_merge and not subject.startswith(PLANNED_BY_EXEMPT_PREFIXES):
            required.append("Planned-by")
        missing = [k for k in required if k not in trailers]
        if missing:
            problems.append(f"{sha[:7]} {subject[:50]} → 缺 {missing}"
                            f"（interpret-trailers 實際解析出：{sorted(trailers) or '無'}）")
    assert not problems, (
        "以下 commit 的 trailer 不完整（以 git interpret-trailers --parse 為準，"
        "字串存在但被空行斷開一樣算缺）：\n  " + "\n  ".join(problems))
