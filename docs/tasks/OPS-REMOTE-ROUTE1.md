# OPS-REMOTE-ROUTE1 遠端出口路線資格驗證 〔T3；🔴外部服務／合規〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/OPS-REMOTE-ROUTE1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　父 Discovery：`OPS-REMOTE-CRAWL1`
- DB：`db_scope: none`　部署：否　環境：local＋候選遠端出口
- Design Gate：N/A；純技術路線決策，不改使用者流程
- 計畫：[`../../ops-remote-crawler-rollout.md`](../../ops-remote-crawler-rollout.md) Phase 2
- 依賴：`OPS-REMOTE-PROBE1` 通過獨立查核；每次 live probe 仍需 Coordinator 授權並分離時窗。
- owner、worktree、iteration、最後交接與狀態見 [`../TASKS.md`](../TASKS.md) Ledger。

## 驗收

- [ ] 使用同版 probe／schema 比較 VPS 直連、合規台灣出口、住宅 worker；每個時窗維持單次請求與零 retry。
- [ ] 證據矩陣區分 reachability、challenge、redirect loop、rate limit、DNS／TLS／timeout，不用單次成功宣稱穩定。
- [ ] 評估服務條款、資料處理地、出口供應商合規、credential 邊界、固定成本、值班負擔、單點故障與退出成本。
- [ ] 每條路線給出 GO／NO-GO／補研究，並列明可信度、停止條件、kill switch 與下一階段可用的最小權限。
- [ ] 需求方完成 Discovery Gate sign-off；沒有明確 GO 路線時 `OPS-REMOTE-WORKER1` 不得 claim。
