# LIVE-SNAPSHOT-FIELDS1 canonical snapshot 保留官方既有欄位〔T3；⚪使用者可見資料〕

- 需求：ruan6047　規劃／執行：Claude Opus 5@Claude Code　查核：須跨模型家族且 ≠ 執行
- review_independence: [cross_family]
- 父卡：`UX-LIVE-GAME1`　spec 基線：`LIVE_GAME_PRODUCT_SPEC v1.1`（沿用父卡）
- DB：`db_scope: none`（只改 Redis snapshot 形狀與前端；不動 schema／migration）
- 部署：是（worker 與 web 皆隨 submodule bump）
- Design Gate：N/A；不新增頁面或狀態，只把官方本來就給的欄位接上既有呈現

## Discovery

父卡上線後 2026-07-31 夜間實測，需求方回報四項問題。以本機直連兩個官方站點比對原始
payload（`stats.cpbl.com.tw/api/proxy/v1/games/2026-A-234` 與主站 `/box/getlive`）後確認：
**多數問題不是資料不存在，是 `build_snapshot` 只挑 12 個欄位、其餘全丟。**

進階站原始 payload 有、canonical snapshot 沒有的：

- 隊伍層級 `Visiting/Home.HittingCnt`、`ErrorCnt`（實測統一 `ErrorCnt=1`，畫面卻顯示 0）
- 頂層 `WinningPitcher`／`LoserPitcher`／`Closer`／`MVP`（含 `YearlyCount`）
- `AccumulationScore`（球隊 W/L/T）、`Field`（球場）、`Referee`（裁判）、`SkipTrackman`

兩站落差（決定「賽中做得到什麼」的邊界）：

- **逐局 H/E 只有主站有**。主站 `ScoreboardJson` 給逐局 `HittingCnt`／`ErrorCnt`（統一失誤發生在
  第 1 局）；進階站 `InningScore` 只有 `{Seq, Score}`。故逐局 H/E 與「煮粥」在 snapshot 路徑
  **無法**取得，須 fail-closed，不得偽造。
- 主站專有、進階站無：打者 `ErrorCnt`／`IsMvp`／`RoleType`／`Lobs`／`GrandSlamHomerunCnt`／
  `GameWinningRbiCnt`；投手 `GameResult`／`IsCompleteGame`／`IsShoutOut`／
  `GameHigherSpeedPitch`／`SavePointCnt`。故完投、完封、最速球、滿貫、致勝打點賽中算不出來。
- 官方**沒有**預期勝率。`CurtGameDetailJson.XweData` 經查為 23 KB 的 URL-encoded 新聞內容，
  不是勝率資料。賽中 WP 須自行計算，屬另一張卡。

另查出 `BATTER_ALIASES` 有 3 個 key 的 snake 拼法與 `snake()` 實際輸出不符，導致賽中 box
的打點、觸身、盜壘整欄空白：`run_batted_incnt`→`run_batted_in_cnt`、
`hit_bypitch_cnt`→`hit_by_pitch_cnt`、`steal_base_okcnt`→`steal_base_ok_cnt`。
另有 3 個 key（`grand_slam_homerun_cnt`／`game_winning_rbi_cnt`／`hitter_uniform_no`）是主站
專有欄位，進階站永遠不會有，屬 dead entry。

根因共通點：父卡與 FIX1 的測試都用**手寫 mock**，而 mock 比真實 payload 更完整也更乾淨
（自行補了 `ErrorCnt`、把 `RunBattedINCnt` 寫成 `RunBattedIncnt`、自行給了 decisions），
等於用對契約的想像驗證對契約的實作。本卡一律改用**生產真實 payload 當 fixture**。

## 驗收條件

- [ ] worker `_team_snapshot` 保留隊伍層級 `hits`／`errors`；`build_snapshot` 保留
      `decisions`（勝敗投／救援／MVP 含本季次數）、`records`（W/L/T）、`venue`、`umpires`、
      `skip_trackman`。欄位一律 additive，缺值為 `None`，不得改動既有 key 的語意。
- [ ] 既有 Redis 中不含新欄位的舊 snapshot 仍可被前端正常渲染（向後相容），不得因缺欄位拋錯。
- [ ] 記分板 R/H/E 的 H 與 E 取自 snapshot 隊伍層級真值；實測 2026-A-234 應顯示
      統一 `E=1`（現況錯誤顯示 0）。逐局 H/E 維持 `null`，不得由總計回填。
- [ ] 賽中 box score 的打點、觸身、盜壘有值（修正 3 個 snake 拼錯）；3 個主站專有的
      dead alias 移除或註明其來源限制。
- [ ] DB 尚未補資料時，決勝資訊／MVP 改由 snapshot 提供；DB 有值時以 DB 為準（不倒退）。
- [ ] TrackMan 可用性改以官方 `skip_trackman` 判定，取代現行推測；賽中仍不呈現空好球帶。
- [ ] 進階站沒有的結論（逐局 H/E、煮粥、完投、完封、最速球、滿貫、致勝打點、個人失誤）
      在 snapshot 路徑一律不呈現，且**不得以「沒有」表述**——缺資料與值為零必須可區分。

## 驗證

- [ ] 測試 fixture 使用生產真實 payload（`tests/fixtures/stats_game_2026-A-234.json`），
      禁止手寫欄位名；新增一項測試以 fixture 的實際 key 集合檢核所有 alias 都對得上，
      使拼錯無法再靜默通過。
- [ ] 先跑紅：對修正前的 alias 與 E 計算跑新測試須失敗，修正後轉綠。
- [ ] `uv run ruff check`、`uv run pytest`、`cd web && npm test`、`npx tsc --noEmit`、
      `npm run build:check`、`git diff --check` 全數通過。
- [ ] 真實瀏覽器對生產 API 驗證：2026-A-234 顯示統一 E=1、打點／盜壘有值、決勝資訊完整；
      未開賽與賽中場次不出現任何主站專有結論。

## 紅線

- 不動 DB schema、migration 或既有 API 路由契約。
- 不從進階站缺的資料反推結論（例：不得由 `RoleType` 倒推預告先發、不得由總計回填逐局）。
- 缺資料一律 fail-closed 並與「值為零」區分呈現。
- 不在本卡做賽中 WP（官方無現成資料，屬新功能，另開卡）。

## Log

- 2026-08-01：父卡夜間實測後由需求方指示開卡。Discovery 以本機直連兩站原始 payload 完成；
  ②「無關勝負」假話已於 2026-08-01 02:00 的 refresh 同步後自然消失（DB 補齊 decisions），
  故本卡不含緊急止血，範圍為把官方既有欄位正式接上。
