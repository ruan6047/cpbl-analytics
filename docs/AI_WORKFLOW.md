# AI 協作工作流 (cpbl-analytics 採用)

> **完整規則見 canonical（submodule）：[`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md)**（唯一權威來源，改規則到 [ruan6047/ai-workflow](https://github.com/ruan6047/ai-workflow)；採用說明見 [`../.ai-workflow/ADOPTION.md`](../.ai-workflow/ADOPTION.md)）。
> 更新規則到最新：`git submodule update --remote .ai-workflow && git add .ai-workflow && git commit -m "chore: sync ai-workflow"`。
> 本專案任務看板／log 見 [`TASKS.md`](TASKS.md)。以下為**核心鐵律速查**，細節與流程圖以 canonical 為準。

## 核心鐵律（速查）
1. **實作／審核分離**：同一張卡的執行與查核＝不同任務、不同經手者；**任何人不得自審自己實作的卡**（含 Claude Code）。
2. **分支 + 部署閘門**：**程式碼(A 類)每卡開分支** `ai/<模型或工具>/<卡ID>`（文件/資料維運不必，見 canonical §0.1）；**只有 `main`（已審核合併）能部署，分支不部署**。
3. **獨立性紅線**：紅線卡（統計/ML 正確性、賽果/救援/RE/守備/球種重建、資料正確性…）審核**必換模型家族或人審**，且**必跑實測**——同家族審（含 Opus 審 Sonnet）不算數。一般卡同家族異 session 審可接受。
4. **退回不代改**：審核發現缺陷 → 退回 + 缺陷報告 → **原執行者同分支修** → 重審；審核者**不得順手改**。連續 ≥3 次退回 → 升級。
5. **留痕**：commit 加 trailer `Requested-by` / `Planned-by` / `Implemented-by` / `Reviewed-by`（模型@工具具體寫）。

**派工＝人工**（使用者）；**Claude Code 預設當審核 + PM（merge 閘門）**。

## cpbl 專屬
- **部署細節**：push cpbl main → 主站 bump submodule → CI（見 [`AI_RUNBOOK.md`](AI_RUNBOOK.md) §3、memory `data-sync-local-to-prod`）。**分支不部署**這條在此語境＝分支不 bump submodule、不同步生產。
- **紅線範圍**：統計/ML（Marcel 紅線、救援/RE/守備/球種分類）＝ CLAUDE.md 的 Fable 級——查核比照本檔紅線（換家族或人審 + 實測）。
