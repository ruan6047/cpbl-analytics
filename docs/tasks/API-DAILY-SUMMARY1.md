# API-DAILY-SUMMARY1 最近比賽日與下一批賽事聚合契約〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/opus-4-8/API-DAILY-SUMMARY1`
- 執行：Opus-4.8@Claude Code　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.1、§8.1、§8.4
- Discovery：現行首頁有 12 組請求與日期語意問題　Design：Design Gate N/A；本卡凍結唯讀聚合 contract

## 目標與驗收

- [x] 單一或最多 3 組唯讀 contract 回傳最近有資料的比賽日、下一批已排定賽事、來源 freshness 與正交 availability。
      → 交付**單一**端點 `GET /api/v1/daily/summary`（`routers/daily.py`）。
- [x] 休兵日、延賽、刷新落後、pending、unknown、source_error 不以 0–0 或昨天／今天硬推；年份與 kind 範圍明確。
- [x] 契約不耦合 WPA；賽前資料只提供 PregameCard 所需欄位，模型缺席時仍可回傳賽程。

## 契約摘要

`GET /api/v1/daily/summary?season=<int|省略>&kind_code=<A|D>`

| 區塊 | 內容 |
|---|---|
| `scope` | `season`（省略＝跨年度）、`kind_code`、實際查的 `kinds`（A→A/E/C）、`as_of` |
| `latest_game_day` | 最近**有結果**的比賽日 + 該日場次（比分＋`game_sno` 進入復盤）；無則 `null` |
| `next_slate` | `as_of` 起最早**尚無結果**的排定日 + `days_from_as_of` + 場次（含 `pregame`）；無則 `null` |
| `freshness` | `last_completed_game_date`、`last_refresh{at,ok,scope,hours_ago,status}`、`unresolved_games[]` |
| `availability` | 三軸正交：`schedule`／`results`／`pregame_model`，各有 `status` + `reason` |

值域：`last_refresh.status` ∈ fresh／stale／failed／unknown／source_error；`schedule` ∈
available／season_complete／source_missing；`results` ∈ available／not_started／source_missing；
`pregame_model` 與每場 `pregame.status` ∈ available／artifact_missing／unsupported／no_features／error。

語意決定（皆有測試守門）：

- **未完成場次比分一律 `null`＋`completed: false`**。DB 的 0–0 是佔位不是賽果，原樣送出等於邀請前端把它讀成 0 比 0。
- **無「昨天／今天」概念**：日期由資料推導；休兵日呈現為 `days_from_as_of` 距離而非空白。
- **延賽**：官網把場次改到新日期並保留 `orig_date`，故它屬於下一批賽事；過去日期仍 0–0 者進 `unresolved_games` 並標 `unknown`（fail closed）——`cpbl.games` 無法區分「刷新落後」與「延賽未更新」，正式定案留給 GAME-RECAP-STATUS1 的官方狀態。
- **DB 失效讓錯誤上浮（500）**，不回空陣列假裝沒有比賽。
- **首頁不含區間**：模型敏感度區間留在賽事頁／方法頁（§5.1）；`signals` 原樣給模型的四個語意群，挑哪一個當主訊號是 PregameCard（UX-OUTCOME-HOME）的產品決策，API 不替模型排序。

## 驗證與依賴

- 驗證：路由快照、contract／DB integration tests、查詢數與回應大小量測、`ruff`、`pytest`。
- 依賴：沿用 GAME-RECAP-STATUS1 的 availability 字彙；若其尚未凍結，先以不衝突欄位命名並在串接前對帳。
- 預估範圍：M；不觸發 refresh、訓練或任何寫入。

## Log

- 2026-07-17 claim（iteration 1）→ `ai/opus-4-8/API-DAILY-SUMMARY1` @ `.claude/worktrees/api-daily-summary1-execution`。
- 2026-07-17 執行完成 → 單一端點交付。STATUS1 字彙未凍結，故本卡欄位刻意避開其將擁有的
  `official_game_status`／`play_by_play_availability`／`advanced_freshness`／`tracking_availability`／
  `wp_availability`；**串接前對帳義務**：STATUS1 凍結後，`availability.results` 與
  `freshness.unresolved_games[].status` 應改引用其官方狀態，本卡不重做該判定。
- 2026-07-17 待辦（不在本卡動）：`docs/AI_RUNBOOK.md` §5 API 地圖尚未列入本端點——該檔在
  OPS-REFRESH1 的 lease 範圍內，故未修改（該表本為精選清單而非窮舉，`/records`／`/venues`／
  `/people` 等既有端點同樣未列）。待其 lease 釋放後補列。
