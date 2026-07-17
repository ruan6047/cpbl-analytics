# UX-UMPIRE-SCOPE1 裁判公開介面 NO-GO 收斂〔T4；🔴統計／資料正確性〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/UX-UMPIRE-SCOPE1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋ML-UMP1／2 NO-GO
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.12–§5.13；[`ML-UMP2_RESULTS.md`](../research/ML-UMP2_RESULTS.md)
- Discovery：兩輪代理帶敏感度翻轉，方向性產品不成立　Design：完全移除聯盟排行，`/umpires` 只作中性索引

## 目標與驗收

- [ ] 移除所有聯盟裁判排行、準確率排名、偏隊／送分／勝負影響語意；不得以「代理帶一致率」改名保留。
- [ ] 單場好球帶散點移至賽事頁的描述性區塊；`/umpires` 與個人頁只保留出賽、coverage、中性分布與 deep-link。
- [ ] 無 tracking／coverage 不足／來源錯誤各自退化，不把缺資料顯示為零影響或零誤判。

## 驗證與依賴

- 驗證：全站文案／consumer audit、無設備 fixture、375 px／鍵盤走查、T4 獨立查核、`tsc`、`build:check`。
- 依賴：單場散點區塊與 UX-GAME-RECAP1 序列化；不重啟 ML-UMP 研究。
- 預估範圍：M。
