# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`
> **只留活卡**：卡片一旦 🏁完成 或 📥封存，整段移到 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)（Ledger 列一併移），本檔保持精簡省 AI 讀取算力。

---

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| [BUG-VENUE-ALIAS](tasks/BUG-VENUE-ALIAS.md) | 球場列表歷史別名歸一 | ruan6047 | GPT-5@Codex | GPT-5@Codex | Opus-4.8@Claude Code | `fix/venue-list-alias-normalization` | ⚪ | ✅通過（事後查核；別名前提經資料驗證，附帶消除第三份規則拷貝） |
| COACH-HIST | 歷年教練職務史（twbsball 經歷節） | ruan6047 | Fable-5@Claude Code | Antigravity | ruan6047 | `ai/antigravity/COACH-HIST-FIX` | ⚪ | ↩退回（重編防禦生日與隊碼碰撞） |
| VENUE-DEFUNCT | 已拆除球場納入球場維度（老台中球場等） | ruan6047 | 待小 spec | 待指派 | 待指派（≠執行者） | `ai/<執行者>/VENUE-DEFUNCT` | ⚪ | 📥Backlog（`台中` 1120 場一軍無 `venue_dim` 列故 `/venues` 不顯示；先定產品範圍） |
| UX-OUTCOME-HOME | 首頁賽事勝率預測整合與重製 | ruan6047 | 待小 spec | 待指派 | 待指派 | `ai/<執行者>/UX-OUTCOME-HOME` | ⚪ | 📥Backlog（首頁移除後獨立成新卡） |
| ML-MATCHUP1 | 天敵候選／優勢對位統計洞察 | ruan6047 | GPT-5@Codex（[`spec`](../matchups-redesign.md)；建議 Fable） | 待指派 | 待指派（跨家族模型或人審） | `ai/<執行者>/ML-MATCHUP1` | 🔴 | 📥Backlog（依賴 MATCHUP-DATA1；baseline、shrinkage、敏感度驗證） |
| UX-MATCHUP1 | `/matchups` 查詢式頁面重製 | ruan6047 | GPT-5@Codex（[`spec`](../matchups-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/UX-MATCHUP1` | ⚪ | 📥Backlog（依賴 MATCHUP-DATA1＋ML-MATCHUP1） |
| UX-MATCHUP2 | 投打對決整合球員個人頁 | ruan6047 | GPT-5@Codex（[`spec`](../matchups-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/UX-MATCHUP2` | ⚪ | 📥Backlog（依賴 UX-MATCHUP1；共用元件與 deep-link） |
| RECORD-DATA1 | 歷年總冠軍權威資料集與球團映射 | ruan6047 | GPT-5@Codex（[`spec`](../records-redesign.md)；建議 Fable） | GPT-5@Codex | 待指派（跨家族模型或人審） | `ai/gpt-5-codex/RECORD-DATA1` | 🔴 | 🔍待查核（36 季完整；待指派人審或跨家族模型查核） |
| RECORD-API1 | 紀錄室分類排行與冠軍 API | ruan6047 | GPT-5@Codex（[`spec`](../records-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/RECORD-API1` | ⚪ | 📥Backlog（依賴 RECORD-DATA1；相容擴充、並列排名、現役篩選） |
| UX-RECORD1 | `/records` 歷史重要性導向重製 | ruan6047 | GPT-5@Codex（[`spec`](../records-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/UX-RECORD1` | ⚪ | 📥Backlog（依賴 RECORD-API1；首屏標竿、生涯榜、冠軍王朝） |
| ML-UMP1 | 裁判誤判預期影響研究 | ruan6047 | 待研究 spec（建議 Fable） | 待指派 | 待指派（跨家族模型或人審） | `ai/<執行者>/ML-UMP1` | 🔴 | 📥Backlog（先驗證再決定是否產品化，不併 UX-10） |
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
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code　分支：`ai/antigravity/COACH-HIST-FIX`
- 執行：Antigravity　查核：ruan6047
- 範圍：
  1. 種子名單＝現任 coaches 72＋managers 90（去重）；爬個人條目經歷節（~150 頁，一次抓+手動刷新，照 wiki-data-sources 慣例）
  2. 解析教練職務行 → 新表 `coach_history(name, team_code, pos, from_date, to_date, source, needs_review)`（migration 冪等）
  3. **解析守則（不腦補）**：行格式變異（兼任/代理/客座 前綴保留進 pos）；日期粒度不一（年/年月/年月日，缺月日存年初/年末界）；隊名歷代對映 team_dim（兄弟象→中信兄弟等，對不上→needs_review）；**非職棒職務**（學校/業餘/國家隊）過濾出主表或另欄標注；解析失敗行一律 needs_review 人工檢
  4. 前端：7C 教練頁「教練職務」表改吃 coach_history（歷年時間軸）；7B 球員頁教練身分區塊同源
- 驗收：抽 10 名教練對照 twbsball 原頁人工核對；needs_review 比率報告；`ruff`+`pytest` 綠
- 狀態：↩退回
- Log：
  - 07-12 需求＋開卡；twbsball 人物經歷節路線可行
  - 07-14 實作資料庫表、經歷解析器、全量爬取 133 名教練生平 6646 條。API 與 Web 端均重構完成。
  - 07-14 查核退回：偵測到跨聯盟隊名字串碰撞（東北樂天金鷲誤對中職樂天桃猿）、敘事型髒資料（無年份、長散文）、同名生日守門漏洞（Wiki無生日直接跳過驗證 review=False）。
  - 07-14 修復實作：
    1. 隊名對照改走 franchises.py 作為單一事實來源；限 `league == '中華職棒'` 匹配，外國一律 `NULL`，加入東北樂天金鷲等關鍵字排除防禦。
    2. 敘事型列（無年份或長散文）於解析時將 phase 標為 `"note"`，並在 API 端點（`people.py` 與 `players.py`）進行 SQL 過濾。
    3. 守門防禦：若同名且 Wiki 無生日（或 DB 無生日）無法互相比對，強制標記 `needs_review = True`，且 `player_id` 設為 `NULL` 阻斷自動歸戶。
    4. 重新全量執行 scraper 過濾數據入庫，更新 pytest 覆蓋各項新案例，全綠通過。

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
- 狀態：🔍待查核　Commit：`7f4dbc9`、`760e942`
- Log：
  - 07-14 ruan6047 派工；建立隔離 worktree，開始官方來源與既有 33 季 games 推導結果交叉核對
  - 07-14 實作完成：新增 `championships` canonical dataset（1990–2025）、共用 franchise mapping、coverage fail-closed 契約；`championship_members` 改由已驗證資料重建
  - 07-14 自測：migration 連跑兩次維持 36 季；33 季 vs games 冠軍零差異；1992／1994／1995 補入 25／23／30 名球員；重建連跑兩次皆 1,461 列；`ruff` 綠、`pytest` 49 passed（1 個既有 Starlette deprecation warning）
  - 07-14 push 因公開 GitHub 外傳需明確授權而被安全審查拒絕；依交接出口條件維持 🔨，待 ruan6047 明確授權 push 後再轉 🔍待查核
  - 07-14 ruan6047 授權 PUSH：確認程式碼已併入 main 並推至 origin/main；正式轉為 🔍待查核，等待指派查核

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
