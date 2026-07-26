# UX-PA-SIM-MATCHUP1 Matchups 單一打席結果分布〔T4；🔴統計／ML〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`claude/ux-pa-sim-matchup1-b6941f`
- 執行：Claude Opus 5@Claude Code（07-25）　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋ml-sim1-review
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.9、§6；[`ml-sim1-review.md`](../../ml-sim1-review.md)
- Discovery：PA 模擬能解釋單次對決但未改善整場 weighted-WP　Design：首版只進 `/matchups` 第二 tab「如果現在對決」

## 目標與驗收

- [x] 只有選定具體打者×投手後可切入第二 tab，與歷史實績／EB 洞察清楚分離；UX-MATCHUP1 fail-closed 不被繞過。
- [x] 顯示結果分布、輸入情境、模型版本與限制；不得包裝為整場勝負提升，區間不得稱信賴區間。
- [x] unavailable、unsupported、artifact missing、API error 各自退化，且不產生替代機率或預設「天敵」。

## 驗證與依賴

- 驗證：固定 fixture 契約測試、文案紅線、校準／總和對帳、375 px／鍵盤走查、T4 跨家族或人工查核。
- 依賴：UX-MATCHUP1；不得順便建立真實打席入口。
- 預估範圍：M。

## Log

- 2026-07-17 註冊（REGISTER-001）：依賴 UX-MATCHUP1，遵守 ML-SIM1 紅線。
- 07-25 claim（CLAIM-002 @ main c615bcd）：需求方 ruan6047 指派 Opus 5 執行，並明確核可超出 WIP limit（agent 4/4 → 5/4）；同時裁決人工審核走生產唯讀 API＋fixture 覆蓋退化態，故 `db_scope` 維持 read（不在本機跑 `run_train_pa_sim`，該流程會寫 `model_versions`）。
- 07-25 實作（範圍：`web/src/components/matchups/**`＋`web/src/app/matchups/matchups-client.tsx`）：
  - `api.ts` 鏡射 `/api/v1/outcome/plate-appearance` 契約（7 種互斥結果、`probability_interval_90`、`shrinkage_weight`），新增 `plateAppearance()` fetcher。
  - `pa-sim-state.ts`：六種非 ok 態判定純函式（unsupported／artifact_missing／unavailable／api_error＋league_fallback／invariant_failed）、紅線文案常數、視角換算（`batterSideDelta`／`batterSideWinProbability`）、總和對帳（容差 1e-6）。**判定只用 API 明示欄位，前端零統計運算。**
  - `pa-sim-panel.tsx`：結果分布（出局／上壘兩組、固定顯示序、機率條＋90% 區間＋打者方 delta＋轉移樣本）、假設情境五軸控制、樣本與模型版本揭露、圖表文字替代列表。
  - `explorer.tsx`：`enablePaSim` prop（預設 false）＋ `MainTabs` 單組對決檢視；tab 與面板只存在於 `pid && opp` 分支，換主角／換對手重置回歷史實績。
  - 統計紅線落地：**league_fallback 是本卡核心 gate**——生產 API 對模型未見球員仍回 `available:true` 與完整機率（純聯盟先驗，實測 `hitter=0000000001` → `hitter_pa=0`／`shrinkage_weight.hitter=0.0`），UI 一律拒絕顯示，避免把聯盟平均當成該球員估計。
- 07-25 測試（`npm test` 158 pass；新增 pa-sim-state.test.ts 22 例、pa-sim-panel.test.ts 10 例）：fixture 逐字取自生產回應；**每條防回歸斷言都先對缺陷版本跑紅**（11 次突變：移除／延後 unsupported gate、移除 league_fallback、放寬對帳容差、文案改「信賴區間」與「比現行更準」、面板搬到清單分支、球員頁啟用、補 50% 預設值、退化態改 div、跨行中文）。
- 07-25 瀏覽器走查（3021 → production API，1440px／375px／深色）：ok 態數值與生產 API／fixture 三方一致（9 局下 2 出局滿壘：起點 29.7%、三振 −28.6pt、一安 +63.7pt，且機率分布不隨情境改變）；真實觸發 unsupported（kind=E）、artifact_missing（本機 API 無 artifact）、api_error（停 API）、league_fallback（梁如豪無 2018+ 打席，面板零百分比）；375px 無橫向溢出、情境控制 44px、真實鍵盤 ←→ 切 tab 焦點與 aria-selected 正確。
- 07-25 走查中修正的三個缺陷（截圖看不出、由真實瀏覽器 console／DOM 抓出）：EmptyState 是 `<p>` 而內容放了 `<div>`／`<p>` 造成 hydration error；面板掛載瞬間閃現「無法模擬」（pending 與 unavailable 未分離）；紅線揭露文字用 `text-faint`（對比 2.6:1，設計系統 §2.1 禁承載必要文字）已全數升為 `muted`。三者皆補上守衛測試。
- 07-25 既有 conformance 缺口（**非本卡引入、未修**）：explorer 既有三個查詢 select 高 33px（<44px 觸控門檻）；頁面最外層與 QueryShell 有 4px `scrollWidth` 差（document 無橫向捲動）。留給 `UX-TOKEN-HYGIENE`／conformance 卡處理，本卡不擴張範圍。
- 07-25 需求方人工審核（第一輪，5 項回饋）與範圍裁決：
  1. **改名球員顯示舊名**（象魔力→魔力藍）→ 需求方核可**本卡擴張範圍**修後端（見下一則 note event）。根因：`batter_pitcher_matchups` 姓名欄是爬取當時快照，`/profile` 走當季 `*_current` 故正確，兩者不一致。修法：新增 `display_name()`／`overlay_display_names()` 純函式＋`_display_name_map()`（當季登錄名 → `players` 主檔 → 快照名），套用 `/api/v1/matchups`、`/players/{id}/matchups`、`.../insights` 三處。本機實測 opp_name 與 pair 皆回「魔力藍」，200 位對手零空名，退役者（羅力／潘威倫／伍鐸…）正常退回主檔。突變驗證：停用覆寫 → 2 測試轉紅。
  2. **選定球隊後對手下拉退回全部 11 隊（含 4 支已解散）** → 需求方核可本卡修。根因：交手隊清單綁在顯示用 list 查詢且只在未篩隊時更新（UX-MATCHUP1 既有）。修法：faced 改為獨立 effect、固定以不帶隊別的查詢推導；可選集合抽成 `visibleOpponentFranchises()` 純函式。真實瀏覽器複驗：`team=AEO011` 下拉由 11 → 8 項（解散隊消失）。突變驗證：篩隊退回全部 → 純函式測試紅；faced 綁回 team → 新增 explorer 原始碼守衛測試紅。
  3. 「只看某個狀況」與 4.「改情境 % 不變」→ 需求方裁決**機率本身要隨情境變**。執行者指出這是模型層工作（現行 `pa_sim` 是 context-neutral）且分格計數會使樣本碎化，故註冊 **`ML-PA-SIM-CONTEXT1`**，驗收紅線＝須在同一走查切分勝過現行 context-neutral 版本，預期可能 NO-GO。本卡文案「情境不改變結果機率」在該卡通過前維持正確。
  5. **模擬對某一隊** → 歷史實績已可對隊；模擬對隊需投手群出場比重模型（直接平均會造出不存在的「平均投手」），註冊 **`ML-PA-SIM-TEAM1`**（Backlog，不排優先序）。
- 07-25 第二輪驗證：`npm test` 165 pass（新增 explorer.test.ts 3 例＋controls.test.ts 4 例）、`tsc`、`ruff`、`pytest` **460 passed**（新增 test_matchup_insights_api.py 2 例＋test_matchup_queries.py 3 例；`_FakeCursor` 擴充支援姓名解析查詢 shape）。
- 07-26 跨家族查核 **APPROVE**（Antigravity／Gemini，非 Claude；REVIEW-005 @ `c8bf6ec`）：P0–P2 findings = 0。查核者獨立重跑全套測試（ruff／pytest 460／tsc／npm test 165／build:check）並**自行重做 4 次突變驗證**（移除 league_fallback gate、`SUM_TOLERANCE` 放寬至 0.5、文案植入「信賴區間」、移除現用名覆寫）皆如預期轉紅；核心紅線 league_fallback 實測「全頁零百分比」；七結果總和 1.0000000000000002（< 1e-6）。**執行者交付時自陳未驗證的「球員頁不得出現模擬 tab」已由查核者以本機 Next dev（port 3025）實測補足。**
- 07-26 查核 P3 建議（不阻擋 merge，**留待未來 API 網路優化卡處理，執行前須先討論**）：`explorer.tsx` 冷啟動且已選定隊別時會連續發兩次 `list` 請求（一次帶隊別供顯示、一次不帶隊別供推導交手清單）。正確性與穩定度無虞（有 stale 守衛與 `scopeKey` 判定），建議未來改由 `list` 回應附帶 `faced_franchises` metadata，省一次 RTT。本卡不處理——那會把單純的顯示層修正擴張成 API 契約變更。
