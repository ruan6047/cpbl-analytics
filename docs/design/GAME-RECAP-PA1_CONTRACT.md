---
title: "GAME-RECAP-PA1 canonical 打席與逐球對應契約"
card_id: GAME-RECAP-PA1
status: approved-contract-merged
date: 2026-07-19
tags:
  - cpbl
  - game-recap
  - data-correctness
links:
  - "[[GAME_RECAP_PRODUCT_SPEC]]"
  - "[[GAME-RECAP-DATA1]]"
  - "[[GAME-RECAP-PA1]]"
---

# GAME-RECAP-PA1 canonical 打席與逐球對應契約

關聯：[[GAME_RECAP_PRODUCT_SPEC]]、[[GAME-RECAP-DATA1]]、[[GAME-RECAP-PA1]]、[[GAME-RECAP-WP-VAL1]]、[[GAME-RECAP-WP-API1]]、[[UX-GAME-PA1]]。

## 結論

PA1 不可直接修改既有 `game_livelog`／`pitch_tracking` migration 或用 request-time 分組補洞。[[GAME-RECAP-DATA1]] 已證明目前的三套近似鍵會在同局重複投打、換投與代打時產生不同邊界；本卡採用「來源版本留痕 → 批次物化 PA → 逐球對應 → 唯讀 API」的資料流。

原卡應拆成三張 T4 子卡，且都必須獨立認領、隔離 DB 資源並經跨模型家族或人工查核：

| 子卡 | DB scope／階段 | 目的 | 依賴 |
| --- | --- | --- | --- |
| `GAME-RECAP-PA1-TAXONOMY1` | `read`／none | 以原始事件抽樣、完整 action 值域與紅燈案例定義 state-machine transition taxonomy；不改 schema。 | [[GAME-RECAP-DATA1]] |
| `GAME-RECAP-PA1-EXPAND1` | `schema`／expand | 建立 source revision、materialized PA、PA-event、PA-pitch mapping 的 additive schema 與 ingest 留痕。 | 本契約核可 |
| `GAME-RECAP-PA1-BUILD1` | `data-migration`／migrate | 實作批次 builder、reconciliation、映射與歷史回填；只在 TAXONOMY1＋EXPAND1 查核通過後開始。 | TAXONOMY1、EXPAND1 |

`GAME-RECAP-PA1` 是契約 owner，不自行吞併上述 migration／backfill。`GAME-RECAP-WP-*` 與精確逐球 UI 保持阻塞，直到 BUILD1 的對帳門檻通過。

## 不變量

1. `pa_id` 是持久化 opaque ID，不由 `(inning, hitter, pitcher)`、`batting_order` 或前端連續島即時計算。
2. 每次 build 都必須綁定一個來源 revision；同一 revision 可重跑並產生相同 PA 身分與排序。
3. 發現晚到事件、事件內容變更或逐球來源變更時，不得以新分組靜默覆寫已公開的 `pa_id`。先進入 reconciliation，再產出可稽核的新 build；無法確認的 PA fail closed。
4. `tracking_availability`、`mapping_reason` 與 ordered pitch references 屬 PA 層；WP/WPA 不屬 PA1。
5. 每個 public consumer 只讀 materialized PA／mapping；既有 `winprob.py`、games route 與前端 moment builder 均不得自行再分組。

## 資料模型（EXPAND1 的設計基線）

下列名稱是 contract，非本卡直接新增的 migration；所有表在 `cpbl` schema、採 additive expand 與參數化 SQL。

| 物件 | 主要欄位 | 用途與索引 |
| --- | --- | --- |
| `game_recap_source_revisions` | game key、`source_kind`、`source_sha256`、`fetched_at`、`row_count`、`max_source_key`、`parser_version` | 每次成功抓取 livelog／tracking 時留下 immutable manifest；唯一鍵為 game key + source kind + hash，索引 game key + fetched_at desc。 |
| `game_plate_appearances` | `pa_id`、game key、`pa_index`、`build_id`、start/end event、event order version、投打起訖、前後 state、`result_action`、`state`、`reconciliation_reason`、`built_at` | current canonical PA；唯一鍵 game key + build + `pa_index`，另建 game key + start event、`pa_id` 索引。`state != ready` 不可供 WP／精確 UI 使用。 |
| `game_pa_events` | `pa_id`、`event_no`、`event_position`、`event_fingerprint` | 保留 PA 成員與全序；唯一鍵 `pa_id,event_position` 及 game event lookup，供對帳與 reconciliation。 |
| `game_pa_pitch_mappings` | `pa_id`、pitch local key `(year,kind,game,pitcher,pitch_cnt)`、`pitch_position`、`mapping_state`、`mapping_reason`、`source_revision_id` | 只在唯一且順序一致時標 `mapped`；索引 `pa_id,pitch_position`，並以 pitch local key 防止同一版本重複綁定。 |
| `game_recap_builds` | `build_id`、game key、livelog revision、tracking revision、builder version、state、built_at、validation summary | API 僅讀 `published` build；保留 source/version 與對帳結果，而不是只靠 `refresh_log`。 |

`pitch_tracking` 的現有複合主鍵可作 local pitch reference，但不是官方 immutable pitch ID；每一 mapping 必須同時保存 revision，來源變更即重新驗證。來源 manifest 不保存 credentials，亦不把「本次 refresh 成功」誤當成單場／單來源已完成。

## PA 狀態機與穩定 ID

TAXONOMY1 必須先從真實 `action_name`、`batting_action_name`、計數變化、`is_change_player`／`is_special_event` 及原文事件建立版本化 transition table；不得以名稱猜測 action 語意。builder 在該版本下：

1. 依 `main_event_no` 做嚴格全序，保存每個事件 fingerprint。
2. 只在 taxonomy 明確識別的「打席開始／中間／終結」轉換建立 PA；換投、代打、跑壘與特殊事件可留為成員事件，但不得各自成為 PA。
3. 初次建立時，對同一 game key + start event + event-order version 產生 deterministic UUIDv5；資料庫持久化該 `pa_id`。
4. 後續 revision 先比對既有 `game_pa_events` fingerprints。若同一 seed 的成員、投打身份或終點有變，build 標為 `reconciliation_required`；不得 delete-and-reinsert 或換 ID 後直接發布。
5. reconciliation 只可在可證明一對一延續時保留 `pa_id`；其餘 PA 設為 `unreliable`，並讓 WP/WPA 與精確逐球映射回 `null`／明確 reason。

這個策略確保 refresh 重跑穩定，並把晚到／修正來源變成可見狀態，而非把 ID 漂移藏在 UPSERT 後面。

## 逐球 mapping 與 availability

mapping 候選須同時滿足 game key、投打身份、PA 事件區間、局／半局與球數狀態的單調序；不得只用目前的 `(inning, pitcher, hitter)` 三鍵。候選數不是一個、球序倒退、投打轉換不一致或 source revision 不一致時，`mapping_state=failed`。

public `tracking_availability` 依 [[GAME_RECAP_PRODUCT_SPEC]] 固定為 `available`、`advanced_pending`、`no_equipment`、`source_missing`、`mapping_failed`、`source_error`；`mapping_reason` 必須保留較細的機器原因。尤其：

- 沒有歷史逐球 ingest 不等於無設備；回 `source_missing`，reason=`source_not_collected`。
- 官方尚未提供預期的隔日資料才可回 `advanced_pending`，必須有來源 revision／refresh 證據。
- `no_equipment` 僅在 STATUS1 或核可的官方／人工球場清冊提供正證據時可用；DATA1 的「未觀測到」不可推論無設備。
- candidate 不唯一、順序矛盾或 PA 不可靠時回 `mapping_failed`，不可傳空陣列假裝無球。

## 發布門檻與紅燈測試

BUILD1 必須先在缺陷版本跑紅，再落地以下驗收：

| 案例 | 必要斷言 |
| --- | --- |
| 同局重複投打 | 兩個 PA 有不同 `pa_id`；每顆球最多綁定一個 PA。 |
| 打席中換投、代打、換人／跑壘事件 | 起訖投打欄位和 member events 可追溯；無 taxonomy 規則即 `unreliable`。 |
| 缺球、無 TrackMan、晚到逐球 | 三種狀態與 reason 分開；不以空 list 合併。 |
| 同一來源重跑 | `pa_id`、event membership、pitch order 完全相同。 |
| 來源修正／晚到事件 | 不能靜默替換已發布 ID；必有 reconciliation build record。 |
| API | `GET` 單一 `pa_id` 才載入逐球；首屏不傳整場 tracking payload；route snapshot／contract test 同步更新。 |

每個 scope（年／球場／賽制）都輸出：box PA、candidate PA、`ready` PA、unreliable PA、mapped／failed pitch、unknown reason。對帳門檻由需求方在 BUILD1 Plan Gate 核可前明定；未達門檻時精確逐球 UI 不得開啟。

## 非目標與交接

- 本卡不計算 WP、WPA、勝率模型或前端視覺化。
- 不以 `home_score + away_score > 0` 判定完賽；official status／freshness 由 [[GAME-RECAP-STATUS1]] owner。
- 不重寫既有攤平 livelog API；其移除近似鍵 consumer 是 WP-API1／UX 子卡的責任。

下一步是由需求方核可本契約與三張子卡的切分，Coordinator 才能註冊／認領子卡並取得 schema/data-migration lease。
