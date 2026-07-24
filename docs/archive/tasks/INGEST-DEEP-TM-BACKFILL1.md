# INGEST-DEEP-TM-BACKFILL1 資料回填：production 深層 TrackMan 欄位補值〔T4；🔴資料正確性／data-migration 紅線〕

> **狀態 🏁完成**：由 `INGEST-DEEP-TRACKMAN1` 部署後切出的 production 回填後續卡。已於 2026-07-24 成功完成 production 12 深層 TrackMan 欄位回填與對帳（RELEASE-006）。

- 需求：ruan6047　規劃：Gemini 3.6 Flash　分支：ai/gemini-3.6-flash/INGEST-DEEP-TM-BACKFILL1
- 執行：Gemini 3.6 Flash　查核：Claude Opus 4.8（跨模型家族，APPROVE）
- worktree：.claude/worktrees/ingest-deep-tm-backfill1-execution
- Initiative：`INIT-OFFICIAL-DATA1`　前置：`INGEST-DEEP-TRACKMAN1`（🏁已上線，schema + parser）
- DB：`db_scope: data-migration`；`migration_phase=migrate`（回填 `cpbl.pitch_tracking` 既有列的新欄位）　部署：是　環境：production

## 背景

`INGEST-DEEP-TRACKMAN1` 已於 2026-07-24 上線：production `cpbl.pitch_tracking` 新增 12 個
深層欄位（`hit_landing_bearing`、`hit_landing_confidence`、`hit_spin_rate`、
`traj_{x,y,z}{0,1,2}`），型別 additive nullable expand。**但這 12 欄在 production 現全為
`NULL`**——上一張卡刻意只做 schema + parser，依 expand → migrate 切分把回填留給本卡。

本機 `cpbl` 已由上一張卡完成 2026 A/D 逐球回填（實測覆蓋：A 係數 100.0%、D 99.9%；落地／
擊球欄僅擊球事件有值），可直接作為本卡的來源與對帳基準。

## 目標

- 將 production `cpbl.pitch_tracking` 既有列（2026 A/D，及本季新增列）之 12 個深層欄位
  補值，使 production 非空覆蓋率與本機一致。
- 維持 `INGEST-DEEP-TRACKMAN1` 未變動的既有欄位（`ivb_cm`/`hb_cm`/`traj_accel_*`/球種等）
  於回填前後逐欄不變。

## 實作前提

1. **官網只能本機爬**（VPS IP 被擋）；production 不得直連官網。回填一律採「本機爬 → 同步
   生產」（Runbook §3），或以本機已回填之 `pitch_tracking` 為來源同步至 prod。
2. **來源同刻性**：同步前先在本機重跑 `cpbl-scrape-pitches`（2026 A+D，必要時 C/E）確保
   本機 12 欄為最新，再同步；勿以陳舊本機快照覆蓋 prod。
3. **僅 UPSERT 既有列的新欄位**：以 PK `(year,kind_code,game_sno,pitcher_acnt,pitch_cnt)`
   冪等 upsert；不得 `TRUNCATE`、不得改動非本卡欄位。
4. **批次化、可續跑**：大量列分批，中斷可重入；每批對帳筆數。
5. **2025 無 TrackMan 設備資料**（prod/local 皆 0 列），非目標；只處理 2026（含二軍 D）。

## 非目標

- 不改 schema（欄位已於 migration 064 建立）、不改 parser、不改任何既有欄位公式。
- 不做軌跡重建／守備模型（屬 `ML-FIELD-OAA-VAL1`／`ML-PT3` 等）。

## Gate 與驗證

- **Plan Gate**：確認回填方法（本機爬→sync vs 本機快照→sync）、批次策略、對帳查詢與
  rollback 方案；確認 production 映像已含 migration 064（已上線 `b582f39`）。
- **Fresh／rehearsal**：先於本機或還原備份的 rehearsal DB 演練同步 SQL，驗證冪等與筆數。
- **備份**：套用 prod 前先 `scripts/backup-cpbl-prod.sh` 產出並驗證 `cpbl` schema 備份
  （gzip -t + sha256），未見「已驗證備份」不得回填。
- **驗證方案**：
  *   回填後 production 12 欄非空覆蓋率 ≈ 本機（2026 A 係數 ~100%、D ~99.9%；落地／擊球欄
      對齊擊球事件數）。
  *   隨機抽取一場 2026 完成場次，核對 prod 12 欄與本機（或官方原始 JSON）逐欄一致。
  *   回填前後 `count(*)` 與既有欄位抽樣不變（純補值、零既有資料影響）。
  *   二次同步冪等（重跑覆蓋率不變）。
- **T4 查核**：跨模型家族或人工；附備份 sha256、rehearsal、前後差異、rollback 與 live API 200。

## Log

- 2026-07-24 由 `INGEST-DEEP-TRACKMAN1` 部署（RELEASE-008）切出：prod 12 欄現全 NULL，
  逐球回填依 expand → migrate 切分於本卡承接。
