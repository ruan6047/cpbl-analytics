# 任務看板（cpbl-analytics）

> 規則見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) 與本專案 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。git 是程式碼／文件事實來源；[`control-plane event log`](control-plane/events.jsonl) 是作業狀態事實來源；本檔是它的 current-state projection。
> **不可手動修改表格**：以 `uv run python scripts/workflow_ledger.py --write` 重建；`--check` 驗證投影未漂移。每張卡的範圍與歷史 Log 位於 [`tasks/`](tasks/)；結案後移至 [`archive/tasks/`](archive/tasks/)，索引列移至 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)。

## Ledger 總表（活卡）

| 卡ID | Initiative | 級別 | 功能 | owner | 分支／worktree | iteration | 交付狀態 | 部署狀態 | 最後交接 |
|---|---|---|---|---|---|---|---|---|---|
| [ML-PT3](tasks/ML-PT3.md) | — | T4 | 中職版球路品質指數 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [ML-SIM1](tasks/ML-SIM1.md) | — | T4 | 簡易勝負預測＋單一打席模擬 | ruan6047（待對帳） | — | 1 | ⏸阻塞 | ⏸未部署 | 2026-07-16T12:30:00+08:00 |
| [ML-SIM2](tasks/ML-SIM2.md) | — | T4 | 全場狀態模擬器 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [ML-UMP1](tasks/ML-UMP1.md) | — | T4 | 好球帶判決差異研究 | ruan6047（收尾） | — | 2 | 📦已合併 | —不適用 | 2026-07-16T12:30:00+08:00 |
| [ML-UMP2](tasks/ML-UMP2.md) | — | T4 | 身高比例逐打者代理帶敏感度重跑 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [TEAM-STYLE1](tasks/TEAM-STYLE1.md) | — | T4 | 球隊球風研究 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [UX-MATCHUP1](tasks/UX-MATCHUP1.md) | — | T3 | /matchups 查詢式頁面重製 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [UX-MATCHUP2](tasks/UX-MATCHUP2.md) | — | T3 | 投打對決整合球員個人頁 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [UX-OUTCOME-HOME](tasks/UX-OUTCOME-HOME.md) | — | T3 | 首頁賽事勝率預測整合 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [UX-RECORD1](tasks/UX-RECORD1.md) | — | T3 | /records 歷史重要性導向重製 | ruan6047（部署） | — | 1 | 📦已合併 | ⏸未部署 | 2026-07-16T12:30:00+08:00 |
| [VENUE-DEFUNCT](tasks/VENUE-DEFUNCT.md) | — | T3 | 已拆除球場納入球場維度 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |

## 依賴與資源註記

- `MATCHUP-DATA1 → ML-MATCHUP1 → UX-MATCHUP1 → UX-MATCHUP2`；前兩卡已結案（ML-MATCHUP1 三輪跨家族審核後 merge `336ee01`，封存於 archive），UI 卡可啟動。
- `RECORD-DATA1 → RECORD-API1 → UX-RECORD1`；前兩卡已結案並封存。
- `ML-UMP1 → ML-UMP2`：身高比例帶重跑複用前者引擎與敏感度框架；方向性呈現仍以 ML-UMP2 翻轉測試為前置閘門。
- `ML-SIM1` 的舊 Ledger 與卡片內容互相矛盾；migration baseline 已 fail-closed 設為 `⏸阻塞`，Coordinator 對帳後才可發新 lifecycle event。
- 升級前歷史仍封存於 [`archive/TASKS_PRE_WF12.md`](archive/TASKS_PRE_WF12.md)，不得為新格式回寫。
