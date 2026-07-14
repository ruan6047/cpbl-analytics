# BUG-VENUE-ALIAS 球場列表遺漏歷史桃園使用年份 〔⚪一般〕

- 重現：在修復前呼叫 `GET /api/v1/venues?season=2026`，查看「樂天桃園」的 `first_year` 與 `last_year`。環境：本機 PostgreSQL 17，既有 2010–2026 一軍賽事資料。
- 預期 vs 實際：同座球場的歷史名稱應合併，樂天桃園應顯示 2010–2026；修復前聚合直接以 `games.venue` 分組，僅顯示 2022–2026，2010–2021 的「桃園」資料未併入。
- 根因：`/api/v1/venues` 的本季使用統計與歷年首末年份聚合未套用既有球場別名規則；球場詳情 API 已將「桃園」→「樂天桃園」及「亞太副場」→「亞太副」。
- 修復：兩個聚合均使用相同 SQL `CASE` 歸一化；回歸測試：[tests/test_venue_factors.py](../../tests/test_venue_factors.py) `test_venue_list_sql_normalizes_historical_aliases`（修復前 ImportError/缺少歸一化查詢，修復後通過）。
- 需求：ruan6047　執行：GPT-5@Codex　查核：Opus-4.8@Claude Code（≠ 執行）　分支：`fix/venue-list-alias-normalization`
- 部署：是　環境：production　PR：—　Merge SHA：`8410875`
- 狀態住 [`../TASKS.md`](../TASKS.md) Ledger

## 查核範圍

1. 檢查 [teams.py](../../src/cpbl/api/routers/teams.py) 的兩個聚合都以相同別名規則分組，且不改變 `kind_code='A'` 與完成比賽篩選。
2. 執行 `uv run pytest`、`uv run ruff check`。
3. 在本機 DB 以 `TestClient` 呼叫 `/api/v1/venues?season=2026`，驗證「樂天桃園」的 `first_year == 2010`、`last_year == 2026`。
4. 確認 diff 僅含此修正與回歸測試，且沒有敏感資訊。

## Log

- 07-14 實作 by GPT-5@Codex → ✅：commit `5fb0760`；`pytest` 68 passed、`ruff` 通過，真 DB API 實測樂天桃園為 2010–2026。
- 07-14 合併狀態核實 by GPT-5@Codex → ⚠️：`5fb0760` 已在 `8410875` 納入 `main`，但尚無獨立查核紀錄；此卡維持待事後查核，不得視為已通過。
- 07-14 交接 by GPT-5@Codex → 🔍待查核：使用者將另指派獨立審核者。
- 07-14 事後查核 by Opus-4.8@Claude Code → ✅通過：
  - 別名前提**獨立驗資料**（非只讀 code）：`桃園` 2010–2021 與 `樂天桃園` 2022–2026 逐年零重疊 →
    確為冠名改名，合併正確。對照組 `台中` 與 `洲際` 在 2010–2013 **並存** → 係兩座球場，未被誤併。
  - 行為驗證：本機 DB 跑 `_VENUES_DIM_SQL(2026)` → 樂天桃園 `first_year=2010`（修復前 2022），682 場併入。
  - `ruff` 通過、`pytest` 68 passed；diff 僅含修正與回歸測試，無敏感資訊；`kind_code='A'` 與完成場篩選未變。
  - 附帶清理（commit 見下）：別名規則原本被複製成第三份（`teams._NORM_GAME_VENUE`），已改為 import
    `venues._NORM_VENUE` 單一來源——此 bug 的成因正是「某處漏了正規化」，再增一份拷貝會重演。
  - `亞太副場` 分支在此 SQL 為死碼（該名僅存在二軍 kind D，兩子查詢皆篩 kind A）；無害，與 `venues.py` 對稱保留。
  - 順帶發現（**不屬本卡**，建議另開卡）：`台中`（老台中球場）有 1120 場一軍（1990–2013）但無 `venue_dim` 列
    （官網 `/field` 無該頁，見 `ingest/cpbl_field.py:26`），故 `/venues` 完全不顯示此球場。是否為已拆除球場補
    dim 列屬產品決策。
