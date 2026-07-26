# GAME-RECAP-PA1-TAXONOMY1 canonical PA transition taxonomy 稽核〔T4；🔴資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-PA1-TAXONOMY1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：[`GAME-RECAP-PA1_CONTRACT.md`](../design/GAME-RECAP-PA1_CONTRACT.md) §「PA 狀態機與穩定 ID」
- DB：`db_scope: read`；僅唯讀本機 `cpbl`，認領時須宣告 `db:local:cpbl`
- 部署：否　環境：—　PR：—　Merge SHA：—
- Discovery：`GAME-RECAP-DATA1` Checkpoint 1 已核可
- Design：Design Gate N/A；純資料正確性稽核，不提供使用者介面
- current-state：📥Backlog；不得與 EXPAND1／BUILD1 平行認領。

## 目標與驗收

- [ ] 以真實 `action_name`、`batting_action_name`、計數變化與換人／特殊事件欄位建立版本化 transition taxonomy，不以名稱猜測語意。
- [ ] 建立現行近似鍵誤配的紅燈案例，至少涵蓋同局重複投打、換投、代打、跑壘與特殊事件。
- [ ] 定義打席開始、中間、終結、非打席事件與未知事件的 fail-closed 行為，以及 builder 可直接消費的版本化輸出。
- [ ] 產出可重跑的抽樣／完整值域證據；跨模型家族或人工 reviewer 以原始事件複核。
- [ ] `uv run ruff check`、`uv run pytest` 通過；不新增 migration、不改 ingest、API 或前端。

## 依賴與交付

- 依賴：`GAME-RECAP-PA1` 契約已合併。
- 後續：查核通過才可解除 `GAME-RECAP-PA1-EXPAND1` 的 transition schema 前置。
- 非目標：不物化 PA、不寫資料庫、不決定 WP／WPA 或 public API。
