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

GitHub `pull_request` checkout 的 synthetic merge commit 排除（DEV-TRAILER-GUARD-
PR-CHECKOUT1，2026-08-04）：GitHub Actions 的 `pull_request` 事件預設 checkout
`refs/pull/<N>/merge`——GitHub 自動產生的合併結果 commit（訊息固定格式
`Merge <sha> into <base>`），不是任何人手動建立、也不可能帶任何 trailer。這個
commit 就是該次 checkout 的 HEAD，必然落在 `_base_ref()..HEAD` 範圍內（CI 上
`_base_ref` 通常退回 `origin/main`：`pull_request` checkout 不會建立本地 `main`
分支，但這個 repo 的 `ci.yml` 用 `fetch-depth: 0` 讓 `origin/main` 這個
remote-tracking ref 存在），導致本測試在**任何** pull_request 觸發的 CI run 上
恆定失敗，與 PR 實際內容無關（PR #41 兩次 push 重現、結果一致：詳見卡面）。

`_pull_request_synthetic_merge_sha()` 排除這一個 commit，且只排除這一個——不
靠 commit message 字串比對（會被巧合訊息繞過、也可能反向誤傷合法 commit），
而是要求以下四條**同時成立**才判定為 synthetic merge（缺一律回 None，維持
「照舊全檢」，寧可少排除也不要誤放行）：

1. `GITHUB_EVENT_NAME` 是 `pull_request`——只有這個事件的預設 checkout 才會
   把 GitHub 自產的合併 ref 當成 HEAD；本機互動或其他事件（含 `push`）一律
   不觸發排除，這保證了驗收條件2：本機無 `GITHUB_*` 環境變數時行為完全不變。
2. `GITHUB_SHA` 等於本地實際算出的 HEAD SHA——不是「假設」HEAD 是那個
   commit，是拿 CI runtime 回報的環境變數對照本地 git 算出來的值，兩者一致
   才算數。這一條同時保證了測試 fixture 之間互不干擾：獨立的 tmp repo 的
   HEAD 是全新算出的 SHA，不可能巧合等於外層 CI（若有）的 `GITHUB_SHA`。
3. HEAD 剛好是雙親 commit——這是 merge commit 的結構特徵，不是可選信號。
4. HEAD 的 commit message **精確**符合 GitHub 產生 synthetic merge 的固定
   格式 `Merge <40 碼 hex sha> into <GITHUB_BASE_REF 的實際值>`（用
   `re.fullmatch` 比對整個 subject，`base` 那一半用 `GITHUB_BASE_REF` 的
   實際字串精確比對，不是泛用正規表示式）。真人 `git merge --no-ff` 的預設
   訊息格式是 `Merge branch '<name>' into <base>`——結構上不同（有引號、有
   'branch' 字樣、不是完整 40 碼 hex），不會被這個格式誤認。

四條都是 CI 環境變數或 commit 結構事實，訊息比對只是其中一條、且被
`GITHUB_BASE_REF` 的實際值收緊，不是「看起來像不像」的字串猜測。排除的
對象精確到「這一個 SHA」本身，它的 parent（含真正的 PR head commit）維持
原樣照舊全檢——不放寬既有 REQUIRED 集合，也不擴大排除範圍。
"""

from __future__ import annotations

import os
import re
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


def _pull_request_synthetic_merge_sha(root: Path) -> str | None:
    """在 GitHub Actions `pull_request` checkout 下，若 HEAD 就是 GitHub 自動
    產生、需被排除的 synthetic merge commit，回傳其 SHA；其餘一切情況
    （本機、`push` 觸發、其他 CI、或任一信號對不上）一律回 None——回 None
    不代表「確認不是」，只代表「無法高度確信是」，此時呼叫端維持照舊全檢。

    四條件同時成立才回傳非 None（理由見本檔 module docstring 對應段落）：
    GITHUB_EVENT_NAME == pull_request、GITHUB_SHA == 本地 HEAD、HEAD 雙親、
    HEAD subject 精確符合 `Merge <40 hex sha> into <GITHUB_BASE_REF>`。
    """
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return None
    github_sha = os.environ.get("GITHUB_SHA")
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if not github_sha or not base_ref:
        return None
    head_sha = _git(root, "rev-parse", "HEAD").strip()
    if head_sha != github_sha:
        return None
    parents = _git(root, "log", "-1", "--format=%P", head_sha).split()
    if len(parents) != 2:
        return None
    subject = _git(root, "log", "-1", "--format=%s", head_sha).strip()
    if not re.fullmatch(rf"Merge [0-9a-f]{{40}} into {re.escape(base_ref)}", subject):
        return None
    return head_sha


def _new_commits(root: Path = ROOT) -> list[str]:
    """HEAD 相對 `_base_ref(root)` 的新 commit（邊界 ref 都解析不出時回空）。

    排除 GitHub `pull_request` checkout 自動產生的 synthetic merge commit
    （`_pull_request_synthetic_merge_sha`，DEV-TRAILER-GUARD-PR-CHECKOUT1）：
    這個 commit 不是任何人寫的、帶不了任何 trailer，只是 GitHub 算
    mergeability 的副產品，不該被當成「這張 PR 的新 commit」來驗。只排除這
    一個精確識別出的 SHA 本身，它的 parent（含真正的 PR head commit）維持
    原樣、照舊全檢。
    """
    base = _base_ref(root)
    if base is None:
        return []
    commits = [s for s in _git(root, "rev-list", f"{base}..HEAD").split() if s]
    synthetic = _pull_request_synthetic_merge_sha(root)
    if synthetic is not None:
        commits = [s for s in commits if s != synthetic]
    return commits


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


# ---------------------------------------------------------------------------
# DEV-TRAILER-GUARD-PR-CHECKOUT1（2026-08-04）：GitHub Actions 的 `pull_request`
# 事件預設 checkout `refs/pull/<N>/merge`——GitHub 自動產生的合併結果 commit，
# 訊息固定格式 `Merge <sha> into <base>`，不是任何人手動建立，帶不了任何
# trailer。這個 commit 就是該次 checkout 的 HEAD，必然落在 `main..HEAD`（或
# CI 退回用的 `origin/main..HEAD`）範圍內，導致 test_new_commits_carry_the_
# required_trailer_set 在任何 pull_request 觸發的 CI run 上恆定失敗——與 PR
# 實際內容無關（PR #41 兩次 run 重現，見卡面 Discovery）。
#
# 用 tmp bare repo + `git commit-tree` 手造一個雙親、無 trailer、訊息符合
# GitHub 固定格式的 commit，模擬 `refs/pull/N/merge` 的行為，重現這個假陽性；
# 同時在它下面疊一個「缺 trailer 的真實 commit」，證明修正不能矯枉過正——
# 排除 synthetic commit 的同時，真正需要被抓的缺陷仍要被抓到。
# ---------------------------------------------------------------------------

def _seed_pr_branch_with_missing_trailer(work: Path) -> str:
    """在 main 之外開一個分支，加一個缺 Planned-by 的真實 commit，模擬一張
    PR 分支的 head（這是「真正待驗的 commit」，修正後仍必須被抓到）。回傳其
    SHA。"""
    _git(work, "checkout", "-q", "-b", "ai/executor/PR")
    (work / "feature.py").write_text("x = 1\n")
    _git(work, "add", "feature.py")
    _git(work, "commit", "-q", "-m",
         "feat(models): add x\n\n"
         "Requested-by: test\nImplemented-by: test\nCo-Authored-By: test <t@example.com>\n")
    return _git(work, "rev-parse", "HEAD").strip()


def _graft_synthetic_merge_commit(work: Path, head_sha: str, *, base_branch: str = "main",
                                  message: str | None = None) -> str:
    """用 `git commit-tree` 手造一個雙親（base_branch 尖端 + head_sha）、無
    trailer 的 commit，並 `checkout --detach` 上去（模擬 actions/checkout 對
    `pull_request` 事件的預設行為：HEAD 落在 GitHub 自產的合併 ref 上，不是
    本地分支）。`message` 預設為 GitHub 對 synthetic merge 使用的固定格式；
    傳入不同格式可模擬「像但不是」的情境。回傳這個新 commit 的 SHA。"""
    base_sha = _git(work, "rev-parse", base_branch).strip()
    tree = _git(work, "rev-parse", f"{head_sha}^{{tree}}").strip()
    if message is None:
        message = f"Merge {head_sha} into {base_branch}"
    synthetic_sha = subprocess.run(
        ["git", "-C", str(work), "commit-tree", tree, "-p", base_sha, "-p", head_sha,
         "-m", message],
        capture_output=True, text=True, check=True).stdout.strip()
    _git(work, "checkout", "-q", "--detach", synthetic_sha)
    return synthetic_sha


def test_pull_request_checkout_excludes_synthetic_merge_but_still_catches_missing_trailer(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """紅→綠核心案例，重現 PR #41 兩次 CI run 的實際故障並證明修正雙向正確。

    修正前：synthetic merge commit 和它底下缺 Planned-by 的真實 commit 一起
    被算進 `_new_commits`，前者缺全部 4 個必要 trailer，恆定回報問題——這條
    assertion 在修正前會紅（即本卡的「紅」）。

    修正後兩件事都要成立：
      1. synthetic merge commit 完全不出現在新 commit 清單／問題清單裡。
      2. 它底下真正缺 trailer 的 commit 仍被抓到——證明沒有矯枉過正把整條
         守衛在 pull_request checkout 下變成失能（紅線3）。
    """
    work = _init_repo_with_remote(tmp_path)
    bad_sha = _seed_pr_branch_with_missing_trailer(work)
    synthetic_sha = _graft_synthetic_merge_commit(work, bad_sha, base_branch="main")

    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_SHA", synthetic_sha)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    commits = _new_commits(work)
    assert synthetic_sha not in commits, (
        "GitHub 自產的 synthetic merge commit（HEAD == GITHUB_SHA、雙親、訊息固定格式）"
        "不該被當成『這張 PR 的新 commit』——它不是任何人寫的，帶不了任何 trailer")
    assert bad_sha in commits, "排除 synthetic commit 不能連帶放過它底下真正的 PR commit"

    problems = _trailer_problems(work, commits)
    assert not any(synthetic_sha[:7] in p for p in problems), (
        "synthetic commit 缺全部 trailer 是預期的（它本來就不該有），"
        "守衛必須完全跳過它，不能出現在問題清單裡")
    assert any(bad_sha[:7] in p and "Planned-by" in p for p in problems), (
        "真實缺 trailer 的 commit 必須仍被抓到——不可矯枉過正變成整條守衛在 PR 上失能")


def test_synthetic_merge_detection_is_noop_without_github_event_name(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """本機（無 GITHUB_EVENT_NAME）下即使雙親＋訊息格式都符合，也不得排除——
    這條保證驗收條件2：本機行為完全不變，排除只在 CI 的 pull_request 情境下
    生效。"""
    work = _init_repo_with_remote(tmp_path)
    bad_sha = _seed_pr_branch_with_missing_trailer(work)
    synthetic_sha = _graft_synthetic_merge_commit(work, bad_sha, base_branch="main")
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.setenv("GITHUB_SHA", synthetic_sha)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    commits = _new_commits(work)
    assert synthetic_sha in commits, (
        "沒有 GITHUB_EVENT_NAME=pull_request 就不該排除任何 commit——"
        "本機互動情境下這個分支本來就該被完整檢查")


def test_synthetic_merge_detection_requires_github_sha_to_match_head(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """GITHUB_SHA 對不上實際 HEAD 時不得排除——避免環境變數殘留或誤設時
    誤傷（例如同一個 CI job 裡先跑了別的 repo 的 checkout）。"""
    work = _init_repo_with_remote(tmp_path)
    bad_sha = _seed_pr_branch_with_missing_trailer(work)
    synthetic_sha = _graft_synthetic_merge_commit(work, bad_sha, base_branch="main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_SHA", "0" * 40)  # 刻意對不上
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    commits = _new_commits(work)
    assert synthetic_sha in commits, (
        "GITHUB_SHA 與本地 HEAD 對不上時，不能假設 HEAD 是 synthetic merge commit")


def test_synthetic_merge_detection_requires_two_parents(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """單親的一般 commit 即使 env 都設對也不得誤判為 synthetic merge——
    synthetic merge 的結構特徵（雙親）是硬性條件，不是可選信號。"""
    work = _init_repo_with_remote(tmp_path)
    (work / "note.md").write_text("x\n")
    _git(work, "add", "note.md")
    _git(work, "commit", "-q", "-m", "chore: normal single-parent commit")
    head_sha = _git(work, "rev-parse", "HEAD").strip()
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_SHA", head_sha)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    assert _pull_request_synthetic_merge_sha(work) is None


def test_synthetic_merge_detection_rejects_real_merge_with_similar_message(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """判別器精確性的關鍵案例：真人 `git merge --no-ff` 的預設訊息格式是
    `Merge branch '<name>' into <base>`——雙親都有、也提到 into <base>，但
    不是 GitHub 那個精確格式（`Merge <40 hex sha> into <base>`，沒有引號、
    沒有 'branch' 字樣、sha 是完整 40 碼 hex）。即使 GITHUB_SHA／GITHUB_
    BASE_REF 都刻意設成與這個真人 merge commit 一致（模擬環境變數不巧對上
    的最壞情況），判別器仍不得把它當成 synthetic merge 排除——這正是紅線2
    要求的「真人 merge commit 即使訊息相似也不得誤排除」。"""
    work = _init_repo_with_remote(tmp_path)
    bad_sha = _seed_pr_branch_with_missing_trailer(work)
    real_merge_sha = _graft_synthetic_merge_commit(
        work, bad_sha, base_branch="main",
        message="Merge branch 'ai/executor/PR' into main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_SHA", real_merge_sha)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    assert _pull_request_synthetic_merge_sha(work) is None, (
        "真人 merge 的訊息格式（'Merge branch <name> into <base>'）不等於 GitHub "
        "synthetic merge 的固定格式（'Merge <40 hex sha> into <base>'），不得誤排除")
    # 而且這個「像但不是」的 merge commit 本身仍要被判定為需要驗 trailer
    # （它缺 Reviewed-by，是 is_merge 分支要求的）。
    commits = _new_commits(work)
    assert real_merge_sha in commits
    problems = _trailer_problems(work, commits)
    assert any(real_merge_sha[:7] in p and "Reviewed-by" in p for p in problems)


def test_synthetic_merge_detection_rejects_base_ref_mismatch(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """訊息裡的 base（'into main'）與 GITHUB_BASE_REF 對不上時不得排除——
    避免只用泛用正規表示式比對訊息格式，確保是拿環境變數的實際值精確比對。"""
    work = _init_repo_with_remote(tmp_path)
    bad_sha = _seed_pr_branch_with_missing_trailer(work)
    synthetic_sha = _graft_synthetic_merge_commit(work, bad_sha, base_branch="main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_SHA", synthetic_sha)
    monkeypatch.setenv("GITHUB_BASE_REF", "develop")  # 訊息說 into main，env 卻說 develop

    assert _pull_request_synthetic_merge_sha(work) is None


def test_synthetic_merge_detection_succeeds_when_all_signals_agree(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """正面案例：四個條件都成立時，判別器準確回傳該 synthetic merge commit 的 SHA。"""
    work = _init_repo_with_remote(tmp_path)
    bad_sha = _seed_pr_branch_with_missing_trailer(work)
    synthetic_sha = _graft_synthetic_merge_commit(work, bad_sha, base_branch="main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_SHA", synthetic_sha)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    assert _pull_request_synthetic_merge_sha(work) == synthetic_sha
