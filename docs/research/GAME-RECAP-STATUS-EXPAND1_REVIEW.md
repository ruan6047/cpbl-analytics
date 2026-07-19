---
title: GAME-RECAP-STATUS-EXPAND1 獨立查核報告
date: 2026-07-20
tags:
  - game-recap
  - review
  - data-correctness
status: approved
---

# GAME-RECAP-STATUS-EXPAND1 獨立查核報告

相關文件：[[GAME-RECAP-STATUS1_REVIEW]]、[[GAME-RECAP-STATUS1_RESULTS]]、[[GAME-RECAP-STATUS-EXPAND1]]

- **Reviewer**: Antigravity (T4 Reviewer)
- **模型家族**: Gemini 3.5 Flash (High)
- **執行者**: GPT-5@Codex
- **日期**: 2026-07-20
- **固定 source SHA**: `7a4476cc959907acd8c079688bccbef8bcc33ff2`
- **基準分支**: `main`
- **任務卡**: [`docs/tasks/GAME-RECAP-STATUS-EXPAND1.md`](../tasks/GAME-RECAP-STATUS-EXPAND1.md)
- **VERDICT**: **APPROVE**
- **P0/P1/P2 Findings**: 0 (無)
- **是否可合併**: **是 (Can merge)**

---

## 1. 聲明與查核方法

- **獨立 review worktree**: 本次查核於獨立的 review worktree (`/Users/ruanruan/Dev/cpbl-analytics-review-expand1`) 進行。
- **唯讀資料庫操作**: 所有涉及本地 PostgreSQL 資料庫的驗證操作（例如手動觸發 `migrate()` 及 `\d` 描述），均為獨立唯讀驗證，未對主分支代碼或 control plane 檔案造成任何 write 污染。
- **無分支修改**: 本查核者明確聲明，未對被審之 source branch `ai/gpt-5-codex/GAME-RECAP-STATUS-EXPAND1` 進行任何修改或推送。

---

## 2. 審核要點核對

| 審核要點 | 判定 | 具體證據與分析 |
|---|---|---|
| **1. Migration 性質** | ✅**PASS** | `061_game_source_revisions.sql` 新建了 `game_source_revisions` 與 `game_schedule_status_revisions` 兩表。不含任何 `DROP TABLE` 或是修改既有 Table 的行為，完全為 **additive**，且在 existing DB 重跑時順利執行，具備**冪等性**。 |
| **2. Schedule raw 完整保存** | ✅**PASS** | `record_schedule_revisions()` 完整提取了 `PresentStatus`、`GameResult`、`GameDate`、`PreExeDate`，生成穩定的 payload hash 作為 version，並將 raw JSON payload 透過 `sanitize_detail` 保存於 `raw_payload` 中，完美覆蓋原始排程變動軌跡。 |
| **3. 四大來源 outcome 互斥記錄** | ✅**PASS** | 在 `cpbl_gamelog.py` 的 `scrape_gamelogs()` 中，針對 `scoreboard` 與 `livelog` 連線失敗、JSON 損毀、抓取正常但內容為空、以及正常內容等，均互斥且分別記錄其 outcome 為 `available|missing|error`。在 `cpbl_advanced.py` 中亦同樣封裝了 `AdvancedScrapeResult` 分別處理其 available/missing/error 狀態。 |
| **4. 重跑去重與內容異動保留** | ✅**PASS** | 兩表 UNIQUE 約束均綁定 business keys (sno、source、source_version/payload_hash)。在 Python 代碼寫入衝突時使用 `ON CONFLICT DO UPDATE` 更新 `last_seen_at` 與遞增 `seen_count`，不插入重複 revision 列；當 payload 異動導致 hash/version 改變時則會成功插入一筆新的 revision 歷史，符合稽核要求。 |
| **5. 敏感資訊遮蔽與長度限制** | ✅**PASS** | `sanitize_detail()` 遞迴遮蔽 `password`, `secret`, `token`, `api_key` 等敏感字串為 `[REDACTED]`。且限制外部字串長度最長為 `500` 字元，list 最長限 `50` 個元素，徹底杜絕敏感資訊洩漏與巨量 HTML 塞爆資料表之風險。 |
| **6. 歷史狀態推定 final 檢查** | ✅**PASS** | 程式碼與 migration 均**未**進行任何 active 狀態映射，亦未觸及歷史 `games` / `livelog` 表的 values，無任何「錯把未知歷史狀態推定成 final」的行為，符合 fail-closed 設計。 |
| **7. Advanced 誠實 aggregate 標記** | ✅**PASS** | `run_refresh_recent.py` 呼叫 `_record_advanced_revisions()` 記錄進階數據 revision 時，明確設定 `game_level_complete = False`，且標明 `"scope": "season_player_aggregate"`，誠實宣告其為球員年度 aggregate 數據，不假裝具備 game-level 到齊能力。 |
| **8. Ingest 異常細分** | ✅**PASS** | `cpbl_gamelog.py` 的 try-except 與 JSON parser 均針對：HTTP 狀態非 200 (`http_XXX`)、解析錯誤 (`invalid_response_json`/`invalid_source_json`)、空資料 (`missing`) 以及連線異常 (`request_error`) 進行了精細的 outcome/error_code 區分與記錄。 |
| **9. Fresh DB / 失敗重試安全性** | ✅**PASS** | 新增之雙表自帶 primary keys, index, check constraints，且 migration 與 ingest 寫入語句皆具備冪等處理，重跑與重試完全可靠。 |
| **10. 測試覆蓋度** | ✅**PASS** | `tests/test_game_source_revisions.py` 包含 9 個測試用例，全面覆蓋：重整 JSON keys 穩定度、遮蔽與截斷、0-0 完賽與 schedule entry 歷程、livelog 與 scoreboard 分開/解析失敗處理、Http failure 錯誤記錄、以及 advanced 數據 aggregate 屬性設定。 |

---

## 3. 唯讀 SQL 驗證與本機測試

### 3.1. 測試套件執行結果
- 執行專屬測試：
  ```bash
  uv run pytest tests/test_game_source_revisions.py
  ```
  **結果**: `9 passed in 3.14s`

- 執行完整 Pytest 套件：
  ```bash
  uv run pytest
  ```
  **結果**: `348 passed, 1 skipped, 1 failed in 31.11s`
  *(註：唯一失敗之 `test_scheduled_checker_reports_running_state` 為已知與本分支無關的時間相依 baseline failure，已在乾淨 main 分支重現。)*

### 3.2. Migration 安全性驗證
在本地 PostgreSQL 實體 (Port 5433) 執行：
1. 升級至最新 migration 成功：
   ```bash
   uv run python -c "from cpbl.db import migrate; migrate()"
   ```
   **結果**: 順利執行，兩新表與 indices/constraints 成功創建。
2. 重跑（冪等性驗證）：
   ```bash
   uv run python -c "from cpbl.db import migrate; migrate()"
   ```
   **結果**: 執行成功，無任何重複建立錯誤，驗證重跑完全可靠。

---

## 4. 稽核結論

本分支 `ai/gpt-5-codex/GAME-RECAP-STATUS-EXPAND1` 之交付成果：
1. 資料模型、重跑安全性及冪等性皆符合 T4 資料正確性標準。
2. 錯誤細分、敏感資訊遮蔽與大小限制皆處理得當，無資料洩漏或部署風險。
3. 測試覆蓋率高且指標全部通過。
4. 本查核者予以 **APPROVE**，此變更可安全合併至 `main`。
