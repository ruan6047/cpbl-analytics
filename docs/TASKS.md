# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`
> **只留活卡**：卡片一旦 🏁完成 或 📥封存，整段移到 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)（Ledger 列一併移），本檔保持精簡省 AI 讀取算力。

---

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| VENUE-DEFUNCT | 已拆除球場納入球場維度（老台中球場等） | ruan6047 | 待小 spec | 待指派 | 待指派（≠執行者） | `ai/<執行者>/VENUE-DEFUNCT` | ⚪ | 📥Backlog（`台中` 1120 場一軍無 `venue_dim` 列故 `/venues` 不顯示；先定產品範圍） |
| UX-OUTCOME-HOME | 首頁賽事勝率預測整合與重製 | ruan6047 | 待小 spec | 待指派 | 待指派 | `ai/<執行者>/UX-OUTCOME-HOME` | ⚪ | 📥Backlog（首頁移除後獨立成新卡） |
| ML-MATCHUP1 | 天敵候選／優勢對位統計洞察 | ruan6047 | GPT-5@Codex（[`spec`](../matchups-redesign.md)；建議 Fable） | 待指派 | 待指派（跨家族模型或人審） | `ai/<執行者>/ML-MATCHUP1` | 🔴 | 📥Backlog（依賴 MATCHUP-DATA1；baseline、shrinkage、敏感度驗證） |
| UX-MATCHUP1 | `/matchups` 查詢式頁面重製 | ruan6047 | GPT-5@Codex（[`spec`](../matchups-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/UX-MATCHUP1` | ⚪ | 📥Backlog（依賴 MATCHUP-DATA1＋ML-MATCHUP1） |
| UX-MATCHUP2 | 投打對決整合球員個人頁 | ruan6047 | GPT-5@Codex（[`spec`](../matchups-redesign.md)） | 待指派 | 待指派（≠執行者） | `ai/<執行者>/UX-MATCHUP2` | ⚪ | 📥Backlog（依賴 UX-MATCHUP1；共用元件與 deep-link） |
| RECORD-DATA1 | 歷年總冠軍權威資料集與球團映射 | ruan6047 | GPT-5@Codex（[`spec`](../records-redesign.md)；建議 Fable） | GPT-5@Codex | Opus-4.8@Claude Code | `ai/gpt-5-codex/RECORD-DATA1` | 🔴 | ✅通過（07-14 事後查核：33 季由 games kind C 獨立推導零差異；1992/94/95 以半季戰績重建佐證；教練獎 24/24 交叉驗證） |
| RECORD-API1 | 紀錄室分類排行與冠軍 API | ruan6047 | Opus-4.8@Claude Code | Opus-4.8@Claude Code | GPT-5@Codex | `ai/opus-4.8/RECORD-API1` | ⚪ | ✅完成（07-15 兩項 findings 已由 RECORD-API1-FIX1 修復、查核通過並合併 main） |
| RECORD-API1-FIX1 | 修正冠軍榜現役判定與球團榜 top N | ruan6047 | Opus-4.8@Claude Code | Opus-4.8@Claude Code | GPT-5@Codex | `ai/opus-4.8/RECORD-API1-FIX1` | ⚪ | ✅通過（07-15 查核：現役聯集、並列 top N、pytest 乾淨 collection 與 coverage fail-closed 均實測通過） |
| UX-RECORD1 | `/records` 歷史重要性導向重製 | ruan6047 | Opus-4.8@Claude Code（spec 不存在→當場定範圍） | Opus-4.8@Claude Code | 待指派（≠執行者） | `ai/opus-4.8/UX-RECORD1` | ⚪ | 🔍待查核（07-15 冠軍為核心＋重排：王朝榜 hero＋生涯榜提第二＋逐年冠亞軍＋球員冠軍次數；coverage fail-closed；build:check/tsc 綠、深淺色截圖驗證） |
| ML-UMP1 | 好球帶判決差異的預期影響研究 | ruan6047 | GPT-5@Codex（[`approved spec`](../umpire-impact-research.md)） | GPT-5@Codex | Fable（獨立重建） | `ai/gpt-5-codex/ML-UMP1` | 🔴 | 🔍待複查（P2-1／P2-2 已修正；run value 僅研究元件、WP／方向性產品 no-go；[`results`](research/ML-UMP1_RESULTS.md)） |
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


### RECORD-API1 紀錄室分類排行與冠軍 API  〔⚪一般〕
- 需求：ruan6047　規劃／執行：Opus-4.8@Claude Code　查核：待指派（≠ 執行者）　分支：`ai/opus-4.8/RECORD-API1`
- **範圍由 ruan6047 當場定案**（原 spec `records-redesign.md` 不存在，卡片無詳細段落 → 反問而非腦補）：完整冠軍編＋並列排名＋現役標記＋可調 top N。
- 產出：
  1. **新端點 `/api/v1/records/championships`**：36 季逐年冠亞軍＋奪冠總教練、球團王朝榜（兄弟／統一並列 10 座，總和 36 = 季數）、球員冠軍次數榜。冠軍教練取自 canonical `championship_managers`，**非** `managers.championships`（維基來源、漏記 7 筆）。
  2. **紅線兌現**：看板明訂「冠軍資料缺年不得公開歷史最多冠軍結論」，但 `championship_coverage()` 先前**只在建置期跑、沒有任何 API 消費**——契約形同虛設。現在 coverage 隨回應附帶，且**缺年時直接不回傳累計排行**（API 擋，非前端自律）。突變測試：把 2013 標為未驗證 → `complete=false`、排行消失、附原因；還原後才回來。
  3. **並列排名**：生涯榜改 `rank()`（同值同名次）。舊版直接 LIMIT 會把同分者任意切掉——生涯同分常見，切掉誰是隨機的＝假排名。故回傳列數可能超過 `limit`。
  4. **現役判定**改為官方登錄名單 ∪ 本季有成績（單用任一都會漏；見記憶 player-name-authority）。
- 相容性：舊 `/api/v1/records` 回應結構不變，僅新增 `rk` 欄位與 `?limit=`。
- 驗收：`ruff` 綠、`pytest` 120 passed（含路由快照 EXPECTED 同步）；coverage 紅線有突變測試。
- **⚠️ 流程缺失（執行者自陳）**：違反 AI_WORKFLOW §2「執行 → 查核 → merge」——**已直接 push main**（`f364f01`、`b9d40d0`），順序顛倒，跳過 merge 閘門；且一度刪除分支與 worktree，讓查核者無處進駐（ruan6047 當場指出）。ruan6047 裁示採**事後查核**（不回退 main）。分支與 worktree 已重建。
- **查核者進駐**：worktree `/Users/ruanruan/Dev/cpbl-analytics-rec`（分支 `ai/opus-4.8/RECORD-API1`，已推遠端；環境現成可直接跑測試）。查核範圍＝`ee9ff20..b9d40d0` 兩個 commit。
- 狀態：✅完成　Commit：`f364f01`、`b9d40d0`；修復／查核／合併見 `RECORD-API1-FIX1`（merge `2adb25e`）
- Log：
  - 07-15 ruan6047 派工；spec 檔不存在 → 反問定範圍後執行
  - 07-15 執行完成但**流程有誤**：直接推 main、刪分支與 worktree；經 ruan6047 指正後重建，改採事後查核。教訓已寫入記憶 `review-before-merge`。
  - 07-15 查核 by GPT-5@Codex → ↩退回（事後查核；開 `RECORD-API1-FIX1`：冠軍球員榜現役判定漏本季成績來源；球團王朝榜未套用 `?limit=`）
  - 07-15 結案 by GPT-5@Codex → ✅完成：`RECORD-API1-FIX1` 已修復兩項 findings、獨立查核通過並合併 `main`（`2adb25e`）。

### RECORD-API1-FIX1 修正冠軍榜現役判定與球團榜 top N  〔⚪一般〕
- 需求：ruan6047　執行：Opus-4.8@Claude Code　查核：GPT-5@Codex　分支：`ai/opus-4.8/RECORD-API1-FIX1`
- 來源：RECORD-API1 事後查核（GPT-5@Codex）的兩項 findings。
- 產出：
  1. **現役判定分岔**（P1）：現役定義（登錄名單 ∪ 本季有成績）原本在 `leaders.py` 寫了**兩份**，冠軍球員榜那份漏了 `*_current`，導致本季有成績但不在現行登錄名單者（升降／離隊，如張志豪 `0000003183`）被標成非現役。抽成 `_active_expr(alias)` 由生涯榜與冠軍榜共用，杜絕再次分岔。
  2. **top N 未套用**（P2）：`limit` 沒作用在球團王朝榜，`?limit=1` 仍回全部五隊。改用與球員榜相同的 `rank() <= n`，`limit=1` 正確回傳並列第一的兄弟／統一兩隊。
  3. **附帶修好驗證迴圈**：`tests/test_championship_managers.py` 會 `import tests.test_championships`，但 repo 既無 root `conftest.py` 也未設 `pythonpath` → **乾淨 checkout 下整套 pytest collection 直接失敗**。先前的「pytest 綠」是在帶 `PYTHONPATH` 的環境跑出來的，等於驗證迴圈失效。`pyproject.toml` 補 `pythonpath = ["."]`。
- 驗收：`ruff` 綠、`pytest` **122 passed**（新增 2 支）。兩支新測試**對修復前的程式碼皆為紅**（已實跑確認），確定擋得住回歸。實測：張志豪 `active` 由 `false` → `true`；`limit=1` 球團榜回兄弟／統一（rk 皆 1）；王朝榜總座數 36 = 季數 36。
- **查核者進駐**：worktree `/Users/ruanruan/Dev/cpbl-analytics-recfix`（分支已推遠端，環境現成）。查核範圍＝`85e61ce`、`2e12422`。**本卡未 push main**，merge 待查核通過。
- 狀態：✅通過　Commit：`85e61ce`、`2e12422`
- Log：
  - 07-15 依查核 findings 執行；流程照 §2 走（推分支、留 worktree、不碰 main）
  - 07-15 查核 by GPT-5@Codex → ✅通過：乾淨 main 未設 `PYTHONPATH` 時 pytest collection 確實因 `tests` 無法 import 而失敗；兩支新回歸測試植入修復前碼皆紅。修復分支 `uv run ruff check` 綠、`uv run pytest` 122 passed；張志豪（0000003183）API `active=true`，`limit=1` 僅回兄弟／統一並列第一，36 冠總數與 coverage fail-closed 突變皆通過（2013 已還原）。

### UX-RECORD1 `/records` 歷史重要性導向重製  〔⚪一般〕
- 需求：ruan6047　規劃／執行：Opus-4.8@Claude Code　查核：待指派（≠ 執行者）　分支：`ai/opus-4.8/UX-RECORD1`
- **範圍由 ruan6047 當場定案**（spec `records-redesign.md` 不存在 → 反問而非腦補）：中度重製，冠軍為核心＋重排。**生涯排行（各項數據歷史榜）提到第二**（ruan6047 補充：不沉到頁尾）。
- 動機：RECORD-API1 新做的 `/api/v1/records/championships`（王朝榜／逐年冠亞軍／球員冠軍次數）**先前前端完全未消費**——整條紅線資料鏈（RECORD-DATA1→API1）沒有任何 UI 出口。
- 產出（純前端，`web/src/app/records/page.tsx` ＋ `web/src/lib/api.ts`，**無 Python／無新端點**）：
  1. 首屏「冠軍王朝榜」：各球團奪冠數**隊色長條圖**，並列排名（兄弟／統一並列 10、樂天 8、味全 5、富邦 3；總和 36＝季數）＋逐年奪冠 chip。
  2. 生涯排行提第二（打者／投手兩欄）。
  3. 逐年冠亞軍時間軸（2025→1990）＋奪冠總教練（canonical `championship_managers`）。
  4. 球員冠軍次數榜（並列排名、現役標記、奪冠年份）。
  5. **coverage fail-closed**：API 缺年時不回 `franchise_ranking`／`player_ranking`，前端據此**不呈現累計王朝結論**、改顯示 `Notice`（兌現看板紅線「缺年不得公開歷史最多冠軍」）。
  6. 整頁重排：冠軍王朝→生涯排行→逐年冠亞軍→球員冠軍→單季之最→比賽紀錄→歷代球隊。
- 驗收：`npm run build:check` 綠、`tsc --noEmit` 綠、`/records` 深淺色截圖均驗證（王朝榜隊色長條、並列排名、年份 chip 皆正確）。無 Python 變更故 pytest 路由快照不受影響。
- **查核者進駐**：worktree `/Users/ruanruan/Dev/cpbl-analytics-record`（分支已推遠端，環境現成、`web/node_modules` 已裝）。查核範圍＝`b593181`（單一 commit）。**本卡未 push main**，merge 待查核通過。
- 狀態：🔍待查核　Commit：`b593181`
- Log：
  - 07-15 ruan6047 派工；spec 不存在 → 反問定範圍（中度：冠軍為核心＋重排）後執行；補充「生涯榜提第二」
  - 07-15 執行完成，流程照 §2 走（開 worktree、推分支、留 worktree、不碰 main）

### ML-UMP1 好球帶判決差異的預期影響研究  〔🔴紅線：統計／反事實估計〕
- 需求：ruan6047（07-14）　規劃：GPT-5@Codex（[`approved spec`](../umpire-impact-research.md)）　分支：`ai/gpt-5-codex/ML-UMP1`
- 執行：GPT-5@Codex　查核：Fable（獨立重建 artifacts＋實測）
- 範圍／驗收：固定垂直帶因缺逐打者 `sz_top/sz_bot`，不是規則真值，canonical 名稱採「好球帶判決差異」，技術欄位仍保留 proxy 語意。建立 count-aware 壘況／出局狀態價值；RE24 本身不能替 called ball/strike 定價。以 2018–2024 建模／調參、2025 untouched test、2018–2025 final refit 評分 2026 TrackMan called 球，按攻守隊與主審做帶 coverage、game-cluster 95% interval、zone／venue sensitivity 的描述性聚合。run value 必勝 count-agnostic baseline；WP 未勝現有 `wp_state()` 即不產出。未通過跨家族紅線查核前，不進 API／UI／production table，不稱實際得失分或裁判真實誤判。
- 狀態：🔍待複查　Commit：`a48c47e`、`2136c8b`、`870d310`、`e3583ba`、`b043d9b`、`acea786`、`141e452`、`57bab21`、`f223148`、`923ff66`
- Log：
  - 07-14 自 UX-10 拆出：反事實估計不宜與一般 UI 同卡；依 AI_WORKFLOW 採 Fable 執行、跨家族或人審查核
  - 07-15 ruan6047 指派研究規格；GPT-5@Codex 建獨立 worktree。唯讀稽核：2026 A called pitches 24,270，24,195（99.69%）唯一連到 livelog，24,226（99.82%）可合法還原 pre-call 球數；歷史 2018–2025 有 730,112 pitch rows／2,335 場。spec 糾正兩個前提：固定帶非規則真值、RE24 不含球數故不可直接定價。
  - 07-15 ruan6047 核可 spec 四項決策：canonical 名稱原採代理帶判決差異；run value 為主、WP 需過 gate；研究期僅離線報告；fixed proxy 必附敏感度且不得當 ground truth。轉 ⏳待執行，等待指派實作者。
  - 07-15 ruan6047 確認人工審查 spec 通過並指派繼續執行；GPT-5@Codex 接 R0→R3，最終查核仍須跨家族或人工獨立實測。
  - 07-15 R0–R3 完成：24,270 called pitches 中 24,192 可評分；2018–2025 歷史 645,705 states。2025 run-value NLL/MAE 均勝 count-agnostic baseline，WP 雖點估計略優但兩項 2,000 次 game-bootstrap interval 都跨 0，依 gate no-ship。
  - 07-15 正式 scoring：2,661 proxy disagreements、260 backoffs；2,000 次 bootstrap 每次同時重建歷史 value table 與 2026 場次聚合。18/18 主審與 6/6 球隊皆 zone-sensitive，coverage 165/200 場，故固定代理帶方向性產品 no-go；API/UI/production table 均未新增。完整報告見 [`docs/research/ML-UMP1_RESULTS.md`](research/ML-UMP1_RESULTS.md)。
  - 07-15 全專案 `ruff check` 綠、`pytest` 165 passed（1 個既有 Starlette/httpx deprecation warning）；CLI audit/validate/score 與 24,192 行 ignored pitch artifact 實測完成。worktree 保留，等待跨家族或人工獨立查核。
  - 07-15 ruan6047 補充 canonical 對外名稱改為「好球帶判決差異」；技術欄位與限制仍保留 `fixed_zone_proxy_v1`／`proxy_disagreement`，避免誤讀為逐打者規則真值。
  - 07-16 Fable 於 detached review worktree 獨立重建全部 artifacts；統計核心、連結契約、狀態轉移、時間切分、bootstrap、gate 與數字均精確重現。退回 P2-1 球隊缺 game-cluster interval、P2-2 預先註冊 baseline／敏感度缺項；未修改實作檔案。
  - 07-16 GPT-5@Codex 修正 P2-1／P2-2：球隊 for/against 與主審共用同一 bootstrap replicate 並附累計及每百顆 95% interval；補主場常數 WP sanity baseline、差異顆數／離帶距離 baseline、home/away／月份分層、現行非對稱 50cm filter 對照。正式 2,000 次重建完成，既有 gate 與所有主結論不變，轉 🔍待 Fable 快速複查。
  - 07-16 修正後驗證：全專案 ruff 綠、pytest 170 passed（僅既有 Starlette deprecation warning）；audit 24,270／24,195／24,226／24,192／3 精確不變，validate 2,000 次與原 gate 數字逐位相同，score 2,000 次 artifacts 已重建。

### RECORD-DATA1 歷年總冠軍權威資料集與球團映射  〔🔴紅線：歷史資料正確性〕
- 需求：ruan6047　規劃：GPT-5@Codex（[`spec`](../records-redesign.md)）　分支：`ai/gpt-5-codex/RECORD-DATA1`
- 執行：GPT-5@Codex　查核：待指派（跨模型家族或人審＋資料實測）
- 範圍：1990–2025 共 36 季 canonical championships dataset、逐年官方來源、歷史隊碼→franchise mapping、coverage 契約；`championship_members` 改以 canonical dataset 決定冠軍隊。
- 驗收：36 季無缺漏；1992／1994／1995 有官方來源；franchise mapping 與既有沿革一致；重跑冪等；缺年時 coverage 必須降級，不得產生完整歷史結論。
- 狀態：✅通過　查核：Opus-4.8@Claude Code（≠ 執行）　Commit：`7f4dbc9`、`760e942`
- Log：
  - 07-14 ruan6047 派工；建立隔離 worktree，開始官方來源與既有 33 季 games 推導結果交叉核對
  - 07-14 實作完成：新增 `championships` canonical dataset（1990–2025）、共用 franchise mapping、coverage fail-closed 契約；`championship_members` 改由已驗證資料重建
  - 07-14 自測：migration 連跑兩次維持 36 季；33 季 vs games 冠軍零差異；1992／1994／1995 補入 25／23／30 名球員；重建連跑兩次皆 1,461 列；`ruff` 綠、`pytest` 49 passed（1 個既有 Starlette deprecation warning）
  - 07-14 push 因公開 GitHub 外傳需明確授權而被安全審查拒絕；依交接出口條件維持 🔨，待 ruan6047 明確授權 push 後再轉 🔍待查核
  - 07-14 ruan6047 授權 PUSH：確認程式碼已併入 main 並推至 origin/main；正式轉為 🔍待查核，等待指派查核
  - 07-14 查核 by Opus-4.8@Claude Code → ✅通過（**以資料獨立重建驗證，非讀 code**）：
    - 33 個有台灣大賽的年份，**冠軍／亞軍／系列賽比分全部逐年吻合**（由 games kind C 自行推導）。2002/2017/2018 的「3 勝封王」正對應半季雙冠的讓一勝，非資料缺漏。
    - 最該懷疑的 1992/1994/1995（無台灣大賽）：以逐場資料重建上下半季戰績，1992/94 兄弟象、1995 統一獅**皆兩個半季居首**，獨立佐證「包辦半季直接封王」。
    - 建置面：36 季、championship_members 1,461 列、1992/94/95 各 25/23/30 名；TRUNCATE 重建冪等；僅採 verification_status='verified'。
    - 交接風險（已於 054 卡處理）：`championship_coverage()` 當時無 API 消費、`CANONICAL_THROUGH_YEAR` 寫死。

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
