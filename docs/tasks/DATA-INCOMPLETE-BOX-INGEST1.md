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

若需求方日後裁決需要清理既有衍生列，PM／Coordinator 必須先將本卡升為
`db_scope: data-migration`，填入 `db_namespace: shared-lease`、逐表 `db_resources`，並核發
`db:local:cpbl` lease。屆時才可建立可還原備份、執行資料處置與逐表對帳。

## 目標與邊界

防止未完成保留賽以中止比分進入每日完成場流程；既有 partial 資料是否處置，須先完成
消費者影響與每日鏈自癒能力的唯讀驗證，再由需求方裁決。

## 需求方裁決（2026-08-08）

處置採「**不處置＋續賽後唯讀驗證**」。不得刪除、修正或重建既有衍生列，也不得申請或使用
共享 local DB 的寫入 lease。

四場保留賽在續賽日進入每日 `[昨天, 今天]` 視窗後，排程會嘗試重抓明細並重建 PA
產物；這是已由 source 路徑查證的預期流程，不是官方資料一定可取得或重建一定成功的保證。
各場續賽隔日進行唯讀驗證：

| 場次 | 續賽日 | 驗證日 |
| --- | --- | --- |
| `2026/D/97` | 2026-08-09 | 2026-08-10 |
| `2026/D/118` | 2026-08-22 | 2026-08-23 |
| `2026/D/117` | 2026-08-30 | 2026-08-31 |
| `2026/D/165` | 2026-09-15 | 2026-09-16 |

每次驗證僅讀取該場的賽程比分、`batting_gamelog`、`pitching_gamelog`、
`game_livelog`、`game_scoreboard` 與 `game_recap_builds` 的 published/revision 狀態，並比對
刷新紀錄。任一來源未更新或 PA build 未成功時，停止「自癒」結論並回報 PM；不得以人工資料
操作補救。
