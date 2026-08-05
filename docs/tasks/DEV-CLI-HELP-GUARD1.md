# DEV-CLI-HELP-GUARD1 scrape CLI --help 護欄＋ruff submodule 排除（工具鏈衛生）　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：Issue #90 R1 查核事故紀錄＋0da7408 merge 後 main
- DB：db_scope=none
- 服務的原始目標：工程安全——任何 CLI 以 --help/-h 探索必須零副作用；lint 訊號無雜訊
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-CLI-HELP-GUARD1），不重複於此檔。

## 核心痛點

- **痛點**：cpbl-scrape-pitches --help 把 --help 當位置參數直接開爬（2026-08-05 查核事故 +46 列）——CLI 探索本身就有副作用；另 .ai-workflow submodule 被 cpbl ruff 掃入produce假 findings

## 驗收條件

- [ ] 盤點 pyproject [project.scripts] 全入口 --help/-h 行為（靜態審碼產出清單 artifact；嚴禁以真跑爬蟲類 CLI 驗證）
- [ ] ingest/ 內手寫 argv 解析入口改 argparse 或等價護欄：--help/-h 零副作用、非法參數 exit≠0 且不執行主流程
- [ ] pyproject ruff 設定排除 .ai-workflow；主 checkout uv run ruff check 全綠
- [ ] 回歸測試：入口 parser 單測（不觸網不觸 DB）
- [ ] G4 凍結檔零 diff：run_refresh_recent.py、cpbl_pitch_tracking.py（在資源宣告 ingest/ 內但明文排除）

## 驗證

- [ ] uv run ruff check＋uv run pytest；非 ingest 入口若有同類隱患→列報告不修（回 PM）
