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
