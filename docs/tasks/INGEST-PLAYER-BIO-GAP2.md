# INGEST-PLAYER-BIO-GAP2 補齊 batch 2 八人其餘 bio 欄〔T2；⚪一般〕

- review_independence: [context]
- 需求：ruan6047（2026-08-03 於 `INGEST-PLAYER-BIO-GAP1` 合併後指示開卡）　規劃：本卡 spec　分支：`ai/<執行者>/INGEST-PLAYER-BIO-GAP2`
- 執行：待指派（建議 L2；走 canonical CLI，範圍窄）　查核：待指派（新 session 即可；≠ 執行）
- Initiative：INIT-OFFICIAL-DATA1　spec 基線：v1
- DB：`db_scope: write`（只 UPDATE `cpbl.players` 的 bio 欄；不改 schema、不動其他表、`migration_phase: none`）
- 部署：是　環境：production（每日鏈自動同步，無獨立 deploy 動作）　PR：—　Merge SHA：—
- 範圍：對 `INGEST-PLAYER-BIO-GAP1` 背景節所稱 batch 2 的 **8 人**，補齊 `country`／`birthday`
  **以外**的 bio 欄（height／weight／debut／education／birthplace／draft／bats／throws）。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 背景（已查證事實，勿重新推導）

`INGEST-PLAYER-BIO-GAP1`（merge `9393646`）於 2026-08-03 實地抓取這 8 人的官網 person 頁，
**全部回 `person_page_parsed`**，且頁面上 height／weight／debut／birthplace／bats／throws
**全部有值**（逐人 `parsed` dict 見 `docs/research/INGEST-PLAYER-BIO-GAP1_scrape_report.json`）。

但該卡的 `db_scope` 只授權兩欄，寫入走**專用窄 UPDATE**（結構上碰不到其餘欄位），
所以這 8 人至今其餘 bio 欄仍是 NULL——**已於 2026-08-03 以 SQL 覆核：8/8 皆為全 NULL**。

**這不是缺口未查明，是刻意留下的範圍邊界。** 值已證實在官網拿得到，本卡只是把它寫進去。

| player_id | 姓名 |
|---|---|
| 0000004796 | 鎛銳 |
| 0000006891 | 力亞士 |
| 0000007547 | 石萬金 |
| 0000007554 | 龍聖 |
| 0000007555 | 霸鉧德 |
| 0000007556 | 波賽樂 |
| 0000007558 | 黃博多 |
| 0000007559 | 蒙德茲 |

### 為什麼不能無腦跑 `cpbl-scrape-bio`

canonical `cpbl_player_bio._upsert` 的語意是「用 person 頁的**全量內容**更新一列」：

- `country`／`birthday`／`bats`／`throws` 走 `COALESCE`（只補缺）；
- `height_cm`／`weight_kg`／`debut`／`education`／`birthplace`／`draft` 是**無條件 `EXCLUDED` 覆蓋**；
- 並且會**用頁面姓名改寫 `name`**。

對這 8 人而言六欄本來就是 NULL、無值可失，風險低；但**撞到退化頁或抓錯人的頁時仍會損資料**，
而生產端 `sync_table players` 是 `DO UPDATE SET` 無條件覆蓋（`refresh-cpbl-prod.sh:143-145`），
**本機寫錯什麼，隔天 10:10 生產照抄，沒有第二道防線**。

另注意 `--skip-done` 依 `bio_updated_at IS NOT NULL` 判斷，這 8 人的時間戳現在是 **2026-08-03**
（GAP1 的窄 UPDATE 有更新它）→ **加 `--skip-done` 會把他們全部跳過**，等於空跑。

## 目標

對這 8 人補齊 `country`／`birthday` 以外的 bio 欄，且**不損及任何既有非空值**。

## 紅線（違反即退回）

1. **範圍釘死在這 8 人**。不得順手處理全表或 `scope=current` 的其他球員——本卡核可的站台
   請求量是 **8 頁**。名單有變必須由人改常數／參數並留痕。
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

- [ ] 8 人逐一列出：補到哪些欄、未補到的欄與理由（官網無此欄／解析不到）。
- [ ] 補值前後對照：這 8 人各 bio 欄的 NULL 數前後數字入交付文件。
- [ ] **既有非空值未被覆蓋成 NULL 或錯值**——以全表（非只有這 8 人）的 bio 欄 NULL 數前後對照佐證，
      證明沒有波及其他球員。
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
