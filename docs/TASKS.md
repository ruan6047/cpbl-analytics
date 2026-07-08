# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`

---

## Ledger 總表

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UI-1 | 深色模式 | ruan6047 | 規劃AI(外部) | 暫無 | **Opus/跨家族** | — | ⚪ | 📥Backlog（封存）|
| UI-2 | 運動風質感 | ruan6047 | 規劃AI(外部) | Antigravity@tool | Opus | `ai/antigravity/ui-2` | ⚪ | 🔍待查核 |
| UI-3 | 微互動 | ruan6047 | 規劃AI(外部) | Antigravity@tool | Sonnet(異 session) | `ai/antigravity/ui-3` | ⚪ | 🔍待查核 |
| UI-4 | 響應式 | ruan6047 | 規劃AI(外部) | Antigravity@tool | Opus(真機實測) | `ai/antigravity/ui-4` | ⚪ | 🔨執行中 |
| UI-5 | 球員對比頁 + 好球帶 tooltip | ruan6047 | 規劃AI(外部) | 暫無 | Opus | — | ⚪ | 📥Backlog（封存）|

> 「待指派」＝ruan6047尚未派工。派工後把 model@tool 補實、狀態改 🔨。

---

## 進行中／待辦卡

### UI-1 深色模式 Dark Mode  〔⚪一般（但跨圖表色清查易錯）〕
- 需求：ruan6047　規劃：規劃AI(外部)　分支：—
- 執行：暫無　查核：**Opus 或跨家族**（暗色下逐頁截圖驗收）
- 狀態：📥Backlog（封存）　Commit：—
- 詳規與硬色清單見 [`UI_IMPLEMENTATION_CHECKLIST.md`](UI_IMPLEMENTATION_CHECKLIST.md) §1
- Log：
  - 07-08 規劃 by 規劃AI；稽核 by Claude-Opus-4.8 → ⚠️低估工作量（19 檔硬色）
  - 07-09 依使用者指示封存此任務

### UI-2 運動風質感（Outfit 字型／毛玻璃／hover 隊色光暈）  〔⚪〕
- 需求：ruan6047　規劃：規劃AI(外部)　分支：`ai/antigravity/ui-2`
- 執行：Antigravity@tool　查核：Opus（視覺驗收）
- 狀態：🔍待查核　Commit：`7f1a240`
- Log：
  - 07-08 規劃 by 規劃AI；稽核 by Claude-Opus → ✅前提正確可執行
  - 07-09 由 Antigravity 啟動執行並完成實作，提報審查

### UI-3 微互動（勝率條伸展／滑桿觸感／View Transition）  〔⚪〕
- 需求：ruan6047　規劃：規劃AI(外部)　分支：`ai/antigravity/ui-3`
- 執行：Antigravity@tool　查核：Sonnet（**異 session**）
- 狀態：🔍待查核　Commit：`eff10d1`
- Log：
  - 07-08 規劃 by 規劃AI；稽核 by Claude-Opus → ✅前提全對
  - 07-09 指派給 Antigravity，啟動執行並完成實作，提報審查

### UI-4 響應式（sticky 首欄／月曆轉列表）  〔⚪〕
- 需求：ruan6047　規劃：規劃AI(外部)　分支：`ai/antigravity/ui-4`
- 執行：Antigravity@tool　查核：Opus（**須真機 375px 實測**）
- 狀態：🔨執行中　Commit：—
- Log：
  - 07-08 規劃 by 規劃AI；稽核 by Claude-Opus → ✅前提正確
  - 07-09 指派給 Antigravity，啟動執行

### UI-5 球員對比頁 + 好球帶 tooltip  〔⚪〕
- 需求：ruan6047　規劃：規劃AI(外部)　分支：—
- 執行：暫無　查核：Opus
- 狀態：📥Backlog（封存）　Commit：—
- Log：
  - 07-08 規劃 by 規劃AI
  - 07-08 稽核 by Claude-Opus-4.8 → ↩退回（`/api/players/search` 不存在、zone-scatter 非 Recharts 且 points 缺 rel_speed/spin_rate）；已於 checklist §5 修正
  - 07-09 依使用者指示封存此任務

---

## 🏁 已完成（本 session）

> ⚠️ 以下均在**工作流建立前**由 Claude-Opus-4.8 直接於 `main` 實作並自驗（無獨立審核／未走分支）。列此為 log 補記；**今後一律走分支 + 獨立審核**。

| 功能 | Commit | 執行 | 查核 | 紅線 |
|---|---|---|---|---|
| 球種分類引擎（軌跡→KMeans）| `215cc87` | Claude-Opus | 自驗（羅戈基準/94%一致率/實測）| 🔴 |
| 好球帶卡改推算球種 + 廣播選手卡 | `d5155b0` | Claude-Opus | 自驗（截圖）| ⚪ |
| 球員頁球種細分（arsenal/mix/鏡頭）| `a7dd350` | Claude-Opus | 自驗（截圖）| ⚪ |
| 本場焦點隊伍上色 | `047dafd` | Claude-Opus | 自驗（DOM 色驗證）| ⚪ |
| 中繼移除「推算」標注 | `ce2d28b` | Claude-Opus | 自驗 | ⚪ |
| 球種分類「整場完整」gate | `80c98ad` | Claude-Opus | 自驗（skip 統計）| 🔴 |
| 今日資料爬取＋分類＋同步生產 | (無碼/資料操作) | Claude-Opus | 生產驗證 | ⚪ |
| UI 提案稽核 + AI 工作流建立 | `940bae4` | Claude-Opus | ruan6047 pending | ⚪ |
