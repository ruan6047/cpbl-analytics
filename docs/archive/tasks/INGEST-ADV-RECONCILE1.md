# INGEST-ADV-RECONCILE1 進階排行榜快照晉升與污染資料修復〔T4；🔴資料正確性／data migration 紅線〕

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/INGEST-ADV-RECONCILE1`
- 執行：待指派　查核：待指派（跨模型家族或人工，須 ≠ 執行）
- Initiative：`INIT-OFFICIAL-DATA1`　spec 基線：[`../research/OFFICIAL_DATA_GAP1_RESULTS.md`](../research/OFFICIAL_DATA_GAP1_RESULTS.md) §3.1、§3.2、§6
- DB：`db_scope: data-migration`；`migration_phase=migrate`；依賴 `INGEST-ADV-EXPAND1` 通過；預定 resources：`db:local:cpbl`、`db:local:cpbl:table:advanced_stats`、新增 advanced tables
- 部署：是　環境：production　PR：—　Merge SHA：—
- Discovery：研究基線已完成；需求方 2026-07-22 指示開卡
- Design：N/A——純技術 ingest／資料修復；public response shape 預設不變

## 範圍

- 拆開 player scalar leaderboard 與 per-pitch-type rows，消除 `acnt` merge overwrite。
- 全量 fetch 寫 staging／run manifest，驗證 schema、空 ID、natural-key 重複與合理筆數後原子晉升。
- partial daily refresh 與完整 snapshot 分開標記；API／分析只讀最後成功完整 snapshot。
- snapshot 晉升必須在單一 transaction 內鎖定 run，驗證 `snapshot_scope='full'` 與
  `(year, kind_code, dataset, role)` 完全相符，先將 `status` 轉為 `promoted`，再 UPSERT
  `advanced_snapshot_state`；任一步失敗即整筆 rollback。DB composite FK 負責 immutable
  scope／identity backstop；可變的 promoted 狀態由此 transaction contract 負責。
- 對 2026 A/D `advanced_stats` 產出污染差異清單；備份後依官方 canonical set 修復。
- 建立 replay-safe batch、dry-run、resume、rollback、before/after row counts 與抽樣 payload 對帳。

## 驗收

- 2026 A 魔爾曼 `fastball`／`breakingball` 兩列皆存在，數值與官方 payload 一致。
- current snapshot 的有效 acnt 集合與同一 run 官方集合一致；空 ID 被 skip 且有計數／告警。
- 晉升後執行 pointer audit：`advanced_snapshot_state` JOIN `advanced_ingest_runs` 不得存在
  `status <> 'promoted'`、`snapshot_scope <> 'full'` 或 scope identity 不一致的列；結果必須為 0，
  並把查詢與 row count 留作 review／production evidence。
- 舊錯誤列不再被 public query 讀到；不得以直接 TRUNCATE 當修復方案。
- `ruff`、完整 pytest、route/API smoke、migration rehearsal、production backup／rollback evidence 齊全。
- T4 跨模型家族或人工查核；production data repair 另需需求方 sign-off。

## Log

- 2026-07-22 register by GPT-5@Codex（依 ruan6047 指示）；iteration 0；證據見研究基線。
- 2026-07-23 iteration 1 by Claude Opus 4.8：拆 scalar/球種/聯盟三 dataset、run-manifest 原子晉升、
  partial/full 分離、讀路徑 gating、reconcile CLI；本機修復 2026 A/D（863→682，備份後 targeted delete）。
- 2026-07-23 Gemini 跨家族 review APPROVE（P0/P1=0；P2×2 依建議於 ec8e2fb 修正）；merge 進 main
  （linear tail 1f59d5f）。
- 2026-07-23 production rollout（需求方 chat 授權）：部署 migration 063（Deploy 29971022124）、
  prod_cpbl_api 手動 migrate；資料修復先以 prod 備份（sha256 f4056ca9…）本機 rehearsal 演練通過後套 prod
  （--single-transaction 鏡像 5 表 + targeted delete，863→682、pointer_audit=0、魔爾曼雙列、live API 200）。
  卡片 🏁完成 / 部署 ✅已驗證。
