# OPS-REMOTE-WORKER1 隔離式遠端 crawler shadow worker 〔T4；🔴爬蟲／資料正確性／資安〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/OPS-REMOTE-WORKER1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　DB：`db_scope: write`，僅隔離 namespace／artifact；禁止 production DB
- 部署：是（shadow only）　環境：獲核可的遠端路線　Design Gate：N/A；內部維運 worker
- 計畫：[`../../ops-remote-crawler-rollout.md`](../../ops-remote-crawler-rollout.md) Phase 3
- 依賴：`OPS-REMOTE-ROUTE1` 明確 GO＋需求方 sign-off；無 GO 不得 claim。
- owner、worktree、iteration、最後交接與狀態見 [`../TASKS.md`](../TASKS.md) Ledger。

## 驗收

- [ ] 一次性 remote job 使用隔離 DB/schema 或不可變 artifact，絕不寫 production、絕不觸發現行 local sync。
- [ ] 與正式 crawler 共用解析 code path，不另造無法代表真實流程的第二套假 crawler；網路與 DB credential 最小權限、可輪替且不進 log。
- [ ] 具全域互斥、冷卻、零跨 run 自動 retry、timeout、kill switch、結構化狀態與 artifact retention。
- [ ] shadow 結果與本機同時段資料做 row count、key set、freshness、parse error 對帳；差異 fail closed。
- [ ] T4 reviewer 實測中止、challenge、DB failure、重複排程與 secret redaction；通過前不建立 production 排程。
