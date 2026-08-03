# INGEST-LIVE-RECONCILE1 將官方 LIVE 暫態逐球納入每日可追溯校正〔T4；🔴資料正確性紅線〕

- review_independence: [human, cross_family]
- 需求：ruan6047（2026-08-03 會話裁定）　規劃：GPT-5@Codex　分支：依認領時 worktree 慣例
- 執行：待指派（建議 L4；逐球資料契約、來源修訂與 production 同步）　查核：待指派（先需求方人工審，再跨家族查核；均須 ≠ 執行）
- Initiative：—　spec 基線：—
- DB：`db_scope: schema`（新增或擴充 provisional source revision 的 append-only 儲存；`migration_phase: expand`）
- 部署：是　環境：本機 ingest＋production 同步　PR：—　Merge SHA：—
- **最早可實作時間**：Gate 3 觀測窗**已於 2026-08-03（第 9 天、`run_id=14`）依需求方裁示收窗**，原寫的「不早於 2026-08-08」以跑滿 14 天為前提，該前提已不成立，故**日期下限解除**。實際 claim 仍硬依賴 `INGEST-GAME-TM-REFACTOR1-G4` 的 Gate 4 需求方 production sign-off 與本卡 Design Gate；任一前置未滿足時維持 Backlog。
- 範圍：將官方 LIVE 視為 provisional 基底，讓每日正式爬取可依來源版本校正，而非讓 Redis 快照直接覆寫賽後權威資料。
- Discovery：`docs/research/GAME_TM_SHADOW_OBSERVATION.md` §4–5（現行正式 writer 與單場 API 的 14 天 shadow 證據）；需補本卡來源版本／衝突矩陣。
- Design：待需求方核可（provisional 欄位範圍、promotion／correction 優先序、使用者可見的 provisional 標示、保留期與回滾）。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 背景

賽中官方 LIVE 逐球常比隔日逐投手 logs writer 更早可用；2026-08-02 的 235／236 在
production 已有原始 TrackMan，但缺 canonical PA build 時前端必須 fail-closed。另有官方
事後修正案例（2026-A-215 的 `content` 文字），現行近三日覆蓋修補窗口以外不會自動回寫。

需求方裁定：每日更新應採納官方 LIVE 資料作為基底，並在後續官方資料到齊或修正時更新它。
此裁定不等於 Redis 是永久真相：必須保存可追溯的來源版本，才能分辨 provisional、已確認與
官方修正，並保留重新 materialize 的能力。

## 驗收條件

- [ ] LIVE snapshot 的逐球僅以官方原始欄位與抓取時間寫入獨立、append-only 的 provisional revision；不得把 Redis JSON 或推導欄位直接覆寫 `cpbl.pitch_tracking`。
- [ ] 每日正式爬取依來源 hash／revision 對同一場逐球做冪等 reconcile：新增、修正與撤回均有來源證據；衝突不可默默丟棄，且最新版官方來源可回寫較早 provisional 值。
- [ ] promotion 至 `cpbl.pitch_tracking` 前，逐球鍵、row count、球數序與必要 TrackMan 直接值均通過預先核可的完整性 gate；未通過者停留 provisional 並在 API 回傳 pending／unknown，不得猜測或混合來源。
- [ ] canonical PA build 與其所有相依表納入同一受控同步族；有原始 TrackMan 但沒有 published mapping 時可觀測、可補建，逐球 UI 繼續 fail-closed。
- [ ] 本機與 production 的 source revisions、promotion 狀態、逐球列數與 checksum 可對帳；production 寫入前必有完整備份，且提供僅回退本卡新資料的程序。
- [ ] 在 `INGEST-GAME-TM-REFACTOR1-G4` 完成 cutover 並取得 production sign-off 前，不修改 `run_refresh_recent.py` 的正式 `pitch_tracking` writer，也不把 provisional 資料併入其對帳母體。（Gate 3 收窗前的觀測隔離義務已於 2026-08-03 履行完畢。）

## 紅線（違反即退回）

1. Gate 3 觀測窗已於 2026-08-03 收窗、凍結解除，本條的觀測隔離義務**已履行完畢**。改寫正式 `pitch_tracking` writer 的權責自此歸 `INGEST-GAME-TM-REFACTOR1-G4`：本卡在該卡完成 cutover 並取得 production sign-off 前，仍不得改動逐球正式 writer，亦不得把 provisional 資料併入其對帳母體。〔writer 單一權責〕
2. 每筆 promotion 必須有 `official source payload hash`、抓取時間與來源類型；缺任一項不得寫入 canonical 表。不得以 Redis key、記憶體內容或 UI 顯示當作來源證據。〔可追溯性〕
3. 對同一 `(year, kind_code, game_sno, pitcher_acnt, pitch_cnt)`，revision 不同時不得無條件 last-write-wins；必須依核可的官方來源優先序與完整性 gate 決定，並留下衝突／決策紀錄。〔資料正確性〕
4. production promotion 前，目標場 TrackMan row count 與已核可來源的差異必為 0，或每個差異都有 `mapping_failed`／官方缺值的逐列證據；「接近完整」不得放行。〔完整性〕
5. 查核者必須在獨立 environment 重跑至少一場「LIVE 先到、正式來源後修正」與一場官方 TrackMan=0 的 fixture／實測案例，並核對 production 對帳；任一不符即退回。〔可重現性〕

## 驗證

- [ ] migration expand／rollback rehearsal、來源 revision append-only 與 idempotent reconcile 的離線測試全綠。
- [ ] Gate 3 最終報告、Gate 4 cross-family review 與需求方 production sign-off 均已留痕，才可進本卡 claim。
- [ ] 以真實場次驗證 provisional → confirmed／corrected 的完整路徑、PA mapping 同步與 production API；保留 checksum、row count、來源時間與回滾演練證據。
- [ ] `uv run ruff check`、`uv run pytest`、相關 DB migration／refresh 檢查、production smoke 與 `git diff --check` 全綠。

## 依賴與邊界

- 硬依賴：Gate 3 收窗（**已於 2026-08-03 達成**）、`INGEST-GAME-TM-REFACTOR1-G4` 的核可與需求方 production sign-off（**未達成**）。日期下限已解除，但那從來只是排程下限、非自動開工授權——真正的閘門是 Gate 4 的 sign-off 與本卡 Design Gate。
- 受影響但不在本卡偷渡實作：`INGEST-PA-DAILY1`（每日 PA build／同步）與 `INGEST-POSTGAME-FINALIZE1`（完賽補齊節點）；claim 時須先對帳資源並決定垂直切片。
- 不調整賽中 UI，不把 provisional 資料標成賽後最終判決，也不在本卡重新設計逐球顯示文案。

## Log

- 2026-08-03 依 ruan6047 指示註冊；將 LIVE 採納方向與 Gate 3 觀測隔離明文化，尚未 claim。
