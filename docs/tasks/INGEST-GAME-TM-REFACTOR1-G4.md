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
`cpbl-check-coverage` **一直有在報，但報成資訊級噪音**——缺陷不在偵測，在**告警無去向且
被自我標註為預期**，屬另卡範圍。**其三**，此缺漏與球場綁定而非隨機，以該場館為主場的球隊其
逐球衍生指標會系統性少一成樣本，屬**與球場相關的缺失** [venue-correlated missingness]，
跨隊比較會有偏差——本卡不處理，但不得在 dry-run 對帳中把這類雙邊 0 列誤記為差異。

同批實測另發現：台東 2 場全零且**不在**既有無設備清單（花蓮／嘉義）內；新莊（全季 89.9%）
有 sno=101／104 兩場異常全零；亞太主全季僅 75.9%，明顯低於其餘 90–99% 的場館。

**告警現況（資料截點 2026-08-03，重現指令如下）**：

```bash
uv run cpbl-check-coverage 2>&1 | grep -vE '^    '            # 各分類的場數
uv run cpbl-check-coverage 2>&1 | awk '/逐球完全零/,0' | grep 'sno=' \
  | sed -E 's/.*[0-9]{2} ([^：]+)：.*/\1/' | sort | uniq -c | sort -rn   # 依球場拆分
```

當日輸出：「逐球完全零」**36 場**（大巨蛋 24／亞太主 8／新莊 3／樂天桃園 1）、「逐球部分
缺漏」1 場。**該 36 場清單的層級是 `ℹ️`**，括號註記為「多為亞太主早季未裝機、大巨蛋設備
不穩」——工具把這批視為預期噪音而非待辦，這正是「告警無去向」的具體形態。註記中「大巨蛋
設備不穩」的判斷也已被上述時序推翻（不是不穩，是自 06-02 起持續無資料）。

> **數字紀律**：本節所有計數均須以上列指令重新產生，**不得以終端輸出的行數代替計數**。
> 初稿曾把 `tail -25` 的行數誤記為「25 場」，經跨家族查核（GPT-5／Codex，2026-08-03）
> 以實跑推翻並列為 blocking finding。查核者複驗時請重跑指令，勿沿用本節數字。

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
      正是原註解想避免卻防錯方向的失敗。

      **判準於卡面釘死，不由執行者事後選定**（紅線 4 適用）：`equipped` ＝ 該球場**最近 10 場
      完成場**中**至少一場**達 `pitches >= 50 AND tracked >= pitches * 0.80`；該球場完成場
      不足 10 場時以現有場次計。窗口 10 與門檻 0.80 為本卡面定值，修訂須經需求方核可並留痕。

      此值已於 2026-08-03 以全季資料驗證同時滿足兩項不變量（重現查詢見下），**執行者須重跑
      並附輸出**：
      - **死設備要掉出**：大巨蛋最近 10 場 0 場達標 → `equipped=false`，其自 06-02 起的
        15 場連續零覆蓋不再被反覆重抓；台東／嘉義市／花蓮同樣維持在外。
      - **單場 downtime 不得失去自癒**：新莊 9/10、洲際 9/10 仍為 `true`；亞太主 10/10 為
        `true`（其 8 場零覆蓋屬早季未裝機，不應因此喪失自癒）；斗六僅 2 場完成場、2/2 為 `true`。

      ```sql
      WITH cov AS (
        SELECT gm.venue, gm.game_sno, gm.game_date,
          (SELECT count(*) FROM cpbl.game_livelog ll WHERE ll.year=gm.year
             AND ll.kind_code=gm.kind_code AND ll.game_sno=gm.game_sno
             AND (ll.is_ball OR ll.is_strike)) AS pitches,
          (SELECT count(*) FROM cpbl.pitch_tracking pt WHERE pt.year=gm.year
             AND pt.kind_code=gm.kind_code AND pt.game_sno=gm.game_sno) AS tracked
        FROM cpbl.games gm
        WHERE gm.year=%s AND gm.kind_code=%s AND gm.home_score+gm.away_score>0),
      r AS (SELECT *, row_number() OVER (PARTITION BY venue
              ORDER BY game_date DESC, game_sno DESC) rn FROM cov)
      SELECT venue, bool_or(pitches>=50 AND tracked>=pitches*0.80) AS equipped
      FROM r WHERE rn<=10 GROUP BY venue;
      ```

      **不得硬編場館名單**；判準必須是資料推導的。
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

### Phase A → Phase B 的放行條件（機械判定，缺一不可）

以下四項全部成立才可進 Phase B。**天數不是判準，但「一個 refresh 週期」也不是**——單一
比賽、單次刷新不足以證明無人值守排程的穩定性：

- [ ] **kind A**：切換後累計至少 **10 個完成場**、且至少 **5 次**實際執行的 refresh run。
- [ ] **kind D**：切換後累計至少 **5 個完成場**、且至少 **3 次**實際執行的 refresh run。
      D 沒有 shadow 時間序列證據，全季 dry-run 只是橫斷面，**不得以之替代**本項。
- [ ] 至少觀測到 **1 次**「TrackMan 發布延遲後由後續 refresh 自癒」的完整案例（某場首次
      抓取覆蓋不足、後續 run 補齊），證明新路徑的自癒在真實延遲下有效。若觀測窗內未自然
      發生，**不得以 fixture 代替**，須延長觀測直到發生。
- [ ] 期間無任何回滾觸發條件成立（定義見紅線 5）。

以上計數須由腳本自 `cpbl.refresh_log` 與 `cpbl.games` 產生為 artifact，不得人工聲明。

### Phase B（iteration 2）：對齊存量並收攤

- [ ] 上述放行條件與六條紅線全數通過後，執行全季寫入重跑並同步 production。
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
   **禁止「大致上都是官方修正」這類整批宣稱**；歸因清單須由腳本自動產生，不得人工聲明。
   **artifact 每列必含**：`endpoint_url`、`fetched_at`（ISO 8601 含時區）、`payload_sha256`
   （該次官方回應全文的 hash）、`prod_value`、`api_value`。**只重打即時端點不足以證明當時的
   官方修正**——官方可能在複驗前又改一次，沒有 hash 與抓取時間就無法分辨「當時就不同」與
   「複驗時才不同」。artifact 連同原始 payload 存於 `ARTIFACT_DIR` 下版本化路徑，查核者須
   能以 hash 驗證其未被事後修改。〔清單 #7 #8〕
3. **`only_prod_pk` 為 0 才可進 Phase B**：正式表有、單場 API 沒有的列，**本卡不授權任何
   DELETE**，增量路徑與全季重跑一律純 UPSERT。狀態機明定如下，不得停在中間態：
   - 母體 **＝ 0** → 放行 Phase B。
   - 母體 **≠ 0** → **阻擋 Phase B 且阻擋本卡結案**。逐筆歸因（官方刪球／`pitch_cnt` 重編／
     我方舊 bug）後交需求方裁定，並**另開卡**執行處置；本卡以 `⏸阻塞` 記錄等待對象與解除
     條件，Phase A 的成果保留在生產（增量路徑已切換、可回退），**不得**以「Phase A 已通過」
     為由宣稱本卡完成。Gate 4 不得代為決定刪除與否。
   此清單同時是 `pa_build` fail-closed 風險的預警（逐球映射靠 `(pitcher_acnt, pitch_cnt)`
   對齊），須一併交接。〔清單 #4〕
4. **門檻先固定**：紅線 1–3、5 的門檻與〈Phase A → Phase B 放行條件〉的各項計數，於執行
   dry-run **之前**即為本卡面定案，事後不得放寬，**不得以「接近門檻」放行**。
   **`equipped` 的窗口 10 與門檻 0.80 同受本條拘束**——它們已在驗收條件釘死並附驗證查詢，
   **不是交由執行者實測後選定的參數**（初稿曾如此寫，經跨家族查核指為實質事後定義門檻而
   修正）。任何修訂須先取得需求方裁示並在 event log 留痕理由——Gate 3 的 14 天門檻因寫卡時
   未記載選定理由而被事後調整，本卡不重蹈。〔清單 #4〕
5. **回滾觸發即回滾**：Phase A 部署後，下列任一成立即設 `CPBL_PITCH_INGEST=pitcher` 回退並
   凍結 Phase B。判準全部機械可判，**母體只計 `equipped=true` 的球場**（見驗收條件的判準與
   查詢），無設備場的 0 覆蓋不是回歸：
   - **覆蓋率退步**：切換後任一日，當日新完成且 `equipped=true` 的場，其
     `tracked / pitches` 低於**切換前基準 − 10 個百分點**。**基準定義**：切換日之前、同 kind、
     `equipped=true` 且 `pitches >= 50` 的最近 **20 場**之 `tracked / pitches` **中位數**，
     於切換當日算定並寫入交付 artifact（含場次清單），此後不再重算。
   - **物理欄位不一致**：出現任一筆物理欄位 `cell_mismatch`（欄位集同紅線 1）。
   - 當日無 `equipped=true` 的新完成場時，本條**不判定**（不算通過也不算失敗），該日不計入
     放行條件的 refresh run 計數。〔清單 #4 #8〕
6. **生產寫入前備份可還原**：Phase B 寫入 production 前須完成三層，**每層都要留可重跑的指令
   與輸出**：
   - 既有 `backup-prod-db.sh` 整庫備份，含 `gunzip -t` 與內容門檻。
   - `cpbl.pitch_tracking` 單表 `pg_dump -Fc -t cpbl.pitch_tracking`，**還原到同一 DB 的臨時
     schema** `restore_check_<YYYYMMDD>`（`pg_restore --schema-only` 後 `--data-only`，或
     `pg_restore -f -` 改寫 search_path），比對兩項：列數相等，且下列 checksum 相等——
     ```sql
     SELECT md5(string_agg(t::text, '|' ORDER BY year, kind_code, game_sno, pitcher_acnt, pitch_cnt))
     FROM <schema>.pitch_tracking t;
     ```
     比對範圍為全表。驗畢即 `DROP SCHEMA restore_check_<YYYYMMDD> CASCADE`。
   - 需求方親手執行寫入。
   「備份檔案已產生」不等於通過本條（見 `OPS-BACKUP-EMPTY1`：只有還原演練才看得到
   `convalidated=t` 卻不成立的 FK）。〔清單 #8〕

## 驗證

- [ ] 離線 fixture 測試：`CPBL_PITCH_INGEST` 兩條路徑、`_lagging_pitch_games()` 的設備過濾與
      聯集去重、孤兒列（`only_prod_pk`）偵測、單場 API 回空時不清空既有列。
- [ ] 全季 dry-run 的差異清單、`only_prod_pk` 母體、請求量計數、放行條件的完成場與 refresh
      run 計數、回滾基準的場次清單與中位數——**全部由腳本自動產生為 artifact**並附於交付；
      報告中的每個數字都要能指回該 artifact，**不得人工轉述、不得以終端輸出行數代替計數**
      （初稿即因把 `tail -25` 的行數誤記為場數而被查核推翻）。
- [ ] 文字欄位歸因 artifact 須含 `endpoint_url`／`fetched_at`／`payload_sha256`（紅線 2），
      且原始 payload 一併保存，查核者能以 hash 驗證未被事後修改。
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
- 2026-08-03 **卡面查核 REQUEST_CHANGES**（GPT-5／Codex，跨家族，非撰擬者），六項 finding
  全數接受並修訂，無一爭議：
  1. 〔Critical〕「`cpbl-check-coverage` 列出 25 場」**無法重現**——實測為「逐球完全零
     **36 場**」（大巨蛋 24／亞太主 8／新莊 3／樂天桃園 1）＋部分缺漏 1 場。撰擬者把
     `tail -25` 的**行數**誤記為場數。已改為附重現指令與依球場拆分，並補記該清單為 `ℹ️`
     資訊級、其註記「大巨蛋設備不穩」亦已被時序推翻。
  2. 〔Critical〕紅線 4 與「窗口由執行者實測選定」自相矛盾。已於卡面**釘死 `equipped` ＝
     最近 10 場至少一場達 0.80**，附全季驗證查詢與兩項不變量（大巨蛋掉出、新莊／洲際
     9/10 與亞太主 10/10 保住自癒），並明列該參數受紅線 4 拘束。
  3. 〔Critical〕回滾條件的「切換前同期基準」無法機械判定。已定義為切換日前同 kind、
     `equipped=true`、`pitches>=50` 的最近 20 場覆蓋率**中位數**，切換當日算定寫入
     artifact 後不再重算；退步門檻 −10 個百分點；無 `equipped` 新完成場之日不判定。
  4. 〔Critical〕`only_prod_pk` 非零時狀態不閉合。已改為**母體 ≠ 0 即阻擋 Phase B 與本卡
     結案**，轉 `⏸阻塞` 並另開卡處置，明禁以「Phase A 已通過」宣稱完成。
  5. 〔Critical〕「一個 refresh 週期」不比按天嚴格（可只涵蓋一場一次刷新）。已改為
     A 至少 10 完成場／5 次 run、D 至少 5 完成場／3 次 run，另加一次真實發布延遲自癒
     觀測且**不得以 fixture 代替**；明載 D 的橫斷面 dry-run 不可替代時間序列證據。
  6. 〔Major〕備份紅線與文字歸因 artifact 欠可執行細節。已釘入臨時 schema 命名、
     `pg_dump -Fc`／`pg_restore` 流程、PK 排序後的 md5 checksum SQL，以及 artifact 必含
     `endpoint_url`／`fetched_at`／`payload_sha256` 與原始 payload 保存。

  查核同時確認已成立、無 finding：大巨蛋覆蓋率時序與官方 API 三場 0 筆 Trackman 皆可重算；
  A/D 場列數、`2026-D-107` 382 列、台東／新莊／亞太主數字一致；Gate 3 物理欄位零 mismatch
  與 float4 處理有文件支撐；章節名、`review_independence`、`spec 基線 v1`、T4 紅線章節合規；
  116 tests passed、`workflow_ledger --check` 通過；父卡補帳無無事件推斷。
- 2026-08-03 流程留痕（查核者記錄，需求方裁量）：本卡三個文件 commit 由撰擬者直接推 main、
  未先行獨立查核，屬**事後查核補救**；`DEV-CI-RED-OWNERSHIP1` 的「範圍未擴張」精確語意應為
  「未新增實作驗收項」，其新增的 Discovery 義務仍屬義務擴張，不得泛稱完全未擴張。
- 待需求方另行裁定（不屬本卡）：大巨蛋 TrackMan 覆蓋缺口是否另開追蹤卡；
  `INGEST-LIVE-RECONCILE1` 的失效日期由誰修正。
