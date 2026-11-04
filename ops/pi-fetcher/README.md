# WP3：沿原爬蟲的私有原文代取器

Pi只依VPS清單代取www，產出原文與索引；直送候選見下方。解析、DB、計算、發布、接收端部署及正式排程由其他工作包承接。
目前版本不含舊guard／CDP／Worker限制／API代送，亦不修改`src/cpbl/ingest/_browser.py`。

## 來源與執行

`OriginalSessionDriver`直接呼叫成熟`session.page_html()`與`session.post()`；沿用原browser/context設定、
當下`fetch`、自然轉址及原helper內部的恢復行為，不提前捕獲JS或重寫原型。
外層不重跑清單／失敗操作。原PLAN的首次診斷「不重試／全HTTP≤50」不能冒稱這個成熟helper無內部重載；
下一次實網核發須明列這個口徑，不因候選可用就自行起跑。

Pi只需以下三檔及**已裝**Python／Playwright／Chromium，不必安裝cpbl或DB/ML相依：

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
page HTML是否取得沿原helper返回／require判定。post status沿原helper返回值，200且JSON可解析才保存。
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
它不下載請求清單、不排程、不輪詢，也不啟動 VPS parser／writer；省略 `--fetch` 的既有直送行為不變。
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

### VPS → Pi 請求讀取方向的既有缺口

既有 `cpbl393-sftp-drop/v1-candidate.1` receiver 是上傳接口：`sshd-receiver.conf.in` 的
allowlist 沒有 `read`／`readdir`，獨立原 manifest 在 chroot 外，亦沒有已核的 `/requests` 讀取路徑。
不能把 sender 的上傳能力當成 Pi 已能自動取得清單，也不能借 root／備份 reader 身分完成它。
本候選沒有改 receiver 合約、建立新路徑或暗加讀取權限。

WP4 的請求 producer 與消費端須先固定本輪 manifest 的原 bytes、ID、hash、可讀檔案路徑與
不和傳輸並行的收件方式，再把必要的讀取方向／權限差異集中納入兩端部署及一次驗證核發。
沒有另造 `current.json`，也沒有把固定 F2 包或人工 `CPBL_REPLAY_*` 當每日新產物。
VPS 必須保留獨立原 manifest，只挑同 ID／hash 的完整 bundle，重用 `verify_bundle`／`read_response`；
最後 `index.json` 的出現不單獨證明 SFTP client 已退出，原可信 sender 的同 run 停寫／不併行消費前提仍需履行。

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
來源必須已停寫，同 run 不得在傳輸中變更或被消費；此為合同的可信 sender 前提，沒有新增鎖／ready 協議。

stdout 僅安全 JSON；rc0／`transfer_complete` 只代表本機前置與整份 SFTP batch 成功，
不代表遠端驗 hash、parser、writer 或發布。非零／逾時／未知一律 rc1，保留原生 `sftp_rc`
（未取得則 null），不從 1／255 等碼猜成既存 ID 或已回滾。輸出不包含子程序 stdout/stderr、
原文、token、key 或例外內容。消費端仍獨立保留原 manifest，走既有 verify/read gate。

**標準 SFTP 不提供 server 強制 write-once**：受認證帳號仍可改寫自己既存檔。
本候選僅以可信 sender 的 mkdir 排他、原生 batch 首錯停與 index 最後發布避免正常誤覆寫。
這項模型須經同版必要審核與部署前明確風險接受；不得以 client 行為宣稱 server immutable。
OpenSSH allowlist／版本／Include/Match／實際帳號與端到端 pin/key/權限相容尚未在真機驗證。
離線程序替身只證 sender 參數、順序、拒收與 rc，不能冒稱驗過原生 server 能力。
