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
| UX-7 | 個人頁傘卡（Person Hub） | ruan6047 | Fable-5@Claude Code | —（子卡執行） | —（子卡查核） | — | ⚪ | 📋已拆 7A/7B/7C（07-12） |
| UX-7A | 球員頁換裝＋PR 氣泡＋出手點 | ruan6047 | Fable-5@Claude Code | Gemini（首輪，已還原） | Fable-5（審） | `ai/opus/UX-7A`(WIP) | ⚪ | ↩已還原（需求方裁定效果未達；重做參考 findings 見卡） |
| UX-7B | 球隊頁＋教練身分（coaches/managers） | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待派工（吃 7A 換裝定調） |
| UX-7C | /people 命名空間（純教練/裁判個人頁） | ruan6047 | Fable-5@Claude Code | Fable-5@Claude Code | Gemini | `ai/fable/UX-7C` | ⚪ | ✅查核通過已 merge（`9c33f32`），待部署 |
| UX-8 | 排行與紀錄群 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-9 | 週邊群 `/matchups`、`/venues` | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-10 | 三頁互動模式重設計 | ruan6047 | 待各自小 spec | 待指派 | 待指派 | — | ⚪ | 📥Backlog（暫緩，不在本輪序） |
| COACH-HIST | 歷年教練職務史（twbsball 經歷節） | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📥Backlog（7C 查核後可排） |
| UX-11 | 選手百分位數氣泡卡 | ruan6047 | Fable 複評 07-12 | —（併卡） | — | — | ⚪ | 🏁併入 UX-7 範圍 1（=既有三 PR 呈現整併+氣泡化，非新建） |
| UX-12 | 出手點 2D 分布圖 | ruan6047 | Fable 複評 07-12 | —（併卡） | — | — | ⚪ | 🏁併入 UX-7（位移半案 07-12 已上線，僅剩出手點） |
| ML-PT3 | 中職版球路品質指數 (CPBL Stuff+) | ruan6047 | 評估報告+Fable 勘誤 | 待指派 | 待指派 | — | 🔴 | 📥Backlog（**排 2026 季末**；勘誤見 PROPOSAL_EVALUATION.md 附錄） |
| ML-SIM1 | 互動式 H2H 對戰模擬器 v2 | ruan6047 | —（併卡） | — | — | — | 🔴 | 🏁併入 UX-10（ruan6047 07-12；predict 互動重設計一起出小 spec） |

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

### UX-7 個人頁傘卡（Person Hub）  〔⚪一般〕
- 需求：ruan6047（07-11 開卡；07-12 擴「球員頁→個人頁」；07-12 令拆子卡）　規劃：Fable-5@Claude Code
- **共同前提（三子卡皆讀）**：
  - 資料現實（07-12 實測）：教練 `coaches` 72 名（year/team/pos/背號；47/72 ex-player 可同名 join players）；總教練 `managers` 90 era（W/L/T/勝率/冠軍，wiki）；裁判 30 名（`game_detail` 執法＋`pitch_tracking` 好球帶）；領隊/啦啦隊無資料源（PERSON-2 backlog：person_dim/領隊/啦啦隊，先查證官網有無名單）。
  - 架構裁定：URL 甲案雙軌（有 acnt→`/players/[id]` 不動；無 acnt→`/people/[kind]/[name]`，kind=coach|umpire）；頁面模型=單頁多身分（hero 身分 chips）。
  - 橫切驗收：新端點同步 pytest EXPECTED；`ruff`+`pytest`+`tsc`+`build:check` 綠；雙色系 375/1280 截圖。
- 依賴序：**7A 先行**（換裝定調）→ **7B**（教練身分掛進球員頁，避免同檔衝突）；**7C 獨立**（新路由，可與 7A 平行）。
- 狀態：📋已拆 7A/7B/7C　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡；07-12 擴需求「球員頁→個人頁」＋研究裁定（甲案雙軌/單頁多身分）；07-12 複評 PROPOSAL_EVALUATION → A/B 收編；07-12 ruan6047 令拆三子卡（量大）

### UX-7A 球員頁換裝＋PR 氣泡＋出手點  〔⚪一般〕
- 需求：ruan6047　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/UX-7A`
- 執行：待指派（建議 Opus：PR 三呈現整併是設計判斷）　查核：待指派（旗艦頁建議人審）
- 範圍：
  1. `/players/[id]` 換裝對齊新語彙＋補缺口（Eyebrow/三態/StatAbbr 名詞解釋鋪設；P1/P2 基礎上）
  2. **PR 呈現整併＋氣泡化**（提案 A）：既有三種 PR（能力值卡雷達/PercentileBar/官方進階 PR 區）整併——氣泡列=本季速讀（Savant 式，含 tracking 衍生 whiff/chase/barrel PR；樣本門檻 min_pa=G×3.1、min_bf=G×1.0）、雷達=生涯風格、官方 PR 收進氣泡。色走 `prColor`/`PR_GRADIENT`（禁 hardcode hex）；不加 Redis（SQL window/物化足夠）
  3. **出手點 2D**（提案 B 剩餘半案）：`rel_side`×`rel_height`（單位 m；覆蓋 99.96%）散點 by 球種＋質心＋「出手一致性」數值（各球種質心分散度）；掛 MovementSection 旁、movement 端點擴欄；左投鏡像沿既有慣例
- 驗收：5 秒盲測「這選手行不行」（氣泡列應為首屏答案）＋雙色系截圖；PR 整併後無重複呈現；橫切驗收見傘卡
- 狀態：↩已還原（07-12 ruan6047 裁定「效果沒有變得比較好」；Gemini 首輪 WIP 快照留分支 `ai/opus/UX-7A`@`d6ca243`，main 從未受影響）　Commit：—
- **重做參考（Fable 審核 findings，07-12；避免二輪重蹈）**：
  - F1（高·雙重事實源）：卡片要求「官方 PR 收進氣泡」，首輪把官方 PR 區移除後**全部自算 PR**——但 `advanced_stats` 有 9 個官方 `_pr` 欄、`batting_current.ops_plus` 官方欄也存在（trend.py 另有滾動版=第三套）。同指標會與官方數字不一致。重做：氣泡直接用官方 `_pr`，官方沒有的才自算並標注
  - F2（高·誠實）：雷達被寫死 `selectAbility(..., "career")` 但旁邊本季/生涯 toggle 仍在且亮「本季」——標示與內容不符。固定生涯就同步改 toggle 語意
  - F3（中）：高相關指標成對佔位（截圖實證 ERA+ 92 與防禦率 92 同 PR）——每對取一
  - F4（中·版面）：位移/出手點/成績單 3 欄 grid 在 1280 擠爆，表格「放球點/一致性」欄被裁切
  - F5（低）：「已鏡像鏡像」typo；一致性建議 cm；單球群 variance null→coalesce 0 顯示 0.000 誤導，樣本過小應顯「—」
  - 好的部分可沿用：氣泡視覺/樣本門檻+未達門檻標注/骨架屏/出手點+一致性照卡實作/整併方向正確
  - 流程：首輪未 commit 未推送即交審（§3.1 交接驗證未過）——二輪務必收尾再交

### UX-7B 球隊頁＋教練身分  〔⚪一般〕
- 需求：ruan6047　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/UX-7B`
- 執行：待指派（Sonnet 可：守門規則已明確）　查核：待指派（≠執行者）
- 範圍：
  1. `/teams/[code]` 換裝＋**教練團名單**（coaches by team：職務/背號；ex-player 連 `/players/[id]`、純教練連 `/people/coach/[name]`——7C 未上線前純教練暫不連結）＋**總教練歷代 era 卡**（managers：任期/W-L-T/勝率/冠軍）
  2. 球員頁**教練身分區塊**＋hero 身分 chips（球員｜教練｜總教練）：coaches 同名 join（歷年職務/隊/背號）＋managers era 戰績卡。**同名歧義守門（紅線）**：coach 名對到多個 player acnt → 不自動掛、記 needs_review，嚴禁腦補
- 依賴：7A merge 後開工（同檔 `/players/[id]`，避免衝突）
- 驗收：同名守門有測試（構造同名 fixture）；教練團/era 卡雙色系截圖；橫切驗收見傘卡
- 狀態：⏳待派工　Commit：—

### UX-7C /people 命名空間（純教練/裁判個人頁）  〔⚪一般〕
- 需求：ruan6047　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/UX-7C`
- 執行：待指派（建議 Opus：新命名空間+新端點）　查核：待指派（≠執行者）
- 範圍：
  1. 路由 `/people/[kind]/[name]`（kind=coach|umpire；中文名 URL-encode，同名以 kind 隔離，規模 25+30 可控；不建 person_dim）
  2. `/people/coach/[name]`：25 名非球員教練——職務史（coaches 歷年）＋若有 managers 戰績卡
  3. `/people/umpire/[name]`：裁判個人頁——執法場次、好球帶判定個人報告（自 umpires router 抽 per-name 查詢）、近期執法場列表（連 games）；順帶解 UX-10 裁判動線問題的一半。**樣本誠實**：執法場次少的裁判判定傾向顯示須帶樣本數（比照 TrackMan 覆蓋慣例）
  4. 新端點（如 `/api/v1/people/umpire/{name}`）入 pytest EXPECTED
- 依賴：無（新路由獨立，可與 7A 平行；7B 的純教練連結等本卡上線後補）
- 驗收：5 秒盲測「這主審好球帶偏不偏」；同名 kind 隔離驗證；橫切驗收見傘卡
- 狀態：✅Gemini 查核通過、已 merge `9c33f32`，待部署　Commit：分支 `ai/fable/UX-7C` 已推送；worktree `../cpbl-analytics-7c`（環境現成，審核可照 §3.1 進駐）
- Log：
  - 07-12 Fable 執行（worktree 首例）：people router 雙端點（教練=coaches+managers、同名唯一才回連球員頁；裁判=崗位場次+記分卡沿 umpires 常數+近期場）＋前端 /people/[kind]/[name]＋/umpires 名字連結入口。pytest 20 passed（EXPECTED 54→56）/ruff/tsc/build 綠；實資料抽驗 葉君璋/平野惠一/蔡豐澤、375 無溢出

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

### COACH-HIST 歷年教練職務史（twbsball 經歷節）  〔⚪一般〕
- 需求：ruan6047（07-12「教練從其他管道拿歷年教練團？」）　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/COACH-HIST`
- 執行：待指派（Sonnet 可＋抽樣人驗；解析規則已列）　查核：待指派（≠執行者）
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

### UX-10 三頁互動模式重設計（暫緩）  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：待各自小 spec　分支：`ai/<執行者>/UX-10-*`
- 執行：待指派　查核：待指派
- 範圍：`/projections`、`/predict`、`/umpires`——問題在**互動模型不在視覺**（predict 特徵子集探索器、projections 投影瀏覽、umpires 報告閱讀動線）。**不在本輪執行序**；屆時拆三張卡各出小 spec。本輪 UX-2/3/4 的 tokens/元件仍會套到這三頁（外觀統一），但不動互動模型。
- **併入 ML-SIM1**（ruan6047 07-12）：H2H 對戰模擬器 v2（PROPOSAL_EVALUATION D 案）併進 predict 小 spec 一起規劃——蒙特卡羅/馬可夫打席模擬（pitch mix×打者對球種決策），🔴 紅線：輸出必附基準對照+不確定性（承賽果預測準則）、預計算用物化表非 Redis、禁裝飾動畫；umpires 部分注意 UX-7C 已先解掉裁判個人頁那半。
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
