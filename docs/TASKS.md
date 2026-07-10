# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`

---

## Ledger 總表

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UI-1 | 深色模式 | ruan6047 | 規劃AI(外部) | 暫無 | **Opus/跨家族** | — | ⚪ | 📥Backlog（封存）|
| UI-2 | 運動風質感 | ruan6047 | 規劃AI(外部) | Antigravity@tool | Opus | `ai/antigravity/ui-2` | ⚪ | 🏁完成 |
| UI-3 | 微互動 | ruan6047 | 規劃AI(外部) | Antigravity@tool | Sonnet(異 session) | `ai/antigravity/ui-3` | ⚪ | 🏁完成 |
| UI-4 | 響應式 | ruan6047 | 規劃AI(外部) | Antigravity@tool | Fable-5@Claude Code(375px模擬) | `ai/antigravity/ui-4` | ⚪ | 🔨執行中(修復) |
| UI-5 | 球員對比頁 + 好球帶 tooltip | ruan6047 | 規劃AI(外部) | 暫無 | Opus | — | ⚪ | 📥Backlog（封存）|
| LIVE-1 | 賽況頁決勝資訊與中職紀錄強化 | ruan6047 | Claude Code(對話中逐步核可) | Opus-4.8+Fable-5@Claude Code | **ruan6047 人審(AI輔助)** | `ai/claude-code/game-live-records` | 🔴 | 🏁完成 |

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
- 狀態：🏁完成　Commit：`7f1a240`
- Log：
  - 07-08 規劃 by 規劃AI；稽核 by Claude-Opus → ✅前提正確可執行
  - 07-09 由 Antigravity 啟動執行並完成實作，提報審查
  - 07-09 使用者 ruan6047 驗收通過，合併至 main
  - 07-10 上線後複審 by Fable-5@Claude Code（生產實測）→ ✅維持通過：Outfit 已載入且 tnum 等寬生效（表格皆掛 tabular-nums；無 tnum 者僅單行戰績無對齊需求）；header blur(12px)+bg/80；hover 光暈實測 20% alpha + 0.3s（cssText 序列化會顯示無 color-mix，計算值正確——複審務必量 computed）；reduced-motion 全域涵蓋

### UI-3 微互動（勝率條伸展／滑桿觸感／View Transition）  〔⚪〕
- 需求：ruan6047　規劃：規劃AI(外部)　分支：`ai/antigravity/ui-3`
- 執行：Antigravity@tool　查核：Sonnet（**異 session**）
- 狀態：🏁完成　Commit：`eff10d1`
- Log：
  - 07-08 規劃 by 規劃AI；稽核 by Claude-Opus → ✅前提全對
  - 07-09 指派給 Antigravity，啟動執行並完成實作，提報審查
  - 07-09 使用者 ruan6047 驗收通過，合併至 main
  - 07-10 上線後複審 by Fable-5@Claude Code（生產實測）→ ✅維持通過：barGrow 0.8s+--target-width 正確；滑桿 hover/focus scale-y-125；View Transition 切換 mode/特徵群組實點無錯誤、佈局無塌陷、console 乾淨

### UI-4 響應式（sticky 首欄／月曆轉列表）  〔⚪〕
- 需求：ruan6047　規劃：規劃AI(外部)　分支：`ai/antigravity/ui-4`
- 執行：Antigravity@tool　查核：Opus（**須真機 375px 實測**）
- 狀態：↩退回　Commit：`b91f7ac`
- Log：
  - 07-08 規劃 by 規劃AI；稽核 by Claude-Opus → ✅前提正確
  - 07-09 指派給 Antigravity，啟動執行並完成實作，提報審查
  - 07-10 查核 by Fable-5@Claude Code（375px DevTools 模擬實測＋量測）→ ↩退回，缺陷報告：
    - 🔴 D1 戰績表 sticky 錨點錯位：`#` th 實寬 29px < 球隊欄 hardcode `left:2.5rem`(40px)，兩 sticky 欄間 11.1px 縫隙透出被捲欄位文字（table auto layout 下 `w-10` 不保證欄寬）。位置 `web/src/app/page.tsx:369-371`
    - 🟡 D2 表頭底色不一致：sticky th 為 `--color-surface`(白) vs thead `bg-surface-2`(灰)，桌機不捲動即可見白/灰拼接（量測 rgb(255,255,255) vs rgba(0,0,0,0) on surface-2）
    - 🟡 D3 hover 不一致：tr `hover:bg-surface-2` 時 sticky td 不透明白底不變色
    - ✅ 通過項：/games 月曆→列表全數（375px 無溢出、24 日卡、空狀態、今天標記、hasDetail 連結、桌機回歸）；sticky 釘住功能本體
    - 附註：查核以 DevTools 375px 模擬非真機；依鐵律#4 退回原執行者（Antigravity）同分支修，未代改
  - 07-10 ruan6047 派 Antigravity 修復 D1–D3（同分支），修畢重審

### UI-5 球員對比頁 + 好球帶 tooltip  〔⚪〕
- 需求：ruan6047　規劃：規劃AI(外部)　分支：—
- 執行：暫無　查核：Opus
- 狀態：📥Backlog（封存）　Commit：—
- Log：
  - 07-08 規劃 by 規劃AI
  - 07-08 稽核 by Claude-Opus-4.8 → ↩退回（`/api/players/search` 不存在、zone-scatter 非 Recharts 且 points 缺 rel_speed/spin_rate）；已於 checklist §5 修正
  - 07-09 依使用者指示封存此任務

### LIVE-1 賽況頁決勝資訊與中職紀錄強化  〔🔴紅線：破紀錄偵測＝資料正確性，錯了公開誤導〕
- 需求：ruan6047（session 內漸進四項：致勝打點入決勝列／焦點卡重排＋特殊紀錄獨立上色／決勝次數標注／中職史上紀錄偵測）
- 規劃：Claude Code 對話中即時規劃、使用者逐步核可　分支：`ai/claude-code/game-live-records`
- 執行：Opus-4.8＋Fable-5@Claude Code　查核：**ruan6047 人審（AI 輔助材料）**
- 狀態：🏁完成　Commit：`131556a`（merge）
- 範圍：API `decision_counts`（本季第N勝/敗/救援/中繼/MVP，box score 慣例含本場）＋ milestones 端點加史上紀錄（生涯累計 8 項，打破/追平/刷新，leakage-safe）；前端焦點卡重排（特殊紀錄區隊色、決勝 grid、刪冗餘標題）＋ 手機 grid 溢出修正
- 誠實邊界：單場型紀錄不做（gamelog 僅 2018+ 看不到早年）；單季紀錄未做（可做未擴）
- 驗證：ruff＋tsc 綠；API 實測 4 場（2022#3 打破290轟／2021#300 追平289／2025#313 刷新305＝使用者例／2026#154 回歸無誤報）；桌機+375px 截圖
- Log：
  - 07-10 執行完成（違規補記：初始誤在 ui-4 工作樹實作，未 commit 前已移植本分支；查核前流程已補正）
  - 07-10 提報 ruan6047 人審
  - 07-10 ruan6047 人審通過（實測+視覺驗收），合併至 main（`131556a`）並部署

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
