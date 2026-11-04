# WP3：沿原爬蟲的私有原文代取器

Pi只依VPS清單代取www，產出原文與索引；直送候選見下方。解析、DB、計算、發布、接收端部署及正式排程由其他工作包承接。
目前版本不含舊guard／CDP／Worker限制／API代送，亦不修改`src/cpbl/ingest/_browser.py`。

## 來源與執行

`OriginalSessionDriver`直接呼叫成熟`session.page_html()`與`session.post()`；沿用原browser/context設定、
當下`fetch`、自然轉址及原helper內部的恢復行為，不提前捕獲JS或重寫原型。
外層不重跑清單／失敗操作。原PLAN的首次診斷「不重試／全HTTP≤50」不能冒稱這個成熟helper無內部重載；
下一次實網核發須明列這個口徑，不因候選可用就自行起跑。

純取源模式只需以下三檔及**已裝**Python／Playwright／Chromium；直送／有界服務另加下方sender及systemd候選。
Pi不必安裝cpbl或DB/ML相依：

```text
ops/pi-fetcher/cpbl_pi_fetch.py
src/cpbl/ingest/www_fetch.py
src/cpbl/ingest/_browser.py
```

子程序只帶瀏覽器必要的標準環境與`CPBL_SCRAPE_CHANNEL/HEADED/UA`，不帶DB/告警/cloud憑證或DEBUG/trace。
Pi拒用`CPBL_SCRAPE_PROFILE`，不得搬Mac個人profile/Cookie。用既有`PLAYWRIGHT_BROWSERS_PATH`；缺件停，不自動下載／安裝。

```bash
# 零網路驗清單；不建立out、不載入Playwright
/existing/venv/bin/python -I -B ops/pi-fetcher/cpbl_pi_fetch.py manifest.json --out /private/job-out --check
# 只有新核發明確涵蓋取源及敏感原文落檔後，才可省略--check執行
# 驗既有bundle（零網路，只讀本機）
/existing/venv/bin/python -I -B ops/pi-fetcher/cpbl_pi_fetch.py manifest.json --out /private/job-out --verify
```

## 既定契約：manifest/1 → bundle/1

清單仍是`cpbl-www-manifest/1`，不另建協議；以下時窗只是尚未生效的範例：

```json
{
  "schema": "cpbl-www-manifest/1", "manifest_id": "example-2026-A",
  "window": {"start": "2099-01-01T12:00:00+08:00", "end": "2099-01-01T13:00:00+08:00"},
  "min_gap_s": 1.0, "max_requests": 2, "max_duration_s": 165,
  "requests": [
    {"id": "p1", "op": "page", "path": "/schedule", "wait": "networkidle", "require": "RequestVerificationToken"},
    {"id": "q1", "op": "post", "page": "p1", "api": "/schedule/getgamedatas",
     "form": {"calendar": "2026/01/01", "location": "", "kindCode": "A"},
     "headers": {"RequestVerificationToken": {"$token": "A"}}}
  ]
}
```

- `page`取原session的HTML文字；`post.page`必須指向最近一個page操作。
- form/header的`{"$token":"A"}`為原inline token，`B`為hidden input；抽取值只在記憶體。
  清單不得帶literal token、Cookie、Authorization或秘密query；只接受www相對路徑及公開參數。
- `393-wp3-original.2` 沿同一形狀新增 `getSelectOpts`、`getFightingScore`、`getFighterScore`、
  `getApartScore` 四個 token 名稱；各自只在原函式錨點起 1600 字元內找 inline token，
  對齊既有 fighting／person／apart 的 `_token_in`。缺錨點或 token 就停，不退回第一個 A。
  舊 `.1` 不認得這些名稱；producer 與 Pi／VPS 必須綁同一相容版，不只核 schema 字串。
- `max_requests`保留舊欄位名，現在明確代表**清單操作開始數**（上限600），不是實際HTTP上限；
  `min_gap_s≥1`亦僅限制兩個清單呼叫起點。原helper重試／附屬活動不是新的清單操作。
- `max_duration_s`為可選工作上限，預設300秒；CLI以標準子程序逾時保護，TERM後5秒、必要KILL再wait5秒。
  可用時間再受window結尾減10秒退出餘裕限制；窗外拒跑、不等待、不另換窗。
- parent把已驗證清單的**同一份bytes**送進worker，避免重讀可變路徑；index綁原bytes的SHA256，不重新序列化冒稱同一份。

輸出為`<out>/<manifest_id>/index.json`（`cpbl-www-bundle/1`）及`responses/<id>.body`。
bundle／responses目錄0700，原文／index檔0600；既有manifest_id一律拒跑、不覆寫、不刪失敗檔。
原文是**既有session返回字串的UTF-8 bytes**，逐字保存、不重排JSON／redact；不是壓縮HTTP wire bytes或headers。
HTML原有內嵌token仍屬敏感原文，只存私有bundle，禁止進Git、對話、卡片或其他未核目的地。
不額外存token值、Cookie jar、session storage或headers；index/log只有公開清單路徑、狀態、bytes/hash及安全摘要。

index每列以`id/op/path或api`對應原清單，含`http_status/ms/body/bytes/sha256`；
`manifest_sha256`綁原清單。page的HTTPstatus在快取／context恢復後可能不可見，記null、不補200；
page HTML是否取得沿原helper返回／require判定。post status沿原helper返回值；預設200且JSON可解析才保存。
`.2` 僅對原 HTML consumer 的 `/standings/seasonaction`、`/team/teamscoreaction`、`/player/trans`
保留 HTTP200 的原始文字，不先 JSON 解碼；沒有把其他 POST 放寬成任意文字，也不新增 body 格式欄位。
HTTP200／保存原文不是業務成功判定，原 HTML parser 仍由 VPS 承接；原成熟 browser 的恢復與挑戰處置不變。
`complete=true`僅表示全部清單原文取得並已呼叫close返回，**不是**GameDatas業務驗收或全部程序退出證據。

`observed`只含SDK可見request／response／redirect／page WS與觀測到的context更換計數；
listener掛上前、失敗／換context中的活動與Worker深層可能不可見。這是可見活動下界，不是完整線路流量；
中間自然轉址不驅動新阻擋層。body≤8MiB／bundle原文≤256MiB是落檔與讀取上限，不能冒稱下載送前上限。

操作失敗／逾時保留既有原文前綴及`complete=false` index；index原子發布，進行中亦不得當完整bundle。
原`_Session.close()`吞例外，`close_returned`只代表方法返回；CLI記子程序已wait，深層PID仍須操作收據如實說明。

## WP4直接消費

VPS保留自己產生的原清單bytes，不用Pi提供的新清單替換它；預設拒收partial、錯清單hash、缺檔、過大、損毀或symlink。
先驗整包，回放時逐筆讀取，最多保留當筆原文，不一次載入256MiB整包：

```python
from cpbl.ingest.www_fetch import verify_bundle, read_response

index = verify_bundle(private_bundle_path, original_manifest_bytes)
for entry in index["entries"]:
    text = read_response(private_bundle_path, entry).decode("utf-8")
    # WP4將text及post的http_status交回既有parser；不log text。
```

`verify_bundle`返回安全index；`read_response`每次重驗當筆bytes/hash，減少驗後再讀的變動風險。
這裡沒有實作WP4回放session／writer；直送由下方獨立入口執行，不因取源成功自動觸發。hash驗完整性，不是發布者身分驗證；受控inbox交接仍依原PLAN。

### 同一入口取新原文後直送

既有 `cpbl_pi_send.py` 新增 `--fetch`，直接呼叫上面的成熟取源入口，成功後才執行原 sender。
這個本機清單模式不下載清單或輪詢，也不啟動 VPS parser／writer；省略 `--fetch` 的既有直送行為不變。
以下只是候選呼叫，`manifest.json` 必須是 VPS 產生並受控交付的本輪原始 bytes，不是手填或舊包替代：

```bash
/existing/venv/bin/python -I -B ops/pi-fetcher/cpbl_pi_send.py /private/manifest.json \
  --bundle /private/job-out/the-original-manifest-id --fetch --timeout 120
```

- `--bundle` 的最後一節必須等於原清單 `manifest_id`，父目錄交原取源入口的 `--out`。
  原取源器的時窗、同 run 拒覆寫、恢復與 worker wait 原樣沿用，不重試外層工作。
- 取源失敗、逾時或既有 run 拒收時一律不呼叫 sender；即使磁碟上有同名完整舊包，也不 fallback。
  原清單在取源後改變時，sender 原有 `manifest_sha256` gate 會拒送。
- 安全結果新增 `fetch_rc`；`child_waited`／`sftp_rc` 仍只指 sender 的原生 SFTP。
  `--timeout` 仍是 SFTP 工作預算；取源預算與退出餘裕沿 manifest，部署核發須涵蓋兩段總長。
  bundle 的 `complete=true` 代表原文完成，sender 的 `transfer_complete` 代表 batch 完成，兩者均非 VPS 入庫成功。

### 新請求讀取與完成收條候選（未部署）

既有 `cpbl393-sftp-drop/v1-candidate.1` receiver 是上傳接口：`sshd-receiver.conf.in` 的
allowlist 沒有 `read`／`readdir`，獨立原 manifest 在 chroot 外，亦沒有已核的 `/requests` 讀取路徑。
不能把 sender 的上傳能力當成 Pi 已能自動取得清單，也不能借 root／備份 reader 身分完成它。
原 receiver 設定及其封版 hash 未改；下面只新增同一 sender 入口的離線候選能力，沒有授予現場讀權。

```bash
# 候選：out 必須事先是執行者擁有的0700目錄；不建立服務或自主輪詢。
/existing/venv/bin/python -I -B ops/pi-fetcher/cpbl_pi_send.py \
  --request-job scrape-daily --out /home/ruan/cpbl-fetcher/www-supply --timeout 120
```

`--request-job` 只接受 `scrape-daily`、`postseason-evening`、`weekly-box-revisions`，
其餘三工作不新增 WWW 請求。此模式不帶本機 manifest／bundle 或 `--fetch`：
一次取得原清單後自行沿其 ID 決定新 bundle，接原取源器、原直送及完成收條，不需手填 `CPBL_REPLAY_*`。

| 資料 | 固定共同候選接口 |
|---|---|
| VPS 原件 | WP4 於 `/app/logs/source/<manifest_id>/manifest.json` 獨立保存原 bytes，0700／0600；ID 為 `<job>-<本job隨機id>-<批次>`，總長沿64字元限制 |
| 供 Pi 取件 | 相同 bytes 原子發布成容器 `/requests/<job>.json`；是原 manifest 本身，沒有新 `current.json` 指標／schema |
| Pi 本機原件 | 一次原生 SFTP GET 到 `<out>/.requests/<job>-<隨機檔名>.json`，排他暫存0600／目錄0700；保留原 bytes/hash，拒絕非本 job 前綴的 ID |
| 新原文 | 原 `<out>/<manifest_id>/index.json` 及 `responses/*`，仍是 bundle/1；取源失敗、過期或同 run 已存在即停，不用前輪包 |
| VPS 收件 | SFTP `/incoming/<manifest_id>`，消費容器 `/inbox/incoming/<manifest_id>`；index 仍最後原子發布，原清單不由 Pi 上傳替換 |
| 完成收條 | 原文 batch 真正 native wait／rc0 後，第二個上傳 client 只 put 暫名 `.delivery.json.upload`，rename 為 `delivery.json` |

收條只有五欄：`manifest_id`、`manifest_sha256`、`index_sha256`、`raw_batch_rc`（int 0）、
`raw_batch_waited`（true）。它是可信 sender 的原文停寫證據，不是 server 的獨立驗收收據。
VPS 只對自己當批 ID／canonical 原 bytes/hash／期限採認收條，再核 index hash 及原
`verify_bundle`／`read_response`；不掃 latest、不以 index 出現當完成、不回前輪或 `.upload`。
發送端也在原文上傳前綁定本次 GET 的 manifest hash；同名檔案被更換時拒送。

**必須集中採認的差異**：收條發布後，metadata SFTP 可能仍未退出或其最後 ACK 遺失；
此時原文傳輸已經真 wait0、之後不再寫原文，VPS 可以按上述 gate 消費。
這與舊「同 run 的所有傳輸／消費不並行」字面不同，不能說完全原樣。
metadata 失敗／未知時 Pi 不重試、不回滾、不刪原文；沒有有效收條的包不得被新 consumer 挑選。
現有 SFTP 帳號仍非 server-enforced immutable；hash 與這份收條不能取代可信 sender／VPS 獨立驗包。

只採單一隔離讀向提案：新 `cpbl393-request-ro` 身分、獨立 Pi key 引用
`/home/ruan/.ssh/cpbl393_request_ed25519`（Python只stat），沿既有 VPS host pin 與公開 known_hosts。
host chroot root 候選 `/srv/cpbl393-request-ro` 必須 root:root／0755；其 `requests` export
由 producer UID999＋新 request-ro 群組／setgid2750 管理，公開原 manifest 檔0640，reader UID不同於999、
僅該新群組可讀。reader 強制 `internal-sftp -R -d /requests`、key-only、禁止 shell／TTY／forward，
僅必要讀取 request allowlist；不掛載 incoming，不放寬原上傳 receiver 讀權。
精確 UID／GID、host root／container mount、帳號可用性、sshd Include／版本相容均未在現場核實；
新身分、key、root、群組、公開檔權限與載入流程，須與兩端部署／一次驗證在同份核發中明採，
不能把這些提案當已部署或沿用備份 key。

每次入口最多三個串行 SFTP client：request GET一個；原文 batch一個；收條 put＋rename一個。
`--timeout` 是各 client 的工作秒數，各自另沿既有最多10秒 TERM／KILL wait；取源仍受原 manifest
時窗、`max_duration_s` 與10秒退出餘裕控制。1MiB是原 manifest 的落檔後解析上限，不是 GET 前的 wire 硬上限；
producer 發布前也須限量。`.requests` 與失敗暫存均保留，沒有新增刪除／輪替權。

WP4 post批包含page＋post，與原 manifest「post參照最近page」相容，但會增加page原文、冷context與時間成本。
`--request-job` 只處理一批；以下有界服務模式負責重入。兩者均不以舊 DIRECT／F2 固定包或舊HTTP額度假證新供給。

### 同入口有界服務與 private state

`SUPPLY_VERSION=393-pi-auto-source.1-candidate`；依賴固定 WP4 producer `8081536d` 的 `ops/jobs/SOURCE.md`。
原文／index仍是manifest/1與bundle/1，完成收條仍只上列五欄；沒有新增done／current協議。

```bash
/existing/venv/bin/python -I -B ops/pi-fetcher/cpbl_pi_send.py \
  --serve-job scrape-daily --out /home/ruan/cpbl-fetcher/www-supply --timeout 120 \
  --discovery-seconds 3000 --max-seconds 6000 --max-reads 1202 --max-operations 600
```

- 首批尚未看見時每30秒最多讀一次；看見本job的20hex隨機prefix後，每5秒最多再讀一次。
  這是明確的discovery等待，不把timer起點當作首次WWW。只接原prefix，遇不同prefix就退出，不接管新run。
  同prefix後續批次的截止只會縮短，不以新manifest重置；總wall budget／read次數也不重置。
- 全三job在每次讀取→取源→raw→receipt期間共用 `<out>/.worker.lock` 的非阻塞 `fcntl.flock`；
  空等時釋放，所以quiet daily不會佔住整個等待窗口。busy沒有發出SFTP／WWW。
- `<out>/.attempts/<prefix>/<四位批號>` 是0600排他claim，兩行僅原manifest SHA和1／2操作預留數；
  新worker也會計入同prefix既有預留，不重置600上限、不再取／重送已嘗試批次。claim不代表成功。
  失敗、逾時及崩潰留下的claim均保留；不resume、不換ID繞過。
- 已呼叫原取源器後失敗，寫全job共用 `.cooldown-until`，20分鐘內其他job也不開讀取或WWW；
  冷卻後仍不重試該批。`.last-source-end` 使下一worker在前次取源返回後至少再等1秒。
  這只約束串行worker，不能冒稱全部附屬HTTP／自然轉址／原helper恢復均有1秒送前硬限制。
- 已啟原生client但沒有wait證據，留下 `.blocked`，後續三job全停，沒有自動解鎖或到期。
  私有狀態不包含token／form／raw；刪除、清理或人工恢復權不由程式新增。
- 原生GET非0不能區分出口已撤回、認證或傳輸故障。首prefix前只按有界discovery輪詢並計數；
  見prefix後則退出為`request_unavailable`，不冒稱missing、job完成或取消已起工作。
  malformed／錯job／hash變動／退出未知不啟WWW；raw或metadata失敗後不自動重送。
- 每次poll都輸出安全rc／實際client-start／wait；最後摘要包含poll次數、三種client數、當prefix預留操作與已交batch數。
  `operations_reserved` 是上界預留，不是實際HTTP量；unknown保留null。
  rc75表示有界worker已停止／本次無新資料，不代表VPS驗收或業務成功；VPS自己的receipt＋verify gate仍唯一決定能否回放。
  只有不同prefix會回rc76，讓systemd在舊worker退出後開全新的worker接棒；舊worker本身不接新run。

`systemd/` 七檔是未安裝的最小候選：一個template oneshot service、三個timer、三個數字設定。
它們直接啟動既有入口，不加shell wrapper或另一排程器。User=ruan／UMask0077；各job共用同一out root；
Restart=no，只有RestartForceExitStatus=76允許換輪接棒，1秒後重啟；每300秒最多啟動2次，
一般失敗／冷卻／blocked不自動重啟、不重送失敗批。這避免舊worker碰到新prefix退出時漏過剛才已略過的timer喚醒。
不補跑錯過時刻，停止時由原service cgroup收尾；程式本身有界，不用另一timeout控制器。
退出狀態與限次語義依[systemd.service](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.service.xml)及
[systemd.unit](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.unit.xml)官方文件；Linux實際載入仍未驗。
新程式root候選 `/home/ruan/cpbl-fetcher/cpbl393-auto-supply`、out root0700均須另核部署；
unit沿既有 `/home/ruan/cpbl-fetcher/cpbl393-7ac2b0d6/{venv,browsers}` 路徑，當下可用性未重查，缺件停而不安裝。
數字設定只放 `/etc/cpbl393-source/<job>.conf`，不讀專案 `.env` 或DB／HC秘密。
Linux原生systemd解析、實際User／路徑／權限及timer觸發尚未驗；本輪只有離線parser／替身。

| job／台北觸發候選 | discovery上限 | Pi總上限 | VPS首次WWW後總窗候選 | read硬額／操作額 |
|---|---:|---:|---:|---:|
| scrape-daily，每日10:10 | 3000秒 | 6000秒 | 3000秒 | 1202／600 |
| postseason-evening，每5分鐘 | 240秒 | 480秒 | 240秒 | 650／600 |
| weekly-box-revisions，週一14:10 | 3600秒 | 7200秒 | 3600秒 | 1322／600 |

以上是**待同次採認的操作預算**，不是全年工作實測時長。Pi總窗同時覆蓋discovery與VPS首次WWW後窗口；
VPS各job須明確注入配對的 `CPBL_JOBS_SOURCE_MAX_OPERATIONS/MAX_SECONDS`，不能換成一個不相符的全域預設。
SFTP工作上限120秒＋既有最多10秒wait；GET還受本次剩餘discovery／服務窗限制，raw與metadata各受producer共同期限限制。
source worker仍受manifest的最多300秒／剩餘窗減10秒控制。若剩餘時間不足就停止，不以延窗補足。

每有新批最少read1＋raw1＋metadata1；重複、空等、缺出口、busy的poll均記錄，busy不計實際client。
每worker的硬read額如表；每prefix raw／metadata各≤600（亦受總窗及5秒重入約束）。
按照30秒discovery＋5秒active，配對來源窗口有效時，保守read上界另為daily702／evening58／weekly842；
quiet且沒有prefix時分別≤101／9／121。evening每日最多288次喚醒，不能只報單次或成功批成本：
quiet日含daily最多2693次read，週一再加121。正常timer每5分鐘最多一次，另外的prefix接棒也必須計數：
evening保守≤576次worker啟動／日（300秒最多2次）；全active粗上界為34952次read／日（週一），不是預期實測。
全active下raw與metadata亦須各別計數：valid來源窗＋5秒重入時，evening每worker各≤49，daily／weekly各≤600；
按上述觸發＋接棒上界保守合計各≤29424 client／日（週一），不是服務必然發出的數量；任何實測與額度均須另核。
原文理論總量仍≤每job操作額×8MiB；每批1／2body，個別≤8MiB，index與manifest落檔後各≤1MiB，收條≤4096B。
DIRECT2只證既有3檔556315 logical bytes直送與VPS gate成功，不證新量額、冷context或這組時限足夠；
HTTP上限是清單操作額，不是完整線路流量，附屬觀測仍是下界。現有檔案保留／SD可用空間與清理政策須在正式運轉包說清，
本候選沒有自動刪原文／備份／attempt紀錄，不把儲存上界當已保留足夠空間。

正式安裝／啟動與Mac停用未授權；共同主PM互斥時先停三timer，再按owner流程等原service和直接client退出，
不能用VPS撤出口／writer鎖解除推定Pi已停止。後續一次完整核發須同時綁新讀向、帳號/key/root、三端固定來源、
Pi服務與VPS S1時序、全部poll／raw／metadata額，以及raw停寫即可消費的新判準。

本機測試只用虛構token／session文字與受控子程序；不是新的官網或Pi證據。
成熟來源14c的ORIGINAL1兩端成功仍為取源路徑依據；本候選正式原文落檔／受控傳輸與範圍驗證尚待新核發及正式審核。

## Pi → VPS 直送候選

`cpbl_pi_send.py` 只使用標準庫、未改的 `www_fetch.py` 與系統 `/usr/bin/sftp`。
同版 receiver 文件／設定原樣保存在 `receiver-v1-candidate/`，版本
`cpbl393-sftp-drop/v1-candidate.1`；其中帳號、UID/GID、目錄與 key 仍是未部署候選，
不是已核發的正式操作。sender 不建立帳號／key、改權限、取源、部署或呼叫 parser／DB。

未來須在整合租用明列這些檔案、認證引用及既有固定包後才可執行，例如：

```bash
/existing/venv/bin/python -I -B ops/pi-fetcher/cpbl_pi_send.py /private/original-manifest.json \
  --bundle /private/job-out/original-manifest-id --timeout 120
```

範例 120 是待核的工作秒數，不是已核窗口；另保留原 `wait_worker` 的 TERM/KILL wait 最多 10 秒。
`--identity-file`／`--known-hosts` 預設為合同的 Pi 專用路徑；只能引用新核發綁定的檔案，
不得用 Mac／Actions key。Python 只 stat 私鑰（當前 UID／0600／非 symlink），不讀其內容；
known_hosts 要是私有專檔，只有一筆指定 host 的 ED25519 公鑰且 SHA256 與固定 pin 相符。
兩個認證路徑在檢查前一律拒絕 `%`／`$` 展開語法與設定跳脫字元，確保 Python 驗證的
字面檔案就是 OpenSSH 使用的檔案；一般路徑及空白仍可使用。
不接受任意主機／帳號／根／遠端 shell command，不載入使用者 SSH config／agent／轉送／代理。

先由原 `verify_bundle(require_complete=True)` 驗整包與獨立原 manifest，再執行**一次**原生 batch：
排他 `mkdir /incoming/<manifest_id>` → `mkdir responses` → 僅 `put` 索引列出的原文 →
`put index.json` 到 `.index.json.upload` → `rename` 為最後的 `index.json`。
相對本機路徑由原 ID 產生，bundle 路徑透過子程序 cwd 傳入，不插入 batch 語法；沒有遞迴、
忽略錯誤、resume、retry、delete 或換 run_id 繞過碰撞。失敗不清理遠端部分檔。
省略request／serve模式時，來源必須已停寫，同 run 不得在傳輸中變更或被消費；這是原可信 sender 前提。
request／serve模式新增的私有鎖與完成收條，及其消費判準差異見上方，不能混成舊介面已核範圍。

stdout 僅安全 JSON；rc0／`transfer_complete` 只代表本機前置與整份 SFTP batch 成功，
不代表遠端驗 hash、parser、writer 或發布。非零／逾時／未知一律 rc1，保留原生 `sftp_rc`
（未取得則 null），不從 1／255 等碼猜成既存 ID 或已回滾。輸出不包含子程序 stdout/stderr、
原文、token、key 或例外內容。消費端仍獨立保留原 manifest，走既有 verify/read gate。

**標準 SFTP 不提供 server 強制 write-once**：受認證帳號仍可改寫自己既存檔。
本候選僅以可信 sender 的 mkdir 排他、原生 batch 首錯停與 index 最後發布避免正常誤覆寫。
這項模型須經同版必要審核與部署前明確風險接受；不得以 client 行為宣稱 server immutable。
OpenSSH allowlist／版本／Include/Match／實際帳號與端到端 pin/key/權限相容尚未在真機驗證。
離線程序替身只證 sender 參數、順序、拒收與 rc，不能冒稱驗過原生 server 能力。
