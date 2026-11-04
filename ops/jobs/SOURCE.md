# #393 VPS逐批請求／相符新包供給候選

此為774之後的獨立候選；621六入口及774訊號錯誤修正的審核不含本增量。
不新增daemon、排程器、HTTP層、傳輸工具或manifest/bundle schema。尚未部署或核發新權限。

## 觸發與工作對應

沿 `python /app/jobs/jobs.py <job>` 原入口及 `_browser.session()` 後端，呼叫者的原日型、收官、先發／A場gate與場次選取均保留。
只在scrape-daily、postseason-evening、weekly-box-revisions實際呼叫WWW葉函式時產生請求，不為quiet或已略過步驟預抓；
weekly-game-pitches、schedule-watchdog、alert-watch不因此增加WWW。既有stats client不改。
每個job程序有全新隨機id，批次manifest_id為 `<job>-<20hex>-<四位遞增批號>`，每批獨立不可重用；沒有current指標schema。

page呼叫沿原path/wait/require產1操作。post呼叫核對caller已取得頁面的token，只把固定名稱`{$token:...}`寫manifest，
同批以page＋post的2操作讓Pi按新頁解析token；回原HTTP status/text予原parser，不整形原文。
因此每個post比原長存session多取一頁，全部計入下列總額度，不能沿舊單一HTTP成本申租。
支援原A/B與WP3 .2四個原function錨點；原token literal只在記憶體，不寫清單、狀態或stdout。

## 三處根目錄及精確檔案

| 用途 | 容器路徑／設定 | 寫讀者與必要權限 |
|---|---|---|
| 獨立原件 | `/app/logs/source/<manifest_id>/manifest.json` | 原job一次建立，目錄0700／檔0600；隸屬既有state root，與export/inbox互不嵌套 |
| 只讀請求出口 | `CPBL_JOBS_REQUESTS_ROOT=/requests`，`<job>.json` | VPS job寫臨時檔後atomic replace，bytes與原件完全相同；根owned job UID＋request-ro群組、setgid2750，檔0640；Pi獨立ro身分只讀此根 |
| 既有收件 | `CPBL_JOBS_INBOX_ROOT=/inbox`，`incoming/<manifest_id>/` | 原receiver仍只寫incoming；VPS job需能讀同一私有目錄；實際UID/GID、mount與host映射由WP5/後續整體核發綁定 |

export固定三名：`scrape-daily.json`、`postseason-evening.json`、`weekly-box-revisions.json`。
它們的內容就是原manifest/1 bytes，沒有包裝或另外的current指標檔。Pi取件／不重取同id由原WP3負責。
VPS只等自己本批id的收件，不掃latest／mtime、不選其他job或前輪。
前批驗完／回放後，只有原業務提出下個實際需求才發布新批；等待下批期間出口仍指向已處理的同id，Pi需去重，不得重取。
job收尾仍持writer鎖時，核最後export檔inode/hash後只撤自己的出口；私有原件／bundle不刪。
Pi在已見本job隨機prefix後看到出口不存在可結束本job等候；看到不同prefix不得接管成同一run。
突然中止可能留到期出口；Pi不得因看見它就重取或延窗，已開始的遠端工作也不能由出口撤回推定已停止。
root必須為已存在絕對非symlink實路徑；private state、export、inbox彼此獨立。缺設定／權限／租用不可冒稱ready。
新request-ro帳號／key／群組／根及唯讀SFTP方向仍未授，不在本增量建立或測試。

## 額度與失敗

`CPBL_JOBS_SOURCE_MAX_OPERATIONS` 必須明確注入1..600，對一個job累計所有page＋post；不是每批重置。
每批1或2操作，批次數最多等於該job操作上限；每批max_requests就是該批操作數。
`CPBL_JOBS_SOURCE_MAX_SECONDS` 必須明確注入有限且>10的秒數，從首次WWW需求算共同截止，含發布／等Pi／等收條／驗包；沒有預設額度。
每批沿既有max_duration_s，最多300秒且不超過剩餘總窗減10秒；原min_gap_s=1只約束同批清單呼叫起點，不冒稱全部HTTP或跨run間距保證。
原每body≤8MiB／每bundle≤256MiB與index≤1MiB不放寬；此後端每批至多2 body，整job原文總量理論上≤操作上限×8MiB，另計index/manifest/receipt/log。
新增的page成本、每批raw SFTP、再1次metadata SFTP及檔案，須全部列後續正式額度；上述上限不證明完整daily實際可在其中完成。
第一個配置／供給／收條／驗包錯誤就記該job source失敗，後續呼叫不重發布／不重取；即使原葉函式吞例外，上層job仍非0。
未取得收條會等到共同截止後失敗，沒有舊包fallback、延窗、重試或自動刪除。已提交的前面業務步驟不冒稱被回滾。
job退出不代控制或證明Pi/SFTP程序已退出；其退出／失敗清理及剩餘私有資料由原owner在同次核發下收尾，不能用job lock釋放推定遠端停止。

## 完成metadata候選及消費次序

原WP3在raw batch native wait完成且rc0後，再同一既有sender發起一次metadata SFTP，
先寫 `incoming/<manifest_id>/.delivery.json.upload`，最後rename成 `delivery.json`，大小≤4096 bytes。
內容只允許五欄，沒有改bundle/index schema：

```json
{"manifest_id":"本批原id","manifest_sha256":"本批原bytes SHA256","index_sha256":"最終index bytes SHA256","raw_batch_rc":0,"raw_batch_waited":true}
```

VPS核精確id／原bytes hash、真int rc0／true waited、index hash後，呼叫原ReplaySession→verify_bundle整包gate；
只接受complete=true、stopped=null、close_returned=true及每筆bytes/hash等原不變條件，驗後再核index未改，讀原文時仍逐筆重驗。
收條不是身份簽章或server強制immutable證據；信任被授權的原sender不在發布後改raw，hash只驗完整性。
此方案把「raw已停寫且metadata收條已原子發布」作消費點；metadata連線可能還未完全退出，
**與舊『所有傳輸程序退出才消費』的逐字要求有差異**。尚待本人在後續同次完整核發採認，不冒稱已生效；候選與實網明確分開。
server目前只write/incoming，沒有requests讀向、完成驗收或immutable保證；這些未知不能靠index存在或本機fixture補成正式收據。

## 多批節奏的有界候選（非已核額度）

VPS一個job仍持既有refresh.lock，原業務呼叫逐批推進；Pi需沿原CLI加有界串行服務／timer，不能要求人工逐批重叫。
Pi全三job共用一個WWW執行互斥；同prefix的id只取一次，raw或metadata失敗後不重送，依原15–20分鐘跨run冷卻紀律處理。
WP3的串行服務／去重／冷卻與native退出收據為它的ownership，本文件不代其創建服務或宣稱它已實作。
建議作完整核發起點的VPS上限：daily 600操作／3000秒（原daily 10:10至11:00 grace），evening 600操作／240秒（原300秒喚醒間隔內的供給預算），weekly-box 600操作／3600秒（候選操作預算，非實測時長）。
數值尚未採認或實證足夠完成全年每日；由consumer按job明確注入同兩個設定，不默認啟用。Pi有效讀取窗口需覆蓋實際首次發布至共同期限，不能拿cron起點冒首次WWW時刻。
建議Pi有待處理工作時最多每5秒讀一次、重複id不取源，並受同job窗口與明確read次數上限約束；單一job若一次只讀其出口，保守read上限為操作上限＋ceil(總秒數/5)＋2，包含空等／重複／缺檔讀，raw和metadata SFTP另各≤批次數。
若Pi實作每輪掃3個job，上述read輪詢上限必須再乘3，不能以每成功batch read1替代；各job窗口重疊仍共用單一串行worker、不開多個冷啟動。
具體timer讀向與冷卻後不重送的共同契約由原WP3固定後一起審核；沒有無限輪詢或無界重試授權。

## 相容固定依賴與驗證限制

原樣採用WP3 commit `2ba17326da2c9e9263c1a410124d832b10e5cc04` 的www_fetch.py，25819B／
SHA256 `f711488057028133b2d168e7e596b1fb7ca20ad30d2fbd90866714964667d4f9`，VERSION393-wp3-original.2；
僅3已知HTML API（含單數 `/player/trans`）及4具名function token相容，其他JSON gate、A/B及原ReplaySession不改。
供給候選不自行重寫這個WP3檔，不把依賴採入當它已獨立審核或部署。
本機只用fixture sender/收條及mock Linux setgid metadata，實際Linux mount/群組權限／SFTP／官網／DB／時窗／量額未驗。
手動模式可明確指定原CPBL_REPLAY_MANIFEST/BUNDLE供固定回放；scheduled trigger=jobs只要走WWW就拒用這組固定包環境，必須走新供給。
