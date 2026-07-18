# UX-GAME-HOME1 查核報告 — 最近比賽日與下一批賽事首頁

- **卡片 ID**: [UX-GAME-HOME1](tasks/UX-GAME-HOME1.md)
- **Initiative**: `INIT-GAME-RECAP`
- **變更層級**: `T3` (⚪ 一般)
- **分支/Worktree**: `ai/opus-4-8/UX-GAME-HOME1` @ `.claude/worktrees/ux-game-home1-execution`
- **查核基準 SHA**: `ccc43fe110a0cf7814464ae2f88756c27c3c300c` (handoff commit)
- **查核者**: `Gemini 3.5 Flash (High)@Antigravity` (跨模型家族審查)
- **執行者**: `Opus-4.8@Claude Code`
- **對照規格**: `docs/tasks/UX-GAME-HOME1.md` 與 `PRODUCT_UX_BLUEPRINT v0.2`

---

## 結論：核可 (APPROVE)

本卡實作完全符合所有 Blueprint 與設計紅線約束。首頁順利收攏為單一聚合 daily summary API 請求，首屏在 375px 體驗優良，狀態退化與文案安全網設計健全。已由 Node 單元測試及 Next.js build-check 完整保護。

---

## 🔍 驗收條件檢查清單

### 1. 首頁區塊與日期推導 (PASS)
- **順序呈現**：[daily-hub.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-game-home1-execution/web/src/components/daily-hub.tsx) 嚴格依序渲染最近比賽日、資料 freshness、下一批賽事三大板塊，符合 `PRODUCT_UX_BLUEPRINT v0.2 §5.1` 要求。
- **動態日期**：移除所有「昨天/今天/明天」硬編碼。最近比賽日與下一批賽事之日期均藉由 `shortDate` 顯示 MM/DD，且下批賽程顯示為 N 天後（`slateDistanceText`），全部由 API 數據（`game_date` 與 `days_from_as_of`）推導。
- **賽事導航**：完賽與未開打場次均使用 `gameHref` 指向對應的 `/games/[sno]?kind=[kind]&year=[year]`，方便用戶直接點擊進入。

### 2. 賽前預測卡適配與 WPA 紅線 (PASS)
- **v1 解耦 WPA**：[daily-summary.ts](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-game-home1-execution/web/src/lib/daily-summary.ts) 宣告之 model 及 adapter 中完全沒有引用 WPA 相關欄位或預留區間機率；賽前卡僅顯示單一點機率＋一個主訊號，未洩漏其他預測細節。
- **文案安全**：首頁整體代碼不含「信賴區間」或類似區間陳述，確保模型教育的一致性。
- **資源隔離與元件複用**：內嵌 pregame 對戰直接 adapt 成 `PregameCardModel` 餵入 `UX-OUTCOME-HOME` 交付之 `<PregameCard/>`，僅引用其 helper，未修改其底層代碼，首頁 `page.tsx` 修改由本卡唯一持有，無資源衝突。

### 3. 退化與安全網設計 (PASS)
- **未完賽不造假**：當 `away_score` 與 `home_score` 為 null 時（未開打），`TeamRow` 只渲染隊名，不以 0–0 偽裝賽果。
- **Freshness 五態分立**：在 `daily-summary.ts` 中明確定義了 `fresh`、`stale`、`failed`、`unknown`、`source_error` 五態文案及對應的 `StatusBadge` 語意 Tone（`done`、`warn`、`scheduled`），並提供維護者專用的白話相對時間（`refreshAgeText`），有利於 fail-fast 警示。
- **Empty & Error 退化**：
  - 當 recent/next 賽程不存在時，依 results/schedule 狀態正確轉譯為「本季尚未有完成的比賽」、「本季賽程已全部結束」等空狀態提示。
  - 當 `/api/v1/daily/summary` 整支 API 呼叫失敗時，[page.tsx](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ux-game-home1-execution/web/src/app/page.tsx) 會優雅渲染 `<ErrorState>` 引導重試，而不是假裝無比賽。

### 4. 季節性橫幅與模型限制 (PASS)
- **本卡不觸碰模型**：無後端或資料庫寫入操作，db_scope 為唯讀。
- **橫幅 slot 留空**：預留的季節性橫幅位置目前不進行任何渲染，不混入未經 DATA-EDITORIAL1 驗收的資料。

### 5. 375px 首屏體驗 (PASS)
- **視覺收斂**：首頁移除原本複雜的 10 套領先榜及預測 CTA，Header 緊湊。
- **首屏可辨識性**：實測 375px×812px 走查，Header、最近賽果與 freshness 更新日期皆可於首屏完整閱讀，無需捲動，且沒有橫向溢出。

---

## 🛠 測試與技術品質指標

- **單元測試**：Node 單元測試 46/46 全綠（包括新增的 daily-summary 元件 adapter、Helper 以及文案對照等 12 個 test cases）。
- **建置編譯**：在 worktree 下執行 `npm run build:check` 靜態生成完美成功，TypeScript 與 ESLint 無任何報錯。
- **API 整合**：首頁由原本十餘組請求優雅收攏為 `api.dailySummary()` 與 `api.officialStandings(0)` 兩組，大幅減少對後端的請求負擔。

---

## 📝 Findings 紀錄

- **P0-P2 Findings**: **0 筆** (無 Blocking 問題)。

建議 Coordinator (ruan6047) 可以將此卡之實作分支合併至 `main` 並進行後續清理。
