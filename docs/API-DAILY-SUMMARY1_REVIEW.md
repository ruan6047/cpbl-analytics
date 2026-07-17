# API-DAILY-SUMMARY1 查核報告 — 最近比賽日與下一批賽事聚合契約

> 卡：[docs/tasks/API-DAILY-SUMMARY1.md](file:///Users/ruanruan/Dev/cpbl-analytics/docs/tasks/API-DAILY-SUMMARY1.md)
> 被審分支：`ai/opus-4-8/API-DAILY-SUMMARY1`
> Worktree：`.claude/worktrees/api-daily-summary1-execution`
> Handoff SHA：`0af9a06` (依 commit log：`0af9a06 chore(control-plane): hand off API-DAILY-SUMMARY1 for review`)
> 查核基準：`0af9a06`
> 查核者：Antigravity (Gemini 3.5 Flash)
> 對照規格：[docs/PRODUCT_UX_BLUEPRINT.md](file:///Users/ruanruan/Dev/cpbl-analytics/docs/PRODUCT_UX_BLUEPRINT.md) §5.1、§8.1、§8.4

## 結論：APPROVE (核可)
建議 Coordinator 進行 merge。實作完全對齊 spec 的語意與紅線，在測試覆蓋率、三軸正交性、唯讀限制與查詢預算上表現優異。

---

## 驗收條件逐條審查

### 1. 唯讀 contract 與查詢預算
- **狀態**：**PASS**
- **證據**：
  - [src/cpbl/api/routers/daily.py:L160-208](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L160-208)
  - **說明**：
    1. 首頁載入基本資訊時（不帶 season 且 pregame 缺席），會固定執行 4 次唯讀 SQL 查詢（日期界線查詢、最新賽日與下一批賽程場次查詢、30天內未定案 unresolved 場次查詢、最新數據刷新日誌查詢）。
    2. 當 outcome_simple 模型可用且有未來的一軍例行賽（kind_code="A"）時，[src/cpbl/api/routers/daily.py:L214](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L214) 會執行額外 1 次 `load_outcome_rows(completed_only=False)` 從 `game_features` 讀取特徵，總計 5 次唯讀查詢。
    3. 全程使用 Python 內存對應（Memory Lookup），沒有發生命名 N+1 查詢或隱藏的 DB round-trip。
    4. 測試 [tests/test_daily_summary.py:L375-387](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/tests/test_daily_summary.py#L375-387) 已腳本化驗證查詢次數預算（`cursor.queries` 長度為 4 且不含寫入 keyword）。

### 2. 休兵日、延賽與刷新落後之推導
- **狀態**：**PASS**
- **證據**：
  - [src/cpbl/api/routers/daily.py:L243](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L243)
  - [src/cpbl/api/routers/daily.py:L253](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L253)
  - **說明**：
    1. 不依賴「昨天/今天」硬寫，日期由資料庫中 `games` 的實際日期推導。
    2. 下一批賽事以相對於當前系統時間之天數差 `days_from_as_of` 計算呈現（例如，2026-07-18 時，下個比賽日為 2026-07-21，其距離為 3 天）。
    3. 延賽場次在 DB 更新日期後作為 `next_slate` 呈現，且比分正確設定為 `None`，不以 0-0 顯示。
    4. 過去日期但仍無比分的場次，皆不會被視為完賽，而是作為 `unresolved_games` 輸出，且 status 標為 `"unknown"`，作為 fail-closed 的維運警示。

### 3. 模型缺席與 WPA 解耦
- **狀態**：**PASS**
- **證據**：
  - [src/cpbl/api/routers/daily.py:L102-114](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L102-114)
  - **說明**：
    1. 當 `outcome_simple.joblib` 缺席（如 `artifact_missing`）或損毀（如 `error`）時，仍正常回傳下一批賽程，只會將 pregame 的 status 分別置為 `"artifact_missing"` / `"error"`，且其勝率 `home_win_probability` 與訊號 `signals` 均為 `null`，不回傳 50% 假數字。
    2. 契約無 any `WPA` 相關欄位，與 WP 曲線等功能完全解耦。

---

## 🔴 紅線與語意檢查

### 1. 未完成場次比分一律 null + completed:false
- **狀態**：**PASS**
- **證據**：
  - [src/cpbl/api/routers/daily.py:L77-79](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L77-79)
  - **說明**：若 completed 為 `false`，強制將 `home_score` 與 `away_score` 清洗為 `None` (null)，防範 DB 的佔位符 0–0 被前端錯誤解讀為比分。

### 2. completed = 有比分 且 game_date 不在未來
- **狀態**：**PASS**
- **證據**：
  - [src/cpbl/api/routers/daily.py:L74](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L74)
  - [src/cpbl/api/routers/daily.py:L166](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L166)
  - **說明**：
    二軍「保留賽」（例如 `delay_kind='保留'`，排在未來的補賽時段，但帶有先前中斷時的比分）在此規則下，因為其 `game_date > as_of`，將正確判定為 `completed: false` 且比分被置為 `null`。最新比賽日不會因此跳入未來。
    實測 `kind_code=D` 時成功排除未來保留賽之干擾（例如 D#164, D#165 雖為 2026-07-17 但為未完成場次，並未計入 `latest_game_day`，且 `latest_game_day` 停留在 `2026-07-16`）。

### 3. availability 三軸正交
- **狀態**：**PASS**
- **證據**：
  - [src/cpbl/api/routers/daily.py:L256-260](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L256-260)
  - **說明**：
    三軸為 `schedule`、`results`、`pregame_model`。各自有 status 和 reason。
    - `schedule` 值域包含 `available`、`season_complete`、`source_missing`。
    - `results` 值域包含 `available`、`not_started`、`source_missing`。
    - `pregame_model` 值域包含 `available`、`artifact_missing`、`error` 等。
    三者各自分立、語意明確。

### 4. fail closed / fail fast 穩健性
- **狀態**：**PASS**
- **證據**：
  - [src/cpbl/api/routers/daily.py:L85-98](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L85-98)
  - **說明**：
    1. 資料庫層失效不捕捉，錯誤直接拋出（HTTP 500），以避免回傳空陣列被誤讀為「今日無賽事」。
    2. `_last_refresh` 中若 `cpbl.refresh_log` 缺表則 status 為 `source_error`，無紀錄則為 `unknown`，不會宣稱新鮮。

### 5. 首頁不放區間與 model signals 處理
- **狀態**：**PASS**
- **證據**：
  - [src/cpbl/api/routers/daily.py:L133-141](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L133-141)
  - **說明**：
    1. Payload 中不含區間 (interval) 欄位。
    2. API 原樣提供預測模型的語意群訊號（strength, suppression 等），由前端 `PregameCard` 自行挑選排序，不在 API 端做排序邏輯。

### 6. STATUS1 字彙對帳
- **狀態**：**PASS**
- **證據**：
  - [src/cpbl/api/routers/daily.py:L8-10](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/src/cpbl/api/routers/daily.py#L8-10)
  - **說明**：
    聚合端點並未定義 `official_game_status` / `play_by_play_availability` / `wp_availability` 等欄位，欄位乾淨度高，與未來之 GAME-RECAP-STATUS1 設計完全無衝突。

---

## 🔍 Findings
**共 0 筆** (P0-P2 嚴重度缺陷皆為 0 筆)

---

## 🛠️ 驗證指令與實際輸出

我們在 worktree 中執行了下列指令：

### 1. `uv run ruff check`
```
All checks passed!
```

### 2. `uv run pytest tests/test_daily_summary.py tests/test_route_snapshot.py -q`
```
............................                                             [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/api-daily-summary1-execution/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
28 passed, 1 warning in 1.45s
```

### 3. API 回應大小與查詢數測量
- 請求：`GET /api/v1/daily/summary?kind_code=A`
  - 大小：`2.1 KB`
  - 查詢數：`4 次` (因本機模型未建置，pregame 顯示 `artifact_missing`)
- 請求：`GET /api/v1/daily/summary?kind_code=D`
  - 大小：`3.0 KB`
  - 查詢數：`4 次` (二軍 pregame 顯示 `unsupported`)
