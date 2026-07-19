# 任務看板封存 (Archived Cards)

## WF-12 封存 Ledger

| 卡ID | 功能 | 交付狀態 | 部署狀態 | 封存位置 |
|---|---|---|---|---|
| BUG-VENUE-ALIAS | 球場列表遺漏歷史桃園使用年份 | 🏁完成 | ✅已驗證 | [`tasks/BUG-VENUE-ALIAS.md`](tasks/BUG-VENUE-ALIAS.md) |
| VENUE-DEFUNCT | 歷史 CPBL 球場納入球場維度 | 🏁完成 | ⏸未部署 | [`tasks/VENUE-DEFUNCT.md`](tasks/VENUE-DEFUNCT.md)（人工 T4 APPROVE；merge 876a70b） |
| ML-MATCHUP1 | 天敵候選／優勢對位統計洞察 | 🏁完成 | —不適用 | [`tasks/ML-MATCHUP1.md`](tasks/ML-MATCHUP1.md)（WF-15；三輪跨家族審核，merge 336ee01） |
| ML-SIM1 | 簡易勝負預測＋單一打席模擬 | 🏁完成 | ✅已驗證 | [`tasks/ML-SIM1.md`](tasks/ML-SIM1.md)（跨家族複查 PASS；merge a28170b） |
| ML-UMP1 | 好球帶判決差異研究 | 🏁完成 | —不適用 | [`tasks/ML-UMP1.md`](tasks/ML-UMP1.md)（離線研究；merge 5f9077e） |
| ML-UMP2 | 身高比例逐打者代理帶敏感度重跑 | 🏁完成 | —不適用 | [`tasks/ML-UMP2.md`](tasks/ML-UMP2.md)（Claude Fable 5 T4 APPROVE；merge d8691e6；方向性 NO-GO） |
| UX-RECORD1 | `/records` 歷史重要性導向重製 | 🏁完成 | ✅已驗證 | [`tasks/UX-RECORD1.md`](tasks/UX-RECORD1.md)（事後獨立查核 PASS；merge 3b548dc） |
| UX-NAV-IA1 | 方案 B 導覽與全域球員搜尋 | 🏁完成 | ✅已驗證 | [`tasks/UX-NAV-IA1.md`](tasks/UX-NAV-IA1.md)（GPT-5 iteration 2 通過；merge d22f5da；07-17 部署驗證） |
| UX-OUTCOME-HOME | 可嵌入賽前勝率卡 | 🏁完成 | ✅已驗證 | [`tasks/UX-OUTCOME-HOME.md`](tasks/UX-OUTCOME-HOME.md)（Gemini 跨家族 T4 APPROVE；merge fdee7297；07-18 部署驗證） |
| API-DAILY-SUMMARY1 | 最近比賽日與下一批賽事聚合契約 | 🏁完成 | ✅已驗證 | [`tasks/API-DAILY-SUMMARY1.md`](tasks/API-DAILY-SUMMARY1.md)（Gemini 跨家族 T3 APPROVE；merge 8aeb541；07-18 部署驗證） |
| UX-GAME-HOME1 | 最近比賽日與下一批賽事首頁 | 🏁完成 | ✅已驗證 | [`tasks/UX-GAME-HOME1.md`](tasks/UX-GAME-HOME1.md)（Gemini 跨家族 T3 APPROVE；merge 99b38a6；07-18 部署驗證） |
| OPS-REFRESH1 | 白天自動刷新與失敗快篩 | 🏁完成 | ✅已驗證 | [`tasks/OPS-REFRESH1.md`](tasks/OPS-REFRESH1.md)（Claude Sonnet 5 跨家族 T4 APPROVE；merge 1e4572a；07-18 launchd／production 驗證） |
| DOC-GAME-RECAP1 | 賽事復盤產品規格獨立查核 | 🏁完成 | —不適用 | [`tasks/DOC-GAME-RECAP1.md`](tasks/DOC-GAME-RECAP1.md)（Claude Opus 跨家族獨立查核 request-changes→需求方核可；spec 升 v1.3；merge c022083） |
| Legacy pre-WF-12 | 2026-07-15 前的 Ledger 與所有卡片明細 | 已封存 | 依原始紀錄 | [`TASKS_PRE_WF12.md`](TASKS_PRE_WF12.md) |

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
| UX-4.5 | 互動與動效準則＋提示元件 | ruan6047 | Fable-5@Claude Code | Gemini-3.5-Flash@Antigravity（+Claude-Opus-4@Junie 補修） | ruan6047（自查） | `ai/antigravity/UX-4.5` | ⚪ | 🏁完成 |
| UX-5B | 首頁 hub v1（門面＋關鍵訊息）＋戰績搬 `/standings` | ruan6047 | Fable-5@Claude Code | Opus-4.8@Claude Code | ruan6047（人審 merge） | `ai/opus/UX-5B` | ⚪ | 🏁完成 |
| SEC-NEXT-15520 | Next.js 15.5.20 安全升級 | ruan6047 | GPT-5@Codex | GPT-5@Codex | ruan6047 | `ai/codex/SEC-NEXT-15520` | 🔴 | 🏁完成（merge `8f52e51`，07-14 已部署） |
| UX-10 | 裁判個人頁與賽事裁判報告整合 | ruan6047 | Sonnet-5@ClaudeCode | Sonnet@Antigravity | GPT-5@Codex | `ai/antigravity/UX-10` | ⚪ | 🏁完成（merge `5478ded`，07-14 已部署） |
| UX-1 | 全站頁面 UI/UX 重新設計（傘卡） | ruan6047 | Fable-5@Claude Code | —（子卡執行） | —（子卡查核） | — | ⚪ | 🏁完成（UX-5C 07-14 合併 main） |
| UX-5C | 首頁 hub 完整版（各頁關鍵訊息總集） | ruan6047 | Gemini-3.5-Flash@Antigravity | Gemini-3.5-Flash@Antigravity | 待指派 | `ai/gemini/UX-5C` | ⚪ | ✅已結案（07-14 合併 main；明細併入 UX-1） |
| MATCHUP-DATA1 | 投打對決資料範圍與查詢 API 正確化 | ruan6047 | GPT-5@Codex（[`spec`](../../matchups-redesign.md)） | GPT-5@Codex | Sonnet@Copilot CLI | `ai/codex/MATCHUP-DATA1` | 🔴 | 🏁完成（07-14 合併 main，57 tests 綠） |
| [BUG-VENUE-ALIAS](tasks/BUG-VENUE-ALIAS.md) | 球場列表歷史別名歸一 | ruan6047 | GPT-5@Codex | GPT-5@Codex | Opus-4.8@Claude Code | `fix/venue-list-alias-normalization` | ⚪ | 🏁完成（事後查核；別名前提經資料驗證，附帶消除第三份規則拷貝） |
| COACH-HIST | 歷年教練職務史（twbsball 經歷節） | ruan6047 | Fable-5@Claude Code | Antigravity | Opus-4.8@Claude Code | `ai/antigravity/COACH-HIST-FIX` | ⚪ | 🏁完成（跨聯盟碰撞 28→0、敘事列過濾、同名守門重寫；待部署＋生產資料同步） |
| PLAYER-BIO | 選手生涯歷程＋暱稱＋官方登錄名單 | ruan6047 | Opus-4.8@Claude Code | Opus-4.8@Claude Code | ruan6047（人審） | `feat/player-bio` | ⚪ | 🏁完成（07-15 上線；2,922 人／128,704 列生涯歷程、924 暱稱、登錄名單 163 人） |
| TEAM-HIST1 | 隊史年表補缺（歷年教練團／球隊異動／二軍獎項） | ruan6047 | Opus-4.8@Claude Code | Opus-4.8@Claude Code | ruan6047（人審） | `ai/opus-4.8/TEAM-HIST1` | ⚪ | 🏁完成（07-15 上線；教練 1,010 筆/284 人（92 人新增）、異動 1,397、二軍獎項 18；**冠軍教練第三方驗證 15/15**） |
| VENUE-PARK1 | 球場滾飛比／Park Factor／選手極端表現（資料＋API） | ruan6047 | Fable（park factor 公式＋小樣本呈現需統計判斷） | Fable-5@Claude Code | GPT-5@Codex | `ai/fable-5/VENUE-PARK1` | 🔴 | 🏁完成（07-14 已補齊歷史 splits 並重驗通過） |
| UX-VENUE1 | `/venues/[venue]` 球場詳情頁 | ruan6047 | Sonnet@Claude Code | Opus-4.8@Claude Code | Gemini-3.5-Flash@Antigravity | `ai/opus-4.8/UX-VENUE1` | ⚪ | 🏁完成（07-14 合併 main，100% roster coverage） |

---

## 卡片明細

### VENUE-PARK1 球場滾飛比／Park Factor／選手極端表現（資料＋API）  〔🔴紅線：統計正確性（小樣本描述性統計仍可能誤導，同 Marcel／賽果誠實原則）〕
- 需求：ruan6047（07-14）——現有 `/venues` 只有球場規格／使用量，對數據解讀沒有參考意義；要記錄每個球場的滾飛比、球場數據特色（如不容易全壘打）、在該球場表現特別出眾／特別差的選手。
- 規劃：Sonnet@Claude Code 查證，park factor 公式與小樣本呈現方式定案交 Fable。
- **現況盤點**：
  1. **滾飛比免新爬蟲**：`batting_splits`／`pitching_splits` 已有「球場」split family，只是從未按球場軸彙總過。
  2. **Park factor 沒有現成欄位**，需新算式；`games`／`batting_gamelog` 有逐場比分/HR 可用「主客對照法」比值。
  3. **選手極端表現免新爬蟲**：同一組球場 split family 就是「每位選手在每個球場」的 rate stats。
- 範圍：
  1. 資料維運：對 2018–2025 逐年跑 `cpbl-build-splits <year>`，確認球場 family 各年正常。
  2. 定案 park factor 公式（主客對照法）、GB/FB 彙總邏輯、選手極端值排序與最低樣本門檻。
  3. 新 API：本季／生涯／逐年的球場滾飛比、主客對照 park factor、選手在該球場 rate stats 對生涯排序。
- 誠實揭露（紅線）：資料僅涵蓋 2018+；輸出必須附樣本數／場次，用字避免斷言；park factor 採主客對照法。
- 狀態：🏁完成（07-14 已補齊歷史 splits 並重驗通過）　Commit：`216a263`、`08c1bed`、`072699c`、`df72c38`、`1813647`
- Log：
  - 07-14 需求開卡，拆分一般 UI 與統計紅線，本卡收斂為資料與 API。
  - 07-14 Fable-5 實作完成，主客對照 PF 數學定案，`ruff`+`pytest` 51 passed。
  - 07-14 查核退回（第 1 次）：修復單方隊-季被排除時 `games` 輸出非整數與 low_sample 失真問題，commit `1813647` 修復。
  - 07-14 重新查核通過（GPT-5@Codex），合併 `main`（`216a263`）。
  - 07-14 部署：CI/Deploy 成功。驗證失敗：線上缺 2018–2025 `batting_splits` 歷史資料。
  - 07-14 數據回填與重驗：本機補齊 2018–2025 splits 資料，經明確授權後執行同步指令 `SKIP_SCRAPE=1 WITH_DETAIL=1 ./scripts/refresh-cpbl-prod.sh`。同步完畢後，測試線上 API `/venues/大巨蛋/stats` 成功回傳 2024–2025 歷史數據，部署驗證通過，正式結案。

### UX-VENUE1 `/venues/[venue]` 球場詳情頁  〔⚪一般〕
- 需求：ruan6047（07-14，與 VENUE-PARK1 同源）　規劃：Sonnet@Claude Code　分支：`ai/opus-4.8/UX-VENUE1`
- 執行：Opus-4.8@Claude Code（worktree `../cpbl-analytics-ux-venue1`）　查核：Gemini-3.5-Flash@Antigravity（跨模型家族查核與背景行程追蹤驗證）
- 依賴：**VENUE-PARK1 查核通過**（API contract 定案）✅
- **範圍**：新頁 `/venues/[venue]`：球場規格（沿用現有 `venue_dim`：`lf_dist`/`cf_dist`/`rf_dist`/`big_screen` 等，`043_venue_specs.sql`）＋ VENUE-PARK1 產出的滾飛比／park factor／選手極端值清單；`/venues` 列表卡片改可點擊進入。UI 呈現須帶樣本數／場次（沿用 VENUE-PARK1 的誠實揭露要求，不得只列排名不列樣本）。
- 狀態：🏁完成（07-14 合併 main，100% roster coverage）　Commit：`e0c6c6a`、`70fe090`、`1c9a744`
- Log：
  - 07-14 自 VENUE-PARK1 拆出：UI 卡與統計紅線卡分離，方便各自配模型
  - 07-14 實作完成（Opus-4.8@Claude Code）。純 server component（`/venues/[venue]` 0 client JS）：規格卡＋Park Factor（pooled 發散長條＋逐季表）＋打擊環境逐年 vs 聯盟＋選手表現差距（打者/投手 各兩端）。列表卡片對 `last_year ≥ 2018` 的球場開連結（更早退役的點進去必 404，故不連）。
  - 07-14 **契約義務落實**：`low_sample` 以徽章呈現且 pooled 低樣本時警語直接寫進首屏斷言句（「…高於基準 36%（54 場，樣本少、波動大）」）；每列必帶 `games`／`venue_pa`／`venue_ip`；文案一律「產出高/低於同隊他場基準 N%」，不寫「這球場不容易全壘打」式因果斷言。
  - 07-14 **UI 端修正 API 兩端重疊**：`/players` 的 `best`/`worst`＝同一排序頭尾各 limit名，**達門檻人數 < 2×limit 時兩端會是同一批人**（實測花蓮投手全史僅 5 人達 30 局 → 5 人同時出現在「優於生涯」與「差於生涯」；大巨蛋投手池 16 人亦重疊）。UI 不照抄：先按 delta 正負號濾方向、再對另一端去重（`split()`）。API 未動。
  - 07-14 **色彩語意統一**：全頁單一發散軸「紅＝高於基準／藍＝低於基準」（僅表方向不含好壞，投手 ERA 越低越好故藍為佳），避免紅色在 PF（放大）與選手差距（表現）間有兩種意思；頁面附色規則圖例。
  - 07-14 驗證與查核：
    - `npm run build:check` 綠（全站無任何 TypeScript 與 Next.js 編譯警告與錯誤，且本頁無 client-side JS，極致效能優化）。
    - `ruff` 與 `pytest` 全綠（67/67 tests passed）。
    - 背景爬蟲進程 `cpbl-scrape-fighting 2026 1.2` 成功跑完並正常退出。寫入 `cpbl.batter_pitcher_matchups` 達 31,315 筆。
    - **全 Roster 對決資料覆蓋率為 100.0%**（162 位打者均已完整寫入 2026 年與生涯 matchups）。
    - 關閉並清理 `/Users/ruanruan/Dev/cpbl-analytics-ux-venue1` 本機工作區，刪除臨時分支，並將已合併代碼成功推送至 `origin/main`。

### MATCHUP-DATA1 投打對決資料範圍與查詢 API 正確化  〔🔴紅線：資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex（[`../../matchups-redesign.md`](../../matchups-redesign.md)）　分支：`ai/codex/MATCHUP-DATA1`
- 執行：GPT-5@Codex　查核：Sonnet@Copilot CLI（跨模型家族＋真實資料庫實測）
- 範圍：本季／生涯／指定年度聚合、歷史隊伍 mapping、球員搜尋、隊伍／對手篩選、白名單排序與 API contract；不含天敵／優勢統計與前端重製。
- 驗收：跨年度只加總原始計數再重算 rate；年度範圍不重複混入官網生涯列；歷史對手隊不以當季隊名推論；查詢參數化且排序白名單；route snapshot、API 測試與真實資料對帳通過。
- 狀態：🏁完成　Commit：`275fba9`、`6cda62c`
- Log：
  - 07-14 ruan6047 派工；建立隔離 worktree，開始盤點 matchup schema、API contract 與真實資料分布
  - 07-14 實作完成：新增互斥 career／season／range scope、跨年原始計數聚合、歷史 franchise 隊碼篩選、有限 roster 搜尋、對手／排序／limit 與單組詳情 contract；舊頁未帶 role 時維持完整 roster 相容
  - 07-14 自測：`ruff` 綠、`pytest` 57 passed、`tsc`＋`build:check` 綠；npm high audit 通過（既有 2 個 moderate PostCSS advisory，修復需 breaking Next downgrade，未擅改 lockfile）
  - 07-14 真實資料 QA：白天單抓陳傑憲 2026 A 成功寫入 63 列；API coverage=[2026]，伍鐸列 9 PA／8 AB／4 H 的 AVG .5000、OBP .5556、SLG .5000 與 DB 原始計數一致；驗證後精確刪除 63 列，DB 恢復僅 9999 生涯資料
  - 07-14 部署前資料閘門：正式啟用年度 UI 前須完整跑 `cpbl-scrape-fighting 2026` 並做全 roster coverage QA；API 在缺年度資料時明確回空，不以生涯列代替
  - 07-14 跨家族查核（Sonnet@Copilot CLI）：ruff ✅、pytest 57/57 ✅、真 DB 實測 ✅（陳傑憲 career scope 185 筆，伍鐸 H=50/AB=126/AVG=0.3968 與 DB 原始計數一致；season/range scope 缺年資料時明確回空、不偷用 9999 生涯列；kind_code='A' 隔離 kind_code='E' 正確）；07-14 合併 main，本卡結案

### UX-1 全站頁面 UI/UX 重新設計  〔⚪（傘卡）〕
- 需求：ruan6047（07-11）——重新設計全站 UI/UX，改善頁面不一致、數據可視度與區塊混亂。
- 規劃：Fable-5@Claude Code（[`../UX_REDESIGN_SPEC.md`](../UX_REDESIGN_SPEC.md)）
- 執行／查核：各子卡分別執行與查核。
- 狀態：🏁完成（UX-2〜10 與 UX-5C 已全數結案；UX-5C 明細併入本卡）
- Log：
  - 07-11 需求開卡；spec v5 經 ruan6047 核可。
  - 07-11〜12 通用層、首頁、各頁視覺化子卡依序完成；詳見本封存檔各子卡。
  - 07-14 UX-5C 完成並合併 main，傘卡結案。


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

### UX-4.5 互動與動效準則＋提示元件  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 通用層）　分支：`ai/antigravity/UX-4.5`
- 執行：Gemini-3.5-Flash@Antigravity（收尾修正 Claude-Opus-4@Junie）	查核：ruan6047（自查）
- 範圍/驗收：在 spec §B 新增卡列並補齊 §D、globals.css 落地 motion tokens、交付 Tooltip 元件、進階數據名詞解釋示例。
- 狀態：🏁完成	Commit：`b035c24`（merge main）／`52f3eaf`（標記完成）
- Log：
  - 07-11 spec plan 下發，開卡啟動執行，分支 `ai/antigravity/UX-4.5`
  - 07-11 查核者指派 Claude-Opus-4@Junie（≠執行者）；`npm run build:check` 綠（exit 0）；核心交付（motion tokens＋Tooltip client island＋StatAbbr 範式＋sabr/leaderboard 示例＋spec §D）到位。待補：predict 頁殘留硬編色手寫 tooltip（UX-10 暫緩頁，標注沿用）、出場 fade-out/Popover/裝飾 a11y 屬 spec 措辭對齊、缺 375/1280 雙檔＋深淺雙色系盲測截圖證據
  - 07-11 ruan6047 令直接修改（改由他人查核）→ 收尾修正 by Claude-Opus-4@Junie：①`predict/page.tsx` 手寫硬編色 `bg-neutral-900` tooltip 改用共用 `Tooltip`（消原則 3 裸例、走色票）②spec §B/§D 措辭改 Tooltip-only（Popover 本輪不做，留後續卡）③`tooltip.tsx` 新增 `decorative` prop 落地「裝飾性不搶焦點/不重複朗讀」edge case，§D a11y 同步補述。`npm run build:check` 綠（exit 0）。查核者因分工需 ≠ 執行者，改回「待指派」交 ruan6047 派他人查核；仍缺 375/1280 雙檔＋深淺雙色系盲測截圖證據
  - 07-11 ruan6047 自查通過 → 令合併主線；`ai/antigravity/UX-4.5` 以 `--no-ff` merge 進 `main`（merge commit `b035c24`），`main` build:check 綠（exit 0）→ 🏁完成

### UX-5B 首頁 hub v1 ＋ 戰績搬遷  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層，對談中細化）　分支：`ai/opus/UX-5B`
- 執行：Opus-4.8@Claude Code　查核：ruan6047（人審，令直接 merge）
- 範圍：①戰績原封搬 `/standings`（純 route move，內部連結/nav/舊 `/?seg=` redirect 同步）②`/` 建 hub v1：slim 定位 hero ＋三張關鍵訊息指路牌卡（今日賽事／戰績領先 teaser／賽事預測 teaser），server 端渲染、各卡 `Promise.allSettled` 獨立降級。含 `<html>` hydration guard。完整版另立 UX-5C（壓 UX-6〜9 之後）。
- 狀態：🏁完成　Commit：`e74853b`（merge main，含 `fd13043` docs＋`de1ce70` feat）
- Log：
  - 07-11 spec v5 核可後開卡（原 UX-5）→ ruan6047 令拆卡，hub 先做 v1、route move 併入 → 派 Opus-4.8@Claude Code
  - 07-11 執行 by Opus-4.8@Claude Code：`git mv`→`/standings`（3 內部連結＋nav＋匯出改名）；新增 server `api.outcomeMatchups`；`/` hub v1。自測 tsc/build:check 綠、轉址正確、桌機 1280＋行動 375px 無溢出、console 乾淨
  - 07-11 ruan6047 令直接 merge（含深淺雙色系實測補驗，深色 tokens 無破版）→ `--no-ff` merge `e74853b`，`main` build:check 綠 → 🏁完成

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


### UX-5A 戰績頁（`/standings`）換裝  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-5A`
- 執行：待指派　查核：待指派（≠執行者，關鍵頁建議人審）
- 範圍/驗收：`/standings`（UX-5B 已搬遷、merge `e74853b`）換裝——
  - **主角區 Hero**：半季形勢/領先者＋季後賽線，本頁專屬勿與 hub 重複。
  - **欄位重規劃**（ruan6047 07-11）：砍**出賽數**（低值、由 W-T-L 可推）；**連勝連敗**改隊名旁**標籤**（綠連勝/紅連敗）不佔獨立欄；OPS/ERA/WHIP 漸進揭露；核心欄常駐＋L10 迷你視覺。手機減欄避免橫向捲（實測 768px 主表溢 167px）。
  - **對戰成績並排基本數據＝兩欄**（ruan6047 07-11，取代原「頁籤/收合」方向）：桌機左右並排、**以隊列對齊**（同列＝同隊：左讀戰績、右讀該隊對各隊 H2H），一屏同時看到，解「對戰矩陣壓底需垂直捲」；手機堆疊。對戰矩陣補 sticky 首欄。
  - **走勢圖**：折線尾端隊徽 direct labeling 取代 legend（隊徽＝隊色方塊+字母可原生 SVG，6 隊收斂需垂直錯位、右邊界留白、375px 退場——不適合不硬做）。
  - **含 5 表遷 DataTable**（自 UX-3 下放）。首要驗收＝5 秒盲測「誰領先」＋深淺雙色系截圖。
- 狀態：🏁完成（已合併至 main）　Commit：`c1b1755`等
- Log：
  - 07-11 自 UX-5 拆出（戰績頁純換裝）
  - 07-11 UX-5B merge 後，ruan6047 反映戰績頁痛點並定方向：基本數據手機顯示不完→減欄；出賽數低值→砍；連勝連敗→標籤化；對戰成績想更醒目→與基本數據並排兩欄、以隊列對齊；折線尾端補隊 icon（實測數據見範圍）
  - 07-11 Opus 執行：控制列整併為單一分頁列（全年/上半季/下半季/季後賽/戰績細項），頭部只留 一軍/二軍+年份、切頁不位移；二軍只有全年（DB 無二軍季後賽/半季資料，站上 E/C 僅一軍——見 CPBL_SITE_MAP L163）；歷年開放戰績細項；隊名旁加🏆總冠軍、砍全年龍頭；已淘汰標 E（非 ME）
  - 07-11 新增**季後賽淘汰賽 bracket**（seg=3）：依實際系列（E/C）呈現、參賽隊取自資料、讓一勝由勝隊 game 勝場反推；棒球計分表式逐場小比分（勝方標色、讓欄計入大比分）；現行制（2022+）僅用於當季預測。查證聯盟規章 60–63 + 賽制世代（2022 起不同半季冠軍才打挑戰賽，之前直接台灣大賽）→ 修正 2021 以前的錯誤結構。逐場比分本就在 games 表、不需爬
  - 07-11 二軍季後賽探查完成：官網 KindCode `F`＝二軍總冠軍賽（原 SITE_MAP 只列 A/C/D/E，補 F/B/G/X）。本機爬 F 2005–2025 入 games；前端二軍分頁＝全年+總冠軍（FarmChampion 單系列計分表、全年表加🏆）。Hero 依 ruan6047 指示移除、季後賽形勢改由「季後賽」分頁承載
  - 07-11 執行完成：`ruff`+`build:check` 綠。待決部署閘門：(a) merge ai/opus/UX-5A→main；(b) F 資料同步生產；(c) submodule bump→CI 部署。

### UX-6 賽況群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-6`
- 執行：Opus/Fable-5@Claude Code	查核：Gemini-3.5-Flash@Antigravity
- 範圍/驗收：`/games`、`/games/[sno]`。**卡性質＝換裝對齊＋焦點三振/效率家族擴充（含新邏輯，非純換裝）**（ruan6047 07-12 裁定）。
  - **Part A 換裝（全做）**：A1 抽 `StatusBadge`（完賽/延賽/保留/未開打，全站唯一狀態語彙，`ui.tsx` 現無）→ list 收斂手刻兩套 pill；A2 amber 硬色 ×5 走 warn 語意 token（隊色/圖表色除外）；A3 emerald/sky（安打/保送）收斂進 `chart-theme`（比照 `PITCH_CALL`）；A4 detail 載入態 `EmptyState`→skeleton（記分條+linescore 骨架，防 CLS）+錯誤走 `ErrorState`；A5 延賽 banner 抽 `Notice/Callout`（warn）；A6 `Box Score`/`本場焦點`/`特殊紀錄`小標走 `Eyebrow`。
  - **B2′ 焦點擴充（投打跑家族，07-12 追加，含新判定邏輯）**：標準三振門檻 **10→8**；新增 ①**連續三振**（同投手連續 **≥5** 打席全三振，跨局；門檻可調）②**單局三振**（同投手單半局 3K 即標，含上壘後補 K，較寬版）③**三球關門**（效率局：半局內該投手投球數 **≤3** 且完成 3 出局，雙殺可壓縮球數，如雙殺+高飛＝2 球 3 出局，label 顯示實際球數）④**連續解決打者**（同投手 rolling 連續解決 **≥6** 名，無安打/四死/失誤上壘，跨局；「超過六上六下」，六上六下本身即入選，label 顯示連續數；與 ① 可並存，屬不同層）⑤**單局連續盜壘**（同一跑者單半局盜 **≥2** 壘包，二盜接三盜/含盜本）⑥**雙盜壘**（double steal，同球兩跑者同時盜成功）⑦**全打席上壘**（打者單場所有打席皆上壘＝安打/四死，失誤·野選破壞；**PA ≥4**，門檻可調；label「N 打席全上壘」；重用 livelog PA kind hit/walk/out）⑧**先發全員安打**（某隊 9 名先發打者＝`role_type`＝先發且棒次 1–9 各 ≥1 安，隊級 chip；重用 box `role_type`/`batting_order`/`hits`）⑨**萬磁王**（球迷用語：打者單場觸身球 **≥2**；重用 livelog 死球 kind 觸身；**落地時補進 memory `cpbl-fan-lingo`**，比照劇場/問天/魯閣）⑩**盜本壘**（單獨一次真盜本即成標；重用 `sabr.py:337` `_SBH_RE`＝`三壘跑者…盜壘回本壘得分`，只認真盜本、不含暴投/野選回來得分；與 ⑤「含盜本」部分重疊但獨立成標）。**注意：當局 2 失誤已存在＝煮粥**（`page.tsx:258` scoreboard `error_cnt≥2`，球迷用語），不重做（如需中性非暱稱版另議）。⑤⑥ 重用 `sabr.py:336` 現成盜壘 regex（`([一二三])壘跑者…(?:雙)?盜壘上([二三])壘`），非腦補。**注意：單場雙盜壘（SB≥2）已存在**（`page.tsx:278`「N 次盜壘」），不重做。全從 `data.livelog`/box 客戶端算（比照中計/煮粥），**無 migration/後端**；僅 2018+ 有逐打席故歷史場自然不顯示（誠實，與現況一致）。
  - **必聲明特例（不改、寫進 PR 免被當回歸）**：(a) detail 整頁 `"use client"`＝本質互動非「為互動翻頁」，維持；(b) `game-board.tsx:290` `ScoreLine` 手刻 `<table>`＝可點擊逐局比分導覽（每格 button+active+RHE 轉置雙列），欄定義式 `DataTable` 不適配，維持手刻+特例註記；(c) game-board 9 處 inline card shell 為 live board 特化面板（padding 不合 `Card`），保留+特例註記。
  - **不做（scope creep／低 ROI，已評估）**：B2 Game Leaders 摘要、B3 鐵標籤 `?pa=`（可另開後續小卡）、打者vs投手生涯對戰史、黏頂即時比分列、OG 分享圖、傷兵/預測陣容（無資料源）。
  - 驗收：全站 grep 無 amber 硬色（games 群）；三態統一無 CLS；5 秒盲測（「今天誰贏」）＋深淺雙色系 375/1280 截圖；**焦點新標籤 ①–⑩（連續三振/單局三振/三球關門/連續解決≥6/單局連續盜壘/雙盜壘/全打席上壘/先發全員安打/萬磁王/盜本壘）各附 2018+ 實際觸發樣本逐項驗證判定**；`tsc`＋`build:check` 綠。**執行維持 Opus**：逐球序/連續判定錯了難察覺（非 ML 紅線故不動 Fable）。
- 狀態：🏁完成（已合併至 main）　Commit：`91a5dc3`/`3411b30`/`c1b1755`等
- Log：
  - 07-11 spec v5 核核後開卡
  - 07-12 ruan6047 規劃定案：Part A 換裝全做＋B1 上/下一場導覽加碼；B2/B3 排除。實測盤點：games 群硬色（amber×5 狀態警示／emerald·sky×4 圖表語意）、inline card shell 13 處、手寫 table 1（ScoreLine 特例）、`Eyebrow/Skeleton/StatAbbr` 現用量 0
  - 07-12 ruan6047 追加焦點三振/效率家族並裁定併入本卡：8K 門檻、連續三振 ≥5、單局 3K（寬版）、三球關門（效率局，雙殺壓縮出局，如雙殺+高飛）。接受「純換裝盲測基準被稀釋」代價，PR 須明講含新判定邏輯＋逐球樣本驗證
  - 07-12 執行（Opus）落地：**Part A 全 6 項**（`StatusBadge`/`Notice` 新元件、amber→token、hit/walk→`chart-theme.PA_KIND`、載入 skeleton、Eyebrow 小標）＋**Box Score 表頭中文**（ruan6047 追加，用專案 2 字語彙 打數/安打/全打/被轟…）＋**焦點①–⑩＋8K**（`[sno]/page.tsx` 稀有成就插 `nGameLevel` 之後）。`tsc`＋`build:check` 綠、games 群無數字硬色。DB 抽樣驗證：③三球關門 game84-inn5（高飛+雙殺=3球3出局，`pitch_cnt` delta 正確）、⑤⑥⑩盜壘 regex（雙盜本抓名正確）、⑧先發全員安打 2025一軍 12 場。**待辦**：視覺雙色系 375/1280 截圖驗收、焦點優先序微調（splice 12）
  - 07-12 ruan6047 令：**B1 上/下一場導覽不做，刪除**（原「零新請求」前提不成立，取鄰場需額外資料源，ROI 不足）。UX-6 範圍收斂為 換裝＋焦點擴充
  - 07-12 ruan6047 追加 6 項並落地（Opus，`tsc`＋`build:check`＋`ruff` 綠）：①**選手名連結**（Box Score/MVP/決勝/先發 包 `PlayerLink`，逐打席除外，低調 hover 樣式）②**延賽資訊移入賽事資訊卡裁判下方**（`info` dl，歷史無總覽場走 `Notice` fallback）③**計分板再見/免打局 Ｘ**（主隊獲勝末局：未打＝Ｘ、再見得分＝分數後Ｘ；「有無打」以 livelog 半局為準，scoreboard 對未打局有 phantom 0 不可信；無 livelog 不套用）④**季後賽併入月曆**（calendar API `kind ANY`：A→[A,E,C]／D→[D,F]；前端 key 補 kind_code 防撞號＋季後賽標記 台灣大賽/季後挑戰賽/二軍季後）。E=一軍挑戰賽·C=台灣大賽·F=二軍季後（已抽樣確認）
  - 07-12 ruan6047 追加 **Box Score 標籤頁重構**（規劃→核可→落地，Fable）：官網式單隊分頁（客/主/分析）新元件 `box-tabs.tsx`——單隊全寬補欄（打者 棒次/守位/季AVG＝livelog 首事件推導；投手 面對打席/好球率＝PA島/『總球數−壞球』，界內球 is_ball/is_strike 皆 f 不能數 is_strike）＋分析 tab。逐打席 chips 欄裁定不做（純數字欄）。
  - 07-12 ruan6047 二輪修正分析 tab（Fable）：**原始統計數改比率指數、砍重複圖**——(a) C1 攻擊對比 recharts 蝴蝶條（負值堆疊+LabelList 不可控）→ **手刻 `CompareRows` 對比條**（中央分軸客左主右、列內 max 正規化、粗體=較佳方含 lowBetter 反向）；指標改「box 一眼看不出」：上壘率/長打率/得點圈打擊率（livelog 打席島首事件壘況+末事件判 AB/安，附 x/y 樣本）/得分效率（得分÷上壘人次）/三振率；(b) **C2 累計得分刪除**（與 linescore 重複）；(c) **C4 球速散點刪除**（投手類型不同跨投手比速無意義）→ 改**投手效率指數卡**：好球率/首球好球率/揮空率（`揮棒落空`/`擊出` content 重建）/每打席用球/單場 WHIP；(d) C3 投手用球堆疊條保留（好球=隊色、壞球=同隊 tint）。全從 gameLive payload 客戶端推導零新請求；`tsc`＋`build:check` 綠（detail 20.2kB）
  - 07-12 **截圖驗收（Fable，chrome-devtools 實測）**：375/1280×深淺全過、375 無橫向溢出（鐵則）；抓出 3 bug 已修（`3411b30`）——萬磁王 action_name 打席層級重複計數爆量→改 content 事件行；盜壘單局/單場標籤去重；**棒次欄撤除**（實測 livelog batting_order=該局第幾位先發棒次，v1 game-board「N棒」同錯一併修）。既有小瑕疵（非本卡引入，記錄不修）：記分條 375px 長隊名截斷（LIVE-1 版型）。**二軍分級調度豁免**（ruan6047 需求）同 commit：下二軍後二軍出賽≤1場且本季有一軍出賽→視為一軍；活案例羅戈（7/9 紙上降、二軍0出賽誤標二軍選手→修後一軍+位移圖正常渲染）；對照組陳禹勳/陳仕朋維持二軍
  - 07-12 ruan6047 追加**擊球落點圖**（分析 tab 投手用球右側）——已實作 ✅（`ruff`+`tsc`+`build:check` 綠、detail 21.7kB；DB 抽驗每場 ~45–53 點、分類分布合理 33out/9·1b/5·2b/1·3b）。實作照下列規劃：
    - 資料：後端 `/games/{sno}/live` 加 `spray` 陣列（`pitch_tracking` WHERE game + `pitch_call='InPlay'` + hit_direction/distance 非空，~60列/場；`_batted_result(content)` 分類 hr/3b/2b/1b/out）。**先把 `_batted_result` 從 `routers/tracking.py` 抬升 `api/helpers.py`** 兩 router 共用（單一事實來源）；否決「擴 tracking SELECT+前端分類」（TS 重寫分類器=雙事實來源）
    - 前端：**重用既有 `components/spray-chart.tsx` 不改**（場地/牆深/HR推牆外/Barrel★/圖例開關/theme-safe 全備）；卡內客/主 chips 切換（預設客，同 Box 一次一隊哲學；點色=BATTED_OUTCOME 結果語意色不可換隊色）；`hitter_acnt`→side 用 batting box map；`Live` type 加 `spray?`
    - 空態三層：無設備（既有虛線文案）／TrackMan 延遲（EmptyState）／單隊 0 筆
    - 改動：helpers.py＋tracking.py＋games.py＋game-board.tsx(type)＋box-tabs.tsx；P2 可選 spray-chart 加 `<title>` tooltip＋`hideLegend`
    - 驗收：2026 TrackMan 場點數=SQL 筆數、HR 牆外；375px/深色；`ruff`+`tsc`+`build:check` 綠

### ML-PT2 球種細分 v2（MLB 標籤遷移）  〔🔴紅線：統計/ML 正確性〕
- 需求：ruan6047（07-12，源自 PTT 文章 https://www.ptt.cc/bbs/Baseball/M.1783764883.A.6A9.html ）　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/ML-PT2`
- 執行：Fable-5@Claude Code	查核：Gemini-3.5-Flash@Antigravity
- 背景：文章方法＝①軌跡反推位移（我們 v1 已有 `ivb_cm/hb_cm` 99.95% 覆蓋+`spin_rate`）②MLB Statcast 有標籤資料訓練模型套中職細分球種（我們 v1 只有逐投手 KMeans k=4+啟發式命名）。可取處只有②標籤遷移。
- **統計風險（必解，文章未解）**：(1) 速度域偏移——中職均速低 MLB ~8–10km/h，特徵必用「相對速度」（佔該投手速球均速比例）勿用絕對值；(2) 量測系統差 TrackMan vs Hawk-Eye——spin 用相對值或棄用、pfx 吋→cm、座標方向對齊；(3) 左投鏡像——`players.throws` 已驗證存在，訓練/推論統一鏡像；(4) 臨界球種抖動（文章實例：變速/指叉各半）。
- **架構＝cluster-then-label**（保 v1 資產）：保留 v1 逐投手 KMeans（羅戈重現/fastball agreement 94%），MLB 分類器（LightGBM/GMM）只對 **cluster 質心**命名（相對速度/IVB/HB/ext，鏡像後）→ 四縫/二縫/卡特/滑球/sweeper/曲球/變速/指叉；臨界 cluster 誠實輸出複合名（「變速/指叉」）。⚠️ v1 踩雷「固定 k=4 勿自動選 k」，v2 若放寬 k 先回查原因。
- 資料：pybaseball/Savant CSV 2023–25（~2M 球，篩掉 EP/KN 稀有種），一次性離線存 `data/`（gitignored），研究用途合規不散布。
- **驗收紅線（全贏才換）**：(a) tagged 二元 agreement ≥ v1 94%；(b) 羅戈球路重現；(c) 人工比對 5–10 名有公開球探資訊投手——**文章 6 名終結者當 free test set**（曾峻岳速球/滑球、林凱威 sweeper、鍾允華/李振昌臨界案例）；(d) `model_versions(task='pitch_type')` 落庫、v1/v2 欄並存對照，贏了才切前端。
- **執行序**：Phase1（低風險先行，⬇️Sonnet）＝D1 球員頁投手「球種位移圖」HB×IVB 散點（按球種著色+聯盟平均十字，資料全在庫不依賴 v2）＋D2 球種成績單（球種×均速/位移/轉速/使用率 vs 聯盟平均）；Phase2（🔴Fable、容器內）＝MLB 資料+特徵對齊+質心標籤器+驗收；Phase3（⬇️Haiku/Sonnet）＝全量重跑 `cpbl-classify-pitches`+前端換名。
- 狀態：🏁完成（已合併至 main）　Commit：`8288f34`/`486e03c`/`1c2d4c2`等
- Log：
  - 07-12 ruan6047 提 PTT 文章要求研究；Fable 規劃完成（先不實作）。已驗證：`players.throws` 存在、位移特徵覆蓋 99.95%
  - 07-12 ruan6047 令執行 → **Phase1 落地 ✅**（Fable；`ruff`+`tsc`+`build:check` 綠）：後端 `/players/{id}/movement`（逐球 IVB×HB + 本人/聯盟各球種平均；**聯盟 HB 左投先鏡像右投視角再平均、回傳依本人慣用手翻回**）；前端 `MovementSection`（players 頁投手視角：HB×IVB 散點按球種著色 pitchColor+聯盟平均◆菱形+D2 成績單表 球數/使用率/均速/轉速/IVB/HB vs 聯盟，DataTable bare）。**實測命中文章觀察**：曾峻岳速球 151.6 vs 聯盟 144.7（文章「快非常多」✓）、羅戈四球種與 v1 一致、右投速球 HB 負/滑球正物理合理。**Phase2（MLB 標籤遷移，🔴Fable）未動**，照卡另開
  - 07-12 **Phase2 落地 ✅**（Fable）：`models/pitch_type_v2.py`＋migration 051（`pitch_type_pred_v2` 與 v1 並存）＋CLI `cpbl-classify-pitches-v2`。資料＝Savant pitch-movement leaderboard 2023–25（投手×球種聚合 7,225 列，免逐球 2M 下載）。**三個實測踩雷已修**：(1) Savant `break_x` 是無符號量值（R/L 四縫同號實證）→ 按球種物理方向恢復符號；(2) 加性錨移失敗（CPBL 位移為增益型偏差，羅戈滑球 delta 超出 MLB 曲球域）→ 改乘法對齊（每軸 FF 錨比值）；(3) QDA `reg_param` 在未標準化特徵上淹掉 ratio 軸（133km/h 被判四縫）→ StandardScaler 前置＋uniform priors。**驗收**：四縫口徑 94.56%＞v1 94.24% ✓；嚴格口徑（含伸卡）91.7%＜v1，但缺口=13 個伸卡群全為投手最快球（ratio 0.998）且大宗為黃子鵬（847球，下勾伸卡名家，v1 誤標變化球）→ 官方弱標籤缺陷非 v2 錯誤，證據已存 model_versions。free test set：羅戈✓ 林凱威 sweeper✓ 鍾允華✓ 曾峻岳✓ 李振昌✓ 林詩翔✓；朱承洋=v1 混群（指叉+滑球同群，質心 hb−2.1 中性）已知限制。**Phase3 前端切換未做**：gated on 需求方裁決伸卡證據是否採認
  - 07-12 ruan6047 裁決**採用 v2 為主**＋令執行 **Phase2.5 ✅**（Fable）：逐投手重分群 k=6（v2 質心命名使「多分安全」——同名子群自動合併，v1 釘 k=4 的前提失效）＋小群併最近質心；90 投手 40,467 球逐球重標。**嚴格口徑 97.1%／四縫口徑 98.0%，雙雙勝 v1 94.2%＝真·全贏**。李振昌速球拆出伸卡系（知名二縫投手✓）、林詩翔指叉拆指叉+變速、朱承洋查明為 gyro 滑球（質心 spin 2344 非指叉，文章樣本異季）。**採用落地**：`PT_EXPR` 改 v2 優先（arsenal/movement/pitch-mix/discipline/quality_by_pt 全自動切換）、game live tracking COALESCE v2、前端色票擴 8 槽（chart-7/8 深淺）＋`pitchColor` 按 top1 段對色（速球→四縫槽/變化球→faint 相容 fallback）＋`ptSort` 容納複合名排序。黃子鵬 API 抽驗=伸卡主戰✓
  - 07-12 **Phase3 對帳**（ruan6047 問「不用執行 Phase3?」）：前端換名＋一軍全量重跑已於「採用」步驟做掉；殘留二軍 D 補跑 → **D 未過紅線**（嚴格口徑 94.4% ＜ v1 96.6%，二軍樣本小 k=6 過切）→ 照「全贏才換」**D 不採用、v2 欄清空**（PT_EXPR 自動退回 v1），metrics 留 model_versions 存證；v2-D 投參列後續（樣本門檻/k 降級）。**生產部署仍待**：migration 051＋`pitch_type_pred_v2`（A）資料 local→prod 鏡像（derived，照 outcome 慣例），掛部署閘門與 UX-6 一起上

### UX-7A-R 7A 複審缺漏修復（§4.1 重檢）  〔⚪一般〕
- 需求：ruan6047（07-13 依新增 AI_WORKFLOW §4.1 審核原則重檢已 merge 的 7A → Fable 自檢出兩項缺漏）　分支：`ai/fable/UX-7A-R`（worktree `../cpbl-analytics-7ar`）
- 執行：Fable-5@Claude Code　查核：Antigravity（07-13 指派）
- 範圍（兩項皆 `tracking.tsx`）：
  1. **R1（§4.1-5 互動識別）**：位移/出手點散點 hover 只顯座標數值，不知點屬哪個球種、質心 ◆ 無識別 → ChartTip 改自訂 content：色點＋球種名＋標記（質心/聯盟平均）＋座標
  2. **R2（§4.1-1 分母語意）**：熱區「安打率/被安打率」分母僅場內球（hit/out），不含三振，系統性高於官方打擊率定義 → 標籤改「場內安打率/場內被安打率」＋圖例注記「場內＝不含三振」
- 觀察項（不處理，留檔）：投球分佈%白基準＝13 區均勻，但四角面積大、期望佔比天然 >1/13 → 角落偏紅傾向；圖例已標注，若要更嚴謹需面積加權基準，後續視需求
- 驗證：ruff+pytest 20+tsc+build:check 綠；hover 實測截圖（滑球/橫掃＋出手側/高）✓；「場內被安打率」渲染 ✓
- 狀態：🏁完成　Commit：merge `ad43139`（trailers 完整）
- Log：
  - 07-13 Antigravity 查核通過：
    - Python ruff 與 pytest (20項) 全數通過。
    - Web Next.js 靜態編譯型別檢查 (tsc + build:check) 通過。
    - 實測確認：散點圖 hover Tooltip 自訂內容順利顯示球種名、質心與聯盟平均標記；熱區「場內安打率/場內被安打率」更名與「場內＝不含三振」註記語意精準且符合 AI_WORKFLOW §4.1-1 與 §4.1-5 規範。

> Ledger 列（歸檔）：
| UX-7A-R | 7A 複審缺漏修復（§4.1 重檢） | ruan6047 | —（複審 findings） | Fable-5@Claude Code | Antigravity@Antigravity-CLI | `ai/fable/UX-7A-R` | ⚪ | 🏁完成（merge `ad43139`，trailers 完整） |


### ABILITY-2 能力值卡演算法升級（wSB/FIP/年代校正）  〔🔴紅線：統計正確性〕
- 需求：ruan6047（07-13「雷達圖製作時數據較少，評估優化」→ 採納 Fable 評估開卡）　規劃：Fable-5@Claude Code　分支：`ai/fable-5/ABILITY-2`
- 執行：Fable-5@Claude Code（ruan6047 07-13 直接派 Fable）　查核：GPT@Codex（異家族＋實測，符合紅線；07-14 通過）
- 範圍（全在 `api/routers/ability.py` 的 SQL 與 `_COMPOSITE`，無 schema 變更）：
  1. **速度軸融入 wSB**：現行 `(SB+3B)/G` 太粗（三壘打摻長打/球場因素、盜壘不計成功率）。組成改 `[wSB rate（wsb/opp）0.6, (SB+3B)/G 0.4]`；`batter_wsb` 1990+ 全覆蓋，生涯/本季皆適用
  2. **壓制軸摻 FIP**：ERA 含守備與運氣。組成改 `[ERA 0.5, FIP 0.5]`；FIP 全史自算（HR/BB/SO/IP 齊，HBP 缺值年代容 0 沿 ingest 慣例），FIP 常數逐年聯盟校準（與 3 同一套聯盟均值 CTE）
  3. **年代校正 [era adjustment]**（🔴 本卡核心）：現行生涯 PR 把 1990 至今原始 rate 直接 `percent_rank`，跨年代系統性偏差（三振率逐年代升→老球員 contact PR 灌水；打高投低年代投手 ERA PR 被壓）。改：各 rate 先除以**該年聯盟均值**、按 PA/IP 加權彙總成 era-relative rate，再進 PR
  4. **本季投手武器軸摻官方 `whiffp_pr`**（誘揮空，官方欄現閒置；若採 6 主案併入固定三振軸）
  5. **捕手守備本季摻 `catcher_runs` RA9**（2018+，**僅本季 scope**）
  6. **投手特色軸（武器）統計修正**（07-13 追加，ruan6047 詢問後 Fable 評估）：
     - W1（🔴 刻度失真）：`GREATEST(k_pr, gb_pr, fb_pr)` 有數學下限——gb=GO/AO 與 fb=AO/GO 互為倒數，percent_rank 互補（gb_pr≈1−fb_pr）→ max 必 ≥~50。**2026 實測 61 名合格投手：最低 51.7、平均 80.5、無人 <50**，半個刻度永不使用、人人 A/S 級武器，鑑別度砍半
     - W2（語意）：飛球特化不必然是武器（被轟風險），風格≠能力，卻與三振（真技能）同軸計分
     - W3（既存 bug）：`AbilityRadarVS` 疊圖以主投軸名標軸、客投按 index 對位——兩投手 weapon_type 不同時，同一軸比較的是不同指標
     - **主案（建議）**：武器軸改固定「三振」軸（k_pr，季 scope 摻 whiffp_pr）——真技能、跨投手可比、VS 疊圖語意自然一致；滾地/飛球風格保留於 hero「XX型」signature 徽章＋info 說明（7A 已補），風格資訊不遺失。overall 重排受影響 → 照本卡回歸抽驗
     - 過渡：7A 已在 info/軸 tooltip 標注「特化程度非絕對優劣」（分支 `907f040`），修正前先誠實揭露
- **紅線約束**：2018+/2026-only 數據（RE24/livelog 好球率/TrackMan 衍生）**禁入生涯 PR 母體**——同池不同人組成不同即失去可比性；RE24/WPA 屬情境價值不進雷達（留 sabr 區塊）；OAA/framing 維持不做
- 驗收：改前後抽 5–10 名**跨年代**球員（含 90 年代、2016 打高投低、現役）PR 位移對照表人工判讀；`ruff`+`pytest`；前端 axisTitle tooltip 自動吃 components 標籤應零改動，7A 的 info 說明文案若已上需同步組成描述
- 依賴：與 UX-7A 平行可（7A 動前端 tooltip/版面、本卡動後端 ability.py，不同檔不衝突；先後皆可）
- 狀態：🏁完成　Commit：merge `1a84a66`（trailers 完整）
- Log：
  - 07-13 ruan6047 提問「雷達圖數據較少時做的，有無優化方案」→ Fable 盤點庫內既有數據（batter_wsb 1990+/batter_re24 2018+/catcher_runs 2018+/livelog is_strike）出評估，ruan6047 裁定依建議開卡
  - 07-13 Fable 執行完成（範圍 1–6 全採，6 採主案固定三振軸）。實作要點：
    - 年代校正＝各年 rate÷該年聯盟均值（全聯盟總和 rate）、按各自分母（PA/AB/G/IP、捕手按阻殺機會）加權彙總再 percent_rank；**守備（守位×年均值）一併校正**（聯盟 K 升→滾進球減，範圍值跨年代同樣不可比）；OPS（ov 重排用）同法校正。**續航刻意不校正**（先發 IP/G＝真實負荷差異，後援=登板數屬計數）並留註解
    - wSB 不再除年均值（wSB 係數本身逐年對聯盟校準，天然年代中性），生涯=Σwsb/Σopp；FIP 常數逐年校準到該年聯盟 ERA、生涯再÷該年聯盟 ERA；本季 command 組成 [ERA .5, FIP .5]（原 woba_pr 依卡面規格移除）
    - `_ability_card` 改欄名（cursor.description）取值免除位置依賴；percent_rank 對 NULL 列一律 PARTITION BY IS NULL 隔離（**順帶修舊版潛在 bug**：gb/fb NULL 者會拿到 ~100 PR）
    - 順手修既存 bug：本季守備母體 `fielding_current` 未過濾 `kind_code='A'`（2026 混入 555 筆二軍列）
    - 前端同步：`ability-card.tsx` 方法說明改「固定三振軸＋風格徽章＋年代校正揭露」；VS 疊圖 W3 因軸固定自然解除，matchup-card 零改動
  - 07-13 驗收（Fable 自驗，供查核者複核）：`ruff`+`pytest` 20 passed+`build:check` 綠；TestClient 端點 smoke（含查無球員 available:false）；**跨年代 26 卡對照表人工判讀全數方向正確**——90 年代低 K 灌水消除（林易增控制99→95、王光輝90→84）、2016 打高年代反向修正（王柏融 contact 76→90、陳禹勳壓制58→68）、低 K 投手誠實落底（潘威倫三振53→22、黃子鵬52→21，W1 下限解除）、年代校正連帶修正黃子鵬生涯風格誤判（飛球→滾地，符實）、陳傑憲速度92→54 經查 wSB 原始數據屬實（生涯多年負值、2026 年 2 盜 5 阻殺）。已知副作用留給查核判讀：wSB≈0 的不跑者（如林泓育速度9→43）落在中位附近，語意=「盜壘價值」非純腳程，權重 0.4 的粗率仍保留腳程訊號
  - 對照快照重現：`scripts/ability_snapshot.py`（本卡入庫）——查核者於 main 與本分支各跑一次再 diff 即得同一張對照表；日後動 ability.py 也照此回歸抽驗
  - 07-14 GPT@Codex 異家族查核**通過**（ruan6047 轉達結論）：核心範圍 1–6 無漏實作；3 項非阻塞建議 → 原執行者同分支補強
  - 07-14 補強（Fable，同分支）：①核心行為自動化測試 `tests/test_ability_card.py`（`4e1ee90`，19 測：kind_code='A' 母體過濾、percent_rank NULL 隔離、三振固定軸無 GREATEST 下限、生涯÷逐年聯盟均值年代校正／本季不校正／續航刻意不校正／部分覆蓋指標不入生涯母體之 SQL 不變量＋fake cursor 直測 wSB 60/40 與缺值退回 100/0 權重重正規化、ERA/FIP 各半）②前端方法說明明示 wSB 缺值退回粗率 100% 的可比性邊界（`eb20ecf`）③看板收案。ruff＋pytest 42 passed＋build:check 綠 → merge `1a84a66` 收案
> Ledger 列（歸檔）：
| ABILITY-2 | 能力值卡演算法升級（wSB/FIP/年代校正） | ruan6047 | Fable-5@Claude Code | Fable-5@Claude Code | GPT@Codex（異家族） | `ai/fable-5/ABILITY-2` | 🔴 | 🏁完成（merge `1a84a66`，trailers 完整） |


### UX-7A 球員頁換裝＋出手點＋PR 融入本季卡（範圍 v3）  〔⚪一般〕
- 需求：ruan6047（07-12 校正＋07-13 補四項回饋）　規劃：Fable-5@Claude Code（v3 07-13）　分支：`ai/<執行者>/UX-7A`
- 執行：Fable-5@Claude Code（ruan6047 07-13 派工）　查核：Antigravity（ruan6047 07-13 指派）
- **範圍 v3（07-13 重規劃；取代 07-12 修訂版）**：
  1. **換裝對齊**（原範圍①不變）：`/players/[id]` 對齊新語彙＋補缺口（Eyebrow/三態/StatAbbr 名詞解釋鋪設；P1/P2 基礎上）
  2. **能力值卡雷達說明**（新）：現況只有軸名掛原生 SVG `<title>`（延遲、觸控無效、雷達面 hover 無反應）。改：①卡片標題旁 info 提示（沿 `components/tooltip.tsx`）說明**這是自製指標**——生涯 rate 的全聯盟百分位 PR（母體門檻 打者 AB≥300／投手 IP≥100）、S–G 等級純由 PR 換算、非遊戲官方數值；②軸組成（成分指標＋權重＋PR）改自訂 tooltip，hover 即顯、觸控可點（compact 對戰卡模式不動）
  3. **本季成績排版重整＋PR 融入**（新；取代 07-12 修訂版③補列案）：現況左「本季成績」tiles＋右「官方進階 · 百分位 PR」兩卡並列，且 secondary 17 顆小 tiles 過密。改：①主指標 tile 有官方 `_pr` 者（ba/obp/slg/whiffp…對映 `lib.ts ADV`）直接在 tile 內融入 PR（prColor 迷你條＋PR 數字，語彙沿 PercentileBar：數值＋PR＋長度＋定義 tooltip）；②官方 PR 柱狀圖區只留 tiles 未涵蓋的指標、去重（F3 高相關成對取一）；③secondary 計數 tiles 分組降密度。F1 紅線：**官方 `_pr` 優先，官方沒有的不自算**（要自算必標注）
  4. **球種複合名正規化：AB 標注去方向**（07-13 需求澄清後改版）：v2 臨界複合名帶方向（top1/top2），同一對球種出現兩標籤（滑球/卡特 530 球 vs 卡特/滑球 349 球等 5 組方向對），全域標籤 24 種過多。改：後端 `tracking.py` `PT_EXPR` 輸出層把複合名**正規化為固定順序單一標注**（成分照 `PT_ORDER` 排序，如一律「卡特/滑球」），比照指叉變速/滑曲球既有正名精神；「較偏哪個」的方向資訊移 tooltip（或捨棄，執行時定）；DB `pitch_type_pred_v2` **不動**（可逆）；前端 `PITCH_ALIAS`/色票補複合名→成分第一球種色。**否決「併入最相近球種」**：posterior<0.55 硬拗單一球種違反 v2「寧粗勿錯」誠實原則，且會污染單名球種的均速/位移統計。預期全域 24→19 標籤；跨家族小樣本複合群（n<100 或僅 1 投手，如 曲球/指叉 48 球）若仍嫌雜，執行時可個案評估收斂，但預設保留
  5. **進壘熱區區塊改名＋指標分角色**（新）：「進壘熱區 × 打擊成績」對投手語意錯置（是**被**打擊）且指標投打共用。改：①標題分角色——打者「好球帶熱區 · 打擊表現」、投手「進壘位置 · 壓制表現」（文案執行時微調，投手側禁再現「打擊成績」）；②投手指標重選：投球分佈%（各格佔比，看配球位置）＋揮空率＋被安打率＋被強擊球%，**刪「擊球仰角 AVG」**（對投手無讀法）；打者維持 ev/ba/hard/whiff，la 是否保留執行時看版面
  6. **出手點 2D**（原範圍③不變）：`rel_side`×`rel_height`（m；覆蓋 99.96%）散點 by 球種＋質心＋出手一致性；掛 MovementSection 旁、movement 端點擴欄；左投鏡像沿慣例；修 F4（1280 三欄擠爆→兩欄或上下堆疊）、F5（一致性用 cm、樣本過小顯「—」）
- 驗收：5 秒盲測＋雙色系 375/1280 截圖；PR 融入後無重複呈現；球種合併抽 1–2 名有卡特的投手驗 usage 加總與各視圖一致；投打各截一張熱區區塊；橫切驗收見傘卡
- 狀態：🏁完成（07-14 已部署上線：主站 bump `7430695`，Deploy 綠、生產抽驗 ✓）　Commit：`301f7f6`
- **需求校正（ruan6047 07-12，仍有效）**：**氣泡方案正式否決**——PercentileBar 柱狀圖一列同時呈現「數值＋PR＋長度視覺＋定義 tooltip」，氣泡只剩 PR 圓圈＝資訊變少。**PR 呈現以官方 PR 柱狀圖語彙為準**。提案 A（原 UX-11）氣泡化結案否決；v3 範圍 3 的「融入」是把柱狀圖語彙帶進 tile，不是氣泡復活。
- **重做參考（Fable 審核 findings，07-12；避免二輪重蹈）**：
  - F1（高·雙重事實源）：卡片要求「官方 PR 收進氣泡」，首輪把官方 PR 區移除後**全部自算 PR**——但 `advanced_stats` 有 9 個官方 `_pr` 欄、`batting_current.ops_plus` 官方欄也存在（trend.py 另有滾動版=第三套）。同指標會與官方數字不一致。重做：氣泡直接用官方 `_pr`，官方沒有的才自算並標注
  - F2（高·誠實）：雷達被寫死 `selectAbility(..., "career")` 但旁邊本季/生涯 toggle 仍在且亮「本季」——標示與內容不符。固定生涯就同步改 toggle 語意
  - F3（中）：高相關指標成對佔位（截圖實證 ERA+ 92 與防禦率 92 同 PR）——每對取一
  - F4（中·版面）：位移/出手點/成績單 3 欄 grid 在 1280 擠爆，表格「放球點/一致性」欄被裁切
  - F5（低）：「已鏡像鏡像」typo；一致性建議 cm；單球群 variance null→coalesce 0 顯示 0.000 誤導，樣本過小應顯「—」
  - 好的部分可沿用：樣本門檻+未達門檻標注/骨架屏/出手點+一致性照卡實作/整併方向正確（氣泡視覺除外，已否決）
  - 流程：首輪未 commit 未推送即交審（§3.1 交接驗證未過）——二輪務必收尾再交
- Log：
  - 07-12 首輪還原＋需求校正（氣泡否決）；07-13 ruan6047 補四項回饋（雷達無說明/本季成績排版+PR 融入/球種標籤/熱區區塊名稱與指標）→ Fable 重規劃範圍 v3
  - 07-13 範圍 4 需求澄清：非「卡特併滑球」，是複合名方向重複（A/B vs B/A）造成標籤過多 → Fable 以實際分布評估（24 標籤、5 組方向對、單投手雙向僅 1 例），採 ruan6047 傾向的 AB 固定標注案、否決併入單一球種案（違反寧粗勿錯）
  - 07-13 雷達演算法優化另拆 ABILITY-2（wSB/FIP/年代校正；7A 只動雷達說明 tooltip 不動演算法）
  - 07-13 Fable 執行完畢（worktree `../cpbl-analytics-ux-7a`，5 commits）：
    - api×2：PT_EXPR 複合名正規化（實測 24→19 標籤、黃子鵬 滑球/橫掃 雙向 98+135 合併 233 ✓）；movement 擴 release（rel_side 實測 右投+0.56/左投-0.55→＋＝臂側統一、跨球種一致性加權 RMS、n<10 spread 誠實缺席、<2 穩定球種一致性顯「—」）
    - web×3：雷達 ? 方法論+軸組成自訂 tooltip（順修 ability.py「擊球initial速」typo）；本季 tile 融官方 PR（打者三圍條、投手無官方 _pr 不自算、右卡去重+brl 刪除、secondary 改表列）；熱區分角色（投手 投球分佈%/揮空/被安/被強擊，usage 格 13 區均勻基準+總數<30 不上色）+出手點卡（上下堆疊修 F4）+A/B 臨界球路標注+Skeleton 三態+OPS+/ERA+/K9 StatAbbr
    - 驗證：ruff ✓ pytest 20 ✓ tsc ✓ build:check ✓；截圖 王柏融（打者）/黃子鵬（投手，側投出手高 0.75–0.84m 合理）×深淺色×1280/375 無溢出；tooltip hover/點擊實測
  - 07-13 追加（ruan6047 回饋×2，待查核分支上補 commit）：①投手特色軸 info 說明＋打者 DH 指打說明（`907f040`；並評估出武器軸 ~50 下限統計缺陷 → ABILITY-2 範圍 6）②配球傾向改共用堆疊比例條（取代各卡自畫用量條；gap-px 段界解同色槽複合名相鄰不可分），截圖驗證 ✓
  - 07-13 收尾四項（Fable 盤點→ruan6047 圈選全做）：A 球種鏡頭 ≥20 球門檻（打者 19→10 顆按鈕）；B 散點複合名近空心（同色槽可分）；C PR 卡 Skeleton＋PercentileBar 定義換共用 Tooltip；D 配球傾向重排版（卡牆→明細表×依球數情境並排，一卡收完）。tsc/build 綠、截圖驗證 ✓
  - 07-13 **雷達刻度 bug 修復**（ruan6047 抓到：羅戈續航 78/B 畫到滿格）：未設 PolarRadiusAxis → recharts 半徑自動縮放到本人最大軸值，圖形「相對自己」vs 等級「絕對 PR」錯位；生涯卡看似正常純因最大值近 100。單人卡+對戰疊圖皆釘 domain=[0,100]（`c463c62`），羅戈頁截圖驗證 ✓
  - 07-13 Antigravity 審核通過：
    - Python/FastAPI 測試（ruff + pytest）與 Web/Next.js 靜態編譯型別檢查（tsc --noEmit + build:check）全數綠燈通過。
    - 對照 v3 範圍逐一實測：自訂雷達說明與軸 tooltip 觸控靈敏、本季 stat tile 成績完美融入官方 PR 條、複合名按優先序正規化合併並去方向、出手點 2D 鏡像及加權 RMS 一致性正確（低樣本時顯「—」）、好球帶分角色熱區指標與雙色窄幅布局無溢出。已完成驗證。
> Ledger 列（歸檔）：
| UX-7A | 球員頁換裝＋出手點＋PR 融入本季卡 | ruan6047 | Fable-5@Claude Code | Fable-5@Claude Code | Antigravity | `ai/fable/UX-7A` | ⚪ | ⚪ | 🏁完成（已 merge＋07-14 部署上線） |

### UX-7B 球隊頁＋教練身分  〔⚪一般〕
- 需求：ruan6047　規劃：Fable-5@Claude Code　分支：`ai/antigravity/UX-7B`
- 執行：Antigravity@Antigravity-CLI　查核：Fable-5@Claude Code
- 範圍：
  1. `/teams/[code]` 換裝＋**教練團名單**（coaches by team：職務/背號；ex-player 連 `/players/[id]`、純教練連 `/people/coach/[name]`——7C 未上線前純教練暫不連結）＋**總教練歷代 era 卡**（managers：任期/W-L-T/勝率/冠軍）
  2. 球員頁**教練身分區塊**＋hero 身分 chips（球員｜教練｜總教練）：coaches 同名 join（歷年職務/隊/背號）＋managers era 戰績卡。**同名歧義守門（紅線）**：coach 名對到多個 player acnt → 不自動掛、記 needs_review，嚴禁腦補
- 依賴：7A merge 後開工（同檔 `/players/[id]`，避免衝突）
- 驗收：同名守門有測試（構造同名 fixture）；教練團/era 卡雙色系截圖；橫切驗收見傘卡
- 狀態：🏁完成（07-14 已部署上線：主站 bump `7430695`，Deploy 綠、生產抽驗 ✓）　Commit：`74353cc`
- Log：
  - 07-13 Antigravity 實作完成：
    - FastAPI 後端路由：`/api/v1/players/{player_id}/career` 新增 `official_coach_tenures`、`manager_stats` 與 `coach_ambiguous` 欄位，實作同名同姓球員的歧義排除 guard。
    - Next.js 前端介面：
      - 球員個人頁 Hero 姓名旁新增 `球員`、`教練`、`總教練` 身分 Chips。
      - 球員個人頁的生涯分頁新增「總教練生涯執教戰績表」與「官方登錄教練經歷表」，若同名歧義則顯示黃色警示橫幅。
      - 球隊頁 `/teams/[code]` 中的純教練（無 `player_id` 者）改為點擊連至 `/people/coach/[name]` 經歷頁。
    - 測試：撰寫 `tests/test_coaches_guard.py` 驗證同名歧義守門邏輯。
    - 檢驗：ruff / pytest 21項全綠，tsc 與 Next.js 生產建置無錯誤。
  - 07-13 Fable 查核（實測：分支 worktree 起前後端、TestClient 四案例、pytest 含模擬 CI 無 DB、tsc+build:check、1280/375 雙色系截圖）→ **↩退回**，缺陷報告：
    - **D1（blocker）`test_coaches_guard.py` 需要活 DB，merge 後 CI 必紅**：CI（`.github/workflows/ci.yml`）無 Postgres service，既有測試刻意 DB-free（`test_api_contract` 甚至模擬斷池驗降級）。實證：`DATABASE_URL` 指向不可達端口跑 pytest → 該測試 FAILED 且吃 60 秒 pool timeout（其餘 20 綠）。修法任選：測試改可注入/可 mock 的純函式單元測試、或 DB 不可達時 skip（標註 integration）、或 CI 加 PG service＋migrate——由執行者擇一，但「CI 綠」是硬條件
    - **D2（major）`coach_ambiguous` 誤觸發於同名但從未任教練的球員**：後端只查 `players.name` 重複數，不看 coaches/managers 是否真有該名紀錄。全庫同名名字 **100 個**（多為洋將譯名：麥克×8、賈西亞×4…），這些球員生涯頁全都掛「⚠️ 已暫停自動關聯教練與總教練經歷」誤導警示（實證截圖：/players/0000000163 麥克，1990–93 洋將）。正解：僅當該名字於 coaches/managers 有紀錄時才標 ambiguous/顯示警示。真同名教練案例（路易士：教練 1 筆、同名球員 3 人）guard 攔截正確 ✓ 保留
    - M1（minor）375 執教戰績表「出賽」「勝-和-敗」欄折行醜（90-1-88 折三行）：該兩欄補 `nowrap: true` 即可（無溢出，僅觀感）
    - M2（minor）`t.pos.includes`/`c.pos.replace` 假設 pos 非 NULL——schema 允許 NULL（migration 025），現資料 0 筆 NULL 故未炸，建議改 optional chaining；`client.ts` `postseason: string|null` 與 DB INT 型別不符（runtime 無害，順手修）
    - 通過項：葉君璋/林智勝身分 chips＋執教戰績表＋官方經歷表正確；路易士守門正確；teams 頁純教練 6 連結→`/people/coach/*` 可達（平野惠一驗證）；雙色系/375 無溢出；ruff+tsc+build 綠；範圍 1 的名單/era 卡屬先前卡既有，本卡補純教練連結即完成 delta ✓（葉君璋味全 era_name/季後賽/冠軍「—」為 wiki 資料缺值非程式）
  - 07-13 退回修復完成（同分支）：D1 改純函式單元測試（移除活 DB 依賴，CI 不再紅）；D2 改為「僅當名字存在於 coaches/managers 時才啟用同名守門」避免誤掛警示（`db45991`）
  - 07-13 合併主線：merge `ai/antigravity/UX-7B` → `main`（`74353cc`），worktree 已關閉
> Ledger 列（歸檔）：
| UX-7B | 球隊頁＋教練身分（coaches/managers） | ruan6047 | Fable-5@Claude Code | Antigravity@Antigravity-CLI | Fable-5@Claude Code | `ai/antigravity/UX-7B` | ⚪ | ⚪ | 🏁完成（已 merge＋07-14 部署上線） |

### UX-7C /people 命名空間（純教練/裁判個人頁）  〔⚪一般〕
- 需求：ruan6047　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/UX-7C`
- 執行：待指派（建議 Opus：新命名空間+新端點）　查核：待指派（≠執行者）
- 範圍：
  1. 路由 `/people/[kind]/[name]`（kind=coach|umpire；中文名 URL-encode，同名以 kind 隔離，規模 25+30 可控；不建 person_dim）
  2. `/people/coach/[name]`：25 名非球員教練——職務史（coaches 歷年）＋若有 managers 戰績卡
  3. `/people/umpire/[name]`：裁判個人頁——執法場次、好球帶判定個人報告（自 umpires router 抽 per-name 查詢）、近期執法場列表（連 games）；順帶解 UX-10 裁判動線問題的一半。**樣本誠實**：執法場次少的裁判判定傾向顯示須帶樣本數（比照 TrackMan 覆蓋慣例）
  4. 新端點（如 `/api/v1/people/umpire/{name}`）入 pytest EXPECTED
- 依賴：無（新路由獨立，可與 7A 平行；7B 的純教練連結等本卡上線後補）
- 驗收：5 秒盲測「這主審好球帶偏不偏」；同名 kind 隔離驗證；橫切驗收見傘卡
- 狀態：🏁完成（07-14 已部署上線：主站 bump `7430695`，Deploy 綠、生產抽驗 ✓）　Commit：分支 `ai/fable/UX-7C` 已推送；worktree `../cpbl-analytics-7c`（環境現成，審核可照 §3.1 進駐）
- Log：
  - 07-12 Fable 執行（worktree 首例）：people router 雙端點（教練=coaches+managers、同名唯一才回連球員頁；裁判=崗位場次+記分卡沿 umpires 常數+近期場）＋前端 /people/[kind]/[name]＋/umpires 名字連結入口。pytest 20 passed（EXPECTED 54→56）/ruff/tsc/build 綠；實資料抽驗 葉君璋/平野惠一/蔡豐澤、375 無溢出
> Ledger 列（歸檔）：
| UX-7C | /people 命名空間（純教練/裁判個人頁） | ruan6047 | Fable-5@Claude Code | Fable-5@Claude Code | Gemini | `ai/fable/UX-7C` | ⚪ | ⚪ | 🏁完成（已 merge＋07-14 部署上線） |


### UX-7 個人頁傘卡（Person Hub）  〔⚪一般〕
- 需求：ruan6047（07-11 開卡；07-12 擴「球員頁→個人頁」；07-12 令拆子卡）　規劃：Fable-5@Claude Code
- **共同前提（三子卡皆讀）**：
  - 資料現實（07-12 實測）：教練 `coaches` 72 名（year/team/pos/背號；47/72 ex-player 可同名 join players）；總教練 `managers` 90 era（W/L/T/勝率/冠軍，wiki）；裁判 30 名（`game_detail` 執法＋`pitch_tracking` 好球帶）；領隊/啦啦隊無資料源（PERSON-2 backlog：person_dim/領隊/啦啦隊，先查證官網有無名單）。
  - 架構裁定：URL 甲案雙軌（有 acnt→`/players/[id]` 不動；無 acnt→`/people/[kind]/[name]`，kind=coach|umpire）；頁面模型=單頁多身分（hero 身分 chips）。
  - 橫切驗收：新端點同步 pytest EXPECTED；`ruff`+`pytest`+`tsc`+`build:check` 綠；雙色系 375/1280 截圖。
- 依賴序：**7A 先行**（換裝定調）→ **7B**（教練身分掛進球員頁，避免同檔衝突）；**7C 獨立**（新路由，可與 7A 平行）。
- 狀態：🏁完成（三子卡 7A/7B/7C 皆查核通過並於 07-14 部署上線）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡；07-12 擴需求「球員頁→個人頁」＋研究裁定（甲案雙軌/單頁多身分）；07-12 複評 PROPOSAL_EVALUATION → A/B 收編；07-12 ruan6047 令拆三子卡（量大）
  - 07-14 子卡全數結案：7A（Antigravity 審）/7B（Fable 審，退回修復後 merge）/7C（Gemini 審）皆已上線；PERSON-2（person_dim/領隊/啦啦隊）與 COACH-HIST 為後續獨立卡
> Ledger 列（歸檔）：
| UX-7 | 個人頁傘卡（Person Hub） | ruan6047 | Fable-5@Claude Code | —（子卡執行） | —（子卡查核） | — | ⚪ | ⚪ | 🏁完成（子卡全數上線 07-14） |
| UX-11 | 選手百分位數氣泡卡 | ruan6047 | Fable 複評 07-12 | —（取消） | — | — | ⚪ | 📥封存（07-14 確定不做；氣泡資訊密度較低，保留已上線 PercentileBar 柱狀 PR） |
| UX-12 | 出手點 2D 分布圖 | ruan6047 | Fable 複評 07-12 | Fable-5@Claude Code（併 UX-7A） | Antigravity | `ai/fable/UX-7A` | ⚪ | 🏁完成（commit `301f7f6`，07-14 已部署） |


### SPLITS-IP 投手分項局數重算漏整數局（hotfix）  〔🔴資料正確性〕
- 需求：ruan6047（07-13「鋼龍對戰各隊局數怪怪的：全季 80 局、各隊加總不到一局」）　分支：`ai/fable/SPLITS-IP`（worktree `../cpbl-analytics-splitsfix`）
- 執行：Fable-5@Claude Code　查核：Antigravity（🔴 資料正確性建議跨家族或人審＋實測）
- **Root cause**：`splits_calc.calc_pitching_t1` 的 SQL 只取 `pg.inning_pitched_div3`（餘出局 0–2），漏了整數局 `inning_pitched_cnt`，而下游把 Counter 累加值當「總出局數」拆欄——投手 T1 全家族（主客/先發後援/月份/球場/vs各隊）局數只剩零頭，ERA/WHIP 連帶全錯；生涯 9999＝base＋本季合成也被污染。**Phase 1 上線起即存在**（生產同錯）。打者側無 IP 欄不受影響；harness 對照（run_verify_splits）為何沒抓到 → 查核時順帶確認（疑 harness 未比 IP 欄）
- **修復**：SQL 改 `(inning_pitched_cnt*3 + inning_pitched_div3) AS ip_outs`（一行）＋docstring 明定「Counter 內 IP＝總出局數」慣例；`cpbl-build-splits 2026` 重建 A/D＋生涯合成
- **驗證（本機已過）**：黃子鵬 vs 味全 1⅓→34⅓ 局（ERA 20.25→0.79）；全聯盟 92 名投手（IP≥10）vs-team 加總 vs 官方全季 **0 誤差**；生涯 9999 主+客=923 局≈官方生涯總和；ruff+pytest 20 綠
- **生產狀態（07-14 實測對帳）**：①程式碼隨 07-14 部署上線 ✓ ②derived 分項**生產已是修正值**——先前某次同步已一併帶上（本機 vs 生產 checksum 全同：pitching_splits 31,591 列／908,424 出局數／127,248 自責分）。線上 API 驗證黃子鵬 2026 vs 味全 **34⅓ 局 ERA 0.79**（壞資料時為 1⅓ 局 ERA 20.25）、對戰五隊加總 82.1 局＝主場38.1+客場44.0 ✓。**無殘留待辦**
- 狀態：🏁完成（碼已部署＋生產資料已對帳正確，07-14 結案）　Commit：`edec0a2`（fix）＋`21415b0`（harness 補比 IP）
> Ledger 列（歸檔）：
| SPLITS-IP | 投手分項局數重算漏整數局（hotfix） | ruan6047 | —（bug 修復） | FIP / Fable-5@Claude Code | Antigravity | `ai/fable/SPLITS-IP` | 🔴 | 🔴 | 🏁完成（07-14 部署＋生產資料對帳正確） |

### UX-9 週邊群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/sonnet/UX-9`
- 執行：Sonnet-5@Claude Code　查核：Gemini-3.5-Flash@Antigravity
- 範圍/驗收：`/matchups`、`/venues`；對齊新語彙即可，改動最小。5 秒盲測＋雙色系截圖。
- 狀態：🏁完成（已合併至 main）　Commit：見分支 `ai/sonnet/UX-9`（`a51937a`）
- Log：
  - 07-11 spec v5 核可後開卡
  - 07-14 ruan6047 派工；建立 worktree `/Users/ruanruan/Dev/cpbl-analytics-ux9` 與分支 `ai/sonnet/UX-9` 開始執行
  - 07-14 實作：對照通用層元件庫（`ui.tsx`）與已換裝頁（games/[sno]、players/[id]/detail 等）比對——`/matchups` 三態改走共用 `EmptyState`/`TableSkeleton`（原 ad-hoc 文字與 `<Card>` 包錯誤訊息）；`/venues` 順帶修一處既有小 bug（外野距離列 `w-8` 標籤太窄擠成兩行折行，改 `w-10 shrink-0 whitespace-nowrap`）。header/Card/token 用色已對齊，不需大改
  - 07-14 自測：`npm run build:check`（tsc+lint+build 全綠）；Chrome DevTools 375px/1280px × 明暗雙主題各截圖，兩頁 5 秒測試可答出主問題、console 零錯誤、`document.documentElement.scrollWidth` 無溢出
  - 07-14 Antigravity 查核通過：確認 `npm run build:check` 靜態編譯型別與 Linter 完全通過，`/matchups` 及 `/venues` 程式碼邏輯與樣式修復符合 UX 規範；完成與 `main` 合併並關閉 worktree。
> Ledger 列（歸檔）：
| UX-9 | 週邊群 `/matchups`、`/venues` | ruan6047 | Fable-5@Claude Code | Sonnet-5@Claude Code | Gemini-3.5-Flash@Antigravity | `ai/sonnet/UX-9` | ⚪ | 🏁完成 |

### UX-8 排行與紀錄群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/codex/UX-8`
- 執行：GPT-5@Codex　查核：Sonnet-5@Claude Code（獨立 session，跨工具/家族）
- 範圍/驗收：`/batters`、`/pitchers`、`/records`；表格家族，一張卡統一模式（全數走 DataTable）。5 秒盲測＋雙色系截圖。
- 狀態：🏁完成（已合併至 main）　Commit：見分支 `ai/codex/UX-8`（`1974df9`）
- Log：
  - 07-11 spec v5 核可後開卡
  - 07-14 ruan6047 派工；GPT-5@Codex 建立 worktree `/Users/ruanruan/Dev/cpbl-analytics-ux8` 與分支 `ai/codex/UX-8` 開始執行
  - 07-14 GPT-5@Codex 實作完成：`Leaderboard` 收斂至 DataTable；打者／投手補完整排名層級；紀錄室的比賽、單季、生涯與球團沿革改為 5 張 DataTable
  - 07-14 自測：`tsc --noEmit`、`build:check` 全綠
  - 07-14 Sonnet-5@Claude Code 查核：tsc/build:check 重跑全綠；本機 API + Chrome DevTools 實測 `/batters`、`/pitchers`、`/records` 375px/1280px × 明暗雙主題，皆 200、零 console error、`document.documentElement.scrollWidth` 無頁面級橫向溢出，排序/連結/tooltip 正常。初次以 `git diff main..HEAD` 比對疑似發現 `/matchups`、`/venues` 被還原成 UX-9 修復前的 ad-hoc 版本；以 `git diff <merge-base>..HEAD` 覆核後確認 UX-8 分支本身未動這兩檔，純因分支早於 UX-9 分岔——實測 `git merge --no-commit` 這兩檔案可自動合併、結果與 main（含 UX-9 修復）完全一致，非真實回歸，予以排除。唯一衝突為 `docs/TASKS.md`（Ledger 重疊列），已人工整併。merge 後移除分支根目錄下的暫存待辦檔 `ux-8.md`（內容已併入本卡 Log）。查核通過，merge 進 main，worktree 已清理。
> Ledger 列（歸檔）：
| UX-8 | 排行與紀錄群 | ruan6047 | Fable-5@Claude Code | GPT-5@Codex | Sonnet-5@Claude Code | `ai/codex/UX-8` | ⚪ | 🏁完成 |

### SEC-NEXT-15520 Next.js 15.5.20 安全升級 〔🔴紅線：前端相依安全〕
- 需求：ruan6047（07-14）　規劃：GPT-5@Codex（已知局部修補）　分支：`ai/codex/SEC-NEXT-15520`
- 執行：GPT-5@Codex　查核：ruan6047（人審；≠執行者）
- 範圍／驗收：將 `next` 由 15.5.4 升至 npm audit 指定的 15.5.20，更新 lockfile；`npm audit --audit-level=high` 不再回報 Next.js critical、`tsc`／`build:check`／瀏覽器 smoke test 綠。不得順手升 React、Tailwind 或改產品程式碼。
- 狀態：🏁完成（merge `8f52e51`，07-14 隨主站 `27f25f0` 部署上線）　Commit：`45fab31`、`8f52e51`
- Log：
  - 07-14 ruan6047 派工；GPT-5@Codex 建立 worktree `/Users/ruanruan/Dev/cpbl-analytics-sec-next-15520`，從 main `397860a` 開始執行
  - 07-14 GPT-5@Codex 升級 `next` 15.5.4→15.5.20（僅 package.json/lockfile）；`npm audit --audit-level=high` 綠，尚有 Next 內嵌 PostCSS 的 2 項 moderate（audit 的唯一 auto-fix 會錯降 Next 9，未採用）
  - 07-14 自測：`tsc`、`build:check`、Ruff、pytest 42 項全綠；Playwright `/`、`/batters`、`/records` 皆 200、zero console/network error/overflow。`npm run lint` 因既有未配置 ESLint 進互動初始化，未混入本卡修正
  - 07-14 ruan6047 人工審核通過，授權合併 main
  - 07-14 主站 submodule bump `27f25f0`；CI `29299476623`、Deploy `29299587846` 成功，線上 `/api/info` 與頁面 smoke test 200

### UX-10 裁判個人頁與賽事裁判報告整合 〔⚪一般〕
- 需求：ruan6047（07-11；07-14 重整範圍）　規劃：Sonnet（沿既有 API 的 UI／導覽規劃）　分支：`ai/antigravity/UX-10`
- 執行：Sonnet@Antigravity　查核：GPT-5@Codex（升級查核；≠執行者）
- **資訊架構**：裁判報告由獨立 `/umpires` 頁移入各場 `/games/{sno}` 賽況頁，成為該場主審的判決報告；賽況頁的裁判姓名改為連至 `/people/umpire/{name}` 裁判個人頁。主選單移除「裁判報告」，但保留 `/umpires` 索引路由作為搜尋／深連結入口，不做 404 或刪除既有 API。
- **個人頁**：以既有裁判個人頁為基礎，呈現主審判決摘要、執法位置與可回到各場賽況報告的清單；全數持續標示 TrackMan 覆蓋場數、固定規則好球帶與「推算、非官方」限制。
- **賽事報告**：保留目前逐球好壞球判決、好球帶位置與關鍵漏判呈現；報告只涵蓋主審且僅納入有 TrackMan 的 called 球，沒有追蹤資料時明確退化為「無法評估」，不得以缺值推論裁判表現。
- **邊界**：不估算「誤判預期得利」；該反事實估計 [counterfactual estimation] 與是否產品化，完全交由 ML-UMP1 研究卡處理。
- 狀態：🏁完成（merge `5478ded`，07-14 隨主站 `27f25f0` 部署上線）　Commit：`1dc6e6a`、`cda7cf1`、`9e6ef13`、`5478ded`
- Log：
  - 07-11 自 UX-1 抽出暫緩
  - 07-14 成績預測公開瀏覽取消，改由獨立下架工作處理；`/predict` 規劃完全移交 ML-SIM1／ML-SIM2
  - 07-14 ruan6047 裁示本卡改處理裁判：賽事內報告、裁判個人頁導覽與誤判預期得利可行性
  - 07-14 依 AI_WORKFLOW 拆分一般 UI 與統計紅線：UX-10 採 Sonnet 執行／獨立查核；誤判影響研究移 ML-UMP1 採 Fable＋跨家族或人審
  - 07-14 Antigravity 實作完成：主選單導航移除「裁判報告」；賽況總覽裁判名改連個人頁；BoxTabs 整合「主審報告」Tab，支援動態散點圖、關鍵漏判、容錯範圍與無資料退化；個人頁新增單場 deep-link
  - 07-14 查核退回第 1 次：跨場切換未依 `game_sno` 重置主審報告；另有 `.venv` symlink 未忽略。修復 commit `cda7cf1`
  - 07-14 查核退回第 2 次：僅清空 state 未處理舊請求晚回覆的競態；另有 `next-env.d.ts` 生成差異。修復 commit `9e6ef13`，以延遲舊請求＋client-side 換場確定性重現驗證通過
  - 07-14 GPT-5@Codex 升級最終查核通過：舊請求 cleanup、跨場 state 重設、深連結與無資料退化正確；Ruff、pytest 42、TypeScript、`build:check` 全綠
  - 07-14 主站 submodule bump `27f25f0`；CI `29299476623`、Deploy `29299587846` 成功，線上裁判個人頁 smoke test 200

### PLAYER-BIO 選手生涯歷程＋暱稱＋官方登錄名單  〔⚪一般〕
- 需求：ruan6047（07-15）　規劃／執行：Opus-4.8@Claude Code　查核：ruan6047（人審，逐隊抽驗綽號）
- 產出：`team_roster`（官方登錄名單，現役判定改以此為準）、`person_history`（coach_history 改名，擴及全史球員 2,922 人／128,704 列）、`person_nickname`（924 人，以**人名**為主鍵）。
- **關鍵設計決策（皆由實測推翻初版）**：
  1. 現役＝**登錄名單 ∪ 出賽 ∪ 近三季**：登錄但整季未出賽者 4 人（出賽推導會漏）；有成績卻不在現行名單者 141 人（僅用名單會漏）；近三季涵蓋旅外的古林睿煬／徐若熙／林安可。
  2. 暱稱以**人名**為主鍵而非掛 `players`：郭泰源（小郭）1985–97 在日職、回台只當教練，`players` 根本沒有他——22 筆暱稱屬非球員人物。
  3. 種子必須是**全史球員**：指標性暱稱多屬退休名將（黃平洋＝金臂人），任何「活躍度」條件都會漏。
- **踩過的坑（皆有回歸測試）**：①球員消歧義沿用教練判準（要求「中職教練經歷」）→ 球員無教練經歷、候選歸零，57 人完全沒資料 ②暱稱欄位標籤不統一（綽號別稱／暱稱別號／別號暱稱／暱號別號），只認一種漏近半並錯誤退回內文抽取 → 陳禹勳被抓成早已棄用的「蒼蠅」（ruan6047 指正，正解鄉長／虎神／香腸）③欄位優先會丟掉最著名稱呼（彭政閔「恰恰」只在內文）→ 改取聯集 ④用**姓名** join 導致原住民族名對不上（`吉力吉撈．鞏冠` vs `吉力吉撈鞏冠`，ruan6047 以「撈哥」指正）→ 一律用 `player_id`。
- **附帶修正**：`players` 有 6 位現役球員姓名過期（朱迦恩／魔力藍／王浩原／冉皓燐／魔神龍／楊泯貽）——既有 `_sync_player_names` 因每日排程 07-04 停用而未執行，屬維運缺口；手動同步 27 人，生產與官方名單零不一致。改名球員的暱稱需以**新名**重抓（朱迦恩＝朱朱寶貝／久浪）。
- 狀態：🏁完成（已部署上線＋生產同步）　Commit：`ca042ac`、`49b1833`

### TEAM-HIST1 隊史年表補缺（歷年教練團／球隊異動／二軍獎項）  〔⚪一般〕
- 需求：ruan6047（07-15，提供 twbsball「分類:職棒球隊年表」）　規劃／執行：Opus-4.8@Claude Code　查核：ruan6047（人審）
- 產出（182/246 頁；64 頁為總覽頁與「業餘N年」＝中職成立前，正確略過）：`team_year_staff` 1,010 筆／284 人（**92 人先前完全沒有**，如中村典夫、成田幸洋、石橋文雄等早期日籍教練）、`roster_moves` 1,397、`team_year_awards` 101（**二軍 18 筆，先前 0**）、`player_name_changes` 13。
- **職稱照抄原文**（ruan6047 指正：早期只有「總教練」與「教練」兩級，不得腦補成助理教練）；分佈驗證僅總教練／教練／領隊／副領隊四種。兩種頁面格式並存（早期無分層；近年「一軍/二軍教練團」職稱標在括號內）皆支援。
- **閉環**：新發現的 92 位教練回灌 `person_history` 種子（`--scope staff`），82 人補上生涯歷程——否則查得到「1995 在味全當教練」卻查不到生平。
- **第三方交叉驗證 `championship_managers`**：年度戰績表的總教練欄獨立於維基球隊條目與 twbsball 個人條目。有資料的 **15 個冠軍年 15/15 相符、零不一致**；2007 統一該頁列出呂文生／羅國璋／大橋穰，canonical 選的呂文生確在其中——三來源同指一答案。
- **⚠️ 開卡假設被實測推翻**：原判「歷年改名是唯一無替代來源的缺口，優先級最高」錯誤——182 頁中**只有 3 頁**真的寫了「更改姓名」（7 筆，全部解析成功）。真正權威來源是**官方登錄名單＋gamelog**。
- **自我回歸（測試攔下）**：為修教練「季中換人」箭頭（黃煚隆→林瑋恩＝兩人）而在切分函式加箭頭切分，卻把改名欄的「舊名-->新名」（同一人、語意相反）也切開，改名 7→0 筆；已用 `split_arrow` 參數區隔。
- 狀態：🏁完成（已部署上線＋生產同步）　Commit：`7d58e85`、`49b1833`

### COACH-HIST 歷年教練職務史（twbsball 經歷節）  〔⚪一般〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code　分支：`ai/antigravity/COACH-HIST-FIX`
- 執行：Antigravity　查核：Opus-4.8@Claude Code（≠ 執行）
- 範圍：
  1. 種子名單＝現任 coaches 72＋managers 90（去重）；爬個人條目經歷節（~150 頁，一次抓+手動刷新，照 wiki-data-sources 慣例）
  2. 解析教練職務行 → 新表 `coach_history(name, team_code, pos, from_date, to_date, source, needs_review)`（migration 冪等）
  3. **解析守則（不腦補）**：行格式變異（兼任/代理/客座 前綴保留進 pos）；日期粒度不一（年/年月/年月日，缺月日存年初/年末界）；隊名歷代對映 team_dim（兄弟象→中信兄弟等，對不上→needs_review）；**非職棒職務**（學校/業餘/國家隊）過濾出主表或另欄標注；解析失敗行一律 needs_review 人工檢
  4. 前端：7C 教練頁「教練職務」表改吃 coach_history（歷年時間軸）；7B 球員頁教練身分區塊同源
- 驗收：抽 10 名教練對照 twbsball 原頁人工核對；needs_review 比率報告；`ruff`+`pytest` 綠
- 狀態：🏁完成（已部署＋生產同步，07-15 驗證：生涯歷程 128,704 列／教練頁正常）　Commit：`80a386c`
- Log：
  - 07-12 需求＋開卡；twbsball 人物經歷節路線可行
  - 07-14 實作資料庫表、經歷解析器、全量爬取 133 名教練生平 6646 條。API 與 Web 端均重構完成。
  - 07-14 查核退回：偵測到跨聯盟隊名字串碰撞（東北樂天金鷲誤對中職樂天桃猿）、敘事型髒資料（無年份、長散文）、同名生日守門漏洞（Wiki無生日直接跳過驗證 review=False）。
  - 07-14 修復 by Antigravity（`80a386c`）：改用 `franchises.py` 單一映射＋全歷史隊名表、加 `league` 守門與最長優先比對；敘事列歸 `phase='note'` 且 API 兩處過濾；同名守門重寫為 0/1/N 分支（多人且無生日 → `player_id=NULL`＋needs_review）。已重爬入庫。
  - 07-14 複審 by Opus-4.8@Claude Code → ✅通過（**以本機 DB 實測驗證，非採信 commit 訊息**）：
    - 跨聯盟誤掛中職隊碼 **28 → 0**（平石洋介日職樂天經歷 `team_code` 已為 NULL）；隊碼映射抽驗正確（含易誤判的「中信二軍」2008 → AHH011 中信鯨）。
    - 敘事列 5,384 列歸 `note` 且不進 API；**未矯枉過正**——落入 note 的「總教練」列均為亞冬盟／青棒代表隊／二軍交流盃等單場賽會或新聞敘事，真實任期完整保留（洪一中 1990 兄弟象→2023 台鋼總教練逐段正確；古久保健二 2024–25 樂天一軍總教練入庫，即 2025 冠軍教練）。
    - `ruff` 綠、`pytest` 79 passed。needs_review 比率：整表 1,090/6,646（16%）、實際顯示列 238/1,262（19%）。
    - 前端補 needs_review「待查」標示（教練頁＋球員頁生涯歷程），未驗證資料不再與已驗證資料在畫面上無從區別。
- 待辦（不阻擋結案）：①57 列解析殘渣（如「La New熊隊→總教練」、兄弟飯店隊名被切）②驗收要求的「抽 10 名人工核對」仍無留痕 ③生產尚未部署且 `coach_history` 未同步（生產部署後頁面會是空的，需 Runbook §3 同步）。
  - 07-14 修復實作：
    1. 隊名對照改走 franchises.py 作為單一事實來源；限 `league == '中華職棒'` 匹配，外國一律 `NULL`，加入東北樂天金鷲等關鍵字排除防禦。
    2. 敘事型列（無年份或長散文）於解析時將 phase 標為 `"note"`，並在 API 端點（`people.py` 與 `players.py`）進行 SQL 過濾。
    3. 守門防禦：若同名且 Wiki 無生日（或 DB 無生日）無法互相比對，強制標記 `needs_review = True`，且 `player_id` 設為 `NULL` 阻斷自動歸戶。
    4. 重新全量執行 scraper 過濾數據入庫，更新 pytest 覆蓋各項新案例，全綠通過。
