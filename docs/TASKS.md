# 任務看板（cpbl-analytics）

> 規則見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) 與本專案 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。git 是程式碼／文件事實來源；[`control-plane event log`](control-plane/events.jsonl) 是作業狀態事實來源；本檔是它的 current-state projection。
> **不可手動修改表格**：以 `uv run python scripts/workflow_ledger.py --write` 重建；`--check` 驗證投影未漂移。每張卡的範圍與歷史 Log 位於 [`tasks/`](tasks/)；結案後移至 [`archive/tasks/`](archive/tasks/)，索引列移至 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)。

## Ledger 總表（活卡）

| 卡ID | Initiative | 級別 | 功能 | owner | 分支／worktree | iteration | 交付狀態 | 部署狀態 | 最後交接 |
|---|---|---|---|---|---|---|---|---|---|
| [API-DAILY-SUMMARY1](tasks/API-DAILY-SUMMARY1.md) | INIT-PRODUCT-UX | T3 | 最近比賽日與下一批賽事聚合契約 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:26+08:00 |
| [DATA-EDITORIAL1](tasks/DATA-EDITORIAL1.md) | INIT-PRODUCT-UX | T4 | Google Sheet 編輯資料管道 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:37+08:00 |
| [DEP-PREDICT-LEGACY1](tasks/DEP-PREDICT-LEGACY1.md) | INIT-PRODUCT-UX | T3 | 舊預測體驗退場 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:29+08:00 |
| [DOC-GAME-RECAP1](tasks/DOC-GAME-RECAP1.md) | INIT-GAME-RECAP | T3 | 賽事復盤產品規格獨立查核 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T22:15:04+08:00 |
| [GAME-RECAP-DATA1](tasks/GAME-RECAP-DATA1.md) | INIT-GAME-RECAP | T4 | 賽事復盤資料覆蓋與 canonical 契約稽核 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T22:15:05+08:00 |
| [GAME-RECAP-PA1](tasks/GAME-RECAP-PA1.md) | INIT-GAME-RECAP | T4 | canonical 打席與逐球可靠對應 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:06+08:00 |
| [GAME-RECAP-STATUS1](tasks/GAME-RECAP-STATUS1.md) | INIT-GAME-RECAP | T4 | 賽事狀態、資料可用性與 freshness API | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:07+08:00 |
| [GAME-RECAP-WP-API1](tasks/GAME-RECAP-WP-API1.md) | INIT-GAME-RECAP | T4 | canonical WP／WPA public contract | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:09+08:00 |
| [GAME-RECAP-WP-VAL1](tasks/GAME-RECAP-WP-VAL1.md) | INIT-GAME-RECAP | T4 | 場中 WP 時間外驗證與支援邊界 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T22:15:08+08:00 |
| [INIT-GAME-RECAP](tasks/INIT-GAME-RECAP.md) | INIT-GAME-RECAP | T4 | 隔日賽事脈絡與逐打席復盤 | ruan6047（Design Gate） | — | 0 | 💡需求 | —不適用 | 2026-07-17T04:44:38+08:00 |
| [INIT-PRODUCT-UX](tasks/INIT-PRODUCT-UX.md) | INIT-PRODUCT-UX | T3 | 全站產品與 UI/UX 收斂 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-17T04:44:24+08:00 |
| [ML-PT3](tasks/ML-PT3.md) | — | T4 | 中職版球路品質指數 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [ML-SIM2](tasks/ML-SIM2.md) | — | T4 | 全場狀態模擬器 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [OPS-REFRESH1](tasks/OPS-REFRESH1.md) | INIT-PRODUCT-UX | T4 | 白天自動刷新與失敗快篩 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:27+08:00 |
| [TEAM-STYLE1](tasks/TEAM-STYLE1.md) | — | T4 | 球隊球風研究 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T12:30:00+08:00 |
| [UX-GAME-HOME1](tasks/UX-GAME-HOME1.md) | INIT-GAME-RECAP | T3 | 最近比賽日與下一批賽事首頁 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:39+08:00 |
| [UX-GAME-PA1](tasks/UX-GAME-PA1.md) | INIT-GAME-RECAP | T3 | 逐打席與逐球脈絡探索器 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:11+08:00 |
| [UX-GAME-RECAP1](tasks/UX-GAME-RECAP1.md) | INIT-GAME-RECAP | T3 | 結論先行的單場賽後復盤 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:40+08:00 |
| [UX-MATCHUP1](tasks/UX-MATCHUP1.md) | INIT-PRODUCT-UX | T4 | /matchups 查詢式頁面重製 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:42+08:00 |
| [UX-MATCHUP2](tasks/UX-MATCHUP2.md) | INIT-PRODUCT-UX | T4 | 投打對決整合球員個人頁 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:43+08:00 |
| [UX-MODEL-METHOD1](tasks/UX-MODEL-METHOD1.md) | INIT-PRODUCT-UX | T3 | 模型方法與限制頁 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:28+08:00 |
| [UX-NAV-IA1](tasks/UX-NAV-IA1.md) | INIT-PRODUCT-UX | T3 | 方案 B 導覽與全域球員搜尋 | ruan6047（release） | `ai/opus-4-8/UX-NAV-IA1 @ .claude/worktrees/ux-nav-ia1-execution-08c218` | 2 | 📦已合併 | ⏸未部署 | 2026-07-17T12:57:09+08:00 |
| [UX-OUTCOME-HOME](tasks/UX-OUTCOME-HOME.md) | INIT-PRODUCT-UX | T4 | 可嵌入賽前勝率卡 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:41+08:00 |
| [UX-PA-SIM-MATCHUP1](tasks/UX-PA-SIM-MATCHUP1.md) | INIT-PRODUCT-UX | T4 | Matchups 單一打席結果分布 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:33+08:00 |
| [UX-PLAYER-IA1](tasks/UX-PLAYER-IA1.md) | INIT-PRODUCT-UX | T3 | 球員頁 IA 骨架與 prototype 決策 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-17T04:44:31+08:00 |
| [UX-PLAYER-SECTIONS1](tasks/UX-PLAYER-SECTIONS1.md) | INIT-PRODUCT-UX | T3 | 球員頁分區內容遷移 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:32+08:00 |
| [UX-RANKINGS1](tasks/UX-RANKINGS1.md) | INIT-PRODUCT-UX | T3 | 打者與投手排行減法 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:30+08:00 |
| [UX-STANDINGS-FOCUS1](tasks/UX-STANDINGS-FOCUS1.md) | INIT-PRODUCT-UX | T3 | 戰績頁競爭脈絡收斂 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:34+08:00 |
| [UX-TEAM-FOCUS1](tasks/UX-TEAM-FOCUS1.md) | INIT-PRODUCT-UX | T3 | 球隊頁本季現況優先 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:35+08:00 |
| [UX-UMPIRE-SCOPE1](tasks/UX-UMPIRE-SCOPE1.md) | INIT-PRODUCT-UX | T4 | 裁判公開介面 NO-GO 收斂 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:36+08:00 |

## 依賴與資源註記

- `MATCHUP-DATA1 → ML-MATCHUP1 → UX-MATCHUP1` 前置已解除；之後分流至 `UX-PA-SIM-MATCHUP1`，或待 `UX-PLAYER-SECTIONS1` 後進 `UX-MATCHUP2`。
- `RECORD-DATA1 → RECORD-API1 → UX-RECORD1` 已全數結案；UX-RECORD1 已部署並封存。
- `ML-UMP1 → ML-UMP2` 已結案封存，方向性裁判／球隊產品維持 NO-GO；`UX-UMPIRE-SCOPE1` 只負責移除排行與收斂中性介面。
- `ML-SIM1` 已完成跨家族複查、合併與 production 驗證；`UX-OUTCOME-HOME` 只交付 PregameCard，首頁唯一 owner 為 `UX-GAME-HOME1`。
- `INIT-GAME-RECAP` 的資料紅線主鏈維持 `GAME-RECAP-DATA1 → GAME-RECAP-PA1 → GAME-RECAP-WP-VAL1 → GAME-RECAP-WP-API1 → UX-GAME-RECAP1 → UX-GAME-PA1`；首頁 v1 另走 `API-DAILY-SUMMARY1 + UX-OUTCOME-HOME → UX-GAME-HOME1`，不依賴 WPA。
- `INIT-PRODUCT-UX` 建議波次：刷新／IA／daily API／PregameCard → 首頁／方法頁 → 舊 predict 退場；球員 IA 與 Matchups 可在不同資源上平行。
- 升級前歷史仍封存於 [`archive/TASKS_PRE_WF12.md`](archive/TASKS_PRE_WF12.md)，不得為新格式回寫。
