# #393 六工作 Linux producer 介面

入口固定為 `python /app/jobs/jobs.py <job> [args]`，工作目錄 `/app`、原映像 `app` UID。
CPBL Dockerfile 僅加入 jobs.py、refresh_status、schedule_watch、alert_watch、alert_ping 與 registry
六個必要檔案到 `/app/jobs`；候選尚未構建／部署，不以現有映像宣稱已包含本介面。
API 的預設 CMD／healthcheck 保留；WP5 的 S1 supercronic 服務自行配置其前景啟動與 healthcheck。

| job | 額外 argv | 既有內容／解除的 Mac 依賴 |
|---|---|---|
| scrape-daily | 可選 `--fast` | 原日型→recent/衍生→team comparison→features→prod-sync 標記；移除 uv、容器前置與跨機同步 |
| postseason-evening | 可選 `--stage all` 或 `--stage boxpa` | 原晚間／先發／boxpa 狀態機；同 DB 直寫及原 reconcile，不備份／跨機同步／bootout |
| weekly-box-revisions | 可選 `--year`、`--days-back` | 原近窗選場及 gamelog/box writer；A/D 分開，收官略過，不 migrate／查本機 Docker |
| weekly-game-pitches | 可選 `--year` | 原全季選場及 stats writer；A/D 分開，部分失敗非零，不 migrate／查本機 Docker |
| schedule-watchdog | 無 | 原 registry cadence/週期判定讀 jobs history；不查 plist、launchd、開機／桌面通知 |
| alert-watch | 無 | 原 services 兩次確認及 evening 武裝／成功／halted；Linux 唯讀 PG/Redis/API，不查 pmset/Docker |

舊 shell 入口的 `--jobs` 已轉交前五個對應 job，僅來源環境需要，映像不封裝這五支 shell。
`alert_watch.py` 的舊 CLI 保留；Linux 使用上表入口。所有未選 Linux 模式的 Mac 路徑維持原預設。

## 注入與狀態

- `CPBL_JOBS_STATE_DIR` 必須對應 `/app/logs`；以私有持久 volume 提供，同 `app` UID、目錄0700，檔案0600。
  沿原相對 logs/data 口徑，不把 cwd 換成 state 目錄。`/app/.env` 不得存在。
- `REFRESH_TRIGGER`：supercronic 明確設 `jobs`；預設 `manual` 不冒充排程成功。
- 四 writer 需明確受保護 `DATABASE_URL`、相容 schema/資料與實際排他，CLI 不 migrate。
  `PGAPPNAME` 預設 cpbl-jobs，DSN 不得另覆成不同身份；仍須現場收據確認，不由 env 宣稱單 writer。
- WWW 只讀既有 `CPBL_REPLAY_MANIFEST`／`CPBL_REPLAY_BUNDLE` 私有唯讀收件包。
  jobs 模式缺包即失敗，不啟 Chromium 或直打 www；stats 沿既有 client。
- 觀測者需 `CPBL_JOBS_API_URL`，alert-watch 另需受保護 `REDIS_URL`／DB 連線；只讀健康，不控制服務。
- healthchecks 直接從受保護環境讀既有 `CPBL_HC_PING_KEY`、`CPBL_HC_API_KEY`、各 BASE/TIMEOUT 名稱；
  不回頭讀 Mac `.env`。`CPBL_ALERT_SLUG_OVERRIDE` 保留既有 test-check 用途，沒有新增 check。
- 四 check 映射：daily 由 scheduled scrape-daily start/exit 送；evening 由 alert-watch 沿原夜間判準；
  services 由 alert-watch 沿兩次連續觀測，並納入 watchdog 持久異常；test 僅沿既有 override。
  services 健康成功沿原 `OK_REFRESH=60 分鐘` 或故障恢復發送，並非每五分鐘成功 ping；
  consumer 不得以五分鐘觀測頻率當作 SaaS 成功 ping 的沉默門檻。
  SaaS 端 schedule/grace/沉默告警與切換前 test-check 仍須依後續核發實核，本候選未真 ping。
- #391 沿原 closed_leagues／DAILY_CLOSED_LEAGUES 與 CPBL_SEASON_CLOSE 控制。
  #375 原 POSTSEASON_STARTER_FLAG／POSTSEASON_STARTER_WATCH_FLAG／ALERT 路徑預設在 state logs，
  不建立 enabled，不改 paused-20261028 檔案；遷移旗標由核定 actor 保留原態。
- 既有每日球種分類內嵌 fit 依6632113188原算法保留（實碼為 QDA/KMeans，非 Random Forest）；
  `src/cpbl/models/pitch_type_v2.py` 的 `MLB_YEARS=(2023,2024,2025)` 與 `MLB_DIR=data/mlb`
  要求三份 `mv2023.csv`、`mv2024.csv`、`mv2025.csv`，cwd `/app` 下讀 `/app/data/mlb/<檔名>`。
  consumer 可把 `/srv/cpbl393-reference/mlb` 唯讀掛至 `/app/data/mlb`；本候選不含這些 CSV。
  原依賴 numpy／scikit-learn 及其 scipy 相依沿既有鎖定環境，沒有新增套件、下載或 fit。
  資料可用性與現場資源前置尚未實驗，不能以檔數或 hash 推定內容適用。
  成績／賽果重訓及回測不進此入口，推論仍由既有 API/其模型工件消費新特徵。

## 鎖與收尾

四 writer 共用 `/app/logs/locks/refresh.lock`，atomic mkdir，真實持續存活 Python PID 寫 pid/kind。
watchdog／alert-watch 各用同 locks 根下的具名鎖。busy=75、不刪外來／舊 namespace 鎖；
持有者收尾驗 inode/pid/kind，關池後才移除 own lock。協作中斷記失敗；SIGKILL/未知殘鎖須先核實舊程序退出再由核定 actor 回復。
部署 consumer 可對同 refresh.lock atomic mkdir 建空目錄 claim；worker 同樣視為 busy，不填 pid/kind或刪該空鎖。
部署端需自行核 own inode/空目錄才 rmdir，不能移除 job 鎖；overlay、空 cron、停止宣告都不代替此鎖。

history 沿原 schema1、label及 logs/schedule-history 路徑，trigger=jobs；scheduled 狀態在
logs/jobs/<job>.json，manual 另檔。週跑同時保留原 last-weekly* 供 J3/J4，晚間原業務 state/status 另保留。
stdout 僅 job/mode/exit/state；完整業務輸出留私有 log。部分失敗／對帳不等不宣稱全部完成或回滾先前提交。

本機候選及 mock 自查不代替 VPS 實跑、DB/資料契約、四 check 故障注入、S1 實際排程或 WP7 停 Mac 驗收。
FIRSTWRITE2/BOOK3/既有推論部署收據沿原固定版，不在此重驗；新部署／共享操作仍另核。
