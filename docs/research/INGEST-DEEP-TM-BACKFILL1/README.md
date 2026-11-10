# INGEST-DEEP-TM-BACKFILL1 — 一次性產物

本目錄原有的 `sync_deep_tm_prod.py` 是該卡執行期間的**一次性產物**，已跑過、母卡已結案。需求方已於 [#416 規劃確認](https://github.com/ruan6047/cpbl-analytics/issues/416#issuecomment-6674304443)核准刪除，本目錄只留這份紀錄。

## 取回已刪除的腳本

`156fc8bcbc83c99f4389f761dc8155383b1a8fcb` 是刪除前已在 `main` 的提交，檔案在該版本仍存在：

```bash
git show 156fc8bcbc83c99f4389f761dc8155383b1a8fcb:docs/research/INGEST-DEEP-TM-BACKFILL1/sync_deep_tm_prod.py
```

刪除它的提交用下列指令查：

```bash
git log --diff-filter=D --format='%H %s' -- docs/research/INGEST-DEEP-TM-BACKFILL1/sync_deep_tm_prod.py
```

## 為什麼刪除

守衛只擋得住 `--help`。無參數時它仍會直接寫生產，負控制也得拿掉守衛跑一支寫生產的腳本，所以刪除才能消除這條路徑。

## `sync_deep_tm_prod.py` —— 移出 `scripts/` 的原因（歷史）

以下是刪除前的紀錄，描述的是當時的檔案。

`DEV-SCRIPT-INVENTORY1`（#141）的 Discovery 於 2026-08-15 判定它是清冊中唯一一支「**探索動作本身就會損壞生產**」的腳本。四個性質疊在同一支檔案上：

| 性質 | 實測 |
|---|---|
| 無 argv 檢查 | `argparse`／`argv` 命中數 **0**——`--help`、`--dry-run`、任何參數都會直接執行 |
| 寫生產 | `DROP TABLE` ／ `UPDATE cpbl.pitch_tracking` 串流進 `prod_pg` |
| 主機硬編 | `VPS = "root@45.76.100.29"`，無 env override（canonical 腳本是 `VPS="${VPS:-…}"`） |
| 無備份 | `backup-prod-db` 命中數 **0**（`refresh-cpbl-prod.sh` 是先呼叫 `backup-prod-db.sh` 才動） |

**所以當時 `python sync_deep_tm_prod.py --help` 會對生產的 `cpbl.pitch_tracking` 執行 DROP／UPDATE，且沒有備份。**

本專案 2026-08-05 已有同形狀的實際事故（`cpbl-scrape-pitches --help` 觸發真實爬蟲寫入 +46 列，見 `tests/test_cli_help_guard.py` 的 docstring）。差別是那次寫進 46 列，這支會 DROP 生產表。

**需求方 2026-08-15 裁定：移進 `docs/research/`，不刪除。** 目錄分離在本 repo 已有現成慣例——`docs/research/**/*.py` 下已有 18 支同性質的一次性產物。移進來讓它脫離 `scripts/` 的視野，同時保留歷史可讀性，且不需要先判定它該不該永久刪除。

當時留待裁定的「是否加守衛或永久移除」，已由上述 #416 裁定回答：永久移除。
