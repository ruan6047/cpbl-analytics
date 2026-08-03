# INGEST-SPLITS-IMPORT-RESTATE1 重建 2025 本土／外籍分項以吸收 bio 補值〔T3；🔴資料正確性〕

- review_independence: [cross_family]
- 需求：ruan6047（2026-08-03 於 `INGEST-PLAYER-BIO-GAP1` 合併後指示開卡）　規劃：本卡 spec　分支：`ai/<執行者>/INGEST-SPLITS-IMPORT-RESTATE1`
- 執行：待指派（建議 L3；既有 canonical 管線重跑＋對帳，無新計算邏輯）　查核：待指派（跨家族；≠ 執行）
- Initiative：INIT-OFFICIAL-DATA1　spec 基線：v1
- DB：`db_scope: write`（重建 `cpbl.batting_splits`／`pitching_splits` 等四表的 2025 與生涯列；不改 schema、`migration_phase: none`）
- 部署：是　環境：production（每日鏈自動同步，無獨立 deploy 動作）　PR：—　Merge SHA：—
- 範圍：以 `INGEST-PLAYER-BIO-GAP1`（merge `9393646`）補值後的 `players.country` 為輸入，重跑
  `cpbl-build-splits 2025` 使本土／外籍分項與身分旗標一致，並對帳確認變動落在預期範圍內。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 背景（已查證事實，勿重新推導）

`INGEST-PLAYER-BIO-GAP1`（merge `9393646`，2026-08-03）把 14 位 2025 年登錄洋將的
`country` 由 NULL 補齊，`cpbl.imports.classify()` 對這 14 人的回傳值**由 `local` 轉為
`import`**。

`cpbl.batting_splits` 的 2025「VS. 本土投手」／「VS. 外籍投手」分項共 **683 列**，
`updated_at` 全部落在 **2026-07-31 06:04 UTC**（`INGEST-SPLITS-RECALC1` Phase P 重建那一批），
**早於補值**。也就是說這 683 列是拿「14 人還是 NULL → 一律判本土」算出來的，**現已 stale**。

**這不是計算錯誤，是輸入變更後的重述** [restatement]：`splits_calc` 的邏輯已於
`INGEST-SPLITS-RECALC1` 查核通過並完成本機與生產重建，本卡**不改任何計算邏輯**。

### 兩件執行前必須知道的事

1. **寫入範圍比卡名大**：`run_build_splits.main()` 在 `build_splits(year, kinds)` 之後
   **緊接著跑 `build_career(year, kinds)`**。生涯分項＝官方生涯 base ＋ 本季（見
   `anchor_career` 與記憶 `splits-recompute-semantics`），本季一變、生涯跟著變。
   所以本卡實際重建的是「2025 分項 **＋** 受 2025 影響的生涯分項」，不是只有 683 列。
   **這是正確行為**（生涯本來就該跟著動），但必須在交付文件裡明寫變動列數，不得只報 683。
2. **生產端無條件覆蓋**：`batting_splits` 在 `refresh-cpbl-prod.sh:194` 的同步清單內，
   包在 `WITH_DETAIL` 條件中，而每日鏈以 `SKIP_SCRAPE=1 WITH_DETAIL=1` 呼叫
   （`scrape-daily.sh:106`）→ **每日同步、`DO UPDATE SET` 無條件覆蓋**。
   本機重建對就對、錯就錯，隔天 10:10 照抄，**沒有第二道防線**。

## 目標

1. 重跑 `uv run cpbl-build-splits 2025`，使 2025 與生涯的本土／外籍分項與補值後的
   `players.country` 一致。
2. 對帳確認變動**限於**與那 14 位洋投對戰過的打者，且變動方向與身分翻轉相符
   （本土側減少、外籍側增加），不得有無關列被動到。

## 紅線（違反即退回）

1. **不得修改 `splits_calc` 的任何計算邏輯或語意常數**。本卡是「同邏輯、換輸入」的重述；
   若重跑後發現計算面缺陷，**停下回報需求方另開卡**，不在本卡順手改。
   （`git diff` 對 `src/cpbl/ingest/splits_calc.py` 應為空。）
2. **重跑前必須先備份可回復的對照基準**：至少把 2025 本土／外籍那 683 列與受影響的生涯列
   匯出成 artifact（scratch 或 repo 皆可，但交付文件要能逐列覆核前後差異）。
   理由見背景 §2——生產無第二道防線，重建錯了要有東西可比。
3. **變動列數與方向必須逐項對帳並照實記錄**。若出現「與那 14 人無對戰關係的打者也變動」，
   **視為異常，必須查清成因後才可交付**，不得以「重算本來就會有浮動」帶過。
4. **不得順手處理 `INGEST-PLAYER-BIO-GAP2` 的範圍**（batch 2 八人其餘 bio 欄）。那是另一張卡；
   兩張卡都寫 `cpbl.players`／衍生表，同時動會讓對帳失去單一歸因。

## 驗收條件

- [ ] `uv run cpbl-build-splits 2025` 已執行，`build_splits` 與 `build_career` 的 summary 入交付文件。
- [ ] 重跑前後對照：2025「VS. 本土投手」／「VS. 外籍投手」的列數、`updated_at`，以及**實際變動的列數**
      （不是 683 這個總列數）。
- [ ] 生涯分項的變動列數一併記錄——卡名只提 2025，但寫入範圍含生涯（見背景 §1）。
- [ ] 變動歸因對帳：變動的打者集合 ⊆ 2025 曾與那 14 位洋投對戰過的打者集合；差集為空，
      或差集非空時已查清成因並記錄。
- [ ] 變動方向抽驗：至少 3 位打者逐列列出「本土側減少的量 ＝ 外籍側增加的量」，證明是身分搬移
      而非重算漂移。
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
- 預估 S（半天內）。查證後若發現需要改計算邏輯，**停下回報需求方**（紅線 1）。

## Log

- 2026-08-03 依 ruan6047 指示開卡（`INGEST-PLAYER-BIO-GAP1` 合併後的範圍外待辦具體化）。
  開卡時已查證：683 列、`updated_at` 2026-07-31 06:04 UTC、`build_splits` 之後會接 `build_career`
  （寫入範圍含生涯分項），事實寫入背景節省執行者重複探查。
