# INGEST-PA-DAILY1 canonical PA build 接進每日 refresh 鏈〔T3〕

- 需求：ruan6047（2026-07-26 會話裁定）　規劃：本卡 spec（源自 GAME-RECAP-WP-CAL1 執行期發現）　分支：依認領時 worktree 慣例
- 執行：Claude Sonnet 5@Claude Code（分支 `ai/claude-sonnet-5/INGEST-PA-DAILY1`，基底 cb6a638）　查核：待指派（≠ 執行）
- Initiative：—（獨立 ingest 卡；服務 INIT-GAME-RECAP 的 canonical PA 資產新鮮度）
- DB：`db_scope: write`（本機 `cpbl` derived 表：`game_plate_appearances`／`game_recap_builds` 等 build 家族；`migration_phase: none`）
- 部署：否（`cpbl-refresh-recent` 只在本機跑；生產僅經既有每日同步接收資料）　環境：—　PR：—　Merge SHA：—
- current-state：🔍待查核；已交付（分支已 push、未 merge，見 2026-08-05 Log），待查核者複核。
- **排程（2026-07-27 需求方裁定）**：升為 UX-GAME-RECAP1 的**硬前置**（recap 脊柱＝ΔRE24 需每日 PA；7/26 三場完成場 0 筆 published PA 為活證據），但**須等 TM Gate3 觀測窗（~8/7）收窗後才派**——本卡改的正是 scrape-daily 鏈，窗內動它會污染 shadow 比較基線。

## 背景（為什麼）

`cpbl-build-pa`（GAME-RECAP-PA1-BUILD1）只在建置期手動跑過，**不在每日 refresh 鏈**：
launchd 每日爬取正常（games/gamelog 天天新），但 PA build 靜止在最後一次手動執行，
缺口隨時間必然擴大。實證：2026-07-26 發現 2026 A 完成 216 場、published build 僅 210 場
（缺 07-24/25 六場），直接使 GAME-RECAP-WP-CAL1 的 coverage 門檻 fail（0.9722 < 0.98），
污染統計判定（該次已由需求方手動補跑復原至 216/216）。WP-API1 未解鎖前消費者是研究
harness，但 coverage gate 必須恆真才不會再混入統計卡判定。

## 目標

`cpbl-refresh-recent` 在 gamelog 寫入後，對當日增量場次執行 canonical PA build
（`pa_build.build_scope` 單場模式，`--game year:kind:sno` 語意），使「完成場皆有
published build」在每日流程後恆成立。

## 驗收條件

- [ ] 一軍路徑：gamelog 寫入成功的當日 snos 逐場 build（kind A；季後 C/E 開打時同一機制自動涵蓋——依 refresh 既有 kind 判定，不得寫死 A）。二軍 D：builder 已支援，是否納入由執行者依當前 D gamelog 覆蓋現況定案並留痕（納入或明確排除皆可，不得沉默跳過）。
- [ ] **fail-closed 不擋主流程**：build 失敗（含 reconciliation_required）記入 `refresh_log` detail 與 stdout log，refresh 其餘步驟照常完成；不得因 build 失敗導致爬取/同步中斷。
- [ ] 冪等：同日重跑 refresh 為 no-op（依 builder 既有「同一來源重跑 no-op」契約）；晚到 livelog 修正走既有 reconciliation 語意，不得覆寫已發布 pa_id。
- [ ] **生產同步對齊**：查核 `scripts/refresh-cpbl-prod.sh` 逐表清單，`game_plate_appearances`、`game_recap_builds` 及 build 家族相依表若未含即加入；同步後生產 coverage 與本機一致（實測留痕）。
- [ ] 完成後 coverage 對帳輸出：refresh log 印出「完成場 vs published build 場數」，缺口非零時明確標示。
- [ ] 測試：離線單元（增量 sno 選集/失敗隔離）＋實跑一次當日增量驗證；`uv run ruff check`＋`uv run pytest` 全綠（動 refresh 者依慣例確認 `refresh_status.py check` 語意不受影響）。

## 邊界與並行注意

- 不改 `pa_build` 核心語意（taxonomy/pa_id/reconciliation 契約屬 PA1 家族，本卡只做接線）。
- 與 `LIVE-GAME-BACKEND1`（🔨執行中）並行：本卡資源 `file:src/cpbl/ingest/run_refresh_recent.py`、`file:scripts/refresh-cpbl-prod.sh`、`file:src/cpbl/ingest/run_build_pa.py`（如需薄參數）、`file:tests/test_refresh_pa*`；與該卡 lease 零重疊，claim 時再對帳。
- 每日時段紅線照舊（AI_RUNBOOK §3）；build 為純 DB 重算不爬網，無節流疑慮。

## 依賴與交付

- 依賴：`GAME-RECAP-PA1-BUILD1` ✅（builder 與契約既有）。
- 後續：coverage 恆真後，統計卡（WP 系列季末重跑等）不再混入資料時效性 fail。

## Log

- 2026-07-26 依 ruan6047 指示開卡（GAME-RECAP-WP-CAL1 結案後續）：CAL1 期間實證 build 缺口污染 coverage 門檻；根因為 build_pa 不在每日鏈。Coordinator register 併同 commit。
- 2026-08-03 緊急資料修復（ruan6047 明確授權）：未認領、未改每日 refresh 鏈；僅對已有原始 TrackMan 的 2026-A-229～232、235、236 執行單場冪等 PA build，並在已驗證 production 全庫備份後同步 `game_recap_source_revisions` 與 PA build 家族表。production API 逐球列恢復為 309／327／332／348／294／257；229 的 3 球與 235 的 8 球仍 mapping_failed，維持 fail-closed。不寫 `pitch_tracking`，不影響 `INGEST-GAME-TM-REFACTOR1` Gate 3 的 14 天 shadow 基線；將 live 資料改為每日正式 writer 的方向必須待該觀測窗收束後另行 Design Gate。
- 2026-08-03 單場補齊（ruan6047 明確授權）：239 的原始資料庫尚無終局資料，故以既有官方 ingest 依序更新賽程、單場 game log／box、單場 TrackMan（261）與 PA build，再以已驗證 production 全庫備份為前提同步必要正式與 PA 表。公開 API 對帳：終場 0:2、284 個逐打席事件、8 筆投手 box、261 列 tracking；不改每日 refresh 或 Gate 3 的正式 writer。
- 2026-08-05 執行（Claude Sonnet 5@Claude Code，分支 `ai/claude-sonnet-5/INGEST-PA-DAILY1`）：Gate3 觀測窗已於 2026-08-03 提前收窗（見派工註記與記憶 `game-tm-refactor-gates.md`），依派工指示解除排程阻塞、開工。

  **開工前提實查**（三項，皆附證據）：
  1. Coverage 缺口 SQL（`completion.completed_games_sql()` canonical 判定，2026）：kind A 234 完成／229 published／缺 5（sno 228,233,237,238,240）；kind D 164 完成／155 published／缺 9（sno 108,178-185）；缺口場次逐一查證 `game_livelog` 皆已存在（非缺來源，純粹 build 未接線的累積缺口，與背景描述一致）。當年無 C/E 完成場（regular season 進行中），確認動態 kind 判定現階段安全。
  2. `run_build_pa --game 2026:A:229` 連跑兩次：皆回 `{'actions': {'noop': 1}, 'build_states': {'published': 1}}`，確認單場模式冪等。
  3. `scripts/refresh-cpbl-prod.sh` 逐表清單：5 張 PA build 家族表（`game_recap_source_revisions`／`game_recap_builds`／`game_plate_appearances`／`game_pa_events`／`game_pa_pitch_mappings`）**全數未在同步清單**（2026-08-03 手動同步是一次性 ad hoc、非清單常態）；其中 4 表 PK 為 `GENERATED ALWAYS AS IDENTITY`，通用 `sync_table()` 會因缺 `OVERRIDING SYSTEM VALUE` 而失敗，須比照既有 `sync_advanced_snapshot()` 前例另立函式。

  **實作**（只做接線，不動 `pa_build` 核心語意）：
  - `run_refresh_recent.py` 新增 `_build_pa_daily`/`_pa_build_step`（fail-closed 外層，獨立可測）＋輔助函式 `_active_kinds`／`_pa_build_targets`／`_pa_build_coverage`；於 `main()` 中補齊缺 gamelog 迴圈之後、分項重算之前呼叫，結果併入 `refresh_log.detail.pa_build`。
  - 目標場次＝「當日窗（不論是否已 published，供晚到 livelog 修正 reconciliation）」∪「全域缺口（completed 但無 published build，不限當日窗，涵蓋歷史累積缺口）」；空清單時**不呼叫** `build_scope`（其 `only_games=[]` 會被 `if only_games:` 判 falsy、退化成全範圍查詢，是需嚴防的陷阱，已用單元測試鎖定）。
  - kind 判定：一軍候選 `("A","C","E")` 動態依當年完成場交集（季後未開打自動排除、開打後自動涵蓋，不寫死 A）。
  - **二軍 D 決策：納入**——builder 已支援＋歷史已有 1664 筆 published D build（即既有 `cpbl-build-pa` 預設 kind 清單本就含 D）＋當前 2026 D 覆蓋率佐證與一軍同等可信（同樣缺口全數有 livelog、純屬接線缺席）。**F（二軍總冠軍賽）決策：不納入**——歷史 0 筆 published（連既有預設 kind 清單都未含 F）、驗收文字未提及，留待二軍季後接近時另立決策，不在此卡靜默擴大範圍。
  - `scripts/refresh-cpbl-prod.sh` 新增 `sync_pa_build()`（比照 `sync_advanced_snapshot` 前例）：5 表依 FK 相依序（source_revisions→builds→plate_appearances→events/mappings）同交易灌入；4 張 identity PK 表用 `OVERRIDING SYSTEM VALUE` 鏡像本機 id（prod 對這 5 表為唯一 writer=本同步腳本，無自產 identity 碰撞風險，同 `advanced_ingest_runs` 前例理由）；`game_recap_builds` 用一般 `ON CONFLICT...DO UPDATE SET state`（僅 state 會於 insert 後變）、其餘三張 write-once 表用 `DO NOTHING`。掛在 `WITH_DETAIL` 區塊內緊接其來源表（`pitching_gamelog` 之後），對齊 `scrape-daily.sh` 每日皆帶 `WITH_DETAIL=1` 的現況。

  **驗證**：`tests/test_refresh_pa_daily.py` 12 個離線單元測試（皆 monkeypatch `conn`／被呼叫函式，比照 CI 無真實 DB 的既有慣例）覆蓋：空清單短路防呆、canonical 完成場判定使用（非手寫）、當日窗∪缺口聯集 SQL 形狀、二軍納入旗標對 candidate kinds 的影響、`build_scope` 空清單陷阱防呆、fail-closed 例外隔離。`uv run ruff check`＋`uv run pytest -q` 全綠，唯一 1 個失敗（`test_task_card_sections.py`）經 `git stash` 確認為 base commit 即存在、與本卡資源範圍（`docs/control-plane/**`／`docs/TASKS.md`）無關的既有缺陷，已另開背景任務追蹤、不在本卡修。真實跑（純 DB、無爬蟲，安全於任何時段）：`_pa_build_step(2026, [8/4,8/5], include_farm=True)` 首次跑建出並 published 全部 14 場缺口（5 A + 9 D、0 錯誤、0 reconciliation_required），coverage 立即回 A 234/234、D 164/164（缺口對帳=0）；緊接第二次呼叫回 `games:0`（真正 no-op，未觸及 `build_scope`）。另以 migrations 066+068+069 原始 DDL 在本機建 scratch schema（`cpbl_sync_rehearsal`，含真實 FK）rehearsal `sync_pa_build()` 邏輯兩輪（不連 SSH、不碰 production）：兩輪皆 0 錯誤，5 表 row count 與 published 狀態與來源逐表 1:1 相符（995,142/4,009,873/233,315 列等全歷史規模）；未實際對 production 執行同步（不 merge/不動 main 的紅線內，同步由 PM 排今日 10:10 daily run 後執行）。`refresh_status.py check` 語意確認不受影響（純讀 `logs/last-status.json`，與 `cpbl.refresh_log`/`detail` 無關；本 worktree 因無執行紀錄回 exit 2，符合既有契約）。

  **交付**：分支已 push（`ai/claude-sonnet-5/INGEST-PA-DAILY1`），未 merge、未動 main；commit SHA 見 push 後 log。改動：`src/cpbl/ingest/run_refresh_recent.py`、`scripts/refresh-cpbl-prod.sh`、新增 `tests/test_refresh_pa_daily.py`。
