# DATA-PA-REBUILD-GAP1 續賽場次的 PA 衍生表未隨自癒重建，且無任何對帳會發現　〔T4〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：docs/incidents/INCIDENTS.md 的 INC-2026-08-13-A（該檔於 DEV-ROADMAP-VERIFIER1 #133 分支 026a7cc，尚未 merge）；docs/ROADMAP.md §3「尚未開卡的已知問題」@ 9319be5
- DB：db_scope=write
- 服務的原始目標：被重抓覆蓋的比賽，其衍生資料必須跟著重建；沒跟上時要有東西發現
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-PA-REBUILD-GAP1），不重複於此檔。

## 資料庫宣告（`docs/DATABASE_CONTRACT.md` §3）

```yaml
db_scope: write
db_namespace: unassigned
db_resources:
  - db:local:cpbl
  - db:local:table:game_recap_builds
  - db:local:table:game_recap_source_revisions
  - db:local:table:game_plate_appearances
  - db:local:table:game_pa_events
  - db:local:table:game_pa_pitch_mappings
migration_phase: none
```

`db_namespace` 填 `unassigned` 而非契約 §3 詞彙表列的 `shared-lease`／`<CARD_ID>` 專屬 DB，
理由與 `DATA-INCOMPLETE-BOX-INGEST1`（該填法經查核者判定該保留）一致：本卡現為 `💡需求`、
規劃階段唯讀，**尚未取得 `db:local:cpbl` lease**；此刻填 `shared-lease` 等於宣稱已可寫入共享
local DB，是不實宣稱。取得 lease 時再改為 `shared-lease`，並於卡面 Log 留痕。
詞彙表缺少「已宣告會寫、但尚未核發 lease」這個狀態，屬 `ai-workflow#12` 的既有議題，
本卡不自行擴充詞彙表。

`db_resources` 較開卡留言多列三張表：`build_game()` 一次交易內除了 `game_plate_appearances`／
`game_pa_events`，還寫 `game_recap_builds`（`INSERT` + `state` 轉移）、
`game_recap_source_revisions`（`upsert_source_revision`，`pa_build.py:978`）與
`game_pa_pitch_mappings`（`_write_pas`，`pa_build.py:1323`）。漏列會讓 lease 的資源範圍
小於實際寫入面。

`migration_phase: none`：修法不新增／不變更 schema，只改目標挑選與對帳；若 Design Gate
選擇需要新欄位（例如在 `game_recap_builds` 上記錄「已知過期」旗標），須改為 `expand` 並補
migration 檔。

## 核心痛點

- **痛點**：2026/D/97 於 2026-08-09 續賽完成，games／pitching_gamelog／game_livelog 都由每日鏈自癒（比分 4:3 → 8:5、livelog 333 列），但 cpbl.game_pa_events 該場仍只有 32 個相異 pa_id。同量 livelog 的 2026/A 8 月完成場平均 68.6 個 PA。2026-08-13 人工盤點時發現（距續賽 4 日），2026-08-14 複驗仍未重建（距續賽 5 日）。非未掛載——run_refresh_recent.py:526 已有 _pa_build_step(..., include_farm=True)。最可能是 PA build 的目標挑選以『有沒有 PA 列』判斷而非『新不新』，已有列即跳過，但該假說未經驗證。全庫掃描範圍為 430 個完成場（A 250／D 180）：PA=0 者 0 場、PA 低於 livelog/8 者 1 場（即 D/97），故當前受害面為單場，但成因是機制性的，續賽場次再發生時會重現。D/97 的公開消費者包含賽況頁、recap、WP／WPA、關鍵打席與 ΔRE24，不是純內部資料

## 驗收條件

- [ ] 先驗成因假說再動手：『目標挑選以有無 PA 列判斷而非新不新』是 PM 未經驗證的推測。讀 _pa_build_targets 與 _build_pa_daily 確認實際條件，成因與推測不符就照實說，不得為了讓卡站得住而調整敘述
- [ ] 全庫掃描界定受害面，artifact 由指令輸出產生：目前判準為『PA 數低於 livelog/8』，該判準是 PM 憑一個案例定的啟發式，請自行檢視其偽陰性（例如 livelog 短但 PA 更短的場次會不會被漏掉）並在報告說明所用判準的依據
- [ ] 修法必須讓『被重抓覆蓋的場次其 PA 會跟著重建』成立，而不只是把 D/97 補回來。只補單場不算完成
- [ ] 依藍圖 §4 的加嚴：目標 1／2 的修復除了證明本次修好，還要以事故回放或 fault injection 證明同型失敗會被擋下——例如刻意讓一場的 livelog 增長後確認 PA 重建、或確認對帳會亮
- [ ] 重建 D/97 的 PA 前須確認不影響其消費者的既有數值語意（賽況頁、recap、WP／WPA、關鍵打席、ΔRE24）；PA builder 有版本紀律（見 pa-builder canonical 契約），版本要不要 bump 請判斷並說明

## 驗證

- [ ] 重建後 D/97 的 PA 數須落入同量 livelog 的合理區間，並與 game_plate_appearances 一致；對照組（其餘 429 場）不得因本次改動而變動，逐場比對 artifact 由指令產生
- [ ] uv run ruff check + uv run pytest；新增行為須有測試釘住
