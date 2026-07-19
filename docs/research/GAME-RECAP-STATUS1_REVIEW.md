---
title: "GAME-RECAP-STATUS1 獨立查核報告"
card_id: GAME-RECAP-STATUS1
status: review-approve
date: 2026-07-20
tags:
  - cpbl
  - game-recap
  - data-correctness
  - review
links:
  - "[[GAME-RECAP-STATUS1]]"
  - "[[GAME-RECAP-STATUS-EXPAND1]]"
  - "[[GAME-RECAP-DATA1]]"
---

# GAME-RECAP-STATUS1 獨立查核報告

- **Reviewer**: Antigravity (T4 Reviewer)
- **執行者**: GPT-5@Codex
- **日期**: 2026-07-20
- **固定 source SHA**: `11a90dcf4a0d1d3d441a0d14f6330d53bd4a6cb2`
  *(註：使用者要求所給之 `11a90dc54e8cfed756a73e721ce4e1c76a6122be` 於 Git tree 中不存在，但其前 7 碼與本分支上之實際 commit SHA `11a90dcf4a0d1d3d441a0d14f6330d53bd4a6cb2` 吻合，故以此 commit 作為固定查核標的。)*
- **稽核分支**: `ai/gpt-5-codex/GAME-RECAP-STATUS1`
- **VERDICT**: **APPROVE**
- **P0/P1/P2 Finding 數量**: 0 (無)

---

## 1. 聲明與查核方法

- **獨立 review worktree**: 本查核工作是在獨立的 review worktree (`/Users/ruanruan/Dev/cpbl-analytics-review-status1`) 進行。
- **唯讀資料庫操作**: 所有涉及本地資料庫的驗證操作，均使用 PostgreSQL 的 `READ ONLY` transaction / `SELECT` 語句，未進行任何寫入或結構變更。
- **無分支修改**: 本查核者明確聲明，未對被審之 source branch `ai/gpt-5-codex/GAME-RECAP-STATUS1` 進行任何修改、提交或推送。
- **未修改控制檔**: 未對 [docs/control-plane/events.jsonl](file:///Users/ruanruan/Dev/cpbl-analytics/docs/control-plane/events.jsonl) 或 [docs/TASKS.md](file:///Users/ruanruan/Dev/cpbl-analytics/docs/TASKS.md) 進行任何修改。

---

## 2. 必查項目逐項判定

### 2.1. present_status 證據
- **判定**: **PASS**
- **詳細分析**:
  - 經唯讀 SQL 查詢驗證，在 2018–2026 年、`kind_code` 為 `A`、`C`、`D`、`E` 的範圍內，`cpbl.games` 的 `present_status` 確實**只觀測到值 `1`**，共 4,675 場。
  - 在這 4,675 場中，比分不為 `0-0` 的場次（即具有活動證據）共 4,252 場，而比分為 `0-0` 的場次共 423 場。
  - 對這 423 場進行追蹤，發現它們在 `cpbl.game_livelog` 與 `cpbl.game_scoreboard` 中**完全沒有任何數據**。這 423 場包含了：
    - `delay_kind='延賽'`：21 場
    - `delay_kind='保留'`：1 場
    - 未開打或被取消之未來賽事（`delay_kind` 為 NULL）：401 場
  - **結論**: 上述證據非常充足，足以反駁 `present_status = 1` 等同 `final` 的假設。如果系統誤以 `present_status = 1` 作為完賽判斷，將會錯誤地把大量未開打的未來賽事或延賽/保留賽判定為 `final`。

### 2.2. 官方狀態保存
- **判定**: **PASS**
- **詳細分析**:
  - 回源審查 [cpbl_site.py](file:///Users/ruanruan/Dev/cpbl-analytics/src/cpbl/ingest/cpbl_site.py)，其中在 `_primary_entry` (L89-93) 選取主記錄時：
    ```python
    played = [e for e in entries if _i(e.get("PresentStatus")) == 1]
    pool = played or entries
    return max(pool, key=lambda e: (_parse_date(e.get("GameDate")) or date.min))
    ```
    此處僅依據 `PresentStatus=1` 優先與最新日期選取單一排程列，將同一個 `game_sno` 的所有 entries 聚合為一。
  - 在 `_delay_meta` (L96-107) 中，整個排程歷程中的 raw `GameResult` 確實只被濃縮成 `delay_kind` (保留/延賽) 與 `orig_date` (原始日期) 兩個摘要欄位。
  - 同場比賽的多筆 schedule revision 歷程**完全沒有被持久化**，直接在 `upsert_games` 聚合時被捨棄。
  - **結論**: 目前的系統與資料庫結構**無法**可靠地追溯原始歷程，亦無法區分 `scheduled`、`final`、`postponed`、`cancelled`、`unknown` 等官方詳細狀態，fail-closed 為 `unknown` 的判定正確。

### 2.3. play-by-play freshness
- **判定**: **PASS**
- **詳細分析**:
  - 審查 [016_game_log.sql](file:///Users/ruanruan/Dev/cpbl-analytics/migrations/016_game_log.sql)，`game_scoreboard` 與 `game_livelog` 表的欄位定義中，**確實缺少** `fetched_at`、`source revision / payload hash`、取得結果 (`outcome`)、`error` 與 `completion marker`。
  - **結論**: 在沒有這些 row-level freshness 標記的現況下，確實無法在資料庫層面區分以下情境：
    - (a) 有 scoreboard、無 livelog (官網本就無資料，例如部分二軍場次)
    - (b) 尚未 refresh
    - (c) 官網確實沒有資料 (例如因雨延賽)
    - (d) 單場來源抓取出錯
    - (e) 整批 refresh 成功但單場缺漏 (例如爬蟲中途被節流)

### 2.4. refresh_log 能力
- **判定**: **PASS**
- **詳細分析**:
  - 審查 [015_refresh_log.sql](file:///Users/ruanruan/Dev/cpbl-analytics/migrations/015_refresh_log.sql) 與 [run_refresh_recent.py](file:///Users/ruanruan/Dev/cpbl-analytics/src/cpbl/ingest/run_refresh_recent.py)。
  - `refresh_log` 確實只記錄了整批執行的日期區間 (`from_date`, `to_date`)、總場次 (`games_total`)、已完成場次 (`games_completed`) 及 aggregate jsonb detail。
  - 當遇到抓取失敗時，它會記錄整批狀態 `ok = False`；當有賽程未完成時，它會在 `note` 寫入一條文字警示。
  - **結論**: `refresh_log` 屬於**整批 (batch) 層級的粗粒度日誌**，沒有 single-game 級別的追蹤，因此**完全不足以**用來為單場產生互斥的 `pending_refresh`、`source_missing`、`source_error`。

### 2.5. advanced freshness
- **判定**: **PASS**
- **詳細分析**:
  - 審查 [017_advanced_stats.sql](file:///Users/ruanruan/Dev/cpbl-analytics/migrations/017_advanced_stats.sql) 與進階數據爬蟲 [cpbl_advanced.py](file:///Users/ruanruan/Dev/cpbl-analytics/src/cpbl/ingest/cpbl_advanced.py)。
  - `advanced_stats` 表為球員年度 aggregate 數據，其 `updated_at` 只是該列 (球員在該年度/賽制/角色的累計進階指標) 的最後寫入更新時間。
  - **結論**: `updated_at` 無法用以指明某一場特定比賽的進階數據是否已經到齊。在缺乏 game-level 官方完成訊號的限制下，`advanced_freshness` 應保持 `unknown`，不可由球員累計更新時間代理。

### 2.6. EXPAND1 提案
- **判定**: **PASS**
- **詳細分析**:
  - 審查 [GAME-RECAP-STATUS-EXPAND1.md](file:///Users/ruanruan/Dev/cpbl-analytics/docs/tasks/GAME-RECAP-STATUS-EXPAND1.md) 提案，其對 schema 和 ingest instrumentation 的規劃確實有其必要性。
  - 提議的 `game_source_revisions` 與 `game_schedule_status_revisions` 新表，至少保存了：
    - Game key, source, raw `PresentStatus`, raw `GameResult`, `fetched_at`, source version/hash, outcome (`available|missing|error`), row_count, sanitized error.
  - 提案中明確考慮了「同一 payload 重跑不產生重複 revision」、支援 revision 去重、解決晚到資料、失敗重試、以及歷史未知資料的邊界。
  - **無錯誤吸收**: 提案特別標明了邊界，不實作也不吸收 `GAME-RECAP-PA1` 的 `tracking_availability`，亦不吸收 `GAME-RECAP-WP-API1` 的 `wp_availability`。
  - **結論**: EXPAND1 提案範圍非常乾淨，能為 STATUS1 後續的 API mapping 提供可審計的 raw 數據支持。

### 2.7. 驗收案例支援度
- **結論**: **PASS**。EXPAND1 提案的 additive 雙表設計可提供以下細粒度證據：
  - **0–0 完賽 / 延賽 / 取消 / 保留賽**: 藉由 `game_schedule_status_revisions` 完整記錄 raw `PresentStatus` 與 `GameResult` 歷程及 payload hash。
  - **有 scoreboard、無 livelog**: `game_source_revisions` 針對同一 game key 可分開記錄 `source='scoreboard'` 為 `available`，與 `source='livelog'` 為 `missing`。
  - **refresh 成功但單場缺漏 / 來源錯誤**: `game_source_revisions` 中對該場的 outcome 記錄為 `error`，並附帶 `error_code` 與 `sanitized_detail`。
  - **advanced 資料晚到**: `game_source_revisions` 中對該場的 `source='advanced'` 記錄為 `available`，其 `fetched_at` 與實際入庫時間綁定，不依賴球員年度 updated_at。

---

## 3. 唯讀 SQL 驗證與結果

在 `docker-compose` PostgreSQL 容器內唯讀執行了以下指令以重現並驗證 DATA1 的審計數據：

### 3.1. 驗證 present_status 範圍
```sql
SELECT present_status, COUNT(*)
FROM cpbl.games
WHERE year >= 2018 AND year <= 2026 AND kind_code IN ('A', 'C', 'D', 'E')
GROUP BY present_status;
```
**輸出**:
```
 present_status | count
----------------+-------
              1 |  4675
```
*(證實 DATA1 稽核的 4,675 場全部 present_status 均為 1。)*

### 3.2. 驗證 0–0 賽事場次與活動證據
```sql
SELECT COUNT(*)
FROM cpbl.games
WHERE year >= 2018 AND year <= 2026 AND kind_code IN ('A', 'C', 'D', 'E')
  AND home_score = 0 AND away_score = 0;
```
**輸出**:
```
 count
-------
   423
```
*(證實 0-0 賽事共 423 場，活動賽事為 4,675 - 423 = 4,252 場。)*

### 3.3. 驗證 0-0 賽事是否完全缺乏 scoreboard 與 livelog
```sql
SELECT COUNT(DISTINCT (l.year, l.kind_code, l.game_sno))
FROM cpbl.game_livelog l
JOIN cpbl.games g ON l.year = g.year AND l.kind_code = g.kind_code AND l.game_sno = g.game_sno
WHERE g.year >= 2018 AND g.year <= 2026 AND g.kind_code IN ('A', 'C', 'D', 'E')
  AND g.home_score = 0 AND g.away_score = 0;
```
**輸出**:
```
 count
-------
     0
```
```sql
SELECT COUNT(DISTINCT (s.year, s.kind_code, s.game_sno))
FROM cpbl.game_scoreboard s
JOIN cpbl.games g ON s.year = g.year AND s.kind_code = g.kind_code AND s.game_sno = g.game_sno
WHERE g.year >= 2018 AND g.year <= 2026 AND g.kind_code IN ('A', 'C', 'D', 'E')
  AND g.home_score = 0 AND g.away_score = 0;
```
**輸出**:
```
 count
-------
     0
```
*(證實 423 場 0-0 賽事在 scoreboard 與 livelog 中均無任何資料。)*

### 3.4. 0–0 賽事的 delay_kind 分佈
```sql
SELECT delay_kind, COUNT(*)
FROM cpbl.games
WHERE year >= 2018 AND year <= 2026 AND kind_code IN ('A', 'C', 'D', 'E')
  AND home_score = 0 AND away_score = 0
GROUP BY delay_kind;
```
**輸出**:
```
 delay_kind | count
------------+-------
 保留       |     1
 延賽       |    21
            |   401
```
*(證實其中 401 場為未來賽事或取消賽事，但 present_status 依然是 1，證實 present_status 判定 final 之謬誤。)*

---

## 4. 稽核結論與 Checkpoint 建議

1. **核可「STATUS1 先不做 API，改由 EXPAND1 補 instrumentation」**:
   - **完全核可**。現行資料模型確實不足以安全提供 STATUS1 API。強行提供 API 將會依賴比分、日期或空陣列等不可靠的副作用進行狀態推測。
2. **允許需求方認領 `GAME-RECAP-STATUS-EXPAND1`**:
   - **允許**。此提案界限清晰，專注於 additive schema 與 raw revision 的收集，是解決當前 row-level freshness 缺口與狀態審計的唯一正確途徑。
3. **無 Finding 合格**:
   - 被審的 branch 交付物 [GAME-RECAP-STATUS1_RESULTS.md](file:///Users/ruanruan/Dev/cpbl-analytics/docs/research/GAME-RECAP-STATUS1_RESULTS.md) 忠實反映了資料庫與程式碼現況，無任何虛構宣稱，無 P0/P1/P2 findings。本查核報告予以 **APPROVE**。
