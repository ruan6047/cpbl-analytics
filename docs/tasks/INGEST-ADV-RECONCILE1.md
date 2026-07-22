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
- 對 2026 A/D `advanced_stats` 產出污染差異清單；備份後依官方 canonical set 修復。
- 建立 replay-safe batch、dry-run、resume、rollback、before/after row counts 與抽樣 payload 對帳。

## 驗收

- 2026 A 魔爾曼 `fastball`／`breakingball` 兩列皆存在，數值與官方 payload 一致。
- current snapshot 的有效 acnt 集合與同一 run 官方集合一致；空 ID 被 skip 且有計數／告警。
- 舊錯誤列不再被 public query 讀到；不得以直接 TRUNCATE 當修復方案。
- `ruff`、完整 pytest、route/API smoke、migration rehearsal、production backup／rollback evidence 齊全。
- T4 跨模型家族或人工查核；production data repair 另需需求方 sign-off。

## Log

- 2026-07-22 register by GPT-5@Codex（依 ruan6047 指示）；iteration 0；證據見研究基線。
