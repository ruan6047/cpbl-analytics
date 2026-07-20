# UX-PLAYER-SECTIONS1 球員頁分區內容遷移〔T3；⚪一般〕

- 需求：ruan6047　規劃：待 UX-PLAYER-IA1 核可骨架　分支：`ai/<執行者>/UX-PLAYER-SECTIONS1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋UX-PLAYER-IA1
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.7
- Discovery：沿用 UX-PLAYER-IA1　Design：依 UX-PLAYER-IA1 核可 prototype

## 目標與驗收

- [ ] 依核可骨架遷移現有模組，預設只呈現角色相關核心結論；未使用內容明確移除或收合，不複製資料請求。
- [ ] matchup、推定球種、Stuff+、projection 嚴守各自 gate；首版球員頁不提供 PA 模擬常駐入口。
- [ ] 打者、投手、雙棲與缺資料 fixture 在 desktop／375 px／鍵盤皆能穩定導覽，既有球員 deep-link 不破壞。

## 驗證與依賴

- 驗證：元件與路由測試、API request audit、瀏覽器走查、`tsc`、`build:check`。
- 依賴：UX-PLAYER-IA1；與 UX-MATCHUP2 序列化球員頁資源。
- 預估範圍：M；若遷移 map 超過 5 個共享檔，依區段再拆垂直卡。
