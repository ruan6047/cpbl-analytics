# #393 原 WP6 測試與操作差異

本文件是待核整合租用的操作輸入，不是執行收據。產品基準為 `377f795ce1be2c11cc99f1c684fcb21e0763ffa3`；只有本文件與同版三個測試檔新增。核發前只做本機合成自查，不讀真 raw、備份、CSV、模型或秘密，不連 DB、Docker、官方、Pi、VPS、HC 或 launchd。

## 1. 原驗收與精確節點

原 PLAN SHA256 `7d2c123440d502ea25b960a807244f8753242f73993c29eea9acc7aa4550d3c1` §10.2/.3/.4/.6；以下共 24 個 runtime 節點，只有原七故障的原變體，沒有新增驗收族群。測試檔為 `tests/test_wp6_393.py`。

| 原項 | pytest 節點（中括號內逐項執行） | 通過契約 |
|---|---|---|
| §10.2 六工作 | `test_runtime_historical_job_real_parser_and_isolated_pg[scrape-daily]`，另五參數為 `postseason-evening`、`weekly-box-revisions`、`weekly-game-pitches`、`schedule-watchdog`、`alert-watch` | 原 main／parser／SQL、真 capture、真隔離 PG；rc0；worker 需真正讀來源，兩觀測工作需真正讀同 PG 的 API；45 表列數／hash／逐列差異歸因 |
| 故障 1–4 | `test_runtime_original_source_faults_keep_real_job_and_pg[pi-unavailable]`；另五為 `manifest-expired`、`bundle-corrupt`、`bundle-oversized`、`stats-403`、`stats-timeout` | 原工作非零退出；不可用／過期／內容破壞或超大／HTTP 403 或 timeout 只注入外部邊界；stats 故障需真觸發該 URL，既有 features 仍非空 |
| 故障 5 | `test_runtime_transaction_sigterm_native_cid_and_real_rollback` | 真 games 寫入交易尚未 commit，原 TERM handler／原 rollback、綁定 CID 的 native wait=143、PG backend 消失、自己的鎖釋放、games 已提交資料 count/hash 完全不變 |
| 故障 6–7 | `test_runtime_original_native_lifecycle_fault_evidence_and_pg[scheduler-stopped]`、`[deployment-recreated]` | 原 WP5 真原生 stop／recreate，固定 lease/image；停止案例另跑原 watchdog；重建需新 CID 同 image 且 running，不能用 busy75 冒重建 |
| §10.3 兩情境 | `test_runtime_original_trainer_decoupling_real_feature_api_artifact[trainer-not-run]`、`[trainer-failed]` | 真 trainer 入口選 PG 列後在 backtest 邊界失敗，或完全未啟 trainer；之後原 daily、真 materialize 非空、發布標記、真 artifact.predict、隔離 API 非空；artifact hash 不變 |
| §10.4 三事件 | `test_runtime_original_three_test_check_events[failed]`、`[interrupted]`、`[silent]` | VPS 發 test fail／start 無 finish／停止 ping；真 API down、獨立通知送達證據、原四欄設定恢復＋success reset |
| §10.6 四路徑 | `test_runtime_original_season_and_starter_controls[closed-paused]`、`[open]`、`[checkpoints-enabled]`、`[watch-enabled]` | 真 season_close；收官不爬仍發布；原 paused 名存在、enabled 不存在；open 僅測試環境；啟用需原 record_attempt／record_fetch 真處理非空項目 |

六個工作是固定原介面：

```text
python /app/jobs/jobs.py scrape-daily
python /app/jobs/jobs.py postseason-evening --stage all
python /app/jobs/jobs.py weekly-box-revisions --year 2026 --days-back 365
python /app/jobs/jobs.py weekly-game-pitches --year 2026
python /app/jobs/jobs.py schedule-watchdog
python /app/jobs/jobs.py alert-watch
```

`weekly-box-revisions --days-back` 只能既有整數 1–366，由核發日與選定真 2026 場次固定；365 是本提案，不冒實跑值。測試不接受 `--help` 或新 `--date/--games`。晚間另允既有 `--stage boxpa`，只適用明列的故障片段；正常六工作使用 all。

## 2. 執行環境與命令

未核本機只執行本檔，避開根 conftest 的 DB 探測及 xdist 拆庫：

```text
PYTHONPATH=src:. /Users/ruanruan/Dev/cpbl-analytics/.venv/bin/python -m pytest --noconftest -q tests/test_wp6_393.py
```

無 `CPBL_WP6_EXECUTE=1` 時：兩項 pregrant 合成檢查，24 項 runtime 預設 skip；skip 不是 runtime 驗收。不得使用全 repo pytest 或 `-n`。

核發後，由 VPS 已存在的隔離測試環境執行原 pytest；不在 production image 安裝 pytest，也不建立新的測試平台。整合租用固定該 Python 絕對路徑、既有依賴、產品 image ID／來源、測試 commit、UID 與工作目錄。每個節點單獨一份已封輸入及新 target DB，全部仍屬同一整合租用；不可在上一節點寫後動態換基準。命令範本中的大寫位置均須在核發附件替成一個精確值，不能照字面執行：

```text
CPBL_WP6_EXECUTE=1 CPBL_WP6_INPUTS=INPUT_JSON PYTHONPATH=src:.:tests TEST_PYTHON -m pytest --noconftest -x -q --tb=no 'tests/test_wp6_393.py::EXACT_NODE' > PRIVATE_LOG 2>&1
```

DSN 經原受保護環境注入 `CPBL_ISOLATED_TEST_DSN`、`CPBL_WP6_REFERENCE_DSN`，不能放命令列、聊天或交付包。另兩個開關只給各自核定節點：`CPBL_WP6_NATIVE_EXECUTE=1`、`CPBL_WP6_HC_EXECUTE=1`。開關本身不授權任何資源。

每個 case 的 `invoked` 是不可覆寫的一次性標記；失敗不清除、不換目錄重試。遇缺件、超額、未知退出、來源不符、通知缺失，停該項並保存原件，原 PM 決定下一步。不能把未開始項目自動視為授權取消。

CWD 不可有 `.env`；測試入口在私有根建立各 case 的 `app/logs`，原 jobs 仍檢查 owner／0700 與自己的鎖。fixture UID 須與私有根的 owner 相同；此結果不冒 production UID999、request/export/SFTP 權限驗收。真 runtime 節點不得在 Mac 執行後聲稱 VPS 已接手；若指定 VPS 測試環境缺既有依賴，只停該項交具體差異，不自裝。

## 3. 封定輸入格式

`CPBL_WP6_INPUTS` 是 euid 擁有的 0600、絕對且非 symlink、最多 1 MiB 的 JSON。以下是欄位格式，`null`／空陣列是尚未核發的值；`sealed:false` 永遠拒絕執行。核發附件須補齊精確值並 seal，不是任選 scope。

```json
{
  "sealed": false,
  "product_source": "377f795ce1be2c11cc99f1c684fcb21e0763ffa3",
  "lease_id": null,
  "creator_receipt_sha256": null,
  "year": 2026,
  "kinds": ["A", "D", "E", "C"],
  "private_root": null,
  "database": null,
  "database_endpoint": {"host": null, "port": null, "user": null},
  "reference_database": null,
  "reference_endpoint": {"host": null, "port": null, "user": null},
  "limits": {"statement_ms": null, "lock_ms": null, "rows_per_table": null,
             "private_bytes": null, "metadata_table_seconds": null},
  "tables": {},
  "cases": {},
  "artifact": null,
  "prediction_date": null,
  "prediction_keys": [],
  "native": {},
  "healthchecks": {}
}
```

共同格式 `asset = {"path": 絕對私有路徑, "bytes": 精確整數, "sha256": 原檔SHA256}`。所有 asset 必須位於同一授權私有根，非 symlink、bytes/hash 相同。creator 收據須固定 schema／快照來源／截止、target 與 reference 的還原完成與權限、每節點初始化差異、全部資源原生 ID／保留期／quota／釋放者；不含秘密或原列。

- `database` 限 `cpbl393_wp6_` 前綴，明確 host/port/user，不能 port5433；reference 不同庫並由 creator 給唯讀角色。helper 不 CREATE/DROP/migrate，也不補序列。原 products 走 `cpbl.db.conn()`；metadata 另只讀 PG 連線，沿既有測試模式。
- `tables` 必須恰為 `wp6_393_support.TABLES` 固定 45 表，每表 `{"keys":[實際唯一鍵欄名]}`。creator 在授權 PG 以既有 schema／主鍵 metadata 封此投影，不允任意 SQL；複合鍵不能少欄。兩端 schema 必須相同。內容 row/cell 使用 PG `md5(to_jsonb(...))`，外層 ordered JSONL 使用 SHA256；UTC／C collation，不輸出原值。
- `artifact` 是既有可信 `outcome_simple.joblib` 的 asset；不得讀未獲授權 pickle。`prediction_date` 是封定歷史 API consumer 日期；`prediction_keys` 為真 `[season,game_sno]` 清單。只呼叫原 loader 的 `completed_only=True`，不改 DB completed／特徵列或模型輸出。

每個會呼叫原 job 的 `cases[精確參數名]`：

```json
{
  "argv": ["scrape-daily"],
  "expected_exit": 0,
  "environment": {"CPBL_SEASON_CLOSE": "open", "DAILY_FORCE_FULL": "1",
                  "REFRESH_POSTSEASON_KINDS": "E,C"},
  "sample_keys": [],
  "www": [],
  "http": [],
  "state": [],
  "mlb_csv": [],
  "minimum_boundary_calls": {"www": 1},
  "maximum_boundary_calls": {"www": 600, "http": 0, "api": 0, "stats_fault": 0},
  "reasons": {},
  "attribution_evidence_sha256": []
}
```

上例只說格式；`http:0` 是禁該邊界，daily 的真 URL 與預算未封不能執行。原始 expected_exit 只正常案例為0；故障依原介面固定非零，拒絕0/64/75，不能用參數錯誤或busy冒故障注入。其他固定欄位：

| 欄位 | 固定語義與來源 |
|---|---|
| `sample_keys` | 事前真場次 `[{"year":2026,"kind":"A","sno":真正序號}]`；整套涵蓋 A/D/E/C。原 SQL 選場仍執行，再與已封場次取交集；不造 ID、不將全年度衍生重算冒少數場吞吐 |
| `www` | `[{"manifest":asset,"bundle":絕對根,"index":asset}]`；index 必是 bundle/index.json；沿原 verify_bundle/read_response；metadata 連回真 Pi 原生取回收據與 index hash |
| `http` | 每項 asset 外加 `method`、精確 `url`、`status`、捕獲時刻／資料截止／原取源收據 hash；只用真官方 bytes。未收錄請求即失敗，沒有網路 fallback |
| `state` | 每項 asset 外加 `destination`，只能相對 logs 路徑。來源為同 grant 真 history／marker／狀態，檔名與內容一併封定；不可跑後偽造成功狀態 |
| `mlb_csv` | 三項 asset 外加 `year=2023/2024/2025`，只複製到該 case 的 data/mlb/mvYEAR.csv；不讀共享主 checkout、不到 Savant 補抓、不生成假 CSV |
| `daily_date`／`evening_at`／`watchdog_at` | 選用 ISO 日期／含時區時刻，只 patch 該 consumer。沒有全部六工作凍結系統時鐘的要求；日型 gates／jobs Run 時刻仍原流程，狀態必與實際適用週期對齊 |
| `reasons` | `{table:{column:{"why":來源理由,"evidence_sha256":真證據hash}}}`；新增／刪除使用 `__added__`／`__removed__`。hash 必在 `attribution_evidence_sha256`；未知差異立即失敗，不跑後自學期望值 |

`environment` 僅白名單 `DAILY_FORCE_FULL/CPBL_SEASON_CLOSE/REFRESH_POSTSEASON_KINDS/POSTSEASON_YEAR/POSTSEASON_EVENING_KINDS`。closed-paused 不設 force/open，必封原兩個 `.paused-20261028` 檔及原 basename，不把旗標環境變數指到 paused（exists 就會啟用）。enabled 兩情境各在自己的私有 case 放對應 enabled 副本及真到期狀態，原件與正式 state 不改名。

每日鏈原有 pitch_type v1/v2 含 KMeans/QDA 即時計算，沿原 derived 邏輯與真 CSV，不冒成訓練解耦的 outcome trainer；其 CPU／RAM／時間須計入同 grant。兩 trainer 案例禁止另啟 outcome fit/backtest；失敗只在真 loader 選到非空 rows 後、呼叫 walk_forward_backtest 前拋錯。

### 3.1 真場次與來源值的一次晚綁規則

申請前固定規則，核發後在已還原 scratch 的唯一原生事件產值；不要求未授權時先讀私 DB/raw 求 hash。本提案的共同基礎場次上限為 A/D/E/C 各最新一場、合計4場，cutoff 固定為「核發窗口開始的台北日期」與 2026-12-31 之較早日。只取 year2026，以原 daily_chain_completed_games_sql 的官方 final／核准證據判準，不用比分自行猜完賽。以下僅在 grant 內 creator 的既有 psycopg 連線，以 READ ONLY 交易執行；`cutoff` 是已核日期物件：

```python
from psycopg import sql
from cpbl.completion import daily_chain_completed_games_sql
query = sql.SQL("""
WITH chosen AS (
 SELECT g.year,g.kind_code,g.game_sno,g.game_date,
 row_number() OVER (PARTITION BY g.kind_code
   ORDER BY g.game_date DESC,g.game_sno DESC,g.game_season_code DESC) AS rn
 FROM cpbl.games g
 WHERE g.year=%s AND g.kind_code=ANY(%s) AND {completed}
)
SELECT year,kind_code,game_sno,game_date FROM chosen WHERE rn=1 ORDER BY kind_code
""").format(completed=sql.SQL(daily_chain_completed_games_sql("g", "%s::date")))
rows = connection.execute(query, (2026, ["A", "D", "E", "C"], cutoff)).fetchall()
```

產物僅四場身分、日期、所採 cutoff／查詢來源 hash 與完成證據 hash；真清單留私有檔，對外只 count/bytes/hash。缺一 kind 即停相關 consumer，不改查詢、假造資料或默認縮驗收。各 case 的 sample_keys 取此固定四場在其既有業務能力內的交集：週跑僅 A/D；daily/evening 的年度賽程仍原邏輯，observer 只核這批來源更新後的同 PG／history。全年度 season/derived/features 仍會讀寫其原範圍，明列資源成本，不冒僅四列 DB 寫入。

來源清單以該四場加上原工作必需的年賽程／current／官方進階／球隊資料及原狀態機到期先發請求，精確 method/path/form/token-symbol、case 用途與每端上限封進同 grant；只有原 WWW_JOBS 的既有 SourceSession 請求、既有 stats httpx 呼叫，不能自行加 endpoint 或跨年。值（場號、真 bundle ID、index hash、response bytes/hash）由同一授權取源事件填封，網路請求上限不因填值增加。用於 enabled 的真歷史待辦狀態須與原四場中 E/C 及封定 evening_at 對上；若既有真 capture/state 缺該條件，停該 consumer，不能造 pregame rows 或假啟動證據。

case URL/capture 清單及 baseline／歸因來源規則在 consumer 開始前 seal；native after/wait、通知送達等事件的實際 bytes/hash 可在既定私有槽由唯一事件晚綁，原事件種類/CID/image/操作/上限及預期判準先封，不能事後更改期望去配結果。這些是同一整合 grant 的附件，不拆成多張授權。

## 4. 故障操作、晚綁與證據

### 4.1 原來源故障

case 的 `www_fault` 只能 unavailable／expired／corrupt／oversized。corrupt 固定真 bundle 第一個 index entry 的 body、offset0 XOR1；oversized 固定同 body 截長成原 MAX_BODY_BYTES+1，皆只改該 case 私有副本，原件不動。expired 只改副本 window 為過期，實呼原 www_fetch.main；Popen 必不可啟動；再由原 job 接收 ReplayError。

stats case 封 `stats_fault_url` 為 `http` 內唯一真 URL，`stats_fault` 為 403／timeout；只在 httpx 外部邊界回 403 或 ReadTimeout。原工作、parser、真 PG 不替換。這些是傳輸邊界故障驗收，不能冒 Pi 實際斷電、SFTP 停止或 publisher 權限的證據；真供給 F 與原 WP3 原生退出沿同整合 grant 另收，不重跑已過 F2/BOOK3。

真輸入只從原 WP3 manifest/1→bundle/1 入口及既有 stats/httpx 入口取得；每段 www ≤600、≥1秒、白天、每日最多一段。封「來源時點／業務日期／請求方法路徑表單／選場／額度／原生退出與取回兩私有根」後才獲取；當下讀的歷史資料不冒當夜 HTTP 快照。這份測試只消費已收件 asset，不新增 capture CLI、爬蟲或 proxy。

### 4.2 原交易 TERM

`native.transaction-sigterm` 固定 `docker_context/cid/image_id/hostname/client_seconds/signal_wait_seconds/ready_file`；ready_file 必是私有根內相對路徑。唯一 CID 由原生 create 事件晚綁：原 WP5 在同租用隔離網路建立測試容器，固定原 image、同 owner UID、必要 RO source/tests/private mounts、受保護 DSN；PID1 精確 command 為：

```text
python /wp6/tests/wp6_transaction_target.py
```

`PYTHONPATH` 由該既有 image 的 src 位置與 `/wp6/tests` 組成；`CPBL_WP6_INPUTS` 路徑兩端相同。原生 create 的具體 argv 骨架（所有位置值由同 grant 填定；ENV_FILE 為授權 actor 產生的0600短期環境檔，不收其內容）：

```text
docker --context CONTEXT create --name TEST_NAME --hostname HOSTNAME --label cpbl.wp6.lease=LEASE_ID --user UID:GID --network TEST_NETWORK --read-only --mount type=bind,source=TEST_COMMIT_ROOT,target=/wp6,readonly --mount type=bind,source=PRIVATE_ROOT,target=PRIVATE_ROOT --env-file ENV_FILE --env CPBL_WP6_EXECUTE=1 --env CPBL_WP6_INPUTS=INPUT_JSON --env PYTHONPATH=/app/src:/wp6/tests --entrypoint python IMAGE_ID /wp6/tests/wp6_transaction_target.py
docker --context CONTEXT start CID
```

image 原 src 位置若不是 /app/src，原 WP5 在 grant 填其已核原位置；不改 image、source 或依賴來配。原生 create 後、start 前以該 CID seal 輸入，取得對應 input hash，再 start；不拿未生成 CID 永久阻塞，也不能 start 後換內容。target hostname、`cpbl.wp6.lease` label 與 image 必逐一對上 grant。控制端執行上表唯一 TERM 節點；ready 只在真 games SQL 已執行且外層未 commit 後產生，需 backend PID/xid assigned。

控制端只執行以下原生 argv，各一次，使用同 grant 的精確位置值：

```text
docker --context CONTEXT inspect --format '{"Id":{{json .Id}},"Image":{{json .Image}},"Hostname":{{json .Config.Hostname}},"Lease":{{json (index .Config.Labels "cpbl.wp6.lease")}}}' CID
docker --context CONTEXT kill --signal=TERM CID
docker --context CONTEXT wait CID
```

wait stdout 必143，client rc0；工具 timeout 不等於 target 退出。未確知退出不清鎖、不刪 CID、不還原其他 writer。target 不需要 pytest；只用 stdlib/mock 與既有產品依賴。case 另封 `transaction_key`（必在 sample_keys）；creator 採真較早 checkpoint，該場真輸入需有可觀測差異。ready 記交易內該場 count/hash，控制端在另一連線讀已提交 count/hash，兩者必不同；不能用完全相同 UPSERT 冒可觀測 rollback。TERM 後再核整個 games count/hash 完全不變、backend 不在與自己的 refresh.lock；不為製造差異改假比分或假 row。

### 4.3 原 scheduler stop／部署重建

原 WP5 固定同 grant 的隔離 Compose 專案／service／原配置與命令；不得把正式 `prod_cpbl_runtime_jobs_393` 借作測試。原生操作骨架：

```text
docker --context CONTEXT compose -p TEST_PROJECT -f BOUND_COMPOSE stop TEST_SERVICE
docker --context CONTEXT wait OLD_CID
docker --context CONTEXT compose -p TEST_PROJECT -f BOUND_COMPOSE up -d --no-deps --force-recreate TEST_SERVICE
```

兩故障各自獨立場景，不能將已停同一事件當部署中途；recreate 前須有原工作真 running/history 及父子執行範圍，與原生 old CID 綁定。不是由 pytest 執行任意 shell，WP5 依原操作面產生下列收據。`native[fault]` 固定 old_cid/image_id 與三個 asset `before/after/native_wait`。recreate 另封 `active_work` asset，必是原 jobs 真 running record（label/state/exit_code），與同段 old CID／state mount 連回原生收據；不能用空容器重建冒部署中斷。before/after **只取安全 projection，不收完整 inspect 的 Env**：Id/Image/Lease/State.Running；前者 running=true，stop 後同 CID running=false，recreate 後新 CID 同 image running=true；wait 原 stdout 0/143/137，未知退出不通過。

scheduler-stopped 的 case argv 必 schedule-watchdog、expected_exit 非零、watchdog_at 固定在失期週期之後。state 引用同段真 scheduler history／時間戳，不能造失敗證據；逐表比較後封原 `schedule-watchdog/last-run.json` hash。deployment-recreated 用同段真 PG、自己的殘鎖／狀態及原生退出證據；原操作若只有 busy75，單項不通過，不能新增部署器來補。

## 5. 三個真 HC test 事件

三事件必在 VPS 逐項執行上表節點，環境由核發 actor 供既有五 HC 欄位與 `CPBL_ALERT_SLUG_OVERRIDE=test`，值不入聊天／命令列。`healthchecks` 只含非秘密：`check_uuid/allowed_hosts/schedule/tz/grace/max_polls/poll_seconds/notification_seconds/notification_bindings`；允許主機精確列出既有 API/ping/update host，不新開 check。test UUID 先由同 grant 原生查詢晚綁，helper 每次讀回核對 UUID。

每事件原既有 `_request`／arm_schedule／ping：先 GET 原 schedule/tz/grace/timeout 私存；arm 暫時 schedule；送 fail、start 或 success 後不再 ping，有限 poll 等 down；finally 原 update_url POST 回四欄、GET核一致及 success reset。原 helper 各 request 最多3次成熟重試，非新重跑。每事件最壞 HTTP attempts 為 `3*(max_polls+7)`，API/ping 的原 timeout 及 backoff 亦須計入同 grant；silent/interrupted 的 schedule/grace 與總窗必足夠，不靠延窗。

通知是獨立外部證據，不能拿 API down 冒送達。通知 owner 在同 grant 指定路徑一次發布 ≤4096B 的 binding：

```json
{"lease_id":"已核ID","event":"failed","rid":"既有alert_ping.run_id(lease_id + : + event)",
 "check_uuid":"已綁test UUID","delivered":true,
 "artifact":{"path":"授權私有通知證據","bytes":0,"sha256":"真hash"}}
```

`notification_bindings` 對 failed/interrupted/silent 各綁一個私有絕對路徑；初始可未生成，通知等待有界，由當次真送達事件填，不能放舊通知。helper 還原後等候通知證據至 notification_seconds；缺失只算該事件未通過。原四欄快照與 mutation.invoked 先落盤；任何恢復失敗都保留交原 PM，不以第二次完整事件重試修飾。真 Mac alert-watch bootout 與 VPS自然排程證據仍由 WP5/WP7 於同 grant 承接，本 helper 不冒已完成。

## 6. 一次整合租用必封的上限、回復及交付

- 統一窗口、每節點一次、source/http/api 最大次數（maximum_boundary_calls），六 job／故障／兩 trainer／三 HC／四控制的執行次序；24 節點各自 target/reference 初始化與封定期望。既有成功片段只引用，不再實跑。
- metadata 各表 statement_ms/lock_ms/rows_per_table/metadata_table_seconds 是正整數；每次比較最多 90 個 server cursor（45表×2端），TERM另兩次 games及backend確認。row/cell metadata仍是敏感資料面，私有保存、總額同包列，不稱零資料存取。
- private_bytes 限單 asset／單次複製／單 case 差異輸出；**不是整卷總額**。creator 另以同 grant 原生 volume quota／觀測固定全部輸入、45表差異、MLB複本、模型RO、logs及native證據的總 bytes/RAM/tmp上限；不可把 1MiB 輸入限制當全資料上限。超額首停、不加新容量研究。
- case 全程最大時長、PG資源、API進程、image/UID/私有mount、真文件複本權與到期清理，一次封定；source3000秒只限I/O，不冒全daily硬timeout。既有 Pi/VPS 停止與資源保留額度、Mac10:10衝突及120分鐘同CID pause由原WP5同包處理，不在此增新controller。
- scratch 是新且獨立資源。失敗只保留自己的狀態與收據，原生 wait 確認、PG無活動、HC已恢復後，由原creator依grant精確drop/rm與釋放；不碰shared/prod、不從備份回復正式、不清他人鎖、不啟正式writer、不自恢復Mac造成雙writer。
- 對外只契約結果、rc、筆數、bytes與hash。pytest全log、真API回應（同grant另存私有、只對外hash）、row/key/cell原始資料、HC快照都留私有根；差異檔只含key SHA／row/cell hash、欄名與已封來源理由。交付包不含這些真資料或秘密。
- 尚待同一整合grant的是真輸入收集、creator/PG/API/model、原生故障、真HC通知與清理。此次只完成可執行測試／操作材料與安全合成自查；不得填原WP6演練完成或停Mac就緒。
