# INGEST-PLAYER-BIO-GAP1 診斷報告（部分交付：診斷完成、補值待執行）

- 卡片：`docs/tasks/INGEST-PLAYER-BIO-GAP1.md`〔T3；🔴統計〕
- 分支：`ai/opus-5/INGEST-PLAYER-BIO-GAP1`
- 狀態：**診斷完成、工具就緒、補值阻塞於 Gate3 shadow 觀測窗（~2026-08-07）**
- 本輪**未對 `www.cpbl.com.tw` 發出任何請求**（需求方裁定：觀測窗期間完全不碰站台，
  含 dry-run）。DB 僅 SELECT，未寫入任何一列。
- **iteration 2**（查核 REJECT 後）：寫入路徑由 canonical `_upsert` 改為專用窄
  UPDATE（F1，見 §4 取捨節）；目標名單由動態撈改為釘死 14 人（F3，見 §4 範圍閘門）；
  §1.3 的機制敘述與一句話結論的涵蓋範圍已依實測更正（F2，見該節勘誤）。
- **iteration 3**：範圍閘門改為**非對稱**（F3 續）——原本對稱要求「集合完全相同」，
  會擋死斷路器中止後的續跑與補完後的冪等重跑，違反卡面「寫入冪等、可重跑」。

## 一句話結論

**`country`／`birthday` 缺口已證實為 parser-version gap；batch 2 全欄 NULL 的
並行成因仍未定。**

這批列最後一次被 bio 爬蟲走訪的時間，早於「`parse_bio` 第一次會讀國籍／生日」
的那個 commit（`cf9d8b8`），而 bio 爬蟲不在排程鏈上、此後沒有再被跑過，於是那
兩欄至今仍空。

**這個結論的涵蓋範圍僅止於那兩欄**：parser-version gap 足以解釋 14 人為何缺
`country`／`birthday`，但**不能排除** batch 2（8 人）當初另外撞上退化頁——那 8 人
連舊解析器讀得到的 height/weight/debut 都是空的，屬另一個需實地查證的問題（§1.4）。

---

## 1. 根因證據鏈（batch 1 已閉合）

### 1.1 解析器在兩批爬取當時讀不到國籍／生日

`cf9d8b8`（2026-07-06 17:19:12 +0800 ＝ **09:19 UTC**）
`feat(ingest): bio scraper extracts handedness, country, birthday` 是**第一版**
會抽「國籍/出生地」與「生日」的 `parse_bio`。該 commit 之前，`parse_bio` 的輸出
dict 根本沒有 `country`／`birthday` 這兩個 key。

兩批缺值列的 `bio_updated_at` 都落在它之前：

| 批次 | 人數 | `bio_updated_at` | 對 `cf9d8b8` |
|---|---:|---|---|
| 一 | 6 | 2026-07-02 09:40–09:41 UTC | 早 4 天 |
| 二 | 8 | 2026-07-03 02:16–02:22 UTC | 早 3 天 |

### 1.2 全表數字把它釘死

以 `cf9d8b8` 的 09:19 UTC 為切點分群（全表 3767 人）：

| 最後 bio 走訪時間 | 人數 | `country IS NULL` |
|---|---:|---:|
| **早於** `cf9d8b8` | 3634 | **14** |
| **晚於** `cf9d8b8` | 133 | **0** |

早於切點的 3634 人中有 3620 人仍有 `country`——那不是 bio 爬蟲給的，是
**opendata 回填**給的（涵蓋 1990–2024）。所以 14 人正是這個交集：

> **2025 年才登錄（opendata 涵蓋不到） ∧ 只被舊解析器走訪過（bio 給不了）**

晚於切點的 133 人零缺口，是同一機制的反證：新解析器一走訪就有值。

### 1.3 為什麼至今沒被修好

- `cpbl-scrape-bio` **不在排程鏈上**（`run_refresh_recent.py` 與 `scrape-daily.sh`
  皆無 bio 步驟）→ `cf9d8b8` 之後**根本沒有再跑過**，新解析器的能力從未施加到這批列。
- 就算再跑，`--skip-done` 也會跳過他們：該旗標依 `bio_updated_at IS NOT NULL` 判斷，
  而他們的時間戳是有值的（只是來自舊解析器）——這正是 §1.2 那條判準的實務後果。

> **勘誤（iteration 1 → 2）**：本節原先宣稱「`scope=current` 涵蓋不到這 14 人」，
> **不成立**。canonical `_target_ids('current')` 取 `batting_current ∪
> pitching_current` 且**沒有年度條件**，而 `pitching_current` 保留 2025 列
> （實測 2025 有 168 列），故缺值 14 人與 current 名單的交集是 **14/14**。
> 換言之 `scope=current` 涵蓋得到他們，卡住的是「沒再跑」與「`--skip-done`」。
> 原句是未經查證的推測，已於 iteration 2 以 SQL 實測更正。

**這推翻了卡面背景節的一句話**：`bio_updated_at` 非 NULL 只證明「被走訪過」，
不證明「被有能力讀國籍／生日的版本走訪過」。判斷 bio 欄位是否可信，時間戳
必須與 `cf9d8b8` 比對，不能只看非空。

### 1.4 batch 2（8 人全欄 NULL）的成因**尚未查證**

舊解析器**仍會**抽 height/weight/debut/birthplace（batch 1 就有值）。batch 2
八人所有 bio 欄皆 NULL，代表當次拿到的頁面**連這些欄位都解析不到**。兩種可能：

- (a) 當次撞上反爬挑戰頁／退化頁（`_upsert` 仍會寫 `bio_updated_at=now()`，
  於是留下「走訪過但全空」的列）；
- (b) 官網真的沒有該球員的 person 頁。

**兩者在 DB 內無法分辨，必須實地打 `/team/person?acnt=` 才能定案**——這正是
被觀測窗押後的部分。工具已就緒（見 §4），徵狀分類會直接回答 (a)/(b)。

> ⚠️ batch 2 恰好是影響最大的一批：164 個誤標先發席次中，**129 席（78.7%）
> 來自 batch 2**。也就是說「成因未查證」的那批，承載了絕大部分的影響。

---

## 2. 這 14 人是誰（卡面「短期洋將」的描述需更正）

正確描述是「**2025 年登錄洋將、`cpbl-opendata` 未涵蓋**」，不是「短期洋將」。
其中多位是**整季輪值先發**：

| player_id | 姓名 | 隊 | 先發 | 局數 | 批次 | 既有欄位 |
|---|---|---|---:|---:|:--:|---|
| 0000006891 | 力亞士 | 富邦 | **24** | **144.0** | 二 | 全 NULL |
| 0000007558 | 黃博多 | 兄弟 | **23** | **123.0** | 二 | 全 NULL |
| 0000007559 | 蒙德茲 | 統一 | **22** | **120.2** | 二 | 全 NULL |
| 0000007554 | 龍聖 | 味全 | **19** | **109.2** | 二 | 全 NULL |
| 0000007556 | 波賽樂 | 樂天 | 15 | 83.1 | 二 | 全 NULL |
| 0000007547 | 石萬金 | 台鋼 | 15 | 75.2 | 二 | 全 NULL |
| 0000007573 | 李博登 | 兄弟 | 14 | 83.1 | 一 | ht/wt/debut/birthplace |
| 0000007555 | 霸鉧德 | 樂天 | 9 | 41.2 | 二 | 全 NULL |
| 0000007588 | 奧德銳 | 統一 | 7 | 39.0 | 一 | ht/wt/debut/birthplace |
| 0000007590 | 那瑪夏 | 台鋼 | 6 | 34.1 | 一 | ht/wt/debut/birthplace |
| 0000007583 | 柯威士 | 兄弟 | 3 | 7.2 | 一 | ht/wt/debut/birthplace |
| 0000007603 | 凱樂 | 樂天 | 3 | 15.1 | 一 | ht/wt/debut/birthplace |
| 0000004796 | 鎛銳 | 味全 | 2 | 17.2 | 二 | 全 NULL |
| 0000007579 | 韋禮加 | 兄弟 | 2 | 19.1 | 一 | ht/wt/debut/birthplace |
| | | | **164** | | | |

（局數為 CPBL 記法，`.1`＝⅓ 局、`.2`＝⅔ 局。）

### 為什麼「整季輪值」比「短期洋將」嚴重

`cpbl.imports.classify()` 對 `country IS NULL` 保守回 `local`，所以這 164 席
在 2025 被標成本土——占該年 718 個先發席次的 **22.8%**。若真是短期洋將，誤標
的是零星、低槓桿的席次；但 144.0／123.0／120.2／109.2 局這種**整季輪值先發**
被標成本土，等於把該季「洋將先發 vs 本土先發」的對比整個抹平：

- 這批人是各隊的**王牌洋投**，其對手隊伍的先發身分差被系統性錯算；
- `starter_import_diff` 的機制假設是「外籍職業補強池的先發平均強於本土」——把
  最強的一群洋投移進本土側，**同時**拉高本土側均值、拉低洋將側均值，
  對該特徵是雙向污染，不是單純的樣本流失。

`ML-WP-BIO-PRIOR1` memo §4 已據此揭露：2025 的 Δ = −0.008404 是在此**不利
偏差下**取得的。補值後該季效果**應該**變強——但這是待驗證的預期，不是結論，
敏感度重跑尚未執行（見 §5）。

---

## 3. 本機 COALESCE vs 生產無條件覆蓋的不對稱（接手前必讀）

`cpbl.players` 不需要獨立部署動作——它在每日鏈的同步清單裡（**無條件執行**，
不在 `WITH_DETAIL` 之類的條件區塊內），補值會在下一次 10:10 自己抵達生產
（`scripts/refresh-cpbl-prod.sh:143-145`）：

```
sync_table players "id" \
  name full_name handedness bats throws birthday country \
  height_cm weight_kg debut education birthplace draft bio_updated_at
```

**但兩端的寫入語意相反**：

| 層 | 對 `country`／`birthday` 的語意 |
|---|---|
| 本機 `cpbl_player_bio._upsert`（canonical，本卡**不使用**） | `COALESCE(既有, EXCLUDED)`——只補缺，不覆蓋 |
| 本機 本卡 `FILL_SQL` 窄 UPDATE | `COALESCE(既有, 新值)`——只補缺，且只碰兩欄 |
| 生產 `sync_table`（`refresh-cpbl-prod.sh:24-39`） | `ON CONFLICT (id) DO UPDATE SET country=EXCLUDED.country, …`——**無條件覆蓋** |

**本機寫錯什麼，生產下一輪就照抄什麼，沒有第二道防線。**
生產端不區分「本機是刻意寫入還是被退化頁洗掉」，一律照抄——所以 §4 的窄 UPDATE
邊界是本機到生產之間的**唯一守門**，不是可選的保險。

---

## 4. 待執行清單（8/7 觀測窗收窗後接手）

工具已 commit 且測試綠，接手者不需重寫。**順序不可調換**：

1. **確認觀測窗已收**（Gate3 shadow ~2026-08-07）。窗內不得執行本節任何一步。
2. **等當日每日鏈跑完再爬**：`logs/last-status.json` 的 `state == succeeded`
   後再等 5 分鐘緩衝。若當日每日鏈失敗 → **不要爬**（站台可能已在節流）。
3. **dry-run 驗證徵狀分類**（不寫 DB，2 頁）：
   ```
   uv run python scripts/backfill_player_bio_gap1.py --dry-run --limit 2 \
     --html-dir <scratch>/bio_html_dry --report <scratch>/bio_gap1_dryrun.json
   ```
   `target_ids` 依 id 排序，前 2 位是 `0000004796` 鎛銳、`0000006891` 力亞士，
   **正好是成因未定的 batch 2**，且他們全欄 NULL、無既有欄位可失去。
   看 `symptom` 回什麼即可定案 §1.4 的 (a)/(b)：
   - `cpbl_page_no_person` → (b) 官網真的沒有該人頁 → `country` 改走
     官方登錄名單的洋將名額歸屬，並在文件註明推導依據（卡面紅線 4）。
   - `non_cpbl_page` → 仍在挑戰／節流 → **停手冷卻 15–20 分鐘**，勿連續重試。
   - `person_page_parsed` → (a) 當初是退化頁，重爬即可補齊。
4. **正式 14 頁寫入 run**（單次；失敗勿連續重跑）：
   ```
   uv run python scripts/backfill_player_bio_gap1.py \
     --html-dir <scratch>/bio_html --report <scratch>/bio_gap1_report.json
   ```
5. **驗證補值**：`SELECT count(*) FROM cpbl.players WHERE country IS NULL`
   前後數字入交付文件（**補值前＝14**，已記錄於本文件）。逐人記錄補到哪些欄、
   未補到的欄與理由。**查不到生日就留 NULL 並註明「官網無此欄」，不得由年齡
   推估、不得用未標註的二手來源**（卡面紅線 4）。
6. **修 `src/cpbl/imports.py` 模組 docstring**：「players.country（已完整無 NULL）」
   已被證偽，須依補值後實況改寫，並補上「時間戳需與 `cf9d8b8` 比對」的維護註記
   （§1.3 的教訓）。
7. **敏感度重跑（只跑一次）**：
   ```
   uv run python scripts/wp_bio_prior1.py --out docs/research/<新檔名>.json
   ```
   **必須 `--out` 到新路徑**，不得覆寫凍結 artifact
   `docs/research/ml_wp_bio_prior1_metrics.json`。跑前確認
   `git diff scripts/wp_bio_prior1.py docs/research/ML-WP-BIO-PRIOR1_SPEC.md` 為空。
   `AS_OF = 2026-07-27` 凍結不動。**逐季 Δ 與 CI 全表照實記錄**，即使 2026 仍反向
   或池化變差——嚴禁因結果不利而回頭改補值方式／換來源／縮小範圍（卡面紅線 2）。
   **不得重判 `ML-WP-BIO-PRIOR1` 的 Go/No-Go**（該卡已 🏁 結案，紅線 3）。
8. **部署驗證**：補值後的下一次 10:10 之後，確認生產 `players` 那 14 列的
   `country`／`birthday` 已有值（部署動作＝每日鏈自動帶上，無獨立 deploy 步驟）。

### 已就緒的工具

- `scripts/backfill_player_bio_gap1.py`——目標名單釘死在卡面核准的 14 人
  （`EXPECTED_GAP_IDS`）；原始 HTML 逐頁落地存證（卡面要求實地查證，不得從解析器
  行為反推）；寫入走**專用窄 UPDATE**。
- `tests/test_bio_gap_backfill.py`——對寫入邊界與範圍閘門斷言（14 項）。

#### 取捨：不走 canonical `_upsert`，改用專用窄 UPDATE

canonical `cpbl_player_bio._upsert` 的語意是「**用 person 頁的全量內容更新一列**」：
`country`／`birthday`／`bats`／`throws` 走 COALESCE，但
`height_cm`／`weight_kg`／`debut`／`education`／`birthplace`／`draft` 是**無條件
`EXCLUDED` 覆蓋**，並且會用頁面姓名改寫 `name`。

本卡要做的事只有「補兩個 NULL 欄」。硬套全量更新語意，任何退化頁／部分解析頁／
抓錯人的頁都會造成資料損失——**這是問題根源**。

iteration 1 曾試圖以「列舉哪些徵狀不可寫」來擋，**實證會漏**：擋掉了挑戰頁與
查無此人頁，仍漏掉兩種——

1. **部分解析頁**：頁面有姓名、`country` 有值但其餘欄缺 → 判定可寫 → `_upsert`
   仍以 `None` 覆蓋 batch 1 那 6 人既有的 height/weight/debut/birthplace。
2. **姓名不符頁**：抓到別人的頁仍寫入，且 `_upsert` 會用該頁姓名改寫 `name`，
   **把目標列改成別人**。

iteration 2 改為**限制寫入語句能觸及的範圍**：

```sql
UPDATE cpbl.players
   SET country  = COALESCE(country, %s),
       birthday = COALESCE(birthday, %s),
       bio_updated_at = now()
 WHERE id = %s
```

其餘六欄與 `name` **結構上不可能被碰到**——不是靠守衛判斷，是語句裡根本沒有它們；
`COALESCE` 保證只補缺不覆蓋。代價是不再走 canonical 寫入路徑，換得的是「寫入邊界
不依賴徵狀列舉的完整性」。考慮 §3 的生產端無條件覆蓋（本機寫錯就照抄到生產、
無第二道防線），這個代價值得。

姓名檢查仍保留，但**定位改變**：從資料保護降為**健全性閘門**——頁面姓名與 DB 不符
代表該頁的 country／birthday 本來就是別人的值，故拒寫並記錄，交人工判斷
（可能抓錯人，也可能官網改名而 DB 未同步；兩者都不該由腳本自行決定）。

#### 範圍閘門（延後執行的副作用）——**非對稱**

`target_ids()` 原本動態撈「執行當下所有缺值球員」。正式執行既然延到 ~8/7，期間若有
新球員登錄且 bio 缺值，動態名單會多抓多寫、**超出卡面核准的 14 人與站台請求量**
——而請求量正是這張卡被押後的原因。

執行目標為「**仍缺值 ∩ 已授權**」（`EXPECTED_GAP_IDS`）。兩個方向的差集意義相反，
閘門必須非對稱：

| 差集 | 意義 | 處置 |
|---|---|---|
| `found − expected`（DB 有、卡面無） | 有新登錄球員缺 bio ＝**未授權的範圍擴張** | **硬中止**，維持現狀不動任何資料 |
| `expected − found`（卡面有、DB 無） | 那個人**已經被補滿了** ＝ 進度 | 視為 completed 並跳過 |

> **iteration 2 → 3 的修正**：原本對稱地要求「集合必須完全相同」，會直接打死兩個
> 合法情境——(1) 斷路器中止後冷卻續跑（剩下的人數必然少於 14 → ABORT，無法續跑，
> 與斷路器「讓人冷卻後續跑」的存在意義直接打架）；(2) 全部補完後重跑（應為成功的
> no-op，卻變成失敗），違反卡面驗收條件「寫入冪等、可重跑」。
> 空集合現在是**成功的 no-op**。

`tests/test_bio_gap_backfill.py` 對三種情境各有一支測試（續跑 13 人／補完 no-op／
未授權 ID 硬中止），並已做變異檢驗：把非對稱改回對稱，續跑與 no-op 兩支即轉紅。

#### 斷路器涵蓋挑戰頁

被節流時官網回的是「成功的挑戰頁」而非例外，而 `consec_fail` 原本只有例外會累加，
14 頁會被一路打完——正是把節流打成深度封鎖的模式。現在 `non_cpbl_page` 會累加
`consec_fail`；`check_circuit` 移出 `try`（免得自己拋的 RuntimeError 被同層
`except` 吞掉誤記成 `fetch_failed`）；報告改寫在 `finally`（斷路器跳掉的當下正是
徵狀資料最有價值的時候）。

---

## 5. 本輪已完成的計算：補值前控制組重現

補值前以**未變動的輸入**跑了一次 `scripts/wp_bio_prior1.py`（唯讀，`--out` 導向
scratchpad，凍結 artifact 未動），輸出與
`docs/research/ml_wp_bio_prior1_metrics.json` **逐欄 bitwise 相同**
（除 `generated_at`）。

> **Coordinator 裁定**：「補值前重現屬控制組，經 Coordinator 裁定不計入紅線 1 的
> 『只跑一次』；該紅線約束的是補值後的敏感度重跑。」

**為什麼必要**：沒有它，補值後的數字不可解讀——分不出 Δ 是來自資料修正，
還是 2026-07-27 之後的 DB 漂移。此重現證明母體與協定未漂移，補值後的差異可
單一歸因於補值本身。

補值前基線（frozen artifact，供 §4 步驟 7 對照）：

| Y | n_val | Brier(bio7) | Brier(主場常數) | Δ | 99% CI |
|---|---:|---:|---:|---:|---|
| 2023 | 298 | 0.238161 | 0.241801 | −0.003640 | [−0.009358, +0.002382] |
| 2024 | 360 | 0.237501 | 0.247965 | −0.010465 | [−0.017833, −0.003573] |
| 2025 | 359 | 0.238971 | 0.247375 | −0.008404 | [−0.016137, −0.000806] |
| 2026 | 219 | 0.252056 | 0.245940 | **+0.006116** | [−0.004094, +0.016480] |
| 池化 | 1236 | 0.240666 | 0.245949 | −0.005283 | [−0.009116, −0.001548] |

2025 的 `missing_birthday_slots = 164`、`identity_slots` 為
`{import: 298, local: 402, loree: 18}`；補值後這 164 席應由 `local` 移往 `import`
（前提是 §4 步驟 3–4 確認 14 人皆為外籍）。

---

## 6. 後續待辦（本卡範圍外，Coordinator 另開卡）

### `cpbl.batting_splits` 2025「VS. 本土/外籍投手」污染

該表 2025 的 683 列 `本土/外籍` 分項是 **2026-07-14 由 `build_splits` 以
`classify()` 計算**寫入的（`updated_at` 可證），當時這 14 人 `country` 為 NULL →
一律計入「VS. 本土投手」。補值後這些列即為 stale，需重跑 `cpbl-build-splits 2025`
才會一致。

- 影響面：2025 有對戰過這 14 位洋投的打者，其本土／外籍分項數據偏移。
- 本卡 `db_scope` 限定只 UPDATE `cpbl.players` 的 bio 欄，故**不在本卡處理**。
- 生產端會自動帶上（已查證）：`batting_splits` 在 `refresh-cpbl-prod.sh:194` 的
  同步清單內，該段包在 `WITH_DETAIL` 條件中，而每日鏈以
  `SKIP_SCRAPE=1 WITH_DETAIL=1` 呼叫（`scrape-daily.sh:106`）→ 每日同步。
  **這代表污染也會每日照抄到生產**，且與 §3 同樣是 `DO UPDATE SET` 無條件覆蓋。

### 上游 memo 的回指連結（待 Coordinator 裁定，本輪未動）

`ML-WP-BIO-PRIOR1_MEMO.md` §6(b) 把「14 位缺值補齊後敏感度重估」列為升級卡前置，
但沒有指回本診斷。該 memo 是 **🏁 已結案卡的凍結交付物**，故本輪**未動它**。

建議做法（擇一，由 Coordinator 裁定）：
- (A) 待 8/7 完整交付時，於該 memo §6(b) 補一行純指標連結，不改任何數字、
  不改 verdict、不改協定描述；或
- (B) 完全不動凍結交付物，改由本檔與卡片單向指回上游（現況即是）。

我的傾向是 (B)：凍結交付物的價值來自「不會再變」，而單向指回已足夠讓查核者
從卡片走到兩份文件。若採 (A)，變更範圍應嚴格限制在一行連結。

---

## 7. 本輪未完成項目（誠實清單）

| 項目 | 狀態 | 阻塞原因 |
|---|---|---|
| 14 人官網 person 頁實地查證 | **未做** | 觀測窗禁止碰站台 |
| batch 2 成因定案 (a)/(b) | **未定** | 同上；DB 內無法分辨 |
| `country`／`birthday` 補值 | **未做** | 同上 |
| 補值前後 `country IS NULL` 對照 | 僅有前值（14） | 補值未執行 |
| `src/cpbl/imports.py` docstring 修正 | **未做** | 依補值實況才能寫對 |
| 補值後敏感度重跑（逐季 Δ／CI） | **未做** | 依補值結果 |
| 「2026 方向警訊是否消解」事實陳述 | **未做** | 同上 |

**未做就是未做**——上表七項都依賴那次被押後的寫入 run，不能以推測代替。
本文件不對補值後的數字做任何預測性宣稱；§2 末的「應該變強」是機制推論，
標示為待驗證預期，不是結論。
