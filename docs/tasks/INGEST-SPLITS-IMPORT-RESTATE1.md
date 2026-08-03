# INGEST-SPLITS-IMPORT-RESTATE1 重建 2025 本土／外籍分項以吸收 bio 補值〔T3；🔴資料正確性〕

- review_independence: [cross_family]
- 需求：ruan6047（2026-08-03 於 `INGEST-PLAYER-BIO-GAP1` 合併後指示開卡）　規劃：本卡 spec　分支：`ai/<執行者>/INGEST-SPLITS-IMPORT-RESTATE1`
- 執行：待指派（建議 L3；既有 canonical 管線重跑＋對帳，無新計算邏輯）　查核：待指派（跨家族；≠ 執行）
- Initiative：INIT-OFFICIAL-DATA1　spec 基線：v1（＝父卡當前版本）
- 卡面修訂：rev2（2026-08-03 兩處前提經實測推翻，見背景節與 `BLOCKED-003` 事件）
- 硬前置：`INGEST-PLAYER-BIO-GAP2`（補 `bats`／`throws`）完成並查核通過前，本卡為 no-op
- DB：`db_scope: write`（重建 `cpbl.batting_splits`／`pitching_splits` 等四表的 2025 與生涯列；不改 schema、`migration_phase: none`）
- 部署：是　環境：production（每日鏈自動同步，無獨立 deploy 動作）　PR：—　Merge SHA：—
- 範圍：待 `INGEST-PLAYER-BIO-GAP2` 補完 `bats`／`throws` 後，重跑 `cpbl-build-splits 2025` 的
  `build_splits` 部分，使 2025 本土／外籍分項納入那 14 位洋投的席次，並對帳確認變動落在預期範圍內
  且生涯零變動。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 背景（已查證事實，勿重新推導）

`INGEST-PLAYER-BIO-GAP1`（merge `9393646`，2026-08-03）把 14 位 2025 年登錄洋將的
`country` 由 NULL 補齊，`cpbl.imports.classify()` 對這 14 人的回傳值**由 `local` 轉為
`import`**。

`cpbl.batting_splits` 的 2025「VS. 本土投手」／「VS. 外籍投手」分項共 **683 列**，
`updated_at` 全部落在 **2026-07-31 06:04 UTC**（`INGEST-SPLITS-RECALC1` Phase P 重建那一批），
早於 bio 補值。

**這不是計算錯誤，是輸入變更後的重述** [restatement]：`splits_calc` 的邏輯已於
`INGEST-SPLITS-RECALC1` 查核通過並完成本機與生產重建，本卡**不改任何計算邏輯**。

### ⚠️ 卡面 rev1 的兩處錯誤（2026-08-03 實測推翻，rev2 更正）

**錯誤 1：綁定條件不是 `country`，是 `throws`。** rev1 沿用 `INGEST-PLAYER-BIO-GAP1`
診斷 §6 的說法「這 14 人 country 為 NULL → 一律計入 VS. 本土投手」，**該說法為假**。
[`splits_calc.py:388`](../../src/cpbl/ingest/splits_calc.py) 的本土／外籍 bucket
**只在 `p_throws` 有值時才產生**，否則整個打席記進 `missing_pitcher_bio` 丟棄——
所以這 14 人的席次是**兩邊都沒算到**，不是被算成本土。

`cf9d8b8` 加的是「**handedness**, country, birthday」三者，故這 14 人連 `bats`／`throws`
都是 NULL（實查：14/14 皆 NULL，且**全表僅此 14 人** `throws` 為 NULL）。
**只補 `country` 對本路徑完全無效**：rev1 的作法實跑後四張表**零變動**
（對帳工具已做變異檢驗，證明抓得到變動）。

→ **硬前置改為 `INGEST-PLAYER-BIO-GAP2`**（補 `bats`／`throws`）。該卡完成前本卡是 no-op。
（此錯誤**不影響** `ML-WP-BIO-PRIOR1` 的敏感度結論——ML 特徵直接呼叫 `classify()`，
無 `throws` 閘門，`identity_slots` 確實有 298→462 的搬移。是兩條不同路徑。）

**錯誤 2：rev1 宣稱連帶重建生涯「是正確行為」，該宣稱為假且會造成資料損壞。**
`build_career(season)` ＝ base ＋ **該 season**，而 base ＝ 官方生涯 − 官方**當前**球季
（＝2025 以前的歷史）。故 `cpbl-build-splits 2025` 產生的是 base+2025，
**把 2026 整季換成 2025**。2026-08-03 實跑造成 17,306 列生涯值被改寫，
實測假說 `d == pa2025 − pa2026` **29,457 列零例外**成立；已以 `cpbl-build-splits 2026`
（每日鏈的當季路徑，`build_career` 是 `DELETE year=9999` 後全量重插）還原，逐格與前態相同。

→ 見紅線 5。本卡**不應**也**不會**改動生涯：那 14 人 2026 零出賽，且 base 來自官方生涯資料
（用官方自己的本土／外籍判定，不走我們的 `classify()`），bio 補值對 base 無影響。

### 執行前必須知道的事

1. **生產端無條件覆蓋**：`batting_splits` 在 `refresh-cpbl-prod.sh:194` 的同步清單內，
   包在 `WITH_DETAIL` 條件中，而每日鏈以 `SKIP_SCRAPE=1 WITH_DETAIL=1` 呼叫
   （`scrape-daily.sh:106`）→ **每日同步、`DO UPDATE SET` 無條件覆蓋**。
   本機重建對就對、錯就錯，隔天 10:10 照抄，**沒有第二道防線**。

## 目標

1. 在 `INGEST-PLAYER-BIO-GAP2` 補完 `bats`／`throws` **之後**，重跑
   `uv run cpbl-build-splits 2025`，使 2025 的本土／外籍分項納入那 14 位洋投的席次。
2. 對帳確認變動**限於**與那 14 位洋投對戰過的打者，且方向正確：這批席次原本
   **兩邊都沒算到**（`missing_pitcher_bio`），補完後應**進入「VS. 外籍投手」**
   ——是**淨增加**，不是本土側減少等量搬到外籍側（rev1 對方向的描述亦錯）。
3. 生涯（9999）**必須零變動**：那 14 人 2026 零出賽，且 base 來自官方生涯資料。
   生涯若有任何變動即為異常（多半是誤跑了非當季的 `build_career`，見紅線 5）。

## 紅線（違反即退回）

1. **不得修改 `splits_calc` 的任何計算邏輯或語意常數**。本卡是「同邏輯、換輸入」的重述；
   若重跑後發現計算面缺陷，**停下回報需求方另開卡**，不在本卡順手改。
   （`git diff` 對 `src/cpbl/ingest/splits_calc.py` 應為空。）
2. **重跑前必須先匯出可回復的對照基準**：四張表 year in (2025, 9999) 的完整前態
   （`scripts/restate1_reconcile.py snapshot`）。生涯必須納入——不是因為它該變，而是因為
   要證明它**沒變**（背景錯誤 2）。生產無第二道防線，重建錯了要有東西可比。
3. **變動列數與方向必須逐項對帳並照實記錄**。若出現「與那 14 人無對戰關係的打者也變動」，
   **視為異常，必須查清成因後才可交付**，不得以「重算本來就會有浮動」帶過。
4. **不得順手處理 `INGEST-PLAYER-BIO-GAP2` 的範圍**（`bats`／`throws` 與其餘 bio 欄）。
   那是本卡的**硬前置**，必須先獨立完成並查核；同時動會讓對帳失去單一歸因，
   也會變成「修資料的人自己驗自己」。
5. **嚴禁對非當前球季執行 `cpbl-build-splits <year>`**。該 CLI 在 `build_splits` 之後
   會跑 `build_career(year)` ＝ base ＋ 該年，而 base 是「當前球季以前的歷史」——
   對非當季執行等於**把當前球季的貢獻換成該年**，且 `build_career` 是
   `DELETE year=9999` 後全量重插，破壞是全表級的。
   **本卡需要的是 2025 的 `build_splits`，不需要也不可以動生涯。**
   若必須以 CLI 執行，跑完**立刻**以 `uv run cpbl-build-splits <當前年>` 還原生涯，
   並在交付文件證明生涯與前態逐格相同（2026-08-03 rev1 執行時已實際踩過此坑）。

## 驗收條件

- [ ] 前置確認：`INGEST-PLAYER-BIO-GAP2` 已完成，14 人 `throws` 皆非 NULL（SQL 實查入文件）。
- [ ] `uv run cpbl-build-splits 2025` 已執行，`build_splits` summary 入交付文件；
      生涯已以當季重建還原並證明與前態逐格相同（紅線 5）。
- [ ] 重跑前後對照：2025「VS. 本土投手」／「VS. 外籍投手」的列數、`updated_at`，以及**實際變動的列數**
      （不是 683 這個總列數）。
- [ ] 生涯（9999）變動列數 **＝ 0**，並附逐格比對證據（背景錯誤 2）。
- [ ] 變動歸因對帳：變動的打者集合 ⊆ 2025 曾與那 14 位洋投對戰過的打者集合；差集為空，
      或差集非空時已查清成因並記錄。
- [ ] 變動方向抽驗：至少 3 位打者逐列列出「VS. 外籍投手」的**淨增加量**，並與該打者對上那
      14 人的實際打席數相符；本土側**不應**等量減少（原本就沒算進去，見背景錯誤 1）。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠（**於 commit 之後執行**——`test_commit_trailers.py`
      在 commit 前跑會 skip，見記憶 `pytest-in-verify-loop`；交付前確認它是 passed 不是 skipped）。

## 驗證

- [ ] 查核者確認 `git diff` 對 `src/cpbl/ingest/splits_calc.py` 為空（紅線 1）。
- [ ] 查核者獨立重現變動歸因對帳（差集為空），不採信執行者的宣稱數字。
- [ ] 查核者確認交付文件記錄的是**實際變動列數**，不是把總列數當變動數。

## 邊界與操作紀律

- **不碰爬蟲**：本卡純重算，資料來源是本機既有 `gamelog`／`game_livelog`，**不對官網發任何請求**。
- **生產同步**：無獨立 deploy 動作，重建結果會在下一次 10:10 隨每日鏈抵達生產；部署驗證＝
  該次之後確認生產端分項與本機一致。
- 先讀 [`docs/reference/GLOSSARY.md`](../reference/GLOSSARY.md) 與記憶 `splits-recompute-semantics`
  的語意定案（末球錨定／GO=FO／幽靈島／保留賽排除），勿依單檔註解各自解讀。
- 已備妥對帳工具 `scripts/restate1_reconcile.py`（前後 parquet 快照＋變動歸因 diff，含變異檢驗紀錄），
  查核者可獨立重現，不必採信執行者宣稱的數字。
- 預估 S（半天內）。查證後若發現需要改計算邏輯，**停下回報需求方**（紅線 1）。

## Log

- 2026-08-03 依 ruan6047 指示開卡（`INGEST-PLAYER-BIO-GAP1` 合併後的範圍外待辦具體化）。
  開卡時已查證：683 列、`updated_at` 2026-07-31 06:04 UTC、`build_splits` 之後會接 `build_career`
  （寫入範圍含生涯分項），事實寫入背景節省執行者重複探查。
- 2026-08-03 rev1 執行後**停下回報需求方**：實測推翻兩處前提（綁定條件是 `throws` 非 `country`；
  連帶重建生涯不是正確行為而是資料損壞），卡面升 rev2、硬前置改為 `INGEST-PLAYER-BIO-GAP2`、
  新增紅線 5。生涯損壞已還原且逐格驗證。
