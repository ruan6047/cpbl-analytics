# 模型路由（可替換操作知識）

> 本檔是本專案的模型選擇事實來源；協作流程鐵律見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。模型名稱與可用性會變動，執行前以當前工具可選清單為準；不得以 `latest` alias 作為自動化依賴。

| 層級 | 適用 | 本專案慣例 |
|---|---|---|
| L1 經濟型 | 格式、文件搬移、驗證、爬蟲與同步 | Haiku 或等價 deterministic automation |
| L2 主力型 | 已知模式的 API／前端／遷移與一般 review | Sonnet 或等價主力模型 |
| L3 高階型 | 跨模組取捨、未知根因、架構與官網逆向 | Opus 或等價高階模型 |
| L4 特殊型 | 統計／ML 正確性、新演算法、難以察覺的決策 | Fable 或等價 frontier 模型；不取代跨家族／人工查核 |

## 路由規則

- 先依風險決定能力，再選供應商；紅線卡的 review 必須跨模型家族或人工。
- 答案唯一且可沿用既有模式時降級；跨檔、不可逆或錯誤難察覺時升級。
- LightGBM、資料庫 schema／資料 migration、Marcel baseline 與賽果／球員統計結論屬紅線；執行與 review 皆需實測證據。
- 部署、migration 轉態與格式檢查優先 deterministic automation；異常且根因不明時升至 L3。
- 每次對話開頭標示建議層級與原因；實際模型切換由使用者決定。
