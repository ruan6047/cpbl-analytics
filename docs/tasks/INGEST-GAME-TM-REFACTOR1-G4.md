# INGEST-GAME-TM-REFACTOR1-G4 逐球正式 writer 切換至單場 API 並對齊存量〔T4；🔴資料正確性紅線〕

- review_independence: [cross_family, human]
- 需求：ruan6047（2026-08-03 會話裁定）　規劃：Claude Opus 5@Claude Code　分支：依認領時 worktree 慣例
- 執行：待指派（建議 L3；refresh 鏈、排程與生產同步的跨模組取捨）　查核：待指派（跨家族技術查核，再需求方 production sign-off；均須 ≠ 執行）
- Initiative：`INIT-OFFICIAL-DATA1`　spec 基線：v1
- DB：`db_scope: write`（`cpbl.pitch_tracking` 冪等 UPSERT；`migration_phase: none`）
- 部署：是　環境：本機排程（`cpbl-refresh-recent` 與新增之每週全季重跑）＋ production 同步　PR：—　Merge SHA：—
- 範圍：[`../research/GAME_TM_SHADOW_OBSERVATION.md`](../research/GAME_TM_SHADOW_OBSERVATION.md) §5 條件 4（Gate 4 cutover），承接同文件條件 1–3 已達成之觀測結論。
- Discovery：[`../research/GAME_TM_SHADOW_OBSERVATION.md`](../research/GAME_TM_SHADOW_OBSERVATION.md) §2–5（Gate 3 shadow 對帳基準、9 天觀測與晉升條件）
- Design：N/A —— 純技術資料管線切換，無使用者可見變更；逐球 UI 與 provisional 標示屬 `INGEST-LIVE-RECONCILE1` 範圍。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 背景

`INGEST-GAME-TM-REFACTOR1` 的 Gate 1–3 已合併且碼已在生產，但**處於 dormant 狀態**：
`run_refresh_recent.py` 仍以逐投手 logs API 為唯一正式 writer，Gate 1–2 的單場 API adapter
（`scrape_game_pitches`）與 Gate 3 的 shadow harness 都只是旁路。本卡執行 Gate 3 文件 §5
條件 4 所指的 cutover，把正式 writer 換成單場 API，並讓存量資料與官方現值對齊。

Gate 3 於 2026-08-03（第 9 天、`run_id=14`）依需求方裁示提前收窗，凍結範圍解除。條件 1–3
的達成證據見 shadow 文件 §3.1 與 §3.2：12 次 run 的非零差異全數收斂為兩類良性模式（新完賽
場時間差、官方賽後修正文字未回補），**無任何一筆物理欄位不一致**；延期／保留／未開打三個
分支改以全季 320 筆賽程回放取證（POSTPONED 24／RESERVED 2／SCHEDULED 60，UNKNOWN 0）。

切換的動機仍是原卡的兩項工程缺陷：請求量與球員名冊異動造成的 acnt 對帳漏損。近 3 天窗口
實測母體為 **14 場 vs 113 位投手**（一軍 9 場／59 人、二軍 5 場／54 人，尚未計
`_lagging_pitch_pitchers` 的額外回抓）。

### 大巨蛋：設備判準的前提已被推翻（2026-08-03 實測）

Gate 3 文件 §5 把大巨蛋連續 3 場雙邊 0 列記為「疑似**新場館**覆蓋缺口」。實測推翻此推測：
該場館 2026-03 覆蓋率 **98.4%**（設備正常運作），2026-05 降為 31.5%（13 場 9 場全零），
**2026-06-02 起 15 場連續全零**至 08-02。直接打官方 API 複驗 sno=238／148／114，livelog
事件 327／336／337 筆完整回傳但**帶 `Trackman` 的 0 筆**——源頭即無資料，非我方漏爬、
亦非發布延遲（5 月場次至 8 月仍為空）。全季該場館 30 場／8,637 球僅擷取 1,739 球。

三項對本卡的直接影響：**其一**，設備狀態是**時變**的，`equipped` 的「本季曾達」判準因
3 月那兩場而讓大巨蛋永久通過，死場次會被每日重抓且永不收斂（見驗收條件）。**其二**，
`cpbl-check-coverage` **一直有在報**（實測列出 25 場含大巨蛋 15 場），缺陷不在偵測而在
**告警無去向**，屬另卡範圍。**其三**，此缺漏與球場綁定而非隨機，以該場館為主場的球隊其
逐球衍生指標會系統性少一成樣本，屬**與球場相關的缺失** [venue-correlated missingness]，
跨隊比較會有偏差——本卡不處理，但不得在 dry-run 對帳中把這類雙邊 0 列誤記為差異。

同批實測另發現：台東 2 場全零且**不在**既有無設備清單（花蓮／嘉義）內；新莊（全季 89.9%）
有 sno=101／104 兩場異常全零；亞太主全季僅 75.9%，明顯低於其餘 90–99% 的場館。

## 驗收條件

### Phase A（iteration 1）：切換增量路徑，不寫存量

- [ ] `run_refresh_recent.py` 的 `_incremental_detail` 與 `_farm_detail` 改以場次維度呼叫
      `scrape_game_pitches`，**kind A 與 kind D 同時切換**；兩者共用既有 pure parser
      `parse_pitches`，不新增第二套欄位映射。
- [ ] `_lagging_pitch_pitchers()`（[`run_refresh_recent.py:82`](../../src/cpbl/ingest/run_refresh_recent.py:82)）
      改寫為 `_lagging_pitch_games()`：輸出 `game_sno` 集合，與當日窗口完成場**取聯集後單次**
      送進 `scrape_game_pitches`，不得成為第二條抓取路徑。
- [ ] **設備判準改為近期感知**：原 SQL 的 `equipped` CTE 採「**本季曾**達 0.80 覆蓋」，此前提
      已被 2026-08-03 實測推翻（見〈背景〉大巨蛋一節）——設備狀態會**隨時間變化**，用全季
      歷史當判準會讓一個已停止產出兩個月的球場永久通過測試、其死場次被每日重抓且永遠補不上，
      正是原註解想避免卻防錯方向的失敗。判準須改為只看近期實績，並以大巨蛋自 2026-06-02
      起的 15 場連續零覆蓋為驗收案例：**這些場次不得再被反覆重抓**。窗口參數由執行者以實測
      選定並在交付證據記錄理由，**不得沿用「本季曾達」**，亦不得硬編場館名單。
- [ ] 同一判準須同時檢視 `run_check_coverage.py`：其 `COVER_OK`／`equipped` 是同一套經驗式
      邏輯，且 docstring 仍寫著「避免把大巨蛋等無設備場誤報」——該前提同樣已被推翻。本卡
      至少須**修正該註解不使其繼續誤導**；是否連帶調整告警邏輯屬另卡範圍（見〈依賴與邊界〉）。
- [ ] 新增環境變數 `CPBL_PITCH_INGEST`（走既有 pydantic-settings）：`game` 為預設、`pitcher`
      為回退，兩條路徑皆可運作且以離線測試覆蓋。此 flag 僅存活至本卡結案（見 Phase B）。
- [ ] 新增每週一次的全季重跑排程（本機 launchd，沿用既有 `cpbl-scrape-game-pitches` 整季
      模式），使官方任何時點的事後修正最遲七天內收斂。排程失敗不得中斷既有每日 refresh。
- [ ] 產出**全季唯讀 dry-run 對帳**：母體為 2026 年 kind A 與 kind D 的全部完成場（現況
      A 187 場／52,125 列、D 101 場／28,782 列），沿用
      [`scripts/reconcile_game_tm.py`](../../scripts/reconcile_game_tm.py) 的比對邏輯（含
      `_REAL_F4_COLS` 的 float4 round-trip，避免 Gate 3 踩過的儲存精度假陽性）。此階段
      **不寫入** `cpbl.pitch_tracking`。
- [ ] 請求量實測留證，**同時揭露兩個數字**：純增量路徑降幅（預期 ~88%）與含每週全季重跑
      攤提後的降幅（288 請求／週攤成日均 41，預期 ~51%），並附 live worker 對同一端點的
      請求量當背景。純增量降幅 < 50% 時須說明原因。

### Phase B（iteration 2）：對齊存量並收攤

- [ ] Phase A 的三條紅線門檻全數通過後，執行全季寫入重跑並同步 production。
- [ ] 移除 `CPBL_PITCH_INGEST` flag 與 `run_refresh_recent.py` 內的 logs 分支；
      `scrape_pitches`／`pitchers_by_kind` 本身保留（`cpbl-scrape-pitches` CLI 與季後／二軍
      整季回填仍在使用），但 refresh 鏈不再有第二種維度。
- [ ] 重跑後重跑一次 dry-run，確認差異收斂符合預期並留證。

## 紅線（違反即退回）

1. **物理欄位零容忍**：全季 dry-run 的 `cell_mismatch` 中，`rel_speed`／`spin_rate`／
   `plate_loc_*`／`traj_*`／`hit_*` 等物理與軌跡欄位必為 **0 筆**。此 0 有實證基礎——Gate 3
   的 12 次 run 在修正 float4 儲存精度假陽性後，物理欄位不一致數始終為 0。〔清單 #4 #8〕
2. **文字欄位逐筆歸因**：`content` 等敘述欄位允許非 0，但**每一筆**都須列出 `(year, kind_code,
   game_sno, pitcher_acnt, pitch_cnt)`、雙方值，並可重打官方端點複驗其為官方賽後修正。
   **禁止「大致上都是官方修正」這類整批宣稱**；歸因清單須由腳本自動產生，不得人工聲明。〔清單 #7〕
3. **`only_prod_pk` 不得刪除**：正式表有、單場 API 沒有的列，清單必須為空或**逐筆歸因**
   （官方刪球／`pitch_cnt` 重編／我方舊 bug）。**本卡不授權任何 DELETE**，增量路徑與全季
   重跑一律純 UPSERT。若母體非 0，處置回需求方裁定並另開卡，Gate 4 不得代為決定。
   此清單同時是 `pa_build` fail-closed 風險的預警（逐球映射靠 `(pitcher_acnt, pitch_cnt)`
   對齊），須一併交接。〔清單 #4〕
4. **門檻先固定**：上述 1–3 於執行 dry-run **之前**即為本卡面定案，事後不得放寬，
   **不得以「接近門檻」放行**。任何修訂須先取得需求方裁示並在 event log 留痕理由——
   Gate 3 的 14 天門檻因寫卡時未記載選定理由而被事後調整，本卡不重蹈。〔清單 #4〕
5. **回滾觸發即回滾**：Phase A 部署後，若當日完成場的逐球覆蓋率低於切換前同期基準，或出現
   任一筆物理欄位 `cell_mismatch`，即設 `CPBL_PITCH_INGEST=pitcher` 回退並凍結 Phase B。
   Phase A → Phase B 的放行條件為**事件式**：已涵蓋至少一個有完賽場的 refresh 週期且期間無
   回滾觸發成立；**不得以天數替代**。
6. **生產寫入前備份可還原**：Phase B 寫入 production 前須完成三層——既有
   `backup-prod-db.sh` 整庫備份（含 `gunzip -t` 與內容門檻）、`cpbl.pitch_tracking` 單表
   `pg_dump` 並**實測還原到臨時 schema 比對列數與 checksum**、以及需求方親手執行寫入。
   「備份檔案已產生」不等於通過本條（見 `OPS-BACKUP-EMPTY1`）。〔清單 #8〕

## 驗證

- [ ] 離線 fixture 測試：`CPBL_PITCH_INGEST` 兩條路徑、`_lagging_pitch_games()` 的設備過濾與
      聯集去重、孤兒列（`only_prod_pk`）偵測、單場 API 回空時不清空既有列。
- [ ] 全季 dry-run 的差異清單、`only_prod_pk` 母體、請求量計數**由腳本自動產生為 artifact**
      並附於交付；報告中的每個數字都要能指回該 artifact，不得人工轉述。
- [ ] 查核者須能獨立重跑 dry-run 與 `uv run cpbl-shadow-game-tm --report`，自行核對
      `cpbl.game_tm_shadow_diffs` 與執行者宣稱是否一致。
- [ ] Phase B 完成後對帳本機與 production 的 `pitch_tracking` 列數、PK 集合與 checksum，
      並保留回滾程序與其實測結果。
- [ ] `uv run ruff check`、`uv run pytest`、`git diff --check` 全綠；部署 handoff 須以
      `git merge-base --is-ancestor` 逐張列出本次 submodule bump 順帶帶上生產的卡——
      Ledger 的「待部署」可能落後真實（碼已在生產），判斷一律對主站**現行** submodule
      指標，不以卡面狀態推定。

## 依賴與邊界

- **硬前置**：Gate 3 觀測窗已收窗（2026-08-03，`run_id=14`）且凍結解除——已滿足。
- **資源互斥**（claim 時宣告）：`file:src/cpbl/ingest/run_refresh_recent.py`、
  `file:src/cpbl/ingest/cpbl_pitch_tracking.py`、`db:cpbl`、本機 refresh 排程。與
  `INGEST-PA-DAILY1`、`INGEST-POSTGAME-FINALIZE1` 同屬 refresh 鏈，claim 前須先對帳，
  不得三卡同時改動同一條鏈。
- **不碰 shadow harness**：migration 065 的四張 `game_tm_shadow_*` 表、`game_tm_shadow.py`
  與 `cpbl-shadow-game-tm` 一律保留原狀。它們是查核者複驗的證據來源；切換後 shadow 與正式
  表同源、比較恆為 0 差異而自然失效，拆除另開 T2 清理卡（觸發時機：本卡結案且 Phase B
  生產對帳通過）。
- **不碰 live 管線**：`live_game_worker.py`／Redis snapshot／`_trackman_snapshot()` 均不在
  範圍。**注意 parser 已分岔**——live worker 有自己的一套 TrackMan 欄位處理，本卡的「共用
  pure parser」契約只覆蓋兩條 ingest path，收斂它屬 `INGEST-LIVE-RECONCILE1` 的 promotion
  gate 職責，不得在本卡偷渡。
- **不修覆蓋率告警的去向**：`cpbl-check-coverage` 對大巨蛋等場館已持續告警兩個半月而無人
  處置，缺陷在**告警沒有強制去向**而非偵測失靈（與 `DEV-CI-RED-OWNERSHIP1` 的「main 紅燈
  無歸屬」是同一種病的兩個表面）。本卡只修那句已被推翻的誤導性註解，告警機制本身另開卡。
- **不追大巨蛋的缺漏資料**：源頭即無 `Trackman`，重爬任何次數都不會出現；正確的產品回應是
  把缺席講清楚（沿用 `SkipTrackman` 三態語意），不是持續重試。venue-correlated missingness
  的量化與前端揭露屬另卡。
- **下游影響（唯讀確認即可）**：`pitch_type_pred`／`pitch_type_pred_v2` 不在 `_upsert` 的
  `_COLS` 內，重跑**不會**洗掉球種分類；`pa_build` 逐球來源唯讀，但其 fail-closed
  reconciliation 對 PK 變動敏感，故紅線 3 的清單須一併交接。

## Log

- 2026-08-03 由 `ruan6047` 於 grilling 質詢會話定案十三項範圍決策後撰擬草稿；尚未註冊、未
  claim。register event 待需求方親手 append 至 `docs/control-plane/events.jsonl`。
- 待需求方另行裁定（不屬本卡）：大巨蛋 TrackMan 覆蓋缺口是否另開追蹤卡；
  `INGEST-LIVE-RECONCILE1` 的失效日期由誰修正。
