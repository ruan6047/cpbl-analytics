# UX-MODEL-METHOD1 模型方法與限制頁〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/UX-MODEL-METHOD1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.14、§6、§7
- Discovery：舊 `/predict` 混合產品互動與模型教育　Design：需求方核可 `/methodology` 不佔主要導覽、由模型 badge deep-link

## 目標與驗收

- [ ] `/methodology` 依賽前勝率、WP、PA 結果分布、matchup credibility、推定球種分段，逐項列問題、期間、baseline、validation、限制與版本。
- [ ] 所有已上線模型 badge 可 deep-link 至穩定 anchor；「模型敏感度區間」與非信賴區間紅線一致。
- [ ] no-go、研究保留與尚未通過 gate 的模型不產生公開能力暗示，頁面在模型 artifact 缺席時仍可讀。

## 驗證與依賴

- 驗證：內容事實查核、anchor／鍵盤／mobile 走查、`tsc`、`build:check`。
- 依賴：只引用已核可模型報告；不等待未來 Stuff+／projection。
- 預估範圍：M。
