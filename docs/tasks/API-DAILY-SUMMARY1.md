# API-DAILY-SUMMARY1 最近比賽日與下一批賽事聚合契約〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/API-DAILY-SUMMARY1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.1、§8.1、§8.4
- Discovery：現行首頁有 12 組請求與日期語意問題　Design：Design Gate N/A；本卡凍結唯讀聚合 contract

## 目標與驗收

- [ ] 單一或最多 3 組唯讀 contract 回傳最近有資料的比賽日、下一批已排定賽事、來源 freshness 與正交 availability。
- [ ] 休兵日、延賽、刷新落後、pending、unknown、source_error 不以 0–0 或昨天／今天硬推；年份與 kind 範圍明確。
- [ ] 契約不耦合 WPA；賽前資料只提供 PregameCard 所需欄位，模型缺席時仍可回傳賽程。

## 驗證與依賴

- 驗證：路由快照、contract／DB integration tests、查詢數與回應大小量測、`ruff`、`pytest`。
- 依賴：沿用 GAME-RECAP-STATUS1 的 availability 字彙；若其尚未凍結，先以不衝突欄位命名並在串接前對帳。
- 預估範圍：M；不觸發 refresh、訓練或任何寫入。
