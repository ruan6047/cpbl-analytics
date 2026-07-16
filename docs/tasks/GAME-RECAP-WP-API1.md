# GAME-RECAP-WP-API1 canonical WP／WPA public contract〔T4；🔴統計／資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-WP-API1`
- 執行：待指派　查核：待指派（須跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.2
- DB：依 DATA1 決策；預設 `read`，若物化另開 schema expand／backfill 卡
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §8、§10
- Discovery：依賴 `GAME-RECAP-WP-VAL1` Go 與 PA1 canonical contract
- Design：Design Gate N/A；本卡實作已核可的 public data contract
- current-state：📥Backlog；已由 Coordinator 註冊，等待 `GAME-RECAP-PA1`／`GAME-RECAP-WP-VAL1`

## 目標

只消費 `GAME-RECAP-PA1` 的 canonical 打席，為已通過 WP-VAL1 的 scope 提供打席前後 WP、WPA、受益隊與模型 metadata；不再自行重建或去重打席。

## 驗收條件

- [ ] 每個可靠打席回傳 `pa_id`、`home_wp_before`、`home_wp_after`、`wpa`、受益隊與 model metadata，事件／比分／壘況直接引用 PA1 契約。
- [ ] 換局、終場、再見、和局、延長及不可靠狀態具有唯一 canonical 行為；不可靠列保留事件但 WP/WPA 不可用。
- [ ] 未通過 WP-VAL1 的賽季／賽制回傳明確 `wp_availability`，不計算代理值。
- [ ] 本卡是 `wp_availability` 的唯一 owner；不要求 STATUS1 聚合或重算模型支援狀態。
- [ ] 現有 `/winprob` 採相容演進或 versioned route；前端遷移完成前不破壞既有 consumer。

## 驗證

- [ ] 先建立現有近似分組會失敗的 route／contract 紅燈測試。
- [ ] 邊界單元測試、API contract、route snapshot 與相容性測試通過。
- [ ] `uv run ruff check`、`uv run pytest` 通過；獨立 reviewer 複算至少一組 WP/WPA 邊界。

## 依賴與交付

- 依賴：`GAME-RECAP-PA1 → GAME-RECAP-WP-VAL1`。
- 後續：解除 `UX-GAME-RECAP1`、`UX-GAME-PA1` 的 WP 契約阻塞。
- 預估範圍：M；migration／大量 backfill 必須拆卡。

## Log

- 2026-07-16 proposed in author preflight v1.1 → 為分離統計 Go/No-Go 與 API 實作而拆出；待 Coordinator 註冊。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；依賴未解除前不得 claim。
