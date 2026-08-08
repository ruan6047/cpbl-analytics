# AI_RUNBOOK — cpbl-analytics 操作事實單一來源

> 給 AI/維護者的**操作手冊**：進來先讀這份，省去重新摸索。
> 分工：[`CLAUDE.md`](../CLAUDE.md) = 準則與紅線（為什麼）；本檔 = 怎麼做、跑什麼、有什麼坑（事實）。
> 兩者衝突時，以**現實 + 本檔**為準，並回頭修正過時的那份。最後核實：2026-06-22。

---

## 1. 一分鐘心智模型

- **雙軌 ML**：(1) **成績預測** [projection]：打擊 rate stat，離線 `cpbl-train`（Marcel vs LightGBM 時間切分回測）；**2026-07-14 已下架公開 `/projections` 瀏覽頁（移除前端路由與導覽），API（`/api/v1/projections/*`）、訓練／回測、資料表與 `/api/info` 指標保留為研究資產**；(2) **賽果預測** [outcome]：單場主隊勝率，API request 時即時 fit 使用者選的特徵子集（**不離線訓練**）。
- **資料雙來源**：歷史**逐年**彙總來自 `ldkrsi/cpbl-opendata`(MIT)；**逐場/逐打席/逐球**由官網爬蟲補足。計數型季彙總仍受逐年粒度限制。
- **部署形態**：獨立 repo，作為主站 `PersonalWebsite` 的 git submodule，已上線 https://cpbl.ruan-ruan.com 。與主站**共用同一 PostgreSQL**（schema `cpbl`）。

---

## 2. 環境與服務

| 場景 | DB | API | Web |
|---|---|---|---|
| **本機** | docker compose `db`（PG 17，**port 5433**） | `uvicorn cpbl.api.main:app --port 4001` | `web/` Next.js `:3000`（**兩個** env：`API_URL` 給 SSR、`NEXT_PUBLIC_API_URL` 給瀏覽器；預設皆 `:4001`） |
| **生產**（VPS Vultr `root@45.76.100.29`） | 容器 `prod_pg`（與主站共用，schema `cpbl`） | 容器 `prod_cpbl_api`（內網 `http://cpbl-api:4001`） | 容器 `prod_cpbl_web` |

- 本機設定：`cp .env.example .env`；關鍵鍵 `DATABASE_URL`（本機預設 `postgresql://cpbl:cpbl@localhost:5433/cpbl`）。
- 生產部署：主站 `docker-compose.prod.yml`；改 code → 在主站 bump submodule → push → 自動部署（見 §7）。

---

## 3. 資料流與「本機爬 → 同步生產」（重要）

```mermaid
graph LR
  OD[cpbl-opendata CSV] -->|cpbl-backfill| LDB[(本機 cpbl)]
  WWW[cpbl.com.tw / stats.cpbl] -->|官網爬蟲<br/>本機跑| LDB
  LDB -->|pg_dump schema=cpbl<br/>SSH 灌入| PDB[(生產 prod_pg cpbl)]
  PDB --> PAPI[prod_cpbl_api] --> NGINX --> 訪客
```

**鐵則：`www.cpbl.com.tw` 爬蟲只能在本機跑，不能在 VPS 跑。** VPS 機房 IP 打 www
回 **404**（Cloudflare 擋資料中心 IP；2026-06-22 實測 `prod_cpbl_api` 內
`cpbl-scrape-games` 全 kind 404），住宅 IP 正常。`stats.cpbl.com.tw` 雖已實測可由 VPS
直連，但仍只能由通過 T4 查核、具 allowlist／request budget／kill switch 的隔離
observer／production worker 使用；不得把「stats 可連」擴張成任意 VPS crawler 權限。
詳見記憶 `data-sync-local-to-prod`。

### 官網反爬（Playwright；2026-06 起）

主站有 HiNet CDN JS 挑戰，純 httpx 回 428 → 爬蟲走 **Playwright**（`ingest/_browser.py`
單例 session：開頁過挑戰 + page context 內 fetch 發 AJAX）。依賴：
`uv sync --group scrape && uv run playwright install chromium`。

- 挑戰**機率性**觸發；`_browser.py` 內建重載退避自癒（`page_html(require=)`/`post()`/`_goto()`）。
- **失敗勿立刻重跑**：連續冷啟動會讓 HiNet 節流升級（token 時好時壞→fetch 全掛→重定向迴圈，
  2026-07-03 實測）。先冷卻 **15–20 分鐘**再單次重試。
- 端點/token/解析錨點/改版排查 → **[`CPBL_SITE_MAP.md`](CPBL_SITE_MAP.md)**（爬蟲事實單一來源）。

### VPS 隔離 live observer（OPS-LIVE-SHADOW1；**已退役，勿再啟動**）

暫時 observer 於 2026-07-30 00:00（Asia/Taipei）硬截止後 clean exit，service 已由
PersonalWebsite protected main `3bee24c` 自 `docker-compose.prod.yml` 移除，該卡 2026-08-03 結案。
截止時間釘在 versioned code，`src/cpbl/ingest/live_shadow_observer.py` 保留為 dormant 產物：
任何啟動都會在發出 network request 前 exit 0，**不能靠它蒐集新資料**，需要即時來源請走
下一節的 live worker。

evidence volume `cpbl_live_shadow_evidence` 與 network `cpbl_live_shadow_egress` **刻意保留在
主站 compose**（原始 raw gzip 與 manifest 已完成 T4 對帳，`LIVE-GAME-BACKEND1` 已據此結案）；
刪除 volume 是不可回復資料操作，須 ruan6047 明示，**嚴禁 `docker compose down -v`**。

### Live game worker（LIVE-GAME-BACKEND1；**已 production cutover，2026-07-30**）

live worker 只打 VPS 可直連的 `stats.cpbl.com.tw`，不走 VPS 回 404 的 www 主站。它是獨立
process：寫 Redis JSON cache，API 只讀 cache 並在 Redis 失效時退回既有 PostgreSQL；不違反
API 唯讀契約。

**生產現況**：主站 compose 的 `cpbl-live-worker`（container `prod_cpbl_live_worker`、
`restart: unless-stopped`、backend network、`depends_on: redis healthy`）以
`LIVE_GAME_WORKER_ENABLED=true` 常駐運行；2026-07-30 由 `LIVE-GAME-BACKEND1` 完成 cutover
（主站 merge `30d81b4f`、Deploy run `30544781295`、真實 live canary `2026-A-231`）。
**碼內預設仍是 `LIVE_GAME_WORKER_ENABLED=false`**——啟用只發生在生產 compose 的 env，
本機／CI 不會誤啟動。回滾路徑為 kill switch key `cpbl:live:kill` 或停掉該 service，兩者皆
經 T4 查核與 production compose 查核確認（下方指令為本機 compose 版本；生產端需在 VPS 以
主站 `REDIS_PASSWORD` 連 `prod_redis`，此處不放未實測的指令列）。

```bash
docker compose up -d --build redis live-worker      # 本機持續 shadow
docker compose run --rm live-worker cpbl-live-worker --once   # 單 cycle canary（compose 網路內的隔離 redis）
docker compose logs -f live-worker

# 即時 kill switch（1=停止抓取；DEL=恢復）
docker compose exec redis redis-cli SET cpbl:live:kill 1
docker compose exec redis redis-cli DEL cpbl:live:kill
```

> ⚠️ one-shot 不要用 `REDIS_URL=redis://localhost:6379/0` 在 host 直跑：compose 的 redis
> **沒有發布 host port**，host 的 6379 是主站 `personal_website_redis`——會把 `cpbl:live:*`
> 寫進別的專案的 Redis（T4 查核實測踩中）。一律走 `docker compose run` 進 compose 網路。

- polling base：live 12 秒、T-90m 內 60 秒、T-30h 內 10 分鐘、其餘 30 分鐘；正常值另加
  0.9–1.1 jitter，錯誤指數退避最多 5 分鐘，每 cycle 最多 8 場。
- `START` 依官方 raw status，不看比分；兩隊 lineup 可各自 partial。A-226～228 證實
  `Pitchers[]` 僅在 START 後出現且帶 box 統計，正式 probable starter 來源在 Design Gate
  定案前一律 fail closed，不得由 `RoleType=先發` 倒推。
- final 後 TrackMan 可能延遲（2026-07-26 A-224／225 完賽當下仍 0），0 筆只標 pending。
- 觀測矩陣與 canary evidence：[`research/LIVE_GAME_BACKEND1_OBSERVATION.md`](research/LIVE_GAME_BACKEND1_OBSERVATION.md)。

**每日刷新現況（最後驗證 2026-07-19）**：本機 launchd 10:10 已成功完成爬取與 production 同步（`sync_ok=true`）。仍必須每天以 `refresh_status.py check --scheduled` 檢查；成功同步不等於資料語意正確——目前 `BUG-HELD-GAME-FRESHNESS1` 已證實未完成保留賽會污染 `last_game_date`，修復前不得僅以 freshness gate 判定資料正確。

### 本機每日爬取（launchd 每日 10:10；手動為 fallback）

launchd 在使用者登入態每日 **10:10** 觸發 `scripts/scrape-daily.sh`；腳本先寫
`state=running`，本機爬成功後才備份並同步 production。**時段紅線**：勿改到深夜／凌晨，
官網挑戰深夜加嚴會硬封鎖新訪客（SITE_MAP §2）。OrbStack 與本機 DB 必須已啟動；否則
狀態會是 `failed_phase=scrape`、`exit=127`，不會嘗試 production sync。

安裝／重建排程：

```bash
ln -sf "$PWD/scripts/com.cpbl.scrape-daily.plist" ~/Library/LaunchAgents/com.cpbl.scrape-daily.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cpbl.scrape-daily.plist   # 啟用
launchctl kickstart -k gui/$(id -u)/com.cpbl.scrape-daily                             # 立即測跑
launchctl bootout gui/$(id -u)/com.cpbl.scrape-daily                                  # 停用
```

**AI 接手失敗的契約**（三個訊號源，由輕到重）：
1. `logs/last-status.json` — 最近一次手動或排程執行；含 `state`、`trigger`、
   `failed_phase=scrape|sync`、兩階段 exit code 與 log tail。`logs/last-launchd-status.json`
   只由 launchd 更新，不會被手動 fallback 覆蓋。
2. `logs/refresh-YYYYMMDD-HHMMSS.log` — 該次完整輸出（last-status.json 的 `log` 指向它）。
3. `SELECT * FROM cpbl.refresh_log WHERE ok=false ORDER BY refreshed_at DESC LIMIT 1` — app 層失敗（含 `note`、`detail.error`）。

Fail-fast：

```bash
python3 scripts/refresh_status.py check                 # 最近一次完整流程
python3 scripts/refresh_status.py check --scheduled     # 今日 11:00 後仍無 launchd 觸發即失敗
docker compose exec -T db psql -U cpbl -d cpbl -c \
  "SELECT refreshed_at, ok, note, detail->>'error' AS error FROM cpbl.refresh_log ORDER BY refreshed_at DESC LIMIT 3"
```

檢查器 exit code：`0` 成功、`2` 排程未觸發／過期、`3` 爬取失敗、`4` 同步失敗、
`5` 狀態檔無效、`6` 尚在執行、`7` 執行超過 180 分鐘而視為死亡／停滯。手動與 launchd
共用 `/private/tmp/cpbl-analytics-refresh.lock` 互斥；已有執行時第二次啟動回 `75`，且不覆寫狀態檔。
`exit=127` = 本機 DB 容器沒開；token 抽不到 = 官網挑戰／改版（見
`cpbl_site._new_session`）。手動 fallback 直接跑 `scripts/scrape-daily.sh`
（預設 `trigger=manual`）；若爬取已成功、只有 sync 失敗，修正 production 原因後應以
`SKIP_SCRAPE=1 WITH_DETAIL=1 scripts/refresh-cpbl-prod.sh` 重試，**不可再次冷啟動 crawler**。

### 官方 box 逐投手快照：每週深度重抓近 30 天（DATA-BOX-REVISION-SNAPSHOT1）

`cpbl.box_pitching_revisions`（append-only、與**該場該投手最近一次觀測**比較的內容
雜湊去重——**不是全域去重**，見下方 BOX-REVISION-R1-001）記錄每次抓 box 時逐投手的
outs／runs／earned_runs，讓「官方賽後修正判決」vs「livelog 漏記」從不可證偽變成可量測
（源起 #107 ML-PITCHER-ER-REBUILD1 spec 基線 §7.6「假設(c)不可證偽」；該研究文件
在其他分支進行中，本卡不碰）。每日窗只重抓 `[昨天,今天]`
2 天，一場比賽被抓過一次後不會再被自動排程碰到；本排程每週把**近 30 天已完成場**的
box 重抓一次，讓 30 天內的修正收斂進快照。**30 天是保守選擇、不是量測結果**——目前不知
道官方改判的延遲分布（那正是本卡要累積出來的資料），累積出第一批 `days_since_game`
分布後應回頭檢視這個窗要不要調整（見 `run_refresh_box_deep` 模組 docstring）。

與每日窗完全分開，不改 `_incremental_detail` 的 2 天窗邏輯；獨立 CLI
（`cpbl-refresh-box-deep`）+ 獨立 launchd job + 獨立狀態檔，落地方式比照上一節的
逐球每週全季重跑：共用 refresh lock 且**忙碌即跳過**、失敗**不自動重試**（下週用同一個
「近 30 天」窗從頭跑，不需要斷點續傳）、排在週一 14:10（距 weekly-game-pitches.sh 的
13:10 一小時緩衝，降低撞期整週跳過的機率）。

```bash
ln -sf "$PWD/scripts/com.cpbl.weekly-box-revisions.plist" ~/Library/LaunchAgents/com.cpbl.weekly-box-revisions.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cpbl.weekly-box-revisions.plist
launchctl kickstart -k gui/$(id -u)/com.cpbl.weekly-box-revisions   # 立即測跑
cat logs/last-weekly-box-revisions.json                              # 狀態（ok/skipped/failed）
```

實測成本（2026-08-08，本機真實跑 `cpbl-refresh-box-deep 2026 A 2` 與
`... D 2`，非估算）：Playwright 瀏覽器啟動 ~7–9 秒（每次 CLI 呼叫各付一次）＋每場
~1.4 秒（`--delay 1.2` 的請求間隔＋實際請求耗時），4 場 A 級耗時 14.2 秒、4 場 D 級
11.1 秒；同窗重跑驗證冪等（79 列不變、`seen_count` 遞增）。今日量測近 30 天窗
A=50 場、D=38 場，線性外推整週實跑約 **2–2.5 分鐘**（≈139 秒）——這是外推不是實測整窗，
且會隨球季推進而變。

**這個機制目前只能看見「近 30 天內」的修正**：30 天以外發生的官方改判不會被本快照觀測到
（歷史場次亦無回溯快照，只有部署日起才開始累積）。

**BOX-REVISION-R1-001（跨家族查核 2026-08-08，已修，migration 072）**：071 原本的
`UNIQUE(year, kind_code, game_sno, pitcher_acnt, content_hash)` 是**全域**內容去重，
不是「與最近一次觀測比較」。後果是 A→B→A 這種回改（聯盟推翻後又推翻回來，或抓取
瞬間看到中間態）——第三次觀測的 content_hash 會撞回第一次那列，只被當成「重複」
+seen_count，B→A 這次真實發生的改判會直接從快照消失，`pitcher_er_revision_report()`
答不出「改過幾次」。已改為「只與該 (year, kind_code, game_sno, pitcher_acnt) 最近
一次觀測比較」，冪等改由 `record_box_pitching_revisions()` 的寫入邏輯保證（INSERT
... WHERE NOT EXISTS 最近一列同 hash）。既有 79 筆快照（修法前寫入）逐一查過：
每個 (year,kind_code,game_sno,pitcher_acnt) 都只有 1 列，尚未出現過第 2 版，
更談不上 A→B→A——這批資料只累積了不到一天，改判需要時間發生，故確認沒有已經
遺失的回改事件。

**BOX-REVISION-R2-001（跨家族查核 2026-08-08，已修）**：R1-001 修完後的第一版
docstring 曾宣稱「只有兩個呼叫端、都受同一把 refresh lock 互斥保護」——這句話
是錯的，查核在 `run_scrape_gamelog.py`（手動 `cpbl-scrape-gamelog <year>` CLI）
找到第三個完全沒鎖的呼叫端。完整盤點：`cpbl_gamelog.scrape_gamelogs` 有 3 個
呼叫點在 `run_refresh_recent.py`（同一 process，受 `scrape-daily.sh` 的
`/private/tmp/cpbl-analytics-refresh.lock` 保護）、1 個在 `run_refresh_box_deep.py`
（週深度重抓，受 `weekly-box-revisions.sh` 的同一把 lock 保護）、1 個在
`run_scrape_gamelog.py`（手動全季回填 CLI，**沒有 lock**）。「讀最近列→決定
INSERT/UPDATE」本身不是原子操作，UNIQUE 約束拿掉後這段完全依賴呼叫端自律——
而呼叫端盤點剛剛才錯過一次，不該把正確性建立在「記得幫每個新呼叫端上鎖」這件
事上。已改為在 `record_box_pitching_revisions()` 內對每個 PK 取
`pg_advisory_xact_lock`（雜湊 `year:kind_code:game_sno:pitcher_acnt` 當 key），
把整段序列化——用 advisory lock 而非 `SELECT ... FOR UPDATE`，是為了不用另外
處理「這個 PK 第一次寫入、還沒有列可鎖」的邊界（advisory lock 鎖的是任意 key，
不需要先有列存在）。正確性因此不再依賴呼叫端盤點是否完整；下次有人加第四個
呼叫端，就算又忘記上鎖，advisory lock 一樣會保護。

**BOX-REVISION-R2-002（跨家族查核 2026-08-08，non-blocking，已揭露）**：
`pitcher_er_revision_report()` 的回傳型別從 `list[dict]` 改成 `dict[str, Any]`
（`{"revisions": [...], "caveat": ...}`）——這是**破壞性回傳契約變更**，不是「單純
新增 caveat 欄位」。截至本卡交付當下，repo 內唯一消費者是測試檔（已同步）；未來
新 consumer 須讀 `result["revisions"]`。

> **零觀測不代表官方沒有改判**（BOX-REVISION-R1-002）：這份資料只涵蓋（1）部署本
> 功能之後才抓到的場次（2018–2026 既有歷史場次無回溯快照）且（2）目前抓取窗口內
> （每日近 2 天、週深度重抓近 30 天）實際觀測到的版本。官方改判的真實發生率未知，
> 30 天以外或部署前發生的修正即使真的存在也不會出現在這裡——**查不到修正只代表
> 「這個窗口沒看到」，不能當作「沒有發生過」的證據**。這句話同時寫進
> `pitcher_er_revision_report()` 的回傳值（`caveat` 欄位），讀數字的人不必回頭
> 翻這份文件才知道限制在哪。

### 逐球 TrackMan：抓取維度 flag 與每週全季重跑（INGEST-GAME-TM-REFACTOR1-G4 Phase A）

refresh 鏈的逐球抓取維度由 `CPBL_PITCH_INGEST` 控制（pydantic-settings）：

| 值 | 路徑 | 請求量 | 用途 |
|---|---|---|---|
| `game`（預設） | 單場 API `/api/proxy/v1/games/{y}-{k}-{sno}` | 每場 1 請求 | 正式路徑；不受球員名冊異動的 acnt 對帳漏損 |
| `pitcher` | 逐投手 logs `/api/proxy/v1/players/logs` | 每投手 1 請求 | **回滾**路徑（紅線 5 觸發時使用） |

值打錯會在啟動時直接拋 `ValidationError`（Literal 型別）——回滾控制桿不得靜默落回預設，
否則「已回退」的宣稱不成立。兩條路徑共用同一組落後場判準（`_lagging_pitch_games`）、
同一 pure parser 與同一冪等 UPSERT，切換只改請求維度、不改入庫語意。

`_lagging_pitch_games` 的**設備判準是近期感知**：某球場最近 **10** 場完成場中至少一場達
`pitches >= 50 AND tracked >= pitches * 0.80`。這兩個常數是**需求方 2026-08-04 裁定的營運
政策**（非資料推導），改動須先有需求方 event——`tests/test_refresh_pitch_ingest.py` 有
字面 pin 住，改了會紅。舊的「本季曾達」判準是 recency-blind 的，已被實測推翻
（大巨蛋 2026-03 覆蓋 98.4%、06-02 起連續全零，舊判準會讓它永久通過而被每日重抓）。

**每週全季重跑**（週一 13:10，`scripts/weekly-game-pitches.sh`）：官方可在任何時點做賽後
修正，每日增量只看近幾天窗口不會回頭，故每週把全季完成場重跑一次使修正最遲七天內收斂。
排程失敗**不得中斷每日 refresh**，落地方式三層：獨立 launchd job 與狀態檔（每日鏈不讀）、
共用 refresh lock 且**忙碌即跳過**（不等待不搶佔）、排在週一休兵日且遠離 10:10。

```bash
ln -sf "$PWD/scripts/com.cpbl.weekly-game-pitches.plist" ~/Library/LaunchAgents/com.cpbl.weekly-game-pitches.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cpbl.weekly-game-pitches.plist
launchctl kickstart -k gui/$(id -u)/com.cpbl.weekly-game-pitches   # 立即測跑
cat logs/last-weekly-pitches.json                                  # 狀態（ok/skipped/failed）
```

**凍結例外清單**（`cpbl_pitch_tracking.FROZEN_GAMES`）：經三方比對證實**兩支官方端點
互相矛盾且單場 API 為較差來源**的場次，由需求方逐場核入；凍結場次**任何寫入路徑都跳過
不寫**（增量、每週全季重跑、手動 CLI、logs 回退路徑皆然）。fail-closed 為雙層——
`_upsert` 在唯一寫入口過濾，`scrape_game_pitches` 另外連請求都不發。

首例 `2026-D-180`（07-30 澄清湖）：logs 端點現值 vs 正式表 0/109 不一致（排除正式表過期）、
vs 單場 API 100/100 不一致，且單場 API 全 105 列缺 `PitchTag`、軌跡係數全異、少 4 列。

> ⚠️ **執行者／AI 不得自行擴充此清單**。新增一律需求方明示核入並留 event，且必須先有
> 三方比對證據證明單場 API 較差——「兩邊不一樣」本身不是核入理由。
> 兩向端對端測試見 `tests/test_refresh_pitch_ingest.py`（清單外照常寫、清單內任何路徑都不觸碰）。

### 同步流程（本機 → 生產）

每日同步採逐表冪等 upsert，且只動 `cpbl` schema；禁止在 VPS 爬官網。標準入口已內建
production 備份、gzip 完整性檢查、migration、upsert、模型重建，以及真實賽事指標與本機
對帳。只有 `/api/info.metrics.last_game_date` 與 `season_games_completed` 都吻合後才寫入
`prod-sync` refresh marker，最後再檢查 `/api/info.metrics.last_refresh` 的 15 分鐘 freshness gate：

```bash
SKIP_SCRAPE=1 WITH_DETAIL=1 scripts/refresh-cpbl-prod.sh
```

每次執行都會先在
`~/Library/Application Support/cpbl-analytics/backups/cpbl-prod-YYYYMMDD-HHMMSS-<pid>.sql.gz`
產生完整備份，驗證後才晉升，預設保留最近 7 份（可用 `BACKUP_DIR`／`BACKUP_KEEP` 覆蓋）；
看見「已驗證備份」前不得進 production migration。回復時只還原該 `cpbl` schema 備份，
不碰主站其他 schema：

```bash
gunzip -c "$HOME/Library/Application Support/cpbl-analytics/backups/cpbl-prod-<timestamp>-<pid>.sql.gz" | \
  ssh root@45.76.100.29 \
  'cd /opt/personal-website && set -a && . ./.env && docker exec -i prod_pg psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME"'
```

production migration 由已部署的 `prod_cpbl_api` 映像執行；若 local main 已有 migration 修正、
production 映像尚未部署，先停止同步並完成正常 main deploy，不得跳過 migration 或臨時改 DB。

---

## 4. CLI 速查（`uv run <cmd>`；皆冪等 UPSERT）

| 指令 | 做什麼 | 何時用 |
|---|---|---|
| `cpbl-backfill` | migrate + opendata 逐年回填(1990–2024) | 初始化 / 改 migration 後 |
| `cpbl-backfill-season <year>` | 官方 teamscore 回填某年 season 彙總(opendata 未涵蓋年) | 補新年度季彙總 |
| `cpbl-scrape-games <from> <to>` | 逐場賽程/比分/先發/勝敗投(A 例行+C 總冠軍+E 季後) | 補當季比分（**逐打席的前提**） |
| `cpbl-scrape-gamelog [year]` | 每場逐局比分 + 逐打席事件流(box/getlive) | 補賽況頁資料；需比分先就緒 |
| `cpbl-refresh-box-deep [year] [kind] [days_back] [--delay]` | 深度重抓近 N 天（預設 30）已完成場的 box（等同對該窗重跑 `scrape_gamelogs`）；**只寫**逐投手 append-only 快照 `cpbl.box_pitching_revisions`（既有表照常冪等 UPSERT，非本卡新增行為） | DATA-BOX-REVISION-SNAPSHOT1 深度層：每日窗只看昨/今 2 天，一場抓過一次後不會再被自動排程碰到；每週跑一次收斂近 N 天內的官方賽後修正 |
| `cpbl-scrape-stats <from> <to>` | 投打進階 + 團隊累計(ERA/WHIP/K9/OPS…) | 當季累計刷新 |
| `cpbl-scrape-standings <year>` | 官方戰績(含上下半季/勝差/H2H/近十場) | 戰績刷新 |
| `cpbl-scrape-pitches [delay]` | 逐球 TrackMan（**投手中心** logs API，全投手→自動涵蓋所有場次）；**現行每日 refresh 的唯一正式 writer** | 逐球刷新 |
| `cpbl-scrape-game-pitches [year] [kind] [snos…\|近N天]` | 逐球 TrackMan（**比賽中心**，單場 API `/games/{y}-{k}-{sno}` 的 LiveLog；與 logs 路徑共用 pure parser、冪等對接同表）；一場一請求、免名冊、實測 ~88% 少請求 | INGEST-GAME-TM-REFACTOR1 Gate 1-2 落地；**尚未切為 refresh 正式路徑**（Gate 3 shadow／Gate 4 cutover 待做） |
| `cpbl-shadow-game-tm [year] [kind] [window_days]` / `--report` | Gate 3 shadow harness：抓賽程 shadow（`games/schedule`，GameStatus 分桶）+ 只對 FINISHED 場打單場 API，寫隔離 `cpbl.game_tm_shadow_*` 表並唯讀對帳正式 `pitch_tracking`；`--report` 只印最近一次 run 摘要 | 14 天觀測窗期間每日手動跑；**不寫** `cpbl.pitch_tracking`、不影響正式 refresh |
| `cpbl-live-worker [--once]` | stats 單場 API → Redis canonical snapshot；集中式 lock／kill switch／adaptive polling | **已 production cutover（2026-07-30）**，生產以 `prod_cpbl_live_worker` 常駐；碼內預設 `LIVE_GAME_WORKER_ENABLED=false`，本機須顯式開啟 |
| `cpbl-scrape-advanced` | 官方進階 + 官方 PR(stats.cpbl) | 進階數據刷新 |
| `cpbl-scrape-detail` / `cpbl-scrape-fighting` | 選手對戰各隊/分項 / 投打對決 | **分項/vs各隊已改重算停爬**（見 build-splits）；detail 僅剩季後 C/E 生涯補抓、fighting 供投打對決 |
| `cpbl-refresh-recent [fast]` | 抓昨天/今天：games+累計+(增量)對戰/逐球 + **重算分項寫回**，寫 `refresh_log` | 每日增量（本機跑） |
| `cpbl-build-splits [year] [kinds]` | **重算**本季 splits+vs各隊四表並寫回 + 生涯(base+本季)（純 DB 不爬，**生產可自跑**） | 已含於 refresh；手動重建分項 |
| `cpbl-anchor-career <season> <csv_dir>` | 錨定生涯基底（官方生涯−官方本季同刻相減，一次性/重錨） | 跨年 roll 或重錨（見其 docstring） |
| `cpbl-ingest-editorial` | 私有 Google Sheet → 嚴格驗證 → append-only 編輯內容 revisions（公開 API 仍唯讀） | **暫停（2026-07-19）**：不得執行 ingest 或 production migration；待其他項目完成後重新規劃。歷史契約見 [`EDITORIAL_DATA_PIPELINE.md`](EDITORIAL_DATA_PIPELINE.md)。 |
| `cpbl-verify-splits [year] [kind]` | 分項重算 vs 官方爬值逐格對照 harness | 只對「新爬的官方值」有意義（寫回後即自比） |
| `cpbl-build-championships` | 由逐年可追溯的 `championships` canonical dataset 決定冠軍→標該年一軍球員+總教練（物化 `championship_members`，純 DB 不爬） | 改冠軍資料／成員邏輯後（已含於 refresh-recent） |
| `cpbl-build-features` | 賽果預測特徵表(leakage-safe) | 改賽果特徵後 |
| `cpbl-train` | 成績預測訓練+回測（**需 LightGBM → 容器內跑**） | 改成績模型/特徵後 |

**補多天缺口的正確順序**（`refresh-recent` 只補昨/今，補不了更早）：
`cpbl-scrape-games 2026 2026` → `cpbl-scrape-gamelog 2026` → `cpbl-scrape-stats 2026 2026` → `cpbl-scrape-standings 2026` → `cpbl-scrape-pitches` →（同步見 §3）。

### macOS LightGBM
host 缺 `libomp.dylib`。**勿 `brew install libomp` 污染 host**；需 LightGBM 的步驟（`cpbl-train`）在容器內跑：`docker compose run --rm api cpbl-train`。`backfill`/爬蟲不需 LightGBM，host 直接跑。

---

## 5. API 地圖（FastAPI，唯讀；`src/cpbl/api/`）

`main.py` 只做 app 組裝；路由按領域拆在 `routers/`（info/projections/leaders/outcome/standings/players/games/ability/tracking/trend/teams），共用工具在 `helpers.py`（局數換算等純函式）與 `rows.py`（跨路由季成績列 SQL）。新端點加進對應 router 後，記得更新 `tests/test_route_snapshot.py` 的 EXPECTED。

| 群組 | 端點 |
|---|---|
| 契約/健康 | `/api/info`（主站 InfoPoller，**永不拋錯**）、`/healthz` |
| 成績預測 | `/api/v1/projections/batting`、`/season/batting-leaders`、`/season/pitching-leaders`、`/season/fielding` |
| 賽果預測 | `/outcome/features`、`/outcome/evaluate`、`/outcome/teams`、`/outcome/matchups`、`/outcome/simulate` |
| 戰績 | `/season/standings`、`/standings` |
| 球員頁 | `/players/{id}/batting|pitching|season|profile|fielding|vs-team|splits|matchups|advanced|discipline|arsenal|pitch-mix|trend`、`/players/roster`、`/matchups` |
| 賽況 | `/games/recent`、`/games/{sno}/live`（含 records/batter_avg/has_tracking/tracking） |
| 紀錄室 | `/records`、`/records/championships`、`/records/postseason`、`/records/team`、`/records/earned-run-free-streak`（投手連續無**自責**分局數，見下） |

### 連續無自責分局數 contract（`/records/earned-run-free-streak`）

- **不是「連續無失分」**：失誤造成的非自責失分不中斷本指標。前端文案必須帶「自責」二字，
  回應的 `note` 是該說明的單一來源。實例：呂彥青 2026-07-26 時點無自責分 28.1 局、無失分僅 9.0 局。
- 自責分一律讀官方 `pitching_gamelog.earned_runs`，**專案不重建自責分**（規則 9.16 不可行，
  理由見 `docs/tasks/ML-PITCHER-SCORELESS1.md` 背景節）。本指標**完全不讀 `game_livelog`**。
- **只計例行賽局數**（`kinds_counted=['A']`，不用 `KIND_GROUPS`）；跨季時中間的季後賽出賽
  ER=0 跳過、ER>0 中斷，被跳過者列在 `skipped_postseason_games`。需求方裁定 2026-07-28，
  理由與實例見 `docs/research/ML-PITCHER-SCORELESS1_RESULTS.md` §1.6。
- 所有不確定一律往「中斷」解讀 → 回傳值是**下界**。口徑與保守性規則的單一來源是
  `src/cpbl/models/scoreless_streak.py` 的模組 docstring。
- **尾段走 `pigeonhole_tail_outs()`**：以官方逐局比分（`game_scoreboard`，取**對手打擊側**）
  界定「零得分後綴」，取鴿籠下界 `官方出局數 − 3 × 前綴局數`。故與投手更替、規則 5.10(d)
  再入賽、牽制出局皆無關。**採計前必驗逐局比分完整**：逐局總和須等於 `games` 的官方終場
  對手得分（官方對官方），不等即尾段 0——`game_scoreboard` 是逐列 UPSERT、無完整性
  constraint，缺一個得分局就會高估。**`score_cnt` 的 NULL 不得正規化為 0**（NULL＝這一局
  得幾分不知道，非 0 分；折成 0 會讓官方終場 0 分的比賽以 `0 == 0` 通過對帳），載入層保留
  `None`、見到即 fail-closed。`DATA_FROM_YEAR`（SQL ＋ 核心函式兩層）仍 enforce；
  `kind_code` 鎖 `^(A|D)$`。
- **尾段採計率低是方法邊界不是缺陷**：一軍 343 個尾段查詢只有 24 個（7%）採得到，因為
  官方逐局比分只知道某局有沒有得分、不知道那分是誰掉的（先發退場後後援掉分會吃掉整個
  後綴）。細節與實例見模組 docstring「方法邊界」節。
- **不要再用逐打席資料推導出局數歸屬**（七輪查核的結論）：`pitch_cnt` 與 `main_event_no`
  主序號**都不是列的唯一鍵**（68,372 組重複投球序號；2,457 個事件序號槽含多列，其中 204 個
  同時含換人列與比賽列），且不消耗投球的出局事件只以「列」存在——**列的缺席偵測不到**。
  任何「以看得見的量設界再證明資料完整」的修法都會被同一類反例打穿。
- **以棒球規則為前提前，先查 `docs/reference/棒球規則.txt`**：我曾自稱「投手換下後不得
  再入賽」，而 5.10(d) 原註明文允許 P→守備位置→P，整個設計因此作廢。
- 窮舉對帳：`uv run python scripts/reconcile_scoreless_streak.py`（全母體、零例外才 exit 0；
  改動演算法後必跑）。交付報告見 `docs/research/ML-PITCHER-SCORELESS1_RESULTS.md`。

### 投打對決查詢 contract

- `/players/roster`：帶 `role=batting|pitching&q=&season=&limit=` 時回有限筆 `items`；未帶
  `role` 暫保留舊 `/matchups` 頁需要的完整 `batters`／`pitchers` 雙名單。
- `/players/{id}/matchups`：`scope=career|season|range`；`range` 必帶 `from_year`＋
  `to_year`。可用 `opponent_team`（自動展開歷史 franchise 隊碼）、`opponent_id`、`limit`、
  `sort`、`order` 篩選。跨年只加總原始計數再重算 rate；無可加總分母的逐年百分比回 `null`。
- `/matchups?hitter=&pitcher=`：同樣支援 scope／年度與 `kind_code`，保留單組進階欄位。
- `year=9999` 是官網生涯彙總保留值。年度 scope 永不 fallback 到 9999；response 的 `coverage`
  會分開回報 `career` 與 `annual_years`。**啟用「本季／指定年度」UI 前必先完整執行
  `cpbl-scrape-fighting <year>` 並確認所有目標球員都有年度 coverage**，不可用單人抽樣資料上線。

---

## 6. 前端地圖（`web/`，Next.js 15 App Router + Tailwind v4 + recharts）

- 路由：`/`(戰績) `/predict`(賽果卡) `/players/[id]`(旗艦) `/games`+`/games/[sno]`(賽況狀態板) `/batters` `/pitchers` `/matchups`。
- 大頁採同目錄模組拆分：`players/[id]/` 的 `page.tsx` 只留 state+抓取+組裝，區塊 UI 在 `hero/season/tracking/trend/fielding/detail.tsx`、共用在 `lib.ts`/`parts.tsx`；`teams/[code]/` 同法（`parts.tsx`）。
- `lib/`：`client.ts`(Client fetch) `api.ts`(Server) `teams.ts`(隊色/字母徽章)。
- 元件：`game-board.tsx`(ESPN 狀態板) `spray-chart` `zone-scatter` `perf-heatmap` `la-ev-scatter` `leaderboard` `ui.tsx`(Card/StatTile/TeamLogo/PercentileBar)。
- 設計：日間 Navy+白；token 在 `globals.css @theme`；百分位藍↔紅發散。

---

## 7. 驗證與部署

### 7.1 多 AI 控制平面（remote coordination + local resource lock）

完整契約見 [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)。本機 Coordinator 為 **ruan6047**；未經使用者明確指派，AI 不得自行派工、認領或釋放其他卡。

- **Remote coordination**：GitHub protected `main` 與 Coordinator 是唯一 lifecycle writer。[`control-plane/events.jsonl`](control-plane/events.jsonl) 為 append-only event log；[`TASKS.md`](TASKS.md) 僅是由 `uv run python scripts/workflow_ledger.py --write` 產生的 current-state projection，禁止手改。
- **lifecycle 事件直接落 main（2026-07-17 起）**：claim／handoff／review／merge／release 事件不跟執行分支走，一律直接 commit 至 main 並在同 commit `--write` 重建 TASKS.md；執行分支不得改動 `docs/control-plane/**` 與 `docs/TASKS.md`，merge 時該路徑衝突以 main 為準。push 前 `git pull --rebase`。
- **Local resource lock**：鎖根目錄固定為 `/private/tmp/cpbl-analytics-control-plane`（不進 git）；`mkdir` 的原子成功／失敗只保護暫時資源，**不得改 card state**。每個 claim 目錄保存 `card_id`、owner、worktree、`claimed_at`、`lease_expires_at`、`resources`；預設 lease 4 小時，可續約。共享可寫資源須逐一宣告，例如 `file:<path>`、`port:<n>`、`container:<name>`、`db:local:cpbl`、`db:production:cpbl`。

```bash
# Coordinator：先確認 event projection、依賴、WIP 與無有效 owner，追加 claim event 後才建立 local lease。
mkdir -p /private/tmp/cpbl-analytics-control-plane
mkdir /private/tmp/cpbl-analytics-control-plane/<CARD_ID>  # 已存在即 claim 失敗，停止
# 建立 lease.json（不得含 secret），再建 worktree。
# worktree 位置統一（2026-07-17 起）：.claude/worktrees/<card_id小寫>-execution；
# 查核進駐副本用 <card_id小寫>-review[-rN]。鎖根目錄仍在 /private/tmp（鎖≠worktree）。
git -C ~/Dev/cpbl-analytics worktree add .claude/worktrees/<card_id小寫>-execution -b ai/<model>/<CARD_ID>

# claim／handoff／review／merge／release 前後：對帳所有活卡與 worktree。
git worktree list
find /private/tmp/cpbl-analytics-control-plane -mindepth 1 -maxdepth 1 -type d
uv run python scripts/workflow_ledger.py --check
uv run python scripts/workflow_ledger.py --live   # 稽核：union main 與所有 ai/* 分支頂端 event log；與 TASKS.md 不一致＝有事件違規漏留在分支

# 交付後要查核：從最新 handoff event + 卡片驗收條件自動產生查核提示詞（不必向執行者索取）
uv run python scripts/review_prompt.py <CARD_ID> | pbcopy
```

- 遠端 event 的 `state_version` 由 1 單調遞增；handoff、review、merge、release 必填 source SHA 與 evidence。`occurred_at` 取寫入當下系統時鐘（先 `date`，禁估算／沿用——WF-18）。逾期前可由 owner 續約；回收前 Coordinator 必須檢查 worktree 的未提交變更，禁止靜默刪除工作內容。
- **release 必以終態落地**（WF-18）：免部署卡 release 即 `🏁完成`、需部署卡 `✅已驗證` 後才 release；結案五步（終態事件→封存→Ledger→lease／分支清理→對帳）見 canonical [`worktree-lifecycle.md`](../.ai-workflow/templates/worktree-lifecycle.md)，代 Coordinator 結案的查核者同樣適用。
- **查核通過即 merge**（2026-07-25 起）：APPROVE 且零阻塞 finding 時 Coordinator 直接 merge，不再逐卡請示；merge 後把 merge_sha 與後續待辦回傳原執行者，由執行者向需求方確認部署。例外（blocking finding、需 rebase 重驗、`db_scope` 為 schema／data-migration、卡面要求 sign-off）仍須停下請示。全文見 [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)「交付→查核→合併慣例」。
- 同一卡族（原卡及 `<CARD_ID>-FIX<n>`）共用一個 worktree。merge 者在卡族全數結案後依序移除 worktree、刪本地分支、刪遠端分支。
- 對 DB 的 claim 另依 [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) 取得資源 lease；schema 與 data migration 不可並行。

### 7.2 測試與驗證

**push 前必過**（`CLAUDE.md` 驗證清單的事實層；實測基線 2026-07-26：pytest 479+ tests ~9s、web 165 tests ~0.3s）：

```bash
uv run ruff check                 # 後端 lint
uv run pytest                     # 後端（44 檔中 39 檔零 DB 依賴，整套 <10s）
cd web && npx tsc --noEmit        # 前端型別
cd web && npm test                # 前端契約測試（node:test + strip-types，零框架依賴）
# 改成績模型還要：容器內 cpbl-train 看回測對照表未退化
```

- **路由快照**：新增 API 端點須同步更新 `tests/test_route_snapshot.py` 的 EXPECTED。
- **bug 卡（T2 快線）**：修復測試必須先對缺陷版本**跑紅**再轉綠，紅證據記入交付（canonical §2 第 6 點；`bug-workflow.md`）。統計／ML 卡「先跑紅」不適用，改依卡面「紅線（違反即退回）」區塊驗證（canonical `statistical-redline.md`）。
- **新 worktree**：先 `cd web && npm install`，否則 tsc／npm test 全紅是缺 node_modules 假象非缺陷；後端 `uv run` 會自動建 venv。
- **CI**（`.github/workflows/ci.yml`）：api job 跑 ruff＋pytest，web job 跑 tsc＋npm test；CI 不部署（部署見 §7.3）。

**DB 契約測試（預設 skip，改對應 ingest 前必須手動實跑一次）**：

三個整合測試以 `skipif` 綁環境變數，未設即 skip——**CI 與日常 pytest 都不會執行**。動 `ingest/editorial.py`、`ingest/cpbl_advanced.py` 快照晉升／回收路徑或其 migration 時，照下列程序在 CARD_ID 隔離 database 實跑（依 [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md)；隔離名寫死在測試內，不可自訂）：

| 測試 | 環境變數 | 隔離 database 名（測試強制驗證） |
|---|---|---|
| `tests/test_editorial_ingest.py`（1 個整合） | `EDITORIAL_TEST_DATABASE_URL` | `cpbl_data_editorial1` |
| `tests/test_advanced_snapshot_schema.py`（2 個整合） | `ADV_SCHEMA_TEST_DATABASE_URL` | `cpbl_ingest_adv_expand1` |

```bash
docker compose up -d db   # 本機 PG（host port 5433）；在 worktree 內 compose 抓不到服務，改用容器名
docker exec cpbl-analytics-db-1 psql -U cpbl -d postgres -c "CREATE DATABASE cpbl_data_editorial1"
DATABASE_URL=postgresql://cpbl:cpbl@localhost:5433/cpbl_data_editorial1 \
  uv run python -c "from cpbl.db import migrate; print(len(migrate()),'migrations')"   # 先套 schema
EDITORIAL_TEST_DATABASE_URL=postgresql://cpbl:cpbl@localhost:5433/cpbl_data_editorial1 \
  uv run pytest tests/test_editorial_ingest.py -q
```

（advanced 同法：database 名換 `cpbl_ingest_adv_expand1`、env 換 `ADV_SCHEMA_TEST_DATABASE_URL`。實測 2026-07-26：editorial 16 passed、advanced 3 passed，皆含原 skip 的整合測試。用完可 `DROP DATABASE` 回收。）

**術語**：kind_code、island、幽靈島、GO/FO、保留賽等跨檔語意見 [`reference/GLOSSARY.md`](reference/GLOSSARY.md)，勿依單檔註解腦補。

### 7.3 部署 = push-to-deploy（在主站操作）
1. 本 repo：commit + push（CI 只跑 lint + tsc，**不部署**）。
2. 主站 `~/Dev/PersonalWebsite`：`apps/subprojects/cpbl-analytics` checkout 到新 commit → `git add` 該 submodule → commit（**只動 submodule 一行**，勿夾帶主站其他未提交變更，VPS 是 `git reset --hard origin/main`）→ push。
3. 主站 CI 成功 → `deploy.yml` 自動 SSH 到 VPS：`submodule update` + `docker compose -f docker-compose.prod.yml build/up` + 健康檢查 + nginx 重啟。約 12 分鐘（build 兩個映像）。
4. 監看：`gh run list --workflow Deploy`；驗證：`curl https://cpbl.ruan-ruan.com/api/info`。

> 純前端版面微調期間先不部署（見記憶 `no-deploy-during-layout-tweaks`），累積到滿意再一次上線。

---

## 8. 已知陷阱（踩過的，勿重蹈）

| 陷阱 | 事實 / 對策 |
|---|---|
| **VPS 來源邊界** | `www.cpbl.com.tw` 機房 IP 被擋，仍維持本機爬＋同步；stats 只有經 T4 核可且 exact allowlist 的隔離 observer／worker 可在 VPS 執行（§3），不可泛化為任意官網爬蟲。 |
| **爬蟲失敗連續重跑** | HiNet 節流會升級，症狀惡化。冷卻 15–20 分再單次重試；排查照 `CPBL_SITE_MAP.md` §5 |
| **「找不到 token」偶發** | 多半是挑戰未過（機率性），非官網改版；`page_html(require=)` 會自癒。冷卻後仍 100% 失敗才是改版 |
| **pitch_tracking 覆蓋不全** | 球場端設備，無設備球場(大巨蛋/亞太主/嘉義/花蓮/新莊)整場 0；官方有的指標一律用官方全季值，勿用逐球重算。記憶 `pitch-tracking-venue-coverage` |
| **pitch_tracking 含二軍** | 有 `kind_code='D'`；逐球查詢**必須加 `kind_code='A'`** |
| **pitch_tracking `pitcher_name` 亂碼** | 編碼問題；比對一律用 `*_acnt`，勿用 name |
| **衍生欄恆 NULL** | `ops_plus/era_plus/fip` DB 永遠 NULL，由 API 即時算。記憶 `derived-stats-computed-live` |
| **`team_current` 是當前半季口徑** | 存官網 `/standings/season` 頁預設範圍＝**當前半季**，勿當全年資料（TEAM-STYLE1 §4 實證：全季聚合對帳全 FAIL、`game_season_code='2'` 聚合 5/6 隊逐位吻合）。`batting_current`／`pitching_current` 已實證為**全年**；`fielding_current` 已排除半季（全年未逐值對帳）。四表口徑對照與證據見 [`reference/GLOSSARY.md`](reference/GLOSSARY.md)；全年團隊數據由 gamelog 聚合（先例 `/api/v1/season/team-split`） |
| **分項主鍵** | `*_splits` 主鍵含 `item_name`（mig 022）；前端分類用 item_name 內容非 group_code |
| **官網 token** | `/schedule` inline JS 抽 `RequestVerificationToken`，放 **header**；不是 hidden input 的 `__RequestVerificationToken`（會 500） |
| **前端 env** | **兩個都在用，不可互相取代**：`API_URL` → Server Component 取資料（`web/src/lib/api.ts:7`，全站 SSR 幾乎都走這支）；`NEXT_PUBLIC_API_URL` → 瀏覽器端（`web/src/lib/client.ts:5`，球員頁等 client component）。兩者預設皆 `http://localhost:4001`，故 **API 開在預設埠時兩個都不必設**；一旦改埠（例如同時跑兩個分支的 API）**必須兩個一起設**，只設一個會出現「SSR 拿到 A 的資料、client 拿到 B 的資料」或整區靜默空白。**此格原記「用 `NEXT_PUBLIC_API_URL`，`API_URL` 會連不到」是錯的**，已於 2026-08-02 更正——當時的誤記曾害人把非預設埠的 SSR 資料誤判為功能缺失。 |
| **同年多隊** | 球員一年多列(多 team_id)，季彙總查詢要 `GROUP BY player_id, year` 加總 |
| **build 污染 dev 快取** | `next build` 與 `next dev` 共用 `web/.next` → dev 跑著時跑 build，dev 讀到對不上的 `./NNN.js`／`Internal Server Error`。**已有 `prebuild` 守衛**（`web/scripts/guard-build.mjs`）：偵測 :3000 有 dev 就中止 `npm run build`。**驗證一律用 `npm run build:check`**（獨立 `.next-check`，守衛不擋、不影響 dev）。萬一仍中招：停 dev → `rm -rf web/.next` → 重啟 dev |

---

## 9. DB schema 重點（`cpbl`，migrations 001–022）

- season/ML：`*_seasons`、`projections`、`model_versions`。
- 歷史冠軍：`championships`（1990–2025 逐年官方來源＋franchise）→ `championship_members`（離線重建成員）。
- 逐場：`games`、`game_scoreboard`、`game_livelog`、`batting_gamelog`、`pitching_gamelog`、`game_features`。
- 當季累計：`batting_current`、`pitching_current`、`team_current`、`fielding_current`。**口徑不一致**：`team_current`＝當前半季，batting/pitching＝全年（fielding 已排除半季）——見 §8 陷阱與 [`reference/GLOSSARY.md`](reference/GLOSSARY.md)。
- 對戰/分項：`matchups`、`vs_team_splits`、`batting_splits`、`pitching_splits`。
- 進階：`advanced_stats`、`pitch_tracking`、`team_standings`、`refresh_log`。
- 慣例：無 ORM、psycopg3 參數化(`%s`)、走 `cpbl.db.conn()`；新 migration `00X_*.sql` 須 `IF NOT EXISTS`（migrate() 每次全跑）；player_id 10 碼字串對齊 opendata。
