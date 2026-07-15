# Database Contract — cpbl-analytics

> 本檔是本專案資料庫操作的事實來源；通用不變量見 canonical [`AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) §4.2。不得記錄 secret、連線字串或 production 憑證。

## 1. 技術與責任邊界

| 項目 | 專案定義 |
|---|---|
| DB 引擎／版本 | PostgreSQL 17；所有應用物件位於 `cpbl` schema |
| 存取層／migration 工具 | psycopg3 raw SQL；冪等 `migrations/*.sql`，由 `cpbl.db.migrate()` 依序執行 |
| 本機 migration runner | `uv run cpbl-backfill`；LightGBM 訓練不屬 migration，於 API 容器內執行 |
| 正式 migration runner | `prod_cpbl_api` 容器內的 `cpbl.db.migrate()`；僅 main 已審核 source SHA 的部署鏈可執行 |
| Control-plane adapter | Runbook §7.1 的 `ruan6047` Coordinator + 原子目錄鎖 |
| Secret 來源 | 本機 `.env` 與正式環境受保護設定；文件與 git 不記錄值 |

## 2. 環境與 namespace

| 環境 | 用途 | 每卡隔離方式 | 寫入權限 | Migration lane／lock |
|---|---|---|---|---|
| local | 開發與爬蟲 | 讀取可共用；寫入卡以 `CARD_ID` 建獨立 DB，或取得 `db:local:cpbl` lease | 卡片執行者（經 Coordinator claim） | `db:local:cpbl` |
| test | 自動測試 | 優先以 `CARD_ID` DATABASE_URL 指向獨立 DB；無法隔離時序列化 | CI／卡片執行者 | `db:test:cpbl` |
| production | 服務 | 不建立開發 namespace | 受保護部署 runner only | `db:production:cpbl` |

## 3. 任務宣告與鎖定

每張碰 DB 的卡在 `docs/tasks/<CARD_ID>.md` 必填：

```yaml
db_scope: none | read | write | schema | data-migration
db_namespace: <CARD_ID 專屬 database/schema，或 shared-lease>
db_resources:
  - db:<environment>:cpbl
  - db:<environment>:table:<table-name>
migration_phase: none | expand | migrate | contract
```

- `schema` 與 `data-migration` 為資料正確性紅線；同一 `<environment, schema>` 僅一個 migration writer。
- Coordinator 以 Runbook §7.1 原子 claim 取得 `db:*` resource lease；共用 local DB 只在明載 owner、清理方式與 lease 時允許寫入。
- schema 卡按 lane 順序 merge；不得平行建立互相依賴的 migration。資料 migration 必須冪等、可續跑、批次化，並預先列出對帳與復原方案。

## 4. Migration 執行與驗證

| 階段 | 命令／workflow | 成功條件 | 失敗處理 |
|---|---|---|---|
| Fresh DB rehearsal | `docker compose up -d db` 後 `uv run cpbl-backfill` | migrations 可重跑、相關測試與資料對帳通過 | 停止 merge；保留輸出並依卡片復原方案處理 |
| Local shared DB | Coordinator 取得 `db:local:cpbl` lock 後執行 | migration ID、前後 schema／筆數對帳記入卡片 | 依 migration 的可逆性回復；不可逆操作先人工 sign-off |
| Production | main 部署鏈在 `prod_cpbl_api` 執行 migrate | source SHA、migration ID、時間、健康檢查與 API smoke test 均記錄 | 依 Runbook §3 先前備份還原 `cpbl` schema；停止後續部署 |

## 5. 回滾與緊急處理

- 生產 `cpbl` schema 的同步或結構操作前，先依 [`AI_RUNBOOK.md`](AI_RUNBOOK.md) §3 建立備份；只可動 `cpbl` schema。
- schema 演進採 expand → migrate → contract；刪欄／刪表、大量轉換與破壞性 DDL 必須獨立卡與人工 sign-off。
- 停止條件、資料同步與 API 驗證依 Runbook §3、§7；production 寫入憑證不提供給本機 AI session。
