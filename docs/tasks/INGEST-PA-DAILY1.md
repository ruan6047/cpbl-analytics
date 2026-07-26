# INGEST-PA-DAILY1 canonical PA build 接進每日 refresh 鏈〔T3〕

- 需求：ruan6047（2026-07-26 會話裁定）　規劃：本卡 spec（源自 GAME-RECAP-WP-CAL1 執行期發現）　分支：依認領時 worktree 慣例
- 執行：待指派　查核：待指派（≠ 執行）
- Initiative：—（獨立 ingest 卡；服務 INIT-GAME-RECAP 的 canonical PA 資產新鮮度）
- DB：`db_scope: write`（本機 `cpbl` derived 表：`game_plate_appearances`／`game_recap_builds` 等 build 家族；`migration_phase: none`）
- 部署：否（`cpbl-refresh-recent` 只在本機跑；生產僅經既有每日同步接收資料）　環境：—　PR：—　Merge SHA：—
- current-state：📥Backlog；已註冊，可認領。

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
