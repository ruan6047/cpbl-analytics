# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`
> **只留活卡**：卡片一旦 🏁完成 或 📥封存，整段移到 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)（Ledger 列一併移），本檔保持精簡省 AI 讀取算力。

---

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UX-1 | 全站頁面 UI/UX 重新設計（傘卡） | ruan6047 | Fable-5@Claude Code | —（子卡執行） | —（子卡查核） | — | ⚪ | 🔨子卡執行中（spec v5 已核可 07-11） |
| UX-5C | 首頁 hub 完整版（各頁關鍵訊息總集） | ruan6047 | 待小 spec | 待指派 | 待指派 | — | ⚪ | 📥Backlog（**壓到 UX-6〜9 完成後**重製） |
| UX-7 | 個人頁：球員/球隊換裝＋教練/裁判個人頁 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📋規劃完成待派工（07-12 擴為 Person Hub） |
| UX-8 | 排行與紀錄群 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-9 | 週邊群 `/matchups`、`/venues` | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-10 | 三頁互動模式重設計 | ruan6047 | 待各自小 spec | 待指派 | 待指派 | — | ⚪ | 📥Backlog（暫緩，不在本輪序） |
| UX-11 | 選手百分位數氣泡卡 | ruan6047 | Fable 複評 07-12 | —（併卡） | — | — | ⚪ | 🏁併入 UX-7 範圍 1（=既有三 PR 呈現整併+氣泡化，非新建） |
| UX-12 | 出手點 2D 分布圖 | ruan6047 | Fable 複評 07-12 | —（併卡） | — | — | ⚪ | 🏁併入 UX-7（位移半案 07-12 已上線，僅剩出手點） |
| ML-PT3 | 中職版球路品質指數 (CPBL Stuff+) | ruan6047 | 評估報告+Fable 勘誤 | 待指派 | 待指派 | — | 🔴 | 📥Backlog（**排 2026 季末**；勘誤見 PROPOSAL_EVALUATION.md 附錄） |
| ML-SIM1 | 互動式 H2H 對戰模擬器 v2 | ruan6047 | 評估報告+Fable 勘誤 | 待指派 | 待指派 | — | 🔴 | 📥Backlog（遠期，與 UX-10 predict 重設計合併規劃） |

> 「待指派」＝ruan6047尚未派工。派工後把 model@tool 補實、狀態改 🔨。
> **依賴序**：(UX-2 🏁 / UX-3 🏁 / UX-4 🏁 / UX-4.5 🏁) 通用層已齊 → UX-5〜9 頁面層（大→小）已解鎖。UX-5 已拆 **UX-5B（hub v1＋搬遷，🏁 merge `e74853b`）→ UX-5A（戰績換裝）→ UX-5C（首頁完整版，壓 UX-6〜9 之後重製）**。UX-10 暫緩。

---

## 進行中／待辦卡

### UX-1 全站頁面 UI/UX 重新設計  〔⚪（大卡：規劃後預期拆多張子卡，涉全站視覺）〕
- 需求：ruan6047（07-11）——**重新設計每個頁面的 UI/UX**。痛點：①頁面不統一 ②數據可視度不夠 ③頁面與區塊混亂；另 成績預測/賽事預測/裁判報告 三頁**操作模式與現實脫節**（抽出 UX-10 暫緩個別處理）。
- 規劃：Fable-5@Claude Code → spec 見 [`UX_REDESIGN_SPEC.md`](UX_REDESIGN_SPEC.md)（八原則＋UX-2〜9 拆卡＋深色模式決策點）
- 執行：子卡各自執行　查核：子卡各自查核（涉全站視覺，建議跨家族或人審驗收）
- 狀態：🔨 spec v5 **已核可**（07-11）；子卡進度：**UX-2/3/4/4.5/5B/5A/6 🏁完成（已 archive）**、UX-7〜9 ⏳待執行、UX-5C 📥（壓 UX-6〜9 後）、UX-10 暫緩。本傘卡隨子卡全數結案後移 archive　Commit：—
- 前置事實（規劃時必讀）：現行設計系統＝日間 Navy+白（memory `frontend-redesign`）；UI-2/3/4 完成運動風質感/微互動/響應式（`docs/archive/`）
- Log：
  - 07-11 需求開卡；派規劃 → spec 迭代 v2〜v5（痛點對應/可視度=快速理解/模組化審計/盲測定義），ruan6047 **核可 spec v5**
  - 07-11〜12 UX-2/3/4/4.5 🏁（通用層全齊）→ UX-5B/5A 🏁 → UX-6＋ML-PT2 🏁（截圖驗收＋Gemini 查核＋merge `66a5752`＋push）；詳 archive
  - 07-12 **歸檔切割修復**（Fable）：Gemini 歸檔時本卡被截斷（位元組級損毀）且 UX-6 孤兒內容殘留，已重建（archive 副本完整，無資料損失）

> **UX-5 拆卡裁示（ruan6047 07-11）**：UX-5B hub v1＋搬遷（🏁）→ UX-5A 戰績換裝（🏁）→ **UX-5C 首頁 hub 完整版**（壓 UX-6〜9 完成後重製）。hub 卡＝「指路牌」，避免與戰績頁重複。

### UX-7 個人頁：球員/球隊換裝 ＋ Person Hub（教練/裁判）  〔⚪一般〕
- 需求：ruan6047（07-11 開卡；07-12 擴充「球員頁→個人頁」：教練/裁判/領隊/未來啦啦隊）　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/UX-7`
- 執行：待指派（建議 Opus：多檔＋新命名空間＋新端點）　查核：待指派（旗艦頁建議人審）
- **資料現實（07-12 實測）**：教練 `coaches` 72 名（year/team/pos/背號，2026；**47/72 為 ex-player 可同名 join players**）；總教練 `managers` 90 era 記錄（W/L/T/勝率/冠軍，wiki）；裁判 30 名（`game_detail` 逐場執法＋`pitch_tracking` 好球帶報告，`/umpires` 聚合頁已有）；領隊/啦啦隊**無資料源**。
- **架構裁定（ruan6047 07-12）**：
  - URL＝**甲案雙軌**：有 acnt → `/players/[id]`（canonical 不動、不斷鏈）；無 acnt → `/people/[kind]/[name]`（kind=coach|umpire，中文名 URL-encode，同名以 kind 隔離；規模 25+30 可控）。**不建 person_dim**（留 PERSON-2）。
  - 頁面模型＝**單頁多身分**：hero 身分 chips（球員｜教練｜總教練｜裁判），各身分一組 section、錨定現在身分。
- 範圍：
  1. `/players/[id]` 換裝對齊＋補缺口（Eyebrow/三態/StatAbbr 名詞解釋鋪設）
  2. 球員頁**教練身分區塊**：coaches 同名 join（歷年職務/隊/背號）＋managers 總教練 era 戰績卡。**同名歧義守門**：coach 名對到多個 acnt → 不自動掛、記 needs_review（嚴禁腦補）
  3. `/teams/[code]` 換裝＋**教練團名單**（coaches by team）＋**總教練歷代 era 卡**（managers 含勝率/冠軍）
  4. `/people/coach/[name]`：25 名非球員教練（職務史＋若有 managers 戰績）
  5. `/people/umpire/[name]`：裁判個人頁——執法場次/好球帶判定個人報告（自 umpires router 抽 per-name）/近期執法場列表（連 games）；順帶解 UX-10 裁判動線問題的一半
  6. **提案 A 收編＝PR 呈現整併+氣泡化**（PROPOSAL_EVALUATION A 案）：球員頁既有三種 PR（能力值卡雷達/PercentileBar/官方進階 PR 區）整併——氣泡列=本季速讀（Savant 式，含 tracking 衍生 whiff/chase/barrel PR，樣本門檻 min_pa=G×3.1/min_bf=G×1.0）、雷達=生涯風格、官方 PR 收進氣泡。色走既有 `prColor`/`PR_GRADIENT`（報告的 hardcode hex 違反 tokens 紅線不採）；不加 Redis（SQL window/物化即可）
  7. **提案 B 收編＝出手點 2D**（位移半案 07-12 已上線）：`rel_side`×`rel_height`（單位 m 非報告寫的 cm；覆蓋 99.96%）散點 by 球種+質心+「出手一致性」數值（各球種質心分散度，比信心橢圓便宜可讀）；掛 MovementSection 旁、movement 端點擴欄；左投鏡像沿既有慣例
  8. 新端點同步 pytest EXPECTED（07-12 快照教訓）
- 不做（PERSON-2 backlog）：person_dim 正規化、領隊、啦啦隊/應援團（**先查證官網有無名單**，有資料源再開卡）
- 驗收：5 秒盲測（球員頁「這選手行不行」、裁判頁「這主審好球帶偏不偏」）＋雙色系 375/1280 截圖；同名守門有測試；`ruff`+`pytest`+`tsc`+`build:check` 綠
- 狀態：📋規劃完成待派工　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡
  - 07-12 ruan6047 擴需求「球員頁→個人頁」；Fable 研究＝資料盤點（教練 72/47 joinable、managers 90 era、裁判 30、領隊/啦啦隊無源）→ 裁定甲案雙軌 URL＋UX-7 一次含 PERSON-1（純教練/裁判個人頁）；person_dim/領隊/啦啦隊列 PERSON-2 backlog
  - 07-12 ruan6047 令複評 PROPOSAL_EVALUATION 四案 → **A/B 收編進 UX-7**（範圍 6/7；A=整併非新建、B 只剩出手點半案）、C 排季末（資料前提勘誤：pitch_tracking 僅 2026 非 2020–2026）、D 遠期連 UX-10；勘誤附錄見 PROPOSAL_EVALUATION.md

### UX-8 排行與紀錄群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-8`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/batters`、`/pitchers`、`/records`；表格家族，一張卡統一模式（全數走 DataTable）。5 秒盲測＋雙色系截圖。
- 狀態：⏳待執行（通用層已齊，已解鎖待派工）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡



### UX-9 週邊群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-9`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/matchups`、`/venues`；對齊新語彙即可，改動最小。5 秒盲測＋雙色系截圖。
- 狀態：⏳待執行（通用層已齊，本輪最後，已解鎖待派工）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### UX-10 三頁互動模式重設計（暫緩）  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：待各自小 spec　分支：`ai/<執行者>/UX-10-*`
- 執行：待指派　查核：待指派
- 範圍：`/projections`、`/predict`、`/umpires`——問題在**互動模型不在視覺**（predict 特徵子集探索器、projections 投影瀏覽、umpires 報告閱讀動線）。**不在本輪執行序**；屆時拆三張卡各出小 spec。本輪 UX-2/3/4 的 tokens/元件仍會套到這三頁（外觀統一），但不動互動模型。
- 狀態：📥Backlog（暫緩）　Commit：—
- Log：
  - 07-11 自 UX-1 抽出暫緩

### UX-11 選手百分位數氣泡卡 (Percentile Player Cards)  〔⚪一般〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/UX-11`
- 執行：待指派　查核：待指派
- 範圍/驗收：選手個人頁頂部百分位數（PR 0–99）紅藍氣泡指標卡。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

### UX-12 出手點與球路軌跡 2D 分布圖 (Release/Movement)  〔⚪一般〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/UX-12`
- 執行：待指派　查核：待指派
- 範圍/驗收：選手頁 Release Point 2D 散點與信心區間圖（含 X/Y 坐標與左右手鏡像）。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

### ML-PT3 中職版球路品質指數 (CPBL Stuff+ Index)  〔🔴紅線：ML/統計正確性〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/ML-PT3`
- 執行：待指派　查核：待指派
- 範圍/驗收：Stuff+ 隨機森林/LightGBM 模型研發與物理評分整合。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

### ML-SIM1 互動式 H2H 對戰模擬器 v2  〔🔴紅線：統計正確性〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/ML-SIM1`
- 執行：待指派　查核：待指派
- 範圍/驗收：雙欄投打選取器，結合配球與揮空/選球熱熱圖，模擬對戰概率分布。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

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
