# DOC-ENTRY-ROUTING1 入口文件的路由正確性：CLAUDE.md 指向的每一份文件都要存在、還活著、且描述為真　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=none
- 服務的原始目標：入口讀完之後，該知道的事實都找得到，且找到的每一份都還為真
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DOC-ENTRY-ROUTING1），不重複於此檔。

## 核心痛點

- **痛點**：新 session 只自動載入 CLAUDE.md，而它指向的路由沒有人在維護——藍圖進不去、封存的檔還在被導向

## 驗收條件

- [ ] CLAUDE.md 補上 docs/ROADMAP.md 的入口。該檔於 2026-08-15 merge，是目標排序、五條任務線與卡片執行規範的權威來源，而 CLAUDE.md 對它零命中——新 session 讀完入口永遠不知道它存在
- [ ] 修正指向已封存文件的路由。CLAUDE.md:5 寫「活卡 Ledger 見 docs/TASKS.md」，而 TASKS.md 開頭第一行即「本檔已於 2026-08-04 cutover 封存、不再重建、不再是投影」，現行狀態面是 GitHub Issues + Project #4
- [ ] 窮舉查核 CLAUDE.md 指向的全部文件：每一份是否存在、是否仍為現行、CLAUDE.md 對它的描述是否仍為真。須輸出自動產生的清單，不接受人工聲明

## 驗證

- [ ] 以 grep 抽出 CLAUDE.md 的全部文件指向，逐份驗存在性與現行性，輸出清單
