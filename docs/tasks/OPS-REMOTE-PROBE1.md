# OPS-REMOTE-PROBE1 Opt-in DEBUG 網路探測介面 〔T3；🔴外部服務／診斷安全〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/OPS-REMOTE-PROBE1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　父 Discovery：`OPS-REMOTE-CRAWL1`
- DB：`db_scope: none`；禁止連線 local／production DB
- 部署：否　環境：local＋VPS 手動 opt-in　Design Gate：N/A；內部診斷 CLI，不是公開產品介面
- 計畫：[`../../ops-remote-crawler-rollout.md`](../../ops-remote-crawler-rollout.md) Phase 1
- 依賴：`OPS-REMOTE-CRAWL1` 先核可 probe contract 與 live probe 停止條件；未核可不得 claim。
- owner、worktree、iteration、最後交接與狀態見 [`../TASKS.md`](../TASKS.md) Ledger。

## 驗收

- [ ] DEBUG 介面為明確 opt-in CLI（例如額外 allow-live flag），endpoint 固定 allowlist；不得提供公開 HTTP debug route。
- [ ] 每次每目標至多一個 request、timeout 有上限、禁止 retry／redirect loop 自動追打、禁止啟動正式 crawler。
- [ ] JSON schema 僅含環境標籤、時間、status、有限 redirect metadata、challenge signature、latency 與分類；cookie、token、authorization、完整 IP／query secret 必須 redacted。
- [ ] fake transport 測試先證明 no-retry、allowlist、redaction 與 deterministic exit codes，再由 Coordinator 分別授權 local／VPS 單次 live probe。
- [ ] 產物只進受保護 CI artifact 或本機忽略路徑；不得把 live diagnostics、headers 或 secrets commit 進 git。
