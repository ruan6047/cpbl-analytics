---
card_id: DATA-INCOMPLETE-BOX-INGEST1
tier: T4
db_scope: write
db_namespace: unassigned
db_resources: []
migration_phase: none
related:
  - "[[DATA-TZ-BOUNDARY1]]"
---

# DATA-INCOMPLETE-BOX-INGEST1

## 現行資料庫宣告

本卡尚未取得 `db:local:cpbl` lease，故 `db_namespace` 填 `unassigned`，而非
`shared-lease`；後者會錯誤宣稱已可寫入共享資料庫。現階段只允許唯讀盤點與 versioned
source 變更。

若需求方裁決需要清理既有衍生列，PM／Coordinator 必須先將本卡升為
`db_scope: data-migration`，填入 `db_namespace: shared-lease`、逐表 `db_resources`，並核發
`db:local:cpbl` lease。屆時才可建立可還原備份、執行資料處置與逐表對帳。

## 目標與邊界

防止未完成保留賽以中止比分進入每日完成場流程；既有 partial 資料是否處置，須先完成
消費者影響與每日鏈自癒能力的唯讀驗證，再由需求方裁決。
