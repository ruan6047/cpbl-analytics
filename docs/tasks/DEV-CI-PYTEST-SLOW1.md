# DEV-CI-PYTEST-SLOW1 CI pytest 結構性慢（763s vs 本機 30s）調查　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code（PM 祕書）
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=none
- 服務的原始目標：CI 回饋速度——required check 上線（OPS-CODE-BRANCH-PROTECT1）前消除結構性等待
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-CI-PYTEST-SLOW1），不重複於此檔。

## 核心痛點

- **痛點**：無 DB 的 CI 環境疑逐測試等待連線逾時才 skip：Pytest step 兩輪高度一致 ~763s（本機 ~30s）；api 設為 required check 後每張 PR 都付 12 分鐘回饋延遲

## 驗收條件

- [ ] 以逐測試計時證據定位慢源（哪些測試各花多久、等待什麼）
- [ ] 修法實測 CI Pytest step 時間顯著下降並附前後 run URL 對照
- [ ] 不放寬任何測試語意；skip 條件維持等價

## 驗證

- [ ] uv run pytest -q 本機全綠
- [ ] 真實 CI run 前後對照
