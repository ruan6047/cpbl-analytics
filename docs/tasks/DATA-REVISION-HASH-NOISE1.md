---
card_id: DATA-REVISION-HASH-NOISE1
tier: T4
db_scope: write
db_namespace: unassigned
db_resources:
  - db:local:cpbl
  - db:local:table:box_pitching_revisions
migration_phase: expand
related:
  - "[[DATA-BOX-DEEP-SILENT-FAIL1]]"
---

# DATA-REVISION-HASH-NOISE1 修正快照的版本雜湊含球季累計欄，使「新增列＝官方改判」的訊號失真　〔T4〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：母卡 DATA-BOX-REVISION-SNAPSHOT1（#109）之服務的原始目標原文；發現來源為 DATA-BOX-DEEP-SILENT-FAIL1（#131）規劃階段 Discovery 的範圍外回報（見 #131 issuecomment-5284769331）
- DB：db_scope=write
- 服務的原始目標：讓自責分／失分重建的殘餘不一致能歸因，而不是只能標記為不可判定（承接母卡 DATA-BOX-REVISION-SNAPSHOT1 之原始目標原文）
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-REVISION-HASH-NOISE1），不重複於此檔。

## 現行資料庫宣告

`docs/DATABASE_CONTRACT.md` §3 要求的四個欄位已補於本檔 frontmatter，填法理由如下。

`db_namespace: unassigned`：沿用 `DATA-INCOMPLETE-BOX-INGEST1`（#113）經查核者判定保留的
先例。本卡尚未取得 `db:local:cpbl` lease，規劃階段全程唯讀；填 `shared-lease` 會錯誤宣稱
已可寫入共享資料庫。**不可**改填 CARD_ID 專屬 DB：驗收條件第 3 條與「驗證」節的回歸樣本
（2026/D/97 的 3 個多版本 PK）都必須在共享 local `cpbl` 的既有 1001 列上驗證，專屬空庫沒有
這些列。進入執行階段前，PM／Coordinator 須核發 `db:local:cpbl` lease 並把本欄改為
`shared-lease`。

`db_resources`：以「`record_box_pitching_revisions` 單一交易內實際會寫哪些表」為準逐項查證，
不抄開卡宣告。該函式自開一個 `conn()` 交易，交易內只有 `pg_advisory_xact_lock`（非表寫入）
與對 `cpbl.box_pitching_revisions` 的 UPDATE／INSERT。已排除三條會藏出額外表的路徑：
（1）`pg_trigger` 對該表 0 個非內部觸發器；（2）`pg_rules` 對該表 0 條 rule；（3）`pg_constraint`
只有 PK 與 `seen_count` CHECK，無外鍵串連。呼叫端 `cpbl_gamelog.scrape_gamelogs` 另外會寫
`game_scoreboard`／`game_livelog`／`batting_gamelog`／`pitching_gamelog`／`game_source_revisions`／
`game_detail`，但那些都在各自的 `conn()` 交易內、且不由本卡修改，故不列入本卡資源。

開卡時 issue 的 resource-claims 宣告為 `db:local:schema`；本檔改列 `db:local:cpbl`，理由是
contract §2／§3 的詞彙裡 migration lane lock 就叫 `db:<environment>:cpbl`，`db:local:schema` 不在
該詞彙表內。兩者指涉同一把全域鎖，不是放寬。**wfcli 開卡後不可改資源宣告（ai-workflow#12），
故 issue 上的字面維持原樣，以本檔為準的差異在此留痕。**

`migration_phase: expand`：驗收條件第 3 條要求「以可查詢的方式標示新舊語意分界（例如版本欄
或 as-of）」，這需要對 `box_pitching_revisions` 新增欄位，屬 additive DDL。⚠️ **這使本卡的實際
`db_scope` 應為 `schema` 而非開卡時宣告的 `write`**——contract §3 明訂 schema 是資料正確性紅線、
同一 `<environment, schema>` 只允許一個 migration writer。同樣受 ai-workflow#12 限制無法改
issue 字面，須由需求方於 Design Gate 裁定是否重開／升級後才可進執行階段。

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
