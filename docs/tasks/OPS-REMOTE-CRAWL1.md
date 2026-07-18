# OPS-REMOTE-CRAWL1 遠端無人值守 crawler 可行性探測 〔T3；🔴外部服務／維運〕

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/OPS-REMOTE-CRAWL1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: none`；不得讀寫 local／production DB
- 部署：否　環境：local＋VPS（僅經明確授權執行 probe）　PR：—　Merge SHA：—
- 範圍：見 [`../discovery/OPS-REMOTE-CRAWL1.md`](../discovery/OPS-REMOTE-CRAWL1.md)
- Discovery：[`../discovery/OPS-REMOTE-CRAWL1.md`](../discovery/OPS-REMOTE-CRAWL1.md)；需求方 2026-07-18 確認
- Design：Design Gate N/A；純技術網路可行性研究，不改使用者流程或公開介面
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log

## 目標與驗收

- [ ] 建立 opt-in、allowlist 限定的單次 probe：每次執行每個目標最多一個請求、禁止 retry、
  不啟動正式 crawler、不寫 DB，輸出不含 cookie／token／credential 的結構化 JSON。
- [ ] 以同一 probe 比較本機住宅出口與 VPS，記錄 HTTP status、redirect chain、challenge
  signature、延遲與執行環境；任何 live probe 均需 Coordinator 明確授權並遵守冷卻紀律。
- [ ] 形成證據矩陣與 GO／NO-GO：評估 VPS 直連、合規台灣出口、住宅網路 worker 三條路線，
  列出可靠性、維護成本、法規／服務條款、secret 邊界及單點故障。
- [ ] 只有 Discovery Gate 通過後才另開 T4 implementation 卡；不得在本卡部署遠端排程、
  繞過反爬 challenge 或修改 production 資料管線。

## 驗證與依賴

- 驗證：probe 的 fake-response／sanitization／no-retry 契約測試；local／VPS 輸出 schema
  一致性；Runbook 記錄執行前置、冷卻與停止條件；跨家族或人工 T3 查核。
- 依賴：OPS-REFRESH1 通過 T4 source review；live VPS probe 另需 Coordinator 明確授權。
- 研究計畫：[`../research/OPS-REMOTE-CRAWL1_PLAN.md`](../research/OPS-REMOTE-CRAWL1_PLAN.md)
- 預估範圍：M；probe 與分析同卡，任何 production crawler／代理採購／排程另開卡。

## Log

- 2026-07-18 註冊：OPS-REFRESH1 固定 SHA `38040bb` 已獲 Claude Sonnet 5 T4 APPROVE；
  依需求方指示另開 Discovery，不回頭修改已核准 source。
