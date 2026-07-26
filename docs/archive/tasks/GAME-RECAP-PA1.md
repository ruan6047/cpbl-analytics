# GAME-RECAP-PA1 canonical 打席與逐球對應契約與切卡〔T4；🔴資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-PA1`
- 執行：待指派　查核：待指派（須跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`db_scope: none`（本卡僅 canonical contract／切卡）；依 `GAME-RECAP-DATA1` 決策，schema 與 data-migration 必須拆為獨立卡，不得直接改既有 migration
- 部署：否（本卡僅契約／切卡）　環境：—　PR：—　Merge SHA：`e7a065b507b3a0851e6709947dcdd76adb59a9eb`
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §3.3、§6.3、§7
- Discovery：`GAME-RECAP-DATA1` 已核可（Checkpoint 1）；採每日批次物化 canonical PA，不得沿用現有近似鍵直接公開。
- Design：Design Gate N/A；本卡建立資料契約，UI 由 `UX-GAME-PA1` 核可
- current-state：📦已合併；canonical 契約與實作切片已通過跨模型家族查核並合併。**這不代表 canonical PA 功能已完成或可部署**；實作與其驗收由 TAXONOMY1、EXPAND1、BUILD1 三張子卡承接。

## 目標

作為 canonical 打席與 `pa_id` 的唯一契約 owner，凍結資料模型、reconciliation 與 availability 語意，並將實作切為可獨立驗證的紅線子卡；不得由本卡直接吞併 schema、資料回填、API 或前端工作。

## 驗收條件

- [x] 契約凍結 stable `pa_id`、來源 revision、reconciliation、打席層 tracking availability 與 fail-closed 邊界。
- [x] 將實作切分為唯讀 taxonomy、additive schema expand、builder／reconciliation／backfill，且明定資料庫 lease 與獨立跨模型家族查核。
- [x] 凍結「WP／前端 consumer 僅讀 materialized PA、不得再用近似鍵分組」的交接邊界。
- [ ] TAXONOMY1 以真實 action 值域與紅燈案例定義 transition taxonomy。
- [ ] EXPAND1 建立 additive schema 與來源 revision 留痕。
- [ ] BUILD1 完成 materialization、對帳、歷史回填與 API-ready published build；未達核可門檻不得開啟精確逐球 UI。

## 驗證

- [x] 合併前完成 `git diff --check`、`uv run ruff check`、`uv run pytest`（332 collected；1 skipped）與跨模型家族契約查核。
- [ ] 子卡各自完成其紅燈測試、對帳／query plan 或 migration rehearsal、適用的 route contract，以及獨立 reviewer 證據。

## 設計與切片（2026-07-19 draft）

- 契約草案：[`GAME-RECAP-PA1_CONTRACT.md`](../design/GAME-RECAP-PA1_CONTRACT.md)。
- 子卡（皆 T4）：[`GAME-RECAP-PA1-TAXONOMY1`](GAME-RECAP-PA1-TAXONOMY1.md)（只讀 transition taxonomy）、[`GAME-RECAP-PA1-EXPAND1`](GAME-RECAP-PA1-EXPAND1.md)（schema expand＋來源 revision 留痕）、[`GAME-RECAP-PA1-BUILD1`](GAME-RECAP-PA1-BUILD1.md)（batch materialization／reconciliation／historical backfill）。
- 子卡已完成註冊但均未認領；必須依 TAXONOMY1 → EXPAND1 → BUILD1 順序取得各自 resource lease、跨模型家族或人工查核與適用的需求方 sign-off。

## 依賴與交付

- 依賴：`GAME-RECAP-DATA1` ✅（Checkpoint 1 已於 2026-07-19 核可）。
- 後續：BUILD1 對帳通過後才解除 `UX-GAME-PA1` 與 WP 主鏈的資料正確性阻塞。
- 預估範圍：本卡已完成；功能工作量由三張子卡各自估算與交付。

## Log

- 2026-07-16 proposed by GPT-5@Codex → 待 Coordinator 註冊 lifecycle event。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；依賴未解除前不得 claim。
- 2026-07-19 `GAME-RECAP-DATA1` 跨家族查核與需求方 Checkpoint 1 核可完成 → 可進 Design／expand 拆卡；禁止以既有近似鍵直接實作 public canonical PA。
- 2026-07-21 契約查核通過後合併（`e7a065b`）；調整卡片為契約／切卡 parent，註冊三張未認領實作子卡。功能驗收仍由子卡完成，並非已部署功能。
