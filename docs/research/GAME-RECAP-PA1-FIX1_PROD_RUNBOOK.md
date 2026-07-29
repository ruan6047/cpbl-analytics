---
title: "GAME-RECAP-PA1-FIX1 生產 PA 重建操作單"
card_id: GAME-RECAP-PA1-FIX1
status: pending-operator
role: 需求方（ruan6047）親自執行——`DATABASE_CONTRACT.md` 保留 production 寫入憑證
date: 2026-07-29
tags:
  - cpbl
  - game-recap
  - pa-build
  - data-migration
  - production
---

# 生產 PA 重建操作單

> **為什麼需要這張單**：submodule bump（主站 `321c41f` → cpbl `537d7f7`）只部署**程式碼**，
> 生產 PA 資料**一列都不會變**——生產 API 不讀 `end_hitter_acnt`、生產 crontab 沒有排程跑
> `cpbl-build-pa`（`INGEST-PA-DAILY1` 仍在 Backlog）、PA 四表不在 `refresh-cpbl-prod.sh`
> 同步清單。生產目前仍是 BUILD1 輸出：296 對誤切、2,185 筆 outs 錯值、282 筆歸屬錯誤。
>
> 本機已完成同樣的重建並經六輪跨家族查核 APPROVE；下列步驟與本機執行過的完全一致。

## 前置檢查

```bash
ssh root@45.76.100.29 'cd /opt/personal-website && docker compose -f docker-compose.prod.yml ps prod_cpbl_api'
```

確認映像已是 bump 後版本（部署完成後）。**映像未更新就跑 migration 會找不到 068/069**
——Runbook §3 明載「production migration 由已部署的 `prod_cpbl_api` 映像執行；若 local main
已有 migration 修正、production 映像尚未部署，先完成正常 main deploy」。

## 1. 備份（`DATABASE_CONTRACT.md`：結構操作前必先備份）

```bash
ssh root@45.76.100.29 'cd /opt/personal-website && bash infra/scripts/backup-db.sh /opt/backups'
```

生產 crontab 每日 03:00 亦有自動備份，但**結構操作前須有一份即時的**。

## 2. 套 migration（068 加欄、069 換唯一鍵，皆冪等 `IF NOT EXISTS`）

```bash
ssh root@45.76.100.29 'cd /opt/personal-website && docker exec prod_cpbl_api python -c "from cpbl.db import migrate; print(migrate()[-3:])"'
```

**預期輸出**尾三個含 `067_home_run_log.sql`、`068_pa_end_hitter.sql`、`069_pa_pitch_mappings_per_build.sql`。

> `api` 啟動**不自動 migrate**，這是手動步驟（記憶 `advanced-snapshot-reconcile` 同一坑）。

## 3. 全庫重建

```bash
ssh root@45.76.100.29 'cd /opt/personal-website && docker exec prod_cpbl_api cpbl-build-pa --from-year 2018 --to-year 2026 --kind A --kind C --kind D --kind E'
```

**不需要爬蟲**（builder 只讀 DB），故生產可自跑。本機耗時約 100 秒／4,279 場。

**預期尾行**（本機實測形狀；生產場次數依其 `game_livelog` 母體而定）：

```
build_scope done: {'games': N, 'actions': {'publish': N-1, 'reconcile': 1},
                   'build_states': {'published': N-1, 'reconciliation_required': 1},
                   'errors': []}
```

`errors` **必須為空**。中途會有一行 ERROR log：

```
invariant violated (half-inning out PA > 3), not publishing 2019/A/173 ...
```

**這是預期行為**——該場來源資料損壞（已單場重爬證實損壞在官網源頭），fail-closed 隔離是正解。

## 4. 驗收（唯讀，可直接比對本機數字）

```bash
ssh root@45.76.100.29 'cd /opt/personal-website && docker exec prod_cpbl_api python /app/scripts/report_pa_rebuild_fix1.py'
```

若映像未含 `scripts/`（Dockerfile 只 COPY src），改用等價 SQL：

```bash
ssh root@45.76.100.29 'cd /opt/personal-website && set -a && . ./.env && docker exec prod_pg psql -U "$DB_USER" -d "$DB_NAME" -c "
select builder_version, state, count(*) from cpbl.game_recap_builds group by 1,2 order by 1,2;" -c "
select count(*) as over3 from (
  select pa.year,pa.kind_code,pa.game_sno,pa.pre_state->>%s,(pa.pre_state->>%s)::int
  from cpbl.game_plate_appearances pa
  join cpbl.game_recap_builds b on b.build_id=pa.build_id and b.state=%s
  where pa.state=%s and pa.outcome_family in (%s,%s)
    and pa.pre_state->>%s in (%s,%s) and pa.pre_state->>%s is not null
  group by 1,2,3,4,5 having count(*)>3) t;"'
```

（參數化留給操作者填 `half`/`inning`/`published`/`ready`/`out`/`sacrifice`/`half`/`1`/`2`/`inning`；
或直接用上方 report 腳本較省事。）

**驗收門檻（與本機一致）**：

| 項目 | 預期 |
|---|---|
| 半局出局 PA > 3（published+ready） | **0** |
| `(半局, pre_outs)` 重複（published+ready） | **0** |
| published build | 全為 `pa-build-1.3.0` / taxonomy `1.1.0` |
| 隔離場次 | 恰 `2019/A/173`（該場零 published） |
| 每場 published 數 | 至多 1（唯一例外即被隔離場） |

## 5. 服務面驗證

```bash
curl -s https://cpbl.ruan-ruan.com/api/info | python3 -m json.tool | head -20
```

`status` 應為 `running`。PA 表的消費面（`/recap-wp`）走 published-only gating，
`2019/A/173` 會自然回 unavailable——**這是正確行為，不是故障**。

## 回滾

migration 068/069 皆為 **additive**（加欄、換唯一鍵範圍放寬），不刪任何資料。
重建亦不刪 build——舊 BUILD1 build 轉 `superseded`、列全保留。
若需回退消費面，把目標場次的舊 build 狀態改回 `published` 即可（同時把新的降級），
但**不建議**：舊資料即是本卡修正的缺陷資料。

## 完成後

請告知，我會寫 release 事件把卡轉 `✅已驗證` → `🏁完成`，並執行結案五步
（終態事件→卡檔封存→Ledger 重建→lease／分支清理→對帳三件套）。
