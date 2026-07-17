# UX-TEAM-FOCUS1 球隊頁本季現況優先〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/UX-TEAM-FOCUS1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.8
- Discovery：球隊頁本季資訊與隊史長內容競爭首屏　Design：本季→攻守→隊史三層

## 目標與驗收

- [ ] 首層呈現本季戰績與走勢、最近／下一場、關鍵球員；第二層對戰、主客場、攻守；隊史置第三層。
- [ ] TEAM-STYLE 未通過研究 gate 前不放球風分數；應援文化與主題日沒有 DATA-EDITORIAL1 實際資料前不放 UI 占位。
- [ ] 與 standings 不重複整張表，既有隊史與年份 deep-link 保留，mobile／鍵盤可用。

## 驗證與依賴

- 驗證：六隊與歷史隊碼 fixture、資料缺漏、375 px／鍵盤走查、`tsc`、`build:check`。
- 依賴：UX-STANDINGS-FOCUS1 的責任邊界；不依賴 TEAM-STYLE1 或 DATA-EDITORIAL1。
- 預估範圍：M。
