# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`
> **只留活卡**：卡片一旦 🏁完成 或 📥封存，整段移到 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)（Ledger 列一併移），本檔保持精簡省 AI 讀取算力。

---

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UX-1 | 全站頁面 UI/UX 重新設計（傘卡） | ruan6047 | Fable-5@Claude Code | —（子卡執行） | —（子卡查核） | — | ⚪ | 🔨子卡執行中（spec v5 已核可 07-11） |
| UX-3 | 共用元件標準化（ui.tsx 收斂＋三態＋DataTable） | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行 |
| UX-4 | 骨架導覽＋標準頁面解剖落地 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📥Backlog（待 UX-2/3） |
| UX-5 | 首頁（戰績）換裝 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📥Backlog（待通用層） |
| UX-6 | 賽況群 `/games`、`/games/[sno]` | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📥Backlog（待通用層） |
| UX-7 | 球員/球隊頁 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📥Backlog（待通用層） |
| UX-8 | 排行與紀錄群 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📥Backlog（待通用層） |
| UX-9 | 週邊群 `/matchups`、`/venues` | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📥Backlog（待通用層） |
| UX-10 | 三頁互動模式重設計 | ruan6047 | 待各自小 spec | 待指派 | 待指派 | — | ⚪ | 📥Backlog（暫緩，不在本輪序） |

> 「待指派」＝ruan6047尚未派工。派工後把 model@tool 補實、狀態改 🔨。
> **依賴序**：(UX-2 🏁) →（UX-3 → UX-4）通用層做完 → UX-5〜9 頁面層（大→小）。UX-10 暫緩。

---

## 進行中／待辦卡

### UX-1 全站頁面 UI/UX 重新設計  〔⚪（大卡：規劃後預期拆多張子卡，涉全站視覺）〕
- 需求：ruan6047（07-11）——**重新設計每個頁面的 UI/UX**。痛點：①頁面不統一 ②數據可視度不夠 ③頁面與區塊混亂；另 成績預測/賽事預測/裁判報告 三頁**操作模式與現實脫節**（抽出 UX-10 暫緩個別處理）。
- 規劃：Fable-5@Claude Code → spec 見 [`UX_REDESIGN_SPEC.md`](UX_REDESIGN_SPEC.md)（八原則＋UX-2〜9 拆卡＋深色模式決策點）
- 執行：子卡各自執行　查核：子卡各自查核（涉全站視覺，建議跨家族或人審驗收）
- 狀態：🔨 spec v5 **已核可**（07-11），UX-2〜10 已開卡進 Ledger；本傘卡隨子卡全數結案後移 archive　Commit：—
- 前置事實（規劃時必讀）：現行設計系統＝日間 Navy+白（memory `frontend-redesign`）；UI-2/3/4 剛完成運動風質感/微互動/響應式（`docs/archive/`）；UI-1 深色模式與 UI-5 對比頁在封存區可視需要復活併入
- Log：
  - 07-11 需求開卡 by ruan6047（Fable-5@Claude Code 代記）
  - 07-11 ruan6047 派規劃（原則先行、通用→個別、大→小）；規劃 by Fable-5@Claude Code 出 spec，🚦待核可
  - 07-11 ruan6047 補需求背景（三痛點）＋範圍裁示（三脫節頁暫緩）→ spec v2：痛點對應表、可視度量化下限、頁面解剖規範、UX-10 暫緩卡
  - 07-11 ruan6047 裁定深色模式併入 UX-2；模組化審計 by Fable-5 → 證實偏低（卡片殼 inline×46、手寫表格×22/9檔、skeleton=0、components 佔 28%），量化基準入 spec 作 UX-3 驗收對照
  - 07-11 ruan6047 澄清「可視度」＝快速理解（過多數據→判讀負荷），非易讀性 → spec v4：原則 1 重寫（漸進揭露/數字不裸列/每區塊一問題/5 秒測試＝頁面卡首要驗收）
  - 07-11 ruan6047 令重評需求 → 規劃自查（審計數字實測仍準；ruan6047 核可四修正）→ spec v5：UX-2 瘦身（全頁雙色系驗收下放頁面卡）、圖表色票 API 歸 UX-2、UX-3 client island 約束、5 秒測試盲測定義、table 勘誤 11 檔
  - 07-11 ruan6047 **核可 spec v5** → 規劃階段收尾；UX-2〜10 依依賴序開卡進 Ledger，待 ruan6047 派工執行

---

### UX-3 共用元件標準化  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 通用層）　分支：`ai/<執行者>/UX-3`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`ui.tsx` 收斂 eyebrow/dl 網格/chip/狀態徽章/skeleton·empty·error 三態/**DataTable**（寬表容器+sticky 首欄+表頭封裝）；互動元件一律 **client island**（禁為加互動翻整頁 `"use client"`）；6 檔 recharts 接 UX-2 色票 API。驗收對照 spec §B「模組化基準」（卡片殼 inline ×46→<10、手寫 table ×22/11 檔→零、skeleton 0→統一），至少 3 頁換裝無回歸。
- 狀態：⏳待執行（待指派執行與查核）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡（**本案槓桿點**：先抽元件，頁面卡才是換裝非重寫）

### UX-4 骨架導覽＋標準頁面解剖落地  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 通用層）　分支：`ai/<執行者>/UX-4`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：header 導覽資訊架構（10 項導覽分組/優先序）、**標準頁面解剖落地**（h1+副標/主角區/輔助區塊排序——直接回應「區塊混亂」）、footer、行動端導覽。驗收：375px 導覽可用；各頁標題與區塊結構一致。
- 狀態：📥Backlog（待 UX-2/3）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### UX-5 首頁（戰績）換裝  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-5`
- 執行：待指派　查核：待指派（≠執行者，關鍵頁建議人審）
- 範圍/驗收：`/`；全站門面，戰績表+特殊戰績重排資訊層級。**首要驗收＝5 秒盲測**（375+1280 首屏截圖答得出「誰領先」且為視覺焦點）＋深淺雙色系截圖。
- 狀態：📥Backlog（待通用層 UX-2/3/4）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### UX-6 賽況群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-6`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/games`、`/games/[sno]`；LIVE-1/ESPN 狀態板剛完成，主要對齊新元件語彙，預期改動小。5 秒盲測（「今天誰贏」）＋雙色系截圖。
- 狀態：📥Backlog（待通用層）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### UX-7 球員/球隊頁  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-7`
- 執行：待指派　查核：待指派（≠執行者，旗艦頁建議人審）
- 範圍/驗收：`/players/[id]`、`/teams/[code]`；旗艦頁（P1/P2 已做過一輪），對齊新語彙+補缺口。5 秒盲測（「這選手行不行」）＋雙色系截圖。
- 狀態：📥Backlog（待通用層）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### UX-8 排行與紀錄群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-8`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/batters`、`/pitchers`、`/records`；表格家族，一張卡統一模式（全數走 DataTable）。5 秒盲測＋雙色系截圖。
- 狀態：📥Backlog（待通用層）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### UX-9 週邊群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-9`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/matchups`、`/venues`；對齊新語彙即可，改動最小。5 秒盲測＋雙色系截圖。
- 狀態：📥Backlog（待通用層，本輪最後）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### UX-10 三頁互動模式重設計（暫緩）  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：待各自小 spec　分支：`ai/<執行者>/UX-10-*`
- 執行：待指派　查核：待指派
- 範圍：`/projections`、`/predict`、`/umpires`——問題在**互動模型不在視覺**（predict 特徵子集探索器、projections 投影瀏覽、umpires 報告閱讀動線）。**不在本輪執行序**；屆時拆三張卡各出小 spec。本輪 UX-2/3/4 的 tokens/元件仍會套到這三頁（外觀統一），但不動互動模型。
- 狀態：📥Backlog（暫緩）　Commit：—
- Log：
  - 07-11 自 UX-1 抽出暫緩

### 開卡格式（範本）

```markdown
### <卡ID> <功能名>  〔⚪一般 或 🔴紅線：原因〕
- 需求：<誰>　規劃：<誰>　分支：`ai/<模型或工具>/<卡ID>`
- 執行：<model@tool>　查核：<model@tool 或 人審>
- 狀態：🔨執行中　Commit：—
- Log：
  - MM-DD <事件>
```

---

## 歷史

已完成／封存卡片（UI-1〜UI-5、LIVE-1、工作流建立前補記）→ [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)
