# GAME-RECAP-DATA1 賽事復盤資料覆蓋與 canonical 契約稽核〔T4；🔴資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-DATA1`
- 執行：待指派　查核：待指派（須跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.2
- DB：`db_scope: read`；只讀 `games`、`game_livelog`、`game_scoreboard`、`batting_gamelog`（box PA 對帳分母）、`pitch_tracking`、`refresh_log` 及 `pg_catalog` 表體積 introspection；若結論要求 schema，另開 expand 卡
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §3、§7、§10
- Discovery：需求方 2026-07-16 確認資料節奏與使用目標；本卡補量化證據
- Design：Design Gate N/A；本卡是只讀資料研究，不改使用者介面
- current-state：📥Backlog；已由 Coordinator 註冊，Design Gate 核可前不得 claim

## 目標

核實現有資料是否足以可靠重建每個打席，並為後續 WP、逐球與 UI 定義 canonical 資料契約。禁止直接假設欄位完整或以單一場次抽樣外推全季。

## 驗收條件

- [ ] 產出逐年、`kind_code`、球場的 games／scoreboard／livelog／pitch_tracking 覆蓋矩陣，分開報告「沒有設備」與「理應有但缺漏」。
- [ ] 對帳每場 box score PA、livelog 重建 PA、逐球可連結 PA 的數量；列出未知 action、換人、再見、延長、和局、延賽與 0–0 邊界案例。
- [ ] 分別重現後端 run distribution、WP API 與前端 moment builder 的三套近似打席分組，建立打線輪轉、換人與事件缺漏的紅燈案例。
- [ ] 定義 canonical `pa_id`、事件排序、打席前後狀態與 source freshness 欄位；明確判定現有欄位能否可靠產生，不能者列 schema／ingest 缺口。
- [ ] 比較「每日批次物化」與「request-time 計算」的資料量、刷新時間、一致性與維護成本，提出單一推薦方案。
- [ ] 結論標明支援／不支援的賽季與賽制，且提供 fail-closed 規則，不能用一軍模型靜默代替二軍或季後賽。

## 驗證

- [ ] 稽核腳本或 SQL 可重跑，查詢皆唯讀、參數化，輸出保存於 `docs/research/`。
- [ ] 至少抽查一般完賽、0–0、再見、延長、和局、換投、同局同投打重複對戰與無 TrackMan 場次。
- [ ] 獨立查核者重跑抽樣並確認分母、缺漏分類及建議與證據一致。
- [ ] 若新增研究程式：`uv run ruff check`、`uv run pytest` 通過。

## 依賴與交付

- 依賴：無。
- 阻塞：`GAME-RECAP-PA1`、`GAME-RECAP-STATUS1` 在本卡 Checkpoint 未核可前不得進入實作。
- 預估範圍：M（研究／稽核；不得順手改 schema 或 API）。

## Log

- 2026-07-16 proposed by GPT-5@Codex → 待 Coordinator 註冊 lifecycle event。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；維持待指派。
- 2026-07-19 review by Claude（Opus 4.8，≠執行）→ **APPROVE**；重跑抽樣分母全數命中、三套分組重現忠於程式碼、ruff／pytest 通過。verdict：[`GAME-RECAP-DATA1_REVIEW.md`](../research/GAME-RECAP-DATA1_REVIEW.md)。非阻擋：N1 白名單已補正、N2 merge 前 rebase。
