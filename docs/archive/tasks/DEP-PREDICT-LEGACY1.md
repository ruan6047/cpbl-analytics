# DEP-PREDICT-LEGACY1 舊預測體驗退場〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/DEP-PREDICT-LEGACY1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: none`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §7
- Discovery：自由選特徵／權重與任選兩隊模擬已不符固定語意模型　Design：replacement before removal

## 目標與驗收

- [ ] 稽核所有前端 consumer；新 UI 不再呼叫舊 features／evaluate／帶 features 的 matchups／simulate 互動。
- [ ] `/predict` 轉到 `/methodology#pregame` 或首頁下一批賽事的單一核可入口，導覽與站內連結無死路。
- [ ] API 是否退場依 consumer／相容性證據另行決定；本卡不得順手移除仍有使用者的 public contract。

## 驗證與依賴

- 驗證：`rg` consumer audit、路由／redirect 測試、瀏覽器走查、`tsc`、`build:check`。
- 依賴：`UX-GAME-HOME1`、`UX-MODEL-METHOD1` 已上線；PA 模擬不阻塞舊整場預測 UI 退場。
- 預估範圍：S–M。
