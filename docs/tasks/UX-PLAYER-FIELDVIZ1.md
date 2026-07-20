# UX-PLAYER-FIELDVIZ1 球員守備守位分布圖〔T3；⚪一般〕

- 需求：ruan6047　規劃：Claude（Opus 4.8）　分支：`ai/<執行者>/UX-PLAYER-FIELDVIZ1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋UX-PLAYER-IA1
- DB：`db_scope: none`（純前端，讀現有 `/fielding` 端點）　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`UX-PLAYER-FIELDVIZ1-BRIEF.md`](../design/UX-PLAYER-FIELDVIZ1-BRIEF.md)
- Discovery：沿用 UX-PLAYER-IA1（守備現況只有數字表，看不出守備範圍與兼守）
- Design：Design Brief 待需求方核可

## 目標與驗收

- [ ] 在 L4 生涯層守備區以球場示意圖呈現守位分布，一眼看出主守位與兼守；圖在表之上（結論先行）。
- [ ] 本季與生涯以同一張圖表達（外圈＝本季、實心＝生涯），**不得新增本季／生涯切換**——UX-PLAYER-SECTIONS1 才剛移除該切換。
- [ ] 純投手、多守位、退役（僅生涯）、無守備資料四情境皆正確；375 px 不溢出；SVG 具 `role="img"` 與描述主守位的 `aria-label`，數值仍由既有表格提供非視覺替代。

## 驗證與依賴

- 驗證：元件測試（守位→座標映射、面積比例、空態）、真實瀏覽器四情境走查、`tsc`、`build:check`。
- 依賴：**UX-PLAYER-SECTIONS1 合併後才可 claim**——同持 `file:web/src/app/players/[id]/**`，資源互斥須序列化。
- 預估範圍：S（單一元件＋映射表，無 API 變更）。
- 非目標：逐年守位變遷堆疊圖（需 API 加 `scope=yearly`，另卡）；分項明細圖表化（樣本量誤導風險，需獨立 Design）。
