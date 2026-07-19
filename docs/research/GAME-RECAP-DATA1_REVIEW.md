# GAME-RECAP-DATA1 獨立查核報告

- 查核卡：[`GAME-RECAP-DATA1`](../tasks/GAME-RECAP-DATA1.md)〔T4；🔴資料正確性〕
- 查核範圍：[`GAME-RECAP-DATA1_RESULTS.md`](GAME-RECAP-DATA1_RESULTS.md)、[`scripts/audit_game_recap_data.py`](../../scripts/audit_game_recap_data.py)、[`tests/test_game_recap_data_audit.py`](../../tests/test_game_recap_data_audit.py)
- 查核者：Claude（Opus 4.8）　執行／撰寫者：GPT-5@Codex（跨模型家族，符合紅線獨立性）
- 日期：2026-07-19　方法：唯讀重跑抽樣（另寫獨立 SQL，未複用被稽核腳本的函式）＋比對三套現行分組重現 vs 真實程式碼＋ruff／pytest；未修改交付物、未改動 WP／API／schema
- **結論：APPROVE（核心 NO-GO 判定誠實且有據；兩點非阻擋事項於 merge 前處理）**

---

## 1. 驗收條件逐項判定

| # | 驗收條件 | 判定 | 依據 |
|---|---|---|---|
| 1 | 逐年／kind／球場覆蓋矩陣，分開「沒有設備」與「理應有但缺漏」 | ✅PASS | `coverage_by_year_kind(_venue)`；tracking 五分類 `source_not_collected`／`equipment_unobserved`／`expected_missing`／`not_expected_yet`／`available`（[audit:143-159](../../scripts/audit_game_recap_data.py)），且明言「仍不是官方設備清冊」 |
| 2 | box PA／livelog 重建 PA／逐球可連結 PA 對帳，列 unknown action／換人／再見／延長／和局／延賽／0–0 邊界 | ✅PASS | PA 三分母表＋逐球三鍵歧義（203 PA）；邊界案例 7 類各抽 10 場；空白 action 5306 列保留供 PA1 對帳；action 值域完整列出 |
| 3 | 分別重現 run_dist／WP／frontend moment 三套近似分組，建立紅燈案例 | ✅PASS | 重現忠於真實程式碼（見 §2）；`repeated_matchup_keys`／`pitching_change_rows`／`frontend≠box` 三類紅燈落地 |
| 4 | 定義 canonical `pa_id`／事件排序／前後狀態／freshness，判定現有欄位能否可靠產生 | ✅PASS | canonical 契約 7 類欄位表；明確判定「無官方 PA ID／不可變 pitch ID／row-level freshness／完成狀態來源」→ NO-GO，schema 缺口另開 expand 卡 |
| 5 | 比較每日批次物化 vs request-time，提出單一推薦 | ✅PASS | 單一推薦：每日 refresh 後批次物化、API 只讀、逐球按 `pa_id` 延遲查詢；並誠實聲明 `refresh_log` 無 phase duration，不冒充 production SLA |
| 6 | 標明支援／不支援賽季與賽制，提供 fail-closed，不以一軍模型靜默代替二軍／季後 | ✅PASS | 支援邊界表＋四條 fail-closed（0–0 不判完成、跨 scope 不套用、對應不唯一回 null、三種缺漏分開） |

## 驗證項

| 項目 | 判定 | 依據 |
|---|---|---|
| 稽核 SQL 唯讀＋參數化，輸出保存 `docs/research/` | ✅PASS | `SET TRANSACTION READ ONLY`（[audit:420](../../scripts/audit_game_recap_data.py)）；全查詢 `%s`，`(from_year,to_year,kinds)*6` 對應 6 段 CTE；輸出即本 RESULTS 檔 |
| 抽查完賽／0–0／再見／延長／和局／換投／同局重複／無 TrackMan | ✅PASS | 7 類邊界案例＋grouping_risks＋no_tracking 抽樣齊備 |
| 獨立查核者重跑抽樣、確認分母／分類／建議一致 | ✅PASS | 見 §3 重現表，全部命中 |
| `uv run ruff check`／`uv run pytest` 通過 | ✅PASS | ruff `All checks passed!`；pytest `7 passed` |

---

## 2. 三套現行分組「重現」核實（NO-GO 立論基礎 — 全部與程式一致）

> NO-GO 全靠「三套近似分組邊界不同」；逐一對到真實程式行號，重現忠實、無虛構。

| 稽核腳本重現 | 真實實作 | 判定 |
|---|---|---|
| run_dist：排末半局＋每半局 `(batting_order, hitter)` 去重、跳過換人／無打者 | [`winprob.py:60-74`](../../src/cpbl/models/winprob.py) `order[:-1]`、`pa_key=(batting_order, hitter_acnt)` | ✅忠實 |
| WP：`(inning, half, batting_order, hitter)` 去重、含末半局 | [`games.py:287`](../../src/cpbl/api/routers/games.py) `pa_key=(inning_seq, vht, batting_order, hitter_acnt)` | ✅忠實 |
| frontend moment：沿用 WP 起點、向後略過換人掃同打者作終點 | [`overview.tsx:18-46`](../../web/src/app/games/[sno]/overview.tsx) `buildMoments()` `if(hitter!==...) break` | ✅忠實 |
| 逐球三鍵 `(inning, pitcher, hitter)` 併多 PA | frontend `game-board` 同鍵過濾（DOC 查核 §2 已核實）；本卡量化 203 PA 歧義 | ✅忠實 |

run_dist 因排末半局＋半局內去重 → 系統性低於 box（Δ 大負）；WP／frontend 因同半局打線輪轉吞第二打席／代打拆席 → 與 box ±小差；三者邊界互不相同，任一皆不可升格 canonical。判定成立。

---

## 3. 分母獨立重現（另寫 SQL，未複用被稽核腳本）— 全部命中

| 指標 | 報告值 | 獨立重現 | 判定 |
|---|---|---|---|
| 2022/A 排程 game_sno | 300 | 300 | ✅ |
| 2022/A 已開打（started） | 300 | 300 | ✅ |
| 2022/A box PA 合計 | 22817 | 22817 | ✅ |
| 空白 action（usable）全 scope | 5306 | 5306 | ✅ |
| livelog 事件（2018–2026, A/C/D/E） | 1326376 | 1326376 | ✅ |
| 逐球（pitch_tracking） | 71763 | 71763 | ✅ |

逐球三鍵一致性內部自洽：unique 71560 ＋ ambiguous 203 ＝ 71763，unmatched 0（逐球僅 2026、同場必有 livelog）。

---

## 4. 非阻擋事項（merge 前處理）

### N1 — 卡片 `db_scope` 白名單漏列　`severity: Low`

- **證據**：卡 §6 列只讀 `games`／`game_livelog`／`game_scoreboard`／`pitch_tracking`／`refresh_log`，但腳本另讀 `cpbl.batting_gamelog`（[audit:213-217](../../scripts/audit_game_recap_data.py)，box PA 對帳分母，稽核必需）與 `pg_class`／`pg_namespace`（[audit:466-475](../../scripts/audit_game_recap_data.py)，表體積 introspection）。
- **影響**：皆唯讀、無資料風險；屬卡片白名單 under-specified，非腳本越權。
- **處置**：補正卡片 §6 白名單納入 `batting_gamelog` 與 `pg_catalog` 唯讀 introspection（本次已隨查核修正）。

### N2 — 執行分支 merge-base 落後 main　`severity: Low`

- **證據**：`ai/gpt-5-codex/GAME-RECAP-DATA1` 的 merge-base 為 `d362c2b`，落後現 main（`0398a69`）。直接 diff main 會出現 DOC-GAME-RECAP1 等「回退」假象（events.jsonl／archive 檔／review 檔）。
- **影響**：非本卡變更；相對 merge-base 交付乾淨（僅新增 3 檔 1754 行）。
- **處置**：merge 前 rebase 到現 main，避免回退已合併工作。

---

## 5. Checkpoint 建議

證據、分母、缺漏分類與建議三者一致，NO-GO 誠實有據。**建議需求方核可 Checkpoint 1**：

- `GAME-RECAP-PA1`：可進設計／expand 拆卡，但禁以現有近似鍵直接實作 public canonical PA。
- `GAME-RECAP-STATUS1`：須先定義官方狀態與 row-level freshness 來源；`present_status=1` 不可單獨判定完成。
- WP/WPA 與精確逐球 UI：維持阻塞，直到 PA1 materialized contract 與資料正確性查核通過。
