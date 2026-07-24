# 任務看板（cpbl-analytics）

> 規則見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) 與本專案 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。git 是程式碼／文件事實來源；[`control-plane event log`](control-plane/events.jsonl) 是作業狀態事實來源；本檔是它的 current-state projection。
> **不可手動修改表格**：以 `uv run python scripts/workflow_ledger.py --write` 重建；`--check` 驗證投影未漂移。每張卡的範圍與歷史 Log 位於 [`tasks/`](tasks/)；結案後移至 [`archive/tasks/`](archive/tasks/)，索引列移至 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)。
> **本表即當前狀態**：lifecycle 事件一律直接 commit 至 main 並同 commit 重建本檔（[`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)）；執行分支不得改動 control-plane 與本檔。`--live` 可稽核是否有事件違規漏留在分支。

## Ledger 總表（活卡）

| 卡ID | Initiative | 級別 | 功能 | owner | 分支／worktree | iteration | 交付狀態 | 部署狀態 | 最後交接 |
|---|---|---|---|---|---|---|---|---|---|
| [DISCOVERY-CPBL-RECORDS1](tasks/DISCOVERY-CPBL-RECORDS1.md) | INIT-OFFICIAL-DATA1 | T3 | 主站紀錄資料價值與穩定鍵 Discovery | — | `claude/discovery-cpbl-records1-b1ce2d @ .claude/worktrees/discovery-cpbl-records1-b1ce2d` | 1 | 📦已合併 | —不適用 | 2026-07-24T12:40:00+08:00 |
| [GAME-RECAP-PA1](tasks/GAME-RECAP-PA1.md) | INIT-GAME-RECAP | T4 | canonical PA 契約與實作切卡 | ruan6047（子卡優先序／後續 Gate） | — | 1 | 📦已合併 | —不適用 | 2026-07-21T01:09:45+08:00 |
| [GAME-RECAP-PA1-BUILD1](tasks/GAME-RECAP-PA1-BUILD1.md) | INIT-GAME-RECAP | T4 | canonical PA builder、對帳與歷史回填 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-22T16:51:12+08:00 |
| [GAME-RECAP-PA1-EXPAND1](tasks/GAME-RECAP-PA1-EXPAND1.md) | INIT-GAME-RECAP | T4 | canonical PA additive schema expand | — | `ai/opus-4-8/GAME-RECAP-PA1-EXPAND1 @ .claude/worktrees/game-recap-pa1-expand1-execution` | 1 | 📦已合併 | ✅已驗證 | 2026-07-24T13:46:00+08:00 |
| [GAME-RECAP-PA1-TAXONOMY1](tasks/GAME-RECAP-PA1-TAXONOMY1.md) | INIT-GAME-RECAP | T4 | canonical PA transition taxonomy 稽核 | — | `ai/opus-4-8/GAME-RECAP-PA1-TAXONOMY1 @ .claude/worktrees/game-recap-pa1-taxonomy1-execution` | 1 | 📦已合併 | —不適用 | 2026-07-24T11:25:22+08:00 |
| [GAME-RECAP-WP-API1](tasks/GAME-RECAP-WP-API1.md) | INIT-GAME-RECAP | T4 | canonical WP／WPA public contract | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-16T22:15:09+08:00 |
| [GAME-RECAP-WP-VAL1](tasks/GAME-RECAP-WP-VAL1.md) | INIT-GAME-RECAP | T4 | 場中 WP 時間外驗證與支援邊界 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-16T22:15:08+08:00 |
| [INGEST-GAME-TM-REFACTOR1](tasks/INGEST-GAME-TM-REFACTOR1.md) | INIT-OFFICIAL-DATA1 | T4 | 重構逐球爬蟲改以單場 API 為單位 | — | `ai/sonnet-5/INGEST-GAME-TM-REFACTOR1-g3 @ .claude/worktrees/ingest-game-tm-refactor1-g3-execution` | 2 | 📦已合併 | ⏸未部署 | 2026-07-24T12:53:42+08:00 |
| [INGEST-RECORDS-HR1](tasks/INGEST-RECORDS-HR1.md) | INIT-OFFICIAL-DATA1 | T4 | 官網 /stats/hr 逐轟里程碑入庫 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-24T12:10:00+08:00 |
| [INIT-GAME-RECAP](tasks/INIT-GAME-RECAP.md) | INIT-GAME-RECAP | T4 | 隔日賽事脈絡與逐打席復盤 | ruan6047（Design Gate） | — | 0 | 💡需求 | —不適用 | 2026-07-17T04:44:38+08:00 |
| [INIT-OFFICIAL-DATA1](tasks/INIT-OFFICIAL-DATA1.md) | INIT-OFFICIAL-DATA1 | T4 | 官方資料契約完整性與低維護 ingest | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-22T16:51:00+08:00 |
| [INIT-PRODUCT-UX](tasks/INIT-PRODUCT-UX.md) | INIT-PRODUCT-UX | T3 | 全站產品與 UI/UX 收斂 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-17T04:44:24+08:00 |
| [MATCHUP-DATA2](tasks/MATCHUP-DATA2.md) | — | T4 | 對戰對手歷史隊別歸屬修正 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-22T03:16:09+08:00 |
| [ML-FIELD-LINEUP1](tasks/ML-FIELD-LINEUP1.md) | INIT-OFFICIAL-DATA1 | T4 | 逐局守備陣容重建可行性與 canonical contract | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-22T16:51:03+08:00 |
| [ML-FIELD-OAA-VAL1](tasks/ML-FIELD-OAA-VAL1.md) | INIT-OFFICIAL-DATA1 | T4 | 利用極座標落點還原 Spray Chart 與外野 OAA | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-22T16:51:07+08:00 |
| [ML-FIELD-OF1](tasks/ML-FIELD-OF1.md) | — | T4 | 外野空中球守備範圍指標 | ruan6047（Design Gate） | — | 0 | 💡需求 | ⏸未部署 | 2026-07-22T16:51:08+08:00 |
| [ML-PT3](tasks/ML-PT3.md) | — | T4 | 中職版球路品質指數 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-22T16:51:09+08:00 |
| [ML-SIM2](tasks/ML-SIM2.md) | — | T4 | 全場狀態模擬器 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-22T16:51:10+08:00 |
| [OPS-CPBL-WEB-HEALTH1](tasks/OPS-CPBL-WEB-HEALTH1.md) | INIT-PRODUCT-UX | T3 | CPBL Web container healthcheck 與可寫快取修復 | 待指派（委託其他 AI） | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-23T06:56:15+08:00 |
| [OPS-REMOTE-CUTOVER1](tasks/OPS-REMOTE-CUTOVER1.md) | INIT-PRODUCT-UX | T4 | 遠端 crawler production canary 與切換 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-18T19:15:40+08:00 |
| [OPS-REMOTE-PROBE1](tasks/OPS-REMOTE-PROBE1.md) | INIT-PRODUCT-UX | T3 | Opt-in DEBUG 網路探測介面 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-18T19:15:37+08:00 |
| [OPS-REMOTE-ROUTE1](tasks/OPS-REMOTE-ROUTE1.md) | INIT-PRODUCT-UX | T3 | 遠端出口路線資格驗證 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-18T19:15:38+08:00 |
| [OPS-REMOTE-WORKER1](tasks/OPS-REMOTE-WORKER1.md) | INIT-PRODUCT-UX | T4 | 隔離式遠端 crawler shadow worker | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-18T19:15:39+08:00 |
| [TEAM-STYLE1](tasks/TEAM-STYLE1.md) | — | T4 | 球隊球風研究 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-22T16:56:00+08:00 |
| [UX-GAME-PA1](tasks/UX-GAME-PA1.md) | INIT-GAME-RECAP | T3 | 逐打席與逐球脈絡探索器 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-22T16:51:11+08:00 |
| [UX-GAME-RECAP1](tasks/UX-GAME-RECAP1.md) | INIT-GAME-RECAP | T3 | 結論先行的單場賽後復盤 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:40+08:00 |
| [UX-PA-SIM-MATCHUP1](tasks/UX-PA-SIM-MATCHUP1.md) | INIT-PRODUCT-UX | T4 | Matchups 單一打席結果分布 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:33+08:00 |
| [UX-TEAM-SPLIT-SCOPE1](tasks/UX-TEAM-SPLIT-SCOPE1.md) | INIT-PRODUCT-UX | T4 | 球隊頁全年／上下半季數據切換 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-22T00:40:22+08:00 |
| [UX-UMPIRE-SCOPE1](tasks/UX-UMPIRE-SCOPE1.md) | INIT-PRODUCT-UX | T4 | 裁判公開介面 NO-GO 收斂 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:36+08:00 |

## 依賴與資源註記

- `MATCHUP-DATA1 → ML-MATCHUP1 → UX-MATCHUP1` 前置已解除；之後分流至 `UX-PA-SIM-MATCHUP1`，或待 `UX-PLAYER-SECTIONS1` 後進 `UX-MATCHUP2`。
- `RECORD-DATA1 → RECORD-API1 → UX-RECORD1` 已全數結案；UX-RECORD1 已部署並封存。
- `ML-UMP1 → ML-UMP2` 已結案封存，方向性裁判／球隊產品維持 NO-GO；`UX-UMPIRE-SCOPE1` 只負責移除排行與收斂中性介面。
- `ML-SIM1` 已完成跨家族複查、合併與 production 驗證；`UX-OUTCOME-HOME` 只交付 PregameCard，首頁唯一 owner 為 `UX-GAME-HOME1`。
- `INIT-GAME-RECAP` 的資料紅線主鏈維持 `GAME-RECAP-DATA1 → GAME-RECAP-PA1 → GAME-RECAP-WP-VAL1 → GAME-RECAP-WP-API1 → UX-GAME-RECAP1 → UX-GAME-PA1`；首頁 v1 另走 `API-DAILY-SUMMARY1 + UX-OUTCOME-HOME → UX-GAME-HOME1`，不依賴 WPA。
- `INIT-PRODUCT-UX` 建議波次：刷新／IA／daily API／PregameCard → 首頁／方法頁 → 舊 predict 退場；球員 IA 與 Matchups 可在不同資源上平行。
- 升級前歷史仍封存於 [`archive/TASKS_PRE_WF12.md`](archive/TASKS_PRE_WF12.md)，不得為新格式回寫。
