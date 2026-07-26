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

- event 必填 canonical §4.1 欄位與投影欄位；同一卡 `state_version` 自 1 嚴格遞增。handoff、review、merge、release 固定 `source_sha` 與 evidence。
- `ruan6047` 是唯一 lifecycle writer；Coordinator 先追加 event，再建立／釋放 local lease，最後重建 Ledger。local telemetry 必填 `lifecycle=false`、`claim_event_id`，不得改 card state。
- **lifecycle event 一律直接 commit 至 `main`**（由 Coordinator 或其指示的階段所有者執行），並在同一 commit 以 `--write` 重建 Ledger，使 `TASKS.md` 恆為當前狀態。**執行分支不得改動 `docs/control-plane/**` 與 `docs/TASKS.md`**；push main 前先 `git pull --rebase`。分支 merge 時上述路徑若衝突，一律以 main 為準（2026-07-17 前的舊分支載有歷史事件 commit，屬過渡遺留，衝突同樣以 main 為準）。
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
  無須再向需求方請求合併授權。merge 者仍不得是該卡執行者。
- **例外必須停下請示**（下列任一成立時，APPROVE 也不自動 merge）：查核含
  blocking／major finding；merge 有衝突或需 rebase 重驗；卡片 `db_scope` 為
  `schema`／`data-migration`；或卡面標記需求方 sign-off。
- **結果回傳原執行者**：merge 後由 Coordinator 將 merge_sha、findings 與後續待辦
  回傳原執行者；由**執行者**向需求方確認是否部署及其他後續（部署狀態轉態仍照
  `AI_RUNBOOK.md` §7，需求方裁定）。REJECT 一律退回原執行者、原分支、iteration+1。
- **查核者重跑不得污染交付 artifact**：交付物含可重生成檔案（報告 JSON、快照）時，
  查核者重跑須以 `--out` 導向 scratch 路徑；若已覆寫，以 `git checkout -- <path>`
  還原受查版本後再繼續（受查 artifact 是已提交版本，不是重跑產物）。

## 權限與事故處理

- 只有 protected `main` 的部署 workflow 可操作 production；外部協作者可提交 PR／review evidence，不可自行 claim、release、merge 或改寫 event log。
- GitHub 不可用時停止 claim／handoff／merge／release；本機鎖不可推進 card state。恢復後由 Coordinator 對帳並補 telemetry。
- claim、handoff、review、merge、release 後執行 `git worktree list`、檢查 local leases，並跑 `uv run python scripts/workflow_ledger.py --check`。
