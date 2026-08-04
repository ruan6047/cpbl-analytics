# INGEST-SPLITS-IMPORT-RESTATE1 交付報告

- 卡片：[`docs/tasks/INGEST-SPLITS-IMPORT-RESTATE1.md`](../tasks/INGEST-SPLITS-IMPORT-RESTATE1.md)（rev2、spec 基線 v1）
- 執行：Claude Opus 5@Claude Code（接手 v1 停下後的續跑）
- 分支：`ai/opus-5/INGEST-SPLITS-IMPORT-RESTATE1`
- 硬前置：`INGEST-PLAYER-BIO-GAP2`（merge `8f6fe7c`）已查核通過並落 main
- 執行日：2026-08-04

本報告所有數字**由指令輸出產生**，對應的機器可讀 artifact：

| 檔案 | 內容 |
|---|---|
| [`INGEST-SPLITS-IMPORT-RESTATE1_PRECHECK.json`](INGEST-SPLITS-IMPORT-RESTATE1_PRECHECK.json) | 硬前置閘門實查 |
| [`INGEST-SPLITS-IMPORT-RESTATE1_REBUILD.json`](INGEST-SPLITS-IMPORT-RESTATE1_REBUILD.json) | `build_splits` summary |
| [`INGEST-SPLITS-IMPORT-RESTATE1_RECONCILE.json`](INGEST-SPLITS-IMPORT-RESTATE1_RECONCILE.json) | 四表 × 兩年份的變動歸因 |
| [`INGEST-SPLITS-IMPORT-RESTATE1_DIRECTION.json`](INGEST-SPLITS-IMPORT-RESTATE1_DIRECTION.json) | 方向與量級抽驗、幽靈島逐席證據 |

**可回復的對照基準（紅線 2）**：重跑**前**的四表 `year in (2025, 9999)` 完整前態，
以及重跑後的同批快照，存於 `artifacts/restate1-2026-08-04/{pre,post}/*.parquet`
（`artifacts/` 在 `.gitignore` 內，依專案紅線不入版控）。**前態只存在於此**——DB 已被
覆蓋，重跑不會再產生它；生產無第二道防線，此為唯一可比對的還原基準，請勿刪除。

重現指令（查核者可拿受審 SHA 自跑，不必採信本文數字）：

```bash
uv run python scripts/restate1_reconcile.py precheck --report <f.json>
uv run python scripts/restate1_reconcile.py snapshot  --out <dir>/pre
uv run python scripts/restate1_reconcile.py rebuild   --report <f.json>
uv run python scripts/restate1_reconcile.py snapshot  --out <dir>/post
uv run python scripts/restate1_reconcile.py diff      --pre <dir>/pre --post <dir>/post
uv run python scripts/restate1_reconcile.py direction --pre <dir>/pre --post <dir>/post
```

---

## 1. 前置確認：GAP2 是否真的落地

14 人 `throws` **全部非 NULL（14/14）**，`cpbl.players` 全表 `throws IS NULL = 0`、
`bats IS NULL = 0`。閘門通過。

逐人 `bats`／`throws`／`country` 見 `_PRECHECK.json` 的 `pitchers` 欄。

---

## 2. 執行方式：為什麼不走 `cpbl-build-splits 2025`

卡面驗收欄的字面寫法沿用 CLI 路徑，但**紅線 5 明訂「本卡需要的是 2025 的 `build_splits`，
不需要也不可以動生涯」**，CLI 只是退而求其次的容許作法（跑完須立刻還原生涯）。
本次採取更強的作法：**直接呼叫 `cpbl.ingest.splits_calc.build_splits(2025, ("A","D"))`，
完全不執行 `build_career`**，因此生涯不是「被改壞後還原」，而是**從頭到尾沒被碰過**。

依據：`build_splits` 的寫入是 `DELETE FROM cpbl.<tbl> WHERE year=%s AND kind_code=%s`
後 INSERT 同一 `year`，**結構上只能碰指定年份**；`build_career` 才是 `DELETE year=9999`
後全量重插。此路徑封裝在 `scripts/restate1_reconcile.py` 的 `rebuild` 子指令，查核者
重現時不會誤觸 CLI。

`build_splits` summary：

| kind | bsplit | psplit | bvt | pvt | pa | blown_saves |
|---|---:|---:|---:|---:|---:|---:|
| A | 8081 | 5941 | 770 | 703 | 27019 | 11 |
| D | 8640 | 6545 | 867 | 768 | 15749 | 7 |

---

## 3. 預期變動面（先立可證偽的預測，再對帳）

GAP2 補的 bio 只有那 14 人的 `bats`／`throws`。`splits_calc` 內只有兩條路徑讀 bio：

1. **打者側閘門** `if p_throws:`（`splits_calc.py:389`）——補值前，對上這 14 人的整個
   打席落入 `missing_pitcher_bio` 被丟棄，家族 3 兩邊都沒算到。
2. **投手側** `_batter_side(h_bats, p_thr)`——`p_thr` 只在打者是「左右開弓」時才影響
   站位判定。實查 2025 A/D 對上這 14 人的左右開弓打者打席數 **＝ 0**。

`*_vs_team` 兩表出自 `calc_*_t1`（gamelog 場次級），完全不讀 bio。生涯（9999）不在
`build_splits` 的寫入範圍。故預測：**只有 `batting_splits` 的 2025 家族 3 會變，其餘全零。**

> v1 的對帳工具把四張表都拿「打者母體」比對，投手側一旦有變動會被誤報成異常；本次
> 依上述路徑分析改成**逐表逐年各自的預期母體**。

---

## 4. 對帳結果

### 4.1 四表 × 兩年份的變動列數

| 表 @ 年份 | 預期 | 前 → 後 | 新增 | 消失 | 值變動 | 觸及列 | 預期外 |
|---|---|---|---:|---:|---:|---:|---:|
| `batting_splits` @2025 | 有變動 | 16703 → 16721 | 18 | 0 | 653 | **671** | 0 |
| `batting_splits` @9999 | 零變動 | 29928 → 29928 | 0 | 0 | 0 | **0** | 0 |
| `pitching_splits` @2025 | 零變動 | 12486 → 12486 | 0 | 0 | 0 | **0** | 0 |
| `pitching_splits` @9999 | 零變動 | 21870 → 21870 | 0 | 0 | 0 | **0** | 0 |
| `batting_vs_team` @2025 | 零變動 | 1637 → 1637 | 0 | 0 | 0 | **0** | 0 |
| `pitching_vs_team` @2025 | 零變動 | 1471 → 1471 | 0 | 0 | 0 | **0** | 0 |

**實際變動列數是 671**（新增 18 ＋ 值變動 653），不是家族 3 的總列數 2457，也不是卡面
背景提到的 683。比對一律排除 `updated_at`（重建必然更新它，計入會讓每列都「變動」）。

### 4.2 生涯（9999）零變動

四張表的 9999 列**逐格比對零差異**（`_RECONCILE.json` 的 `career_changed_total = 0`）。
獨立佐證：`batting_splits` 的 `max(updated_at)` 在 2025 是 `2026-08-04 13:59:37+00`
（本次重建），在 9999 仍是 `2026-08-03 11:18:31+00`（v1 還原生涯那次）——**9999 這批列
連寫入都沒發生過**。

### 4.3 變動歸因：差集為空，且兩集合實為相等

- 預期母體（2025 A/D `game_livelog` 中曾與那 14 人實際對戰過的打者）：**261 組 (kind, acnt)**。
- 實際變動：**261 組 (kind, acnt)**，涵蓋 **192 位**相異球員（143 組 A ＋ 118 組 D）。
- **差集為 0**；且因兩者組數相同，實際變動集合與預期母體**完全相等**，不只是子集。

額外不變式（皆通過）：變動列的 `item_group_code` **只有 `'3'`**；`item_name` 只出現
`VS. 左投`／`VS. 右投`／`VS. 外籍投手`——**`VS. 本土投手` 一列都沒被觸及**。

### 4.4 方向：淨增加，本土側零變動

| item | 列數 前→後 | 打席 前→後 | 打席差 |
|---|---|---|---:|
| VS. 左投 | 350 → 352 | 9834 → 12514 | **+2680** |
| VS. 右投 | 366 → 367 | 27433 → 29290 | **+1857** |
| VS. 外籍投手 | 314 → 329 | 9543 → 14080 | **+4537** |
| VS. 本土投手 | 369 → 369 | 27724 → 27724 | **0** |

方向完全符合卡面目標 2 的預測：這批席次原本兩邊都沒算到，補完後**淨增加**進外籍側；
**本土側沒有等量減少，是零變動**（rev1 對方向的描述已被證偽）。
左投＋右投的增量 2680 ＋ 1857 ＝ **4537**，與外籍側增量**逐打者完全相等**
（`hand_gap` 非零列數 ＝ 0）——同一個 `if p_throws:` 閘門放行的是同一批打席。

### 4.5 量級抽驗：與獨立來源逐打者比對

對照來源是 canonical PA 表 `game_plate_appearances`（pa-build-1.3.0），與 `splits_calc`
是兩套獨立的物化路徑。**261 位打者逐一比對，`import_gap` 非零列數 ＝ 0。**

> ⚠️ 查詢必須先用 `game_recap_builds.state='published'` 篩掉 superseded 版本：同一場會有
> 多個 `build_id`（2025 A/D 有 359 場重建過），直接對整張表 count 會把同一打席重複計
> 2–3 次（13,717 列 vs 4,572 個真實打席）。本報告初稿的交叉查詢就踩過這個坑。

前 6 名（完整 261 列在 `_DIRECTION.json`）：

| kind | acnt | VS. 左投 | VS. 右投 | VS. 本土投手 | VS. 外籍投手 | 獨立 PA 表 | 幽靈島扣除 | 差 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | 0000004633 | 52 | 36 | 0 | 88 | 88 | 0 | 0 |
| A | 0000005340 | 60 | 26 | 0 | 86 | 86 | 0 | 0 |
| A | 0000006927 | 62 | 24 | 0 | 86 | 86 | 0 | 0 |
| A | 0000005540 | 45 | 39 | 0 | 84 | 84 | 0 | 0 |
| A | 0000003625 | 43 | 39 | 0 | 82 | 82 | 0 | 0 |
| A | 0000005549 | 40 | 40 | 0 | 80 | 80 | 0 | 0 |

---

## 5. 範圍外發現：幽靈島規則會丟掉「手勢故意四壞」（**未修，建議另開卡**）

分項淨增 4537 席、獨立 PA 表 4539 席，殘差 **2 席**。逐席定位結果：

| kind | 場次 | event | 打者 | 投手 | 結果 | canonical PA 表 |
|---|---:|---|---|---|---|---|
| A | 89 | `0510025000` | 0000007239 | 0000007558 | 故四 | 收錄（ready、整段無投球） |
| D | 89 | `0710012000` | 0000006888 | 0000007555 | 故四 | 收錄（ready、整段無投球） |

**成因**：`splits_calc.py:337` 的「幽靈島」規則丟棄整島無投球列的島，立意是濾掉換人
公告列傳播出來的假島（原註解：全季 117 例、box 不計）。但**手勢故意四壞同樣零投球，
是真打席卻一併被丟**。這與記憶 `rule-premise-and-reconciliation-limits` 記錄的
「9.14(d) 手勢故意四壞零投球也算自責分」是同一個物理現象打穿不同規則的第三次。

判準已寫進對帳工具並逐席取證，不是人工聲明：對上這 14 人的幽靈島共 8 席，其中
**只有 2 席構成少算**；另外 6 席分為兩類——1 席是代打誤切（A 第114場，PA 表把
`0820007000→0820011000` 併為同一席歸給代打者，分項由後半島算到同一席，不構成少算），
5 席 PA 表亦不收錄（規則命中本意）。

**規模**（2026 年份未查，本次只掃 2025 A/D）：幽靈島規則丟棄且帶合法結果詞彙的島共
**444 席**，其中「故四」**26 席**（A 17／D 9）。其餘多數是規則本意要濾掉的假島。

**本卡不修**：紅線 1 明訂「若重跑後發現計算面缺陷，停下回報需求方另開卡，不在本卡順手
改」。這是 `splits_calc` 的既有語意，對全體投手一致生效、與本次 bio 重述無關（把這 14 人
的 bio 拿掉，這 26 席一樣被丟）。`git diff` 對 `src/cpbl/ingest/splits_calc.py` 為空。

> 開卡前建議先釐清的前提（**勿直接假設官方計入**）：`INGEST-SPLITS-RECALC1` 的官方值
> 對帳曾宣稱 17,997 格全命中，若官方分項確實計入這 26 席，該對帳理應會露出差異——
> 兩者至少有一個前提需要重驗。記憶 `rule-premise-and-reconciliation-limits` 已記過
> 「窮舉對帳零例外只證一致性，不驗前提真假」。

---

## 6. 驗收條件對照

| 卡面驗收條件 | 結果 |
|---|---|
| 前置確認：14 人 `throws` 皆非 NULL（SQL 實查入文件） | ✅ §1，14/14、全表 NULL=0 |
| `build_splits` 已執行且 summary 入文件；生涯與前態逐格相同 | ✅ §2 §4.2（更強：生涯未被寫入） |
| 前後對照：列數、`updated_at`、**實際變動列數** | ✅ §4.1 §4.4，實際變動 **671** 列 |
| 生涯（9999）變動列數 ＝ 0，附逐格比對證據 | ✅ §4.2 |
| 變動歸因：變動打者集合 ⊆ 對戰過的打者集合，差集為空 | ✅ §4.3，差集 0 且兩集合相等 |
| 方向抽驗：≥3 位打者淨增量與實際打席數相符；本土側不等量減少 | ✅ §4.5，261 位全對；本土側零變動 |
| `ruff check` ＋ `pytest` 全綠（commit 之後執行） | 見 §7 |

## 7. 驗證

於 commit **之後**執行（`test_commit_trailers.py` 在 commit 前跑會 skip）：

- `uv run ruff check` → `All checks passed!`
- `uv run pytest -q` → **996 passed, 3 skipped**
- `uv run pytest tests/test_commit_trailers.py -v` → 3 項全 **PASSED**，
  其中 `test_new_commits_carry_the_required_trailer_set` 確實執行（非 skipped）

### 7.1 執行紀錄：本分支不含 merge origin/main

派工的環境說明要求先把 `origin/main` merge 進分支，但這與派工紅線 3「嚴禁 merge main」
字面衝突，且 `tests/test_commit_trailers.py:119` 對**任何** merge commit 都要求
`Reviewed-by`。實測：merge 進來後該守衛紅（merge commit 無 trailer）。

解法不是補一個 `Reviewed-by`——那等於**捏造一次不存在的查核**。改為拿掉該 merge
commit，分支維持 `858f02d` ＋ 本次兩個 commit 的線性歷史，同時滿足紅線 3 與守衛。
本卡的執行前提是 GAP2 的**資料庫效果**（14 人 `bats`／`throws` 已補），不是它的程式碼，
故不 merge 不影響任何結果。

已在合併樹上另跑過一次完整驗證作為相容性佐證：**1037 passed, 3 skipped**（多出的 41 項
是 GAP2 隨 `origin/main` 帶入的新測試），該次唯一紅燈即上述 merge commit 的 trailer。

## 8. 生產同步

無獨立 deploy 動作。`batting_splits` 在 `refresh-cpbl-prod.sh:194` 的同步清單內，每日鏈以
`SKIP_SCRAPE=1 WITH_DETAIL=1` 呼叫，故本次重建結果會在下一次 10:10 隨每日鏈抵達生產。
**排程與部署驗證不在本批範圍**，由 PM 祕書統一安排。
