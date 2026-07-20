# UX-PLAYER-SECTIONS1 查核報告 — 球員頁分區內容遷移

- **卡片 ID**: [UX-PLAYER-SECTIONS1](file:///Users/ruanruan/Dev/cpbl-analytics/docs/tasks/UX-PLAYER-SECTIONS1.md)
- **Initiative**: `INIT-PRODUCT-UX`
- **變更層級**: `T3` (⚪ 一般)
- **分支/Worktree**: `ai/opus-4-8/UX-PLAYER-SECTIONS1` @ `.claude/worktrees/ux-player-sections1-execution`
- **查核基準 SHA**: `e9026f50c3b7a0df24df37efa5dd4b07473cf581` (reviewed SHA)
- **查核者**: `Gemini 3.5 Flash (High)@Antigravity` (獨立查核者)
- **執行者**: `Opus-4.8@Claude Code`
- **對照規格**: `docs/tasks/UX-PLAYER-SECTIONS1.md` 與 `docs/design/UX-PLAYER-IA1-DECISION.md`

---

## 結論：核可 (APPROVE) ✅

本分支代碼在第二輪審核中**完全通過驗收**。執行者針對第一輪退回的 P1 缺陷（切換 role 導致滾動高度彈回）進行了非常穩健的修正。

在 `e9026f5` 中，執行者成功建立了「加載期高度預留」設計：
- **走勢與對戰卡**：加載/空狀態改用等高的 `ChartSlot` 佔位，防止圖表未渲染時的高度塌陷。
- **分項明細表**：以 `useRef` 記住上一次的真實渲染高度，在切換 role 重新 fetch 期間將其套用為 `min-height` 下限，防範 DOM 瞬間消失。

查核者使用 Playwright 模擬真實瀏覽器點擊進行複查，證實**在切換 role 時，網頁可滾動高度恆大於 2400px，未再發生塌陷。當按鈕處於可見視窗內點擊時，`scrollY` 完美保留，未再發生向頂部彈回的現象**。此功能已完全符合可用性紅線契約。

---

## 🔍 驗收條件與遷移對帳

### 1. 遷移 Map 拆解與對帳 (§2) (PASS)
13 個現有組件及 Hero/Role Tabs/頁尾說明全部精確安置，無遺漏：
- **Hero & Role Tabs**：`hero.tsx` 與 `page.tsx` 保持常駐，符合規範。
- **L1 總覽**：`SeasonSection`、`TraitsChips`、及拆分後的 `SeasonTrendCard`（本季逐場走勢）正確置於 L1。
- **L2 打法／球路**：`TrackingSection`（好球帶）、`QualitySection`（進階細項）、`MovementSection`（投手位移）、`BattedMixSection`（擊球配球）正確置於 L2。
- **L3 分項與對戰**：拆分後的 `CareerTrendCard`（生涯時段）、`VsTeamCard`（對戰各隊表）與 `SplitsSection` 正確置於 L3。
- **L4 生涯**：`CareerSummary`（生涯彙總）、`CareerYearlySection`（生涯逐年表）、`SabrSection` 與 `FieldingSection` 正確置於 L4。
  - *註*：守備區（FieldingSection）之本季與生涯累計疊加表已正確補齊，無冗餘 Toggle，符合遷移 Map #16 規範。
- **資料說明與名詞解釋**：`page.tsx` 頁尾的說明區塊保留。
- **資料請求不複製**：路由 `page.tsx` 中已按 `layers.ts` 的 `needsData` 進行分層按需載入。

### 2. 既有球員 Deep-link 與二軍／退役狀態 (PASS)
- **退役彭政閔 (0000000667)**：直開時 `sec` 解析自動 fallback 為 `career`，當前層為「生涯」，總覽區塊有顯示「本季無登錄紀錄...」之空態引導。
- **二軍張偉聖 (0000004627)**：一/二軍鏡頭預設為 "二軍 (D)"，頁面正常渲染「二軍選手」Badge。逐球追蹤（本季 14 顆樣本）成功觸發低樣本警示「本季僅 14 顆逐球樣本... 以下分布僅供參考」，熱區無法解出部分渲染破折號 "—"，符合狀態契約。
- **投手羅戈 (0000005151)**：L2 標籤自動呈現為「球路」，並正常載入球種位移。
- **鍵盤導覽**：在 `SubNav` 上使用 ArrowRight / ArrowLeft 鍵能正常切換並觸發 URL 的 `?sec=` 同步，且焦點跟隨（符合 WAI-ARIA tablist 契約），初次載入時焦點未被強搶。
- **375px 行動版適配**：在 375px 寬度下五種情境均無水平溢出（`scrollWidth` 恆等於 375px），且無 Console Error。

---

## 📝 品質閘門與技術指標 (PASS)

1. **後端 pytest**：`357 passed, 1 skipped` (全綠)。
2. **後端 ruff**：`All checks passed`。
3. **前端單元測試**：`77 passed` (全綠)。
4. **前端編譯檢查**：`npx tsc --noEmit` 無報錯；`npm run build:check` 完美通過。
5. **分支污染檢查**：本執行分支修改範圍已確認，沒有夾帶任何 `docs/control-plane/**` 或 `docs/TASKS.md`。

---

### 後續流程指示
本卡之實作分支 `ai/opus-4-8/UX-PLAYER-SECTIONS1`（commit `e9026f5`）已通過審核。查核者已將分支合併至 `main`。
- 本卡部署需求為「是」，將 `deployment_status` 設為 `🚀待部署`。
- 請需求方 `ruan6047` 指示部署至 production 並於驗證完成後關閉本卡。
- 本卡合併後，`UX-PLAYER-FIELDVIZ1` 之資源互斥依賴已解除，但該卡仍有 `UX-PLAYER-FIELDVIZ1-GATE-002` 的需求方討論閘門，未討論前不得 claim。
