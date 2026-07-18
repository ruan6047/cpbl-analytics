# OPS-REMOTE-CUTOVER1 遠端 crawler production canary 與切換 〔T4；🔴production／資料正確性／資安部署〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/OPS-REMOTE-CUTOVER1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　DB：`db_scope: write`；production `cpbl` 需專屬 lane lock、備份與 rollback
- 部署：是　環境：production＋本機 fallback　Design Gate：N/A；內部維運切換
- 計畫：[`../../ops-remote-crawler-rollout.md`](../../ops-remote-crawler-rollout.md) Phase 4–5
- 依賴：`OPS-REMOTE-WORKER1` T4 APPROVE、shadow 對帳達標、需求方 production sign-off。
- owner、worktree、iteration、最後交接與狀態見 [`../TASKS.md`](../TASKS.md) Ledger。

## 驗收

- [ ] 先 canary 單一排程時窗；remote 與 local crawler 有跨主機互斥，任何時刻只允許一個 primary writer。
- [ ] production 寫入前備份，逐表／批次失敗可觀測且 rollback rehearsal 通過；freshness 驗證使用真實資料 contract。
- [ ] 告警區分未觸發、challenge、crawler failure、sync failure、stale running 與資料對帳失敗；禁止沉默 fallback 後宣告成功。
- [ ] 本機 launchd 先保留停用／手動 fallback，不在同一變更刪除；回退 remote 後可單次安全接手且不冷啟動重跑。
- [ ] 連續多日 canary SLO、成本與值班負擔達標後，才由需求方決定 remote primary；未達標即 NO-GO／回復本機。
- [ ] 跨家族 T4 review、production sign-off、CI／deploy／smoke／資料 QA 全部留痕後才可 release。
