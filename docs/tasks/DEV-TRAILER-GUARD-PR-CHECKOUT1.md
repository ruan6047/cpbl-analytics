# DEV-TRAILER-GUARD-PR-CHECKOUT1 trailer 守衛在 pull_request 觸發的 CI checkout 上恆定假陽性〔T2；⚪一般〕

- 需求：ruan6047（經 `DEV-CI-SCORELESS-DB-SKIP1` 驗證 PR #41 CI 時發現並登記）　規劃：Claude Sonnet 5@Claude Code　分支：`ai/<執行者>/DEV-TRAILER-GUARD-PR-CHECKOUT1`
- 執行：待指派（建議 L2；需精確辨識 GitHub synthetic merge commit 而不誤放行真實 commit，設計需謹慎）　查核：待指派（新 context 即可，≠ 執行）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`tests/test_commit_trailers.py`（僅調整 synthetic merge commit 的排除判定，不放寬既有必要 trailer 集合對真實 commit 的要求）
- Discovery：Claude Sonnet 5@Claude Code（2026-08-04；於 `DEV-CI-SCORELESS-DB-SKIP1` PR #41 兩次 CI run 上重現）
- Design：Design Gate N/A——純測試基礎設施修正，無使用者可見介面。

## 問題陳述

GitHub Actions 的 `pull_request` 事件預設 checkout `refs/pull/<N>/merge`——GitHub 自動產生的合併結果 commit（訊息固定格式 `Merge <sha> into <base>`），不是任何人手動建立、也不可能帶任何 trailer。

`tests/test_commit_trailers.py::_new_commits()` 以本地 `main` 為界計算 `main..HEAD` 的新 commit；在 `pull_request` checkout 下，HEAD 就是這個 synthetic merge commit，必然被算進「新 commit」集合，導致此測試在**任何** pull_request 觸發的 CI run 上恆定失敗，與 PR 實際內容無關。

**已於 PR #41 兩次 push 重現、且結果可預期地一致**：
- run `30902007847`（commit `414d1c4`）：`4a9a143 Merge 414d1c40bc1eec684959c6225164d209408fa548 int[o main]` 缺全部 4 個必要 trailer；同批也抓到 `414d1c4` 自己缺 `Planned-by`（這項是真缺陷，已修正）。
- 修正 `414d1c4` 缺陷、amend 為 `5b047b1` 並 force-push 後重跑（run `30903052809`）：`414d1c4`／`5b047b1` 不再出現在問題清單，**證明測試對真實 commit 的判定正確**；但 `9b2323b Merge 5b047b120104f13ac6e5bed7478aa8a9ac8eb591 int[o main]`（GitHub 對新 push 重算的另一個 synthetic merge commit）依然缺全部 trailer，`api` job 依然失敗。

這代表 `test_commit_trailers.py` 自 `DEV-TRAILER-GUARD-SCOPE1`（2026-07-29）生效以來，**從未在真正的 `pull_request` 觸發 checkout 下被驗證過**——本專案先前的合併慣例是本機 `git merge --no-ff` 後直接 push `main`（見 `CONTROL_PLANE_CONTRACT.md`〈交付→查核→合併慣例〉），從未真的走 GitHub PR merge。PR #41 很可能是本專案第一個實際觸發 `pull_request` event 的 CI run，才第一次踩到這個路徑。

**這是 `OPS-CONTROL-PLANE-PR-GUARD1` 新的硬阻塞（且比原本發現的 DB 測試問題更根本）**：若不修，把 `api` 設為 PR required check 後，**每一張 PR 的 `api` job 都會恆定失敗**——不是某個測試偶爾紅，是這個守衛本身的判定範圍在 PR checkout 下必然把 GitHub 自己產生的 commit 算進來。Required check 會變成無差別鎖死所有 PR，而不是「保護」。

## 驗收條件

- [ ] `test_commit_trailers.py` 能正確辨識並排除 GitHub `pull_request` checkout 產生的 synthetic merge commit，且**不放寬**既有必要 trailer 集合對真實（非 synthetic）commit／merge commit 的要求。判定依據建議用 CI 環境變數（如 `GITHUB_EVENT_NAME`／`GITHUB_BASE_REF`／`GITHUB_SHA` 對照 PR head SHA）精確定位「這個 checkout 是否處於 pull_request 情境、真正待驗的 commit 是哪個」，而非僅憑 commit message 字串比對（避免被巧合訊息繞過或反向被合法 commit 誤傷）。
- [ ] 本機（無 `GITHUB_*` 環境變數）下 `_base_ref`／`_new_commits` 行為與既有測試（含變異檢驗）完全不變。
- [ ] 刻意構造一個「缺 trailer 的真實 commit」於 pull_request checkout 情境下模擬測試，確認修正後仍被抓到——不可矯枉過正變成整條守衛在 PR 上失能。
- [ ] 至少一個真實 PR 的 `pull_request`-觸發 CI run 上，`api` job 的 `test_commit_trailers.py` 通過（附 run URL 為證，不接受本機模擬替代）。

## 驗證

- 本機以 tmp bare repo + 手動建構 `refs/pull/N/merge` 風格的 synthetic merge commit（`git commit-tree` 直接造一個雙親、無 trailer 的 commit，模擬 GitHub 行為）重現目前假陽性；修正後同一情境不再誤判。
- `uv run pytest tests/test_commit_trailers.py -q` 全過（含既有變異檢驗）。
- 開一個小型驗證 PR，觸發 `pull_request` CI，`gh run view <run-id> --json jobs,conclusion` 確認 `api` 通過；並在同一 PR 上補一個刻意缺 trailer 的 commit 驗證仍被擋。

## 非目標

- 不放寬 T2+ commit 需要 `Requested-by`／`Planned-by`／`Implemented-by`（／merge 加 `Reviewed-by`）的既有規則本身。
- 不擴大守衛範圍去檢查 `main` 上的 Coordinator commit（`DEV-TRAILER-GUARD-SCOPE1` 已定案排除，理由見該測試 module docstring）。

## Log

- 2026-08-04 register by Claude Sonnet 5@Claude Code（於 `DEV-CI-SCORELESS-DB-SKIP1` PR #41 兩次 CI run 上重現並定位 root cause；不在該卡範圍內代修，另立此卡）。
