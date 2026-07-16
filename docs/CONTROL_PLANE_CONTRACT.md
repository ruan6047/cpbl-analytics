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
- claim concurrency key 為 `cpbl-analytics:<CARD_ID>`；共享資源逐項宣告 `file:*`、`port:*`、`container:*`、`db:*`。預設 lease 4 小時；到期回收前檢查 worktree 與未提交變更，禁止靜默移除。
- WIP limit：agent 2、review queue 2；達上限停止新 claim，優先完成 review／release。

## 權限與事故處理

- 只有 protected `main` 的部署 workflow 可操作 production；外部協作者可提交 PR／review evidence，不可自行 claim、release、merge 或改寫 event log。
- GitHub 不可用時停止 claim／handoff／merge／release；本機鎖不可推進 card state。恢復後由 Coordinator 對帳並補 telemetry。
- claim、handoff、review、merge、release 後執行 `git worktree list`、檢查 local leases，並跑 `uv run python scripts/workflow_ledger.py --check`。
