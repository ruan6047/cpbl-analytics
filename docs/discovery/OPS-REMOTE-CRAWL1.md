# Discovery Brief — OPS-REMOTE-CRAWL1

## 問題與情境

- 使用者／利害關係人：ruan6047；cpbl-analytics 維運者與資料消費者。
- 觸發情境與現行流程：CPBL 主站資料只能由台灣住宅網路上的 Mac crawler 擷取，再同步
  production；OPS-REFRESH1 以 launchd 讓流程無人值守，但仍依賴筆電開機與住宅網路。
- 痛點與影響：本機 worker 是單點故障；既有觀察顯示 VPS／機房 IP 可能遭 404 或 HiNet
  challenge，但尚缺同一探測工具、同時段與結構化證據，無法判斷遠端直連是否穩定可行。

## 目標與邊界

- 目標結果：先核可低風險 DEBUG probe contract，再以可重現證據決定遠端無人值守 crawler
  應採 VPS 直連、合規台灣出口或住宅網路 worker；產出可交給 shadow／cutover 卡的網路與安全契約。
- 成功條件：兩種出口使用同一 probe schema；能區分可達、challenge、redirect loop、封鎖與
  transient failure；完成路線比較及明確 GO／NO-GO／補研究結論。
- 非目標：本 Discovery 不寫 probe code、不寫 DB、不跑完整 Playwright crawler、不解 challenge、
  不偽造身份、不連續重試、不採購代理、不部署 production 排程，也不宣稱單次成功代表長期可靠。

## 證據與假設

- 已知證據：[`../AI_RUNBOOK.md`](../AI_RUNBOOK.md) 與
  [`../CPBL_SITE_MAP.md`](../CPBL_SITE_MAP.md) 記錄 VPS 機房 IP 失敗、住宅網路可透過
  Playwright 取得資料，以及連續冷啟動會升級節流；OPS-REFRESH1 已讓本機刷新可觀測。
- 待驗證假設：VPS 封鎖是否固定依 ASN／地理位置；台灣合規出口是否能穩定通過；住宅
  worker 能否在不增加維護負擔下由遠端控制與監測；probe signature 是否足以分類故障。
- 研究計畫：[`../research/OPS-REMOTE-CRAWL1_PLAN.md`](../research/OPS-REMOTE-CRAWL1_PLAN.md)
- 驗證方法：先以 fake response 驗證 probe 安全契約；取得 Coordinator 授權後，在分離時窗
  各做低頻單次 local／VPS probe，保留 sanitized JSON 並比較。

## 決策

- 需求方確認：ruan6047／2026-07-18／本 task 對話。
- 結論：進入分階段 Discovery；只可先核可 `OPS-REMOTE-PROBE1` 的安全 DEBUG contract，
  路線、shadow worker 與 production cutover 逐 Gate 解鎖，尚未核准遠端 crawler 或 production 部署。
