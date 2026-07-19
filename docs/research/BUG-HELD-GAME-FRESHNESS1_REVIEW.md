---
title: "BUG-HELD-GAME-FRESHNESS1 保留比賽 freshness 修正獨立查核報告"
card_id: BUG-HELD-GAME-FRESHNESS1
status: review-approve
date: 2026-07-19
tags:
  - cpbl
  - freshness
  - data-correctness
  - review
links:
  - "[[BUG-HELD-GAME-FRESHNESS1]]"
  - "[[held-game-freshness-fix]]"
---

# BUG-HELD-GAME-FRESHNESS1 保留比賽 freshness 修正獨立查核報告

- 查核卡：[`BUG-HELD-GAME-FRESHNESS1`](../tasks/BUG-HELD-GAME-FRESHNESS1.md)〔T4；🔴資料正確性〕
- 查核標的：分支 `ai/gpt-5-codex/BUG-HELD-GAME-FRESHNESS1`（head `5e1b7bf3775b621166c70c08429fe01ea706e41c`）
- 查核者：Antigravity（Gemini 3.5 Flash (High)）@Google DeepMind　執行者：GPT-5@Codex（跨模型家族，符合紅線獨立性 §3）
- 日期：2026-07-19　方法：單元測試 + 本地與生產資料庫唯讀對帳 + 腳本與 API 語意回源查核；未修改交付物。
- **結論：APPROVE（P0=0）。修復完全阻斷了帶有中止比分的未來保留賽對 freshness 指標的污染，對帳語意完全一致；測試已轉綠。**

---

## 0. 重現與根因確認

本地與生產 DB 在 2026 二軍（`kind_code='D'`）中皆存在 5 場未完成保留賽，其帶有中止比分且 `present_status=1`，但 `game_date` 位於未來（8月至9月）：
* 2026-08-08 (game_sno 119): 5-4
* 2026-08-09 (game_sno 97): 4-3
* 2026-08-22 (game_sno 118): 1-0
* 2026-08-30 (game_sno 117): 1-4
* 2026-09-15 (game_sno 165): 1-3

舊判定 `home_score + away_score > 0` 誤將其計為已完賽（completed），使 `last_game_date` 被推高至 `2026-09-15`，且本季已完賽場次多算 5 場（353 vs 348）。

---

## 1. 修正方案查核

本次修復建立最小完賽契約 `src/cpbl/completion.py`，規定必須比分 > 0 且日期不晚於觀測日（`game_date <= CURRENT_DATE`）：

1. **API routers info.py**：
   - 成功引入 `completed_games_sql()` 取代原有的 `home_score + away_score > 0`。
   - 本地執行 `/api/info` 實際調用結果回報 `last_game_date: '2026-07-16'` 及 `season_games_completed: 348`，成功將未來保留賽排除。
2. **生產同步腳本 `refresh-cpbl-prod.sh`**：
   - 使用 `COMPLETED_GAMES_SQL="$(uv run python -m cpbl.completion)"` 動態產生 SQL，嵌入對帳查詢。
   - 保證了 `sync gate` 與 API 內部使用的 SQL 完賽條件完全對齊，徹底消除「兩端錯得一致」的隱患。
3. **單元測試與回歸測試**：
   - 新增 `tests/test_completion.py` 與 `tests/test_api_contract.py` 相關測試，對正常完賽、延賽、未來保留賽、未來保留賽續完等情境建立完整 regression barrier。目前全數 PASS。

---

## 2. Consumer Inventory（盤點結論）

對於 codebase 中其餘 `home_score + away_score > 0` 舊判定的盤點結論如下：

| 消費模組 | 舊判定位置 | 風險評估 | 處置結論 |
|---|---|---|---|
| **API** | `api/routers/daily.py` (line 166) | 無 | **不受影響**：已有 `game_date <= as_of` 限制，語意上與 completion.py 等價。 |
| **API** | `api/routers/games.py` (line 65) | 低 | **STATUS1後修**：用於 /api/v1/games/recent，將在 `GAME-RECAP-STATUS1` 統一口徑。 |
| **API** | `api/routers/standings.py` (line 197/200) | 中 | **STATUS1後修**：用於 _half_progress 計算 clinch 剩餘場次，將在 `GAME-RECAP-STATUS1` 統一口徑。 |
| **Ingest** | `ingest/cpbl_gamelog.py` (line 271) | 低 | **STATUS1後修**：決定哪些 snos 需要下載 gamelog，待 `GAME-RECAP-STATUS1` 後修復。 |
| **Ingest** | `ingest/run_refresh_recent.py` (line 44/227) | 無 | **不受影響**：皆限制在 recent days 窗口中，不會受未來保留賽干擾。 |
| **ML** | `features/outcome.py` (line 144) | 無 | **不受影響**：僅處理歷史已結束賽季，不受未來保留賽影響。 |
| **ML** | `models/matchup.py` (line 175/267) | 無 | **不受影響**：用於計算歷史對戰基礎統計，不影響當前/未來賽況。 |
| **ML** | `models/run_umpire_impact.py` (line 169) | 無 | **不受影響**：用於歷史裁判影響力彙總。 |

---

## 3. 資料庫唯讀對帳實測證據

### 3.1 本地開發資料庫對帳
```sql
SELECT 
  (SELECT max(game_date) FROM cpbl.games WHERE home_score + away_score > 0) AS old_last_game,
  (SELECT count(*) FROM cpbl.games WHERE year = 2026 AND home_score + away_score > 0) AS old_comp,
  (SELECT max(game_date) FROM cpbl.games WHERE home_score + away_score > 0 AND game_date <= '2026-07-19'::date) AS new_last_game,
  (SELECT count(*) FROM cpbl.games WHERE year = 2026 AND home_score + away_score > 0 AND game_date <= '2026-07-19'::date) AS new_comp;
```
結果：
* `old_last_game`: `2026-09-15` | `old_comp`: `353`
* `new_last_game`: `2026-07-16` | `new_comp`: `348`

### 3.2 生產資料庫對帳（VPS root@45.76.100.29）
```bash
ssh root@45.76.100.29 "docker exec prod_pg psql -U app_writer -d alpha_db -c \"...\""
```
結果與本地完全吻合，證實生產環境與本地面臨相同的 5 場未來保留賽偏誤。

---

## 4. 驗收核可與後續流程指引

1. **Verdict = APPROVE (P0=0)**.
2. 此查核已成功解除紅線限制。
3. 後續將執行 rebase + merge 至 `main`，並啟動 `push-to-deploy` 主站 submodule 同步，更新生產環境服務與 verification gate。
