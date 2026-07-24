---
title: "GAME-RECAP-PA1-TAXONOMY1 獨立審核報告"
card_id: GAME-RECAP-PA1-TAXONOMY1
status: APPROVED
reviewer_identity: "Google DeepMind Antigravity AI (Gemini 3.6 Flash)"
execution_actor: "Claude Opus 4.8"
execution_commit: "70e22c78c25a11d27471696dde0fd45a7371c222"
execution_branch: "ai/opus-4-8/GAME-RECAP-PA1-TAXONOMY1"
review_date: 2026-07-24
---

# GAME-RECAP-PA1-TAXONOMY1 獨立審核報告

> **審核裁決：`APPROVE`**
>
> 查核者身分：**Google DeepMind Antigravity AI (Gemini 3.6 Flash)**，確與執行者（Claude Opus 4.8）屬不同模型家族。
> 本審核報告所有測試指令、SQL dump、重跑 diff 均由查核者於本機環境親自執行與證偽，無任何腦補或覆述。

---

## 1. 驗收閘門實測結果

### 閘門 1：異動範圍與程式規範（Scope & Lint & Test Cleanliness）
- **異動檔案數**：`git show --stat 70e22c7` 證明 commit `70e22c7` 僅變更 5 個指定檔案：
  1. `docs/design/GAME-RECAP-PA1-TAXONOMY1.md`
  2. `docs/design/pa_transition_taxonomy.v1.json`
  3. `docs/research/GAME-RECAP-PA1-TAXONOMY1_RESULTS.md`
  4. `scripts/pa_transition_taxonomy.py`
  5. `tests/test_pa_transition_taxonomy.py`
  無 `migrations/**`、無 `src/cpbl/**` 產品碼變動、無 DB 寫入。
- **Ruff 檢查**：
  ```bash
  $ uv run ruff check
  All checks passed!
  ```
- **單元測試**：
  ```bash
  $ uv run pytest tests/test_pa_transition_taxonomy.py -q
  .................                                                        [100%]
  17 passed in 0.12s
  ```
- **全站迴歸測試**：
  ```bash
  $ uv run pytest -q
  396 passed, 3 skipped, 1 warning in 8.40s
  ```

### 閘門 2：證據可重跑性與逐位元對比（Reproducibility）
- **重跑指令**：
  ```bash
  uv run python scripts/pa_transition_taxonomy.py --from-year 2018 --to-year 2026 \
    --kind A --kind C --kind D --kind E \
    --json /tmp/tax.json --output /tmp/tax.md
  ```
- **Diff 比對**：
  ```bash
  $ diff /tmp/tax.json docs/design/pa_transition_taxonomy.v1.json
  3c3
  <   "generated_at": "2026-07-24 11:06:37.382623+08:00",
  ---
  >   "generated_at": "2026-07-24 10:48:23.660667+08:00",

  $ diff /tmp/tax.md docs/research/GAME-RECAP-PA1-TAXONOMY1_RESULTS.md
  24c24
  < - 重建 island 總數：330268；耗時 12.31 秒；產生時間 2026-07-24 11:06:37.382623+08:00。
  ---
  > - 重建 island 總數：330268；耗時 12.121 秒；產生時間 2026-07-24 10:48:23.660667+08:00。
  ```
  **結論**：JSON 與 MD 產物除 `generated_at` 時間戳與秒數外，100% 逐位元完全一致。

### 閘門 3：值域覆蓋與反名稱猜測（100% Action Login & Signal Alignment）
- **DB 真值比對**：
  ```sql
  SELECT DISTINCT action_name FROM cpbl.game_livelog WHERE COALESCE(action_name,'')<>'' ORDER BY 1;
  ```
  DB 共 58 個相異 `action_name`。`TERMINAL_TAXONOMY` 亦登錄 58 個項目（去除字尾空白後 100% 映射），無任何漏登錄。
- **客觀效果驗證**：
  - `out` 指派（20 個）：`batter_out_rate` 介於 0.966～1.000，`hit_rate` = 0.000。
  - `hit` 指派（10 個）：`hit_rate` 介於 0.988～1.000，`batter_out_rate` = 0.000。
  - `walk` / `hbp` 指派（4 個）：`walk_hbp_rate` 介於 0.977～0.998。
  - `reach_on_error` 指派（5 個）：`reach_error_rate` 介於 0.997～1.000，`batter_out_rate` = 0.000。
  - `fielders_choice` 指派（4 個）：reach 高或特定選擇，`hit` = 0, `walk` = 0。
  - `sacrifice` 指派（6 個）：`batter_out_rate` 介於 0.992～1.000，但屬規則犧牲獨立分家。
  - `uncaught_third_strike` 指派（5 個）：不死三振家族獨立分類，不強行填補打者出局/上壘命運，留給 builder 依 outcome 細節判定（fail-closed）。
  - `non_pa` 指派（`突破僵局上壘`）：所有打者指標皆為 0.000，證明純屬 runner placement，非 PA。

---

## 2. 獨立複核紅燈案例原始 DB 事件

### 案例 A：同局同打者二度上場（2026/A/54 第 1 局 郭天信）
**PSQL Dump**:
```text
 main_event_no | out_cnt | ball_cnt | strike_cnt | pitch_cnt | cp | se | hitter_name | pitcher_name | action_name | left
---------------+---------+----------+------------+-----------+----+----+-------------+--------------+-------------+----------------------------------
 0110001000    |       0 |        1 |          0 |         1 |  0 |  0 | 郭天信      | 後勁         | 一壘安打    | 壞球。
 0110004000    |       0 |        1 |          2 |         4 |  0 |  0 | 郭天信      | 後勁         | 一壘安打    | 擊出中外野平飛球，一壘安打 。
 ... (中間經過 8 位打者輪轉) ...
 0110041000    |       2 |        0 |          1 |        37 |  0 |  0 | 郭天信      | 後勁         | 刺殺        | 擊出界外球。
 0110042000    |       2 |        0 |          1 |        38 |  0 |  0 | 郭天信      | 後勁         | 刺殺        | 擊出內野滾地球， 打者-三壘手 傳一壘手刺殺出局...
```
**複核**：`(inning, pitcher, hitter)` 三鍵會將 pc 1-4（安打）與 pc 37-38（刺殺）誤併為單一 PA。Island detection 正確判斷為 2 個非連續 PA island。

### 案例 B：打席中換投（2025/A/52 第 8 局 陳思仲）
**PSQL Dump**:
```text
 main_event_no | out_cnt | ball_cnt | strike_cnt | pitch_cnt | cp | se | hitter_name | pitcher_name | action_name | left
---------------+---------+----------+------------+-----------+----+----+-------------+--------------+-------------+----------------------------------
 081001000     |       2 |        0 |          0 |         9 |  1 |  0 | 陳思仲      | 張瑞麟       | 四壞球      | 更換投手：張瑞麟=>林旺熙。
 081002000     |       0 |        1 |          0 |         1 |  0 |  0 | 陳思仲      | 林旺熙       | 四壞球      | 壞球。
 081003000     |       0 |        2 |          0 |         2 |  0 |  0 | 陳思仲      | 林旺熙       | 四壞球      | 壞球。
 081004000     |       0 |        2 |          0 |         0 |  1 |  1 | 陳思仲      | 李吳永勤     | 四壞球      | 更換投手：林旺熙=>李吳永勤
 081005000     |       0 |        2 |          1 |         1 |  0 |  0 | 陳思仲      | 李吳永勤     | 四壞球      | 揮棒落空。
 081007000     |       0 |        4 |          1 |         3 |  0 |  0 | 陳思仲      | 李吳永勤     | 四壞球      | 壞球。四壞球上壘。
```
**複核**：陳思仲於單一打席經歷張瑞麟（未實投被換下）、林旺熙（投 2 球）、李吳永勤（投 3 球，最後保送）。三鍵法會切碎或漏失；`pitch_cnt` 在新投手登場時重新自 1 起算。Island detection 成功涵蓋單一打者打席，且邊界排除換人列後保持完整性。

### 案例 D：跑壘特殊事件截斷打席（2026/A/76 第 2 局 朱育賢）
**PSQL Dump**:
```text
 main_event_no | out_cnt | ball_cnt | strike_cnt | pitch_cnt | cp | se | hitter_name | pitcher_name | action_name | left
---------------+---------+----------+------------+-----------+----+----+-------------+--------------+-------------+----------------------------------
 0220017000    |       2 |        1 |          0 |        29 |  0 |  0 | 朱育賢      | 江國豪       |             | 壞球。
 0220018000    |       2 |        1 |          1 |        30 |  0 |  0 | 朱育賢      | 江國豪       |             | 好球沒揮棒。
 0220019000    |       2 |        1 |          1 |        30 |  0 |  1 | 朱育賢      | 江國豪       |             | 二壘跑者郭天信出局-牽制 3人出局。
```
**複核**：朱育賢見 2 球後，二壘跑者遭牽制刺殺出局成為第 3 出局。打席以 `action_name = ""` 截斷，正確歸類為 `truncated_fragment`，非 PA、不計算打者成績。

### 案例 E：突破僵局跑者非 PA（2026/D/137 第 10 局 全浩瑋）
**PSQL Dump**:
```text
 main_event_no | out_cnt | ball_cnt | strike_cnt | pitch_cnt | cp | se | hitter_name | pitcher_name | action_name | left
---------------+---------+----------+------------+-----------+----+----+-------------+--------------+-------------+----------------------------------
 1020002000    |       2 |        0 |          0 |         0 |  1 |  0 | *全浩瑋     | *郭玟毅      | 突破僵局上壘 | 更換投手...
 1020003000    |       0 |        0 |          0 |         0 |  0 |  0 | *全浩瑋     | *郭玟毅      | 突破僵局上壘 | 突破僵局上二壘。
 1020004000    |       0 |        0 |          0 |         0 |  1 |  0 | *許子謙     | *郭玟毅      | 四壞球      | 更換代跑：*全浩瑋=>*劉曜豪。
```
**複核**：全浩瑋 `pitch_cnt = 0`，`action_name = 突破僵局上壘`，純屬突破僵局跑者放置。正確歸類為 `non_pa_tiebreak`，排除於 PA 分母外。

### 案例 D-pitch：pitch_cnt 非逐列唯一（2026/A/1 伍立辰）
**PSQL Dump**:
```text
 main_event_no | pitch_cnt | cp | se | hitter_name | pitcher_name | action_name | content
---------------+-----------+----+----+-------------+--------------+-------------+----------------------------------
 0720014000    |        13 |  0 |  0 | 林子偉      | 伍立辰       | 四壞球      | 壞球。四壞球上壘。
 0720015000    |        13 |  0 |  0 | 宋嘉翔      | 伍立辰       | 飛球接殺    | 教練暫停
 0720016000    |        14 |  0 |  0 | 宋嘉翔      | 伍立辰       | 飛球接殺    | 擊出中外野高飛球...
 0720017000    |        14 |  1 |  0 | 歐晉        | 伍立辰       | 四壞球      | 更換代打...
```
**複核**：同一 `(game, pitcher, pitch_cnt)` 出現於多列（暫停、代打事件與實際投球列共享 `pitch_cnt`），證實逐球映射必須挑選真正的投球列。

---

## 3. Builder 契約與 Fail-closed 設計評估

1. **版本化契約（§9）**：
   `docs/design/pa_transition_taxonomy.v1.json` 提供結構化 JSON schema (`taxonomy_version = "1.0.0"`)，定義 `actions` 字典與 `island_classes`。設計極度適合 [[GAME-RECAP-PA1-EXPAND1]] 與 [[GAME-RECAP-PA1-BUILD1]] 消費。
2. **Fail-closed 安全守門**：
   - 未登錄 `action_name` 預設觸發 `unknown_action` 並中斷告警。全史 2018–2026 實測 0 筆 unknown。
   - `uncaught_third_strike` 類別不代推勝負/上壘命運，避免粗暴猜測。

---

## 4. 審核結論

本任務交付物邏輯嚴密、數據精確、100% 可重跑重現，完全符合所有紅線與技術要求。

**裁決：`APPROVE`**，建議 Coordinator（ruan6047）准予 merge 並解除 [[GAME-RECAP-PA1-EXPAND1]] 之前置鎖。
