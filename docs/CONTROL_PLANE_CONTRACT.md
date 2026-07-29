# Control-plane Contract — cpbl-analytics

> 共同不變量見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) §4.1。本檔將跨人協作狀態與本機資源鎖分離；不得填入 token、secret 或個資。

## Adapter 邊界

| 範圍 | 實作 | 事實來源／用途 |
|---|---|---|
| Remote coordination | GitHub protected `main` + `ruan6047` 操作的 PR／Actions | 唯一 lifecycle writer；task、review、lease、CI |
| Local resource | `/private/tmp/cpbl-analytics-control-plane/<CARD_ID>/lease.json` 原子目錄鎖 | worktree、port、container、DB namespace 暫時互斥；僅 telemetry |
| Event store | [`events.jsonl`](control-plane/events.jsonl) 的 append-only Git history | 不可覆寫 lifecycle 歷史 |
| Ledger projection | `uv run python scripts/workflow_ledger.py --write` | [`TASKS.md`](TASKS.md) current-state；禁止手改 |

## Event、claim 與 WIP

- event 必填 canonical §4.1 欄位與投影欄位；同一卡 `state_version` 自 1 嚴格遞增。handoff、review、handoff-accepted、merge、release 固定 `source_sha` 與 evidence。
- **`closes_review_round`（review 事件選填，布林）**：`false` 表示這一筆是**中繼關卡**（Design Gate、需求方本地人工審…），**本輪查核尚未結束**；缺席即視為終結本輪。卡面要求多道關卡時（例：`UX-ENTITY-LINKS2` 的「先本地人工審再交跨家族查核」），**前面各關的 review 事件必須帶 `false`**，否則 `review_prompt.py` 會判定本輪已結束而拒絕為後續關卡產生提示詞（DEV-REVIEW-PROMPT-GATE1）。
  - 判定**以最新一筆 review 為準**：event log append-only，寫錯只能追加更正——採「存在任一終結本輪者」就永遠改不回來。故 `[中繼, 終局 REJECT]` 仍視為本輪結束；`[終局, 追加更正為中繼]` 則回到未結束。
  - 不得用 `delivery_status`、`owner` 或 `review_result` 的字面推斷此性質：實測 146 筆既有 review，最終 APPROVE 有 17 筆同樣停在 `🔍待查核`，且 owner 常寫成「（執行，交付待查核）」本身就含「查核」二字。**這個性質只由本欄位表達。**
- **跨 writer handoff 另見 [`HANDOFF_CONTRACT.md`](HANDOFF_CONTRACT.md)**（canonical §4.1／WF-20）：T2 以上或任何 owner 變更，sender 須先 push **完整 40 字元** `source_sha`，receiver 完成驗證清單後才寫 `handoff-accepted` 並取得所有權。該檔只規範 handoff 類事件的欄位與接收驗證，**envelope、event store 與 Ledger 投影仍以本檔為準**，不構成第二個狀態來源。baseline 為 2026-07-29，不追溯既有 150 筆無 acceptance 的 handoff。
- `ruan6047` 是唯一 lifecycle writer；Coordinator 先追加 event，再建立／釋放 local lease，最後重建 Ledger。local telemetry 必填 `lifecycle=false`、`claim_event_id`，不得改 card state。
- **lifecycle event 一律直接 commit 至 `main`**（由 Coordinator 或其指示的階段所有者執行），並在同一 commit 以 `--write` 重建 Ledger，使 `TASKS.md` 恆為當前狀態。**執行分支不得改動 `docs/control-plane/**` 與 `docs/TASKS.md`**；~~push main 前先 `git pull --rebase`~~ → **push main 前先 `git pull --ff-only`**（2026-07-29 修正，理由見下）。分支 merge 時上述路徑若衝突，一律以 main 為準（2026-07-17 前的舊分支載有歷史事件 commit，屬過渡遺留，衝突同樣以 main 為準）。
- **⚠️ 不得在 `--no-ff` merge 之後執行 `git pull --rebase`**：`git rebase` **預設丟棄 merge commit**，會把剛建立的 merge 靜默壓平成線性歷史，且**不報錯**。後果是 merge event 記錄的 `source_sha` 指向一個不在 `main` 上的 orphan commit，`Reviewed-by` trailer 隨 merge commit 一併消失（canonical §6 要求 merge commit 帶此 trailer）。
  - **已發生兩次**：2026-07-26 `INGEST-RECORDS-HR1`（non-ff merge `b8b89bc` 被線性化，實際落地 `78713dc`，見該卡 NOTE 事件）、2026-07-29 `DEV-TRAILER-GUARD-SCOPE1`（merge `cb97be1a` 成 orphan，見 `MERGE-CORRECTION-008`）。第一次已記錄卻未修本契約，故複發。
  - **改用 `--ff-only` 的理由**：落後時**明確失敗**而非靜默改寫歷史，由人決定如何處理（rebase 純 event commit、或 `--rebase=merges` 保留拓樸）。fail-loud 優於 fail-silent。
  - **已壓平且已推送時不得重寫 `main`**：改寫已推送的共用歷史比帳面錯誤嚴重得多。正確處置是追加 `merge-correction` 事件，記錄 orphan SHA、實際落地 SHA、內容等價性驗證，以及 `Reviewed-by` attestation 的補位。
- claim concurrency key 為 `cpbl-analytics:<CARD_ID>`；共享資源逐項宣告 `file:*`、`port:*`、`container:*`、`db:*`。預設 lease 4 小時；到期回收前檢查 worktree 與未提交變更，禁止靜默移除。
- WIP limit：agent 4、review queue 3（2026-07-24 自 2／2 上調，以吸收 BUILD1 執行期間的 lane-independent 前端批次；批次清空後回檢，非 lane-independent 卡不得靠此上調繞過車道互斥）；達上限停止新 claim，優先完成 review／release。

## 交付→查核→合併慣例（2026-07-25 定案）

canonical §2.1「實作與審核分離」不變：執行者不得查核或 merge 自己的變更。本節只固定
**查核之後**的操作分工，消除「每卡逐次請示」的往返。

- **查核提示詞由腳本產生，不向執行者索取**：`uv run python scripts/review_prompt.py <CARD_ID>`
  （可接 `| pbcopy`）。它讀該卡**最新 handoff event** 與卡片的驗收條件／驗證章節，
  自動帶入分支、`source_sha`、worktree、tier、`db_scope` 與獨立性要求。執行者只需把
  交付摘要寫進 handoff `evidence`（本來就是必填），不必另外產出提示詞。
- **APPROVE 即 merge，不再逐次請示**：查核回 APPROVE 且**零阻塞 finding**（INFO／
  非阻塞不算）時，Coordinator 直接以 `--no-ff` merge 並寫 merge＋release 事件，
  無須再向需求方請求合併授權。merge 者仍不得是該卡執行者；**例外依 canonical
  §2.1（WF-18）**：APPROVE／必要 sign-off 完成後、需求方明確授權時，執行者可代行
  merge 機械操作，merge commit 必帶 `Reviewed-by`、merge 事件必記授權來源——授權
  只豁免「誰按下 merge」，不豁免查核。
- **release 必以終態落地＋結案清單**（WF-18，canonical §0＋[`worktree-lifecycle.md`](../.ai-workflow/templates/worktree-lifecycle.md)）：
  免部署卡 release 即 `🏁完成`，需部署卡在部署 `✅已驗證` 前不得 release；結案
  五步（終態事件→卡檔封存→Ledger 重建→lease／分支清理→對帳三件套）缺一不可，
  **代 Coordinator 結案的查核者同樣適用**，無法完成即明確交回、不得停在中間態。
- **`occurred_at` 取寫入當下系統時鐘**（WF-18，canonical §4.1）：寫 event 前先
  `date "+%Y-%m-%dT%H:%M:%S+08:00"`，禁估算、遞增推定或沿用前值。
- **例外必須停下請示**（下列任一成立時，APPROVE 也不自動 merge）：查核含
  blocking／major finding；merge 有衝突或需 rebase 重驗；卡片 `db_scope` 為
  `schema`／`data-migration`；或卡面標記需求方 sign-off。
- **結果回傳原執行者**：merge 後由 Coordinator 將 merge_sha、findings 與後續待辦
  回傳原執行者；由**執行者**向需求方確認是否部署及其他後續（部署狀態轉態仍照
  `AI_RUNBOOK.md` §7，需求方裁定）。REJECT 一律退回原執行者、原分支、iteration+1。
- **查核者重跑不得污染交付 artifact**：交付物含可重生成檔案（報告 JSON、快照）時，
  查核者重跑須以 `--out` 導向 scratch 路徑；若已覆寫，以 `git checkout -- <path>`
  還原受查版本後再繼續（受查 artifact 是已提交版本，不是重跑產物）。
- **基線版本查核防線**（WF-17，canonical [`baseline-cascade.md`](../.ai-workflow/templates/baseline-cascade.md)）：
  查核 Initiative 子卡時，核對卡面 `spec 基線` 版本＝父卡當前版本，不一致即退回
  （防舊基線交付）。`review_prompt.py` 自動帶入父卡當前基線版本屬工具層強化，
  因 `file:scripts/review_prompt.py` 由 OPS-PROCESS-GUARD1 認領互斥，
  待該卡結案後以 follow-up 落地；落地前由查核者手動核對。

## 權限與事故處理

- 只有 protected `main` 的部署 workflow 可操作 production；外部協作者可提交 PR／review evidence，不可自行 claim、release、merge 或改寫 event log。
- GitHub 不可用時停止 claim／handoff／merge／release；本機鎖不可推進 card state。恢復後由 Coordinator 對帳並補 telemetry。
- claim、handoff、review、merge、release 後執行 `git worktree list`、檢查 local leases，並跑 `uv run python scripts/workflow_ledger.py --check`。
