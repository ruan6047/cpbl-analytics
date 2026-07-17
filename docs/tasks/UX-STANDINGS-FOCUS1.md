# UX-STANDINGS-FOCUS1 戰績頁競爭脈絡收斂〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/UX-STANDINGS-FOCUS1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.4
- Discovery：現況 standings 同時承擔戰績、特殊紀錄與歷史資料　Design：競爭位置為唯一核心問題

## 目標與驗收

- [ ] 首層只保留全年／上下半季、勝差、近況、連勝敗、季後賽脈絡與一張走勢圖；特殊紀錄移至合適頁面。
- [ ] 主客場、月份、對戰各隊採進階展開；未驗證季後賽機率不得出現。
- [ ] 年份與歷史戰績查詢零退化，375 px 不依賴整頁水平捲動。

## 驗證與依賴

- 驗證：歷史年份對照、狀態／表格／圖表測試、375 px／鍵盤走查、`tsc`、`build:check`。
- 依賴：無；完成後可提供 UX-TEAM-FOCUS1 的入口與責任邊界。
- 預估範圍：M。
