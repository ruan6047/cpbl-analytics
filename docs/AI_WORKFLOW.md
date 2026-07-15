# AI 協作工作流（cpbl-analytics 採用）

> **完整規則見 canonical（submodule）：[`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md)**（唯一權威來源；規則改動在 [ruan6047/ai-workflow](https://github.com/ruan6047/ai-workflow)）。採用與遷移說明見 [`../.ai-workflow/ADOPTION.md`](../.ai-workflow/ADOPTION.md)。
> 本專案的任務 Ledger 見 [`TASKS.md`](TASKS.md)，卡片明細在 [`tasks/`](tasks/)；控制平面 [control plane]、資料庫與部署操作分別見 [`AI_RUNBOOK.md`](AI_RUNBOOK.md)、[`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) 與 Runbook §7。模型選擇見 [`MODEL_ROUTING.md`](MODEL_ROUTING.md)。

## 核心鐵律（速查）

1. **實作／審核分離**：同一張 A 類卡的執行、查核與 merge 必須是不同經手者；查核者只退回、不代改。
2. **分支 + 部署閘門**：程式碼（A 類）每卡開分支與獨立 worktree；僅已審核合併至 `main` 的提交可部署。A 類 repo 必須以 branch protection／required checks 強制。
3. **紅線獨立性**：安全、金流、統計／ML、資料正確性、資安部署與 production migration 必須換模型家族或人工查核，並附實測證據。
4. **控制平面**：只有 Runbook 指定的 Coordinator 可原子 claim／release 卡片、建立 worktree、核發共享資源 lease；看板文字與聊天訊息不是鎖。
5. **資料庫契約**：碰 DB 的卡片必填 `db_scope`；schema／data migration 為紅線，依 [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) 宣告 namespace、鎖、備份、回滾與驗證。
6. **可驗證交接**：執行→查核前必須工作區乾淨、分支已推、自測與環境證據齊全；任何回歸測試必須先對缺陷版本跑紅。
7. **留痕**：commit 加 `Requested-by`、`Planned-by`、`Implemented-by`、`Reviewed-by` trailers；人以 GitHub 帳號記錄、AI 以 `模型@工具` 記錄。
8. **狀態與封存**：交付與部署分欄；需部署的卡唯有驗證成功才可完成。`TASKS.md` 僅留活卡 Ledger，卡片一檔，結案後封存。

派工由人工進行；Coordinator 由 `AI_RUNBOOK.md` 指定。任何工具擔任執行者時，均不得兼任該卡查核者。
