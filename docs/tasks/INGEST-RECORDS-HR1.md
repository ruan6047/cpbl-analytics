# INGEST-RECORDS-HR1 官網 /stats/hr 逐轟里程碑入庫〔T4；🔴資料正確性／schema〕

> **狀態 📥Backlog**：由 DISCOVERY-CPBL-RECORDS1（已 merge `dfec0a1`）判定 /stats/hr = Go 後註冊。待 GAME-RECAP-PA1-EXPAND1 部署釋出 migration lane 後認領。

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/INGEST-RECORDS-HR1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：`INIT-OFFICIAL-DATA1`　spec 基線：[`../research/DISCOVERY-CPBL-RECORDS1_RESULTS.md`](../research/DISCOVERY-CPBL-RECORDS1_RESULTS.md)（/stats/hr Go 段）
- DB：`db_scope: schema→write`；`migration_phase: expand→migrate`　部署：是　環境：production
- Discovery：`DISCOVERY-CPBL-RECORDS1` 判 /stats/hr 為 Go；穩定鍵 1584 列抽樣零碰撞、改名／跨年／同場多轟／季後四項抽查通過

## 背景

DISCOVERY-CPBL-RECORDS1 實測 `/stats/hr` 提供既有資料**沒有**的逐轟里程碑維度（`HomeRunType`、`Citizenship`），穩定鍵 `(year, kind_code, 場次, 局數, hitter_acnt, pitcher_acnt)` 於 1584 列抽樣零碰撞，event identity 於改名（`0000001606` 林祐樂→林岱安）、跨年（1997 vs 2026）、同場多轟、季後賽（KindCode=C/E）四情境均以真實回應驗證可重跑。

## 目標與驗收

- [ ] 新增 `cpbl.home_run_log`（或等價命名）additive migration，PK = 上述穩定鍵，冪等 UPSERT；保留 `HomeRunType`／`Citizenship` 等新維度。
- [ ] parser 對缺欄位寬容（`r.get`＋`_to_int/_to_float`），與既有 ingest 容缺慣例一致。
- [ ] **低頻 audit ingest**，不併入每日 Playwright（DISCOVERY 已評估一次性／低頻足夠）；只能本機爬（VPS IP 被擋）。
- [ ] 回填抽查 event identity 四情境；`uv run ruff check`＋`uv run pytest`（新端點同步路由快照 EXPECTED）通過。
- [ ] production rehearsal＋備份＋跨模型家族或人工 review 通過，且經需求方 production sign-off 才部署。

## 依賴與非目標

- 依賴：`GAME-RECAP-PA1-EXPAND1` 部署後釋出 migration lane（同一 `<environment, cpbl>` 無並行 migration writer）。
- 非目標：`/stats/toplist`（No-Go，與既有 leaders 純重複）、`/stats/mvp`（單月 MVP，低優先 backlog，不在本卡）。

## Log

- 2026-07-24 register by Claude Opus 4.8（Coordinator，依 ruan6047 指示）；iteration 0。依 DISCOVERY-CPBL-RECORDS1 Go 結論開卡。
