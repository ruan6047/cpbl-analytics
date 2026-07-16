# 任務看板（cpbl-analytics）

> 規則見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) 與本專案 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。git 是程式碼／文件事實來源；[`control-plane event log`](control-plane/events.jsonl) 是作業狀態事實來源；本檔是它的 current-state projection。
> **不可手動修改表格**：以 `uv run python scripts/workflow_ledger.py --write` 重建；`--check` 驗證投影未漂移。每張卡的範圍與歷史 Log 位於 [`tasks/`](tasks/)；結案後移至 [`archive/tasks/`](archive/tasks/)，索引列移至 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)。

## Ledger 總表（活卡）

| 卡ID | Initiative | 級別 | 功能 | owner | 分支／worktree | iteration | 交付狀態 | 部署狀態 | 最後交接 |
|---|---|---|---|---|---|---|---|---|---|
| [DOC-GAME-RECAP1](tasks/DOC-GAME-RECAP1.md) | INIT-GAME-RECAP | T3 | 賽事復盤產品規格獨立查核 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T22:15:04+08:00 |
| [GAME-RECAP-DATA1](tasks/GAME-RECAP-DATA1.md) | INIT-GAME-RECAP | T4 | 賽事復盤資料覆蓋與 canonical 契約稽核 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T22:15:05+08:00 |
| [GAME-RECAP-PA1](tasks/GAME-RECAP-PA1.md) | INIT-GAME-RECAP | T4 | canonical 打席與逐球可靠對應 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:06+08:00 |
| [GAME-RECAP-STATUS1](tasks/GAME-RECAP-STATUS1.md) | INIT-GAME-RECAP | T4 | 賽事狀態、資料可用性與 freshness API | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:07+08:00 |
| [GAME-RECAP-WP-API1](tasks/GAME-RECAP-WP-API1.md) | INIT-GAME-RECAP | T4 | canonical WP／WPA public contract | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:09+08:00 |
| [GAME-RECAP-WP-VAL1](tasks/GAME-RECAP-WP-VAL1.md) | INIT-GAME-RECAP | T4 | 場中 WP 時間外驗證與支援邊界 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T22:15:08+08:00 |
| [INIT-GAME-RECAP](tasks/INIT-GAME-RECAP.md) | INIT-GAME-RECAP | T4 | 隔日賽事脈絡與逐打席復盤 | ruan6047（Design Gate） | — | 0 | 💡需求 | —不適用 | 2026-07-16T22:15:03+08:00 |
| [ML-PT3](tasks/ML-PT3.md) | — | T4 | 中職版球路品質指數 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [ML-SIM2](tasks/ML-SIM2.md) | — | T4 | 全場狀態模擬器 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [ML-UMP2](tasks/ML-UMP2.md) | — | T4 | 身高比例逐打者代理帶敏感度重跑 | ruan6047（push／release） | `ai/gpt-5-codex/ML-UMP2 @ /private/tmp/cpbl-analytics-UMP2` | 1 | 📦已合併 | —不適用 | 2026-07-17T02:25:06+08:00 |
| [TEAM-STYLE1](tasks/TEAM-STYLE1.md) | — | T4 | 球隊球風研究 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [UX-GAME-HOME1](tasks/UX-GAME-HOME1.md) | INIT-GAME-RECAP | T3 | 昨日回顧與賽事復盤首頁入口 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:12+08:00 |
| [UX-GAME-PA1](tasks/UX-GAME-PA1.md) | INIT-GAME-RECAP | T3 | 逐打席與逐球脈絡探索器 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:11+08:00 |
| [UX-GAME-RECAP1](tasks/UX-GAME-RECAP1.md) | INIT-GAME-RECAP | T3 | 結論先行的單場賽後復盤 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:10+08:00 |
| [UX-MATCHUP1](tasks/UX-MATCHUP1.md) | — | T3 | /matchups 查詢式頁面重製 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [UX-MATCHUP2](tasks/UX-MATCHUP2.md) | — | T3 | 投打對決整合球員個人頁 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [UX-OUTCOME-HOME](tasks/UX-OUTCOME-HOME.md) | — | T3 | 首頁賽事勝率預測整合 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |

## 依賴與資源註記

- `MATCHUP-DATA1 → ML-MATCHUP1 → UX-MATCHUP1 → UX-MATCHUP2`；前兩卡已結案（ML-MATCHUP1 三輪跨家族審核後 merge `336ee01`，封存於 archive），UI 卡可啟動。
- `RECORD-DATA1 → RECORD-API1 → UX-RECORD1` 已全數結案；UX-RECORD1 已部署並封存。
- `ML-UMP1 → ML-UMP2`：前者已結案封存；身高比例帶重跑可複用其引擎與敏感度框架，方向性呈現仍以 ML-UMP2 翻轉測試為前置閘門。
- `ML-SIM1` 已完成跨家族複查、合併與 production 驗證並封存；`UX-OUTCOME-HOME` 的模型依賴已解除，但仍待 Design／派工。
- `INIT-GAME-RECAP` 仍在 Design Gate；依賴主鏈為 `GAME-RECAP-DATA1 → GAME-RECAP-PA1 → GAME-RECAP-WP-VAL1 → GAME-RECAP-WP-API1 → UX-GAME-RECAP1 → UX-GAME-PA1`，`GAME-RECAP-STATUS1` 與 `UX-GAME-HOME1` 走平行狀態／入口切片。未核可前不得 claim 實作卡。
- 升級前歷史仍封存於 [`archive/TASKS_PRE_WF12.md`](archive/TASKS_PRE_WF12.md)，不得為新格式回寫。
