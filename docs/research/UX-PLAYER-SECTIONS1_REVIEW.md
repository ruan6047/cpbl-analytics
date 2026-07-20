# UX-PLAYER-SECTIONS1 查核報告 — 球員頁分區內容遷移

- **卡片 ID**: [UX-PLAYER-SECTIONS1](file:///Users/ruanruan/Dev/cpbl-analytics/docs/tasks/UX-PLAYER-SECTIONS1.md)
- **Initiative**: `INIT-PRODUCT-UX`
- **變更層級**: `T3` (⚪ 一般)
- **分支/Worktree**: `ai/opus-4-8/UX-PLAYER-SECTIONS1` @ `.claude/worktrees/ux-player-sections1-execution`
- **查核基準 SHA**: `83b71c241a7853d03540ca3bf18afc5d8b5e01f5` (reviewed SHA)
- **查核者**: `Gemini 3.5 Flash (High)@Antigravity` (獨立查核者)
- **執行者**: `Opus-4.8@Claude Code`
- **對照規格**: `docs/tasks/UX-PLAYER-SECTIONS1.md` 與 `docs/design/UX-PLAYER-IA1-DECISION.md`

---

## 結論：退回 (REQUEST_CHANGES) ↩

本分支代碼在四層 IA 骨架、分層載入、稀疏警示與遷移 Map 的靜態安置上皆符合核可規範；然而，在真實瀏覽器互動行為走查中，發現了**一項嚴重的 P1 級滾動高度遺失缺陷**。本卡的前置 IA1 曾發生「執行者連四輪自證 PASS、查核連四輪 FAIL」的現象，根因是本機 API 回應過快掩蓋了真實的 Layout Shift，使得執行者在自測中產生了假陽性。查核者已利用 Playwright 模擬真實瀏覽器點擊，精確定位並證實此項回歸缺陷，特此退回至原執行者進行修正。

---

## 🔍 驗收條件與遷移對帳

### 1. 遷移 Map 逐項對帳 (§2) (PASS)
查核者逐一比對 `docs/design/UX-PLAYER-IA1-DECISION.md` 的遷移對帳表，全部 13 個模組與 Hero、Role Tabs、頁尾說明等已被正確安置，未有遺漏：
- **Hero & Role Tabs**：`hero.tsx` 與 `page.tsx` 保持常駐，符合規範。
- **L1 總覽**：`SeasonSection`、`TraitsChips`、及拆分後的 `SeasonTrendCard`（本季逐場走勢）正確置於 L1。
- **L2 打法／球路**：`TrackingSection`（好球帶）、`QualitySection`（進階細項）、`MovementSection`（投手位移）、`BattedMixSection`（擊球配球）正確置於 L2。
- **L3 分項與對戰**：拆分後的 `CareerTrendCard`（生涯時段）、`VsTeamCard`（對戰各隊表）與 `SplitsSection` 正確置於 L3。
- **L4 生涯**：`CareerSummary`（生涯彙總）、`CareerYearlySection`（生涯逐年表）、`SabrSection` 與 `FieldingSection` 正確置於 L4。
  - *註*：遷移 Map #16 要求「本季守備併同表首列，移除切換按鈕」。執行者於 commit `83b71c2` 補作此條，實測郭天信生涯守備呈現「本季與生涯累計疊加，無切換按鈕」，退役彭政閔自然退回生涯單表，符合預期。
- **資料說明與名詞解釋**：`page.tsx` 頁尾的說明區塊保留。
- **資料請求不複製**：路由 `page.tsx` 中已按 `layers.ts` 的 `needsData` 進行分層按需載入。

### 2. 既有球員 Deep-link 與二軍／退役狀態 (PASS)
- **退役彭政閔 (0000000667)**：直開時 `sec` 解析自動 fallback 為 `career`，當前層為「生涯」，總覽區塊有顯示「本季無登錄紀錄...」之空態引導。
- **二軍張偉聖 (0000004627)**：一/二軍鏡頭預設為 "二軍 (D)"，頁面正常渲染「二軍選手」Badge。逐球追蹤（本季 14 顆樣本）成功觸發低樣本警示「本季僅 14 顆逐球樣本... 以下分布僅供參考」，熱區無法解出部分渲染破折號 "—"，符合狀態契約。
- **投手羅戈 (0000005151)**：L2 標籤自動呈現為「球路」，並正常載入球種位移。
- **鍵盤導覽**：在 `SubNav` 上使用 ArrowRight / ArrowLeft 鍵能正常切換並觸發 URL 的 `?sec=` 同步，且焦點跟隨（符合 WAI-ARIA tablist 契約），初次載入時焦點未被強搶。
- **375px 行動版適配**：在 375px 寬度下五種情境均無水平溢出（`scrollWidth` 恆等於 375px），且無 Console Error。

---

## 🚨 Blocking Findings 紀錄

### P1 缺陷：雙棲選手切 role 滾動位置大幅彈回 (Layout Shift 觸發瀏覽器 Scroll Reset)

- **嚴重級別**：`P1` (嚴重可用性缺陷，違反「切 role 切層不應將用戶彈回頁首」紅線)
- **可重現步驟**：
  1. 訪問：`http://localhost:3012/players/0000003563?sec=splits` (雙棲余德龍)。
  2. 滾動頁面至 `scrollY = 400`。
  3. 用滑鼠點擊能力卡下方的「投球」Role 切換按鈕。
  4. 觀察：`scrollY` 瞬間歸零（彈回頁首）。
- **證據與根因分析**：
  查核者在 Playwright 測試中，利用 `window.__isSpaMarker` 監控確認了切換過程中**並未觸發傳統的整頁 Refresh (Full Page Reload)**，它是純粹的 SPA 路由跳轉。
  但在點擊「投球」後的 50ms 內，`scrollY` 已經變為 0，此時 `pageHeight` 從 2488px 短暫縮水後恢復為 2286px。
  
  進一步測試顯示，**若在點擊前將 scrollY 設為安全的 100px (此時滾動位置仍在常駐的 PlayerHero 內)，切換 role 後 scrollY 能完美保留在 100px**。
  
  這徹底證實了根因：在 `page.tsx` 中，當 `role` 改變時，多個 `useEffect` 會立刻將 `vsTeam`、`careerMonthly`、`trend` 等多個資料狀態重設為 `null`：
  ```typescript
  // page.tsx
  useEffect(() => {
    setTrend(null);
    setVsTeam(null);
    ...
  }, [id, role]);
  ```
  在 Next.js 的 client-side 重新 fetch 期間，整個 L3 (`splits`) 下方的三個大型模組（生涯趨勢圖、對戰各隊表、分項明細表）因為 state 變為 `null` 而同時卸載 (Unmount) 或轉為矮小的 Loading/Empty 狀態。這導致**網頁的高度在一瞬間大幅度縮水**至低於 400px。
  
  此時瀏覽器檢測到「當前 scroll 偏移量 (400px) 已大於網頁最大可滾動高度」，**被迫將滾動條強行彈回 0**。隨後 API 回應（本機快，但仍有幾毫秒的微小延遲），組件重新渲染撐開高度，但滾動位置已被永遠留在了 0 處。
  
  此缺陷在本機執行時，由於本機 API 回應在極短的 compositing 幀內完成，可能形成 race condition 的假陽性（有時瀏覽器來不及 reset scroll 就被重新撐開的高度挽救）；但在真實網路或模擬的 slow-cpu 情況下，100% 會被觸發。

- **處置建議**：
  在 `role` 或 `seasonKind` 改變觸發 effect 重新 fetch 時，**不要**在 effect 開頭粗暴地調用 `setVsTeam(null)` 讓舊的 DOM 高度消失。
  改採 **Stale-While-Revalidate (SVR)** 模式：在 API fetch 未返回前，保留並顯示上一次的資料（或讓組件內部使用帶有固定 `min-height` 的 Skeleton 骨架預留高度），直到新資料返回後才無縫替換，以此消除 Layout Shift，保護瀏覽器的 scroll 記憶。

---

## 📝 品質閘門查核結果

1. **後端 pytest**：`357 passed, 1 skipped` (全綠)。
2. **後端 ruff**：`All checks passed`。
3. **前端單元測試**：`77 passed` (全綠)。
4. **前端編譯檢查**：`npx tsc --noEmit` 無報錯；`npm run build:check` 完美通過。
5. **分支污染檢查**：本執行分支修改範圍侷限於 `web/src/app/players/[id]/` 下，**未攜帶任何 `docs/control-plane/**` 或 `docs/TASKS.md` 的變更**，符合 contract 契約。
6. **Commit Trailer 檢查**：實作 commit 均帶有 `Requested-by` 與 `Implemented-by` trailer，符合規範。

---

### Review 處置與交接
由於發現 P1 級別可用性回歸缺陷，本次查核判定為 **REQUEST_CHANGES**。任務將退回原執行者，iteration 遞增至 2，worktree 保留。請原執行者針對上述 Layout Shift 引起的 scroll 彈回進行修復。
