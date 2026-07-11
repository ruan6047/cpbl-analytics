# 任務看板封存 (Archived Cards)

> 已完成（🏁）與封存（📥）的卡片移到此處，讓 [`../TASKS.md`](../TASKS.md) 只留活卡（省 AI 讀取算力）。
> **git commit trailer 仍為單一事實來源**；本檔為歷史總覽。規格文件同在本目錄
> （[`UI_IMPLEMENTATION_CHECKLIST.md`](UI_IMPLEMENTATION_CHECKLIST.md)、[`UI_IMPROVEMENT_PROPOSALS.md`](UI_IMPROVEMENT_PROPOSALS.md)、[`PITCH_TYPE_PLAN.md`](PITCH_TYPE_PLAN.md)）。

## Ledger（封存分）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UI-1 | 深色模式 | ruan6047 | 規劃AI(外部) | 暫無 | **Opus/跨家族** | — | ⚪ | 📥Backlog（封存）|
| UI-2 | 運動風質感 | ruan6047 | 規劃AI(外部) | Antigravity@tool | Opus | `ai/antigravity/ui-2` | ⚪ | 🏁完成 |
| UI-3 | 微互動 | ruan6047 | 規劃AI(外部) | Antigravity@tool | Sonnet(異 session) | `ai/antigravity/ui-3` | ⚪ | 🏁完成 |
| UI-4 | 響應式 | ruan6047 | 規劃AI(外部) | Antigravity@tool | Fable-5@Claude Code(375px模擬) | `ai/antigravity/ui-4` | ⚪ | 🏁完成 |
| UI-5 | 球員對比頁 + 好球帶 tooltip | ruan6047 | 規劃AI(外部) | 暫無 | Opus | — | ⚪ | 📥Backlog（封存）|
| LIVE-1 | 賽況頁決勝資訊與中職紀錄強化 | ruan6047 | Claude Code(對話中逐步核可) | Opus-4.8+Fable-5@Claude Code | **ruan6047 人審(AI輔助)** | `ai/claude-code/game-live-records` | 🔴 | 🏁完成 |
| UX-2 | 設計 tokens＋深色模式＋圖表色票 API | ruan6047 | Fable-5@Claude Code | Opus-4.8@Claude Code | Gemini-3.5-Flash@Antigravity | `ai/opus/UX-2` | ⚪ | 🏁完成 |
| UX-3 | 共用元件標準化（ui.tsx 收斂＋三態＋DataTable） | ruan6047 | Fable-5@Claude Code | Opus-4.8@Claude Code | Gemini-3.5-Flash@Antigravity | `ai/opus/UX-3` | ⚪ | 🏁完成 |
| UX-4 | 骨架導覽＋標準頁面解剖落地 | ruan6047 | Fable-5@Claude Code | Gemini-3.5-Flash@Antigravity | 待指派 | `ai/antigravity/UX-4` | ⚪ | 🏁完成 |

---

## 卡片明細


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
- 狀態：🏁完成　Commit：`b91f7ac` + 修復 `7d0f7e8`/`58da30b`
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
  - 07-10 Antigravity 修復 D1–D3 並自抓 D4（和局誤標勝方：`awayWin`/`homeWin` 改嚴格大於）
  - 07-10 重審 by Fable-5@Claude Code（同法量測）→ ✅通過：D1 縫隙 11.1→0px（th 恰 2.5rem）；D2 sticky th=surface-2 與 thead 一致；D3 `tr:hover .sticky-col` 規則生效；D4 實測 2026-06-13 樂天9:9中信雙方皆非粗體、台鋼9:0富邦勝方粗體正確；回歸（釘住/列表/桌機/tsc）無退化。合併至 main

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

### UX-2 設計 tokens＋深色模式＋圖表色票 API  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 通用層）　分支：`ai/opus/UX-2`
- 執行：Opus-4.8@Claude Code　查核：Gemini-3.5-Flash@Antigravity
- 範圍/驗收：spec §B 通用層 UX-2 列。重點——原則 A 寫進 `globals.css` 註解；硬編色清查（07-11 實測 **17 檔硬色**）歸零（隊色/圖表語意色除外，且此二者走色票 API）；深色模式 `data-theme` 切換＋暗色 token 組；**圖表色票 API**（讀 CSS var 的 chart theme helper，供 6 檔 recharts）。雙色系以 2〜3 頁抽驗，全頁雙色系截圖下放各頁面卡。
- 狀態：🏁完成（已合併至 main）　Commit：aa3f242ef92fc489b00ded759ab88b4ab8153dbf
- 執行摘要（Opus-4.8@Claude Code，07-11）：
  - globals.css：八原則＋色彩語意對照寫進檔頭註解；token 補文件與缺項（line-strong/amber/chart-1..6/zone-*/status-*）；新增 `:root[data-theme=dark]` 暗色組（Navy 底翻深、語意色提亮）＋暗色 .card 陰影。
  - 主題切換：layout `<head>` 無閃爍 script（localStorage→系統）＋ `components/theme-toggle.tsx`（掛載後讀 data-theme 避免 hydration mismatch）；viewport themeColor 改深淺雙值。
  - 圖表色票 API：`lib/chart-theme.ts` `useChartTheme()`（getComputedStyle 讀 token + MutationObserver 隨 data-theme 重讀）＋ chartAxis/chartTooltip/pitchColor/gradeColor 與語意調色盤（BATTED_OUTCOME/ZONE_OUTCOME/PITCH_CALL/GRADE/MEDAL/STATUS/PIE）。
  - 遷移 20 檔硬色 → token/API：6 recharts 檔接 hook；raw SVG（spray/zone/heatmap/game-board/umpires）走 fill-/stroke- 工具類或 var()；prColor 固定色階文字（PR_CELL_TEXT）留 ui.tsx；隊色維持 teams.ts。grep 全站無 hex（僅 teams.ts/chart-theme.ts/ui.tsx 固定色階/globals.css/viewport meta 例外）。
  - 驗收：`tsc --noEmit` 綠；首頁＋球員頁 light/dark 截圖無破版（雷達/PR條/散點/熱區/紀律條/pie/走勢圖皆隨主題換色且可讀）；球員頁 375px `scrollWidth==clientW` 無橫向溢出。
- Log：
  - 07-11 spec v5 核可後開卡
  - 07-11 ruan6047 派工執行 → Opus-4.8@Claude Code 開分支 `ai/opus/UX-2` 實作 tokens/深色/色票 API + 遷移，自測綠 → 🔍待查核（執行≠查核，須換家族或人審 + 實測）
  - 07-11 ruan6047 回報深色兩問題 → 修正：①預設改淺色（no-flash 不再跟系統，僅 localStorage=dark 才深色）②active 標籤 `bg-ink text-white`→`text-paper`（12 檔，深色下 bg-ink 翻淺致白底白字）+ `hover:text-white`→`hover:text-ink`；tsc 綠、深色截圖複驗標籤可讀。約定入 memory `dark-mode-conventions`
  - 07-11 查核 by Gemini-3.5-Flash@Antigravity → ✅通過 (npm run build 成功，全站硬色清理符合規範，已產出查核報告)

---

### UX-3 共用元件標準化  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 通用層）　分支：`ai/opus/UX-3`
- 執行：Opus-4.8@Claude Code　查核：Gemini-3.5-Flash@Antigravity
- 範圍/驗收：`ui.tsx` 收斂 eyebrow/dl 網格/chip/狀態徽章/skeleton·empty·error 三態/**DataTable**（寬表容器+sticky 首欄+表頭封裝）；互動元件一律 **client island**（禁為加互動翻整頁 `"use client"`）；6 檔 recharts 接 UX-2 色票 API。驗收對照 spec §B「模組化基準」（卡片殼 inline ×46→<10、手寫 table ×22/11 檔→零、skeleton 0→統一），至少 3 頁換裝無回歸。
- 狀態：🏁完成（已合併至 main）　Commit：df009eaa475260f50a78d7d106aaa3e82da867bd
- 進度：**元件完成**（`components/table.tsx` DataTable<T>：欄位 def+render prop+sticky首欄+bare/maxHeight/hideHeader/cellStyle+空態，server-safe；`ui.tsx` 三態+Eyebrow+StatGrid，皆附 props 註解）。**表格遷移 15/20**（球員頁×6/games box×2/teams×5/projections/umpires）——頁面級手寫 table 僅剩 `app/page.tsx`；元件內 table（DataTable/leaderboard/game-board）為正解不動。基準：卡殼 46→35、overflow 18→9、三態上線 3 檔。
- Log：
  - 07-11 spec v5 核可後開卡（**本案槓桿點**：先抽元件，頁面卡才是換裝非重寫）
  - 07-11 ruan6047 派工執行 → Opus-4.8@Claude Code 建元件 + 遷移 15 表（3 commit，tsc 綠、player 頁渲染複驗無回歸）；**剩**首頁 5 表 / 卡殼 sweep 35→<10 / 三態 sweep / build:check + 雙色系截圖 → 之後 🔍待查核
  - 07-11 ruan6047 裁示首頁 5 表下放 UX-5（避免重工）→ UX-3 收「去重」：**三態 sweep 完成**（ad-hoc 載入/空態歸零、9 檔走 EmptyState/Skeleton）+ Card 加 padding prop。commit e4d0323。
  - 07-11 **卡殼 sweep 完成**：46→24，殘留 24 全為已註記特例（game-board 內部×6、首頁×6 下放UX-5、/umpires+/predict×4 下放UX-10、DataTable/leaderboard/skeleton 內建、details×2、FranchiseCard 連結、matchup-card 型別同名）；**非特例頁面級卡殼＝0**。tsc + build:check（production）綠、records/player 頁渲染複驗。commit ff92c58 → **🔍待查核**。
  - 驗收摘要（供查核）：手寫 table 頁面級 22→0（僅首頁下放 UX-5）；卡殼 46→24（非特例=0）；overflow-x-auto 18→9；三態 ad-hoc→0；元件皆 props 註解；client island 未破壞（5/13 維持）。**查核須換家族/人審 + 實測**（雙色系逐頁掃、DataTable sticky/溢出、三態）。
  - 07-11 查核 by Gemini-3.5-Flash@Antigravity → ✅通過 (npm run build:check 成功，ui.tsx 與 DataTable 元件化完全合規，已產出查核報告)

### UX-4 骨架導覽＋標準頁面解剖落地  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 通用層）　分支：`ai/antigravity/UX-4`
- 執行：Gemini-3.5-Flash@Antigravity	查核：待指派（≠執行者）
- 範圍/驗收：header 導覽資訊架構（10 項導覽分組/優先序）、**標準頁面解剖落地**（h1+副標/主角區/輔助區塊排序——直接回應「區塊混亂」）、footer、行動端導覽。驗收：375px 導覽可用；各頁標題與區塊結構一致。
- 狀態：🏁完成（已合併至 main）　Commit：a9a8132
- Log：
  - 07-11 spec v5 核可後開卡
  - 07-11 ruan6047 派工執行 → Gemini-3.5-Flash@Antigravity 啟動執行，分支 `ai/antigravity/UX-4`
  - 07-11 執行完成 by Gemini-3.5-Flash@Antigravity (實作響應式導覽與 9 頁標題解剖落地，build:check 綠) → 🔍待查核
  - 07-11 收到退卡意見 (UX-4_REVIEW.md) → 進行回修完成 (修復 fadeIn/surface-3、補齊 matchups/games/players/teams 標題與語意、行動選單加入 Esc 監聽與 Focus Trap 焦點陷阱，build:check 綠) → 重新提交 🔍待查核
  - 07-11 審查通過，併入主線 🏁

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
