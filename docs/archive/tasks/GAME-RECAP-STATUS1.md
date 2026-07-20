# GAME-RECAP-STATUS1 賽事狀態、資料可用性與 freshness API〔T4；🔴資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-STATUS1`
- 執行：待指派　查核：待指派（須跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：依 DATA1 結論；預設 `read`，需要逐來源紀錄時另開 schema expand／backfill 卡
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §7
- Discovery：`GAME-RECAP-DATA1` 已核可（Checkpoint 1）；仍須以官方狀態值域與 row-level freshness 證據定義 contract，證據不足時 fail closed。
- Design：Design Gate N/A；本卡提供狀態 public contract，文案與頁面由 UX 卡核可
- current-state：📥Backlog；已由 Coordinator 註冊，Checkpoint 1 已解除，可進實作前的狀態值域與 freshness 設計。

## 目標

提供官方賽事狀態、raw play-by-play availability 與來源 freshness，讓前端不再以 0–0、空陣列或時間猜測資料狀態。本卡不擁有 canonical PA／tracking mapping 或 WP availability。

## 驗收條件

- [ ] API 分開回傳 `official_game_status`、raw `play_by_play_availability`、`advanced_freshness` 與各來源時間。
- [ ] `unknown`、`source_error`、`pending_refresh` 具有可證明且互斥的判定；證據不足時 fail closed 為 unknown。
- [ ] 0–0、延賽、取消、有 scoreboard 無 livelog、refresh 成功但單場缺漏、進階資料晚到均有 contract test。
- [ ] 若現有 `refresh_log` 不足，先交付 schema expand／ingest instrumentation 子卡，STATUS1 不以猜測補洞。
- [ ] 契約明確指向 PA1 提供 `tracking_availability`、WP-API1 提供 `wp_availability`；STATUS1 不依賴或重做兩者判斷。

## 驗證

- [ ] 官方 `present_status` 值域與真實樣本列入研究 artifact，不虛構 mapping。
- [ ] API contract、route snapshot、資料缺漏整合測試通過。
- [ ] `uv run ruff check`、`uv run pytest` 通過；獨立 reviewer 以 DB 原始列重算狀態抽樣。

## 依賴與交付

- 依賴：`GAME-RECAP-DATA1` ✅（Checkpoint 1 已於 2026-07-19 核可）。
- 後續：解除 `UX-GAME-RECAP1`、`UX-GAME-HOME1` 的狀態契約阻塞。
- 預估範圍：M；schema／ingest instrumentation 另拆卡。

## Log

- 2026-07-16 proposed in author preflight v1.1 → 補齊狀態與 freshness API owner；待 Coordinator 註冊。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；依賴未解除前不得 claim。
- 2026-07-19 `GAME-RECAP-DATA1` 跨家族查核與需求方 Checkpoint 1 核可完成 → 可進官方狀態值域與 row-level freshness 設計；不得以 `present_status=1` 或比分猜測 completed。
