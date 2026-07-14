# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`
> **只留活卡**：卡片一旦 🏁完成 或 📥封存，整段移到 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)（Ledger 列一併移），本檔保持精簡省 AI 讀取算力。

---

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UX-1 | 全站頁面 UI/UX 重新設計（傘卡） | ruan6047 | Fable-5@Claude Code | —（子卡執行） | —（子卡查核） | — | ⚪ | 🔨子卡執行中（餘 UX-8/9/5C；UX-7 群 07-14 已結案） |
| UX-5C | 首頁 hub 完整版（各頁關鍵訊息總集） | ruan6047 | 待小 spec（建議 Opus） | 待指派（Sonnet） | 待指派（Opus，獨立 session） | `ai/<執行者>/UX-5C` | ⚪ | 📥Backlog（**壓到 UX-6〜9 完成後**重製） |
| UX-8 | 排行與紀錄群 | ruan6047 | Fable-5@Claude Code（已完成） | 待指派（Sonnet） | 待指派（Sonnet，獨立 session） | `ai/<執行者>/UX-8` | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-9 | 週邊群 `/matchups`、`/venues` | ruan6047 | Fable-5@Claude Code（已完成） | 待指派（Sonnet） | 待指派（Sonnet，獨立 session） | `ai/<執行者>/UX-9` | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-10 | 裁判個人頁與賽事裁判報告整合 | ruan6047 | Sonnet（沿既有 API 的 UI／導覽規劃） | 待指派（Sonnet） | 待指派（Opus，獨立 session） | `ai/<執行者>/UX-10` | ⚪ | 📥Backlog（既有資料／個人頁重整；誤判影響研究拆 ML-UMP1） |
| ML-UMP1 | 裁判誤判預期影響研究 | ruan6047 | Fable（統計定義／驗證設計） | 待指派（Fable） | 待指派（跨家族模型或人審） | `ai/<執行者>/ML-UMP1` | 🔴 | 📥Backlog（先驗證再決定是否產品化，不併 UX-10） |
| COACH-HIST | 歷年教練職務史（twbsball 經歷節） | ruan6047 | Fable-5@Claude Code（已完成） | 待指派（Opus） | 待指派（跨家族模型或人審） | `ai/<執行者>/COACH-HIST` | 🔴 | 📥Backlog（資料正確性；7C 已上線，接點就緒可排） |
| ML-PT3 | 中職版球路品質指數 (CPBL Stuff+) | ruan6047 | Fable（已完成勘誤） | 待指派（Fable） | 待指派（跨家族模型或人審） | `ai/<執行者>/ML-PT3` | 🔴 | 📥Backlog（**排 2026 季末**；勘誤見 PROPOSAL_EVALUATION.md 附錄） |
| ML-SIM1 | 簡易勝負預測＋單一打席情境模擬 | ruan6047 | 待細 spec（建議 Fable） | 待指派（Fable） | 待指派（跨家族模型或人審） | `ai/<執行者>/ML-SIM1` | 🔴 | 📥Backlog（取代 UX-10O；去重複訊號，不模擬後續全打席） |
| ML-SIM2 | 全場狀態模擬器（完整陣容／牛棚／後續打席） | ruan6047 | 遠期評估（啟動時 Fable） | 待指派（Fable） | 待指派（跨家族模型或人審） | `ai/<執行者>/ML-SIM2` | 🔴 | 📥Backlog（**遠期目標，暫時不做**） |
| TEAM-STYLE1 | 球隊球風研究（年度／時期風格向量→球隊頁＋賽果候選特徵） | ruan6047 | 待研究 spec（建議 Fable） | 待指派（Fable） | 待指派（跨家族模型或人審） | `ai/<執行者>/TEAM-STYLE1` | 🔴 | 📥Backlog（速度戰／投手戰等為待驗證假說；先描述，增量回測通過才進模型） |

> 「待指派」＝ruan6047尚未派工。派工後把 model@tool 補實、狀態改 🔨。
> **依賴序**：通用層（UX-2/3/4/4.5）🏁 → 頁面層 UX-5〜9 已解鎖。**UX-5A/5B/6/7 群 🏁完成並上線**；剩 **UX-8 → UX-9 → UX-5C（首頁完整版，壓最後重製）**。UX-10 待裁判報告小 spec。

---

## 進行中／待辦卡

### UX-1 全站頁面 UI/UX 重新設計  〔⚪（大卡：規劃後預期拆多張子卡，涉全站視覺）〕
- 需求：ruan6047（07-11）——**重新設計每個頁面的 UI/UX**。痛點：①頁面不統一 ②數據可視度不夠 ③頁面與區塊混亂；裁判報告的資訊架構另抽 UX-10 處理。
- 規劃：Fable-5@Claude Code → spec 見 [`UX_REDESIGN_SPEC.md`](UX_REDESIGN_SPEC.md)（八原則＋UX-2〜9 拆卡＋深色模式決策點）
- 執行：子卡各自執行　查核：子卡各自查核（涉全站視覺，建議跨家族或人審驗收）
- 狀態：🔨 spec v5 **已核可**（07-11）；子卡進度：**UX-2/3/4/4.5/5B/5A/6 🏁完成、UX-7 群（7A/7B/7C）🏁完成並於 07-14 上線**（皆已 archive）、UX-8/9 ⏳待執行、UX-5C 📥（壓 UX-8/9 後）、UX-10 暫緩。本傘卡隨子卡全數結案後移 archive　Commit：—
- 前置事實（規劃時必讀）：現行設計系統＝日間 Navy+白（memory `frontend-redesign`）；UI-2/3/4 完成運動風質感/微互動/響應式（`docs/archive/`）
- Log：
  - 07-11 需求開卡；派規劃 → spec 迭代 v2〜v5（痛點對應/可視度=快速理解/模組化審計/盲測定義），ruan6047 **核可 spec v5**
  - 07-11〜12 UX-2/3/4/4.5 🏁（通用層全齊）→ UX-5B/5A 🏁 → UX-6＋ML-PT2 🏁（截圖驗收＋Gemini 查核＋merge `66a5752`＋push）；詳 archive
  - 07-12 **歸檔切割修復**（Fable）：Gemini 歸檔時本卡被截斷（位元組級損毀）且 UX-6 孤兒內容殘留，已重建（archive 副本完整，無資料損失）

> **UX-5 拆卡裁示（ruan6047 07-11）**：UX-5B hub v1＋搬遷（🏁）→ UX-5A 戰績換裝（🏁）→ **UX-5C 首頁 hub 完整版**（壓 UX-6〜9 完成後重製）。hub 卡＝「指路牌」，避免與戰績頁重複。

### UX-8 排行與紀錄群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-8`
- 執行：待指派（Sonnet）　查核：待指派（Sonnet，獨立 session；≠執行者）
- 範圍/驗收：`/batters`、`/pitchers`、`/records`；表格家族，一張卡統一模式（全數走 DataTable）。5 秒盲測＋雙色系截圖。
- 狀態：⏳待執行（通用層已齊，已解鎖待派工）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡



### UX-9 週邊群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-9`
- 執行：待指派（Sonnet）　查核：待指派（Sonnet，獨立 session；≠執行者）
- 範圍/驗收：`/matchups`、`/venues`；對齊新語彙即可，改動最小。5 秒盲測＋雙色系截圖。
- 狀態：⏳待執行（通用層已齊，本輪最後，已解鎖待派工）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### COACH-HIST 歷年教練職務史（twbsball 經歷節）  〔🔴紅線：歷史資料正確性〕
- 需求：ruan6047（07-12「教練從其他管道拿歷年教練團？」）　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/COACH-HIST`
- 執行：待指派（Opus）　查核：待指派（跨家族模型或人審；≠執行者）
- **管道查證（07-12 實測）**：twbsball **無**逐年球隊條目（`2015年中信兄弟` 不存在，allpages 驗證）→ 改**人物中心**：個人條目「經歷」節有結構化教練職務＋精確起訖（林威助實測：`:*[[中華職棒]][[中信兄弟隊]][[總教練]]（[[2020年]]12月07日～[[2023年]]05月10日）`）。存取沿 `cpbl_overseas.py` 的 query API 模式（`action=query&prop=revisions`，UA+退避，無 Anubis 問題已驗證）。
- 範圍：
  1. 種子名單＝現任 coaches 72＋managers 90（去重）；爬個人條目經歷節（~150 頁，一次抓+手動刷新，照 wiki-data-sources 慣例）
  2. 解析教練職務行 → 新表 `coach_history(name, team_code, pos, from_date, to_date, source, needs_review)`（migration 冪等）
  3. **解析守則（不腦補）**：行格式變異（兼任/代理/客座 前綴保留進 pos）；日期粒度不一（年/年月/年月日，缺月日存年初/年末界）；隊名歷代對映 team_dim（兄弟象→中信兄弟等，對不上→needs_review）；**非職棒職務**（學校/業餘/國家隊）過濾出主表或另欄標注；解析失敗行一律 needs_review 人工檢
  4. 前端：7C 教練頁「教練職務」表改吃 coach_history（歷年時間軸）；7B 球員頁教練身分區塊同源
- 驗收：抽 10 名教練對照 twbsball 原頁人工核對；needs_review 比率報告；`ruff`+`pytest` 綠
- 依賴：7C merge 後（前端接點在 7C 的頁）
- 狀態：📥Backlog（ruan6047 07-12 裁定 a 案：先排 backlog，不疊進 7C 送審）　Commit：—
- Log：
  - 07-12 需求＋管道查證＋開卡（Fable）；twbsball 逐年球隊條目假設被否、人物中心路線實測可行

### UX-10 裁判個人頁與賽事裁判報告整合  〔⚪一般〕
- 需求：ruan6047（07-11；07-14 重整範圍）　規劃：Sonnet（沿既有 API 的 UI／導覽規劃）　分支：`ai/Antigravity/UX-10`
- 執行：Antigravity@Sonnet　查核：待指派（Opus，獨立 session；≠執行者）
- **資訊架構**：裁判報告由獨立 `/umpires` 頁移入各場 `/games/{sno}` 賽況頁，成為該場主審的判決報告；賽況頁的裁判姓名改為連至 `/people/umpire/{name}` 裁判個人頁。主選單移除「裁判報告」，但保留 `/umpires` 索引路由作為搜尋／深連結入口，不做 404 或刪除既有 API。
- **個人頁**：以既有裁判個人頁為基礎，呈現主審判決摘要、執法位置與可回到各場賽況報告的清單；全數持續標示 TrackMan 覆蓋場數、固定規則好球帶與「推算、非官方」限制。
- **賽事報告**：保留目前逐球好壞球判決、好球帶位置與關鍵漏判呈現；報告只涵蓋主審且僅納入有 TrackMan 的 called 球，沒有追蹤資料時明確退化為「無法評估」，不得以缺值推論裁判表現。
- **邊界**：不估算「誤判預期得利」；該反事實估計 [counterfactual estimation] 與是否產品化，完全交由 ML-UMP1 研究卡處理。
- 狀態：🔍待查核　Commit：`1dc6e6a`
- Log：
  - 07-11 自 UX-1 抽出暫緩
  - 07-14 成績預測公開瀏覽取消，改由獨立下架工作處理；`/predict` 規劃完全移交 ML-SIM1／ML-SIM2
  - 07-14 ruan6047 裁示本卡改處理裁判：賽事內報告、裁判個人頁導覽與誤判預期得利可行性
  - 07-14 依 AI_WORKFLOW 拆分一般 UI 與統計紅線：UX-10 採 Sonnet 執行／Opus 獨立查核；誤判影響研究移 ML-UMP1 採 Fable＋跨家族或人審
  - 07-14 Antigravity 實作完成：主選單導航移除「裁判報告」；賽況總覽裁判名改為 Link 連結個人頁；在 BoxTabs 中整合「主審報告」Tab，支援動態散點圖、關鍵漏判及容錯範圍，無資料時顯示無法評估；個人頁「看單場 →」新增 tab=umpire 與 year 參數引導。
  - 07-14 Sonnet@Claude Code 接手收尾：worktree 內工作區原為未 commit 狀態，補跑驗證後 commit `1dc6e6a`——`ruff check`／`pytest`（42 passed）／`npm run build:check` 全綠；Chrome DevTools 實測 `/games/204` 真實資料（2026-07-12 樂天桃猿 vs 台鋼雄鷹）：賽況總覽裁判姓名可點、BoxTabs「主審報告」渲染好球帶散點圖＋關鍵漏判＋容錯滑桿、個人頁 `/people/umpire/楊崇煇` 記分卡與「看單場 →」深連結（`?tab=umpire&year=2026`）回跳報告皆正確。待 Opus 獨立 session 查核。


### ML-UMP1 裁判誤判預期影響研究  〔🔴紅線：統計／反事實估計〕
- 需求：ruan6047（07-14）　規劃：Fable（統計定義／驗證設計）　分支：`ai/<執行者>/ML-UMP1`
- 執行：待指派（Fable）　查核：待指派（跨家族模型或人審；≠執行者）
- 範圍／驗收：定義每個錯判在判決前狀態的預期得分或勝率差（實際判決對比正確判決的反事實結果），按攻守隊與裁判聚合；先建立可重現的 RE24 或勝率基準、資料切分、校準與不確定性，並對照「漏判數／距離」baseline。僅用有 TrackMan 的 called 球；未通過獨立審核與實測前，不寫入 UI、不稱為球隊實際得利或失分。
- 狀態：📥Backlog　Commit：—
- Log：
  - 07-14 自 UX-10 拆出：反事實估計不宜與一般 UI 同卡；依 AI_WORKFLOW 採 Fable 執行、跨家族或人審查核

### ML-PT3 中職版球路品質指數 (CPBL Stuff+ Index)  〔🔴紅線：ML/統計正確性〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/ML-PT3`
- 執行：待指派（Fable）　查核：待指派（跨家族模型或人審；≠執行者）
- 範圍/驗收：Stuff+ 隨機森林/LightGBM 模型研發與物理評分整合。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

### ML-SIM1 簡易勝負預測＋單一打席情境模擬  〔🔴紅線：統計正確性〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/ML-SIM1`
- 執行：待指派（Fable）　查核：待指派（跨家族模型或人審；≠執行者）
- 範圍／驗收分兩模式：
  1. **簡易勝負預測（現有賽事預測修正版）**：預測賽前主／客勝率；取消使用者自由勾選特徵與權重滑桿。固定模型按「整體戰力、打線、失分抑制／先發、賽程／主場」等語意群設計，每群只能使用一個代表訊號或一個明確定義的合成值，禁止把勝率／近況、得分／OPS／AVG 等同義代理同時當成多份獨立證據。輸出須列實際採用訊號、方向、樣本期間與不確定性；時間走查回測同時比較全押主場 baseline、既有全特徵模型，至少回報 Accuracy、Brier、LogLoss 與校準，未勝 baseline 不上線。
  2. **單一打席情境模擬**：投手×打者的互斥結果機率；依當下局數／上下半局／比分／壘況／出局映射下一狀態，復用既有 `wp_state()` 計算各結果與加權後整場勝率。可由賽況 `year+kind_code+game_sno+main_event_no` 帶入真實打席。
- 共同邊界：**不含完整陣容、牛棚與後續全打席個人化模擬**；細節待派工前另出 spec。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成
  - 07-14 ruan6047 裁示取代 UX-10O；全場狀態模擬拆為 ML-SIM2 遠期目標，暫時不做
  - 07-14 ruan6047 裁示加入簡易勝負預測，修正現版指標重複計算與手調權重參考性不足問題

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
