# VENUE-DEFUNCT 歷史 CPBL 球場納入球場維度〔🔴資料正確性〕

> 卡名沿用既有 ID；產品名稱改為「歷史 CPBL 球場」，不以拆除與否分類。

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/gpt-5-codex/VENUE-DEFUNCT`
- 執行：GPT-5@Codex　查核：待重新獨立查核（須 ≠ 執行）
- worktree：`/private/tmp/cpbl-analytics-VENUE-DEFUNCT`
- DB：`db_scope: schema`；`db_namespace: VENUE_DEFUNCT`；`migration_phase: expand`；migration `059_historic_cpbl_venues.sql`
- DB resources：`db:local:VENUE_DEFUNCT`、`db:local:VENUE_DEFUNCT:table:venue_dim`、`container:cpbl-venue-defunct-db`、`port:55433`
- 清理／回復：fresh rehearsal container 採 `--rm`；migration 可重跑，且只補齊既有 NULL 規格欄位
- 部署：否　環境：local rehearsal　PR：—　Merge SHA：—

## 需求

讓曾舉辦 CPBL 一軍例行賽、但本季未使用的球場出現在 `/venues`，並能開啟一個誠實的規格／歷史頁。首例是逐場資料的 `台中`（1990–2013；1,120 場），其規格頁既有 `國體` 對應但尚未套進一軍球場歸一化。

## 事實與來源

- `台中` 是位於臺中市雙十路一段 16 號的臺中棒球場，並非洲際棒球場；CPBL 官方場地頁提供容量、座位、外野距離與地址。
- 官方資料：<https://cpbl.com.tw/field/cont?sid=0M062382190802773937>（容量 8,500；內／外野 5,500／3,000；340／400／340 呎）。
- 台灣棒球維基與維基百科佐證其位於臺體大旁、2013 下半季後未再舉辦 CPBL 例行賽；此卡不宣稱場地已拆除。
- 維基百科記載 2006 改建後的 325／400／325 呎，與官方現頁衝突；本卡的單值 `venue_dim` 以 CPBL 官方現頁為準，不主張它代表任何指定歷史年份。

## 範圍與做法

1. 將 `台中` 歸一為既有 canonical key `國體`，套用於球場列表、球場因素與詳情請求的別名處理；保留 `games.venue` 原始值，不做資料覆寫。
2. 新 migration 以官方資料冪等 seed `國體` 的完整規格，確保未執行球場爬蟲的新環境也能列出該場地。
3. `/venues` 的歷史球場卡一律可點擊；歷史頁在無 2018+ 逐場資料時仍顯示規格與 CPBL 一軍使用年份，並清楚揭露「無球場因素／打擊環境可用資料」，不以 404 隱藏。
4. 不新增「已拆除」欄位；`last_year < 當前賽季` 僅表示本季未使用，不推論場地營運狀態。

## 不在範圍

- 不以維基資料覆寫 CPBL 官方規格，亦不建立改建前後的版本化規格資料表。
- 不將 2018 年前資料補算為 Park Factor 或打擊環境。
- 不處理其他場地，除非資料庫比對後能由 CPBL 官方或同級來源確認其 canonical 對應與規格。

## 驗收

1. `台中` 在所有球場歸一化 SQL 與 `_canon()` 皆解析為 `國體`。
2. migration 重複執行後，`國體` 具完整官方規格且不覆寫既有非空爬取值。
3. `/api/v1/venues` 對本機既有資料回傳 `國體`，其一軍使用年份含 1990–2013，且不再另列 `台中`。
4. `/venues/國體` 在無 2018+ 分析資料時仍回 200，顯示規格、使用年份與「逐場分析資料自 2018 年起」限制。
5. `uv run ruff check`、`uv run pytest` 與 `cd web && npx tsc --noEmit` 通過。

## 查核重點

- 確認 `台中` 與 `國體` 的地址、官方頁與 games 年份資料一致，不可只憑名稱合併。
- 確認畫面未稱其已拆除或仍營運，只陳述 CPBL 一軍使用年份與資料可用性。
- 檢查 migration 的 `ON CONFLICT` 不會用 seed 覆寫球場爬蟲已取得的資料。

## Log

- 2026-07-15 實作 by GPT-5@Codex：`台中 → 國體` 已套用於列表／詳情／球場因素的 canonical 規則；新增官方規格 migration 與歷史規格頁。
- 自測：`uv run pytest` 123 passed、`uv run ruff check` 通過、`cd web && npx tsc --noEmit` 通過。
- 本機 PostgreSQL 實測：migration 後 `國體` 為容量 8,500、340／400／340 呎；`games.venue='台中'` 為 1990–2013 共 1,120 場一軍例行賽，`/api/v1/venues?season=2026` 回傳同一 canonical 項目。
- 2026-07-16 查核退回：升級為 T4 資料正確性紅線卡；修正前端別名、來源錯誤降級與空白選手區塊後再送獨立查核。
- 2026-07-16 修正驗證：fresh PostgreSQL 17 隔離容器連續執行 59 個 migrations 兩次皆通過；第二次 `coach_history` 已為 view（`relkind='v'`），`059` seed 為 `國體` 8,500 人、340／400／340 呎。
- 前端驗證：Node 純函式回歸 5/5、`tsc --noEmit`、`build:check` 通過；Chrome DevTools 實測 `/venues/台中` HTTP 200，畫面顯示「臺中棒球場」與 1990–2013，API request 已改送 canonical `國體`。console 僅既有缺少 `favicon.ico` 的 404，與本卡無關。
- 2026-07-16 人工 T4 復審固定 SHA `099bc298`：APPROVE，P0–P2 findings 歸零。non-fast-forward merge `876a70b`；GitHub Actions CI run `29512142200` 全綠後封存，worktree 與本地／遠端分支均已清理。
