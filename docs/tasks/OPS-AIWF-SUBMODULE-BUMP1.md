# OPS-AIWF-SUBMODULE-BUMP1 把 .ai-workflow submodule 從落後 135 個 commit 的 gitlink 推進到現行 origin/main　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=none
- 服務的原始目標：狀態面的寫入通道要是現行的，且上下游之間要有可通行的路
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：OPS-AIWF-SUBMODULE-BUMP1），不重複於此檔。

## 核心痛點

- **痛點**：狀態面的唯一寫入通道停在 135 個 commit 前，於是上游修好的東西到不了這裡、這裡的實務也升不上去

## 驗收條件

- [ ] bump 後既有八個動詞（open／assign／deploy-declare／deploy-state／handoff／review／doctor／snapshot）行為不退化：每一個都要有實際呼叫的證據，不接受「碼還在」當證明。上游 cli/src 變動 6,981 行、其中 review.py +825、validation.py +534，屬行為面不是純測試
- [ ] 上游新增的 amend／checkpoint 兩個動詞：確認它們不會在既有流程被意外觸發，且說明本專案要不要用。checkpoint 在上游文件與 CI 零命中
- [ ] bump 前後對同一張測試卡跑完整生命週期（open→assign→handoff→review→handoff release），逐步比對寫入的欄位與留言格式是否相同。差異逐項列出並判定可接受與否

## 驗證

- [ ] uv run ruff check + uv run pytest；wfcli 自身的測試（上游新增約 3,700 行 cli/tests）須在 bump 後跑過
- [ ] gitlink 推進後，docs/ROADMAP.md:19 引用的 52839f0 應變為可抵達（該 commit 晚於現行 gitlink，是 #140 標為不可抵達的原因）
