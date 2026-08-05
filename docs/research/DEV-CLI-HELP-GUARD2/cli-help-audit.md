# DEV-CLI-HELP-GUARD1 — `[project.scripts]` 入口 `--help` 行為盤點

> **本檔由指令產生，勿手改。**重新產生：
> `uv run python docs/research/DEV-CLI-HELP-GUARD1/audit_cli_help.py --out docs/research/DEV-CLI-HELP-GUARD1/cli-help-audit.md`

掃描對象：`7ecf5efdc00cde96d33f06ad6faaa2c03b95d49f`　—　**GUARD2 修補後**（macOS host；train×2 因 LightGBM 缺 libomp 無法 import，其護欄由 container-probe.md 的容器內取證補齊）。

取證方式與判定碼定義見 `audit_cli_help.py` docstring。重點：盤點**未真跑任何爬蟲**——
探針在子行程中把 `migrate`／`conn`／`scrape_*` 等副作用出口換成會拋例外的 stub，
再對下列 I/O 出口硬封鎖，任何呼叫都會拋例外而不是真的送出去：

- `socket.socket.connect`
- `socket.create_connection`
- `socket.getaddrinfo`
- `subprocess.run`
- `subprocess.Popen`
- `psycopg.connect`
- `psycopg.Connection.connect`
- `psycopg.AsyncConnection.connect`
- `psycopg_pool.ConnectionPool`
- `psycopg_pool.AsyncConnectionPool`
- `psycopg_pool.NullConnectionPool`
- `psycopg_pool.AsyncNullConnectionPool`

封鎖面是**列舉**的，不是「全部」。本檔刻意不宣稱「物理上不可能碰 DB」——初版就是
因為漏封 `psycopg.AsyncConnection.connect` 與 `AsyncConnectionPool` 而讓那句絕對
宣稱不成立（查核 CLIHG1-R1-01）。繞過上列 Python 符號的路徑（ctypes、直接 syscall、
未列舉的第三方 driver）不在封鎖範圍內；本專案 ingest 入口只走 psycopg 與 httpx/socket，
故此封鎖面對本盤點充分。清單與 `tests/test_cli_help_guard.py` 由測試綁定，不得單邊漂移。

✅ 上列出口本次全部封鎖成功（探針自行回報，非人工聲明）。

入口總數 **46**：✅ SAFE 43／🔴 SIDE_EFFECT 1／其他 2。

## 逐入口

| console script | 解析方式 | `--help` | `-h` | 未知旗標 | 未知位置參數 | 模組 |
|---|---|---|---|---|---|---|
| `cpbl-anchor-career` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_anchor_career.py` |
| `cpbl-backfill` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_backfill.py` |
| `cpbl-backfill-season` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_backfill_season.py` |
| `cpbl-build-championships` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_build_championships.py` |
| `cpbl-build-features` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/features/run_build_features.py` |
| `cpbl-build-pa` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_build_pa.py` |
| `cpbl-build-sabr` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/models/run_build_sabr.py` |
| `cpbl-build-splits` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_build_splits.py` |
| `cpbl-check-coverage` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_check_coverage.py` |
| `cpbl-classify-pitches` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/models/run_classify_pitches.py` |
| `cpbl-classify-pitches-v2` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/models/pitch_type_v2.py` |
| `cpbl-ingest-editorial` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_ingest_editorial.py` |
| `cpbl-live-game` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_live_game.py` |
| `cpbl-live-worker` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_live_game_worker.py` |
| `cpbl-reconcile-advanced` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_reconcile_advanced.py` |
| `cpbl-refresh-recent` 🧊 | 手寫 sys.argv | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_refresh_recent.py` |
| `cpbl-research-umpire-impact` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/models/run_umpire_impact.py` |
| `cpbl-scrape-advanced` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_advanced.py` |
| `cpbl-scrape-awards` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_awards.py` |
| `cpbl-scrape-bio` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_bio.py` |
| `cpbl-scrape-coaches` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_coaches.py` |
| `cpbl-scrape-coaches-history` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_coaches_history.py` |
| `cpbl-scrape-detail` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_detail.py` |
| `cpbl-scrape-field` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_field.py` |
| `cpbl-scrape-fighting` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_fighting.py` |
| `cpbl-scrape-game-pitches` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_game_pitches.py` |
| `cpbl-scrape-gamelog` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_gamelog.py` |
| `cpbl-scrape-games` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape.py` |
| `cpbl-scrape-home-runs` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_home_runs.py` |
| `cpbl-scrape-legends` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_legends.py` |
| `cpbl-scrape-managers` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_managers.py` |
| `cpbl-scrape-overseas` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_overseas.py` |
| `cpbl-scrape-pitches` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_pitches.py` |
| `cpbl-scrape-retired` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_retired.py` |
| `cpbl-scrape-roster` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_roster.py` |
| `cpbl-scrape-standings` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_standings.py` |
| `cpbl-scrape-stats` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_stats.py` |
| `cpbl-scrape-transactions` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_transactions.py` |
| `cpbl-scrape-wiki` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_wiki.py` |
| `cpbl-shadow-game-tm` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_shadow_game_tm.py` |
| `cpbl-train` | argparse | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | `src/cpbl/models/train.py` |
| `cpbl-train-outcome` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/models/outcome_gbm.py` |
| `cpbl-train-outcome-simple` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/models/run_train_outcome_simple.py` |
| `cpbl-train-pa-sim` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/models/run_train_pa_sim.py` |
| `cpbl-train-pitching` | argparse | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | `src/cpbl/models/train_pitching.py` |
| `cpbl-verify-splits` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_verify_splits.py` |

🧊 ＝ INGEST-GAME-TM-REFACTOR1-G4 觀測凍結檔，本卡只盤點不修改。

「未知位置參數」欄的 🔴 不必然是缺陷：`cpbl-scrape-field` 的位置參數就是自由格式的
球場名，任何字串都是合法過濾條件，探針送的假值自然被當成球場名接受。

## 本卡資源邊界

DEV-CLI-HELP-GUARD1 的寫入集只有 `src/cpbl/ingest/`（扣掉兩個 G4 凍結檔）、
`pyproject.toml`、`tests/test_cli_help_guard.py`。因此下列入口**刻意未修**，
只在此列管、回報 PM：

- 🧊 `cpbl-refresh-recent` — G4 觀測凍結檔，明文排除（`git diff` 零 diff 為驗收條件）。
- `src/cpbl/models/` 與 `src/cpbl/features/` 下的入口 — 不在寫入集；
  且 `DATA-TZ-BOUNDARY1` 卡正平行作業於 models/features，不得越界。

`cpbl-train` / `cpbl-train-pitching` 在 macOS host 因 LightGBM 缺 `libomp` 而無法 import
（CLAUDE.md 既知限制，需在容器內跑），探針取不到證據；兩者靜態分類皆為「無參數」，
與同群 `cpbl-train-outcome` 等一致，可推定同屬 `--help` 直接開跑那一類。

## 🔴 `--help` 會觸發主流程的入口（探索即副作用）

- `cpbl-refresh-recent` — 主流程觸及 cpbl.db.migrate　**（G4 凍結檔，本卡不修）**

## ⚠️ `--help` 非零退出／例外的入口（無副作用，但語意錯）

- `cpbl-train` — ❔ IMPORT_ERROR：OSError: dlopen(/Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/dev-cli-help-guard2-execution/.venv/lib/python3.12/site-pack
- `cpbl-train-pitching` — ❔ IMPORT_ERROR：OSError: dlopen(/Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/dev-cli-help-guard2-execution/.venv/lib/python3.12/site-pack

