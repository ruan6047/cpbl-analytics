# DATA-REVISION-HASH-NOISE1 修正快照的版本雜湊含球季累計欄，使「新增列＝官方改判」的訊號失真　〔T4〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：母卡 DATA-BOX-REVISION-SNAPSHOT1（#109）之服務的原始目標原文；發現來源為 DATA-BOX-DEEP-SILENT-FAIL1（#131）規劃階段 Discovery 的範圍外回報（見 #131 issuecomment-5284769331）
- DB：db_scope=write
- 服務的原始目標：讓自責分／失分重建的殘餘不一致能歸因，而不是只能標記為不可判定（承接母卡 DATA-BOX-REVISION-SNAPSHOT1 之原始目標原文）
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-REVISION-HASH-NOISE1），不重複於此檔。

## 核心痛點

- **痛點**：box_revisions.py:120 的 content_hash = canonical_source_version(safe_payload) 對整列 sanitize 後的 PitchingJson 取雜湊，而該列含球季累計欄（TotalWins／TotalLoses／TotalInningPitched／TotalEarnedRunCnt 等）。任何投手在該場之後又上場，其累計欄即改變，重抓舊場次必定產生一列新版本——即使該場的 InningPitchedCnt／RunCnt／EarnedRunCnt 一格未動。因此「同一 (場,投手) 有多列＝官方改判過」這個判讀是失真的。實測：全表 972 列／968 個 (場,投手)，多版本者僅 3 個且全在 2026/D/97；逐列 diff raw_payload 後四個單場欄兩版完全相同，差異全在累計欄與時間戳——本表全史觀測到的真實單場改判次數為 0/968，而表面上看起來有 3 次。母卡 #109 的原始目標是「讓自責分／失分重建的殘餘不一致能歸因」，而歸因正是靠這個訊號；訊號髒了，該目標就不成立。近期放大風險：#131 的補抓（約 98 場）與每週深度重抓都會對舊場次重抓，每次都可能量產假版本列

## 驗收條件

- [ ] 先量化再決定修法：現行 968 個 (場,投手) 中，若改以單場欄（inning_pitched_cnt／inning_pitched_div3／runs／earned_runs）為雜湊輸入，會有幾列變成同版本？artifact 由指令輸出產生。若量化後發現影響極小或判讀其實可用，照實說並可建議不修
- [ ] 決定雜湊的語意邊界並寫出理由：哪些欄位屬「這一場的事實」、哪些屬「觀測當下的球季狀態」。判準要能套用到未來新增的欄位，不得只列舉現有欄位
- [ ] 既有 972 列不得刪除或改寫。若新語意會讓歷史列的版本判定改變，須以可查詢的方式標示新舊語意分界（例如版本欄或 as-of），不得讓同一張表混用兩種語意而無從分辨
- [ ] 依藍圖 §4 對目標 1／2 的加嚴：除證明本次修好，還要以回放證明同型失敗會被擋下——例如模擬一位投手累計欄變動後重抓同一場，確認不再產生新版本列
- [ ] 評估對 #131 的相依：#131 的補抓會對約 98 場重抓。本卡若先落地可避免量產假版本列；若後落地則需說明那批列如何處置。此相依由需求方於 Design Gate 排序，本卡不自行決定

## 驗證

- [ ] 以 2026/D/97 的 3 個多版本 (場,投手) 為回歸樣本，證明新語意下它們不再被判為改判，且四個單場欄的比對結論不變
- [ ] uv run ruff check + uv run pytest；新增行為須有測試釘住
