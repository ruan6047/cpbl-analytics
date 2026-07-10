# CPBL Analytics 專案理解與 UI/UX 改善提案

本文件提供對 **CPBL Analytics** 專案的深入理解，並針對目前的 UI/UX 設計提出具體的修改規劃與改進建議。依據您的要求，此階段為**研究與規劃**，不進行實際的程式碼修改。

> **職責歸屬 (Provenance)**（規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)）
> - 需求提供方 [Requested]：ruan6047　規劃 [Plan]：規劃 AI（外部）　日期：2026-07-08
> - 狀態：規劃完成 → 轉 [`UI_IMPLEMENTATION_CHECKLIST.md`](UI_IMPLEMENTATION_CHECKLIST.md) 執行；已經 Claude-Opus-4.8 稽核（修正見 checklist）
> - 對應看板卡：[`TASKS.md`](TASKS.md) UI-1~5

---

## 一、 專案架構與核心功能理解

經由對程式碼與專案結構的梳理，CPBL Analytics 是一個功能完整且精緻的中華職棒（CPBL）進階數據分析與賽事預測系統：

### 1. 技術棧與前端架構
*   **前端框架**: Next.js 15 (App Router, TypeScript)
*   **樣式與主題**: Tailwind CSS v4 (使用 `@theme` 定義設計系統 Token)，全域變數搭配 `globals.css`。
*   **資料視覺化**: 使用 `recharts` 繪製能力雷達圖，以及自訂的 SVG 擊球分佈圖、走勢圖等。
*   **後端與資料庫**: FastAPI + PostgreSQL (具有 20 多個 migration 腳本，資料涵蓋歷史 open-data 及官網爬取的 TrackMan/Statcast 進階逐球資料)。

### 2. 核心頁面與功能模組
*   **戰績首頁 (`/`)**: 顯示當季與歷年一軍/二軍戰績、特殊的戰績切換（如場地、分差、月份走勢、對戰組合 H2H 矩陣）。
*   **賽況頁 (`/games` / `/games/[sno]`)**: 採用月曆視圖呈現賽程，單場賽事細節具有 **ESPN 風格的狀態板**（包含即時記分板、壘包出局燈、球數燈、即時推算勝率、投打對決與 Recent Plays）。
*   **球員旗艦頁 (`/players/[id]`)**: 個人儀表板，包含隊色 Hero 區、Savant 風格的百分位 PR 條、遊戲風能力雷達圖、逐球 discipline 紀律分析、球種分析（Arsenal）以及逐月與分項趨勢。
*   **賽事預測頁 (`/predict`)**: 讓使用者透過勾選特徵變因（勝率、得分、先發投手 ERA/WHIP 等）手動微調權重滑桿，模擬預測今日或自選球隊的勝率，並具有模型共線性警告與歷史回測面版。

---

## 二、 現有 UI 的優勢分析

在提出修改規劃前，我們發現現有的 UI 已經具備非常優秀的基礎：
1.  **高度的可讀性與對比度**: 全站採用日間淺色系（Navy + 白），文字對比強烈，並內建了鍵盤導覽焦點環（`:focus-visible`）與跳過導覽連結（`.skip-link`），無障礙（Accessibility）體驗佳。
2.  **靈活的隊色裝飾**: 球隊與球員頁面能動態載入對應的隊色（如味全龍紅、兄弟黃、統一橘等）作為背景與裝飾，提升球迷的歸屬感，同時避免了官方 Logo 的版權問題（使用字母徽章代替）。
3.  **依據數據的色階**: 模仿 MLB Baseball Savant，使用藍（低）↔ 灰（中）↔ 紅（高）的發散色階，讓使用者一眼看出各項進階數據的強度。
4.  **教育性與誠實性**: 預測介面並非單純給出明牌，而是透明展示回測數據，誠實呈現單場 ~60% 的可預測天花板，引導使用者理解數據的本質。

---

## 三、 UI/UX 改善提案規劃（不直接修改程式碼）

為了讓 CPBL Analytics 達到**更極致、WOW 聲連連（Premium & Dynamic）**的視覺效果，我們從以下幾個維度規劃了 UI 修改方案：

### 提案 1：全面支援「深色模式 (Dark Mode)」🌙
*   **修改規劃**:
    1.  在 `globals.css` 中引入 `@media (prefers-color-scheme: dark)` 或使用 CSS 變數實作 `.dark` 類別切換。
    2.  定義深色主題 Token：
        *   `--color-paper`: `#0b132b` (深藍黑底)
        *   `--color-surface`: `#1c2541` (卡片深藍)
        *   `--color-surface-2`: `#3a506b` (按鈕/懸停深藍灰色)
        *   `--color-ink`: `#ffffff` (白字)
        *   `--color-line`: `#2d3748` (深色分隔線)
    3.  於 Header 右側新增一個輕量的主題切換按鈕（Sun / Moon 圖示），並使用 `localStorage` 記憶使用者選擇。

### 提案 2：提升視覺精緻度與「運動風質感 (Sports Tech Aesthetic)」🎨
*   **修改規劃**:
    1.  **漸層與毛玻璃效果 (Glassmorphism)**: 
        *   Header 改用更強烈的毛玻璃效果：`bg-surface/80 backdrop-blur-md`。
        *   球員 Hero 區的隊色背景引入微弱的斜向漸層（如：隊色 70% 漸變到 100% 亮度），增加立體感。
    2.  **微調字體系統**:
        *   在 `layout.tsx` 載入 Google Fonts 的 `Outfit` 或 `Plus Jakarta Sans` 用於英數字與數據展示，搭配中文字體，使數據呈現更具張力與動感。
    3.  **精緻的卡片邊框與陰影**:
        *   卡片在 Hover 時，加上微弱的隊色邊框發光效果（利用 CSS `box-shadow` 與動態 `--team-color` 變數）。

### 提案 3：動態微動畫與微互動 (Micro-interactions) ⚡
*   **修改規劃**:
    1.  **預測滑桿 (Range Slider) 的動態視覺**:
        *   在 `/predict` 的權重滑桿被拖動時，滑桿的軌道（track）動態顯示隊色的漸變，並在數值變化時加入微弱的 scale-up 動畫，提示影響力已被變更。
    2.  **對戰勝率條的載入動畫**:
        *   當賽事預測卡 (`MatchupCard`) 展開或勝率載入時，兩側的隊色勝率條（Home / Away %）應從中間向兩側伸展（`transition-all duration-500 ease-out`），而非瞬間出現。
    3.  **頁面/Tab 切換的過渡**:
        *   使用 CSS **View Transitions API**，讓 `/players/[id]` 內的「本季」與「生涯」切換、或是 `/games` 的月份切換，具有平滑的左右滑動或淡入淡出效果，減少排版跳動感。

### 提案 4：行動端/響應式佈局優化 (Mobile & Responsive UX) 📱
*   **修改規劃**:
    1.  **凍結首欄 (Sticky Column)**:
        *   在所有表格中，將第一欄（球隊/球員名稱）設為 `sticky left-0 z-10 bg-surface`。當使用者在手機上橫向滑動數據時，球隊名稱依然固定在最左側。
    2.  **月曆視圖在行動端的變形**:
        *   在手機上，`/games` 的 7 欄月曆格子會擠壓得極小。規劃在行動端（`md` 以下）自動切換為「列表視圖 (List View)」，將該月有比賽的日期依序往下排列，保留大面積的球隊徽章與分數。
    3.  **觸控優化 (Tap Targets)**:
        *   將特徵選擇的按鈕、年份/分季切換的 Chip 稍微加大高度（維持 44px 觸控友善原則），避免觸控誤點。

### 提案 5：新增功能介面的 UI 提案（未來擴充規劃）🚀
*   **修改規劃**:
    1.  **「球員/投手對比」模式 (Player VS Mode)**:
        *   設計一個專門的對比頁面，允許選取兩名打者或投手。
        *   UI 呈現：左側球員 A、右側球員 B，中間呈現重疊的能力雷達圖，下方則是並排的 Savant 百分位 PR 條。方便球迷比較「誰更強、強在哪裡」。
    2.  **預測準確度儀表板 (Predict Accuracy Dashboard)**:
        *   在預測頁的 `BacktestPanel` 中，除了簡單的長條圖，可以規劃加入一個「勝負預測信心曲線」。當預測勝率偏離 50% 越多（例如 >65%），該場次的實際命中率折線圖，讓球迷知道模型在哪些比賽「特別有信心」且「預測精準」。
    3.  **好球帶互動圖 (Interactive Strike Zone)**:
        *   在球員頁或單場頁的好球帶散佈圖 (`zone-scatter.tsx`) 中，加上點擊個別球點可跳出 Tooltip 顯示「球速、球種、轉速、擊球初速 (EV)」等詳細 Statcast 數據。
