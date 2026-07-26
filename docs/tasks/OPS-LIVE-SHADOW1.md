# OPS-LIVE-SHADOW1 VPS 隔離 live source observer 〔T3；⚪production 隔離觀測〕

- 需求：ruan6047　規劃：GPT-5.6@Codex　分支：`ai/<執行者>/OPS-LIVE-SHADOW1`
- 執行：待指派（建議 L2；沿用既有 HTTP／容器模式，範圍限 deterministic observation）　查核：待指派（建議 L3；須獨立驗證 production 隔離與撤除邊界，且 ≠ 執行）
- Initiative：INIT-OFFICIAL-DATA1　spec 基線：v1
- DB：`db_scope: none`；不得取得或掛載 local／production DB credentials
- 部署：是　環境：production VPS（隔離 shadow namespace）　PR：—　Merge SHA：—
- 範圍：見 [`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §4.1–§4.2；只蒐集 `LIVE-GAME-BACKEND1` T4 觀測矩陣需要的來源證據，不提供 public contract
- Discovery：ruan6047 於 2026-07-26 核可「先建立、審核並部署隔離 VPS observer，使開發機可關閉」；成功條件為不接 production data plane 仍能跨 T-30h／T-90m／T-60m／T-30m／START 留存證據
- Design：Design Gate N/A；本卡為無公開入口、無使用者可見狀態的暫時性維運觀測器
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log

## 驗收條件

- [ ] observer 僅對 `stats.cpbl.com.tw` 執行唯讀請求；不得連 `www.cpbl.com.tw`、production DB、production Redis、公開 API router 或 Docker socket，且不得開放 inbound port。
- [ ] 以獨立 container name、network、read-only root filesystem 與專用持久化 volume 執行；限制 CPU／memory／log rotation，process 使用 non-root user，重啟後可接續 append，不覆寫既有 observation。
- [ ] 每筆 JSONL 證據至少保存 UTC／Asia-Taipei 觀測時間、game ID、HTTP status／latency、官方 raw status、目標 key path 的 presence／count 與 payload hash；不得把時間窗、空陣列或未知值推論成已公布／完賽。
- [ ] 具全域 request budget、jitter／backoff、單 instance lock、kill switch，以及不晚於 2026-07-30T00:00:00+08:00 的自動停止條件；停止後容器不得因 restart policy 循環復活。
- [ ] observer 輸出只作 `LIVE-GAME-BACKEND1` 查核證據；不得被 production API、前端或正式 refresh 消費。完整 T4 後端卡仍須獨立查核，不因本卡通過而降級。

## 驗證

- [ ] unit／integration tests 覆蓋成功、429／5xx／timeout、schema drift、重啟續寫、request budget、kill switch、截止時間與不覆寫；`uv run ruff check`、`uv run pytest` 通過。
- [ ] 以本機正式 image rehearsal，檢查 non-root、read-only rootfs、無 inbound port、無 DB／production cache environment、資源限制、volume 持久化與停止後不重啟。
- [ ] 獨立查核 APPROVE 且合併 `main` 後才可部署；部署時記錄 main source SHA、container inspect、stats 200／latency、第一筆 JSONL、kill-switch smoke 與完整撤除命令。
- [ ] 7/30 或證據收集完成後移除 container／network；volume 在 `LIVE-GAME-BACKEND1` 證據匯出與 checksum 對帳完成前保留，之後依需求方指示刪除。

## 依賴與範圍

- 本卡從 `main` 獨立實作，不 cherry-pick 或部署尚未通過 T4 的 `ai/codex/LIVE-GAME-BACKEND1`。
- 本卡無 implementation 前置；其經查核的輸出是 `LIVE-GAME-BACKEND1` 來源觀測矩陣的證據輸入。
- `UX-LIVE-GAME1` 仍只依賴完整 `LIVE-GAME-BACKEND1` additive API contract，不得依賴本 observer。

## Log

- 2026-07-26T20:24:13+08:00 register by GPT-5.6@Codex（依 ruan6047 核可建立 VPS 隔離 observer 卡；尚未 claim、實作或部署）。
