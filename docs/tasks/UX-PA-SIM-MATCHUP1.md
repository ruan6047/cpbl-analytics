# UX-PA-SIM-MATCHUP1 Matchups 單一打席結果分布〔T4；🔴統計／ML〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/UX-PA-SIM-MATCHUP1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋ml-sim1-review
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.9、§6；[`ml-sim1-review.md`](../../ml-sim1-review.md)
- Discovery：PA 模擬能解釋單次對決但未改善整場 weighted-WP　Design：首版只進 `/matchups` 第二 tab「如果現在對決」

## 目標與驗收

- [ ] 只有選定具體打者×投手後可切入第二 tab，與歷史實績／EB 洞察清楚分離；UX-MATCHUP1 fail-closed 不被繞過。
- [ ] 顯示結果分布、輸入情境、模型版本與限制；不得包裝為整場勝負提升，區間不得稱信賴區間。
- [ ] unavailable、unsupported、artifact missing、API error 各自退化，且不產生替代機率或預設「天敵」。

## 驗證與依賴

- 驗證：固定 fixture 契約測試、文案紅線、校準／總和對帳、375 px／鍵盤走查、T4 跨家族或人工查核。
- 依賴：UX-MATCHUP1；不得順便建立真實打席入口。
- 預估範圍：M。
