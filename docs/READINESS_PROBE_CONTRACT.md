# CPBL 內部就緒探針契約（#332）

> 消費者：PersonalWebsite #63 的 Compose healthcheck／腳本。本檔只描述 CPBL 產生的訊號；
> 接線、部署與主站門檻由 #63 負責。公開 `/healthz`、`/api/info` 的 HTTP 200 降級契約不變，
> 本探針**不是**公開端點，也不新增 HTTP 路由或 port。

## 1. 呼叫

在**目標服務自己的容器內**執行（`docker compose exec` 或 Compose `healthcheck.test`）：

```bash
python -m cpbl.readiness --target api      # 在 api 容器
python -m cpbl.readiness --target worker   # 在 live-worker 容器
```

- stdout 恆為**單一行 JSON**；stderr 不保證為空，消費端不得解析 stderr。
- 總預算：父程序以 9s 終止探測子程序，加上直譯器啟動與輸出，呼叫端 timeout 至少給 10s。

| 退出碼 | `result` | 意義 |
|---|---|---|
| 0 | `ready` | 已就緒 |
| 1 | `not_ready` | 已知失敗（依賴錯誤、worker 停用／killed／locked／輪次錯誤、交付 partial） |
| 2 | `unknown` | 無法證明（逾時、缺設定、證據過期或失聯、壞形狀） |
| 3 | `unknown` | 探針本身失敗（參數錯、子程序輸出違約）；`reasons=["probe_failed"]` |

消費端規則：只有「退出碼 0 **且** JSON `ready:true`、`schema_version:1`、`target` 相符」才算就緒；
非零、缺 JSON、未知 `schema_version`、碼與欄位矛盾一律視為未就緒。

## 2. 共同欄位

```json
{"schema_version":1,"target":"api","ready":true,"checked_at":"2026-10-19T04:07:52.940789+00:00",
 "result":"ready","reasons":[], ...target-specific}
```

`reasons` 為排序、去重的固定代碼；不含連線字串、錯誤本文或憑證。

## 3. `--target api`

- DB：讀 `DATABASE_URL`（必須明示設定，不吃預設值）。取連線上限 3s（池逾時＝`db_timeout`）、
  `statement_timeout=1500ms`；`SELECT current_user, current_database()` 必須等於 DSN 的
  user／dbname，再跑 `cpbl.games` 代表欄位 `LIMIT 0`。**空表合法**。
- Redis：讀 `REDIS_URL`（必須明示）；connect／read timeout 各 1s，回應必須是精確 `PONG`。
- 已知錯誤優先於 unknown：任一依賴 `error` ⇒ `not_ready`。

範例（隔離環境實測，2026-10-19）：

```json
{"schema_version":1,"target":"api","ready":false,"checked_at":"…","result":"unknown",
 "reasons":["redis_timeout"],"dependencies":{"database":{"state":"ok","identity_match":true,
 "games_shape":true},"redis":{"state":"unknown","pong":null}}}
```

| reasons | result |
|---|---|
| `db_config_missing`／`redis_config_missing`／`db_identity_unknown` | unknown |
| `db_timeout`／`redis_timeout` | unknown |
| `db_identity_mismatch`／`db_query_failed`／`redis_connection_failed`／`redis_invalid_pong` | not_ready |

⚠️ 已知限制：密碼錯誤等認證失敗會被連線池重試吞掉原因，呈現為 `db_timeout`（unknown，約 3.2s），
不是 `not_ready`。方向是保守的（不會誤判 ready）。

## 4. `--target worker`

### 證據位置與權限

| 項目 | 值 |
|---|---|
| 目錄 | `LIVE_WORKER_READINESS_DIR`，預設 `/tmp/cpbl-live-readiness`（容器內 `/tmp` 隨容器生命週期＝同實例） |
| 目錄權限 | 0700，擁有者須為 worker 的 euid；不符時 worker 停用證據、讀取端回 `evidence_dir_unavailable` |
| 最新摘要檔 | `<dir>/latest.json`，0600，`{"summary":…,"digest":sha256}`，摘要上限 64KiB（6 分區／8 場） |
| Unix socket | `<dir>/worker.sock`，0600；只接受一行 `{"nonce":"<32 hex>"}`，回最新摘要並回聲 nonce |
| Redis 輪次憑據 | `<LIVE_GAME_CACHE_PREFIX>:readiness:<instance>`（預設 `cpbl:live:readiness:<instance>`），TTL＝sleep＋180s |

容器存取要求：探針必須以**與 worker 相同的 UID** 在**同一容器**內執行（映像 `USER app`；
`docker compose exec live-worker …` 預設即是）。以 root 或其他 UID 執行會因擁有者檢查回 unknown。
不需要額外 volume、port、capability。`LIVE_GAME_WORKER_ENABLED`、`REDIS_URL` 須與 worker 同值
（同容器即自動成立）。

### 判定順序

1. `LIVE_GAME_WORKER_ENABLED` 非真 ⇒ `not_ready`／`worker_disabled`。
2. socket 必須存在、0600、本 UID；送新 nonce，1.5s 內回聲 ⇒ 否則 `unknown`
   （`worker_socket_unavailable`、`worker_unreachable`、`worker_nonce_mismatch`、`worker_reply_invalid`）。
   程序停止、凍結或卡死都落在這裡；舊檔與舊 Redis 紀錄**不能**代替存活。
3. 記憶體 M2（最近完成輪）至少要與本機檔或 Redis 憑據之一的 instance／attempt／digest 相同；
   任一較新或兩處皆舊 ⇒ 2s 後重讀**一次**，仍不一致 ⇒ `unknown`
   （`evidence_persist_stale`、`evidence_cross_round`）。尚無完成輪 ⇒ `no_completed_attempt`。
4. 時效：`valid_until = finished_at + 實際 sleep 秒數 + 60s`，超過 ⇒ `evidence_stale`；
   新一輪已開始（M1）超過 120s 仍無結論 ⇒ `cycle_timeout`。
5. 以上通過時，`result` 取 M2 的單輪結論（最新 attempt 優先，舊成功不參與）。

### 單輪結論（worker 端計算）

| 情況 | result | reasons 範例 |
|---|---|---|
| legacy `disabled`／`killed`／`locked`／`error` | not_ready | `worker_killed`、`worker_cycle_error` |
| 任一分區 `Games` 缺席／null／非 list、列身份或時間不明、分區抓取失敗 | unknown | `partition_games_not_list`、`partition_rows_invalid`、`partition_fetch_failed` |
| 明確 `Games: []` | （合法零場） | — |
| 超過既有每輪上限（overflow）、單場來源失敗、寫入讀回不一致 | not_ready | `delivery_partial` |
| 必要欄位（身份、時間、已知 phase、兩隊、live/final 比分、來源版本）缺或投影遺失、LiveLog 形狀未知 | unknown | `snapshot_phase_unknown`、`raw_livelog_malformed` |
| 觀測元件自身故障 | unknown | `observer_fault:<hook>` |

逐場處置 `disposition`：`write_readback`（寫入後讀回一致）、`reused_final`（既有 final 必要欄位完整，
未改寫、原 TTL／時點保留）、`moved_out_of_window`（明細開賽時間已移出觀測窗）、`failed`、`incomplete`。
不宣稱官方更正或全 PA 到齊。

合法缺值（未公告先發、部分打序、TrackMan pending、非 final 賽果遮蔽）只進
`worker.source_availability`（`complete`／`partial`），**不影響** `result`；與 `worker.delivery` 分列。

### 範例

```json
{"schema_version":1,"target":"worker","ready":true,"checked_at":"…","result":"ready","reasons":[],
 "worker":{"instance":"1adce49b…","in_progress":false,"current_attempt_started_at":null,
  "evidence":{"file":"match","redis":"match"},"persist":{"file":"ok","redis":"ok"},
  "attempt":7,"started_at":"…","finished_at":"…","sleep_seconds":13,"valid_until":"…",
  "legacy_state":"ok","partitions":[{"kind":"A","year":2026,"month":10,"state":"complete",
  "explicit_list":true,"row_count":1,"invalid_identity_count":0,"invalid_time_count":0}],
  "candidate_count":1,"selected":["2026-A-226"],"overflow_count":0,
  "games":[{"game_id":"2026-A-226","disposition":"write_readback","phase":"live","reasons":[]}],
  "delivery":{"state":"complete","moved_out_of_window":0,"reused_final":0,"write_readback":1,
   "failed":0,"unresolved":0},
  "source_availability":{"state":"partial","games":[…]}}}
```

## 5. 不做的事

- 不改抓取、選場、轉換、補抓、同步、鎖、冷卻或既有 snapshot／lock／health 鍵的 TTL。
- `--once` 模式不產生證據，輸出與退出碼不變。
- 不自動關流量、重啟、補抓或修復；探針只揭露。
- 不承接 #293 的賽後資料交付／受保護同步。
