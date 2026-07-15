# 任務看板（cpbl-analytics）

> 規則見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) 與本專案 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。git commit trailer 為衝突時的事實來源。
> **本檔僅為活卡 Ledger**；狀態只在此表。每張卡的範圍、DB 宣告與 Log 位於 [`tasks/`](tasks/)；完成或封存後移至 [`archive/tasks/`](archive/tasks/)，索引列移至 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)。

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 交付狀態 | 部署狀態 |
|---|---|---|---|---|---|---|---|---|
| [VENUE-DEFUNCT](tasks/VENUE-DEFUNCT.md) | 已拆除球場納入球場維度 | ruan6047 | 待指派 | 待指派 | `ai/<執行者>/VENUE-DEFUNCT` | ⚪ | 📥Backlog | —不適用 |
| [UX-OUTCOME-HOME](tasks/UX-OUTCOME-HOME.md) | 首頁賽事勝率預測整合 | ruan6047 | 待指派 | 待指派 | `ai/<執行者>/UX-OUTCOME-HOME` | ⚪ | 📥Backlog | —不適用 |
| [ML-MATCHUP1](tasks/ML-MATCHUP1.md) | 天敵候選／優勢對位統計洞察 | ruan6047 | 待指派 | 待指派 | `ai/<執行者>/ML-MATCHUP1` | 🔴 | 📥Backlog | —不適用 |
| [UX-MATCHUP1](tasks/UX-MATCHUP1.md) | `/matchups` 查詢式頁面重製 | ruan6047 | 待指派 | 待指派 | `ai/<執行者>/UX-MATCHUP1` | ⚪ | 📥Backlog | —不適用 |
| [UX-MATCHUP2](tasks/UX-MATCHUP2.md) | 投打對決整合球員個人頁 | ruan6047 | 待指派 | 待指派 | `ai/<執行者>/UX-MATCHUP2` | ⚪ | 📥Backlog | —不適用 |
| [UX-RECORD1](tasks/UX-RECORD1.md) | `/records` 歷史重要性導向重製 | ruan6047 | Opus-4.8@ClaudeCode | 待指派 | `ai/opus-4.8/UX-RECORD1` | ⚪ | 🔍待查核 | ⏸未部署 |
| [ML-UMP1](tasks/ML-UMP1.md) | 好球帶判決差異研究 | ruan6047 | GPT-5@Codex | Fable-5@Claude Code | 已合併（`7585604`） | 🔴 | 📦已合併（07-16 複查 PASS；run-value 僅研究元件、WP／固定帶方向性產品 no-go，詳 [`results`](research/ML-UMP1_RESULTS.md)） | —不適用（離線研究） |
| [ML-UMP2](tasks/ML-UMP2.md) | 身高比例逐打者代理帶敏感度重跑 | ruan6047 | 待指派 | 待指派 | `ai/<執行者>/ML-UMP2` | 🔴 | 📥Backlog | —不適用 |
| [ML-PT3](tasks/ML-PT3.md) | 中職版球路品質指數 | ruan6047 | 待指派 | 待指派 | — | 🔴 | 📥Backlog | —不適用 |
| [ML-SIM1](../ml-sim1-spec.md) | 簡易勝負預測＋單一打席模擬 | ruan6047 | GPT-5@Codex | Fable-5@Claude Code | 已合併（`7dfa82f`） | 🔴 | 📦已合併（07-16 複查 PASS；七項 findings 全數 CLOSED，詳 [`review`](../ml-sim1-review.md)／[`plan`](../ml-sim1-plan.md)） | ⏸未部署 |
| [ML-SIM2](tasks/ML-SIM2.md) | 全場狀態模擬器 | ruan6047 | 待指派 | 待指派 | — | 🔴 | 📥Backlog | —不適用 |
| [TEAM-STYLE1](tasks/TEAM-STYLE1.md) | 球隊球風研究 | ruan6047 | 待指派 | 待指派 | — | 🔴 | 📥Backlog | —不適用 |

## 依賴與資源註記

- `MATCHUP-DATA1 → ML-MATCHUP1 → UX-MATCHUP1 → UX-MATCHUP2`；前兩卡為資料／統計紅線，未獨立查核不得啟動 UI 卡。
- `RECORD-DATA1 → RECORD-API1 → UX-RECORD1`；前兩卡已結案並封存，UX-RECORD1 正待獨立查核。
- `VENUE-DEFUNCT` 目前存在對應 worktree／分支，但 Ledger 仍是 Backlog；Coordinator 必須在下次 claim 前先對帳、確認是否為有效 lease，不能直接視為已派工。
- `ML-UMP1`（已合併）→ `ML-UMP2`：身高比例帶重跑完全複用 ML-UMP1 引擎與敏感度框架；方向性呈現（含「判決偏向哪隊」）以 ML-UMP2 翻轉測試為前置閘門。
- 2026-07-15 前的完整看板文字與已完成卡歷史已封存於 [`archive/TASKS_PRE_WF12.md`](archive/TASKS_PRE_WF12.md)。
