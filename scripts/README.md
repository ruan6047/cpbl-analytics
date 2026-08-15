# scripts/ 可執行入口清冊

> [!warning] 本檔由 `scripts/script_inventory.py` **自動產生**，勿手改。
> 重新產生：`uv run python scripts/script_inventory.py --write`
> 同步偵測器：`tests/test_script_inventory.py`（CI 於每個 PR 與 push main 執行）。

卡片：`DEV-SCRIPT-INVENTORY1`。射程＝三個入口面：`scripts/**`、`docs/research/**/*.py`、`pyproject [project.scripts]`。

## 分類：四類，各自回答「能不能跑、能不能刪」

| 分類 | 檔頭標記 | 應在的位置 | 可以刪嗎 | 可以跑嗎 |
|---|---|---|---|---|
| **常設工具** | `standing` | `scripts/` 頂層 | 不行 | **可以，這就是給你跑的** |
| **CI 繫結守衛** | `ci_guard` | `scripts/ci/` | 不行，刪了 CI 會紅 | **不必，CI 會跑** |
| **一次性產物** | `oneshot` | `docs/research/<CARD-ID>/` | 要需求方裁定 | **不要** |
| **待產品裁定** | `product_pending` | 不動 | 待裁 | 待裁 |

分類推導**與檔案現在放在哪無關**（否則不變式會變成恆真的廢話）：排程可達 → 常設；活文件給出可執行指令 → 常設；pytest 機械載入 → CI 繫結；綁卡且無上述訊號 → 一次性產物；**四項皆無 → fail closed，須具名改判**。

## 檔案系統上可分辨：檔頭標記（不變式 1）

`scripts/**` 的每一支都在檔頭帶一行 `LIFECYCLE:`，內容必須等於機械推導出來的分類：

```
# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（INGEST-DEEP-TM-BACKFILL1）
```

**新增腳本沒標、或標錯 → CI 紅。** `docs/research/<CARD-ID>/` 那一面靠**位置本身**分辨，不需要標記。

> [!note] 限度：檔頭標記 `ls` 看不到，要開檔才看得到。
> GitHub 在目錄列表直接渲染本檔（`scripts/README.md`），所以**瀏覽 `scripts/` 的人不必先知道清冊存在**——但在終端機 `ls` 的人仍看不出差別。

## 位置棘輪（不變式 2）——⚠️ 規劃階段的搬遷計畫被不變式 3 否決

規劃階段的方案是把一次性產物 `git mv` 進 `docs/research/<CARD-ID>/`、CI 繫結守衛移入 `scripts/ci/`。**引用完整性掃描一跑就否決了它**：

- 該搬的共 **28** 支；其中 **20** 支的活引用落在本卡射程（`scripts/` ＋ `tests/`）之外
- 阻擋的引用絕大多數是**凍結證據文件裡的重現指令**（`docs/research/<CARD>_RESULTS.md` 的「重現方法：`uv run python scripts/x.py …`」），另有 `src/` 的 docstring 與 3 張活卡的 spec 檔
- 搬走而不同步 ＝ **親手弄壞歷史證據的重現指令**，與 `data_tie_remedy1.py` 的 `FROZEN_FILES` 被抓到的是同一種傷害
- 只搬「免費的 8 支」會製造**更糟的假訊號**：一個只裝了部分成員的 `scripts/ci/`，會讓留在 `scripts/` 的其餘同類看起來像常設工具

**所以本輪零搬動。** 位置債逐支登記如下，**這個集合只能縮不能長**——新增的位置不符即 CI 紅。後續卡以正確射程（含 `docs/research/`、`src/`、他卡 spec）執行時，本表就是工單。

| 入口 | 分類 | 應在 | 射程外活引用（阻擋原因） |
|---|---|---|---|
| `audit_game_recap_data.py` | CI 繫結守衛 | `scripts/ci/` | `docs/research/GAME-RECAP-DATA1_RESULTS.md:29`、`docs/research/GAME-RECAP-DATA1_REVIEW.md:4` |
| `backfill_player_bio_gap1.py` | CI 繫結守衛 | `scripts/ci/` | `docs/archive/tasks/INGEST-PLAYER-BIO-GAP2.md:121`、`docs/research/INGEST-PLAYER-BIO-GAP1_DIAGNOSIS.md:180`、`docs/research/INGEST-PLAYER-BIO-GAP1_DIAGNOSIS.md:192`　…另 1 處 |
| `backfill_player_bio_gap2.py` | CI 繫結守衛 | `scripts/ci/` | **無**——射程內可搬，但為避免部分搬動造成假訊號，本輪一併保留 |
| `check_scoreless_null_folding.py` | 一次性產物 | `docs/research/ML-PITCHER-SCORELESS1/` | `docs/research/ML-PITCHER-SCORELESS1_RESULTS.md:249` |
| `check_splits_pa_split1_results.py` | 一次性產物 | `docs/research/INGEST-SPLITS-PA-SPLIT1/` | `docs/archive/tasks/INGEST-SPLITS-PA-SPLIT1.md:65` |
| `compare_runless_vs_er_streak.py` | 一次性產物 | `docs/research/ML-PITCHER-RUNLESS1/` | `docs/research/ML-PITCHER-RUNLESS1/RESULTS.md:287`、`docs/research/ML-PITCHER-RUNLESS1/RESULTS.md:292`、`docs/research/ML-PITCHER-RUNLESS1/RESULTS.md:338`　…另 1 處 |
| `data_tie_remedy1.py` | CI 繫結守衛 | `scripts/ci/` | **無**——射程內可搬，但為避免部分搬動造成假訊號，本輪一併保留 |
| `data_tz_boundary1.py` | 一次性產物 | `docs/research/DATA-TZ-BOUNDARY1/` | `docs/tasks/DOC-G4-FREEZE-STALE1.md:6` |
| `dryrun_game_tm_fullseason.py` | CI 繫結守衛 | `scripts/ci/` | **無**——射程內可搬，但為避免部分搬動造成假訊號，本輪一併保留 |
| `g4_gate_report.py` | 一次性產物 | `docs/research/INGEST-GAME-TM-REFACTOR1-G4/` | **無**——射程內可搬，但為避免部分搬動造成假訊號，本輪一併保留 |
| `g4_redline1_probe.py` | 一次性產物 | `docs/research/INGEST-GAME-TM-REFACTOR1-G4/` | **無**——射程內可搬，但為避免部分搬動造成假訊號，本輪一併保留 |
| `ibb_ghost1_probe.py` | 一次性產物 | `docs/research/INGEST-SPLITS-IBB-GHOST1/` | `docs/research/INGEST-SPLITS-IBB-GHOST1_RESULTS.md:23`、`docs/research/INGEST-SPLITS-IBB-GHOST1_RESULTS.md:24`、`docs/research/INGEST-SPLITS-IBB-GHOST1_RESULTS.md:25`　…另 5 處 |
| `outcome_leak_compare.py` | 一次性產物 | `docs/research/ML-OUTCOME-LEAK1/` | `docs/research/ML-OUTCOME-LEAK1_RESULTS.md:39` |
| `outcome_simple_calibration_audit.py` | 一次性產物 | `docs/research/ML-OUTCOME-SIMPLE-LEAK2/` | `docs/research/ML-OUTCOME-SIMPLE-LEAK2_RESULTS.md:111`、`docs/research/ML-OUTCOME-SIMPLE-LEAK2_RESULTS.md:255`、`docs/research/ML-OUTCOME-SIMPLE-LEAK2_RESULTS.md:259`　…另 1 處 |
| `reconcile_game_tm.py` | 一次性產物 | `docs/research/INGEST-GAME-TM-REFACTOR1/` | `docs/research/GAME_TM_SHADOW_OBSERVATION.md:43`、`docs/tasks/INGEST-GAME-TM-REFACTOR1-G4.md:141`、`docs/tasks/INGEST-GAME-TM-REFACTOR1.md:62`　…另 1 處 |
| `reconcile_splits_recalc1.py` | 一次性產物 | `docs/research/INGEST-SPLITS-RECALC1/` | `docs/research/INGEST-SPLITS-IBB-GHOST1_RESULTS.md:184` |
| `rehearsal_backfill.py` | 一次性產物 | `docs/research/INGEST-DEEP-TM-BACKFILL1/` | **無**——射程內可搬，但為避免部分搬動造成假訊號，本輪一併保留 |
| `rehearsal_pa_build.py` | 一次性產物 | `docs/research/GAME-RECAP-PA1-BUILD1/` | `docs/research/GAME-RECAP-PA1-BUILD1_HANDOFF.md:170`、`docs/research/GAME-RECAP-PA1-BUILD1_HANDOFF.md:215`、`docs/research/GAME-RECAP-PA1-BUILD1_HANDOFF.md:50` |
| `replay_schedule_branches.py` | 一次性產物 | `docs/research/INGEST-GAME-TM-REFACTOR1-G4/` | `docs/research/GAME_TM_SHADOW_OBSERVATION.md:141`、`docs/research/GAME_TM_SHADOW_OBSERVATION.md:146` |
| `report_pa_rebuild_fix1.py` | 一次性產物 | `docs/research/GAME-RECAP-PA1-FIX1/` | **無**——射程內可搬，但為避免部分搬動造成假訊號，本輪一併保留 |
| `restate1_reconcile.py` | 一次性產物 | `docs/research/INGEST-SPLITS-IMPORT-RESTATE1/` | `docs/archive/tasks/INGEST-SPLITS-IMPORT-RESTATE1.md:122`、`docs/archive/tasks/INGEST-SPLITS-IMPORT-RESTATE1.md:79`、`docs/research/INGEST-SPLITS-IMPORT-RESTATE1_RESULTS.md:26`　…另 6 處 |
| `state_plane_migrate.py` | CI 繫結守衛 | `scripts/ci/` | `docs/CONTROL_PLANE_CONTRACT.md:155`、`docs/archive/tasks/OPS-STATE-PLANE-MIG1.md:32`、`docs/archive/tasks/OPS-STATE-PLANE-MIG1.md:8`　…另 5 處 |
| `strength1_report_tables.py` | CI 繫結守衛 | `scripts/ci/` | `docs/research/GAME-RECAP-WP-STRENGTH1_RESULTS.md:368`、`docs/research/GAME-RECAP-WP-STRENGTH1_RESULTS.md:399`、`docs/research/GAME-RECAP-WP-STRENGTH1_RESULTS.md:49`　…另 1 處 |
| `team_style2_manager_pairs.py` | CI 繫結守衛 | `scripts/ci/` | `docs/research/TEAM-STYLE2_RESULTS.md:104`、`docs/research/TEAM-STYLE2_RESULTS.md:121` |
| `team_style_vectors.py` | 一次性產物 | `docs/research/TEAM-STYLE1/` | `docs/archive/tasks/UX-TEAM-STYLE1.md:49`、`docs/research/TEAM-STYLE1_RESULTS.md:100`、`docs/research/TEAM-STYLE1_RESULTS.md:101`　…另 2 處 |
| `verify_pa_build_fix1.py` | 一次性產物 | `docs/research/GAME-RECAP-PA1-FIX1/` | **無**——射程內可搬，但為避免部分搬動造成假訊號，本輪一併保留 |
| `verify_splits_pa_split1.py` | 一次性產物 | `docs/research/INGEST-SPLITS-PA-SPLIT1/` | `docs/archive/tasks/INGEST-SPLITS-PA-SPLIT1.md:65`、`docs/research/INGEST-SPLITS-PA-SPLIT1_RESULTS.md:19`、`src/cpbl/ingest/splits_pa_merge.py:12` |
| `wp_bio_prior1.py` | CI 繫結守衛 | `scripts/ci/` | `docs/archive/tasks/INGEST-PLAYER-BIO-GAP1.md:10`、`docs/archive/tasks/INGEST-PLAYER-BIO-GAP1.md:44`、`docs/archive/tasks/INGEST-PLAYER-BIO-GAP1.md:72`　…另 7 處 |

## 欄位語意（哪些有機械讀者，哪些沒有）

| 欄位 | 來源 | 過期時誰會知道 |
|---|---|---|
| `分類`／`檔頭標記` | 機械推導 | **CI**——集合漂移、標記與分類不符即紅 |
| `寫入` | W1 AST call-graph ＋ W2 正則 SQL 掃描交叉複算 | **CI**——新的判準不一致即紅 |
| `runnable` | 靜態 argv 守衛偵測（CLI 側沿用 `test_cli_help_guard.py` 的執行期證明） | **CI** |
| `purpose_declared` | module docstring 首句，機械抽取 | **CI**——與原始碼不符即紅 |
| `purpose_verified` | **人工維護** | ⚠️ **沒有機械讀者，會過期** |

> [!warning] `purpose_verified` 是人工欄：**沒有任何機器分得出它是否還為真**。
> 改了函式本體而不動 docstring 與參數，本清冊不會響。本欄只保證「有人在某個時點讀過碼」，不保證「現在仍為真」。

## 計數對帳

- `scripts/**`：**50**
- `docs/research/**/*.py`：**19**
- `pyproject [project.scripts]`：**47**
- **三面總和：116**

檔案面分類分佈：CI 繫結守衛 10、一次性產物 39、待產品裁定 1、常設工具 19

## 寫入面：兩套獨立判準交叉複算

- **W1（AST call-graph）**：從入口函式沿呼叫圖走，是否**可達**一個含寫入 SQL 的函式。跨 `src/cpbl/**` 模組傳遞。
- **W2（正則 SQL 掃描）**：入口的 import 閉包內，是否**存在**含寫入 SQL 動詞的字串字面。不看呼叫圖。

**不取聯集也不取交集**：聯集會把「只是 import 了一個含寫入函式的模組」誤判成寫入者；交集會漏掉「呼叫 `build_splits()` 但自己一行 SQL 都沒有」的真寫入者。不一致者逐支人工裁定，出現**未裁定的新不一致**即 CI 紅，**裁定條目過期**（兩判準已一致）也會 CI 紅——後者是刻意的，`roadmap_lines.py` 的 `GATE_OVERRIDES` 被 `#137` 判為缺陷的理由正是「沒有到期來源」。

- 兩判準皆適用：**108** 支，其中不一致 **28** 支（全部已裁定）
- **只有一套判準：8** 支（`.sh`／`.plist` 沒有 Python AST，W1 結構性不適用）——**這一格沒有交叉複算**，不假裝有
- 判定為寫入型：**53** 支（`scripts/**` 10、`docs/research/` 1、CLI 42）

> [!important] **W1 有一個結構性盲點，而它剛好落在最危險的那支上。**
> `docs/research/INGEST-DEEP-TM-BACKFILL1/sync_deep_tm_prod.py` 把 `COPY` ＋ `UPDATE cpbl.pitch_tracking` 透過 `subprocess.run(['ssh', VPS, …'psql'], input=…)` 串進**生產**——
> 寫入完全不經過 Python 的 DB cursor，**AST 呼叫圖看不到**，只有 W2 掃字面抓得到。
> 這一支就是「為什麼要兩套判準」的答案。

### 不一致清單（逐支人工裁定）

| 入口 | W1 AST | W2 SQL | 裁定 | 理由 |
|---|---|---|---|---|
| `cpbl-research-umpire-impact` | 唯讀 | 寫 | 唯讀 | 唯讀研究，產物落檔案 |
| `cpbl-verify-splits` | 唯讀 | 寫 | 唯讀 | 唯讀驗證入口 |
| `docs/research/INGEST-DEEP-TM-BACKFILL1/sync_deep_tm_prod.py` | 唯讀 | 寫 | **寫** | ⚠️ **W1 的結構性偽陰性**：它以 `subprocess.run(['ssh', VPS, ... 'psql'], input=script)` 把 `COPY cpbl.pitch_tracking_deep_staging` ＋ `UPDATE cpbl.pitch_tracking` 串進**生產** psql——寫入完全不經過 Python 的 DB cursor，AST 呼叫圖看不到。W2 掃字面才抓得到。這一支就是兩套判準必須並存的理由 |
| `docs/research/ML-PITCHER-ER-REBUILD1/cases/build_cases.py` | 唯讀 | 寫 | 唯讀 | 唯讀取樣落 JSON |
| `docs/research/ML-PITCHER-ER-REBUILD1/rebuild_er.py` | 唯讀 | 寫 | 唯讀 | docstring 明寫「本檔只讀 DB、只寫 JSON 到本目錄，不改任何既有模組、不寫任何表」；檔內 `cur.execute` 全是 SELECT |
| `docs/research/ML-WP-VAL-RESAMPLE1/bin_stability.py` | 唯讀 | 寫 | 唯讀 | 唯讀重抽樣分析 |
| `docs/research/ML-WP-VAL-RESAMPLE1/census.py` | 唯讀 | 寫 | 唯讀 | 唯讀普查 |
| `docs/research/ML-WP-VERDICT-ROBUST1/budget_trace.py` | 唯讀 | 寫 | 唯讀 | 唯讀預算追蹤 |
| `docs/research/ML-WP-VERDICT-ROBUST1/compare_verdicts.py` | 唯讀 | 寫 | 唯讀 | 同一份資料同一份指標、只換判定規則的對照，不落表 |
| `scripts/ability_snapshot.py` | 唯讀 | 寫 | 唯讀 | 唯讀抽驗：呼叫 API helper `_ability_card` 取快照 dump 成 JSON；W2 命中的是 cpbl.api 閉包裡別條路徑的寫入 |
| `scripts/capture_player_ia_fixtures.py` | 唯讀 | 寫 | 唯讀 | 唯讀：打 API 取 payload、截斷後落 web fixtures 檔 |
| `scripts/check_splits_pa_split1_results.py` | 唯讀 | 寫 | 唯讀 | 純讀 artifact JSON 與 RESULTS.md 對數字，完全不開 DB |
| `scripts/data_rules_audit1.py` | 唯讀 | 寫 | 唯讀 | 唯讀稽核；凍結在舊判準供重現當初數字 |
| `scripts/data_tie_remedy1.py` | 唯讀 | 寫 | 唯讀 | 唯讀；只讀 completion 與 games 算並列名次 |
| `scripts/dryrun_game_tm_fullseason.py` | 唯讀 | 寫 | 唯讀 | dry-run：只比對不寫入，卡面即以此為射程 |
| `scripts/g4_gate_report.py` | 唯讀 | 寫 | 唯讀 | 唯讀 Gate 報表 |
| `scripts/g4_phase_a_metrics.py` | 唯讀 | 寫 | 唯讀 | 唯讀觀測指標；凍結在舊判準 |
| `scripts/g4_redline1_probe.py` | 唯讀 | 寫 | 唯讀 | 唯讀探針 |
| `scripts/ibb_ghost1_probe.py` | 唯讀 | 寫 | 唯讀 | 唯讀探針 |
| `scripts/outcome_leak_compare.py` | 唯讀 | 寫 | 唯讀 | 唯讀回測對照，產物落檔案不落 DB |
| `scripts/outcome_simple_calibration_audit.py` | 唯讀 | 寫 | 唯讀 | 唯讀校準稽核 |
| `scripts/pa_transition_taxonomy.py` | 唯讀 | 寫 | 唯讀 | docstring 明宣告唯讀（db_scope=read）；產物是 JSON 與 md，不物化 PA |
| `scripts/reconcile_game_tm.py` | 唯讀 | 寫 | 唯讀 | 唯讀對帳：比兩條 fetch path，不落表 |
| `scripts/replay_schedule_branches.py` | 唯讀 | 寫 | 唯讀 | Gate 3 補證：對歷史賽程**回放**既有分類邏輯，只讀不落表 |
| `scripts/team_style2_manager_pairs.py` | 唯讀 | 寫 | 唯讀 | docstring 明寫「唯讀；描述性」——換教練混雜效應檢定 |
| `scripts/verify_pa_build_fix1.py` | 唯讀 | 寫 | 唯讀 | 唯讀驗證 |
| `scripts/verify_splits_pa_split1.py` | 唯讀 | 寫 | 唯讀 | 開頭即 `SET TRANSACTION READ ONLY`，物理上寫不了 |
| `scripts/wp_bio_prior1.py` | 唯讀 | 寫 | 唯讀 | 唯讀先驗分析 |

### 單一判準（`.sh`／`.plist`，無交叉複算）

| 入口 | W2 SQL | 裁定 | 說明 |
|---|---|---|---|
| `backup-prod-db.sh` | 寫 | 唯讀 | W2 命中的 `CREATE TABLE` 在 awk 樣式 `/^CREATE TABLE /{t++}` 裡——那是**數 dump 裡有幾張表**的內容門檻驗證，不是建表。本腳本對 DB 唯讀（`pg_dump`），寫的是本機備份檔。⚠️ 仍是高後果操作：不看 argv、連生產、跑完整 dump |
| `com.cpbl.scrape-daily.plist` | 唯讀 | 唯讀 | W2 單獨採信 |
| `com.cpbl.weekly-box-revisions.plist` | 唯讀 | 唯讀 | W2 單獨採信 |
| `com.cpbl.weekly-game-pitches.plist` | 唯讀 | 唯讀 | W2 單獨採信 |
| `refresh-cpbl-prod.sh` | 寫 | **寫** | W2 單獨採信 |
| `scrape-daily.sh` | 寫 | **寫** | W2 單獨採信 |
| `weekly-box-revisions.sh` | 寫 | **寫** | W2 單獨採信 |
| `weekly-game-pitches.sh` | 寫 | **寫** | W2 單獨採信 |

## 引用完整性（不變式 3）

全庫 `scripts/<name>.<ext>` 字面路徑共 **895** 處。**只有 `enforced` 那一面強制**——其餘的過期是歷史事實不是缺陷：

| 面別 | 處數 | 強制？ | 為什麼 |
|---|---:|---|---|
| `scan` | 206 | 回報 | 掃描器產物 JSON 是當時的快照 |
| `sealed` | 198 | 回報 | `docs/control-plane/**` 已於 `8271d7c` 封存唯讀，**永遠改不了** |
| `self` | 173 | 不適用 | 掃描器自身的說明範例 |
| `enforced` | 144 | ✅ 強制 | `scripts/`、`src/`、活契約與設計文件——壞了就是現在的缺陷 |
| `historical` | 144 | 回報 | `docs/archive/**` 與卡片交付產物＝凍結證據，**本卡射程外** |
| `fixture` | 30 | 不適用 | `tests/**` 的合成路徑；真實路徑壞掉 pytest 自己會紅（更強的機制） |

**壞路徑——⚠️ **強制面**（1）**：

- `docs/REVIEW_GATE_CONTRACT.md:284 → scripts/review_gate_preflight.py`

**壞路徑——歷史面（僅回報）（2）**：

- `docs/archive/tasks/INGEST-DEEP-TM-BACKFILL1.md:49 → scripts/backup-cpbl-prod.sh`
- `docs/research/GAME-RECAP-PA1-BUILD1_HANDOFF.md:179 → scripts/backup-cpbl-prod.sh`

> [!important] 這條不變式是被 `scripts/data_tie_remedy1.py` 的 `FROZEN_FILES` 逼出來的——它以**字面路徑**硬編兩支一次性產物，而 CI 只 import `_streaks_for` 碰不到 `is_frozen`。搬走那兩支會讓守衛靜默回 `False`，零訊號。
> **現在搬走它們會讓 CI 紅**，這就是那個缺陷的修法。

## 寫入型必須 `--help` 安全（不變式 4）

判定為寫入型的入口，argv 必須在主流程前被解析。**既有不合格者具名列入 allowlist**。

原則上本卡只加不變式、不改既有腳本行為（那會讓本卡從盤點變成改一批腳本），但需求方對**排程 shell** 推翻了這個處置：`refresh-cpbl-prod.sh`／`scrape-daily.sh`／`weekly-game-pitches.sh` 與 `sync_deep_tm_prod.py` **同級**——探索動作即造成損害——而破壞半徑更大（後者 DROP 一張表，`refresh-cpbl-prod.sh` 是整條生產同步鏈）。三支已加 argv 守衛並從下表撤除，證明見 `tests/test_shell_help_guard.py`。

| 入口 | 理由與去向 |
|---|---|
| `cpbl-refresh-recent` | #53 INGEST-GAME-TM-REFACTOR1-G4 Phase B 凍結資源，DEV-CLI-HELP-GUARD1／2 明文不改。`--help` 主流程觸及 cpbl.db.migrate，且它是每日鏈 scrape-daily.sh 的主要寫入者。去向：#53 Phase B 解凍後併入 test_cli_help_guard.py 的斷言範圍 |
| `docs/research/INGEST-DEEP-TM-BACKFILL1/sync_deep_tm_prod.py` | ⚠️ **本輪射程內最危險的一支**：完全不看 argv，任何參數都直接 ssh 進生產跑 `COPY` ＋ `UPDATE cpbl.pitch_tracking`；`VPS` 是裸常數不可覆蓋、無 dry-run、無備份。已於 `dac8d8e` 移出 `scripts/`（＝瀏覽者不會再誤觸），但**檔案本身的行為沒變**。去向：修行為需另卡，母卡 INGEST-DEEP-TM-BACKFILL1 已封存 |
| `scripts/rehearsal_backfill.py` | 完全不看 argv：任何旗標（含 --help）都直接 DROP/CREATE pitch_tracking_rehearsal。去向：本卡只標記；修行為需另卡，且該卡母卡 INGEST-DEEP-TM-BACKFILL1 已封存 |
| `scripts/rehearsal_pa_build.py` | 完全不看 argv，寫合成 year=2099 列。去向：同上，PA-DAILY 若啟動時一併處理 |
| `scripts/weekly-box-revisions.sh` | 無 argv 守衛，會直接跑 `cpbl-refresh-box-deep`（Playwright 打官網 + 寫本機 DB）。⚠️ **與同批三支同性質，本卡射程外**：它是 `#132` 的資源（該卡同時持有 `scripts/refresh_status.py` 與 `src/cpbl/api/routers/info.py`），本卡改它等於動另一張活卡的檔案。去向：`#132` 收工後比照同批三支補上守衛 |

> [!note] 判準沿用 `tests/test_cli_help_guard.py`，不另立一套。
> CLI 側該檔以**執行期密封探針**證明（所有 I/O 出口 stub 化後才呼叫 `main()`）；
> `.py` 的 `scripts/` 側因本卡紅線**不得執行任何腳本**，改以**靜態**近似：「有 argparse 且入口在主流程前呼叫 `parse_args`」。
> **限度**：靜態判準證明不了「parse_args 之後才有副作用」，只證明 argv 有被解析。
> shell 側的靜態判準更弱——整檔正則只看得到守衛在不在、看不到它在哪。已加守衛的三支因此另由 `tests/test_shell_help_guard.py` 以**副本 ＋ 假樁**逐支證明 `--help` 零外部呼叫、零檔案產出，並釘住「守衛之前不得有副作用」；該檔的 `test_every_safe_shell_is_covered_here` 使「清冊判 safe 卻沒人證明」直接 CI 紅。

## 清冊：`scripts/**`（50）

| 入口 | 分類 | 位置 | 應在 | 寫入 | runnable | 卡 | purpose_declared | purpose_verified |
|---|---|---|---|---|---|---|---|---|
| `audit_game_recap_data.py` | CI 繫結守衛 | `scripts/` | ⚠️ `scripts/ci/` | 唯讀 | ✅ --help 安全 | GAME-RECAP-DATA1 | GAME-RECAP-DATA1：賽事復盤資料覆蓋與 canonical 打席契約唯讀稽核。 | ⚠️ 未查證 |
| `backfill_player_bio_gap1.py` | CI 繫結守衛 | `scripts/` | ⚠️ `scripts/ci/` | **寫** | ✅ --help 安全 | INGEST-PLAYER-BIO-GAP1 | INGEST-PLAYER-BIO-GAP1：補齊 players 缺 country／birthday 的一次性 bio 重爬。 | ⚠️ 未查證 |
| `backfill_player_bio_gap2.py` | CI 繫結守衛 | `scripts/` | ⚠️ `scripts/ci/` | **寫** | ✅ --help 安全 | INGEST-PLAYER-BIO-GAP2 | INGEST-PLAYER-BIO-GAP2：補齊 14 人的 handedness 與 batch 2 其餘 bio 欄。 | ⚠️ 未查證 |
| `data_tie_remedy1.py` | CI 繫結守衛 | `scripts/` | ⚠️ `scripts/ci/` | 唯讀 | ✅ --help 安全 | DATA-TIE-REMEDY1 | DATA-TIE-REMEDY1：5 場 0:0 隱形和局的取證、補爬與影響評估。 | ⚠️ 未查證 |
| `dryrun_game_tm_fullseason.py` | CI 繫結守衛 | `scripts/` | ⚠️ `scripts/ci/` | 唯讀 | ✅ --help 安全 | INGEST-GAME-TM-REFACTOR1-G4 | INGEST-GAME-TM-REFACTOR1-G4 Phase A：全季唯讀 dry-run 對帳（單場 API vs 正式表存量）。 | ⚠️ 未查證 |
| `state_plane_migrate.py` | CI 繫結守衛 | `scripts/` | ⚠️ `scripts/ci/` | 唯讀 | ✅ --help 安全 | OPS-STATE-PLANE-MIG1 | OPS-STATE-PLANE-MIG1 Task 2：一次性遷移 Ledger 活卡至 GitHub Issues + Projects v2。 | ⚠️ 未查證 |
| `strength1_report_tables.py` | CI 繫結守衛 | `scripts/` | ⚠️ `scripts/ci/` | 唯讀 | ✅ --help 安全 | GAME-RECAP-WP-STRENGTH1 | 由 canonical artifact 產生 GAME-RECAP-WP-STRENGTH1 報告的數字區塊。 | ⚠️ 未查證 |
| `team_style2_manager_pairs.py` | CI 繫結守衛 | `scripts/` | ⚠️ `scripts/ci/` | 唯讀 | ✅ --help 安全 | TEAM-STYLE2 | TEAM-STYLE2 換教練混雜效應檢定（唯讀；描述性）。 | ⚠️ 未查證 |
| `wp_bio_prior1.py` | CI 繫結守衛 | `scripts/` | ⚠️ `scripts/ci/` | 唯讀 | ✅ --help 安全 | ML-WP-BIO-PRIOR1 | ML-WP-BIO-PRIOR1：WP 賽前先驗 bio 方向研究 spike（唯讀；協定見預註冊 spec）。 | ⚠️ 未查證 |
| `check_scoreless_null_folding.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/ML-PITCHER-SCORELESS1/` | 唯讀 | ⚠️ --help 不安全 | ML-PITCHER-SCORELESS1 | 窮舉「把缺值折成有效值」的寫法（ML-PITCHER-SCORELESS1 紅線 2 的守衛）。 | ⚠️ 未查證 |
| `check_splits_pa_split1_results.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-SPLITS-PA-SPLIT1/` | 唯讀 | ⚠️ --help 不安全 | INGEST-SPLITS-PA-SPLIT1 | RESULTS 引用數字 ↔ artifact 一致性檢查（REVIEW-008 F1 的防再犯守衛）。 | ⚠️ 未查證 |
| `compare_runless_vs_er_streak.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/ML-PITCHER-RUNLESS1/` | 唯讀 | ✅ --help 安全 | ML-PITCHER-RUNLESS1 | ML-PITCHER-RUNLESS1：失分口徑 vs 自責分口徑的**逐人對照**與**媒體數字檢查點**。 | ⚠️ 未查證 |
| `data_rules_audit1.py` | 一次性產物 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | DATA-RULES-AUDIT1 | DATA-RULES-AUDIT1：規章→資料判讀的偽陽偽陰審計（**唯讀**）。 | ⚠️ 未查證 |
| `data_tz_boundary1.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/DATA-TZ-BOUNDARY1/` | 唯讀 | ✅ --help 安全 | DATA-TZ-BOUNDARY1 | DATA-TZ-BOUNDARY1：日期界線時區用點盤點（**唯讀**，artifact 由本腳本產生）。 | ⚠️ 未查證 |
| `g4_gate_report.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-GAME-TM-REFACTOR1-G4/` | 唯讀 | ✅ --help 安全 | INGEST-GAME-TM-REFACTOR1-G4 | INGEST-GAME-TM-REFACTOR1-G4 Phase A：gate 判定與凍結例外後的紅線 1 複判（唯讀）。 | ⚠️ 未查證 |
| `g4_phase_a_metrics.py` | 一次性產物 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | INGEST-GAME-TM-REFACTOR1-G4 | INGEST-GAME-TM-REFACTOR1-G4 Phase A：唯讀量測三件套（全部產 artifact，不得人工轉述）。 | ⚠️ 未查證 |
| `g4_redline1_probe.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-GAME-TM-REFACTOR1-G4/` | 唯讀 | ✅ --help 安全 | INGEST-GAME-TM-REFACTOR1-G4 | INGEST-GAME-TM-REFACTOR1-G4 Phase A：紅線 1／3 的歸因探針（唯讀，產 artifact）。 | ⚠️ 未查證 |
| `ibb_ghost1_probe.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-SPLITS-IBB-GHOST1/` | 唯讀 | ✅ --help 安全 | INGEST-SPLITS-IBB-GHOST1 | INGEST-SPLITS-IBB-GHOST1 探針：零投球「故四」幽靈島的官方語意查證。 | ⚠️ 未查證 |
| `outcome_leak_compare.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/ML-OUTCOME-LEAK1/` | 唯讀 | ⚠️ --help 不安全 | ML-OUTCOME-LEAK1 | ML-OUTCOME-LEAK1 一次性留痕：跑走查回測但**不寫入** model_versions。 | ⚠️ 未查證 |
| `outcome_simple_calibration_audit.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/ML-OUTCOME-SIMPLE-LEAK2/` | 唯讀 | ⚠️ --help 不安全 | ML-OUTCOME-SIMPLE-LEAK2 | ML-OUTCOME-SIMPLE-LEAK2 留痕：校準斜率閘門重校的全部依據，**不寫入** DB／artifact。 | ⚠️ 未查證 |
| `reconcile_game_tm.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-GAME-TM-REFACTOR1/` | 唯讀 | ✅ --help 安全 | INGEST-GAME-TM-REFACTOR1 | INGEST-GAME-TM-REFACTOR1 Gate 2：單場 API vs 逐投手 logs 逐列等價對帳（唯讀，不寫 DB）。 | ⚠️ 未查證 |
| `reconcile_splits_recalc1.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-SPLITS-RECALC1/` | **寫** | ✅ --help 安全 | INGEST-SPLITS-RECALC1 | INGEST-SPLITS-RECALC1 重建對帳：diff 必須逐格等於已查核的預期 delta。 | ⚠️ 未查證 |
| `rehearsal_backfill.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-DEEP-TM-BACKFILL1/` | **寫** | ⚠️ --help 不安全（具名例外） | INGEST-DEEP-TM-BACKFILL1 | Rehearsal script for INGEST-DEEP-TM-BACKFILL1. | ⚠️ 未查證 |
| `rehearsal_pa_build.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/GAME-RECAP-PA1-BUILD1/` | **寫** | ⚠️ --help 不安全（具名例外） | GAME-RECAP-PA1-BUILD1 | GAME-RECAP-PA1-BUILD1 production rehearsal：DB 層 reconciliation / atomic swap / 冪等。 | ⚠️ 未查證 |
| `replay_schedule_branches.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-GAME-TM-REFACTOR1-G4/` | 唯讀 | ⚠️ --help 不安全 | INGEST-GAME-TM-REFACTOR1-G4 | Gate 3 條件 3 補證：對歷史賽程回放既有分類邏輯，證明延期/保留賽分支在真實資料上跑過。 | ⚠️ 未查證 |
| `report_pa_rebuild_fix1.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/GAME-RECAP-PA1-FIX1/` | 唯讀 | ✅ --help 安全 | GAME-RECAP-PA1-FIX1 | GAME-RECAP-PA1-FIX1 全庫重建驗收報告：對 DB 實際狀態窮舉（非 dry-run）。 | ⚠️ 未查證 |
| `restate1_reconcile.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-SPLITS-IMPORT-RESTATE1/` | **寫** | ✅ --help 安全 | INGEST-SPLITS-IMPORT-RESTATE1 | INGEST-SPLITS-IMPORT-RESTATE1：分項重建的前後快照與變動歸因對帳。 | ⚠️ 未查證 |
| `team_style_vectors.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/TEAM-STYLE1/` | 唯讀 | ✅ --help 安全 | TEAM-STYLE1 | TEAM-STYLE1 球隊球風向量計算（唯讀；描述性）。 | ⚠️ 未查證 |
| `verify_deep_tm_backfill.py` | 一次性產物 | `scripts/` | ✅ | 唯讀 | ⚠️ --help 不安全 | INGEST-DEEP-TM-BACKFILL1 | Verification script for INGEST-DEEP-TM-BACKFILL1. | ⚠️ 未查證 |
| `verify_pa_build_fix1.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/GAME-RECAP-PA1-FIX1/` | 唯讀 | ✅ --help 安全 | GAME-RECAP-PA1-FIX1 | GAME-RECAP-PA1-FIX1 對帳：修正前後的打席切分與出局數，全母體窮舉。 | ⚠️ 未查證 |
| `verify_splits_pa_split1.py` | 一次性產物 | `scripts/` | ⚠️ `docs/research/INGEST-SPLITS-PA-SPLIT1/` | 唯讀 | ✅ --help 安全 | INGEST-SPLITS-PA-SPLIT1 | INGEST-SPLITS-PA-SPLIT1 查證（iteration 3）：`splits_calc` 重複計打席的範圍與選手層級影響。 | ⚠️ 未查證 |
| `capture_player_ia_fixtures.py` | 待產品裁定 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | UX-PLAYER-IA1 | 擷取球員頁 IA prototype 用的真實 fixture（UX-PLAYER-IA1）。 | ⚠️ 未查證 |
| `ability_snapshot.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ⚠️ --help 不安全 | ABILITY-2 | 能力值卡回歸快照：跨年代抽驗球員的各軸 PR/總評/組成 dump 成 JSON。 | 能力值卡回歸抽驗；docstring 明寫改前後各跑一次再 diff |
| `backup-prod-db.sh` | 常設工具 | `scripts/` | ✅ | 唯讀 | ⚠️ --help 不安全 | OPS-BACKUP-EMPTY1 | 備份並驗證整個 production 資料庫（alpha_db：cpbl schema ＋ 主站 public schema）； stdout 只輸出備份路徑。 | 備整庫並驗內容門檻（OPS-BACKUP-EMPTY1 的產物，已是常設） |
| `com.cpbl.scrape-daily.plist` | 常設工具 | `scripts/` | ✅ | 唯讀 | — | — | — | ⚠️ 未查證 |
| `com.cpbl.weekly-box-revisions.plist` | 常設工具 | `scripts/` | ✅ | 唯讀 | — | — | — | ⚠️ 未查證 |
| `com.cpbl.weekly-game-pitches.plist` | 常設工具 | `scripts/` | ✅ | 唯讀 | — | — | — | ⚠️ 未查證 |
| `pa_transition_taxonomy.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | GAME-RECAP-PA1-TAXONOMY1 | GAME-RECAP-PA1-TAXONOMY1：canonical PA 狀態機 transition taxonomy 唯讀稽核。 | canonical taxonomy 的產生器（唯讀）；產物勿手改，改了要重跑 |
| `reconcile_scoreless_streak.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | ML-PITCHER-SCORELESS1 | 窮舉對帳：連續無自責分局數（ML-PITCHER-SCORELESS1）＋連續無失分局數（ML-PITCHER-RUNLESS1）。 | 窮舉對帳；AI_RUNBOOK:380 寫「改動演算法後必跑」，義務靠人記得 |
| `refresh-cpbl-prod.sh` | 常設工具 | `scripts/` | ✅ | **寫** | ✅ --help 安全 | — | CPBL 線上資料手動更新（不掛 cron，避免浪費資源；要更新時自己跑）。 | 本機爬完同步生產的主鏈；讀碼確認會呼叫 backup-prod-db.sh 與 verify_refresh_info.py |
| `refresh_status.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | — | Write and inspect machine-readable daily refresh status files. | 每日鏈的狀態記錄輔助，唯讀 JSON 檔 |
| `review_gate_inventory.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | DEV-REVIEW-PROMPT-GUARD1 | 多關卡（multi-gate）查核要求的可重現盤點——**含分類與計數**。 | ⚠️ REVIEW_GATE_CONTRACT 宣告「納管＋測試」但實測無測試載入，宣告未落實 |
| `review_prompt.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ⚠️ --help 不安全 | DEV-BASELINE-GUARD-DECL1 | 審核提示詞產生器：從 control-plane 最新 handoff event + 卡片檔自動生成查核提示詞。 | 查核提示詞產生器；AI_RUNBOOK:433 逐字給指令，18 commits |
| `roadmap_lines.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | DOC-CPBL-ROADMAP1 | CPBL 藍圖排程區塊的任務線歸屬驗證器（唯讀，fail-closed）。 | ROADMAP §1 線別歸屬的機械判定者，fail closed |
| `scrape-daily.sh` | 常設工具 | `scripts/` | ✅ | **寫** | ✅ --help 安全 | YYYYMMDD-HHMM | 每日本機自動爬取（由 launchd 觸發，免手動 CLI）。 | launchd 每日 10:10 觸發，呼叫 refresh-cpbl-prod.sh 並用 refresh_status.py 記狀態 |
| `script_inventory.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | DEV-SCRIPT-INVENTORY1 | DEV-SCRIPT-INVENTORY1：可執行入口清冊的**產生器**。 | ⚠️ 未查證 |
| `verify_refresh_info.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | — | Fail unless /api/info exposes a recent successful refresh marker. | 同步後打 /api/info 驗證，唯讀 |
| `weekly-box-revisions.sh` | 常設工具 | `scripts/` | ✅ | **寫** | ⚠️ --help 不安全（具名例外） | DATA-BOX-REVISION-SNAPSHOT1 | 每週一次的 box 深度重抓（DATA-BOX-REVISION-SNAPSHOT1 深度層）。 | ⚠️ 未查證 |
| `weekly-game-pitches.sh` | 常設工具 | `scripts/` | ✅ | **寫** | ✅ --help 安全 | INGEST-GAME-TM-REFACTOR1-G4 | 每週一次的逐球全季重跑（INGEST-GAME-TM-REFACTOR1-G4 Phase A）。 | ⚠️ 未查證 |
| `workflow_ledger.py` | 常設工具 | `scripts/` | ✅ | 唯讀 | ✅ --help 安全 | — | 由 append-only control-plane events 產生活卡 Ledger。 | ⚠️ 已於 33c7c3f 加拒絕執行守衛——TASKS.md 已封存，--write 會覆寫封存產物 |

## 清冊：`docs/research/**/*.py`（19）

| 入口 | 分類 | 位置 | 應在 | 寫入 | runnable | 卡 | purpose_declared | purpose_verified |
|---|---|---|---|---|---|---|---|---|
| `audit_cli_help.py` | CI 繫結守衛 | `docs/research/DEV-CLI-HELP-GUARD1/` | ✅ | 唯讀 | ✅ --help 安全 | DEV-CLI-HELP-GUARD1 | DEV-CLI-HELP-GUARD1 盤點工具：掃描 pyproject `[project.scripts]` 全部入口的 --help 行為。 | ⚠️ 未查證 |
| `scan_g4_freeze.py` | 一次性產物 | `docs/research/DOC-G4-FREEZE-STALE1/` | ✅ | 唯讀 | ✅ --help 安全 | DOC-G4-FREEZE-STALE1 | DOC-G4-FREEZE-STALE1：全庫 G4 觀測凍結陳述盤點（唯讀）。 | ⚠️ 未查證 |
| `sync_deep_tm_prod.py` | 一次性產物 | `docs/research/INGEST-DEEP-TM-BACKFILL1/` | ✅ | **寫** | ⚠️ --help 不安全（具名例外） | INGEST-DEEP-TM-BACKFILL1 | Sync 12 deep TrackMan fields from local DB to production DB for INGEST-DEEP-TM-BACKFILL1. | ⚠️ 未查證 |
| `confirm_live_schema.py` | 一次性產物 | `docs/research/INGEST-SCORELESS-INNING-PITCHER1/` | ✅ | 唯讀 | ⚠️ --help 不安全 | INGEST-SCORELESS-INNING-PITCHER1 | 單次確認請求：對一場「未落在 G4 保存樣本內」的完成場重取 schema。 | ⚠️ 未查證 |
| `probe_inning_pitcher.py` | 一次性產物 | `docs/research/INGEST-SCORELESS-INNING-PITCHER1/` | ✅ | 唯讀 | ✅ --help 安全 | INGEST-SCORELESS-INNING-PITCHER1 | INGEST-SCORELESS-INNING-PITCHER1：stats.cpbl 單場 API 逐局責任投手粒度查證。 | ⚠️ 未查證 |
| `build_cases.py` | 一次性產物 | `docs/research/ML-PITCHER-ER-REBUILD1/cases/` | ⚠️ `docs/research/ML-PITCHER-ER-REBUILD1/` | 唯讀 | ⚠️ --help 不安全 | ML-PITCHER-ER-REBUILD1 | `earned_rule_boundary` 分層討論案例集產生器（唯讀，不改任何計算碼）。 | ⚠️ 未查證 |
| `gate_ablation.py` | 一次性產物 | `docs/research/ML-PITCHER-ER-REBUILD1/` | ✅ | 唯讀 | ⚠️ --help 不安全 | ML-PITCHER-ER-REBUILD1 | 逐 fail-closed 閘門的消融對照（卡面紅線「fail-closed 不得雙向濫用」的證據產生器）。 | ⚠️ 未查證 |
| `rebuild_er.py` | 一次性產物 | `docs/research/ML-PITCHER-ER-REBUILD1/` | ✅ | 唯讀 | ✅ --help 安全 | ML-PITCHER-ER-REBUILD1 | ML-PITCHER-ER-REBUILD1：從 `cpbl.game_livelog` 逐事件重建每位投手每場的 自責分（earned runs）、失分（runs）與出局數（outs），並與官方 `cpbl.pitching_gamelog` **三維對帳**。 | ⚠️ 未查證 |
| `bin_stability.py` | 一次性產物 | `docs/research/ML-WP-VAL-RESAMPLE1/` | ✅ | 唯讀 | ✅ --help 安全 | ML-WP-VAL-RESAMPLE1 | ML-WP-VAL-RESAMPLE1：池化十分位「顯著性」對 bootstrap seed 的穩健度（唯讀）。 | ⚠️ 未查證 |
| `census.py` | 一次性產物 | `docs/research/ML-WP-VAL-RESAMPLE1/` | ✅ | 唯讀 | ✅ --help 安全 | ML-WP-VAL-RESAMPLE1 | ML-WP-VAL-RESAMPLE1：受影響打席母體的**逐季**普查（唯讀；由指令產生，非人工聲明）。 | ⚠️ 未查證 |
| `compare.py` | 一次性產物 | `docs/research/ML-WP-VAL-RESAMPLE1/` | ✅ | 唯讀 | ✅ --help 安全 | ML-WP-VAL-RESAMPLE1 | ML-WP-VAL-RESAMPLE1：VAL1 指標的三路對照（canonical / 今日舊讀法 / 今日修正）。 | ⚠️ 未查證 |
| `budget_trace.py` | 一次性產物 | `docs/research/ML-WP-VERDICT-ROBUST1/` | ✅ | 唯讀 | ✅ --help 安全 | ML-WP-VERDICT-ROBUST1 | ML-WP-VERDICT-ROBUST1 §A — 邊界分箱在 v2 與 v3 兩種讀法下的可重現性實測。 | ⚠️ 未查證 |
| `compare_verdicts.py` | 一次性產物 | `docs/research/ML-WP-VERDICT-ROBUST1/` | ✅ | 唯讀 | ✅ --help 安全 | ML-WP-VERDICT-ROBUST1 | ML-WP-VERDICT-ROBUST1 §C — 同一份資料、同一份指標，只換判定規則的逐 scope 對照。 | ⚠️ 未查證 |
| `analyze_gates.py` | 一次性產物 | `docs/research/RESEARCH-VERDICT-AUDIT1/` | ✅ | 唯讀 | ✅ --help 安全 | RESEARCH-VERDICT-AUDIT1 | RESEARCH-VERDICT-AUDIT1 §2 — 對否定判定的決定性閘門做「雜訊底線」重算。 | ⚠️ 未查證 |
| `audit_io.py` | 一次性產物 | `docs/research/RESEARCH-VERDICT-AUDIT1/` | ✅ | 唯讀 | ⚠️ --help 不安全 | RESEARCH-VERDICT-AUDIT1 | 本卡三支腳本共用的輸出／驗證入口。 | ⚠️ 未查證 |
| `build_verdict_list.py` | 一次性產物 | `docs/research/RESEARCH-VERDICT-AUDIT1/` | ✅ | 唯讀 | ✅ --help 安全 | RESEARCH-VERDICT-AUDIT1 | RESEARCH-VERDICT-AUDIT1 §3 — 把窮舉母體與逐檔處置合成裁決清單，並硬性檢查覆蓋。 | ⚠️ 未查證 |
| `scan_verdicts.py` | 一次性產物 | `docs/research/RESEARCH-VERDICT-AUDIT1/` | ✅ | 唯讀 | ✅ --help 安全 | RESEARCH-VERDICT-AUDIT1 | RESEARCH-VERDICT-AUDIT1 §1 — 否定判定的指令窮舉掃描。 | ⚠️ 未查證 |
| `bases_outs_extraction_proof.py` | 一次性產物 | `docs/research/UX-HOME-LIVE-STRIP1/` | ✅ | 唯讀 | ⚠️ --help 不安全 | UX-HOME-LIVE-STRIP1 | UX-HOME-LIVE-STRIP1 取證工具：證明壘包圖上抽為共用元件後，賽況頁的渲染輸出沒有變。 | ⚠️ 未查證 |
| `scan_time_semantics.py` | 常設工具 | `docs/research/TIME-SEMANTICS-CONTRACT1/` | ✅ | 唯讀 | ✅ --help 安全 | TIME-SEMANTICS-CONTRACT1 | TIME-SEMANTICS-CONTRACT1：時間語意用點盤點（**唯讀**，artifact 由本腳本產生）。 | ⚠️ 未查證 |

## 清冊：`pyproject [project.scripts]`（47）

| CLI | 寫入 | runnable | purpose_declared | purpose_verified |
|---|---|---|---|---|
| `cpbl-anchor-career` | **寫** | ✅ --help 安全 | CLI：錨定生涯分項基底（一次性/重錨用）。 | ⚠️ 未查證 |
| `cpbl-backfill` | **寫** | ✅ --help 安全 | CLI 入口：套用 migration + 從 cpbl-opendata 回填。 | ⚠️ 未查證 |
| `cpbl-backfill-season` | **寫** | ✅ --help 安全 | CLI：以官方 teamscore 回填某年的 season-level 彙總（opendata 未涵蓋年份，如 2025）。 | ⚠️ 未查證 |
| `cpbl-build-championships` | **寫** | ✅ --help 安全 | CLI：重建年度總冠軍成員表（不爬蟲，純由已入庫資料重建）。 | ⚠️ 未查證 |
| `cpbl-build-features` | **寫** | ✅ --help 安全 | CLI：建賽果預測特徵表（cpbl.game_features）。 | ⚠️ 未查證 |
| `cpbl-build-pa` | **寫** | ✅ --help 安全 | CLI：物化 canonical PA build 並回填（GAME-RECAP-PA1-BUILD1）。 | ⚠️ 未查證 |
| `cpbl-build-sabr` | **寫** | ✅ --help 安全 | CLI：重建 sabermetrics 打底表 + Phase A 進階指標（livelog 2018+ 推算 / 官方計數）。 | ⚠️ 未查證 |
| `cpbl-build-splits` | **寫** | ✅ --help 安全 | CLI：重算本季分項（splits + vs各隊）寫回四張官方表，取代本季 apart/vs-team 爬蟲。 | ⚠️ 未查證 |
| `cpbl-check-coverage` | 唯讀 | ✅ --help 安全 | CLI：資料涵蓋率排查（唯讀、不爬網）——抓「應有卻缺漏」的場次。 | ⚠️ 未查證 |
| `cpbl-classify-pitches` | **寫** | ✅ --help 安全 | CLI：離線推算球種，寫回 pitch_tracking.pitch_type_pred。 | ⚠️ 未查證 |
| `cpbl-classify-pitches-v2` | **寫** | ✅ --help 安全 | 球種細分 v2（ML-PT2 Phase2）：MLB 標籤遷移 cluster-then-label。 | 手動觸發：球種細分 v2，未接排程（memory：二軍／生產未同步） |
| `cpbl-ingest-editorial` | **寫** | ✅ --help 安全 | CLI for validated Google Sheets editorial ingest. | ⚠️ 未查證 |
| `cpbl-live-game` | 唯讀 | ✅ --help 安全 | CLI【實驗】：賽況即時 TrackMan 單次探測（不寫 DB、不掛排程；等使用者下令實測）。 | ⚠️ 未查證 |
| `cpbl-live-worker` | 唯讀 | ✅ --help 安全 | 集中式 stats live worker；預設關閉，需 ``LIVE_GAME_WORKER_ENABLED=true``。 | ⚠️ 未查證 |
| `cpbl-reconcile-advanced` | **寫** | ✅ --help 安全 | CLI：一次性修復污染的 advanced_stats + 建立完整快照（INGEST-ADV-RECONCILE1）。 | ⚠️ 未查證 |
| `cpbl-refresh-box-deep` | **寫** | ✅ --help 安全 | CLI：深度重抓近 N 天已完成場的 box（DATA-BOX-REVISION-SNAPSHOT1 深度層）。 | ⚠️ 未查證 |
| `cpbl-refresh-recent` | **寫** | ⚠️ --help 不安全（具名例外） | CLI：抓昨天/今天比賽需更新的數值，並寫入刷新紀錄、偵測缺漏。 | 每日鏈主要寫入者，566 行；⚠️ --help 觸及 cpbl.db.migrate（#53 凍結） |
| `cpbl-research-umpire-impact` | 唯讀 | ✅ --help 安全 | ML-UMP1 離線研究 CLI；不寫 production table，也不由 API 觸發。 | 632 行研究入口，零活引用；產物落檔案不落 DB |
| `cpbl-scrape-advanced` | **寫** | ✅ --help 安全 | CLI：全量抓本季官方進階 leaderboard 並原子晉升 current snapshot。 | ⚠️ 未查證 |
| `cpbl-scrape-awards` | **寫** | ✅ --help 安全 | CLI：抓官網年度獎項 → cpbl.player_awards（本機台灣 IP；一次性 + 手動刷新）。 | 手動觸發：官方獎項，卡台灣 IP 需本機探查 |
| `cpbl-scrape-bio` | **寫** | ✅ --help 安全 | CLI：爬選手 bio 細項（身高體重/初出場/學歷/出生地/選秀）寫回 players。 | ⚠️ 未查證 |
| `cpbl-scrape-coaches` | **寫** | ✅ --help 安全 | CLI：爬現役球團教練團（官網 /team/index）。 | ⚠️ 未查證 |
| `cpbl-scrape-coaches-history` | **寫** | ✅ --help 安全 | CLI 入口：爬取 TwBsBall 個人經歷節（教練／球員）並入庫 cpbl.person_history。 | 手動觸發：twbsball 隊史教練團，一次抓＋手動刷新 |
| `cpbl-scrape-detail` | **寫** | ✅ --help 安全 | CLI：爬本季登錄選手的「對戰各隊成績」+「分項成績」。 | ⚠️ 未查證 |
| `cpbl-scrape-field` | **寫** | ✅ --help 安全 | CLI：爬官網 /field 球場規格 enrich venue_dim（一次性 + 手動刷新）。 | ⚠️ 未查證 |
| `cpbl-scrape-fighting` | **寫** | ✅ --help 安全 | CLI：爬本季登錄打者的「投打對決」(batter-vs-pitcher)。 | ⚠️ 未查證 |
| `cpbl-scrape-game-pitches` | **寫** | ✅ --help 安全 | CLI：以「單場 API」為單位抓逐球 TrackMan（INGEST-GAME-TM-REFACTOR1）。 | ⚠️ 未查證 |
| `cpbl-scrape-gamelog` | **寫** | ✅ --help 安全 | CLI：回填本季每場賽況（逐局比分 + 逐打席事件流）。 | ⚠️ 未查證 |
| `cpbl-scrape-games` | **寫** | ✅ --help 安全 | CLI：爬官網逐場賽程/結果（一軍：例行賽 A + 總冠軍賽 C + 季後挑戰賽 E）。 | ⚠️ 未查證 |
| `cpbl-scrape-home-runs` | **寫** | ✅ --help 安全 | 低頻執行 /stats/hr 逐轟 audit ingest（只限本機白天）。 | 手動觸發：全壘打紀錄 |
| `cpbl-scrape-legends` | **寫** | ✅ --help 安全 | CLI：抓「退役傳奇／現任教練」的生涯分項成績（getapartscore 9999 A/C/E）。 | 手動觸發：退役／教練生涯分項 |
| `cpbl-scrape-managers` | **寫** | ✅ --help 安全 | CLI：抓維基百科歷任總教練 → cpbl.managers（一次性 + 手動刷新，不掛 cron）。 | ⚠️ 未查證 |
| `cpbl-scrape-overseas` | **寫** | ✅ --help 安全 | CLI：抓淡江棒球維基旅外列表 → cpbl.overseas（一次性 + 手動刷新，不掛 cron）。 | 手動觸發：旅外資料（twbsball query API） |
| `cpbl-scrape-pitches` | **寫** | ✅ --help 安全 | CLI：回填逐球 TrackMan 追蹤資料（stats.cpbl logs API）。 | ⚠️ 未查證 |
| `cpbl-scrape-retired` | **寫** | ✅ --help 安全 | CLI：抓維基各隊退休背號 → cpbl.retired_numbers（一次性 + 手動刷新，不掛 cron）。 | 手動觸發：退役名單 |
| `cpbl-scrape-roster` | **寫** | ✅ --help 安全 | CLI：爬官方球隊登錄名單（官網 /team/index 的 TeamPlayersList）。 | 手動觸發：登錄名單 |
| `cpbl-scrape-standings` | **寫** | ✅ --help 安全 | CLI：爬官方球隊戰績（含上下半季：和局/勝差/淘汰指數/H2H/主客場/連勝敗/近十場）。 | ⚠️ 未查證 |
| `cpbl-scrape-stats` | **寫** | ✅ --help 安全 | CLI：爬本季投手成績（ERA + 進階指標 + 名字）。 | ⚠️ 未查證 |
| `cpbl-scrape-transactions` | **寫** | ✅ --help 安全 | CLI：爬官網球員異動（升一軍/降二軍）→ player_transactions。 | ⚠️ 未查證 |
| `cpbl-scrape-wiki` | **寫** | ✅ --help 安全 | CLI：抓維基百科個人頁 infobox（所屬球隊／國際賽獎牌／獎項）→ cpbl.wiki_*。 | ⚠️ 未查證 |
| `cpbl-shadow-game-tm` | **寫** | ✅ --help 安全 | CLI：INGEST-GAME-TM-REFACTOR1 Gate 3 — shadow harness 觀測週期（每日手動觸發）。 | ⚠️ 未查證 |
| `cpbl-train` | **寫** | ✅ --help 安全 | 訓練與回測打擊成績預測：Marcel baseline vs LightGBM。 | ⚠️ 未查證 |
| `cpbl-train-outcome` | **寫** | ✅ --help 安全 | 賽事預測：時間切分回測對照（LightGBM vs 邏輯回歸 vs 全押主場 baseline）。 | ⚠️ 未查證 |
| `cpbl-train-outcome-simple` | **寫** | ✅ --help 安全 | 固定語意群賽前模型：離線回測、閘門、artifact 與 metrics 持久化。 | ⚠️ 未查證 |
| `cpbl-train-pa-sim` | **寫** | ✅ --help 安全 | 單一打席模型：覆蓋率、走查、artifact 與 metrics 持久化。 | ⚠️ 未查證 |
| `cpbl-train-pitching` | **寫** | ✅ --help 安全 | 訓練與回測投手成績預測：Marcel（投手版）baseline vs LightGBM。 | ⚠️ 未查證 |
| `cpbl-verify-splits` | 唯讀 | ✅ --help 安全 | CLI：驗證「重算分項」對照「官方爬取分項」——Phase 0 harness。 | ⚠️ 未查證 |

## 已知陷阱（疑似重複群組的裁定結果）

### TM 四支：不是重複，但參數不一致

`reconcile_game_tm`（Gate 2：單場 API vs 逐投手 logs API）、`dryrun_game_tm_fullseason`（G4 Phase A：單場 API vs 正式表存量）、`verify_deep_tm_backfill`（本機 DB vs 生產 DB）、`sync_deep_tm_prod`（寫生產）——四個不同的對照兩端，零重疊。

⚠️ **四支全部把年份釘死 2026**（前兩支是 argparse 預設，後兩支是 SQL 字面），且 `reconcile_game_tm` 預設 `--kind A`、`dryrun_game_tm_fullseason` 預設 `--kinds A D`——**對同一批資料的預設母體不同，而差異沒寫在任何一支的 docstring 裡**。

### `reconcile_*` 字首同時指涉唯讀對帳與破壞性重建

`reconcile_game_tm` 與 `reconcile_scoreless_streak` 是**純唯讀**；`reconcile_splits_recalc1 --apply` 會**實際呼叫 `build_splits()` 重建 2018–2026 A/D**。檔名看不出這個差別——本清冊的「寫入」欄是唯一分得出來的地方。

### splits 三支：診斷 → 報告守衛 → 修復對帳，一條鏈的三段

`verify_splits_pa_split1`（`SET TRANSACTION READ ONLY` 診斷）→ `check_splits_pa_split1_results`（把 RESULTS.md 的數字對回 artifact）→ `reconcile_splits_recalc1`（`--apply` 重建）。不是重複。

### 無自責分三支：三個不同層

`reconcile_scoreless_streak`（窮舉對帳，全史 2018+、A＋D）、`compare_runless_vs_er_streak`（逐人對照，預設只 2026 一軍——差異有寫在 docstring 裡）、`check_scoreless_null_folding`（AST 靜態掃描，完全不碰 DB）。

⚠️ `check_scoreless_null_folding` 的 `TARGETS` 是**硬編三個檔案路徑**，新增的相關檔案不會自動納入，且它**未接上 pytest**——這個守衛從交付至今未被自動跑過。

### bio 兩支：寫入欄位零重疊

`backfill_player_bio_gap1` 補 `country`／`birthday`；`backfill_player_bio_gap2` 補 `bats`／`throws`／`height_cm`／`weight_kg`／`debut`／`education`／`birthplace`／`draft`。不是重複，但檔名 `gap1`／`gap2` 看不出補的是不同欄位。

### 三支自稱守衛但從未接上觸發器

`check_scoreless_null_folding`、`check_splits_pa_split1_results`、`ibb_ghost1_probe` 的 docstring 都自稱「防再犯守衛／不符即 exit 1」，但**沒有任何測試或排程載入它們**。它們的防護是名義上的——這是「告警沒有讀者等於沒有告警」在腳本層的同構物。

## 位置例外（分類正確但刻意不搬）

| 入口 | 理由 |
|---|---|
| `docs/research/DEV-CLI-HELP-GUARD1/audit_cli_help.py` | 推導判 CI 繫結（`tests/test_cli_help_guard.py::test_seal_surface_matches_audit_tool` 以硬編路徑載入它防兩份 seal 漂移），但它是 DEV-CLI-HELP-GUARD1 的**交付產物**、已住在自己卡的目錄裡。搬它要同時改 `tests/test_cli_help_guard.py` 的路徑常數與 `docs/research/DEV-CLI-HELP-GUARD1/cli-help-audit.md`——後者射程外 |
| `docs/research/TIME-SEMANTICS-CONTRACT1/scan_time_semantics.py` | ⚠️ **本卡掃出來的既有不一致**：`docs/TIME_SEMANTICS_CONTRACT.md:243` 給了重跑指令（`uv run python docs/research/…/scan_time_semantics.py --verify`），依推導規則屬常設工具，卻住在 research 卡目錄。判準與位置真的不符，但它是 TIME-SEMANTICS-CONTRACT1 的交付產物，搬它要改活契約——射程外。列為交付報告的待裁項 |
| `scripts/data_rules_audit1.py` | scripts/data_tie_remedy1.py 的 FROZEN_FILES 以**字面路徑**硬編它，而 CI 只 import `_streaks_for` 碰不到 `is_frozen`——搬走會讓守衛靜默回 False。凍結理由是「必須能重現當初的數字」，動它會讓歷史證據不可重現 |
| `scripts/g4_phase_a_metrics.py` | 同上：FROZEN_FILES 字面路徑成員判定，凍結理由是「判準一換觀測就不可比」 |
| `scripts/verify_deep_tm_backfill.py` | 需求方裁定 3：它是活卡 DEV-VERIFY-TM-ASSERTS1（T2、Backlog）的射程本體，搬它等於改另一張活卡的資源路徑。例外具名可讀，勝過偷改別卡 |

## 觀測面限制

- **「未找到消費者」不等於「沒有消費者」**：本清冊的觀測面只有 **git 追蹤檔案**。本機執行歷史、需求方手動操作、封存前的口頭流程都不在裡面。用詞一律「未找到」。
- **本輪零刪除**。已用盡的只標記，刪除是需求方的獨立裁定。
- 位置不變式證明的是「位置與分類一致」，**不是「分類是對的」**。分類含具名人工改判，機器只驗一致性不驗真假。
- **分段路徑**（`"scripts/" + name` 這類靜態解析不了的組裝）共 49 處，引用完整性檢查涵蓋不到，逐處列出：`docs/research/TIME-SEMANTICS-CONTRACT1/scan_time_semantics.py:149`、`scripts/data_rules_audit1.py:761`、`scripts/data_tie_remedy1.py:322`、`scripts/script_inventory.py:68`、`scripts/script_inventory.py:302`、`scripts/script_inventory.py:306`、`scripts/script_inventory.py:838`、`scripts/script_inventory.py:980`、`scripts/script_inventory.py:1438`、`tests/test_backup_prod_db.py:16`、`tests/test_backup_prod_db.py:186`、`tests/test_backup_prod_db.py:196`、`tests/test_backup_prod_db.py:203`、`tests/test_bio_gap2_backfill.py:19`、`tests/test_bio_gap_backfill.py:27`、`tests/test_prod_sync_revision_seq.py:33`、`tests/test_prod_sync_revision_seq.py:183`、`tests/test_prod_sync_revision_seq.py:184`、`tests/test_prod_sync_revision_seq.py:185`、`tests/test_prod_sync_revision_seq.py:216`、`tests/test_refresh_pitch_ingest.py:26`、`tests/test_refresh_remote_train.py:20`、`tests/test_review_prompt.py:7`、`tests/test_roadmap_lines.py:28`、`tests/test_scrape_daily.py:32`、`tests/test_scrape_daily.py:33`、`tests/test_scrape_daily.py:115`、`tests/test_scrape_daily.py:132`、`tests/test_scrape_daily.py:156`、`tests/test_scrape_daily.py:310`、`tests/test_script_inventory.py:243`、`tests/test_script_inventory.py:281`、`tests/test_script_inventory.py:327`、`tests/test_script_inventory.py:341`、`tests/test_script_inventory.py:349`、`tests/test_script_inventory.py:357`、`tests/test_script_inventory.py:369`、`tests/test_script_inventory.py:422`、`tests/test_script_inventory.py:480`、`tests/test_script_inventory.py:485`、`tests/test_script_inventory.py:486`、`tests/test_script_inventory.py:487`、`tests/test_script_inventory.py:558`、`tests/test_shell_help_guard.py:289`、`tests/test_shell_help_guard.py:361`、`tests/test_state_plane_migrate.py:16`、`tests/test_task_card_sections.py:8`、`tests/test_verify_refresh_info.py:27`、`tests/test_workflow_ledger.py:5`

