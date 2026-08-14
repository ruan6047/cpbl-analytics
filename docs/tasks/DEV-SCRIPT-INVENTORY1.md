# DEV-SCRIPT-INVENTORY1 腳本清冊：分清常設工具與卡片一次性產物，讓「這支還能不能跑」看得出來　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=none
- 服務的原始目標：要跑的東西看得出來是什麼、還活不活著
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-SCRIPT-INVENTORY1），不重複於此檔。

## 核心痛點

- **痛點**：約 94 個可執行入口沒有任何清冊，而卡片的一次性產物與常設維運工具從外面看長得一模一樣

## 驗收條件

- [ ] 產出清冊：scripts/ 的 47 支與 pyproject [project.scripts] 的 47 支 CLI 逐支列出用途、性質（常設工具／卡片一次性產物／已死）、以及判定依據。實測 47 支中 35 支未被任何文件提到過
- [ ] 常設工具與一次性產物在檔案系統上可分辨——目錄、命名、或檔頭標記擇一，不得只靠清冊（清冊會過期，而瀏覽 scripts/ 的人不會先讀清冊）
- [ ] 疑似重複的群組逐組裁定：至少 TM 四支、splits 三支、無自責分三支、player_bio 兩支，說明是真重複還是各有射程
- [ ] 已死的腳本本輪只標記不刪除。刪除是需求方的獨立裁定，且須先確認沒有文件或排程指向它

## 驗證

- [ ] 清冊須由指令自動產生，不接受人工聲明；未判定的項目要列出來不得靜默跳過
- [ ] uv run ruff check + uv run pytest
