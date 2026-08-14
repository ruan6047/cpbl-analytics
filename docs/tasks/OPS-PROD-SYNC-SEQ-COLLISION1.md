# OPS-PROD-SYNC-SEQ-COLLISION1 生產同步的 identity 序列每日被拉回本機 max，撞上 prod 自己配過的 id　〔T4〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：scripts/refresh-cpbl-prod.sh 的 sync_revision_table() 與其上方「已知且刻意接受的副作用」註解 @ 9e4b4ea；實測證據見本卡留言
- DB：db_scope=schema
- 服務的原始目標：本機爬到的資料要能可靠地到達生產，且失效時不得每日靜默復發
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：OPS-PROD-SYNC-SEQ-COLLISION1），不重複於此檔。

## 核心痛點

- **痛點**：2026-08-14 10:22 起每日鏈的同步階段固定失敗（exit=3，game_source_revisions_pkey duplicate key），生產資料自 2026-08-13T02:36Z 起停止更新且每日復發。機制：sync_revision_table() 插入時刻意不帶 id、讓 prod 自行配號，但 _stage 的 pg_dump --data-only 會一併輸出該表 identity 序列的 setval，把 prod 的序列拉回本機當前 max。腳本註解已載明此副作用並判為無害，理由是 prod 對這兩表從不自行 INSERT 且正確性不依賴 id——該假設會失效：每日 setval 到 local_max 後 prod 由該點續號，prod 自己的 max 因此逐日爬升；一旦超過本機（實測 prod max=18590 vs local max=18056、prod 1203 列 vs local 1218 列），隔日 setval 拉回低點就撞上 prod 過去配過的號。任何事前的一次性 setval 都無效，因為 pg_dump 的 setval 在同一批 payload 內、位於 INSERT 之前——PM 已於 2026-08-14 實測驗證此點（setval 至 18590 後執行仍失敗於同一號）

## 驗收條件

- [ ] 修法必須讓「事前修正被 payload 內的 setval 蓋掉」這條路徑消失，而不是每次人工補 setval。三個候選方向（濾掉 staged dump 的 setval 行／INSERT 之後才 setval 且設為 prod 自己的 max／這兩表不走 pg_dump 暫存）由執行者比較後提案，需求方裁定
- [ ] 既有列不得刪除或改寫。prod 現有 1203 列與 local 1218 列的內容差集須先量出來——兩者列數不同，修好序列不代表內容一致
- [ ] 同型表一併檢視：game_schedule_status_revisions 走同一個函式，目前 seq 領先 max（18308 vs 18138）故未撞，但機制相同。須說明它為何尚未失效、以及修法是否同時涵蓋
- [ ] 依藍圖 §4 對目標 1／2 的加嚴：除證明本次修好，還要以回放或 fault injection 證明同型失敗會被擋下——例如構造 prod max > local max 的情境，確認修法後仍能同步
- [ ] 不得以「重跑一次就好」結案：本缺陷每日復發，修法要能證明明日的排程會通過

## 驗證

- [ ] 修法後實跑一次 SKIP_SCRAPE=1 的同步並確認 /api/info 的 last_refresh 追上；artifact 由指令輸出產生
- [ ] uv run ruff check + uv run pytest；scripts/ 的改動須有測試（scrape-daily.sh 已有 17 個 case 的假 repo 手法可沿用）
