# DEV-CLI-HELP-GUARD2 models/features 六入口 --help 補修＋train×2 容器確認（GUARD1 續）　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：Issue #91 交付 artifact〈本卡資源邊界〉節（main 18a6146）
- DB：db_scope=none
- 服務的原始目標：工程安全——CLI 探索零副作用全覆蓋（`cpbl-refresh-recent` 仍有副作用；其逐球 writer 由 #53 G4 Phase B 資源佔用，另案處理）
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-CLI-HELP-GUARD2），不重複於此檔。

## 核心痛點

- **痛點**：GUARD1 範圍外 7 入口中 6 支（build-features/build-sabr/classify-pitches/train-outcome×2/train-pa-sim）--help 仍直接開跑主流程；train×2 於 host 缺 libomp 無法取證

## 驗收條件

- [ ] 六支入口沿用 cpbl.ingest._cli 護欄：--help/-h 零副作用、非法參數 exit≠0 不執行主流程；既有合法呼叫形式不變
- [ ] cpbl-train／cpbl-train-pitching 於容器內以密封探針取證（docker compose run；嚴禁無探針真跑訓練），有隱患一併修
- [ ] audit 工具重產前後盤點：未修入口 7→1（僅剩 `cpbl-refresh-recent`，仍有副作用且另案處理）
- [ ] 回歸測試併入 tests/test_cli_help_guard.py；#53 G4 Phase B 佔用檔零 diff

## 驗證

- [ ] uv run ruff check＋uv run pytest；容器取證輸出附交付報告
