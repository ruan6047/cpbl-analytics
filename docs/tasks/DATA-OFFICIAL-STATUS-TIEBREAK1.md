# DATA-OFFICIAL-STATUS-TIEBREAK1 官方比賽狀態的決勝鍵改用內容欄位，不倚賴兩機各自任意配號的 id　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=read
- 服務的原始目標：同一筆事實在本機與生產必須得到相同答案，且該相同性要有結構理由
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-OFFICIAL-STATUS-TIEBREAK1），不重複於此檔。

## 核心痛點

- **痛點**：同一場比賽的官方狀態，本機與生產可能選到不同的列，而目前一致只是觀察不是保證

## 驗收條件

- [ ] 決勝鍵不含 id：games.py:147 的 DISTINCT ON (source) 最終決勝鍵改為內容欄位，兩機在相同資料下必得相同贏家
- [ ] 打平列須有窮舉證據：本機實測約 54 組 (last_seen_at, fetched_at) 完全相同，修法須說明這些組別在新決勝鍵下如何決定，不得只證明「目前一致」
- [ ] 跨機對帳：本機與生產逐場比對官方狀態贏家，差異須能被「生產落後 N 列」完全解釋，不得有無法解釋的分歧

## 驗證

- [ ] uv run ruff check + uv run pytest（路由快照：端點行為若變須同步 EXPECTED）
- [ ] 兩機唯讀對帳腳本輸出（不得以人工聲明代替窮舉證據）
