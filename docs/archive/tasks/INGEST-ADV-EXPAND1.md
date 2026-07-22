# INGEST-ADV-EXPAND1 進階排行榜維度與快照 additive schema〔T4；🔴資料正確性／schema 紅線〕

- 需求：ruan6047　規劃／執行：GPT-5@Codex　分支：`ai/gpt-5-codex/INGEST-ADV-EXPAND1`
- 查核：Claude Opus 4.8（跨模型家族；iteration 2 APPROVE）
- Initiative：`INIT-OFFICIAL-DATA1`　spec 基線：[`../../research/OFFICIAL_DATA_GAP1_RESULTS.md`](../../research/OFFICIAL_DATA_GAP1_RESULTS.md) §3.1、§3.2、§3.5
- DB：`db_scope: schema`；`migration_phase=expand`；預定 resources：`db:local:cpbl`、`db:local:cpbl:table:advanced_stats` 與新增表
- 部署：✅已驗證　環境：production　PR：[#38](https://github.com/ruan6047/cpbl-analytics/pull/38)　Merge SHA：`9e547358`
- Discovery：研究基線已完成；需求方 2026-07-22 指示開卡
- Design：N/A——純技術 additive schema，無 public API／UI 變更

## 範圍

- 新增 `advanced_pitch_type_stats`，主鍵至少含 `(year, kind_code, role, acnt, pitch_type)`；保存
  `pitches/kph/kph_max/spin_rate/spin_rate_max/throws` 與 provenance。
- 新增 `advanced_league_summary`，主鍵至少含 `(year, kind_code, category, pitch_type)`，
  metrics 使用 JSONB 容忍官方加欄。
- 新增完整 run／snapshot provenance 所需的 additive 結構；不得在本卡刪除、回填或切換
  `advanced_stats` 讀路徑。
- migration 必須 `IF NOT EXISTS`、可重跑；新增索引須評估 production lock 時間。

## 非目標

- 不修資料、不刪污染列、不切 API、不重跑爬蟲；由 `INGEST-ADV-RECONCILE1` 承接。
- 不把 coarse `fastball|breakingball` 映射成 `pitch_type_pred_v2`。

## Gate 與驗證

- 先讀 `DATABASE_CONTRACT.md`，取得唯一 schema migration lane。
- localhost 空庫與既有資料庫各重跑兩次 migration；schema diff、PK／index contract test 通過。
- production 前完整備份與 rollback rehearsal；T4 跨家族或人工查核＋需求方 sign-off。

## Log

- 2026-07-22 register by GPT-5@Codex（依 ruan6047 指示）；iteration 0；證據見研究基線。
- 2026-07-23 iteration 2 經 Claude Opus 4.8 固定 `946a716` 跨家族複驗 APPROVE，P0/P1/P2=0；PR #38 合併。
- 2026-07-23 production 前備份與 isolated rollback rehearsal 通過；備份 SHA-256 `588b4d1a…`。
- 2026-07-23 production rollout：cpbl CI `29941479851`、主站 CI `29942070155`、Deploy `29942259302` 全綠；由新 `prod_cpbl_api` 執行 migration 062（1.61s）。既有 `advanced_stats/games/pitch_tracking` 維持 `863/13,514/72,346`，四張新表為空、四個核心約束齊全、API 與代表頁面皆 200。`INGEST-ADV-RECONCILE1` 未執行。
