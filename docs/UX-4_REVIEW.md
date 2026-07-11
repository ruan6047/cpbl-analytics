# UX-4 查核報告 — 骨架導覽＋標準頁面解剖落地

> 卡：[`TASKS.md`](TASKS.md) UX-4　分支：`ai/antigravity/UX-4`　查核基準 commit：`751b10b`
> 查核者：Gemini-3.5-Flash@Antigravity（審查）　執行者：待修正後回交盲測
> 對照 spec：[`UX_REDESIGN_SPEC.md`](UX_REDESIGN_SPEC.md) §A 八原則 / §B 通用層 UX-4

## 結論：暫不核可（需回修）

整體方向正確——header 導覽（10 項、三分組）、footer 強化、響應式行動端漢堡選單、多頁 `<header>` 標題解剖都有落地，`build:check` 綠。但有 **2 個實作缺陷（無效 class/動畫）**、頁面解剖**落地不完整且不一致**，以及數個無障礙/穩健性缺口，需回修後重跑盲測。

---

## 🔴 必修（實作缺陷 / spec 違反）

- **`web/src/components/nav-links.tsx` — `active:bg-surface-3`**
  專案只定義 `surface`／`surface-2`（見 `globals.css` L34-36、原則 2「三層底色，不新增灰階」）。`surface-3` **不存在** → 死 class（active 按壓態底色沒生效），同時字面違反「禁止第四層灰」。改用既有 token（如 `surface-2`）。

- **`web/src/components/nav-links.tsx` — `animate-[fadeIn_0.15s_ease-out]`**
  `globals.css` 只有 `@keyframes barGrow`（L173），**沒有 `fadeIn`** → 面板入場淡入動畫實際無效。補一個 `@keyframes fadeIn`，或移除這個無效 class（否則是誤導性程式碼）。

## 🟠 遺漏 —「各頁標題與區塊結構一致」未達成（本卡核心驗收項）

commit 訊息稱「9 頁標題解剖落地」，但仍有頁面沒對齊標準（`mb-6` + `h1.text-2xl font-extrabold tracking-tight text-ink` + `p.mt-1.5`）：

- **`web/src/app/matchups/page.tsx` L77-79** — 整頁漏遷移，仍是舊樣式 `mb-5` / `font-bold` / `mt-2`。此頁在 NAV 內（投打對決），屬本輪範圍。
- **`web/src/app/games/[sno]/page.tsx` L443** — 同一檔案中直播態 h1 仍是舊 `text-2xl font-bold`，只有歷史態（L432）被遷移 → 同頁兩種標題長相，正是「結構不一致」。
- **`web/src/app/players/[id]/hero.tsx` L61** — 旗艦頁 h1 用 `text-3xl font-bold text-ink`，字級/字重與全站標準（2xl / extrabold）不同。
- **`web/src/app/teams/[code]/page.tsx` L60** — 隊名是 `<div class="text-2xl font-extrabold">`，該頁沒有任何 `<h1>`（違反「h1+副標」解剖與 a11y 大綱）。此次只把 `font-bold` 改 `font-extrabold`，沒補上 h1 語意。

> 建議：明確界定本卡負責哪些頁；至少把 NAV 內全部頁（含 `matchups`、`games/[sno]` 兩態、`teams/[code]`）統一，並補 `teams/[code]` 的 `<h1>`。若 `players`/`teams` 明確歸 UX-7，也應在卡上白紙黑字排除，避免「一致」驗收落空。

## 🟡 無障礙 / 穩健性（建議修）

- **行動端選單缺 Esc 關閉與焦點陷阱**：面板用 `role="dialog" aria-modal="true"`，但沒有 `Escape` 關閉、開啟時焦點沒移入面板、關閉後焦點沒還給按鈕、Tab 也不被困在面板內。對 modal dialog 是標準要求。
- **`aria-haspopup="true"`** 對 dialog 面板語意偏弱，建議 `aria-haspopup="dialog"`（或 `"menu"` 視實際互動模型）。
- **`top-[57px]` 魔術數字**：面板起點硬編 57px 對齊 header 高度，header 內距/字級一變就會露縫或蓋住。建議用 sticky header 實際高度變數或讓 header/面板共用一個高度 token。
- **桌機 nav 移除了 `flex-wrap`**：原本 `flex-wrap`，新版桌機為 `hidden md:flex`（單行不換行）。10 連結＋2 分隔＋logo＋主題鈕，在 `md`（768px）附近可能水平溢出（原則 6：無橫向溢出）。需在 768–900px 實測，或保留必要時換行/縮字級。
- **active 態用 `cpbl` 品牌色**（`bg-cpbl/10 border-cpbl/20 text-cpbl`）：原則 3 規定「行動/焦點＝accent」，桌機 active 也用 `border-accent`。行動端 active 卻用品牌藍，語意不一致，建議統一為 accent。

## 🟢 已正確處理（免修）

- NAV 為 10 項、分「賽事／數據／預測」三組，符合 spec §B「10 項導覽的分組/優先序」。
- reduced-motion 已由 `globals.css` L152 全域 `*` 規則覆蓋，`scale`/transition 會被抑制（原則 7 過關）。
- footer 補版權、上邊框與 RWD 排版，合理。
- 桌機 active 態 `border-accent` 語意正確；`aria-current`、skip-link、`:focus-visible` 焦點環都在。

---

## 建議驗收動線

1. 修必修兩項（`surface-3`、`fadeIn`）。
2. 補齊/統一標題解剖（尤其 `matchups`、`games/[sno]` 直播態、`teams/[code]` 補 `h1`），或在卡上明確劃出範圍。
3. 行動選單補 Esc + 焦點管理；桌機 nav 於 375/768/1280 三檔實測無橫向溢出（原則 6 量測：`scrollWidth ≤ viewport`）。
4. 按 spec §A「量測而非目視 + 375/1280 雙檔 + console 零錯誤」重跑，再交查核者盲測。
