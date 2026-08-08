# DOC-G4-FREEZE-STALE1 修正 G4 觀測凍結過期陳述與可重跑掃描　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：DATA-INCOMPLETE-BOX-INGEST1-R1-02 @ merge_sha a1b54d8d927bae36e2c915b463277f734726b495
- DB：db_scope=none　資源：`scripts/data_tz_boundary1.py`、`src/cpbl/completion.py`、`tests/test_tz_boundary.py`、`tests/test_cli_help_guard.py`、`docs/tasks/DEV-CLI-HELP-GUARD2.md`、`docs/tasks/DATA-TZ-BOUNDARY1.md`、`docs/research/DOC-G4-FREEZE-STALE1/`
- 服務的原始目標：文件不得與權威來源矛盾，否則下一個執行者會依過期陳述誤判自己不能動碼
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DOC-G4-FREEZE-STALE1），不重複於此檔。

## 核心痛點

- **痛點**：docs/AI_WORKFLOW.md:26 寫「G4 凍結中，收窗後修」、docs/tasks/DATA-TZ-BOUNDARY1.md:19 寫「鏈端只記錄不改——G4 觀測凍結」，但權威來源 docs/tasks/INGEST-GAME-TM-REFACTOR1-G4.md L21/L362 明載 Gate 3 已於 2026-08-03（第 9 天、run_id=14）依需求方裁示提前收窗、凍結範圍解除。文件與權威來源互相矛盾，讀者無從判斷哪一份為準；#113 的執行者即因此在動鏈端碼時缺少對齊依據，由查核者以 DATA-INCOMPLETE-BOX-INGEST1-R1-02 指出

## 驗收條件

- [ ] 兩處陳述改為與權威來源一致；權威來源為 INGEST-GAME-TM-REFACTOR1-G4.md，修改時須引用其行號作為依據
- [ ] 不得只刪掉「凍結中」三個字了事：AI_WORKFLOW.md:26 剩下的「cpbl-refresh-recent 連 --help 都會觸發每日鏈」仍然為真且該修法現已解除阻塞，須明確寫出當前狀態（限制仍在／阻塞已解除）而非留下語意殘缺的句子
- [ ] DATA-TZ-BOUNDARY1.md:19「鏈端只記錄不改」已被 #113 實際推翻（run_refresh_recent.py 已改），須反映此事實並說明該卡的鏈端範圍現在如何處理
- [ ] 全庫掃一次同類過期陳述：grep 「G4」「凍結」「收窗後」等詞，把命中結果逐條判定為仍有效／已過期，artifact 由指令輸出產生而非人工列舉
- [ ] `data_tz_boundary1.py` 不再把 ingest 全域標成 `chain_frozen`，artifact 改以「待 #53 G4 Phase B」表達鏈端延後原因
- [ ] 修正 completion 與 CLI／時區測試的過期理由層敘述；保留「UTC 上界保守」與「CLI 仍有副作用」的既有結論
- [ ] 全庫掃描 artifact 與可重跑指令落在 `docs/research/DOC-G4-FREEZE-STALE1/`，每個命中都帶判定與理由

## 驗證

- [ ] grep -rn 「凍結」 docs/ 的前後對照，逐條標註處置
- [ ] uv run ruff check＋uv run pytest；不執行任何 crawler CLI 或 DB 寫入
