# Database Contract — cpbl-analytics

> 本檔是本專案資料庫**技術操作事實**的來源；不得記錄 secret、連線字串或 production 憑證。任務流程（階段、確認、資源租用）以安裝版 vNext 規則（`wfx brief`）為準；本檔只管 DB 技術與安全邊界。舊制度的通則（[`AI_WORKFLOW.md` §4.2 @ `f207d2e`](https://github.com/ruan6047/ai-workflow/blob/f207d2ecf80556d6b90beeb0438bf648288a5fd9/AI_WORKFLOW.md)）只作歷史查閱。

## 1. 技術與責任邊界

| 項目 | 專案定義 |
|---|---|
| DB 引擎／版本 | PostgreSQL 17；所有應用物件位於 `cpbl` schema |
| 存取層／migration 工具 | psycopg3 raw SQL；冪等 `migrations/*.sql`，由 `cpbl.db.migrate()` 依序執行 |
| 本機 migration runner | `uv run cpbl-backfill`；LightGBM 訓練不屬 migration，於 API 容器內執行 |
| 正式 migration runner | `prod_cpbl_api` 容器內的 `cpbl.db.migrate()`；僅 main 已審核 source SHA 的部署鏈可執行 |
| 共享資源協調 | vNext 資源租用（`rules/core/github.md` §6）；Project #10 `Resource` 欄只記當前占用，不是鎖 |
| Secret 來源 | 本機 `.env` 與正式環境受保護設定；文件與 git 不記錄值 |

## 2. 環境與 namespace

| 環境 | 用途 | 每卡隔離方式 | 寫入權限 | Migration lane |
|---|---|---|---|---|
| local | 開發與爬蟲 | 讀取可共用；寫入卡以卡號建獨立 DB，或取得共享本機 DB 的資源租用 | 卡片執行者（已取得資源租用） | `db:local:schema` |
| test | 自動測試 | 優先以卡號專屬 DATABASE_URL 指向獨立 DB；無法隔離時序列化 | CI／卡片執行者 | `db:test:schema` |
| production | 服務 | 不建立開發 namespace | 受保護部署 runner only | `db:production:schema` |

## 3. 任務宣告與互斥

每張碰 DB 的卡在規劃內容寫明：

```yaml
db_scope: none | read | write | schema | data-migration
db_namespace: <卡號專屬 database/schema，或共享（需資源租用）>
db_resources:
  - db:<environment>:schema
  - db:<environment>:table:<table-name>
migration_phase: none | expand | migrate | contract
```

- `schema` 與 `data-migration` 為資料正確性紅線；同一 `<environment, schema>` 僅一個 migration writer。
- 改動共享 DB 前依 vNext 規則取得資源租用（用途、存取模式、釋放條件）；共用 local DB 只在明載 owner、清理方式與釋放條件時允許寫入。租用是協作許可，不是技術隔離——同一 `<environment, schema>` 只有一個 migration writer 靠執行者與 PM 確認，⛔ 不靠字串比對判衝突。
- schema migration 與 data migration 不可並行；schema 卡按 lane 順序 merge，不得平行建立互相依賴的 migration。資料 migration 必須冪等、可續跑、批次化，並預先列出對帳與復原方案。

## 4. Migration 執行與驗證

| 階段 | 命令／workflow | 成功條件 | 失敗處理 |
|---|---|---|---|
| Fresh DB rehearsal | `docker compose up -d db` 後 `uv run cpbl-backfill` | migrations 可重跑、相關測試與資料對帳通過 | 停止 merge；保留輸出並依卡片復原方案處理 |
| Local shared DB | 取得共享本機 DB（`db:local:schema`）的資源租用後執行 | migration ID、前後 schema／筆數對帳記入卡片 | 依 migration 的可逆性回復；不可逆操作先人工 sign-off |
| Production | main 部署鏈在 `prod_cpbl_api` 執行 migrate | source SHA、migration ID、時間、健康檢查與 API smoke test 均記錄 | 依 Runbook §3 先前備份還原 `cpbl` schema；停止後續部署 |

## 5. 回滾與緊急處理

- 生產 `cpbl` schema 的同步或結構操作前，先依 [`AI_RUNBOOK.md`](AI_RUNBOOK.md) §3 建立備份；只可動 `cpbl` schema。
- schema 演進採 expand → migrate → contract；刪欄／刪表、大量轉換與破壞性 DDL 必須獨立卡與人工 sign-off。
- 停止條件、資料同步與 API 驗證依 Runbook §3、§7；production 寫入憑證不提供給本機 AI session。
