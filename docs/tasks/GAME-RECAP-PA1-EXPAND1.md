# GAME-RECAP-PA1-EXPAND1 canonical PA additive schema expand〔T4；🔴資料正確性／schema〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-PA1-EXPAND1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：[`GAME-RECAP-PA1_CONTRACT.md`](../design/GAME-RECAP-PA1_CONTRACT.md) §「資料模型」
- DB：`db_scope: schema`；`migration_phase: expand`。認領時須取得本機與 production `cpbl` schema lane lock，禁止與其他 migration writer 並行。
- 部署：是　環境：production　PR：—　Merge SHA：—
- Discovery：`GAME-RECAP-DATA1` Checkpoint 1 已核可
- Design：Design Gate N/A；純持久化基礎設施，無 public UI
- current-state：📥Backlog；**TAXONOMY1 已跨家族查核通過並 merge（2026-07-24，REVIEW-003/MERGE-004）**，transition schema 前置解除；仍待認領與 schema lane（`db_scope=schema`）可用。

## 目標與驗收

- [ ] 以新、冪等 migration additive 建立 contract 指定的 source revision、build、PA、PA-event、PA-pitch mapping 物件與索引；不得改寫既有 migration。
- [ ] 使用參數化 SQL、`cpbl.db.conn()` 與明確 constraint／索引策略；不儲存 credentials，並保留來源 revision／parser version。
- [ ] migration rehearsal、rollback／restore 路徑與 query plan 證據完整；production 前取得備份、schema lane 與需求方 sign-off。
- [ ] `uv run ruff check`、`uv run pytest` 通過；跨模型家族或人工 reviewer 審核 schema、安全性與可重跑性。

## 依賴與交付

- 依賴：`GAME-RECAP-PA1-TAXONOMY1` 通過；同一 `<environment, cpbl>` 無其他 migration writer。
- 後續：schema 已驗證部署後，才可認領 BUILD1。
- 非目標：不建立 builder、不回填資料、不新增 public API 或前端。
