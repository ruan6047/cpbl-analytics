# DEV-CLI-HELP-GUARD1 — `[project.scripts]` 入口 `--help` 行為盤點

> **本檔由指令產生，勿手改。**重新產生：
> `uv run python docs/research/DEV-CLI-HELP-GUARD1/audit_cli_help.py --out docs/research/DEV-CLI-HELP-GUARD1/cli-help-audit.md`

掃描對象：`af35ab306dc3fa8b96534f11eb3e329c0c9e9630`　—　**修補前基線**（本卡 spec 基線 commit）。同一支工具、同一套判定，對照 cli-help-audit.md 的修補後結果。

取證方式與判定碼定義見 `audit_cli_help.py` docstring。重點：盤點**未真跑任何爬蟲**——
探針在子行程中把 `migrate`／`conn`／`scrape_*` 等副作用出口換成會拋例外的 stub，
再對 socket／psycopg／subprocess 硬封鎖，因此物理上不可能送出請求或碰 DB。

入口總數 **46**：✅ SAFE 8／🔴 SIDE_EFFECT 18／其他 20。

## 逐入口

| console script | 解析方式 | `--help` | `-h` | 未知旗標 | 未知位置參數 | 模組 |
|---|---|---|---|---|---|---|
| `cpbl-anchor-career` | 手寫 sys.argv | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_anchor_career.py` |
| `cpbl-backfill` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_backfill.py` |
| `cpbl-backfill-season` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_backfill_season.py` |
| `cpbl-build-championships` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_build_championships.py` |
| `cpbl-build-features` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/features/run_build_features.py` |
| `cpbl-build-pa` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_build_pa.py` |
| `cpbl-build-sabr` | 手寫 sys.argv | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/models/run_build_sabr.py` |
| `cpbl-build-splits` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_build_splits.py` |
| `cpbl-check-coverage` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_check_coverage.py` |
| `cpbl-classify-pitches` | 手寫 sys.argv | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/models/run_classify_pitches.py` |
| `cpbl-classify-pitches-v2` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/models/pitch_type_v2.py` |
| `cpbl-ingest-editorial` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_ingest_editorial.py` |
| `cpbl-live-game` | 手寫 sys.argv | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_live_game.py` |
| `cpbl-live-worker` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_live_game_worker.py` |
| `cpbl-reconcile-advanced` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_reconcile_advanced.py` |
| `cpbl-refresh-recent` 🧊 | 手寫 sys.argv | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_refresh_recent.py` |
| `cpbl-research-umpire-impact` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/models/run_umpire_impact.py` |
| `cpbl-scrape-advanced` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_advanced.py` |
| `cpbl-scrape-awards` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_awards.py` |
| `cpbl-scrape-bio` | 手寫 sys.argv | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_bio.py` |
| `cpbl-scrape-coaches` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_coaches.py` |
| `cpbl-scrape-coaches-history` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_coaches_history.py` |
| `cpbl-scrape-detail` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_detail.py` |
| `cpbl-scrape-field` | 手寫 sys.argv | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_field.py` |
| `cpbl-scrape-fighting` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_fighting.py` |
| `cpbl-scrape-game-pitches` | 手寫 sys.argv | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_game_pitches.py` |
| `cpbl-scrape-gamelog` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_gamelog.py` |
| `cpbl-scrape-games` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape.py` |
| `cpbl-scrape-home-runs` | argparse | ✅ SAFE | ✅ SAFE | ⚠️ EXIT_NONZERO | ⚠️ EXIT_NONZERO | `src/cpbl/ingest/run_scrape_home_runs.py` |
| `cpbl-scrape-legends` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_legends.py` |
| `cpbl-scrape-managers` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_managers.py` |
| `cpbl-scrape-overseas` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_overseas.py` |
| `cpbl-scrape-pitches` | 手寫 sys.argv | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_pitches.py` |
| `cpbl-scrape-retired` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_retired.py` |
| `cpbl-scrape-roster` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_roster.py` |
| `cpbl-scrape-standings` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_standings.py` |
| `cpbl-scrape-stats` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_stats.py` |
| `cpbl-scrape-transactions` | 手寫 sys.argv | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/ingest/run_scrape_transactions.py` |
| `cpbl-scrape-wiki` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_scrape_wiki.py` |
| `cpbl-shadow-game-tm` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_shadow_game_tm.py` |
| `cpbl-train` | 無參數（完全不讀 argv） | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | `src/cpbl/models/train.py` |
| `cpbl-train-outcome` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/models/outcome_gbm.py` |
| `cpbl-train-outcome-simple` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/models/run_train_outcome_simple.py` |
| `cpbl-train-pa-sim` | 無參數（完全不讀 argv） | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | 🔴 SIDE_EFFECT | `src/cpbl/models/run_train_pa_sim.py` |
| `cpbl-train-pitching` | 無參數（完全不讀 argv） | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | ❔ IMPORT_ERROR | `src/cpbl/models/train_pitching.py` |
| `cpbl-verify-splits` | 手寫 sys.argv | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | ⚠️ CRASH | `src/cpbl/ingest/run_verify_splits.py` |

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

- `cpbl-backfill` — 主流程觸及 cpbl.db.migrate
- `cpbl-build-championships` — 主流程觸及 cpbl.db.migrate
- `cpbl-build-features` — 主流程觸及 cpbl.db.migrate
- `cpbl-build-sabr` — 主流程觸及 cpbl.db.migrate
- `cpbl-classify-pitches` — 主流程觸及 cpbl.db.migrate
- `cpbl-refresh-recent` — 主流程觸及 cpbl.db.migrate　**（G4 凍結檔，本卡不修）**
- `cpbl-scrape-awards` — 主流程觸及 cpbl.db.migrate
- `cpbl-scrape-bio` — 主流程觸及 cpbl.ingest.cpbl_player_bio.scrape
- `cpbl-scrape-field` — 主流程觸及 cpbl.db.migrate
- `cpbl-scrape-game-pitches` — 主流程觸及 cpbl.db.migrate
- `cpbl-scrape-managers` — 主流程觸及 cpbl.db.migrate
- `cpbl-scrape-overseas` — 主流程觸及 cpbl.db.migrate
- `cpbl-scrape-pitches` — 主流程觸及 cpbl.db.migrate
- `cpbl-scrape-retired` — 主流程觸及 cpbl.db.migrate
- `cpbl-scrape-transactions` — 主流程觸及 cpbl.db.migrate
- `cpbl-train-outcome` — 主流程觸及 cpbl.models.outcome._load
- `cpbl-train-outcome-simple` — 主流程觸及 cpbl.models.outcome_simple.load_outcome_rows
- `cpbl-train-pa-sim` — 主流程觸及 cpbl.models.pa_sim.load_pa_dataset

## ⚠️ `--help` 非零退出／例外的入口（無副作用，但語意錯）

- `cpbl-anchor-career` — ⚠️ EXIT_NONZERO：exit=2｜CLI：錨定生涯分項基底（一次性/重錨用）。
- `cpbl-backfill-season` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-build-splits` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-check-coverage` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-live-game` — ⚠️ EXIT_NONZERO：exit=1｜CLI【實驗】：賽況即時 TrackMan 單次探測（不寫 DB、不掛排程；等使用者下令實測）。
- `cpbl-scrape-advanced` — ⚠️ CRASH：ValueError: could not convert string to float: '--help'
- `cpbl-scrape-coaches` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-scrape-detail` — ⚠️ CRASH：ValueError: could not convert string to float: '--help'
- `cpbl-scrape-fighting` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-scrape-gamelog` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-scrape-games` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-scrape-legends` — ⚠️ CRASH：ValueError: could not convert string to float: '--help'
- `cpbl-scrape-roster` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-scrape-standings` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-scrape-stats` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-scrape-wiki` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-shadow-game-tm` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'
- `cpbl-train` — ❔ IMPORT_ERROR：OSError: dlopen(/private/tmp/claude-501/-Users-ruanruan-Dev-cpbl-analytics--claude-worktrees-workflow-review-optimization-33882b/
- `cpbl-train-pitching` — ❔ IMPORT_ERROR：OSError: dlopen(/private/tmp/claude-501/-Users-ruanruan-Dev-cpbl-analytics--claude-worktrees-workflow-review-optimization-33882b/
- `cpbl-verify-splits` — ⚠️ CRASH：ValueError: invalid literal for int() with base 10: '--help'

