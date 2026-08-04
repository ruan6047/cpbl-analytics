# DEV-STALE-GUARD-TESTS1 cutover 遺留守衛測試對封存卡恆紅　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code（PM 祕書）
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=none
- 服務的原始目標：CI 綠燈恆真——守衛語意跟上 cutover 後的狀態面（決議 7 的收尾）
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-STALE-GUARD-TESTS1），不重複於此檔。

## 核心痛點

- **痛點**：test_task_card_sections.py 仍讀凍結的 TASKS.md 並要求每卡有 docs/tasks 檔，但七張 🛑 封存卡檔案已依決議移入 archive——origin/main 全庫 pytest 恆定 1 failed，PR #85 的 api job 連帶無法全綠

## 驗收條件

- [ ] 該測試認得封存語意：🛑/🏁 列的檔案允許在 docs/archive/tasks/（或整測試明確退役並附理由——凍結快照不再演化，守衛對象已消失）
- [ ] origin/main 基底全庫 uv run pytest 零 failed
- [ ] 順手盤點其他仍讀 TASKS.md/docs/tasks 的守衛測試，列清單不修（逐一標註 cutover 後語意是否仍成立）

## 驗證

- [ ] 本機全庫 pytest 前後對照
- [ ] PR CI api job 全綠 run URL
