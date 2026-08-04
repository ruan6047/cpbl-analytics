# AI 協作工作流（cpbl-analytics 採用）

> **⚠️ 2026-08-04 起新治理生效（WF-22 Wave 0/1 已實施、cutover 已宣告）**：
> 作業狀態唯一事實來源＝**GitHub Issues＋user Project #4「cpbl-analytics 任務看板」**；
> 唯一狀態寫入通道＝ai-workflow repo 的 **`wfcli`**（`cli/`）。`docs/control-plane/events.jsonl`
> 與 `docs/TASKS.md` 投影**已封存唯讀**（終筆 `8271d7c`）——不得再追加事件或重建 Ledger。
> 開卡／派工／結案決策＝需求方本人；機械寫入＝PM 祕書 session 專責。canonical 全文
> 改版（Wave 2）前，下文與新制衝突處以
> [`research/WORKFLOW-REVIEW-2026-08-04.md`](research/WORKFLOW-REVIEW-2026-08-04.md)（決議紀錄）
> ＋[`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md) §2 為準。

> **完整規則見 canonical（submodule）：[`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md)**（唯一權威來源；規則改動在 [ruan6047/ai-workflow](https://github.com/ruan6047/ai-workflow)）。既有專案升級依 [`../.ai-workflow/MIGRATION.md`](../.ai-workflow/MIGRATION.md)。
> 本專案任務看板見 [`TASKS.md`](TASKS.md)，控制平面見 [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)，新卡範本索引見 [`TEMPLATES.md`](TEMPLATES.md)，資料庫與部署操作分別見 [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) 與 [`AI_RUNBOOK.md`](AI_RUNBOOK.md) §7。模型選擇見 [`MODEL_ROUTING.md`](MODEL_ROUTING.md)。

## 核心鐵律（速查）

1. **變更分級 + 部署閘門**：依 canonical T0–T4 按風險、範圍、可逆性選閘門；T2 以上程式碼（A 類）每卡開分支，每卡／卡族有獨立 worktree；只有已審核合併至 `main` 的提交可部署。
2. **實作／審核分離**：同一張卡的執行與查核須由不同經手者；查核發現缺陷以 PR review／event 留 finding，原執行者在原分支修正，查核者不得改 source branch。卡面／baseline／SHA／依賴等 preflight 失敗不建立 review、不增加 iteration；第三個可計數實質退回先進 escalation checkpoint，只有重複根因、舊 finding 未修或需求方裁定才轉 `🚨已升級`（canonical [`review-escalation.md`](../.ai-workflow/templates/review-escalation.md)）。有效但不計數的 review 仍可閉合 finding；同 attempt finding 衝突須以 `review-correction` 裁決，epoch 切換須有需求方明示授權。查核結論統一用 `APPROVE | REQUEST_CHANGES`；舊的自由文字 `REJECT` 不得用於 WF-21 baseline 後新事件。
3. **紅線獨立性**：安全、金流、統計／ML、資料正確性、資安部署與 production migration 一律 T4；review 必換模型家族或人工，且須附實測證據與必要 sign-off。
4. **Discovery → Design → Plan**：T3/T4 先確認問題、證據與成功條件；使用者可見的 T3/T4 卡必過 Design Gate，純技術 T3/T4 卡必記錄 Design Gate `N/A` 理由；大型工作以 Initiative 管理 spec 基線、依賴、里程碑與變更。
5. **聯邦式控制平面**：GitHub remote coordination 管 task、review、lease、CI；local resource lock 管 worktree／port／container；event log 是歷史，Ledger 是投影，不可各自手改。
6. **留痕**：T0/T1 commit 至少 `Requested-by`、`Implemented-by`；T2 以上實作 commit 再加 `Planned-by`；merge、PR 結案或 B2 權威文件核可再加 `Reviewed-by`。
7. **驗證與封存**：先讀再說、不虛構 API／表／指令；secrets 永不進 git；交付須附改動、原因與實測。需部署的卡僅在驗證成功後可 `🏁完成`，失敗／回滾不得封存。

派工由人工進行；Coordinator 由 [`AI_RUNBOOK.md`](AI_RUNBOOK.md) 指定。同一卡的執行者不得兼任查核者：一般卡查核以新 context／session 為獨立即可，紅線卡須換模型家族或人工審核。
