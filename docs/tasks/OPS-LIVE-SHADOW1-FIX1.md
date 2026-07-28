# OPS-LIVE-SHADOW1-FIX1 完賽場停止輪詢〔T4；🔴production request safety〕

- 需求：ruan6047　規劃／執行：GPT-5.6@Codex　查核：須跨模型家族或人工，且 ≠ 執行
- 父卡：`OPS-LIVE-SHADOW1`　spec 基線：`LIVE_GAME_PRODUCT_SPEC v1.0`＋父卡既有 T4 安全契約
- DB：`db_scope: none`　部署：是（既有 VPS shadow observer image 更新）
- Design Gate：N/A；不新增介面、來源或產品狀態，只收斂既有 observer 的 request target

## Discovery／成功條件

- 2026-07-28 production evidence：A-226、A-227 已為 `FINISHED`，但 observer 每 cycle 仍請求 schedule＋A-226＋A-227＋A-228；21:43 時已用 3439/6000 attempts，剩 2561。依約 14 requests/min 的場中速率，A-228 明日完整九局有提前耗盡 hard budget 的風險。
- 成功條件：只在 **single-game HTTP 200 raw `GameStatus == "FINISHED"`** 後持久記錄該 allowlisted game ID；後續 cycle 與 container restart 均不再請求其 game endpoint。schedule 及尚未 FINISHED 的 A-228 繼續依既有 adaptive interval 輪詢。
- 本修正只減少 request；不得提高 6000 total、18/min global、5/game/min、timeout、retry 或 deadline，不得擴 URL allowlist／credential／network／volume 權限。

## 驗收條件

- [ ] `state.json` additive 保存排序且去重的 `terminal_game_ids`；只接受 `ALLOWED_GAME_IDS` 子集。既有無此欄位 state 向後相容；未知 ID／非字串／非 list 必須 fail closed。
- [ ] 只有 single-game response 同時滿足 `status_code == 200` 且 `raw_status == "FINISHED"` 才可標 terminal；schedule 的 status list、`SCHEDULED`、`START`、未知值、3xx／429／5xx／network error 均不得標記。
- [ ] terminal 標記與既有 attempts state 共用 writer lock、原子寫入與 fsync；不得覆寫 `attempts_total`、`recent_attempts`、`next_sequence` 或既有 evidence。
- [ ] 同一 process 下一 cycle、container restart 與 compose redeploy 後都跳過 terminal game endpoint；schedule 保留，未 terminal 的 A-228 必須繼續請求。
- [ ] 若本 cycle 首次觀察 FINISHED，該 response 仍完整寫入 raw gzip／manifest，從**下一 cycle**開始跳過；不得刪除或重寫既有 A-226/A-227 evidence。
- [ ] adaptive interval 只依本 cycle 實際結果決定；terminal game 不再以舊 `START` 狀態強迫 12 秒 interval。

## 驗證與部署閘門

- [ ] TDD RED 證明現況第二 cycle／restart 仍請求已完賽場；GREEN 覆蓋持久化、重啟、精確 FINISHED 判定、state validation、schedule/A-228 保留及既有 budget/evidence 不回歸。
- [ ] `uv run ruff check`、`uv run pytest` 全綠；production-equivalent scratch volume rehearsal 證明首次 terminal response 落證據、下一 cycle／restart 不再送出 terminal URL。
- [ ] 實作完成須由非 OpenAI 家族或人工完成 T4 implementation review；APPROVE、protected main merge、ruan6047 deployment sign-off 後，才可由 PersonalWebsite protected main 正常 workflow 部署。禁止 SSH 熱改、手動 `docker run` 或直接修改 production `state.json`。
- [ ] 部署後唯讀驗證：A-226/A-227 各最多新增一次 FINISHED observation 後停止成長；A-228 observation 繼續、budget 消耗率下降、sequence/raw SHA 連續、STOP/deadline 不變。

## 紅線

- 不把比分、局數、時間窗或 schedule status list 推論為 FINISHED；唯一 terminal 訊號是 allowlisted single-game HTTP 200 的 exact raw status。
- 不移除 schedule 請求、不放寬 request hard limits、不延長 2026-07-30 00:00（Asia/Taipei）deadline。
- 不刪除 evidence volume；本卡通過也不代表父卡 observation／7/30 對帳與撤除完成。

## Log

- 2026-07-28：A-226/A-227 完賽後由 ruan6047 指示「等今天比賽都結束再弄」並確認「現在比賽都結束了」；production 唯讀證據確認 request 浪費與 A-228 budget 風險，據此開 FIX1。
