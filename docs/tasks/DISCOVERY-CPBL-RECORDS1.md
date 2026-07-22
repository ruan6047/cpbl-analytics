# DISCOVERY-CPBL-RECORDS1 主站紀錄資料價值與穩定鍵 Discovery〔T3；⚪一般研究〕

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/DISCOVERY-CPBL-RECORDS1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：`INIT-OFFICIAL-DATA1`　spec 基線：[`../research/OFFICIAL_DATA_GAP1_RESULTS.md`](../research/OFFICIAL_DATA_GAP1_RESULTS.md) §3.6
- DB：`db_scope: read`　部署：否　環境：—　PR：—　Merge SHA：—
- Discovery：本卡即 Discovery；需求方 2026-07-22 指示開卡
- Design：N/A——只研究資料與產品邊界；若要新增 `/records` 使用者流程另過 Design Gate

## 研究決策

- 確認 `/stats/hr` 是否有穩定 endpoint／年份／賽制／事件 key，能否提供既有資料沒有的逐轟里程碑。
- 將 `/standings/history`、`/standings/special`、`/stats/toplist`、`/teamhistory` 分類為
  canonicalization、regression oracle 或 public dataset；`/stats/mvp` 預設 NO-GO（既有資料重複）。
- 評估一次性／低頻 audit 是否足夠，避免把低價值頁面加入每日 Playwright。

## 驗收

- 所有頁面列出真實 endpoint、token、參數值域、stable key、資料粒度、重複來源與反爬成本。
- `/stats/hr` 至少抽查跨年、同場多轟、球員改名與季後賽，證明 event identity 可重跑。
- 產出逐頁 Go／No-Go；只有產品價值與資料契約同時成立才開後續 ingest 卡。
- 主站探測遵守白天、低頻、失敗冷卻與斷路器紅線。

## Log

- 2026-07-22 register by GPT-5@Codex（依 ruan6047 指示）；iteration 0。
