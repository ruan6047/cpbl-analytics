---
title: "GAME-RECAP-PA1 canonical 打席契約獨立查核報告"
card_id: GAME-RECAP-PA1
status: review-approve
date: 2026-07-19
tags:
  - cpbl
  - game-recap
  - data-correctness
  - review
links:
  - "[[GAME-RECAP-PA1]]"
  - "[[GAME-RECAP-PA1_CONTRACT]]"
  - "[[GAME_RECAP_PRODUCT_SPEC]]"
  - "[[GAME-RECAP-DATA1]]"
---

# GAME-RECAP-PA1 canonical 打席契約獨立查核報告

- 查核卡：[`GAME-RECAP-PA1`](../tasks/GAME-RECAP-PA1.md)〔T4；🔴資料正確性〕
- 查核標的：[`docs/design/GAME-RECAP-PA1_CONTRACT.md`](../design/GAME-RECAP-PA1_CONTRACT.md)＋卡片更新（執行分支 `ai/gpt-5-codex/GAME-RECAP-PA1`，head `b9ea43b`）
- 查核者：Claude（Opus 4.8）@Claude Code　執行／撰寫者：GPT-5@Codex（跨模型家族，符合紅線獨立性 §3）
- 日期：2026-07-19　方法：契約 vs spec §3.3／§6.3／§7／§8 逐項對帳＋所有引用表/欄位名回源程式碼查證＋三套近似分組 NO-GO 前提回源＋merge/衝突試算；未修改交付物、未改 schema／API／前端
- **結論：APPROVE（P0=0）。契約定義的資料模型、`pa_id`／reconciliation、availability 語意與三卡切分足以避免近似鍵回歸；三點非阻擋事項見 §5。**

---

## 0. 卡片範圍與交付一致性

本卡 claim 事件明訂範圍為「技術設計、canonical contract 定稿與 expand／backfill 子卡切分」，`db_scope: none`，不得改既有 migration／ingest／API／前端。查核確認交付與範圍一致：

| 檢查 | 判定 | 依據 |
|---|---|---|
| 分支僅動文件 | ✅PASS | `git diff --name-only main...` 僅 `docs/design/GAME-RECAP-PA1_CONTRACT.md`（新增）、`docs/tasks/GAME-RECAP-PA1.md`（更新），共 +108/-2 |
| 未碰 control-plane／migration／src／web | ✅PASS | name-only 篩 `control-plane|migrations/|src/|web/` 無命中 |
| 未新增 migration（DB scope none 屬實） | ✅PASS | 契約 §資料模型明言「名稱是 contract，非本卡直接新增的 migration」 |

## 1. 四個查核維度（handoff 指定）

| 維度 | 判定 | 依據 |
|---|---|---|
| 資料模型 | ✅PASS | 5 物件（`game_recap_source_revisions` manifest／`game_plate_appearances` current canonical PA／`game_pa_events` 成員全序／`game_pa_pitch_mappings`／`game_recap_builds`），皆 `cpbl` schema、additive expand、參數化 SQL；唯一鍵與索引逐表指定；**把來源 provenance 與衍生 PA 分離**，正是 DATA1「`refresh_log` 不足以證明單場單來源完成」的正解 |
| `pa_id`／reconciliation | ✅PASS | opaque、持久化、非 `(inning,hitter,pitcher)`／`batting_order`／前端連續島即時計算；deterministic UUIDv5 seed=`game key＋start event＋event-order version`；後續 revision 先比對 `game_pa_events` fingerprint，成員／投打／終點變動即 `reconciliation_required`，**禁 delete-and-reinsert／禁靜默換 ID**，僅可證明一對一延續才保留 `pa_id`，其餘 `unreliable` 並讓 WP／逐球 fail-closed 回 `null` |
| availability 語意 | ✅PASS | public `tracking_availability` 六值與 spec §7 表**逐字一致**；四條硬性分流誠實：無歷史 ingest→`source_missing`(`source_not_collected`)、官方未更新才 `advanced_pending`(需 revision 證據)、`no_equipment` **僅在 STATUS1／官方球場清冊有正證據時可用、DATA1「未觀測」不可推論**、候選不唯一→`mapping_failed` 不傳空陣列 |
| 切卡防近似鍵回歸 | ✅PASS | `TAXONOMY1`(read/none，真實 action 值域建 transition table，禁名稱猜語意)→`EXPAND1`(schema/expand)→`BUILD1`(data-migration，僅前二者查核通過後啟動)；各自獨立 claim＋隔離 DB lease＋跨家族查核；`WP-*` 與精確逐球 UI **保持阻塞**直到 BUILD1 對帳門檻過 |

## 2. 事實回源查證（不虛構表／欄位 §7）

| 契約引用 | 回源 | 判定 |
|---|---|---|
| livelog `action_name`／`batting_action_name`／`main_event_no`／`is_change_player`／`is_special_event`／`pitch_cnt` | [`cpbl_gamelog.py:114-118`](../../src/cpbl/ingest/cpbl_gamelog.py) `_LL_COLS` 全數存在 | ✅真實 |
| pitch local key `(year,kind,game,pitcher,pitch_cnt)` | [`migrations/018_pitch_tracking.sql:34`](../../migrations/018_pitch_tracking.sql) PK=`(year,kind_code,game_sno,pitcher_acnt,pitch_cnt)`；註解「`(game,pitcher,pitch_cnt)` 唯一」 | ✅真實 |
| 「現有複合主鍵可作 local reference，非官方 immutable pitch ID」 | 018 無官方 pitch id 欄位，判定正確 | ✅屬實 |
| `tracking_availability` 六值域 | spec §7 line 126 逐字相符 | ✅一致 |
| PA base 欄位不含 WP、availability 屬 PA 層 | spec §8.1／§8.2 一致（WP 屬 WP-API1） | ✅一致 |

## 3. NO-GO 前提回源（三套近似分組確實邊界不一）

契約結論全靠「三套近似鍵在同局重複投打／換投／代打產生不同邊界」。逐一回源真實程式：

| 近似分組 | 真實實作 | 判定 |
|---|---|---|
| run_dist 半局內 `(batting_order,hitter)` 去重、`skip is_change_player` | [`winprob.py:71-74`](../../src/cpbl/models/winprob.py) `pa_key=(batting_order,hitter_acnt)` | ✅忠實 |
| WP `(inning,half,batting_order,hitter)` 去重、`skip is_change_player` | [`games.py:287-288`](../../src/cpbl/api/routers/games.py) | ✅忠實 |
| 前端 buildMoments 從 WP 起點掃連續同 hitter、`skip is_change_player` | [`overview.tsx:28-36`](../../web/src/app/games/[sno]/overview.tsx) `hitter=log[start].hitter_acnt`；`hitter_acnt !== hitter → break` | ✅忠實 |

三者皆以 `(batting_order/hitter)` 為鍵並跳過換人，故**同局同打者二度打擊（打線打回一輪）或打席中換投**會在三層產生不一致邊界——契約 NO-GO 立論成立，非虛構。

## 4. 驗收條件對應（本卡定義、subcard 落地）

本卡 §驗收/§驗證 checkbox 為最終實作標的，刻意由子卡落地；查核判定**契約是否已把每條定義到可被 subcard 驗收**：

| 卡片驗收條件 | 契約落點 | 判定 |
|---|---|---|
| 穩定 `pa_id`／refresh 冪等相同 ID | §不變量 2＋§狀態機 3、「同一來源重跑」紅燈斷言 | ✅已定義 |
| 下游只消費同一契約、不自行分組 | §不變量 5 | ✅已定義 |
| PA 層 `tracking_availability`＋reason、不代理 WP | §不變量 4＋§逐球 mapping | ✅已定義 |
| 同局重複／換投／代打／缺 pitch count fail-closed | §發布門檻紅燈表 6 案例 | ✅已定義 |
| 按單一 `pa_id` 回逐球、首屏不傳整場 payload | §發布門檻 API 斷言＋spec §10 | ✅已定義 |
| 無設備／官方未更新／缺漏／mapping 失敗四狀態分離 | §逐球 mapping 四分流 | ✅已定義 |
| 對帳率依年／球場／賽制輸出、未達門檻不開 UI | §發布門檻末段 | ✅已定義 |

## 5. 非阻擋事項（不影響 APPROVE）

- **N1（機械性，merge 前處理）**：執行分支 merge-base（`298a3ec`）落後 `main`（現 `f643620`）；main 領先兩筆皆僅動 `docs/TASKS.md`／`events.jsonl`，與本分支（僅 design/card 文件）無交集，`git merge-tree` 試算無衝突。merge 前 rebase 即可。
- **N2（流程後續，非缺陷）**：`TAXONOMY1`／`EXPAND1`／`BUILD1` 尚未註冊／認領——契約與卡片刻意載明「需求方＋跨家族／人工查核核可契約前禁止註冊／認領」。屬設計，非本卡缺失。
- **N3（文件可讀性，選作）**：`pa_id` UUIDv5 seed 含 event-order version 與「持久化該 `pa_id`」的關係，建議 EXPAND1／BUILD1 spec 明示「持久化錨定**首次發布身份**、seed 僅供初次生成，後續一律走 reconciliation 比對」；契約 §狀態機 step 4 已隱含涵蓋，僅為降低實作者誤讀。

## 6. 驗證

- 交付為 docs-only（design 契約＋卡片文字），無程式碼路徑，pytest／ruff 對本交付無增量訊號；執行者 handoff 已記 worktree 內 `git diff --check`／`ruff check`／`pytest 332 collected；1 skipped` PASS。查核未改動任何交付物與 source／schema。
- 本查核採唯讀對帳（契約 vs spec vs 程式碼事實），符合 T4 紅線「換模型家族＋實測證據」。

---

**Verdict = APPROVE（P0=0）。** 跨模型家族獨立查核（Opus 4.8 ≠ 執行者 GPT-5@Codex）已解除 GAME-RECAP-PA1 契約的 T4 資料正確性紅線。此查核**不合併執行分支、不註冊子卡、不部署**；下一關為**需求方 ruan6047 核可契約與三張子卡切分**（比照 DATA1 Checkpoint），核可後方可由 Coordinator rebase＋merge 契約至 main 並註冊／認領 `TAXONOMY1`／`EXPAND1`／`BUILD1`。
