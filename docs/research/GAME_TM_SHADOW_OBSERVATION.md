# INGEST-GAME-TM-REFACTOR1 Gate 3 — Shadow 觀測窗記錄

> 執行者：Sonnet 5（2026-07-24）。本檔記錄 Gate 3 shadow harness 的設計、對帳基準、
> 觀測窗啟動時間與凍結範圍，供續作者（Gate 4 執行者／查核者）銜接，不進
> `docs/control-plane/**` 或 `docs/TASKS.md`（依卡片指示，執行分支不得動這兩處）。

## 1. 設計摘要

**不重寫 Gate 1-2 產物**：`src/cpbl/ingest/game_tm_shadow.py` 只 import 既有的
`parse_pitches`／`_fetch_game_livelog`／`completed_game_snos`（`cpbl_pitch_tracking.py`），
自己不重新實作抓取或解析。四張隔離表（migration `065_game_tm_shadow.sql`）：

| 表 | 用途 |
|---|---|
| `cpbl.game_tm_shadow_runs` | 每次觀測週期一列：窗口參數、抓取/略過計數、對帳摘要 |
| `cpbl.game_tm_shadow_schedule_obs` | 賽程 shadow（append-only，不去重）：保存 `GameStatus`／`SkipTrackman` 隨時間的原始快照 |
| `cpbl.game_tm_shadow_pitch_tracking` | 單場 API 產出的逐球資料，欄位=`cpbl_pitch_tracking._COLS` 存成 jsonb row；**絕不是** `cpbl.pitch_tracking`，正式 writer/查詢完全不碰 |
| `cpbl.game_tm_shadow_diffs` | 每次 run 的差異清單（append-only；「最近一次 run 的列」＝目前未解差異） |

CLI：`uv run cpbl-shadow-game-tm [year] [kind] [window_days]`（預設本季 A、近 3 天窗口）／
`uv run cpbl-shadow-game-tm --report`（不重跑，只印最近一次 run 摘要+未解差異）。

## 2. 對帳基準與邊界覆蓋

`run_shadow_cycle()`：

1. 抓賽程 shadow（`/api/proxy/v1/games/schedule?kindCode=&year=&month=`），依 `GameStatus`
   分桶。**實測值域（2026-07-24）**：`FINISHED`／`SCHEDULED`（未開打）／`POSTPONED`（延期）／
   `RESERVED`（保留賽）。`RESERVED` 與 `SCHEDULED` 皆 `Score` 恆 0-0，**不能靠比分分辨**，
   只能看官方 `GameStatus`——這正是卡片點名「0-0 未開打」與「保留賽」邊界的官方依據。
   未知狀態（官方未來新增值）進 `UNKNOWN` 桶，記 `unknown_schedule_status` 異常，不當完成場、不崩潰。
2. **`GameSno` 多筆歷史記錄防呆**：同一 `game_sno` 延期/保留賽改期後會在賽程 feed 留下多筆
   （`PreExeDate` 不同）。實測 `2026-A-151`：`POSTPONED@06-09` → `RESERVED@06-25` →
   `FINISHED@06-28` 三筆同時存在同月回應。`dedupe_latest_per_game()` 以最新 `PreExeDate`
   者為現況判定依據，避免舊記錄蓋掉後來的 FINISHED；`schedule_obs` 仍保存全部原始列
   （不去重），可看到完整狀態演變。
3. 與本機 `cpbl.games` 完成場判定（`completed_game_snos`）交叉核對：本機已判完成
   （score>0 且 date<=今日）但官方狀態非 FINISHED，記 `schedule_status_mismatch`
   （對應記憶 `completed-game-judgment` 點名的保留賽誤判風險）；反向（官方 FINISHED
   但本機尚未同步）記 `local_lag`，僅供觀察不算錯誤。
4. 只對官方 **FINISHED** 場打單場 API，寫入隔離 shadow 表；**不動** `cpbl.pitch_tracking`。
5. 讀正式 `cpbl.pitch_tracking`（唯讀）做同一組場次的 PK 集合＋逐格欄位對帳，比對邏輯
   與 `scripts/reconcile_game_tm.py` 相同（PK only_shadow/only_prod + cell mismatch）。
6. `SkipTrackman=true` 卻仍觀測到逐球資料只記錄 `skip_trackman_anomaly` 供人工檢視，不算錯誤
   （官方旗標語意單向：true=明確 skip，false 不保證資料完整或缺失）。

### 2.1 踩雷：float4 儲存精度誤判（已修正）

`cpbl.pitch_tracking` 多數物理欄位是 `real`（float4），shadow 表用 jsonb 保存
`parse_pitches` 算出的原生 Python float（float64）。**首次 bootstrap 直接 `==` 比對，
6 場 1184 列全部「假陽性」不一致**（如 `rel_side` prod=`0.4585777` vs shadow=`0.458577696`
——同一值，只是儲存精度不同）。修正：比對前對 `_REAL_F4_COLS`（`rel_speed`／`spin_rate`／
`rel_side`／`rel_height`／`extension`／`zone_speed`／`plate_loc_side`／`plate_loc_height`／
`hit_exit_speed`／`hit_launch_angle`／`hit_direction`／`hit_distance`／`hit_hang_time`／
`traj_accel_y`／`traj_accel_z`／`zone_time`／`ivb_cm`／`hb_cm`）做一次 float4 round-trip
再比較；migration 064 新增的 `double precision` 欄位（`traj_x0..z2`／`hit_landing_bearing`／
`hit_spin_rate`）全精度直接比對，不受影響。單元測試見
`tests/test_game_tm_shadow.py::test_diff_rows_ignores_float4_storage_precision_noise`。

## 3. 觀測窗啟動記錄

- **啟動時間**：2026-07-24（Asia/Taipei），`run_id=3`（`cpbl.game_tm_shadow_runs`）。
- **Day 1 bootstrap 結果**：`year=2026 kind=A window_days=5`，賽程 shadow 觀測 9 場
  （6 FINISHED、3 SCHEDULED、0 POSTPONED/RESERVED/UNKNOWN），成功打 6 場單場 API，
  對正式 `pitch_tracking`（共 1184 列）**0 差異**（PK 集合、逐格欄位皆一致，含 float4
  精度修正後）。
- **凍結範圍（🔴 違反＝重置 14 天觀測期）**：`src/cpbl/ingest/cpbl_pitch_tracking.py`
  （parser／單場 fetch）、`src/cpbl/ingest/run_refresh_recent.py`（逐球 refresh 正式路徑）、
  `src/cpbl/ingest/game_tm_shadow.py` 的比較邏輯（`diff_rows`／`diff_schedule_status`／
  `_cell_equal`／`dedupe_latest_per_game`）、`cpbl.pitch_tracking` schema 或正式寫入契約。
  `SkipTrackman=false` 不得被映射成 tracking available／complete。

## 4. 續作程序（每日手動觸發，14 天）

```bash
cd ~/Dev/cpbl-analytics   # 或本卡 worktree：.claude/worktrees/ingest-game-tm-refactor1-g3-execution
uv run cpbl-shadow-game-tm          # 本季 A，近 3 天窗口，跑一次觀測週期（冪等，可安心每天重跑）
uv run cpbl-shadow-game-tm --report # 不重跑，只看最近一次摘要 + 未解差異
```

- 每次執行只寫隔離 `cpbl.game_tm_shadow_*` 表，與正式 `cpbl-scrape-pitches`／
  `cpbl-refresh-recent` 完全獨立、互不影響，可與現行每日爬蟲同一天執行。
- 觀察 `games_skipped_reserved`／`games_skipped_postponed`／`unknown_schedule_status`
  是否有非預期增長；`diffs_found > 0` 時用 `--report` 或直接查
  `cpbl.game_tm_shadow_diffs WHERE run_id=(SELECT max(id) FROM cpbl.game_tm_shadow_runs)`
  檢視細節。
- 查詢觀測窗已進行天數：`SELECT now() - min(started_at) FROM cpbl.game_tm_shadow_runs;`
  （CLI 每次執行也會印出）。

## 5. Gate 4 晉升條件（本卡不做，另開卡）

滿足以下條件後才可另開 `INGEST-GAME-TM-REFACTOR1-G4` cutover 卡：

1. 觀測窗達 **14 天**（`observation_window_days()` ≥ 14）。
2. 期間**每日** run 的 `diffs_found` 皆為 0，或所有非零差異皆已人工複核為可解釋的
   已知邊界（如 `local_lag` 純屬時間差，非資料錯誤）。
3. 至少涵蓋一次真實的延期／保留賽／未開打場次觀測（`games_skipped_postponed`／
   `games_skipped_reserved`／`games_skipped_scheduled` 至少各出現過非零值，證明分類邏輯
   在真實資料上跑過這些分支，不只是單元測試）。
4. Gate 4 cutover 本身須由跨模型家族且非本卡執行者查核，並取得需求方 production
   sign-off 才可切換 `run_refresh_recent.py` 的逐球正式路徑。
