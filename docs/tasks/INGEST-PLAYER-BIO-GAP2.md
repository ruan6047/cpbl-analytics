# INGEST-PLAYER-BIO-GAP2 補齊 14 人的 handedness 與 batch 2 其餘 bio 欄〔T2；🔴資料正確性〕

- review_independence: [context]
- 需求：ruan6047（2026-08-03 於 `INGEST-PLAYER-BIO-GAP1` 合併後指示開卡）　規劃：本卡 spec　分支：`ai/<執行者>/INGEST-PLAYER-BIO-GAP2`
- 執行：待指派（建議 L2；走 canonical CLI，範圍窄）　查核：待指派（新 session 即可；≠ 執行）
- Initiative：INIT-OFFICIAL-DATA1　spec 基線：v1（＝父卡當前版本）
- 卡面修訂：rev2（2026-08-03 範圍 8→14，見背景「rev1 範圍錯誤」節與 `SCOPE-002` 事件）
- 下游：`INGEST-SPLITS-IMPORT-RESTATE1` 以本卡為**硬前置**（本卡不補 `throws`，該卡即為 no-op）
- DB：`db_scope: write`（只 UPDATE `cpbl.players` 的 bio 欄；不改 schema、不動其他表、`migration_phase: none`）
- 部署：是　環境：production（每日鏈自動同步，無獨立 deploy 動作）　PR：—　Merge SHA：—
- 範圍：**`bats`／`throws` 補齊全部 14 人**（batch 1＋2；全表僅此 14 人 `throws` 為 NULL）；
  `height`／`weight`／`debut`／`education`／`birthplace`／`draft` 只有 batch 2 那 **8 人**需要補。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 背景（已查證事實，勿重新推導）

`INGEST-PLAYER-BIO-GAP1`（merge `9393646`）於 2026-08-03 實地抓取這 14 人的官網 person 頁，
**全部回 `person_page_parsed`**，且頁面上 height／weight／debut／birthplace／bats／throws
**全部有值**（逐人 `parsed` dict 見 `docs/research/INGEST-PLAYER-BIO-GAP1_scrape_report.json`）。

但該卡的 `db_scope` 只授權 `country`／`birthday` 兩欄，寫入走**專用窄 UPDATE**
（結構上碰不到其餘欄位）。**這不是缺口未查明，是刻意留下的範圍邊界。**

### ⚠️ 卡面 rev1 的範圍錯誤（2026-08-03 實測更正）

rev1 把範圍寫成「batch 2 的 8 人」，**過窄**。`cf9d8b8` 加的是「**handedness**, country,
birthday」三者，所以 **batch 1 那 6 人的 `bats`／`throws` 一樣是 NULL**（他們只是靠更早的
解析器拿到了 height／weight／debut／birthplace）。

2026-08-03 SQL 實查：

| 群組 | `throws` NULL | `height_cm` NULL |
|---|---:|---:|
| batch 1（6 人） | **6** | 0 |
| batch 2（8 人） | **8** | 8 |
| 全表 3767 人 | **14** | — |

**全表只有這 14 人 `throws` 為 NULL。**

**為什麼這件事比補齊身高體重重要得多**：`splits_calc.py:388` 的本土／外籍 bucket
**只在 `p_throws` 有值時才產生**，否則整個打席被記進 `missing_pitcher_bio` 丟棄。
這 14 人 2025 有 **206 場出賽**，其對戰打席至今**在本土／外籍分項兩邊都沒被算到**
（不是被算成本土——`INGEST-PLAYER-BIO-GAP1` 診斷 §6 的說法為假）。
下游 `INGEST-SPLITS-IMPORT-RESTATE1` 在本卡完成前是 no-op，已實跑證實（四張表零變動）。

| player_id | 姓名 | 批次 | 需補 |
|---|---|:--:|---|
| 0000007573 | 李博登 | 1 | bats／throws |
| 0000007579 | 韋禮加 | 1 | bats／throws |
| 0000007583 | 柯威士 | 1 | bats／throws |
| 0000007588 | 奧德銳 | 1 | bats／throws |
| 0000007590 | 那瑪夏 | 1 | bats／throws |
| 0000007603 | 凱樂 | 1 | bats／throws |
| 0000004796 | 鎛銳 | 2 | bats／throws ＋ 其餘六欄 |
| 0000006891 | 力亞士 | 2 | 同上 |
| 0000007547 | 石萬金 | 2 | 同上 |
| 0000007554 | 龍聖 | 2 | 同上 |
| 0000007555 | 霸鉧德 | 2 | 同上 |
| 0000007556 | 波賽樂 | 2 | 同上 |
| 0000007558 | 黃博多 | 2 | 同上 |
| 0000007559 | 蒙德茲 | 2 | 同上 |

### 為什麼不能無腦跑 `cpbl-scrape-bio`

canonical `cpbl_player_bio._upsert` 的語意是「用 person 頁的**全量內容**更新一列」：

- `country`／`birthday`／`bats`／`throws` 走 `COALESCE`（只補缺）；
- `height_cm`／`weight_kg`／`debut`／`education`／`birthplace`／`draft` 是**無條件 `EXCLUDED` 覆蓋**；
- 並且會**用頁面姓名改寫 `name`**。

對 batch 2 那 8 人而言六欄本來就是 NULL、無值可失；但 **batch 1 那 6 人的 height／weight／
debut／birthplace 是有值的**，`_upsert` 撞到退化頁會把它們覆蓋成 NULL——正是 GAP1 改走窄 UPDATE 的原因。
而生產端 `sync_table players` 是 `DO UPDATE SET` 無條件覆蓋（`refresh-cpbl-prod.sh:143-145`），
**本機寫錯什麼，隔天 10:10 生產照抄，沒有第二道防線**。

另注意 `--skip-done` 依 `bio_updated_at IS NOT NULL` 判斷，這 14 人的時間戳現在是 **2026-08-03**
（GAP1 的窄 UPDATE 有更新它）→ **加 `--skip-done` 會把他們全部跳過**，等於空跑。

## 目標

1. **14 人**的 `bats`／`throws` 補齊——這是下游 `INGEST-SPLITS-IMPORT-RESTATE1` 的解鎖條件。
2. batch 2 那 8 人的其餘 bio 欄一併補齊。
3. 全程**不損及任何既有非空值**。

## 紅線（違反即退回）

1. **範圍釘死在這 14 人**。不得順手處理全表或 `scope=current` 的其他球員——本卡核可的站台
   請求量是 **14 頁**。名單有變必須由人改常數／參數並留痕。
2. **不得腦補**：官網沒有的欄位就留 NULL 並記錄「官網無此欄」，不得由其他來源推估或
   從未標註的二手站填入。
3. **爬蟲節流**：走 www 域（HiNet 挑戰），**單次 run 完成**；失敗先冷卻 15–20 分鐘再單次重試，
   **嚴禁連續重跑**（會升級節流，症狀惡化）。開跑前確認當日每日鏈 `logs/last-status.json`
   的 `state == succeeded`；當日鏈失敗則**不要爬**。
4. **不得順手處理 `INGEST-SPLITS-IMPORT-RESTATE1` 的範圍**。兩張卡都影響 `players` 的下游，
   同時動會讓對帳失去單一歸因。
5. **姓名不符時不得自動繞過**：`players.name` 會**合法過期**（改名經每日 gamelog 同步），
   所以「頁面姓名 ≠ DB 姓名」**不自動等於抓錯人**，須人工判別，不得自動重試繞過。

## 驗收條件

- [ ] 14 人逐一列出：補到哪些欄、未補到的欄與理由（官網無此欄／解析不到）。
- [ ] **`throws` NULL 全表 14 → 0**（下游解鎖條件，SQL 實查入文件）；`bats` 同。
- [ ] 補值前後對照：這 14 人各 bio 欄的 NULL 數前後數字入交付文件。
- [ ] **既有非空值未被覆蓋成 NULL 或錯值**——特別是 batch 1 那 6 人既有的 height／weight／
      debut／birthplace 必須逐位不變；並以全表 bio 欄 NULL 數前後對照佐證未波及其他球員。
- [ ] `country`／`birthday` 這兩欄的值**與 GAP1 寫入的完全相同**（未被本卡改動）。
- [ ] 原始 HTML 或逐人解析報告落地存證（scratchpad 或 repo；HTML 勿入 repo）。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠（**於 commit 之後執行**——`test_commit_trailers.py`
      在 commit 前跑會 skip，見記憶 `pytest-in-verify-loop`；交付前確認它是 passed 不是 skipped）。

## 驗證

- [ ] 查核者確認補值來源可追溯（逐人可覆核），且無紅線 2 的腦補填值。
- [ ] 查核者確認 `country`／`birthday` 與 GAP1 的交付值逐位相同。
- [ ] 查核者確認全表其他球員的 bio 欄未被波及。

## 邊界與操作紀律

- **只能本機爬**（VPS 機房 IP 被擋 404）；爬完照 [`AI_RUNBOOK.md`](../AI_RUNBOOK.md) §3 的既有每日鏈同步生產。
- 官網結構事實查 [`docs/CPBL_SITE_MAP.md`](../CPBL_SITE_MAP.md)，改版排查照其 §5 症狀對照表，勿從零逆向。
- 可直接沿用 `scripts/backfill_player_bio_gap1.py` 的作法（釘死名單＋原始 HTML 存證＋窄寫入），
  但該腳本的 `FILL_SQL` 只寫兩欄，**本卡要寫的是另外六欄＋bats／throws**，語句需另寫；
  沿用時**不得放寬**成 canonical 全量 `_upsert` 而不加防護（理由見背景）。
- 預估 S（半天內）。

## Log

- 2026-08-03 依 ruan6047 指示開卡（`INGEST-PLAYER-BIO-GAP1` 合併後的範圍外待辦具體化）。
  開卡時已查證：8 人其餘 bio 欄 8/8 仍全 NULL、官網頁面確有這些值、`--skip-done` 會跳過他們
  （時間戳已被 GAP1 更新為 2026-08-03），事實寫入背景節省執行者重複探查。
- 2026-08-03 rev2：`INGEST-SPLITS-IMPORT-RESTATE1` 執行時實測發現範圍過窄——`bats`／`throws`
  是全部 14 人皆缺（非只有 batch 2 的 8 人），且它正是本土／外籍分項的綁定條件。
  級別由 T2⚪ 升為 T2🔴資料正確性（本卡是下游資料正確性的解鎖點），範圍 8 → 14。
