# GAME-RECAP-STATUS-EXPAND1 賽事來源 revision 與狀態 instrumentation〔T4；🔴資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-STATUS-EXPAND1`
- 執行：待指派　查核：待指派（須跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`db_scope: schema`；獨立 local test DB；resources=`db:local:cpbl`、`db:test:cpbl`；`migration_phase: expand`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §7 與 `GAME-RECAP-STATUS1` 證據稽核分支 `ai/gpt-5-codex/GAME-RECAP-STATUS1`（source SHA `11a90dc`）
- Discovery：`GAME-RECAP-DATA1` 已核可；`GAME-RECAP-STATUS1` 證實既有資料不足以提供單場、單來源狀態與 freshness。
- Design：Design Gate N/A；本卡只提供 additive schema 與 ingest instrumentation，不定義 UI 文案。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 目標

保存官方排程原始狀態與每場、每來源的取得 revision，使 STATUS1 後續可依可追溯證據判定
`official_game_status`、raw `play_by_play_availability` 與 `advanced_freshness`，不再以比分、日期、
空陣列或整批 `refresh_log` 推測。

## 驗收條件

- [ ] 新增 additive、冪等 migration；不得修改既有 migration 或覆寫 `games`／scoreboard／livelog。
- [ ] 保存 schedule raw revision：game key、raw `PresentStatus`、raw `GameResult`、原始日期、取得時間、payload hash／source version。
- [ ] 保存每場、每來源 revision：source=`schedule|scoreboard|livelog|advanced`、outcome=`available|missing|error`、row count、取得時間、error code／sanitized detail。
- [ ] 同一 payload 重跑不產生重複 revision；內容改變會產生可追溯的新 revision。
- [ ] ingest 成功、來源缺漏與來源錯誤分開寫入；錯誤不得被空陣列吞掉，detail 不得含 secret 或完整 HTML。
- [ ] 歷史未知狀態不得補寫為 `final`；backfill／data migration 若需要，另開 migrate 卡。
- [ ] 0–0、延賽、取消、有 scoreboard 無 livelog、整批 refresh 成功但單場缺漏、進階資料晚到均有紅燈轉綠測試。
- [ ] migration 可在 fresh DB 重跑；schema、索引、筆數、duplicate prevention 與失敗重試均有對帳證據。

## 邊界與停止條件

- 本卡不新增 public API、不定義 STATUS1 的最終 mapping、不實作 PA／tracking mapping 或 WP availability。
- 若官方 `PresentStatus`／`GameResult` 真實值域仍無法由 raw payload 證明，僅保存 raw revision，mapping 保持 `unknown`。
- 若 advanced 官方來源無 game-level completion 訊號，只記錄實際取得證據；不得由 player aggregate `updated_at` 代理單場到齊。
- production migration 僅能由 main 的受保護部署鏈執行，且須先備份、取得 migration lane、完成 smoke test。

## 依賴與交付

- 阻塞依賴：`GAME-RECAP-STATUS1` source SHA `11a90dc` 必須先通過跨模型家族／人工查核並由需求方核可。
- 後續：解除 `GAME-RECAP-STATUS1` API mapping／contract test 實作阻塞；若需歷史 revision backfill，另拆 data-migration 卡。
- 預估範圍：M。

## Log

- 2026-07-20 需求方 ruan6047 授權註冊；因 STATUS1 T4 稽核尚待獨立查核，本卡保持 Backlog，不得 claim migration lane。
