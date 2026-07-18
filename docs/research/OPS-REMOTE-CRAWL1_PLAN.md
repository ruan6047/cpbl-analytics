# Research Plan — OPS-REMOTE-CRAWL1

## 研究決策

- 要降低的不確定性：哪一種執行位置能在不繞過反爬限制的前提下，提供低維護、可觀測且
  足夠穩定的 CPBL 無人值守刷新。
- 研究問題：封鎖與 challenge 是否依出口環境穩定重現；三條候選路線的可靠性、安全性、
  維護成本與合規風險為何；需要哪些停止條件才能避免節流升級。
- 需求方：ruan6047　Discovery lead：待指派

## 假設與證據

| 假設 | 現有證據與來源 | 信心 | 不成立時的影響 |
|---|---|---|---|
| 現行 VPS 無法穩定直連 CPBL 主站 | AI_RUNBOOK／CPBL_SITE_MAP 的 404 與 challenge 紀錄 | 中 | 可優先採 VPS 直連，但仍需跨時窗可靠性驗證 |
| 台灣住宅出口可用但 Mac 是單點故障 | 現行 Playwright crawler 與 OPS-REFRESH1 流程 | 高 | 需重新檢查 crawler 本身或上游改版，不應先談遠端化 |
| 合規台灣出口可降低封鎖 | 尚無專案內實測 | 低 | 排除代理路線，改評估住宅 worker 或官方資料源 |

## 方法與界線

- 方法：設計 allowlist 單次 probe；以 fixture 驗證 no-retry／sanitization；獲授權後在不同
  出口與分離時窗執行，彙整狀態、redirect、challenge signature 與 latency。
- 對象／資料範圍：只探測既有 CPBL_SITE_MAP 已知公開入口；每次每目標最多一請求，禁止
  自動擴張 endpoint、暴力重試或完整資料擷取。
- 隱私與同意：不處理個資；輸出移除 cookie、authorization、token、完整 IP 與 query
  secret；代理方案須另查服務條款與資料處理邊界。
- AI 參與：可產生 probe、整理 sanitized evidence 與比較架構；不可將 challenge 視為可繞過
  目標，不可從單次結果聲稱長期可用。

## 結論

- 發現：待執行。
- 對 Discovery／Design 的影響：待證據矩陣完成後決定 GO／NO-GO 或補研究。
- 需求方確認：ruan6047／2026-07-18；implementation 仍須另開 T4 卡。
