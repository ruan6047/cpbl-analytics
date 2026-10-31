# #400 結論：2026 季 Mac 現行排程的時間點合理性

- 卡：[#400](https://github.com/ruan6047/cpbl-analytics/issues/400) 驗收 1；執行階段，2026-10-31。
- 性質：針對 Mac 本機 launchd 現況、有日期的快照。#393 搬到 VPS 後改寫的是 [`docs/SCHEDULE_TIMELINE.md`](../../SCHEDULE_TIMELINE.md)，本檔保留為歷史，不跟著改。
- 證據：全部引自 R1 固定版本 [R1_schedule_timing.md](https://github.com/ruan6047/cpbl-analytics/blob/10148f5f8e0494871c1d6041e606e31dbd894f1c/docs/research/SCHED-TIMING-400/R1_schedule_timing.md)（§ 指它的節，G# 指它的 §7 缺口）與量測輸出 [R1_measurements.md](https://github.com/ruan6047/cpbl-analytics/blob/10148f5f8e0494871c1d6041e606e31dbd894f1c/docs/research/SCHED-TIMING-400/R1_measurements.md)（〔M#〕指它的節）。本檔沒有新增量測。
- 優化項目 O#：見 [PLAN_400.md §2](https://github.com/ruan6047/cpbl-analytics/blob/ad70a289875c68ee642878b82570695cb0402a2e/docs/research/SCHED-TIMING-400/PLAN_400.md)；歸屬已由需求方裁定 D1（[issuecomment-6543888486](https://github.com/ruan6047/cpbl-analytics/issues/400#issuecomment-6543888486)）。
- 時刻：本檔不寫排程時刻，一律以 `scripts/schedule-registry.json` 的欄位路徑指稱；現值查法見時間線文件 §0。
- 判定值：合理／合理但有條件／建議調整／實測不足無法判定。

## 賽季

| 排程 | 判定 | 理由 | 證據 | 優化項 |
|---|---|---|---|---|
| `com.cpbl.scrape-daily` | 合理但有條件 | 時刻不受官方發布限制，主要資料在前一晚就齊了；但 `.alert.deadline` 偏緊：例行賽有賽日 69 次中 16 次完成晚於期限，原因（睡眠或反爬退避）分不出來 | §3 E2、E3〔M4〕；§4.1〔M2a〕；G5 | O1、O5、O6、O11 |
| `com.cpbl.weekly-game-pitches` | 合理 | 週頻率對應以天計的晚發布；時刻只用來避開每日鏈，觀測期間與每日鏈零重疊 | §3 E4〔M8〕；§4.2〔M9〕；§5 | O7 |
| `com.cpbl.weekly-box-revisions` | 合理但有條件 | 週頻率就是修訂偵測延遲的上限；但 6 個共同週期中有 1 次因逐球週跑耗時被拉長而撞鎖、整週跳過；拉長的原因【推論】疑似睡眠，當日沒有 pmset 證據可證（R1 §4.2） | §3 E5〔M6〕〔M7〕；§4.3〔M9〕；§5 | O7 |
| `com.cpbl.schedule-watchdog` | 合理 | 判的是週期不是時刻，時刻只影響異常當天多久被看見；觀測期間每天都有執行紀錄 | §4.4〔M10〕 | O12 |
| `com.cpbl.postseason-evening` | 合理但有條件 | 輪詢間隔讓正式站同步落在終場後約 5–8 分（C 戰乾淨樣本 n=4，A 夜沒有樣本）；以「最晚開賽＋`.evening_alert.deadline_after_start_minutes`」為期限時，一軍 A 有 1/357 場時長超過門檻，該類比賽有在結束前先到期的風險；但期限取當晚所有場次的最晚開賽（開賽時刻解析不到時退回 `.evening_alert.fallback_deadline`），R1 沒有把該場與當晚實際期限對齊，是否真的會先到期【未知】 | [R1](https://github.com/ruan6047/cpbl-analytics/blob/10148f5f8e0494871c1d6041e606e31dbd894f1c/docs/research/SCHED-TIMING-400/R1_schedule_timing.md) §3 E1〔M3〕、E2〔M4〕；§4.5〔M11〕；G2 | O2、O8、O10 |
| `com.cpbl.alert-watch` | 實測不足無法判定 | 晚間告警的武裝、成功、halted 流程在賽季從未實際啟動，log 從季後才開始 | §4.6〔M12〕；G6 | O9 |

## 休季

| 排程 | 判定 | 理由 | 證據 | 優化項 |
|---|---|---|---|---|
| `com.cpbl.scrape-daily` | 合理 | 收官後走 skip 或 sync_only，觀測期間 skip 日判完日型即結束（#399 合併前；現行 skip 日另有可用性補位，見時間線文件 §1.1）；休季樣本只有 4 天 | [R1](https://github.com/ruan6047/cpbl-analytics/blob/10148f5f8e0494871c1d6041e606e31dbd894f1c/docs/research/SCHED-TIMING-400/R1_schedule_timing.md) §4.1〔M2b〕；G1 | O1、O11 |
| `com.cpbl.weekly-game-pitches` | 實測不足無法判定 | 依程式碼兩軍收官後會跳過，但尚無休季週期的實測 | §4.2；G1 | O7 |
| `com.cpbl.weekly-box-revisions` | 實測不足無法判定 | 同上；深抓窗在二軍結束後已經空了 | §4.3〔M9〕；G1 | O7 |
| `com.cpbl.schedule-watchdog` | 合理 | skip 日照寫歷史，判定照常有意義 | §4.4〔M10〕 | O12 |
| `com.cpbl.postseason-evening` | 合理 | 每次喚醒都是 `plan → quiet`，不連 DB／stats、不取鎖，語意正確；空喚醒的單次成本未量 | §4.5〔M11〕；G8 | O2、O4 |
| `com.cpbl.alert-watch` | 合理 | 只送 `services` 心跳，evening 段不啟動，符合「沒有比賽就沒有期限」 | §4.6〔M12〕 | O9 |

## 未納入

VPS `prod_cpbl_live_worker`、未安裝的 `lineup-announcements`、樹莓派取源不在 launchd，依範圍裁定只標記現況、不判定（時間線文件 §5）。
