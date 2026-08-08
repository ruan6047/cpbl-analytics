# DATA-TZ-BOUNDARY1 日期界線時區修正：CURRENT_DATE(UTC)→Asia/Taipei（AUDIT1 C12 殘項）　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：docs/research/DATA-RULES-AUDIT1_REPORT.md C12 節（a3b84b6）＋REMEDY1 helper 模式（0da7408）
- DB：db_scope=read
- 服務的原始目標：資料正確性——所有日期界線語意以 Asia/Taipei 為準
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-TZ-BOUNDARY1），不重複於此檔。

## 核心痛點

- **痛點**：DB CURRENT_DATE 走 UTC，台北 00:00–07:59 視「今天」為昨天——日期界線查詢在晨間窗口整批偏移一天（AUDIT1 C12 定案；含 1 個精確等值用點直接受影響）

## 驗收條件

- [ ] 全庫 SQL 盤點 CURRENT_DATE/CURRENT_TIMESTAMP/now() 日期界線用點（artifact 由指令產生），逐點分類：語意敏感／無害／鏈端凍結
- [ ] 語意敏感點改 (now() AT TIME ZONE 'Asia/Taipei')::date（沿 completion.py helper 模式）；C12 精確等值用點修復＋回歸
- [ ] 鏈端（`src/cpbl/ingest/`）用點：#113 已將 `run_refresh_recent.py` 的完成場判準改為共用 `completed_games_sql()`，故不再是「只記錄不改」；但該 helper 預設仍為 UTC，且 `cpbl_pitch_tracking.py` 仍有原始 `CURRENT_DATE` 用點。兩者的 Asia/Taipei 日界切換須以另行授權的鏈端實作卡處理；Gate 3 已於 2026-08-03 提前收窗並解除 G4 凍結，不能再以凍結作為延後理由（[`INGEST-GAME-TM-REFACTOR1-G4.md`](INGEST-GAME-TM-REFACTOR1-G4.md) L21、L362）。
- [ ] 回歸：晨間窗口語意測試不依賴牆鐘（注入時間或斷言 SQL 形態＋DB 端雙時區日期差驗證）
- [ ] uv run ruff check＋uv run pytest 全綠

## 驗證

- [ ] DB 一律唯讀；報告數字由指令輸出產生；與 DEV-CLI-HELP-GUARD1 寫入集互斥（api/models/features vs ingest/pyproject）可真平行
