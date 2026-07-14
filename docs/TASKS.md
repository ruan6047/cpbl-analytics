# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`
> **只留活卡**：卡片一旦 🏁完成 或 📥封存，整段移到 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)（Ledger 列一併移），本檔保持精簡省 AI 讀取算力。

---

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UX-OUTCOME-HOME | 首頁賽事勝率預測整合與重製 | ruan6047 | 待小 spec | 待指派 | 待指派 | `ai/<執行者>/UX-OUTCOME-HOME` | ⚪ | 📥Backlog（首頁移除後獨立成新卡） |
| ML-MATCHUP1 | 天敵候選／優勢對位統計洞察 | ruan6047 | GPT-5@Codex（[`spec`](../matchups-redesign.md)；建議 Fable） | 待指派 | 待指派（跨家族模型或人審） | `ai/<執行者>/ML-MATCHUP1` | 🔴 | 📥Backlog（依賴 MATCHUP-DATA1；baseline、shrinkage、敏感度驗證） |
| UX-MATCHUP1 | `/matchups` 查詢式頁面重製 | ruan6047 | GPT-5@Codex（[`spec`](../matchups-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/UX-MATCHUP1` | ⚪ | 📥Backlog（依賴 MATCHUP-DATA1＋ML-MATCHUP1） |
| UX-MATCHUP2 | 投打對決整合球員個人頁 | ruan6047 | GPT-5@Codex（[`spec`](../matchups-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/UX-MATCHUP2` | ⚪ | 📥Backlog（依賴 UX-MATCHUP1；共用元件與 deep-link） |
| RECORD-DATA1 | 歷年總冠軍權威資料集與球團映射 | ruan6047 | GPT-5@Codex（[`spec`](../records-redesign.md)；建議 Fable） | GPT-5@Codex | 待指派（跨家族模型或人審） | `ai/gpt-5-codex/RECORD-DATA1` | 🔴 | 🔨實作完成，待授權 push（36 季完整；本機資料 QA＋49 tests 綠） |
| RECORD-API1 | 紀錄室分類排行與冠軍 API | ruan6047 | GPT-5@Codex（[`spec`](../records-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/RECORD-API1` | ⚪ | 📥Backlog（依賴 RECORD-DATA1；相容擴充、並列排名、現役篩選） |
| UX-RECORD1 | `/records` 歷史重要性導向重製 | ruan6047 | GPT-5@Codex（[`spec`](../records-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/UX-RECORD1` | ⚪ | 📥Backlog（依賴 RECORD-API1；首屏標竿、生涯榜、冠軍王朝） |
| ML-UMP1 | 裁判誤判預期影響研究 | ruan6047 | 待研究 spec（建議 Fable） | 待指派 | 待指派（跨家族模型或人審） | `ai/<執行者>/ML-UMP1` | 🔴 | 📥Backlog（先驗證再決定是否產品化，不併 UX-10） |
| VENUE-PARK1 | 球場滾飛比／Park Factor／選手極端表現（資料＋API） | ruan6047 | Fable（park factor 公式＋小樣本呈現需統計判斷） | Fable-5@Claude Code | GPT-5@Codex | `ai/fable-5/VENUE-PARK1` | 🔴 | ❌部署驗證失敗（程式已上線；production 缺 2018–2025 splits） |
| UX-VENUE1 | `/venues/[venue]` 球場詳情頁 | ruan6047 | Sonnet@Claude Code | 待指派（Sonnet） | 待指派（≠執行者） | `ai/<執行者>/UX-VENUE1` | ⚪ | 📥Backlog（依賴 VENUE-PARK1；純 UI，吃前卡 API） |
| COACH-HIST | 歷年教練職務史（twbsball 經歷節） | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📥Backlog（7C 已上線，接點就緒可排） |
| ML-PT3 | 中職版球路品質指數 (CPBL Stuff+) | ruan6047 | 評估報告+Fable 勘誤 | 待指派 | 待指派 | — | 🔴 | 📥Backlog（**排 2026 季末**；勘誤見 PROPOSAL_EVALUATION.md 附錄） |
| ML-SIM1 | 簡易勝負預測＋單一打席情境模擬 | ruan6047 | 待細 spec | 待指派 | 待指派 | — | 🔴 | 📥Backlog（取代 UX-10O；去重複訊號，不模擬後續全打席） |
| ML-SIM2 | 全場狀態模擬器（完整陣容／牛棚／後續打席） | ruan6047 | 待遠期評估 | 待指派 | 待指派 | — | 🔴 | 📥Backlog（**遠期目標，暫時不做**） |
| TEAM-STYLE1 | 球隊球風研究（年度／時期風格向量→球隊頁＋賽果候選特徵） | ruan6047 | 待研究 spec | 待指派 | 待指派 | — | 🔴 | 📥Backlog（速度戰／投手戰等為待驗證假說；先描述，增量回測通過才進模型） |

> 「待指派」＝ruan6047尚未派工。派工後把 model@tool 補實、狀態改 🔨。
> **依賴序**：通用層（UX-2/3/4/4.5）🏁 → 頁面層 UX-5〜10 已解鎖。**UX-5A/5B/6/7/8/9/10 群 🏁完成並上線**；剩 **UX-5C（首頁完整版，壓最後重製）**。
> **投打對決依賴序**：`MATCHUP-DATA1 → ML-MATCHUP1 → UX-MATCHUP1 → UX-MATCHUP2`。前兩卡為資料／統計紅線，須先獨立查核通過，UI 卡才能開工。
> **紀錄室依賴序**：`RECORD-DATA1 → RECORD-API1 → UX-RECORD1`。冠軍資料缺年屬資料正確性紅線，須補齊並獨立查核通過後，才能公開「歷史最多冠軍」結論。
> **球場依賴序**：`VENUE-PARK1 → UX-VENUE1`。前卡為統計紅線（park factor 公式／小樣本呈現），須先獨立查核通過，UI 卡才能開工。

---

## 進行中／待辦卡

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

### ML-UMP1 裁判誤判預期影響研究  〔🔴紅線：統計／反事實估計〕
- 需求：ruan6047（07-14）　規劃：Fable（統計定義／驗證設計）　分支：`ai/<執行者>/ML-UMP1`
- 執行：待指派　查核：待指派
- 範圍／驗收：定義每個錯判在判決前狀態的預期得分或勝率差（實際判決對比正確判決的反事實結果），按攻守隊與裁判聚合；先建立可重現的 RE24 或勝率基準、資料切分、校準與不確定性，並對照「漏判數／距離」baseline。僅用有 TrackMan 的 called 球；未通過獨立審核與實測前，不寫入 UI、不稱為球隊實際得利或失分。
- 狀態：📥Backlog　Commit：—
- Log：
  - 07-14 自 UX-10 拆出：反事實估計不宜與一般 UI 同卡；依 AI_WORKFLOW 採 Fable 執行、跨家族或人審查核

### RECORD-DATA1 歷年總冠軍權威資料集與球團映射  〔🔴紅線：歷史資料正確性〕
- 需求：ruan6047　規劃：GPT-5@Codex（[`spec`](../records-redesign.md)）　分支：`ai/gpt-5-codex/RECORD-DATA1`
- 執行：GPT-5@Codex　查核：待指派（跨模型家族或人審＋資料實測）
- 範圍：1990–2025 共 36 季 canonical championships dataset、逐年官方來源、歷史隊碼→franchise mapping、coverage 契約；`championship_members` 改以 canonical dataset 決定冠軍隊。
- 驗收：36 季無缺漏；1992／1994／1995 有官方來源；franchise mapping 與既有沿革一致；重跑冪等；缺年時 coverage 必須降級，不得產生完整歷史結論。
- 狀態：🔨實作完成，待授權 push　Commit：`7f4dbc9`、`760e942`
- Log：
  - 07-14 ruan6047 派工；建立隔離 worktree，開始官方來源與既有 33 季 games 推導結果交叉核對
  - 07-14 實作完成：新增 `championships` canonical dataset（1990–2025）、共用 franchise mapping、coverage fail-closed 契約；`championship_members` 改由已驗證資料重建
  - 07-14 自測：migration 連跑兩次維持 36 季；33 季 vs games 冠軍零差異；1992／1994／1995 補入 25／23／30 名球員；重建連跑兩次皆 1,461 列；`ruff` 綠、`pytest` 49 passed（1 個既有 Starlette deprecation warning）
  - 07-14 push 因公開 GitHub 外傳需明確授權而被安全審查拒絕；依交接出口條件維持 🔨，待 ruan6047 明確授權 push 後再轉 🔍待查核

### VENUE-PARK1 球場滾飛比／Park Factor／選手極端表現（資料＋API）  〔🔴紅線：統計正確性（小樣本描述性統計仍可能誤導，同 Marcel／賽果誠實原則）〕
- 需求：ruan6047（07-14）——現有 `/venues` 只有球場規格／使用量，對數據解讀沒有參考意義；要記錄每個球場的滾飛比、球場數據特色（如不容易全壘打）、在該球場表現特別出眾／特別差的選手。
- 規劃：Sonnet@Claude Code 查證（見下方現況盤點），park factor 公式與小樣本呈現方式定案交 Fable。
- **現況盤點（已查證，非腦補）**：
  1. **滾飛比免新爬蟲**：`batting_splits`／`pitching_splits` 已有「球場」split family（`item_group_code`，含 `ground_outs`/`fly_outs`），只是從未按球場軸彙總過。
  2. **Park factor 沒有現成欄位**，需新算式；`games`／`batting_gamelog` 有逐場比分/HR 可用「主客對照法」（同隊主場 vs 該隊客場 HR／長打率比值，控制球隊強弱差異）。
  3. **選手極端表現免新爬蟲**：同一組球場 split family 就是「每位選手在每個球場」的 rate stats（AVG/OBP/SLG/OPS），要做的是排序找極端值（設最低樣本門檻）。
  4. **時間粒度**：`batting_splits` 目前只存 `year=2026`（本季即時重算）＋生涯累計（`9999`），無逐年歷史列。但 `cpbl-build-splits <year>` CLI **本來就吃 year 參數**且表 PK 含 `year`，對 2018–2025 逐年各跑一次即可回填、不會互相覆蓋——**這是資料維運（C 類），不用開分支／不算程式碼變更**，需要驗證的是各年球場 family 是否正常產出（`splits_calc.py` 已有未知 item fail-loud 機制）。
- **範圍**：
  1. 資料維運：對 2018–2025 逐年跑 `cpbl-build-splits <year>`，確認球場 family 各年正常、無 diagnostics 未知 item。
  2. 定案 park factor 公式（主客對照法）、GB/FB 彙總邏輯、選手極端值排序邏輯與最低樣本門檻。
  3. 新 API：本季／生涯／逐年的球場滾飛比、主客對照 park factor、選手在該球場 rate stats 對生涯排序找極端值。
- **誠實揭露（紅線）**：
  1. 資料僅涵蓋 2018+（`batting_gamelog`/livelog 起始年，1990–2017 無法歸因球場）。
  2. 單球場單季主場數僅 10–25 場，輸出必須附樣本數／場次，用字避免「這球場就是不容易全壘打」式斷言；park factor 採主客對照法（控制球隊強弱），不比聯盟平均（避免被強弱隊主場用量差干擾）。
- 交付物：API contract（含樣本數欄位）＋資料驗證報告，供 UX-VENUE1 直接消費 → **[`VENUE_PARK1_CONTRACT.md`](VENUE_PARK1_CONTRACT.md)**。
- 狀態：📦已合併／❌部署驗證失敗　Merge commit：`216a263`；程式已上線，待同步歷史 splits 後重驗
- Log：
  - 07-14 需求＋現況盤點（Sonnet）：確認滾飛比／選手極端表現免新爬蟲（沿用既有 `batting_splits`/`pitching_splits` 球場 family）；park factor 需新算式（主客對照法，ruan6047 07-14 選定）；逐年回填（2018–2025，ruan6047 07-14 選定）靠既有 `cpbl-build-splits <year>` CLI，屬資料維運非程式碼變更
  - 07-14 ruan6047 裁示拆卡：紅線（公式／樣本數判斷）與 UI 分離，方便各自配模型（Fable vs Sonnet）→ 拆出 UX-VENUE1，本卡收斂為資料＋API
  - 07-14 ruan6047 派工 Fable-5@Claude Code；開 worktree `../cpbl-analytics-venue-park1`（分支 `ai/fable-5/VENUE-PARK1`）
  - 07-14 ⚠️ 規劃修正：`cpbl-build-splits <year>` CLI 會連跑 `build_career`（生涯=base+**指定年**，base 錨定 2026）——對歷史年跑會**改寫生涯表**。回填改直接呼叫 `build_splits()`、不經 CLI；規劃卡「屬資料維運」的前提部分不成立（需先補 14 個歷史詞彙＋2 個球場別名的 A 類程式碼變更）
  - 07-14 回填完成：2018–2025×(A,D) 全綠零未知詞彙（14 詞逐個抽 content 原文定案語意，`失`/`裁決` 型態不明不猜滾飛、比照「違規」，全史 ~33 例缺口記報告）；PA 量級核對 ≈78/場 ✓；僅本機 DB、生產未同步
  - 07-14 Fable-5@Claude Code 實作完成 commit `08c1bed`（ingest 詞彙+別名）、`072699c`（API 三端點+無 DB 測試）、`df72c38`（contract+驗證報告）：`/venues/{venue}/factors|stats|players`。方法論＝主客對照 PF（分季配對、合併=Σobs/Σexp 非 PF 平均、n_else=0 排除、單季<30/合併<60 場 low_sample、不做 shrinkage）；`ruff`+`pytest` 51 passed；實測抽驗：大巨蛋 HR PF 0.661（124 場，逐季一致）、新莊 2024 1.33、桃園別名合併 9 季 489 場、未知球場 404、王柏融大巨蛋 Δ−.35（128 PA 明示）。待跨家族查核（審核者可進駐 worktree `../cpbl-analytics-venue-park1`）
  - 07-14 查核退回（第 1 次）：①`games`=隊-場/2，單方隊-季被排除時輸出 0.5 場，違反場次語意且 low_sample 失真（`venues.py` 舊 179 行）②worktree 內 `TASKS.md` 停在分支時點快照與看板現況不符 ③查核環境 Docker db 未啟動，紅線卡待補真 DB 實測
  - 07-14 Fable-5@Claude Code 修復 commit `1813647`：`games` 改回傳實際完成場次（整數；SQL 端每場恆 2 隊列、排除只在 Python 聚合，Σ含排除/2 恆整數），估計基礎另立 `eligible_team_games`/`excluded_team_games`（逐季+合併皆帶），`low_sample` 改依估計基礎（單季<2×30、合併<2×60 隊-場）；obs/exp/PF 數學不變。新增回歸測試重現單方排除（舊 0.5 → 修後 games=1 int）；契約文件同步。真 DB 實測（本機 db 已起）：大巨蛋/花蓮/桃園逐季+合併 games 全整數、PF 與修前一致（0.661/1.36/0.998）。另 merge main 進分支（`cf2ae57`）使 worktree 看板同步現況；合併後全套 67 tests 綠。待重新查核——**紅線卡查核需起本機 db（`docker compose up -d db`）做端點實測與回填對帳**
  - 07-14 跨家族查核（GPT-5@Codex）：`pytest` 67/67、`ruff` 綠；真 DB 實測大巨蛋／樂天桃園／新莊皆滿足 `eligible_team_games + excluded_team_games = games × 2`，HR PF 分別為 0.661／0.998／0.900；通過後合併 main（`216a263`），待部署驗證
  - 07-14 部署：cpbl main `77ffa63` → 主站 submodule `6b9b0a1` → GitHub CI/Deploy 成功；公開 `/api/info` 與三個新端點皆 200。**驗證失敗**：`/venues/大巨蛋/stats?from_year=2018` 僅回 2026（預期含 2018–2025），production 缺歷史 `batting_splits` 回填資料；未安全比較本機／production 資料新鮮度前，禁止用整 schema 覆寫。待資料同步後重驗並更新狀態。

### UX-VENUE1 `/venues/[venue]` 球場詳情頁  〔⚪一般〕
- 需求：ruan6047（07-14，與 VENUE-PARK1 同源）　規劃：Sonnet@Claude Code　分支：`ai/<執行者>/UX-VENUE1`
- 依賴：**VENUE-PARK1 查核通過**（API contract 定案）才能開工。
- **範圍**：新頁 `/venues/[venue]`：球場規格（沿用現有 `venue_dim`：`lf_dist`/`cf_dist`/`rf_dist`/`big_screen` 等，`043_venue_specs.sql`）＋ VENUE-PARK1 產出的滾飛比／park factor／選手極端值清單；`/venues` 列表卡片改可點擊進入。UI 呈現須帶樣本數／場次（沿用 VENUE-PARK1 的誠實揭露要求，不得只列排名不列樣本）。
- 狀態：📥Backlog（待 VENUE-PARK1 解鎖）　Commit：—
- Log：
  - 07-14 自 VENUE-PARK1 拆出：UI 卡與統計紅線卡分離，方便各自配模型

### UX-OUTCOME-HOME 首頁賽事勝率預測整合與重製  〔⚪一般〕
- 需求：ruan6047（07-14）——配合首頁微調將原賽事預測 teaser 移除，未來搭配 `ML-SIM1` 簡易勝負預測模型開發完成後，重新設計高質感的預測卡片整合回首頁。
- 規劃：待指派　分支：`ai/<執行者>/UX-OUTCOME-HOME`
- 執行：待指派　查核：待指派
- 狀態：📥Backlog
- Log：
  - 07-14 自 UX-5C 移除首頁預測 teaser，並獨立開卡至 Backlog

### ML-PT3 中職版球路品質指數 (CPBL Stuff+ Index)  〔🔴紅線：ML/統計正確性〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/ML-PT3`
- 執行：待指派　查核：待指派
- 範圍/驗收：Stuff+ 隨機森林/LightGBM 模型研發與物理評分整合。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

### ML-SIM1 簡易勝負預測＋單一打席情境模擬  〔🔴紅線：統計正確性〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/ML-SIM1`
- 執行：待指派　查核：待指派
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
