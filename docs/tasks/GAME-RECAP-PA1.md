# GAME-RECAP-PA1 canonical 打席與逐球可靠對應〔T4；🔴資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-PA1`
- 執行：待指派　查核：待指派（須跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：依 `GAME-RECAP-DATA1` 決策；可能為 `read` 或獨立 schema expand 卡，不得直接改既有 migration
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §3.3、§6.3、§7
- Discovery：`GAME-RECAP-DATA1` 已核可（Checkpoint 1）；採每日批次物化 canonical PA，不得沿用現有近似鍵直接公開。
- Design：Design Gate N/A；本卡建立資料契約，UI 由 `UX-GAME-PA1` 核可
- current-state：📥Backlog；已由 Coordinator 註冊，Checkpoint 1 已解除，可進 Design／expand 拆卡與實作。

## 目標

作為 canonical 打席與 `pa_id` 的唯一 owner，先可靠分組 livelog 打席，再串起 pitch_tracking，取代後端 WP、前端 moment 與逐球元件各自的近似鍵，確保同局重複對戰、換投、代打與事件缺漏不會產生不同打席邊界。

## 驗收條件

- [ ] 每個可重建打席具有穩定 `pa_id`、start/end event、投打者、打席結果與 ordered pitches；重新 refresh 後相同來源資料產生相同 ID。
- [ ] `models/winprob.py`、games WP route 與前端 moment builder 後續都能只消費同一打席契約，不需自行 `(batting_order,hitter)` 或連續 hitter 分組。
- [ ] PA response 擁有打席層 `tracking_availability` 與 mapping reason，但不計算或代理任何 WP 欄位。
- [ ] 同局同投打重複對戰、換投中打席、代打、換人事件與缺 pitch count 都有明確對應或 fail-closed 行為。
- [ ] API 可按單一 `pa_id` 回傳逐球資料與 availability reason，避免賽事首屏傳輸整場大型 tracking payload。
- [ ] 無設備、官方尚未更新、來源有缺漏與 mapping 失敗是不同狀態，不以同一個空陣列掩蓋。
- [ ] 對帳率與未知原因依年／球場／賽制輸出；未達 `GAME-RECAP-DATA1` 核可門檻不得開啟精確逐球 UI。

## 驗證

- [ ] 先建立可重現現有近似鍵誤配的紅燈測試。
- [ ] 單元與整合測試涵蓋同局重複對戰、換投、代打、無 TrackMan、晚到資料及 refresh 重跑穩定性。
- [ ] API route snapshot／contract test 更新；查詢具明確索引策略與 query plan 證據。
- [ ] `uv run ruff check`、`uv run pytest` 通過；獨立 reviewer 以原始事件人工對帳抽樣。

## 依賴與交付

- 依賴：`GAME-RECAP-DATA1` ✅（Checkpoint 1 已於 2026-07-19 核可）。
- 後續：解除 `UX-GAME-PA1` 的資料正確性阻塞。
- 預估範圍：M；需要 schema 時先拆 migration expand 卡與 backfill 卡。

## Log

- 2026-07-16 proposed by GPT-5@Codex → 待 Coordinator 註冊 lifecycle event。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；依賴未解除前不得 claim。
- 2026-07-19 `GAME-RECAP-DATA1` 跨家族查核與需求方 Checkpoint 1 核可完成 → 可進 Design／expand 拆卡；禁止以既有近似鍵直接實作 public canonical PA。
