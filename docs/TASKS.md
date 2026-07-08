# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`

---

## Ledger 總表

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UI-1 | 深色模式 | 使用者 | 規劃AI(外部) | 待指派 → Sonnet | **Opus/跨家族** | `ai/…/ui-1` | ⚪ | ⏳待執行（獨立 sprint）|
| UI-2 | 運動風質感 | 使用者 | 規劃AI(外部) | 待指派 → Sonnet | Opus | `ai/…/ui-2` | ⚪ | ⏳待執行 |
| UI-3 | 微互動 | 使用者 | 規劃AI(外部) | 待指派 → Sonnet | Sonnet(異 session) | `ai/…/ui-3` | ⚪ | ⏳待執行 |
| UI-4 | 響應式 | 使用者 | 規劃AI(外部) | 待指派 → Sonnet | Opus(真機實測) | `ai/…/ui-4` | ⚪ | ⏳待執行 |
| UI-5 | 球員對比頁 + 好球帶 tooltip | 使用者 | 規劃AI(外部) | 待指派 → Opus | Opus | `ai/…/ui-5` | ⚪ | ↩退回（spec 修正後轉待執行）|

> 「待指派」＝使用者尚未派工。派工後把 model@tool 補實、狀態改 🔨。

---

## 進行中／待辦卡

### UI-1 深色模式 Dark Mode  〔⚪一般（但跨圖表色清查易錯）〕
- 需求：使用者　規劃：規劃AI(外部)　分支：`ai/<>/ui-1`
- 執行：待指派（建議 Sonnet）　查核：**Opus 或跨家族**（暗色下逐頁截圖驗收）
- 狀態：⏳待執行（建議獨立 sprint）　Commit：—
- 詳規與硬色清單見 [`UI_IMPLEMENTATION_CHECKLIST.md`](UI_IMPLEMENTATION_CHECKLIST.md) §1
- Log：
  - 07-08 規劃 by 規劃AI；稽核 by Claude-Opus-4.8 → ⚠️低估工作量（19 檔硬色）

### UI-2 運動風質感（Outfit 字型／毛玻璃／hover 隊色光暈）  〔⚪〕
- 需求：使用者　規劃：規劃AI(外部)　分支：`ai/<>/ui-2`
- 執行：待指派（建議 Sonnet）　查核：Opus（視覺驗收）
- 狀態：⏳待執行　Commit：—
- Log：07-08 規劃 by 規劃AI；稽核 by Claude-Opus → ✅前提正確可執行

### UI-3 微互動（勝率條伸展／滑桿觸感／View Transition）  〔⚪〕
- 需求：使用者　規劃：規劃AI(外部)　分支：`ai/<>/ui-3`
- 執行：待指派（建議 Sonnet）　查核：Sonnet（**異 session**）
- 狀態：⏳待執行　Commit：—
- Log：07-08 規劃 by 規劃AI；稽核 by Claude-Opus → ✅前提全對

### UI-4 響應式（sticky 首欄／月曆轉列表）  〔⚪〕
- 需求：使用者　規劃：規劃AI(外部)　分支：`ai/<>/ui-4`
- 執行：待指派（建議 Sonnet）　查核：Opus（**須真機 375px 實測**）
- 狀態：⏳待執行　Commit：—
- Log：07-08 規劃 by 規劃AI；稽核 by Claude-Opus → ✅前提正確

### UI-5 球員對比頁 + 好球帶 tooltip  〔⚪〕
- 需求：使用者　規劃：規劃AI(外部)　分支：`ai/<>/ui-5`
- 執行：待指派（建議 Opus：新路由+API 缺口+自繪 SVG）　查核：Opus
- 狀態：**↩退回 → spec 已修正 → 待重新規劃核可後轉 ⏳**　Commit：—
- Log：
  - 07-08 規劃 by 規劃AI
  - 07-08 稽核 by Claude-Opus-4.8 → ↩退回（`/api/players/search` 不存在、zone-scatter 非 Recharts 且 points 缺 rel_speed/spin_rate）；已於 checklist §5 修正

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
| UI 提案稽核 + AI 工作流建立 | `940bae4` | Claude-Opus | 使用者 pending | ⚪ |
