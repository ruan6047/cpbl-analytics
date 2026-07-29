# 任務看板（cpbl-analytics）

> 規則見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) 與本專案 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。git 是程式碼／文件事實來源；[`control-plane event log`](control-plane/events.jsonl) 是作業狀態事實來源；本檔是它的 current-state projection。
> **不可手動修改表格**：以 `uv run python scripts/workflow_ledger.py --write` 重建；`--check` 驗證投影未漂移。每張卡的範圍與歷史 Log 位於 [`tasks/`](tasks/)；結案後移至 [`archive/tasks/`](archive/tasks/)，索引列移至 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)。
> **本表即當前狀態**：lifecycle 事件一律直接 commit 至 main 並同 commit 重建本檔（[`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)）；執行分支不得改動 control-plane 與本檔。`--live` 可稽核是否有事件違規漏留在分支。

## Ledger 總表（活卡）

| 卡ID | Initiative | 級別 | 功能 | owner | 分支／worktree | iteration | 交付狀態 | 部署狀態 | 最後交接 |
|---|---|---|---|---|---|---|---|---|---|
| [DEV-TRAILER-GUARD-SCOPE1](tasks/DEV-TRAILER-GUARD-SCOPE1.md) | — | T2 | trailer 守衛取樣範圍 | Claude Sonnet 5@Claude Code | `ai/sonnet-5/DEV-TRAILER-GUARD-SCOPE1 @ .claude/worktrees/dev-trailer-guard-scope1-execution` | 1 | 🔍待查核 | —不適用 | 2026-07-29T12:15:00+08:00 |
| [DEV-VERIFY-TM-ASSERTS1](tasks/DEV-VERIFY-TM-ASSERTS1.md) | — | T2 | TM 回填驗證腳本補上真正的斷言 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-29T12:14:00+08:00 |
| [INGEST-GAME-TM-REFACTOR1](tasks/INGEST-GAME-TM-REFACTOR1.md) | INIT-OFFICIAL-DATA1 | T4 | 重構逐球爬蟲改以單場 API 為單位 | — | `ai/sonnet-5/INGEST-GAME-TM-REFACTOR1-g3 @ .claude/worktrees/ingest-game-tm-refactor1-g3-execution` | 2 | 📦已合併 | ⏸未部署 | 2026-07-24T12:53:42+08:00 |
| [INGEST-PA-DAILY1](tasks/INGEST-PA-DAILY1.md) | — | T3 | canonical PA build 接進每日 refresh 鏈 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-26T20:55:46+08:00 |
| [INGEST-PLAYER-BIO-GAP1](tasks/INGEST-PLAYER-BIO-GAP1.md) | INIT-OFFICIAL-DATA1 | T3 | 補齊 14 位球員的 country／birthday | Claude Opus 5@Claude Code | `ai/opus-5/INGEST-PLAYER-BIO-GAP1 @ .claude/worktrees/ingest-player-bio-gap1-execution` | 3 | ⏸阻塞 | ⏸未部署 | 2026-07-28T11:50:08+08:00 |
| [INGEST-SPLITS-PA-SPLIT1](tasks/INGEST-SPLITS-PA-SPLIT1.md) | INIT-OFFICIAL-DATA1 | T4 | 查證分項重算是否同樣重複計打席 | Claude Fable 5@Claude Code（真 Fable 5） | `ai/fable-5/INGEST-SPLITS-PA-SPLIT1 @ .claude/worktrees/fable-5-suitable-tasks-8aa8d9` | 1 | 🔍待查核 | —不適用 | 2026-07-29T13:14:47+08:00 |
| [INIT-GAME-RECAP](tasks/INIT-GAME-RECAP.md) | INIT-GAME-RECAP | T4 | 隔日賽事脈絡與逐打席復盤 | 子卡依 v1.3 藍圖推進 | — | 0 | 📥Backlog | —不適用 | 2026-07-27T18:14:24+08:00 |
| [INIT-OFFICIAL-DATA1](tasks/INIT-OFFICIAL-DATA1.md) | INIT-OFFICIAL-DATA1 | T4 | 官方資料契約完整性與低維護 ingest | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-22T16:51:00+08:00 |
| [INIT-PRODUCT-UX](tasks/INIT-PRODUCT-UX.md) | INIT-PRODUCT-UX | T3 | 全站產品與 UI/UX 收斂 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-17T04:44:24+08:00 |
| [LIVE-GAME-BACKEND1](tasks/LIVE-GAME-BACKEND1.md) | INIT-OFFICIAL-DATA1 | T4 | 賽前情報與比賽中 live backend | GPT-5.6@Codex（執行；等待官方時序觀測） | `ai/codex/LIVE-GAME-BACKEND1 @ .claude/worktrees/live-game-backend1-execution` | 1 | 🔨執行中 | ⏸未部署 | 2026-07-26T21:09:11+08:00 |
| [MATCHUP-DATA2](tasks/MATCHUP-DATA2.md) | — | T4 | 對戰對手歷史隊別歸屬修正 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-22T03:16:09+08:00 |
| [ML-FIELD-LINEUP1](tasks/ML-FIELD-LINEUP1.md) | INIT-OFFICIAL-DATA1 | T4 | 逐局守備陣容重建可行性與 canonical contract | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-22T16:51:03+08:00 |
| [ML-FIELD-OAA-VAL1](tasks/ML-FIELD-OAA-VAL1.md) | INIT-OFFICIAL-DATA1 | T4 | 利用極座標落點還原 Spray Chart 與外野 OAA | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-22T16:51:07+08:00 |
| [ML-FIELD-OF1](tasks/ML-FIELD-OF1.md) | — | T4 | 外野空中球守備範圍指標 | ruan6047（Design Gate） | — | 0 | 💡需求 | ⏸未部署 | 2026-07-22T16:51:08+08:00 |
| [ML-PA-SIM-CONTEXT1](tasks/ML-PA-SIM-CONTEXT1.md) | — | T4 | 打席結果分布的情境條件化 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-25T19:06:00+08:00 |
| [ML-PA-SIM-TEAM1](tasks/ML-PA-SIM-TEAM1.md) | — | T4 | 打席模擬對某一隊 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-25T19:07:00+08:00 |
| [ML-PT3](tasks/ML-PT3.md) | — | T4 | 中職版球路品質指數 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-22T16:51:09+08:00 |
| [ML-SIM2](tasks/ML-SIM2.md) | — | T4 | 全場狀態模擬器 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-22T16:51:10+08:00 |
| [OPS-BACKUP-EMPTY1](tasks/OPS-BACKUP-EMPTY1.md) | — | T3 | 生產每日備份長期產出空檔 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-29T13:55:00+08:00 |
| [OPS-LIVE-SHADOW1](tasks/OPS-LIVE-SHADOW1.md) | — | T4 | VPS 隔離 live source observer | ruan6047（7/30 evidence 對帳／撤除待辦） | `ai/codex/OPS-LIVE-SHADOW1 @ .claude/worktrees/ops-live-shadow1-execution（保留至 evidence 對帳／撤除後結案）` | 1 | 📦已合併 | ✅已驗證 | 2026-07-26T23:11:01+08:00 |
| [OPS-REMOTE-CUTOVER1](tasks/OPS-REMOTE-CUTOVER1.md) | INIT-PRODUCT-UX | T4 | 遠端 crawler production canary 與切換 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-18T19:15:40+08:00 |
| [OPS-REMOTE-PROBE1](tasks/OPS-REMOTE-PROBE1.md) | INIT-PRODUCT-UX | T3 | Opt-in DEBUG 網路探測介面 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-18T19:15:37+08:00 |
| [OPS-REMOTE-ROUTE1](tasks/OPS-REMOTE-ROUTE1.md) | INIT-PRODUCT-UX | T3 | 遠端出口路線資格驗證 | 待指派 | — | 0 | 📥Backlog | —不適用 | 2026-07-18T19:15:38+08:00 |
| [OPS-REMOTE-WORKER1](tasks/OPS-REMOTE-WORKER1.md) | INIT-PRODUCT-UX | T4 | 隔離式遠端 crawler shadow worker | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-18T19:15:39+08:00 |
| [UX-ENTITY-LINKS2](tasks/UX-ENTITY-LINKS2.md) | INIT-PRODUCT-UX | T2 | 實體連結 pattern 普及化（整塊 hover:underline → ENTITY_LINK） | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-25T00:59:21+08:00 |
| [UX-GAME-PA1](tasks/UX-GAME-PA1.md) | INIT-GAME-RECAP | T3 | 逐打席與逐球脈絡探索器 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-22T16:51:11+08:00 |
| [UX-GAME-RECAP1](tasks/UX-GAME-RECAP1.md) | INIT-GAME-RECAP | T3 | 結論先行的單場賽後復盤 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-17T04:44:40+08:00 |
| [UX-LIVE-GAME1](tasks/UX-LIVE-GAME1.md) | INIT-PRODUCT-UX | T3 | 賽前情報到比賽中狀態板 | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-26T17:29:31+08:00 |
| [UX-TEAM-FIELD-HIST1](tasks/UX-TEAM-FIELD-HIST1.md) | INIT-PRODUCT-UX | T3 | 球隊頁歷史年守備位置圖（union fielding_seasons） | 待指派 | — | 0 | 📥Backlog | ⏸未部署 | 2026-07-25T02:36:00+08:00 |

## 依賴與資源註記

- `MATCHUP-DATA1 → ML-MATCHUP1 → UX-MATCHUP1` 前置已解除；之後分流至 `UX-PA-SIM-MATCHUP1`，或待 `UX-PLAYER-SECTIONS1` 後進 `UX-MATCHUP2`。
- `RECORD-DATA1 → RECORD-API1 → UX-RECORD1` 已全數結案；UX-RECORD1 已部署並封存。
- `ML-UMP1 → ML-UMP2` 已結案封存，方向性裁判／球隊產品維持 NO-GO；`UX-UMPIRE-SCOPE1` 只負責移除排行與收斂中性介面。
- `ML-SIM1` 已完成跨家族複查、合併與 production 驗證；`UX-OUTCOME-HOME` 只交付 PregameCard，首頁唯一 owner 為 `UX-GAME-HOME1`。
- `INIT-GAME-RECAP` 的資料紅線主鏈：`GAME-RECAP-DATA1 ✅ → GAME-RECAP-PA1 ✅ → GAME-RECAP-WP-VAL1 ✅（全 scope unsupported）→ GAME-RECAP-WP-CAL1 🏁（事後校準 No-Go）→ GAME-RECAP-WP-STRENGTH1 🏁（No-Go：八項凍結賽前特徵時間外無增量資訊，p0 相對主場常數僅 −0.0009 且兩季為負；merge 198ad87）→ GAME-RECAP-WP-API1 🏁✅（2026-07-27 需求方定位改寫 canonical→參考資訊＋揭露〔T3〕解阻塞，`/recap-wp` 已上線並帶 `wp_reliability` 揭露；統計改善鏈封存為升級路徑，未來 scope 通過原 v2 門檻只翻升 reliability、consumer 無 breaking change）→ UX-GAME-RECAP1 → UX-GAME-PA1（WP 契約阻塞已解除）`；首頁 v1 另走 `API-DAILY-SUMMARY1 + UX-OUTCOME-HOME → UX-GAME-HOME1`，不依賴 WPA。
- `INIT-PRODUCT-UX` 建議波次：刷新／IA／daily API／PregameCard → 首頁／方法頁 → 舊 predict 退場；球員 IA 與 Matchups 可在不同資源上平行。
- 升級前歷史仍封存於 [`archive/TASKS_PRE_WF12.md`](archive/TASKS_PRE_WF12.md)，不得為新格式回寫。
