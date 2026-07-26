# GAME-RECAP-PA1-EXPAND1 canonical PA additive schema expand〔T4；🔴資料正確性／schema〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-PA1-EXPAND1`
- 執行：Opus 4.8　查核：Antigravity（Gemini 3.6 Flash，跨家族，≠ 執行，APPROVE）
- Initiative：INIT-GAME-RECAP　spec 基線：[`GAME-RECAP-PA1_CONTRACT.md`](../design/GAME-RECAP-PA1_CONTRACT.md) §「資料模型」
- DB：`db_scope: schema`；`migration_phase: expand`。認領時須取得本機與 production `cpbl` schema lane lock，禁止與其他 migration writer 並行。
- 部署：是　環境：production　PR：—　Merge SHA：`921de18`（source `c586b1d`；✅已驗證部署 DEPLOY-006，主站 21f9ea8）
- Discovery：`GAME-RECAP-DATA1` Checkpoint 1 已核可
- Design：Design Gate N/A；純持久化基礎設施，無 public UI
- current-state：✅已驗證部署（2026-07-24，REVIEW-004/MERGE-005/DEPLOY-006）。交付 `migrations/066_game_recap_pa_expand.sql`（因 main 平行落 `065_game_tm_shadow` 改號 065→066，DDL 不變）+ 7 守門測試；跨家族 APPROVE。production 已上線並 smoke 驗證（migrate 66 files/066:True、cpbl 五表建立且皆空、/api/info 200）。migration lane 釋出 → **BUILD1／INGEST-RECORDS-HR1 解除阻塞**。

## 目標與驗收

- [x] 以新、冪等 migration additive 建立 contract 指定的 source revision、build、PA、PA-event、PA-pitch mapping 物件與索引；不得改寫既有 migration。（`066`，5 表 + 索引/約束）
- [x] 使用參數化 SQL、`cpbl.db.conn()` 與明確 constraint／索引策略；不儲存 credentials，並保留來源 revision／parser version。（DDL 靜態枚舉 CHECK；migrate() 走 conn()）
- [x] migration rehearsal、rollback／restore 路徑與 query plan 證據完整（隔離 DB 重現）；production 前備份（cpbl-prod-20260724-133738）、schema lane 與需求方 sign-off 皆完成，已部署驗證（DEPLOY-006）。
- [x] `uv run ruff check`、`uv run pytest` 通過（420 passed/3 skipped）；跨模型家族 reviewer（Antigravity/Gemini）審核 schema、安全性與可重跑性 APPROVE。

## 依賴與交付

- 依賴：`GAME-RECAP-PA1-TAXONOMY1` 通過；同一 `<environment, cpbl>` 無其他 migration writer。
- 後續：schema 已驗證部署後，才可認領 BUILD1。
- 非目標：不建立 builder、不回填資料、不新增 public API 或前端。
