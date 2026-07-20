---
title: "GAME-RECAP-STATUS1 官方狀態與 row-level freshness 證據稽核"
card_id: GAME-RECAP-STATUS1
status: implemented-after-instrumentation
date: 2026-07-20
tags:
  - cpbl
  - game-recap
  - data-correctness
  - freshness
links:
  - "[[GAME-RECAP-STATUS1]]"
  - "[[GAME-RECAP-DATA1]]"
  - "[[GAME_RECAP_PRODUCT_SPEC]]"
---

# GAME-RECAP-STATUS1 證據稽核

## 結論

第一次稽核時，本卡不得直接新增公開 API。既有資料不足以把 `official_game_status`、
`play_by_play_availability` 與 `advanced_freshness` 映射為規格要求的互斥狀態；唯一正確
行動是先開一張 **schema expand／ingest instrumentation** 子卡，保存官方原始狀態和每場、
每來源的取得結果。未完成前，任何 STATUS1 API 都必須 fail closed 為 `unknown`，不應佯裝
具備 `final`、`pending_refresh` 或 `source_error` 的判定能力。

`GAME-RECAP-STATUS-EXPAND1` 通過跨模型家族 T4 查核並整合後，2026-07-20 以本機官網
唯讀取樣重新驗證 2026 一軍 385 筆 raw schedule entry，足以凍結下列保守 mapping；未觀測
的取消狀態與保留賽仍維持 `unknown`。

## Instrumentation 後 raw 值域證據

| `PresentStatus` | `GameResult` | 筆數 | 日期／比分證據 | Public status |
|---:|---:|---:|---|---|
| 1 | 空值 | 155 | 全部為未來賽程、0–0 | `scheduled` |
| 1 | 0 | 204 | 全部為已賽日期且比分總和大於 0 | `final`；0–0 contract 仍只依 raw status，不依比分 |
| 0 | 1 | 23 | 全部為已過日期、0–0，與官網延賽歷程一致 | `postponed` |
| 0 | 2 | 2 | 已開賽後中止且帶比分，既有官網語意為保留賽 | `unknown`；public enum 無 `suspended` |
| 1 | 1 | 1 | 已過日期、0–0，無足夠證據區分目前生命週期 | `unknown` |

未觀測到可證明 `cancelled` 的 raw 值；因此實作不猜測取消代碼。若未來觀測到新值，須先
補研究證據與 contract test，再擴充 mapping。

## 可證明的事實

| 問題 | 證據 | 影響 |
|---|---|---|
| `present_status` 不能表達賽事生命週期 | DATA1 的 2018–2026 A/C/D/E 稽核只有值 `1`（4,675 場），其中 4,252 場有活動證據、423 場為 0–0。 | 不能由它區分 scheduled、final、postponed、cancelled；更不能把 `1` 當 final。 |
| 官方狀態歷程未持久化 | `cpbl_site._primary_entry()` 只選 `PresentStatus=1` 優先、最新日期的單一列；`GameResult` 只被 `_delay_meta()` 濃縮成 `delay_kind`／`orig_date`。 | 已丟失排程、延賽、取消與保留的 raw state，無法回推可審計 mapping。 |
| raw play-by-play 沒有 row-level freshness | `game_scoreboard`、`game_livelog` 僅有 game key 與內容，沒有 `fetched_at`、source revision、success/error 或 completed marker。 | 「有 scoreboard 無 livelog」、「refresh 成功但單場缺漏」無法與「尚未抓取」區分。 |
| `refresh_log` 只是整批觀測 | migration 015 只記錄 scope、日期範圍、games_total、games_completed、detail、ok、note；DATA1 也已明示不能證明單場／單來源完成。 | 不可據此產生 `pending_refresh` 或 `source_error`。 |
| advanced 僅能提供 player aggregate 更新時間 | `advanced_stats.updated_at` 的鍵是 `(year, acnt, role)`；刷新紀錄 detail 只保存 aggregate row count。 | 無法誠實聲稱某一場的 advanced 資料到齊或晚到。 |

補充：`delay_kind='延賽'|'保留'` 是已知的歷程摘要，不能推出已取消或最終完賽；帶比分的未來保留賽也已被 [[BUG-HELD-GAME-FRESHNESS1]] 證實存在，比分不能作狀態替代品。

## 必要子卡：GAME-RECAP-STATUS-EXPAND1（已查核並整合）

| 項目 | 定義 |
|---|---|
| 級別 | T4，資料正確性 [data correctness] |
| DB scope | `schema`，phase=`expand`；需獨占 `db:local:cpbl` migration lane |
| 目標 | 以 additive schema 保存 `(game key, source)` 的 raw 官方狀態與每次取得結果，建立可重跑的 status mapping 證據鏈。 |
| 最小資料 | `game_source_revisions`：game key、source (`schedule`／`scoreboard`／`livelog`／`advanced`)、fetched_at、source_version/hash、outcome (`available`／`missing`／`error`)、row_count、error_code；`game_schedule_status_revisions`：raw `PresentStatus`、raw `GameResult`、原始日期與 payload hash。 |
| 禁止事項 | 不覆寫既有 `games`／livelog；不從日期、比分或空陣列推測狀態；不補寫歷史未知狀態為 final。 |
| 驗收 | 真實原始 payload 值域和 transition table；同一場 scoreboard 有／livelog 無可重現；失敗取得留下 source error；每個 API 判定皆能指向 revision；migration 冪等、寫入可續跑。 |
| 後續 | EXPAND1 通過後再啟動 STATUS1 的 API mapping／contract test；advanced 若無 game-level official source，維持 `unknown`，不可由球員彙總時間代理。 |

## STATUS1 後續契約邊界

- 本卡只擁有 `official_game_status`、raw `play_by_play_availability`、`advanced_freshness`。
- `tracking_availability` 僅由 [[GAME-RECAP-PA1]] 的後續 data-migration 契約提供；不在此重算。
- `wp_availability` 僅由 [[GAME-RECAP-WP-API1]] 提供；不以完賽／livelog 狀態替代。
