# DEV-ROADMAP-GATE-DERIVED1 移除排程區塊的逐卡 Gate 覆寫，區塊只放機器導得出來的東西　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：母卡 DEV-ROADMAP-VERIFIER1（#133）的 R3-003 finding 與其服務的原始目標；#130 的 R3 阻塞 finding
- DB：db_scope=none
- 服務的原始目標：排程區塊只承載機器導得出來的事實，人寫的說明與必須與它一致的正文同屬一個擁有者
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-ROADMAP-GATE-DERIVED1），不重複於此檔。

## 核心痛點

- **痛點**：scripts/roadmap_lines.py 的 GATE_OVERRIDES 是硬編的逐卡說明文字，且優先於狀態導出，沒有到期或真實性來源。DEV-ROADMAP-VERIFIER1（#133）的 R3-003 已判為「Gate 欄的產品／治理設計問題」並轉 Backlog，而它在同一天就回來擋住 DOC-CPBL-ROADMAP1（#130）：GATE_OVERRIDES 中 DATA-BOX-DEEP-SILENT-FAIL1 那條寫「⏰ 2026-08-17 14:10 週跑後 7 場掉出 days_back=30 窗」，該事實已被 #131 的規劃階段 Discovery 推翻（days_back 是 CLI 位置參數非物理限制，且母體漏算 kind=A 的 9 場），而 #130 的正文已正確承認此例被推翻——同一份文件的權威敘述因此自相矛盾。#130 修不了它：那段文字住在 #133 的宣告資源，而手改 marker 區塊會讓 --check 失配（那正是驗證器該擋的事）。該覆寫寫於 2026-08-14 上午，同日下午即過期

## 驗收條件

- [ ] 移除 GATE_OVERRIDES，Gate 欄改為純由交付狀態導出。SCHEMA_VERSION 須遞增並說明理由
- [ ] 被移除的資訊不得憑空消失：#53「放行條件沒有量測工具」、#119「等 #53 結案」、#131「規劃階段先做唯讀查證」等內容是狀態導不出來的，須在報告中逐條列出並指明它們應改寫到哪裡（PM 判斷是 #130 §3 的正文，因為那是與它必須保持一致的敘述的同一個擁有者——但請自行評估此判斷）
- [ ] 既有 fail-closed 行為不得因移除覆寫而放寬：未知交付狀態仍須 fail closed（VERIFIER1-CONV-001 曾因覆寫先於驗證而被繞過）
- [ ] 不得改 docs/ROADMAP.md——那是 #130 的宣告資源。本卡只改腳本與測試；§3 正文的補寫由 #130 自行處理
- [ ] 不得以「保留覆寫但加到期檢查」代替移除：到期檢查需要一個真實性來源，而 Gate 文字的真實性來源就是需求方的判斷，無法機械驗證。若執行者認為有可機械驗證的方案，可提案但須說明其真實性來源是什麼

## 驗證

- [ ] 以 #130 分支上的 docs/ROADMAP.md 實跑 --check：移除覆寫後區塊內容會變，該分支的 §3 因此會失配——請說明 #130 應如何重生區塊，並確認 --check 在重生後通過
- [ ] uv run ruff check + uv run pytest；既有測試不得退步，移除覆寫相關的測試須說明為何移除而非放寬
