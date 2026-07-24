---
title: "GAME-RECAP-PA1-BUILD1 canonical PA builder 交付 Handoff"
card_id: GAME-RECAP-PA1-BUILD1
status: awaiting-independent-review
role: executor（Opus 4.8）
date: 2026-07-24
tags:
  - cpbl
  - game-recap
  - pa-build
  - data-migration
  - handoff
---

# GAME-RECAP-PA1-BUILD1 交付 Handoff

關聯：[[GAME-RECAP-PA1]]、[[GAME-RECAP-PA1_CONTRACT]]、[[GAME-RECAP-PA1-EXPAND1]]、
[[GAME-RECAP-PA1-TAXONOMY1]]、[[GAME-RECAP-DATA1]]。

> **執行者 = Opus 4.8；本報告交付後狀態 🔍待查核。** 查核須由**跨模型家族且非 Claude**
> 之查核者（Gemini／Antigravity 或人工）進行。執行者不得自寫 APPROVE／merge。

## 1. 交付範圍與結論

實作每日批次 canonical PA builder，依 TAXONOMY1（taxonomy_version=1.0.0）把來源 revision
物化為 deterministic、持久化的 `pa_id`、event membership 與 ordered pitch mapping，寫入
EXPAND1（migration 066）建的 5 張表。**不新增 WP／WPA、不新增 public API／前端**（非目標）。

- 逐球來源 (`pitch_tracking`) **唯讀**：未改逐球 parser、refresh 正式路徑、schema 或寫入契約
  （INGEST-GAME-TM-REFACTOR1 Gate 3 shadow 觀測期紅線未觸碰）。
- 執行分支 `ai/opus-4-8/GAME-RECAP-PA1-BUILD1`；未改 `docs/control-plane/**`、`docs/TASKS.md`。

## 2. 檔案清單

| 檔案 | 作用 |
| --- | --- |
| `src/cpbl/ingest/pa_build.py` | builder：純核心（island／分類／pa_id／fingerprint／逐球映射／reconciliation）+ 薄 DB 層（fetch／source manifest／atomic publish／backfill／QA） |
| `src/cpbl/ingest/run_build_pa.py` | CLI `cpbl-build-pa`（單場／範圍回填 + QA 報告） |
| `tests/test_pa_builder.py` | 32 純函式紅燈 + 整合測試 |
| `scripts/rehearsal_pa_build.py` | DB 層 rehearsal：publish → 冪等 noop → reconciliation |
| `pyproject.toml` | 註冊 `cpbl-build-pa` entrypoint |
| `docs/research/GAME-RECAP-PA1-BUILD1_QA.md` | 全史回填 QA 對帳（自動產生） |

## 3. Builder 設計（供查核者複核）

### 3.1 資料流

```
game_livelog ─┐            ┌─► game_recap_source_revisions (immutable manifest: sha256+parser+max_key)
              ├─ build_game ┼─► game_recap_builds (每 build 一列；partial unique：每場≤1 published)
pitch_tracking┘ (唯讀)      ├─► game_plate_appearances (pa_id + state + tracking_availability)
                           ├─► game_pa_events (成員全序 + fingerprint)
                           └─► game_pa_pitch_mappings (逐球 mapped/failed；每球至多一個 PA)
```

### 3.2 島 → PA → state（分類消費 TAXONOMY1）

- **island 偵測**：連續同 `(inning_seq, visiting_home_type, hitter_acnt)`；`is_change_player`
  與空 hitter 列**附掛不切界**；`main_event_no::bigint` 全序。與
  `scripts.pa_transition_taxonomy._island_starts` 有 conformance 測試釘住（無語意漂移）。
- **分類**：讀版本化 `pa_transition_taxonomy.v1.json` 的 role／outcome_family：
  - `completed_pa`（登錄 pa_terminal，含無投球 award）→ **ready**
  - `unknown_action`（有 action 未登錄）→ **unreliable**（fail closed）
  - `truncated_fragment`（空 action 有投球）→ **truncated**
  - `non_pa_tiebreak` / `non_pa_running_fragment` → **non_pa**（不進 PA 分母）
- **決策點供複核**：`outcome_family=uncaught_third_strike` 的不死三振為登錄 pa_terminal，
  本 builder 判 **ready**（保留 `outcome_family` 供 WP-VAL1 自行決定是否排除）；未把合法
  PA 誤降 unreliable。

### 3.3 穩定 `pa_id`

deterministic UUIDv5，namespace 固定，seed = `year|kind|game|start_event_no|event_order_version`
（`event_order_version=evord-1.0`）。同 start 事件跨 build／revision 恆同一 `pa_id`。PA 實體
FK 目標為代理鍵 `pa_row_id`（乾淨引用完整性），`pa_id` 為索引非唯一（跨 build 相同）。

### 3.4 逐球映射（每球至多一個 PA — 契約紅燈）

`pitch_tracking (pitcher_acnt, pitch_cnt)` 全場逐投手唯一；映射靠 PA 成員的真實投球列
`(pitcher_acnt, pitch_cnt, hitter_acnt)` 對齊。牽制／暫停列沿用前一 `pitch_cnt` 但可能已換
hitter → **用 hitter 排除跨 PA 誤綁**。全庫實測：**73,826 顆逐球唯一歸屬單一島（99.98%）**，
僅 12 顆跨島歧義 + 2 顆孤兒 → 全部 fail closed（`mapping_state=failed` / orphan，不虛構歸屬、
不傳空 list 假裝無球）。DB 端 `(source_revision_id, pitcher, pitch_cnt)` UNIQUE 硬保證。

`tracking_availability`：無逐球源 → `source_missing`(reason=source_not_collected)；有源且期望
投球全 mapped → `available`；否則 `mapping_failed`。**不由「未觀測到」推論 `no_equipment`**
（需 STATUS1 正證據）。

### 3.5 reconciliation / fail closed（不靜默替換已發布 `pa_id`）

- 同一來源重跑（sha 相同 → 同一 revision id、同 builder／taxonomy version）→ **冪等 no-op**。
- 晚到／修正 revision：先比對既有 published build 的 `pa_id × PA fingerprint`
  （fingerprint 由 published 已儲存欄位無損重建，算法與新 build 共用）。
  - 完全等價 → publish（atomic swap：同交易 demote 舊 → 發布新）。
  - 任一成員／投打／終點變更或有新增／消失 `pa_id` → 產出 **reconciliation_required** build，
    **不** publish、**不** 刪舊、**不** 換 ID；變更 PA 標 `reconciliation_required`，保留舊
    published 供稽核。

## 4. 契約「發布門檻與紅燈測試」對應

| 契約案例 | 落實 | 證據 |
| --- | --- | --- |
| 同局重複投打 → 相異 `pa_id`；每球≤1 PA | pa_id seed 含 start_event；映射 (pitcher,pitch_cnt,hitter) | `test_repeat_batter_pas_have_distinct_pa_ids`、`test_each_pitch_bound_to_at_most_one_pa`；真實 2026/A/54、162 |
| 打席中換投／代打／換人 → 起訖投打可追溯；無規則即 unreliable | start/end_pitcher + member events；unknown→unreliable | `test_pitching_change_stays_one_island`、真實 2025/A/52 PA#63（起投≠終投） |
| 缺球／無 TrackMan／晚到逐球 → 三態分開 | source_missing / mapping_failed / available | `test_no_tracking_source_is_source_missing_not_no_equipment`、`test_missing_pitch_is_not_faked_as_empty` |
| 同一來源重跑 → 完全相同 | 冪等 no-op；同 pa_id／membership／order | `test_same_revision_rerun_is_identical`、rehearsal v2 |
| 來源修正／晚到 → 不靜默替換已發布 ID | reconciliation_required build、保留舊 published | `test_reconcile_*`、rehearsal v3 |
| API 首屏不傳整場 tracking | 本卡不做 API（非目標）；route snapshot 未變 | `test_route_snapshot` 全綠 |

## 5. QA 對帳結果（全史回填 rehearsal）

全史（1990–2026、kind A/C/D/E）本機回填：**4263 場，4257 publish + 6 noop（冪等重跑證明），
0 失敗**。全部 published，每場恰一個 published build。

**PA 分母（published）**

| 指標 | 數值 |
| --- | --- |
| 全 island（candidate PA） | 330,268 |
| ready（完成 PA，登錄 pa_terminal） | 328,286（99.4%） |
| unreliable（unknown_action fail closed） | **0**（taxonomy 覆蓋全 action 值域） |
| truncated（空 action 有投球，跑壘/局終截斷） | 1,734 |
| non_pa（tiebreak／純跑壘殘列） | 248 |
| reconciliation_required（回填皆首建，無晚到） | 0 |
| distinct `pa_id` | = PA 列數（無碰撞） |

**逐球對帳（全庫 73,840 顆）**

| 指標 | 數值 |
| --- | --- |
| mapped | 73,633 |
| failed（非 ready PA 的球 + ambiguous） | 205 |
| orphan（無 PA 成員擁有；資料品質邊界） | 2 |
| 合計 | 73,633 + 205 + 2 = **73,840 全數歸屬** |

**tracking_availability（published PA）**：available 19,356、mapping_failed 674、
source_missing 309,990（多為 2026 前無逐球 ingest 之年；無設備球場如台東/嘉義市／花蓮亦計
source_missing，未推論 no_equipment）。

**全庫紅線驗證（SQL 直查全部 mapping／build）**

| 檢查 | 結果 |
| --- | --- |
| 任一逐球綁到 >1 個 PA（每球至多一個 PA） | **0 違反** |
| 任一場有 >1 個 published build（atomic 唯一） | **0 違反** |
| mapping 列數 = 73,838 = 73,840 − 2 orphan | 一致 |

**資料量**：5 張 `game_recap_*`／`game_pa*`／`game_plate_appearances` 表共 ~791 MB（主體為
`game_pa_events` 1,330,123 列＝每 livelog 事件一列）。

完整每年/賽制/球場對帳（170 列）見 [`GAME-RECAP-PA1-BUILD1_QA.md`](GAME-RECAP-PA1-BUILD1_QA.md)。

## 6. Rehearsal／備份／rollback 證據

### 6.1 本機 rehearsal

- **migration 冪等**：`migrate()` 全 66 檔重跑乾淨（含 066）；`test_migration_rerun`、
  `test_game_recap_pa_expand` 全綠。
- **全史回填**：`cpbl-build-pa 1990–2026 A/C/D/E` 逐場 commit、可續跑（crash 後重跑冪等 skip
  已完成場）；單場失敗不阻斷（記錄後續跑）。
- **DB 層 reconciliation rehearsal**（`scripts/rehearsal_pa_build.py`，合成 year=2099 場、
  只動 livelog、跑完清理）：publish → 冪等 noop → reconciliation 三步 assert 全過，證實
  「不換 ID、不刪舊 published、atomic 唯一」。

### 6.2 production 備份／rollback（部署鏈執行，非本卡執行）

本卡為**純 additive 資料 migration**：只寫 066 新建的 5 張 `game_recap_*` 表，**不轉換／不刪
既有資料**，故 rollback 風險極低。

- **備份**：production 部署前由 `scripts/backup-cpbl-prod.sh` 產生 `cpbl` schema 完整 gzip
  備份（驗證後才晉升，保留 7 份）；見 Runbook §3。**看見「已驗證備份」前不得進 production
  migration**。
- **rollback（三層，由輕到重）**：
  1. 重建：published build 可用 atomic swap 重新發布；reconciliation build 不影響現行 published。
  2. 清空 PA 資料：`TRUNCATE cpbl.game_pa_pitch_mappings, cpbl.game_pa_events,
     cpbl.game_plate_appearances, cpbl.game_recap_builds, cpbl.game_recap_source_revisions
     RESTART IDENTITY;`（純 additive，清空不影響 livelog／pitch_tracking／其他 schema）。
  3. schema 還原：`gunzip -c <backup>.sql.gz | ... psql`（只還原 `cpbl` schema，見 Runbook §3）。
- **可續跑**：backfill 逐場 commit；中斷後重跑由冪等 no-op 快速跳過已完成場，無需游標檔。

## 7. 驗證

- `uv run ruff check` → **All checks passed**。
- `uv run pytest` → **452 passed, 3 skipped**（含本卡 32 新測試；route snapshot 未變）。

## 8. 部署與 sign-off 閘門

> **更正（post-review，2026-07-24；不動任何程式碼）**：原文誤述「066 尚未部署 production」。
> 事實查證：deploy commit `83ad0ad`（deploy EXPAND1 066 to production）**已在 `origin/main`**
> （`git merge-base --is-ancestor 83ad0ad origin/main` 為真）→ **migration 066（PA schema）
> 早已上線 production**。以下為更正後的部署範圍。

- 需**需求方 data-migration sign-off** 才部署 production（DATABASE_CONTRACT §4）。
- **066 schema 端已在 production**，本卡剩餘部署範圍為 **BUILD1 builder 程式碼 + production 回填**：
  1. merge 本分支 → main → 部署 `prod_cpbl_api` 映像（含 `pa_build.py` / `cpbl-build-pa`）。
  2. 對 production 執行回填：在 prod 容器跑 `cpbl-build-pa`（冪等、可續跑、逐場 commit），
     或 local→prod 同步 derived `game_recap_*` 表（比照 outcome-prediction-refactor 鏡像模式）。
  3. production migration 若有後續 migration 由已部署映像執行；本卡不新增 migration。
- production 動作前先依 §6.2 產生並驗證 `cpbl` schema 備份；本機爬→同步生產紀律見 Runbook §3。

## 9. 查核指引（reviewer checklist）

1. 逐球映射：抽驗 published build，確認 `game_pa_pitch_mappings` 每 `(pitcher,pitch_cnt)` ≤1 列、
   `mapped+failed = pitch_tracking` 場球數（無遺漏、無重複綁）。
2. 同局重複打者：抽驗真實場（2026/A/54、162）H1 兩打席 `pa_id` 相異。
3. reconciliation：跑 `scripts/rehearsal_pa_build.py`，確認 v3 舊 published `pa_id` 不變。
4. fail closed：確認 unknown_action→unreliable、truncated 的球 mapping_failed、orphan 不虛構。
5. taxonomy pin：確認 `game_recap_builds.taxonomy_version=1.0.0`、`builder_version=pa-build-1.0.0`。
6. 非目標：確認未新增 API 路由（route snapshot）、未改逐球 parser／schema。

## 10. Owner 更正

lease owner placeholder 為「Opus 4.8（執行）」，與實際執行者一致，無需更正。
若 handoff append-only 顯示 owner 非 Opus，請以此報告更正為 Opus 4.8（執行者）。
