# DEV-REVIEW-PROMPT-BASE1 查核提示詞在交付 SHA 的 worktree 內假性失敗〔T2；🟡流程〕

- review_independence: [context]
- 需求：ruan6047（2026-08-04 於 `DEV-BASELINE-GUARD-DECL1` 查核假性退回後指示開卡）　規劃：本卡 spec　分支：`ai/<執行者>/DEV-REVIEW-PROMPT-BASE1`
- 執行：待指派（建議 L2；改動窄，難點在「該讀哪一份 event log」的取捨而非實作）　查核：待指派（新 session 即可；≠ 執行）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`scripts/review_prompt.py`、對應測試
- Discovery：—（T2；缺陷已有逐字重現，見〈問題陳述〉）
- Design：Design Gate N/A——無使用者可見介面。
- **資源互斥**：`file:scripts/review_prompt.py` 目前由 `DEV-BASELINE-GUARD-DECL1`（🔍待查核）占用，**該卡合併前不得認領本卡**，否則同檔兩支未合併分支。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../../TASKS.md`](../../TASKS.md) Ledger；歷史寫入 adapter event log。

## 問題陳述

`review_prompt.py:120` 從**自己所在 worktree** 的 `ROOT / docs/control-plane/events.jsonl` 讀事件。
但依 `CONTROL_PLANE_CONTRACT.md`，control-plane **只存在於 main**，執行分支不得攜帶。於是在交付
SHA 的 detached worktree 內執行時，那份 event log 對該卡恆為 0 筆，`review_prompt.py:141` 直接吐
`錯誤：<CARD> 沒有 handoff event（尚未交付查核）。`

而 `HANDOFF_CONTRACT.md` §3 的驗收清單要求查核者「以 `git worktree add --detach <path> <完整SHA>`
建立獨立 detached worktree」。**照清單順序做的查核者，第一步就會撞到這個假性失敗**——訊息還把它
說成「尚未交付查核」，指向一個不存在的缺失。

正確順序（先在 main 產生提示詞，再依提示詞建 worktree）沒有寫在任何地方，只靠當事人推得出來。

## 2026-08-04 的實例（本卡由此而來）

`DEV-BASELINE-GUARD-DECL1` 三筆事件（register／claim／handoff）齊全落 main `2d569d6`，
`claim_event_id` 與 40 字元 `source_sha` 皆合規。查核者在交付 SHA `3b32fca` 的 detached worktree
內產生提示詞，得到上述錯誤，據以判定「送審前條件未成立、event log 缺 claim／handoff」並退回，
**未進行程式碼查核**。逐字重現：

- 在 `3b32fca` 的 detached worktree → 該卡事件數 **0**，錯誤訊息如上
- 在 main（`2d569d6`）→ 正常輸出提示詞

疊加的次要成因：主 checkout 當時落後 1 個 commit（停在 `00b9ab4`），從當時本地 `main` 開出來的
worktree 同樣讀不到。**兩種成因的症狀完全一樣，訊息無法區分**。

## 可考慮的方向（不預設答案）

`MAIN_ROOT`（`review_prompt.py:56`，由 `--git-common-dir` 反推主 checkout）**已經存在**，目前只用來
組 worktree 指令。候選：

1. event log 改讀 `MAIN_ROOT`——但主 checkout 可能停在舊 main 或別的分支，讀了不見得對。
2. 維持讀 `ROOT`，但在**找不到事件時**判斷當前 checkout 是否可能不帶 control-plane（HEAD detached／
   `docs/control-plane` 與 main 有落差），把訊息改成可行動的指引。
3. 兩者都做：優先讀 `MAIN_ROOT` 並印出實際來源與其 HEAD，落後時明講。

**取捨要明寫**：靜默改讀別處會讓「提示詞內容來自哪一份事實」變得不透明，比現在的假性失敗更難查。

## 非目標

- 不改 `HANDOFF_CONTRACT.md` §3 清單的內容（清單本身沒錯，缺的是與工具的先後關係）。
- 不改 control-plane 只存在於 main 這條規則。
- 不處理「主 checkout 落後」本身——那是操作紀律，本卡只要求症狀可區分。

## 驗收條件

- [ ] 在交付 SHA 的 detached worktree 內產生提示詞時，**不再**輸出會被誤讀成「執行者未交付」的訊息；
      輸出必須能讓查核者當場自行解決（明示事實來源、當前 checkout 為何不帶 control-plane、下一步指令）。
- [ ] **真正未交付**（該卡確實沒有 handoff event）仍明確失敗，且與上一項的訊息**可區分**——
      以負向測試證明兩種情境不會產生同一段輸出。
- [ ] 若改讀 `MAIN_ROOT`：印出實際讀取路徑與該 checkout 的 HEAD；取不到或落後時 fail loud，不靜默沿用。
- [ ] 在 `HANDOFF_CONTRACT.md` §3 或提示詞內明記「先於 main 產生提示詞，再建 detached worktree」的先後。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠。

## 驗證

- [ ] 三情境各跑一次並附輸出：(a) main 上正常產生；(b) 交付 SHA 的 detached worktree；
      (c) 確實無 handoff event 的卡。(b) 與 (c) 的輸出必須不同。
- [ ] `uv run ruff check` ＋ `uv run pytest`，**於 commit 之後執行**（`test_commit_trailers.py`
      在 commit 前會 skip，基線 3 skipped）。

## Log

- 2026-08-04 register 見 event log。
