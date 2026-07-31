# OPS-BACKUP-EMPTY1 交付報告：生產備份的修復與還原演練

- 卡片：`docs/tasks/OPS-BACKUP-EMPTY1.md`（T3；🔴資料安全）
- 分支：`ai/opus-5/OPS-BACKUP-EMPTY1`
- 執行：Claude Opus 5@Claude Code（生產端指令全部由 ruan6047 親手執行）
- 日期：2026-07-31

---

## 1. 結論摘要

備份機制的缺陷有**兩層**，第二層是開卡時未預期的：

1. **備份產不出來**——VPS cron 因憑證預設值錯誤連續 88 天產出 20-byte 空檔，且失敗無人接收。
2. **備份即使正確產出也還原不進去**——生產帶著一個標記為 `convalidated=t` 卻不成立的外鍵，
   還原時兩個 FK 建不起來。**任何檔案層級的檢查都看不到這一層**，只有實際還原一次才會現形。

兩層皆已處置並驗證。

---

## 2. 對卡面〈根因〉的修正與補充

卡面已於 2026-07-29 更正過一次（原第 3 點「缺 pipefail」不成立）。本次執行再補兩項：

### 2.1 曝險描述不完整——cpbl schema 一直有每日已驗證備份

`refresh-cpbl-prod.sh:116` 每次同步前呼叫 `backup-cpbl-prod.sh`。開發機
`~/Library/Application Support/cpbl-analytics/backups/` 實況為 7 份滾動、每份
141–239 MB、皆非空。

故「88 天零可用備份」**僅適用於 VPS 那支整庫 cron**。真正零覆蓋的是主站 `public`
schema（18 張表）直到 07-29 手動整庫 dump。單讀卡面會高估曝險。

### 2.2 正確實作已存在且每日在跑

`backup-cpbl-prod.sh` 已具備卡面目標 1 的全部性質：`set -euo pipefail`、寫 `.partial`
＋`trap rm -f` EXIT、`test -s`＋`gzip -t` 驗證、通過才 `mv` 晉升、清理只在晉升後執行、
憑證走 `set -a && . ./.env` 無 `admin` 預設值。

故本卡不是發明新做法，而是**採用已證明可行的路徑並淘汰壞掉的那條**。

---

## 3. 實作

### 3.1 `backup-cpbl-prod.sh` → `backup-prod-db.sh`，改備整庫

`alpha_db` 為兩專案共用。實測整庫壓縮後只比 cpbl-only 大 **633,869 bytes（+0.26%）**
（240,274,215 vs 239,640,346），主站 18 張表壓縮後約 0.6 MB——近乎零成本換到全庫覆蓋。

改名理由：`backup-cpbl-prod.sh` 產出整庫備份會誤導還原者對 schema 範圍的判斷。
這張卡的主題正是「產出物不得謊報自己是什麼」。歷史文件中的舊名**不改**——它們如實
記錄了當時的狀態。

### 3.2 內容驗證（卡面目標 2）

單次解壓同時取 `CREATE TABLE` 數與位元組數，任一低於門檻即拒絕晉升。
預設 `BACKUP_MIN_TABLES=90`／`BACKUP_MIN_BYTES=100000000`，皆可覆寫。

**為什麼只驗 gzip 完整性不夠**：空輸入的 gzip 是合法串流。那 88 份 20-byte 檔
**每一份都能通過 `gzip -t`**。這個失敗模式只有內容檢查抓得到。

`LC_ALL=C` 釘住位元組語意：POSIX 允許 awk 的 `length()` 在 UTF-8 locale 下回傳字元數。
macOS awk 實測兩種 locale 皆回位元組（含中文字串驗證），故此處是可攜性保險而非
修正既有缺陷；GNU awk 行為不同。

### 3.3 退出碼分流

`64` 參數錯、`66` 內容驗證失敗。與 `refresh-cpbl-prod.sh` 既有的 `65`（freshness 基準
取不到）區隔——執行中實際踩到過撞號，log 裡分不出是哪一段失敗。

### 3.4 清理邏輯

改以檔名內嵌時間戳排序（與前綴無關），並納入舊前綴 `cpbl-prod-*`，讓改名前的備份
隨輪替自然淘汰，不會永久佔用 1.7 GB。bash 3.2 相容（macOS 內建版本無 `mapfile`）。

### 3.5 告警（卡面目標 3）

不新增基礎設施。失敗使 `refresh-cpbl-prod.sh` 非零退出，狀態落入 `logs/last-status.json`
——本專案既有的「AI 接手診斷」入口（見 `scrape-daily.sh` 檔頭）。卡面要求「只寫 log
不算」，此處滿足：狀態是機器可讀的結構化檔案，且既有流程已規定每日查閱。

---

## 4. 變異檢驗（卡面紅線 3）

以假 `ssh` 構造三種情境，實測輸出如下：

```
[a] pg_dump 連線失敗   → exit=23  產物數=0
[b] dump 空但 exit 0   → exit=66  產物數=0
    stderr: 備份內容驗證失敗：CREATE TABLE 0 < 門檻 90
[c] 正常 dump（95 表） → exit=0   產物數=1
    stderr: 已驗證備份：tables=95 uncompressed_bytes=3221
    stdout: /private/tmp/mut/out/alphadb-prod-20260731-172055-58077.sql.gz
```

**情境 (b) 即 88 天缺陷的失敗模式**：pg_dump 未能產出內容但外層成功。舊機制在此情境
留下 20-byte 假檔；新機制以 exit 66 拒絕且目錄零產物。

自動化守衛：`tests/test_backup_prod_db.py` 共 12 項，含
`test_dump_with_no_content_is_rejected_and_leaves_no_artifact` 直接重現該情境。
`ruff` 全綠；`pytest -q` **976 passed／4 skipped**。

---

## 5. 還原演練（卡面驗收條件）

於本機拋棄式 PostgreSQL 17 容器執行（`cpbl-restore-drill`，port 55432，與開發 DB
完全隔離，演練後已刪除）。**未對生產還原**（紅線 1）。

### 5.1 第一輪：失敗，並查出生產資料缺陷

```
psql -v ON_ERROR_STOP=1  → exit 3
ERROR: insert or update on table "blog_posts" violates foreign key constraint
       "blog_posts_author_id_fkey"
```

不加 `ON_ERROR_STOP` 重跑以窮舉錯誤，共 **2 筆**，同一根因：

| 表 | 孤兒列 | 總列 |
|---|---|---|
| `blog_posts` | 1 | 1 |
| `media` | 11 | 11 |

全部指向已刪除的 user `93d667d4-ef7b-40ff-9410-e8e47f62149c`；現存唯一使用者為
`8af852cb-8ccb-4af3-a50f-fb4bc05d91af`。還原後 `public` schema 只有 13 個 FK（應為 15）。

### 5.2 排除「備份漏列」的可能

生產回報 `blog_posts_author_id_fkey` 的 `convalidated = t`。已驗證的外鍵不應容忍孤兒，
故先假設是**備份漏列**（若成立則比還原失敗嚴重一個等級）。生產端實測排除：

```
users_count=1                     ← 與備份一致，未漏列
rls=users:false:false             ← 無 row-level security
dump_role=app_writer superuser=true
fk_def=FOREIGN KEY (author_id) REFERENCES users(id)   ← 目標確為 public.users
orphan_blog=1  orphan_media=11    ← 生產自己算出的孤兒數，與備份一致
```

**結論：備份忠實，生產資料本身帶有完整性違反。** 要製造此狀態需在刪除 `users` 該列時
繞過 FK 強制執行（`session_replication_role=replica` 或 `DISABLE TRIGGER ALL`）。
PostgreSQL 信任 `convalidated` 不會重查，故此矛盾可無限期潛伏，只在 dump/restore
重建約束時現形。

### 5.3 修復與第二輪演練

處置：**改指向現存使用者，不刪列**（`media` 11 筆是站上在用的圖示與 logo）。
先在拋棄式副本驗證有效，再交需求方於生產執行；SQL 帶三道斷言（`users` 恰 1 列、
修後孤兒為 0、列數維持 1 和 11），不成立即 `RAISE` 回滾。

生產實測：`BEFORE blog孤兒=1／media孤兒=11` → 斷言全過 → `AFTER blog列數=1／media列數=11`
→ `COMMIT`。

修復後重取備份並重跑演練：

| 指標 | 修復前 | 修復後 |
|---|---|---|
| `psql` exit（`ON_ERROR_STOP=1`） | 3 | **0** |
| ERROR 筆數 | 2 | **0** |
| `public` schema FK 數 | 13 | **15** |
| `blog_posts_author_id_fkey` | 不存在 | `convalidated=true` |
| `media_uploaded_by_fkey` | 不存在 | `convalidated=true` |

關鍵表列數與生產逐項吻合：`game_livelog` 1,337,619／`batting_splits` 163,275／
`pitching_splits` 115,074／`games` 13,514／表結構 cpbl 81 ＋ public 18。

**卡面驗收條件「在非生產實例還原成功並比對關鍵表列數」達成。**

---

## 6. 曝險期間查明（卡面驗收條件）

**2026-05-05 → 2026-07-31，88 天。**

兩條獨立線索互相印證：

- **log 側**：`/var/log/db-backup.log` 有 88 筆「開始備份」，最早 `20260505_030001`。
  05-05 至 07-31 為 27＋30＋31 ＝ **88 個日曆天**，數字精確相等 → 每日一筆、無缺日。
- **檔案側**：清理邏輯從未執行（log 中「清理舊備份」出現 0 次），故 `/opt/backups`
  的檔案集合亦為完整歷史，最舊同為 `20260505`。

卡面警告「最舊檔案日期不等於缺陷起始日」在當時成立——`KEEP=30` 卻留 86 份的矛盾
未解釋。現已解釋：清理段落位於 pipeline 之後、腳本早退故從未執行。矛盾消解後，
最舊日期**可以**作為起始日。

**排除 log 輪替**：`/var/log/db-backup.log*` 僅單一檔案，無 `.1`／`.gz`；
`/etc/logrotate.d/` 下 10 個設定無一涵蓋該路徑。

**殘留不確定性（照實記）**：無法排除有人刪除過更早的 log。但兩組獨立產物皆指向
05-05，這是目前可取得的最強證據。

**時區**：cron 為 `0 3 * * *`＝03:00 **UTC**＝台北 11:00，非〈問題陳述〉字面暗示的
凌晨 3 點（沿用卡面 2026-07-29 的更正）。crontab 確認**無 `MAILTO`**，佐證「非零退出碼
沒有接收者」。

---

## 7. VPS cron 停用

crontab 僅一行。以註解取代而非 `crontab -r`，保留脈絡；原設定另存
`/root/crontab-backup-20260731.txt`。停用後 `crontab -l` 只剩說明註解。

**未刪除 `/opt/backups` 任何檔案**（卡面紅線 2：88 份空檔為證據；3 份真整庫 dump 為
額外副本）。

---

## 8. 未做與限制（明列）

1. **主站 `infra/scripts/backup-db.sh` 本體未處置**。cron 停用後該腳本形同死碼，
   是否於主站 repo 標記 deprecated 需另行決定——本 session 在主站 repo 的 commit
   受權限閘門阻擋，無法代行。
2. **異地性**：備份現僅存於開發機（7 份滾動）＋ VPS `/opt/backups` 3 份手動整庫 dump。
   備份與 DB 同主機是弱設計，開發機相對 production DB 本身即異地，故本方案優於原
   VPS cron；但**單一開發機仍是單點**，未處理。
3. **還原演練為一次性人工執行**，未自動化、未排程。「備份可還原」這個性質目前
   仍依賴人記得做。
4. `blog_posts` 那筆 `slug=testpage`／`status=published` 的測試文章**內容未處置**——
   本次只改作者指向。是否下架屬產品決策，刻意與資料完整性修復分開。
5. **完整性掃描的涵蓋範圍**。第二輪演練以 `ON_ERROR_STOP=1` 取得 exit 0 且 stderr
   為空——代表 dump 中**每一條語句**都成功執行，含全部 PK／UNIQUE／CHECK／FK 的建立
   與驗證。故「生產資料滿足自身 schema 宣告的所有約束」這件事，在本次快照上是**已證明
   而非推測**。
   未涵蓋的是：(a) 存在於生產但未被 `pg_dump` 輸出的約束（理論上不應發生，未查證）；
   (b) 應用層不變量（例如某欄位語意上該非空但 schema 未強制），schema 層測不到。
