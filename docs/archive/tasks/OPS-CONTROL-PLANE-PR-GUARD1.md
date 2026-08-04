# OPS-CONTROL-PLANE-PR-GUARD1 將 control-plane 轉為受保護 PR 的機械守衛〔T3；🟡流程〕

- 需求：ruan6047（2026-08-04 裁定 enforcement model）　規劃：GPT-5.6@Codex　分支：`ai/<執行者>/OPS-CONTROL-PLANE-PR-GUARD1`
- 執行：待指派（建議 L3；GitHub remote rules、CI 與 lifecycle 契約須一致）　查核：待指派（建議 L2；≠ 執行）
- Initiative：—　spec 基線：v1
- review_independence: [context]
- DB：`db_scope: none`
- 部署：否　環境：GitHub repository settings + CI　PR：—　Merge SHA：—
- 範圍：`.github/workflows/ci.yml`、`docs/CONTROL_PLANE_CONTRACT.md`、`docs/AI_RUNBOOK.md`，以及 GitHub `main` 的 remote rules；不修 application／資料正確性邏輯。
- Discovery：GPT-5.6@Codex（2026-08-04；GitHub API、Actions 與本地契約查核）
- Design：Design Gate N/A——純協作與交付流程，無使用者可見介面。

## 問題陳述

`DEV-EVENT-REPAIR-ANCHOR1` 需要 post-commit 的 Git history 驗證，但現行 control-plane 直接 push `main`。GitHub `main` 尚未啟用 branch protection（`gh api repos/ruan6047/cpbl-analytics/branches/main/protection` 回 404），CI 也只在 push 後執行；所以失敗最多被事後發現，不能阻止 pending repair 進入 remote main。

需求方已裁定新模型：control-plane 與程式碼一律先進 PR，只有 required checks 成功後才可 merge main。此卡要把裁定變成可拒絕、可重現的 remote 行為，並改掉 project contract 中的 direct-main 假設。

## Discovery 結論

目前 candidate required check 是 CI workflow 的 `api` job（含 ruff＋pytest）與 `web` job。兩者都不能立刻設 required：最近 main push run `30895706890` 的 `api` 失敗，`tests/test_scoreless_streak_api.py::test_every_counted_appearance_is_officially_er_zero` 嘗試連 `localhost:5433` 而 CI 沒有 PostgreSQL；`web` 成功。這不是本卡授權範圍內可憑猜測修的 DB 測試問題。

因此「API 有可重現綠色基線」是 remote rules 變更前的硬 Gate。若仍為紅，執行者必須停止，記錄精確 failing test／run URL，並由需求方指派或註冊專門修復卡；不得把 red `api` 設 required 來鎖住所有 PR，也不得改用只跑 web 的 check 來假裝保護 Anchor 的 Python guard。

## 核可的 enforcement model

- main 不接受人類或 AI 的 direct push；所有 lifecycle event 與程式碼變更都由 PR merge 落 main。現有 control-plane event 的「直接 commit main」條文必同步撤換，否則 remote rule 與 Runbook 自相矛盾。
- main merge 要求 PR 分支已與 main 同步、required `api` 與 `web` checks 成功，且不允許以本機帳號 bypass。具體使用 branch protection 或 repository ruleset 由執行者依 GitHub UI／API 可用能力選擇，但交付必以行為證據而非設定截圖驗收。
- `api` 必保留 full Git history（現有 `fetch-depth: 0`），並在本卡後續 `DEV-EVENT-REPAIR-ANCHOR1` 落地時包含 production `workflow_ledger.py --check`；Guard 卡本身不預先假設尚不存在的 CLI flag。
- 需要 emergency bypass 時，需求方須另行明示並留 lifecycle event；此卡不建立常設 bypass。

## 執行計畫

### Task 1：取得 required-check 綠色基線或建立其修復去向（S）

在 clean GitHub Actions run 驗證 `api`／`web` 的實際 check 名稱與結果。若 `api` 仍因 PostgreSQL 缺失失敗，停止設定 remote rules，留下 run URL、root symptom 與可執行 owner card；不得代修不在範圍的 DB test。

**驗收條件：**

- [ ] `api` 與 `web` 有同一 source SHA 的成功 run，check 名稱可供 remote rules 精確要求。
- [ ] 若無法達成，新增／指名有 owner 的修復卡並將本卡 `⏸阻塞`，不修改 main protection。

**驗證：** `gh run list --workflow CI`、`gh run view <run-id> --json jobs,conclusion,url`。

### Task 2：以 PR 先轉換 project lifecycle 契約（M）

在一張普通 PR 中更新 Runbook／Contract：事件由受保護 PR merge 寫入 main；Ledger 在 PR branch 生成、required CI 驗證，merge 後再以 main SHA 對帳。移除 direct-main 指令與「push 前 ff-only 即可」的錯誤保證，保留 event append-only、state version 與 lease 規則。

**驗收條件：**

- [ ] 文件沒有任何仍要求 lifecycle 直接 push main 的操作指令。
- [ ] 新流程明列 PR branch、required checks、merge 後 Ledger 對帳與 emergency exception 留痕。
- [ ] 文件／Ledger 相關測試與完整 `pytest` 綠色。

**驗證：** `rg -n '直接 commit 至 `main`|push origin HEAD:main' docs`、`uv run pytest -q`、`uv run python scripts/workflow_ledger.py --check`。

### Task 3：套用 remote rules 並做三種行為證據（M）

只有 Task 1 綠色、Task 2 已核可 merge 後，設定 GitHub main rules。以隔離測試分支／PR 驗證，不把故意失敗的 repair merge main。

**驗收條件：**

- [ ] direct `git push origin HEAD:main` 被 remote 拒絕；嘗試本身不得改寫 main。
- [ ] required check 失敗的 PR 無法 merge；PR 落後 main 亦無法 merge，直到更新後重新通過 checks。
- [ ] checks 全綠且 branch up-to-date 的 PR 可正常 merge；merge 後 main 的 Ledger 與 event log 對帳成功。

**驗證：** GitHub branch rules API／UI 輸出、三張測試 PR 的 URL 與 status、`gh pr checks <pr>`、`gh pr merge --auto --merge` 的拒絕／成功證據、merge 後 `workflow_ledger.py --check`。

### Checkpoint：解除 Anchor 阻塞前

- [ ] Task 1–3 全部完成；remote rules 的行為證據由獨立查核者重跑。
- [ ] `DEV-EVENT-REPAIR-ANCHOR1` 的 BLOCKED event 已引用本卡 merge SHA 與三項 evidence，才可解除。

## 非目標

- 不修 `test_scoreless_streak_api` 的 DB 依賴；它只是一項 required-check 綠色基線的 blocker。
- 不改 canonical `.ai-workflow`；若 project contract 的 PR 模型與 canonical 衝突，停下交需求方裁定，不自行改 submodule。
- 不導入 GitHub App、外部簽章或常設 admin bypass。

## 紅線

1. **不得在 `api` 為紅時啟用它為 required。** 這會把每張 PR 無差別鎖死，並把既有紅燈藏成「保護已完成」。
2. **不得以只成功的 `web` 取代 `api`。** Anchor 的守衛在 Python CI，略過 `api` 等於建立外觀有鎖、實際無鎖的規則。
3. **不得只用設定截圖宣稱受保護。** 必須有 direct push 拒絕、失敗 PR 不可 merge、成功 PR 可 merge 三種真實行為證據。
4. **不得保留未記錄的 bypass。** 否則受保護 PR 只是慣例，不是機械邊界。

## 驗收條件

- [ ] required `api`／`web` 先有同 SHA 綠色基線，或本卡以有 owner 的修復卡明確阻塞。
- [ ] project workflow 文件改為 PR merge，沒有 direct-main lifecycle 衝突。
- [ ] GitHub main 規則以三種 remote 行為證據證明生效。
- [ ] 完整 `pytest`、ruff、Ledger check 通過；remote 變更後再跑一次 GitHub Actions 成功。

## 驗證

- [ ] 查核者以不同測試 branch 重跑 direct push 與 failed-PR 拒絕情境。
- [ ] 查核者核對 required check 的名稱與實際 workflow job，非只看文件。
- [ ] 查核者確認 Anchor 卡仍未在本卡完成前認領。

## 邊界

- 預估 M；Task 1→2→3 必須串行，remote settings 不與其他 writer 平行修改。
- 這是 `DEV-EVENT-REPAIR-ANCHOR1` 的硬前置；它完成前 Anchor 保持 `⏸阻塞`。

## Log

- 2026-08-04 register by GPT-5.6@Codex（依 ruan6047 已核可的 enforcement model 建卡）。Discovery 實測：main protection API 404；CI `api`／`web` 已存在且 checkout `fetch-depth: 0`；main run `30895706890` 的 `api` 因 `test_every_counted_appearance_is_officially_er_zero` 連不到 localhost PostgreSQL 失敗、web 成功。故先設 required check 會永久鎖死 PR，綠色基線／修復去向列為 Gate 0，而非在本卡腦補 DB 解法。
