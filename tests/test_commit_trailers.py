"""執行分支的 commit 必須帶完整 trailer 集合（canonical AI_WORKFLOW §6）。

**為什麼是測試而不是人工檢查**：trailer 契約原本靠「執行者記得寫＋查核者記得驗」，
兩層在同一天的兩張卡上都失守——GAME-RECAP-WP-STRENGTH1 iteration 4（缺 Planned-by、
空行斷開 trailer 區塊）與 UX-PREGAME-SOURCE-GUARD1 iteration 1（派工範本漏 Planned-by，
Coordinator 還在 handoff 宣稱「已驗證完整」，實際只驗了「能被解析」）。每次都燒掉
一整輪查核來抓機器兩秒可查的事。

檢查範圍：**當前 HEAD 相對本地 `main` 分支的新 commit**（執行分支模式）。

為什麼是本地 `main` 而不是 `origin/main`（DEV-TRAILER-GUARD-SCOPE1，2026-07-29）：
舊版拿 `origin/main..HEAD` 當「這是執行分支自己的新 commit」的標記，但「不在
origin/main 裡」只在執行者的情境下才等於這件事——Coordinator 剛在本地 main 上
合併、還沒 push 時，那個 merge commit 同樣「不在 origin/main 裡」，於是同一個
commit 的判定會因為推沒推過而翻轉：未推時亮紅（守衛把它當成執行分支 commit
來驗），push 之後 `origin/main` 追上 → `origin/main..HEAD` 變空 → 自動跳過 →
轉綠。轉綠不是因為 trailer 補好了，是因為取樣範圍空了——一個會被 push 動作
消音的守衛，等於鼓勵用 push 讓它閉嘴。2026-07-28 這個翻轉在 ML-PITCHER-SCORELESS1
合併時實際發生（兩個 control-plane commit 缺 Requested-by／Implemented-by，
push 前被抓到、push 後就看不到了）。

改用本地 `main` 分支當邊界解決的正是這一點：`git push` 不會移動任何本地分支，
所以「HEAD 相對本地 main 的新 commit」這個問題，從 push 前到 push 後永遠是
同一個答案——判定不再依賴 ref 是否已經同步到 remote。CI 找不到本地 `main`
時的退回見 `_base_ref` docstring。

範圍決定——main 上的 Coordinator commit 不在這個守衛的範圍內：這不是圖方便的
權宜之計，是實測後的決定。曾考慮過反向擴大範圍（承認 main 上的 Coordinator
commit 本來就該受檢，見 958caf1、150770b 兩個乾淨的先例）；但把同一套 REQUIRED
往回套到這個守衛生效當天（c3042f3，2026-07-27 18:04）之後的 main 歷史實測，
200 個 commit 裡有 93 個（46.5%）缺至少一項必要 trailer——而且不是零星案例，
是 `chore(control-plane)`／`chore(workflow)`／`docs(research)` 這些 Coordinator
日常留痕前綴的常態（多數缺 Implemented-by 或 Co-Authored-By）。canonical §6 對
T0/T1 commit 本來就只要求 Requested-by＋Implemented-by（不含 Co-Authored-By），
和這個守衛現有的 REQUIRED 三件套本來就不是同一把尺；要把 main 收進來，得先有
一套「哪些前綴只要哪些欄位」的政策，那是另一個決定，不是這張 S 卡的範圍
（見 DEV-TRAILER-GUARD-SCOPE1 卡面 Log 的後續卡建議）。量測腳本：
`git rev-list c3042f3..<main tip>` 逐一跑 `_trailer_problems`，數字會隨 main
推進而變，要重驗請重新對當前 main tip 跑一次，不要照抄本檔寫的 93/200。

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


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=True).stdout


def _base_ref(root: Path) -> str | None:
    """判定「新 commit」的邊界 ref。永遠優先本地 `main`：`git push` 不會移動
    任何本地分支，所以以本地 main 為界不受推沒推過影響——這正是
    DEV-TRAILER-GUARD-SCOPE1 要修的「用 origin/main 當標記」問題本身。

    只有本地找不到 `main`（例如 CI 的 detached-HEAD checkout 只抓了 PR ref、
    沒建本地 main 分支）才退回 `origin/main`。這個退回不會重現同一個 bug：
    CI 只在「這次 checkout 本來就是已推/已是 PR」的狀態下才會跑，不存在
    「同一個 commit 在同一次 checkout 裡推前推後判定不同」的落差——落差只
    發生在本機/agent 持續修改同一個工作樹的互動 session，而那裡本地 main
    一定存在（worktree 共用同一份 refs）。兩個邊界 ref 都解析不出時（極簡
    clone、沒 main 也沒 origin/main）——回 None，呼叫端視為「無新 commit」
    並跳過；這是本守衛目前唯一殘留的靜默略過環境，DEV-TRAILER-GUARD-SCOPE1
    執行報告有記錄，不算意外。
    """
    for ref in ("main", "origin/main"):
        probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet", ref],
                               capture_output=True, text=True)
        if probe.returncode == 0:
            return ref
    return None


def _new_commits(root: Path = ROOT) -> list[str]:
    """HEAD 相對 `_base_ref(root)` 的新 commit（邊界 ref 都解析不出時回空）。"""
    base = _base_ref(root)
    if base is None:
        return []
    return [s for s in _git(root, "rev-list", f"{base}..HEAD").split() if s]


def _parsed_trailers(root: Path, sha: str) -> dict[str, str]:
    body = _git(root, "log", "-1", "--format=%B", sha)
    parsed = subprocess.run(["git", "interpret-trailers", "--parse"],
                            input=body, capture_output=True, text=True, check=True).stdout
    out: dict[str, str] = {}
    for line in parsed.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip()
    return out


def _trailer_problems(root: Path, commits: list[str]) -> list[str]:
    """對每個 commit 算缺了哪些必要 trailer；回傳可讀的問題描述清單（空清單＝全過）。

    抽成獨立函式讓正式檢查與變異檢驗共用同一套判定邏輯，避免兩邊各寫一份而
    漂移。
    """
    problems: list[str] = []
    for sha in commits:
        subject = _git(root, "log", "-1", "--format=%s", sha).strip()
        is_merge = len(_git(root, "log", "-1", "--format=%P", sha).split()) > 1
        trailers = _parsed_trailers(root, sha)
        required: list[str] = list(REQUIRED)
        if is_merge:
            required.append("Reviewed-by")
        if not is_merge and not subject.startswith(PLANNED_BY_EXEMPT_PREFIXES):
            required.append("Planned-by")
        missing = [k for k in required if k not in trailers]
        if missing:
            problems.append(f"{sha[:7]} {subject[:50]} → 缺 {missing}"
                            f"（interpret-trailers 實際解析出：{sorted(trailers) or '無'}）")
    return problems


def test_new_commits_carry_the_required_trailer_set():
    commits = _new_commits()
    if not commits:
        pytest.skip("HEAD 相對本地 main 無新 commit（或無法解析任何邊界 ref）——"
                    "本守衛只驗執行分支自己的新 commit；main 上的 Coordinator commit "
                    "不在範圍內，理由與量測方式見本檔 module docstring")
    problems = _trailer_problems(ROOT, commits)
    assert not problems, (
        "以下 commit 的 trailer 不完整（以 git interpret-trailers --parse 為準，"
        "字串存在但被空行斷開一樣算缺）：\n  " + "\n  ".join(problems))


# ---------------------------------------------------------------------------
# 變異檢驗（DEV-TRAILER-GUARD-SCOPE1 紅線2）：構造一個缺 trailer 的 commit，
# 證明新守衛在「推前」與「推後」都抓得到——判定不能因為 push 而翻轉。
# 用隔離的 tmp_path 造 (bare remote, working repo) pair，不碰真正的 repo。
# ---------------------------------------------------------------------------

def _init_repo_with_remote(tmp_path: Path) -> Path:
    """建一個有 origin 的 working repo，main 上先有一個乾淨（trailer 齊全）
    的初始 commit且已推到 remote——起點乾淨、無落差，才能單純觀察「新增一個
    缺 trailer 的 commit」在推前推後的判定變化。"""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test")
    _git(work, "remote", "add", "origin", str(remote))
    (work / "README.md").write_text("init\n")
    _git(work, "add", "README.md")
    _git(work, "commit", "-q", "-m",
         "chore(control-plane): seed\n\n"
         "Requested-by: test\nImplemented-by: test\nCo-Authored-By: test <t@example.com>\n")
    _git(work, "push", "-q", "origin", "main")
    return work


def test_mutation_missing_trailer_caught_before_and_after_push(tmp_path: Path):
    work = _init_repo_with_remote(tmp_path)

    # 模擬執行分支：main 之外開一個分支，該分支上新增一個缺 Planned-by 的
    # commit（subject 不落在 PLANNED_BY_EXEMPT_PREFIXES，所以 Planned-by 是
    # 必要項，故意留空）。
    _git(work, "checkout", "-q", "-b", "ai/executor/CARD")
    (work / "feature.py").write_text("x = 1\n")
    _git(work, "add", "feature.py")
    _git(work, "commit", "-q", "-m",
         "feat(models): add x\n\n"
         "Requested-by: test\nImplemented-by: test\nCo-Authored-By: test <t@example.com>\n")
    bad_sha = _git(work, "rev-parse", "HEAD").strip()

    # --- 推前 ---
    pre_commits = _new_commits(work)
    assert bad_sha in pre_commits, "推前：新 commit 應該落在守衛的取樣範圍內"
    pre_problems = _trailer_problems(work, pre_commits)
    assert any(bad_sha[:7] in p and "Planned-by" in p for p in pre_problems), \
        "推前：守衛應該抓到缺 Planned-by"

    # --- push 分支到 origin（origin 上出現這個 branch，但本地 main 沒動）---
    _git(work, "push", "-q", "-u", "origin", "ai/executor/CARD")

    # --- 推後 ---
    post_commits = _new_commits(work)
    assert bad_sha in post_commits, (
        "推後：分支已經推上 origin 了，但判定邊界是本地 main、不受 push 影響——"
        "同一個 commit 不能因為推了就從取樣範圍裡消失")
    post_problems = _trailer_problems(work, post_commits)
    assert any(bad_sha[:7] in p and "Planned-by" in p for p in post_problems), \
        "推後：守衛仍要抓到缺 Planned-by（這正是 DEV-TRAILER-GUARD-SCOPE1 要修的紅線）"

    # 推前推後判定完全一致：同一組 sha、同一組問題描述。
    assert pre_commits == post_commits
    assert pre_problems == post_problems


def test_main_scope_excludes_coordinator_commits_by_design(tmp_path: Path):
    """紅線3的另一半：main 上的 Coordinator commit 不進取樣範圍是明寫的設計
    決定，不是意外的靜默放行——這裡直接證明「即使該 commit 什麼 trailer 都
    沒有，只要它就是本地 main 本身（HEAD == main），_new_commits 回空」，並
    在 module docstring 記錄理由（46.5% 歷史誤鳴率）與量測方式。"""
    work = _init_repo_with_remote(tmp_path)
    (work / "note.md").write_text("x\n")
    _git(work, "add", "note.md")
    _git(work, "commit", "-q", "-m", "chore(control-plane): missing every trailer")
    assert _new_commits(work) == [], (
        "main 上的新 commit（HEAD == main）永遠不進取樣範圍——這是設計排除，"
        "不是漏掉；理由見本檔 module docstring 與 DEV-TRAILER-GUARD-SCOPE1 卡面 Log")
