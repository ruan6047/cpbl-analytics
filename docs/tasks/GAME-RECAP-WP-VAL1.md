# GAME-RECAP-WP-VAL1 場中 WP 時間外驗證與支援邊界〔T4；🔴統計〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-WP-VAL1`
- 執行：待指派　查核：待指派（須跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`db_scope: read`；唯讀 canonical PA、games 與既有 run distribution／win expectancy
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §8
- Discovery：`GAME-RECAP-DATA1` 已核可；仍依賴 `GAME-RECAP-PA1` canonical contract。
- Design：Design Gate N/A；本卡只做統計 Go/No-Go，不改 public API 或 UI
- current-state：📥Backlog；已由 Coordinator 註冊，等待 `GAME-RECAP-PA1`。

## 目標

沿用現有 `models/winprob.py` 方法，但改用 PA1 的 canonical 打席，以 walk-forward／holdout season 驗證 WP 校準與規則邊界，先決定哪些賽季與賽制可對外提供，再投入 public API。

## 驗收條件

- [ ] 建模期間與驗證期間完全分離，逐季報告 Brier score、校準分箱、樣本數、主場基準與模型 span。
- [ ] 一軍例行賽、季後賽、二軍分別得到 `supported`、`proxy_with_warning` 或 `unsupported` 結論，不以一軍結果靜默外推。
- [ ] 再見、九局後規則、十二局和局、提前結束與狀態不可重建案例有明確統計處置。
- [ ] 產出 Go/No-Go 報告與門檻；未通過的 scope 不得進入 `GAME-RECAP-WP-API1`。

## 驗證

- [ ] 先證明現有同母體 calibration 不能作為時間外證據，再新增可重跑的 holdout／walk-forward 測試。
- [ ] `uv run ruff check`、`uv run pytest` 通過，驗證指令與 artifact 寫入 `docs/research/`。
- [ ] 獨立紅線 reviewer 重跑至少一個留出季並核對分母、資料洩漏與規則邊界。

## 依賴與交付

- 依賴：`GAME-RECAP-DATA1` ✅ → `GAME-RECAP-PA1`。
- 後續：只有通過的 scope 可解除 `GAME-RECAP-WP-API1` 阻塞。
- 預估範圍：M；不得順手修改 public API／前端。

## Log

- 2026-07-16 proposed in author preflight v1.1 → 為分離統計 Go/No-Go 與 API 實作而拆出；待 Coordinator 註冊。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；依賴未解除前不得 claim。
- 2026-07-19 `GAME-RECAP-DATA1` Checkpoint 1 已核可 → 僅保留 PA1 為阻塞依賴。
