# UX-TOKEN-ACCENT-CONTRAST1 accent 在 surface-2 底上未達 WCAG AA〔T2；🟦前端〕

- 需求：ruan6047（2026-07-31 於 `UX-BRAND-HOME1` 的獨立 Design Gate 審查中發現，裁定另開卡）　規劃：本卡 spec　分支：`ai/<執行者>/UX-TOKEN-ACCENT-CONTRAST1`
- 執行：待指派（建議 L2；全站色彩 token 調整，模式已知但需逐頁回歸）　查核：待指派（建議 L2；≠ 執行）
- Initiative：`INIT-PRODUCT-UX`　spec 基線：`UI_UX_SYSTEM` v1 §2.1／§8
- review_independence: [cross_family]
- DB：`db_scope: none`
- 部署：是（前端）　環境：生產　PR：—　Merge SHA：—
- 範圍：`web/src/app/globals.css`（token 值）＋ 受影響頁面的回歸驗證
- Discovery：**本卡第一項交付是「該改哪一個 token」的判斷**，不是直接改值。三條路徑各有代價，見〈Discovery 必答〉。
- Design：Design Gate 需求方人工審——本卡會改變全站觀感（accent 是行動／焦點色，出現在每一頁）。

## 問題陳述

`--color-accent`（淺色 `#d62839`）在 `--color-surface-2`（`#eef2f7`）底上的對比為 **4.42:1，未達 WCAG AA 對一般字級要求的 4.5:1**。

實測數據（以 WCAG 相對亮度公式計算）：

- accent `#d62839` on `surface` `#ffffff`：**4.97:1** ✅
- accent `#d62839` on `paper` `#f5f7fa`：**4.63:1** ✅
- accent `#d62839` on `surface-2` `#eef2f7`：**4.42:1** ❌
- 深色 accent `#ff5a6a` on 深色 `surface-2` `#1a2c44`：**4.65:1** ✅

也就是說**只有淺色模式的 `surface-2` 這一組不合格**，其餘組合都過。`surface-2` 依 `UI_UX_SYSTEM` §1-2 是三層底色的第三層（`paper → surface → surface-2`），用於「卡內強調區／圖表格線／空態底」（`globals.css:36` 註解），是高頻底色。

發現經過：`UX-BRAND-HOME1` 規劃 hero（底色 `bg-surface-2`）時，外部設計審查者指出對比臨界，稱「約 4.65:1 極為臨界」；Coordinator 實算為 4.42:1——**審查者方向正確但數字錯誤，且低估了嚴重度：這不是臨界通過，是不通過**。

## 非目標

- **不改 `--color-accent` 的語意**（行動／焦點）。這是 `UI_UX_SYSTEM` §1-3 的既定角色，本卡只處理數值與用法。
- 不處理其他 token 的對比問題（如 `text-faint` 在 Lighthouse 曾被報過，屬既有議題）。若掃描時順帶發現，記錄但不修。
- 不改深色模式的 accent（實測通過）。

## Discovery 必答（先答再改值）

1. **實際受影響的範圍有多大？** 全站有多少處是「accent 文字 ＋ surface-2 底」且字級小於大字門檻（<24px 且 <18.66px 粗體）？**要用掃描結果回答，不要估。** 若只有個位數處，選項 C（逐處改用色）可能比動 token 划算。
2. **三條路徑選哪條？**
   - **A. 調暗 `--color-accent`**：一次解決所有組合。代價是全站觀感改變，且 accent 在 `#ffffff` 上本來就過（4.97），為了第三層底色而讓主色變暗，可能得不償失。
   - **B. 調亮 `--color-surface-2`**：從 `#eef2f7` 往 `#f4f7fa` 方向。代價是三層底色的層次感被壓縮，`paper`／`surface`／`surface-2` 的區辨度下降——而三層底色是 §1-2 的核心原則。
   - **C. 不動 token，改用法**：規定 accent 小字不得用於 surface-2，改用 `ink`／`cpbl`。代價是規則變複雜、要靠人記，且沒有機制守。
3. **要不要加自動守衛？** 是否可寫一條測試／腳本掃描「語意色 × 底色」的組合並計算對比，讓未來的違規被擋下？**若可行，這比改一次值更有價值**；若不可行，明講為什麼，不得宣稱有守衛而實際沒有。
4. **`--color-up`（`#1d6fb8`）與其他語意色在三層底色上的對比是否也有同類問題？** 本卡不修，但要一次算清楚並記錄，避免下次又是「發現一個修一個」。

### Discovery 書面答案（iteration 2）

1. **實際影響範圍：10 個靜態 JSX site（production 7、`/dev` 3）。** 先以
   `rg -o --glob '*.{ts,tsx}' 'text-accent(?:/[0-9]+)?' web/src | wc -l` 找到 86 個
   `text-accent` token、分布 37 檔；再以 TypeScript AST 掃描帶 `bg-surface-2` 的 JSX
   ancestor 與 `text-accent` descendant，得到 15 個候選。逐一排除 4 個只在 hover／互斥
   conditional branch 才會成立的假陽性，以及 1 個 `text-2xl`（24px，已達大字門檻），
   剩下 10 個一般字級 site：
   - production 7：`ui.tsx` 3、`daily-hub.tsx` 1、`games/page.tsx` 3；
   - `/dev` 3：`dev/player-ia/sections.tsx` 1、`variant-view.tsx` 2。

   AST 掃描以 `node --input-type=module -e` 載入 `typescript`，對每個 TSX 的 `className`
   文字收集 `bg-surface-2` ancestor，再列出含非 hover `text-accent` 的 descendant；完整候選
   行號留在本輪 handoff evidence。這個計數是靜態 JSX site，不宣稱等於 runtime 元件實例數。
2. **採路徑 A（調暗語意色）。** 10 個 site 已橫跨共用元件、首頁與賽程；選 C 會把單一
   token 契約改成依 ancestor 背景判斷的人工規則，且 Tailwind class composition 無法可靠用
   純字串 lint 防守。選 B 會壓縮 `paper／surface／surface-2` 的結構層次並影響所有中性容器。
   A 的色差小、一次修正所有既存與未來組合，且可由數值守衛完整驗證，維護成本最低。
3. **加兩層自動守衛。** `color-contrast.test.ts` 從 canonical `globals.css` 解析 5 個一般
   文字語意色 × 3 底色 × 2 模式共 30 組，門檻 4.60:1，並守 `accent/down` 共色；
   `chart-theme.test.ts` 另守 `LIGHT_FALLBACK` 的 `up/down/accent/cpbl` 必須鏡像淺色 CSS，
   避免 SSR／首次繪製使用過期副本。前者不涵蓋 faint、圖表分類／隊色／status、alpha
   背景與 runtime 巢狀組合；後者只守 fallback 與 CSS 的資料一致性，不替代元件視覺回歸。
4. **其他語意色確有同類問題，已據實處理。** 舊 `amber #b45400` on 淺色
   `surface-2` 只有 4.44:1；舊深色 `cpbl #5a8fe0` on 深色 `surface-2` 只有 4.33:1，
   因此分別修為 `#b15100` 與 `#5c95e2`。`up` 舊值最差 4.65:1，維持不動。新矩陣
   30 組全數 ≥4.60:1，最差為深色 cpbl on surface-2 的 4.61:1；完整表見
   `docs/design/UI_UX_SYSTEM.md` §2.1。

## 紅線

1. **不得只驗改動的那一組。** 任何 token 值變更都要重算**該色在三層底色 × 深淺兩態**的全部組合，附計算結果，不得只證明目標組合修好了。
2. **不得宣稱「全部合規」而未附窮舉證據。** 依既有教訓（`completeness-claims-must-be-generated`），完整性宣稱須由腳本自動產生，不得人工聲明。
3. 深色模式現行通過，**改動後不得使其退化**。

## 驗收條件

- [ ] Discovery 四問有書面答案，第 1 問附掃描計數與指令。
- [ ] 選定路徑並落地，且 accent 在三層底色 × 深淺兩態的全部六種組合皆有計算結果，不合格者為零或已明確標為「僅限大字」並附受限清單。
- [ ] 第 4 問的其他語意色對比表已產出並記錄（本卡不修）。
- [ ] 若採自動守衛：涵蓋範圍與**不涵蓋範圍**都明寫在測試 docstring。
- [ ] `UI_UX_SYSTEM.md` §2.1 同步記錄結論（值變更或用法限制）。
- [ ] `uv run ruff check` ＋ `uv run pytest` ＋ `cd web && npm test` ＋ `npm run build:check` 全綠。

## 驗證

- [ ] 需求方人工審：token 值若變更，須實際看過全站主要頁面的觀感差異後才放行。
- [ ] 查核者以獨立計算重現對比數字（不採信卡面或執行者提供的數值）。
- [ ] 查核者實測深淺兩態，不得只驗淺色。
- [ ] 查核通過前不得 merge main。

## 邊界

- 只改 `globals.css` 的 token 值或新增用法規範，不改元件結構。
- 預估 S～M（Discovery 是主體；若選 C 則改動極小）。

## Log

- 2026-07-31 register by Claude Opus 5@Claude Code（依 ruan6047 指示）；iteration 0。來源：`UX-BRAND-HOME1` 獨立 Design Gate 審查第 7 點。需求方裁定「兩者都做」——`UX-BRAND-HOME1` 內先以紅線約束用法（accent 在 surface-2 上只能用大字），token 本身是否調整由本卡獨立驗收。
- 2026-08-02 iteration 2 by GPT-5@Codex：依獨立查核 REJECT 補 `LIGHT_FALLBACK` 同步與語意色 drift 守衛，重寫 §2.1 對比矩陣，並補齊 Discovery 四問與 canonical 文件殘留 hex。
