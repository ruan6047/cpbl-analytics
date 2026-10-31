# WP3：沿原爬蟲的私有原文代取器

Pi只依VPS清單代取www，產出原文與索引。解析、DB、計算、發布、inbox傳輸及正式排程由其他工作包承接。
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
這裡沒有實作WP4回放session／writer，也不自行送VPS。hash驗完整性，不是發布者身分驗證；受控inbox交接仍依原PLAN。

本機測試只用虛構token／session文字與受控子程序；不是新的官網或Pi證據。
成熟來源14c的ORIGINAL1兩端成功仍為取源路徑依據；本候選正式原文落檔／受控傳輸與範圍驗證尚待新核發及正式審核。
