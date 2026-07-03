# CPBL_SITE_MAP — 中職官網架構地圖（爬蟲事實單一來源）

> 涵蓋兩個站台：**www.cpbl.com.tw**（主站）與 **stats.cpbl.com.tw**（官方進階數據站）。
> 目的：官網改版 / 反爬升級時，照「§5 改版排查 SOP」快速定位要修哪裡，不必重新逆向。
> 所有事實皆實測確認；更新本檔時同步更新對應模組 docstring。最後核實：2026-07-04。

---

## 1. 兩站總覽

| | www.cpbl.com.tw（主站） | stats.cpbl.com.tw（進階站） |
|---|---|---|
| 技術棧 | Vue SPA + ASP.NET MVC（AJAX action） | Next.js App Router（RSC 串流） |
| 反爬 | **HiNet CDN Anti-DDoS JS 挑戰**（2026-06 起；純 httpx 回 428） | 無挑戰（純 httpx 可用）；部分 API 經 gated proxy |
| 我方 client | **Playwright**（`ingest/_browser.py` 單例 session） | httpx 直連 |
| IP 限制 | VPS 機房 IP 被擋（404）→ **只能本機爬** | 台灣住宅 IP 正常 |
| token | 三種（見 §3） | 無 token |

---

## 2. 主站反爬層（`_browser.py`，所有主站爬蟲的地基）

**機制**：Playwright 開頁讓 HiNet 挑戰 JS 跑完 → 同一 page context 內用
`page.evaluate(fetch)` 發 AJAX（cookie/指紋一致才 200；cookie 交接給 httpx 不行）。
模組級單例：一個爬蟲 run 共用一個 browser context，挑戰過一次全程有效。

**挑戰是機率性的**，且對「短時間連續冷啟動」會**升級節流**（2026-07-03 實測）。
內建三層自癒（都會 log warning，重試退避 2s/6s/15s）：

| 症狀 | 自癒手段 | 對應方法 |
|---|---|---|
| 首載回挑戰頁（缺 token） | 重載頁面退避重試 | `page_html(require=…)` |
| in-page fetch 被攔（status=-1 / 428） | 重載頁面退避重試 | `post()` |
| cookie 壞掉→重定向迴圈（TOO_MANY_REDIRECTS） | 換乾淨 context 重試 | `_goto()` |

**操作紅線**：CLI 整輪失敗時**勿立刻重跑**——連續冷啟動會讓 HiNet 節流升級成
「token 時好時壞→fetch 全掛→重定向迴圈」的惡化循環。**先冷卻 15–20 分鐘**再單次重試。

依賴：`uv sync --group scrape && uv run playwright install chromium`（只在本機）。

---

## 3. 主站 token 三態（改版時先分清是哪一種）

| 型態 | 取法 | 用法 | 正規表式 |
|---|---|---|---|
| **A. header-token** | 頁面 inline JS 抽 `RequestVerificationToken: '…'` | 放 **HTTP header** `RequestVerificationToken` | `RequestVerificationToken:\s*'([^']+)'` |
| **B. hidden-input** | `<input name="__RequestVerificationToken" value>` | 隨**表單 body** 提交（或放 header，依 endpoint） | `name="__RequestVerificationToken"[^>]*value="([^"]+)"` |
| **C. function-block** | 頁面 JS 特定函式區塊（如 `getFighterScore: function`）內的 token | 放 header，**每個 endpoint 各自的 token** | `_token_in(html, marker)` |

⚠️ A 與 B **不可互換**：getgamedatas 用 B 會 500。

## 4. 端點對照表（模組 × 頁面 × endpoint × token × 回傳）

### 主站 www.cpbl.com.tw

| 模組 | 過挑戰頁（token 來源） | endpoint / 解析目標 | token | 回傳 / 解析錨點 |
|---|---|---|---|---|
| `cpbl_site` | `/schedule` | POST `/schedule/getgamedatas`（calendar+location+kindCode） | A | `{"Success":true,"GameDatas":"<JSON字串>"}`，需**二次** json.loads |
| `cpbl_gamelog` | `/box?year=&KindCode=&gameSno=` | POST `/box/getlive`；box 頁本身解析賽事明細 | B | `ScoreboardJson`（逐局）+ `LiveLogJson`（逐打席）；一個 token 重用多場 |
| `cpbl_stats`（投打進階） | `/stats/recordall` | POST `/stats/recordallaction` | B（**表單欄位**） | HTML 表格；選手 id 錨點 `/team/person?acnt=(\d+)` |
| `cpbl_stats`（團隊/名單/守備） | `/team/teamscore?ClubNo=` | POST `/team/teamscoreaction`（Position=01 打者/03 守備） | B | HTML `<tr>` 解析；同上錨點 |
| `cpbl_standings` | `/standings/season` | POST `/standings/seasonaction`（Year+KindCode+SeasonCode） | A | HTML 表格（含勝差/H2H/近十場/淘汰指數） |
| `cpbl_fighting`（投打對決） | `/team/fighting?Acnt=` | POST `/team/getfightingoptsaction` + `/team/getfightingscore` | C×2（opts/score 各一） | JSON；score **只給 fightingTeamNo 不給 fightingAcnt**（給了會空） |
| `cpbl_player_detail`（對戰各隊/分項） | `/team/person?acnt=` + `/team/apart?Acnt=` | POST `/team/getfighterscore` + `/team/getapartscore` | C×2（各自頁面） | JSON；vs-team **無 kindCode**（二軍不可用）、apart 有 |
| `cpbl_transactions`（升降） | `/player/trans` | POST `/player/trans`（傳統表單：Year+Month+ClubNo+…+token） | B（body） | HTML 表格事件列 |
| `cpbl_awards` | `/stats/yearaward` | POST `/stats/yearawardaction` | B | HTML；得主錨點 `/team/person?acnt=` |
| `cpbl_player_bio` | `/team/person?acnt=`（純頁面） | 無 AJAX；解析 `<dd class="…">` | — | SSR HTML（可用 `domcontentloaded` 快載） |
| `cpbl_coaches` | `/team/index?teamNo=`（純頁面） | 無 AJAX；解析教練區塊 | — | SSR HTML |

### 進階站 stats.cpbl.com.tw（httpx 直連，無挑戰）

| 模組 | endpoint | 解析 | 改版訊號 |
|---|---|---|---|
| `cpbl_advanced` | GET `/players/{acnt}`（HTML） | RSC 串流：串接所有 `self.__next_f.push([1,"…"])` → unicode unescape → 括號配對抽含 `"wobaPr"` 的物件 | `_summary_object` 抓不到 |
| `cpbl_pitch_tracking` | GET `/api/proxy/v1/players/logs`（**公開 JSON API**） | `Data.Logs[].Trackman.{Play,Pitch,Hit}`；`Trackman=null`＝無設備球場，不收 | HTTP 非 200 / schema 變 |

> 進階站解析**脆弱點在 RSC**（advanced）；logs API 是正式 JSON 較穩。
> 逐球含二軍（kindCode D）——查詢一軍**必須**過濾 `kind_code='A'`。

### 外部資料源（非官網，一次性/手動）

維基球隊條目（總教練）、twbsball query API（旅外）：見記憶 `wiki-data-sources`；
opendata 逐年 CSV：`ldkrsi/cpbl-opendata`（回填用，不再變動）。

---

## 5. 改版排查 SOP（症狀 → 原因 → 修哪裡）

| 症狀 | 最可能原因 | 排查/修法 |
|---|---|---|
| `找不到 RequestVerificationToken`（**偶發**，重跑會過） | HiNet 挑戰頁未過（機率性） | 已由 `page_html(require=)` 自癒；連續失敗＝節流→**冷卻 15–20 分** |
| 同上（**冷卻後仍 100% 失敗**） | 官網改版：token 改名/搬家 | 手動 dump 頁面 HTML（`page_html` 存檔）→ 找新 token 樣式 → 改 §3 對應 regex |
| `POST … TypeError: Failed to fetch` / 428 | fetch 被挑戰攔截 | 已由 `post()` 重載退避自癒；持續＝節流，冷卻 |
| `ERR_TOO_MANY_REDIRECTS` | 挑戰 cookie 壞掉 | 已由 `_goto()` 換 context 自癒 |
| getgamedatas 回 500 | 用錯 token 型態（B 代 A） | 檢查是否誤用 hidden-input token |
| `Success=false` 或空 GameDatas | 參數格式變（calendar/kindCode） | 開瀏覽器 DevTools 看官網自己怎麼發 |
| stats.cpbl `_summary_object` 抓不到 | RSC payload 結構變 | dump `__next_f` 串接結果，重找 `wobaPr` 錨點所在物件 |
| VPS 上全部 404 | 機房 IP 被擋（**非改版**） | 正常現象；只能本機爬（記憶 `data-sync-local-to-prod`） |
| `exit=127`（launchd 每日爬） | 本機 DB 容器沒開（OrbStack 未啟動） | 起 OrbStack + `docker compose up -d db` |

**dump 頁面快速指令**（診斷用，寫進 scratchpad 勿入 repo）：

```python
from cpbl.ingest._browser import session
html = session().page_html("/schedule")   # 需要時加 require=None 看原始挑戰頁
open("/tmp/dump.html", "w").write(html)
```

---

## 6. 與其他文件的分工

- 本檔：**官網結構事實**（endpoint/token/解析錨點/改版排查）。
- `docs/AI_RUNBOOK.md`：操作流程（跑哪個 CLI、同步生產、每日排程）。
- `CLAUDE.md`：準則紅線（為什麼）；爬蟲細節一律指向本檔。
- 各 `ingest/*.py` docstring：該模組的最小契約摘要（與本檔衝突時以實測為準並回修）。
