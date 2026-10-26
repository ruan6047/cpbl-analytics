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

### pytest 證據位置

每次 `pytest` 都會輸出 `pytest location` 三行：絕對 cwd、Git HEAD 短 SHA 與分支名。
預設模式使用 pytest 標頭；`-q` 會隱藏 pytest 的標頭，故改由 terminal reporter 輸出相同內容。
審閱測試證據時，以 cwd 與 SHA 判讀實際受測 worktree；**不可用收集數或子模組狀態
推斷測試位置**。非 Git 目錄時，HEAD 會顯示 `unavailable`，分支顯示 `detached`。

| 場景 | DB | API | Web |
|---|---|---|---|
| **本機** | docker compose `db`（PG 17，**port 5433**） | `uvicorn cpbl.api.main:app --port 4001` | `web/` Next.js `:3000`（**兩個** env：`API_URL` 給 SSR、`NEXT_PUBLIC_API_URL` 給瀏覽器；預設皆 `:4001`） |
| **生產**（VPS Vultr `root@45.76.100.29`） | 容器 `prod_pg`（與主站共用，schema `cpbl`） | 容器 `prod_cpbl_api`（內網 `http://cpbl-api:4001`） | 容器 `prod_cpbl_web` |

- 本機設定：`cp .env.example .env`；關鍵鍵 `DATABASE_URL`（本機預設 `postgresql://cpbl:cpbl@localhost:5433/cpbl`）。
- 生產部署：主站 `docker-compose.prod.yml`；改 code → 在主站 bump submodule → push → 自動部署（見 §7）。

---

## 3. 資料流與「本機爬 → 同步生產」（重要）

<a id="architecture-reference"></a>

### 架構參考：已核版本、目標與現況差距（2026-10-25 文件整合）

本段是執行位置、資料流與直接依賴的主要架構落點；元件／目錄、現役與保留模型及主站介面仍引用 [`AGENTS.md`](../AGENTS.md)「核心定位與邊界」「專案結構」「賽果預測 — 現役模型與舊互動探索器」「子專案契約」，DB 技術與寫入安全沿 [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) §1 及其直接相關段落，不另建架構總綱或假稱 DB 契約已有下述發布新條文。

**來源與效力**：需求目標沿 [ROADMAP 的 2026-10-24／25 本次對話確認集合](ROADMAP.md#confirmed-direction-20261025)，本次沒有 Issue／新的 GitHub 裁定留言，文檔採納待本固定版本審核。以下技術摘要沿用 10/24 已存的指定來源讀碼、依賴盤點、全晚門檻／歷史保存核對及正式有限觀測，非 10/25 新查正式機。來源版本與程式定位一併保留，既有各卡裁定／已接受證據／#358 擱置不變；本段不授權取源、寫入、安裝、搬移、改排程或部署。

| 證據基準 | 可聲稱的範圍／限制 |
|---|---|
| 本機 CPBL `906ba269b53a6d74f948078564bcbec70ca5b6ba` | 以下 C／D 串接、讀端與資料依賴的讀碼基準，不代表正式運行逐行相同。本次隔離文件分支取得官方 main 仍為此版。 |
| 主站本機 HEAD `0ba058ece432f0fc1e7eef99da0b1c0a2a9e4e3b`、CPBL 子模組指標 [gitlink] `00a4f48825ae2f4c2c69ea060f12ddea9bba1b1d` | 主站設定與部署來源定位；主站 SHA 不是 CPBL SHA，也不是正式部署證明。 |
| 正式有限觀測：2026-10-24 台北 23:11–23:12，主站 `e08218a7`、CPBL gitlink／repo HEAD `ddc29a79` | 未核映像內原始碼雜湊與 repo HEAD 等同。當時篩到 API／web／worker／Redis／nginx running/healthy；6 項有界唯讀 SELECT 共 17 列，只證指定 metadata 可讀，不證全表完整或所有 PG 容器健康。 |

#### 已核版本的執行位置與資料流

```mermaid
flowchart LR
  M["Mac：launchd／每日與晚間入口"] --> WWW["www 瀏覽器取得"]
  WWW --> B["本機 DB 與計算"]
  OD["歷史 cpbl-opendata／backfill"] --> B
  O["Mac：有限公告 owner／stats HTTP"] --> B
  B --> S["有限或完整資料同步"] --> D["正式 PG"]
  W["正式 stats live worker"] --> R["Redis 快照"]
  D --> A["正式 API"]
  R --> A
  A --> V["web／公開讀端"]
  S -->|"依模式／訓練條件"| T["API 容器內模型訓練"]
```

圖是已盤點版本的責任映射，非唯一寫入順序；原一般表／局部原子群組不可讀成全庫同一交易。下方原操作段落與命令繼續保留適用政策，舊整庫 dump 圖不作為所有現行同步模式的描述。

| 執行位置／既有單元 | 直接來源定位與資料流 | 已知限制 |
|---|---|---|
| Mac 觸發、取源、本機 DB | `scripts/com.cpbl.scrape-daily.plist` → `scripts/scrape-daily.sh`；`ops/launchd/com.cpbl.postseason-evening.plist` → `scripts/postseason-evening.sh`，另有 weekly plist；www 經 `src/cpbl/ingest/_browser.py`。 | plist 存在不證今天已安裝／運行；本機取得與計算是已盤點的 Mac 依賴。 |
| Mac 有限公告 owner | `config/launchd/com.cpbl.lineup-announcements.plist`、`src/cpbl/ingest/run_live_game_worker.py` 額外保存／同步模式；stats HTTP JSON → E／C 公告 → 有限同步。 | 模式限制本機 DB／Redis，未證正式 worker 已開公告 owner；HTTP 取得不等於歷史保存已脫 Mac。 |
| 正式供應與賽中 worker | 主站 `docker-compose.prod.yml` 的 API／web、共享 PG／Redis、模型持久卷及 `cpbl-live-worker`；`run_live_game_worker.py` → `live_game_worker.py` 的 StatsLiveSource → Redis；API／web 依 DB／快取契約讀取。 | worker 健康不證本次來源成功；Redis 快照不等於正式 PA／季累計已更新，未核所有容器／整庫。 |
| 本機計算／同步與正式讀端 | `src/cpbl/ingest/run_refresh_recent.py`、`pa_build.py` → `scripts/refresh-cpbl-prod.sh` → 正式；`src/cpbl/api/routers/games.py`、`web/src/lib/live-game.ts` 消費 DB／published／映射及快照。 | 原始列存在、正式可讀及整鏈成功分開；本機版本不能冒稱正式 `ddc29a79` 映像逐行已驗。 |
| 模型與主站部署交界 | 同步腳本在 API 容器內訓練；主站 `.github/workflows/deploy.yml` 載入映像並套用 compose，可能重建 API／worker，另重建 nginx。部署操作仍見本檔 §7.3。 | 不是已證獨立 trainer 服務；持久卷不會自動續跑被重建終止的程序。CPBL CI／merge、主站部署、資料同步是不同事實與授權。 |

**有限可行性觀測**：10/24 普通 VPS stats 單場 GET 得 403 後即停；www 首頁 200 不證完整資料取得或瀏覽器路徑可行，API／worker 未裝 Playwright／Chromium。來源網路／IP／CDN 與容量是兩軸，升規格不解前者；403 不證永久封鎖，200 不證全鏈成功。既有短容量樣本只見記憶體／swap 壓力及有限磁碟餘量，未量 Chromium／訓練峰值，不能證必須擴容或現資源必足。未新量容量或查 worker 來源成功日誌；HostConfig 的局部觀測也不能推論所有層都沒有資源隔離，現有安全暫停／續跑能力尚未證實。

#### 局部一致性、逐場發布與現行耦合

| 資料群／現行安排 | 必須成立的條件與精確界線 |
|---|---|
| PA 家族與逐球映射 | 來源修訂／build／PA／映射及 published build 相容；現有五表家族與目標場 PA 同步有局部原子契約。原始逐球可先存在，無精確映射不能假稱已配對；不是所有 raw tracking、所有場次及全部讀端同一交易。讀碼定位：`pa_build.py:1695–1704,1897–1918`、`refresh-cpbl-prod.sh:580–637,1006–1041`。 |
| 進階快照 | 父 run、三類資料與 state/current_run_id 共五表，先資料後指標指向 [pointer]、同交易保持外鍵與可見性；只限該來源 run 範圍。季別／排行榜 run 不能因單場 final 晉升為單場累計，未證所有進階資料有逐場快照。定位：`refresh-cpbl-prod.sh:541–577,1266–1268`。 |
| 正式比分／基本 box、季累計／戰績 | 場次、來源範圍、可靠完賽 [final] 與必要欄位齊備；0:0 不靠比分猜完賽，保留未完成不當終場或併累計。季累計需可信完賽集合及必要跨場基準，不能以 Redis 有比分代替官方累計已更新。一般表逐表提交，不是整場／全庫同交易。 |
| 衍生指標 | 同指標來源／時點相容；守備局數直接影響捕手 RA9，traits／RE24 等已有局部容錯，成功表可保留；不宣稱全部綁死、全部能單場增量或都須逐球重算。定位：`src/cpbl/models/sabr.py:810–872`、`run_refresh_recent.py:1120–1147,1185–1200`。 |
| 特徵／同步／訓練與成功標記 | 本機 C 在 `RUN_OUTCOME=1` 時將 features 建置放完整同步前，D 在同步後遠端訓練再到 freshness/prod-sync 與整鏈 sync_ok；light／sync_only 已可跳訓練。失敗可能阻同步或只截斷同步後標記，不能一概說資料未寫；成功亦不證每欄齊全。定位：`refresh-cpbl-prod.sh:1048–1088,1111–1175,1231–1241,1303–1395`。 |

**全晚門檻 [gate] 的原目的保留**：A 的全季取得＋games 整表同步＋舊 A 完賽讀端交互作用，可能把其他仍進行中場次的部分比分當完賽。因此原卡在不改共享判準／API／前端／同步範圍下接受先結束者延後，保留場交隔日；E／C 與 stats 不一律受此 gate，這也不證官網只能全晚發布。原來源：[#343 Q1](https://github.com/ruan6047/cpbl-analytics/issues/343#issuecomment-6361673244)、[保留分支](https://github.com/ruan6047/cpbl-analytics/issues/343#issuecomment-6362085657)；本機定位 `src/cpbl/ingest/postseason_evening.py:493–527,1341–1375,1707–1735,2114–2118`。本輪不接管 #365 或撤銷原接受取捨。

逐場已齊先提供是已確認目標：**場次／來源／時間 → 該群條件（正式賽果／季累計依可靠 final） → 必要計算與群組就緒 → 對外一致可讀**，不是唯一程式寫入順序，必要賽中快照不等 final。取得範圍、寫入範圍與讀端完賽判定須共同維持等價防污染保護，不能只刪 gate、換觸發或改成功標記；單場與跨場摘要對同場完賽事實／可用範圍一致，不要求全局同交易。無直接相依者先供，未齊短標「待更新」；有效相容前版可保留並標時點，但未證已有自動替代機制。官方修訂影響 mapping／指標時，須維持相依重算及局部發布契約，具體觸發方法仍待規劃。

#### 已確認的五項目標責任（尚未整體落地）

這是邏輯責任，不是現有五個服務、固定容器或新 writer 制度；與上表既有單元對照，不把目標當目前已接線。

| 責任 | 已確認目標與真正等待條件 |
|---|---|
| 取得／保存 | 辨別來源、場次、取得／實際發布時點及修訂，保存必要依據與原看點；官方名單後才指定對決。缺一來源只影響直接相依內容，不以舊資料冒稱最新；不新增任意遠端 crawler 權限。 |
| 計算 | 以相容輸入／時點／場次範圍計算，缺輸入只停直接相依結果；正式累計依可靠完賽。必要賽中／單場計算不一律等無賽日或 10:10，讀取需求不等於所有衍生逐球重算。 |
| 發布 | 該群必要資料、published 版本／映射與局部原子群組就緒後，確認對外實際可讀；未齊不拖無關有效成果，核心發布不等模型特徵或重訓。 |
| 賽中讀取 | API／web 從可用 DB／快取提供可信賽況與已支持分析，不等待整批取得／重算／模型；有效舊資料標時點／過期，無有效資料如實缺項，readiness 不證完整或全部新鮮。 |
| 輔助模型 | 例行重訓／回測與版本評估有需要時放休戰日，賽前必要特徵更新及有效相容模型推論獨立處理；連續有賽可沿用相容有效模型，不要求每個休戰日重訓。失效／不相容如實標未更新或暫不供預測，不拖核心資料；現有同步耦合仍待調整。 |

**橫向目標與未選方法**：賽前、賽中、賽後及 10:10 所需取得、計算、同步與發布都不依賴個人 Mac 開機、連網或人工維持，優先集中現有正式主機、必要時擴容，外部非個人取源為條件式備選。10:10 以晚發布、補漏、更正、相依重算與對帳為目標，現鏈仍有首度取得責任，不能現在停掉。部署重建與正在取得／計算／寫入的生命週期分開，維持 §7.3 原操作及授權。儲存／schema／queue、新服務、CLI／狀態平台、觸發時刻／計算頻率、CPU／RAM 配額與退讓方式未選定；必要核心修復／補校不一律低優先，同機分程序／容器不自動保證隔離，不以未證安全暫停／續跑推論能力不存在。

<a id="history-retention-target"></a>

#### 已確認的保存與歷史時間口徑（方法待規劃）

需求方 2026-10-25 確認：對外發布時保留當時內容及可還原必要依據，事後重算作補充、不取代原稿；已發布看點與必要依據隨該場歷史頁服務保留，不先定固定年限。包括正式打線前兩隊近況及確認名單後對決，可有多個時點版本，不指定版本數或每場全庫快照。

| 最低內容集合 | 保留或可可靠連回的內容 |
|---|---|
| 場次與分析範圍 | game 身分、賽別／類型、目標時點、截止場次及實際樣本，不混後續出賽。 |
| 實際發布成果 | 原看點／結構化重點、必要視覺資料、重點數值與當時缺項說明，不要求截整頁。 |
| 時間與來源版本 | 來源觀測、內容產生、實際發布時點與來源引用／版本；觀測不是官方公布時間。 |
| 必要輸入與方法 | 實際用到的輸入、統計範圍、方法／規則版本；不可變來源的引用實體仍可還原才可只連回，若會覆寫須保存必要值。只保存實際參與該看點的模型版本，不讓模型訓練成所有內容前置。 |
| 修訂與結果對照 | 原稿／依據與後續更正、重算及實際結果的關聯；不以事後資訊覆寫原判斷，也不把已知錯誤當最新事實。 |

被引用來源實體須隨必要依據可用，不能被短期 raw／中間物清理破壞還原；頁面暫隱或改版不等於底層可刪。這不等於全部 raw 永久保存、永不清理或零成本；未被引用且不影響還原／既有證據的中間物、重複取得與操作 log，保留期及清理條件仍待規劃。保存、公開展示與備份分責，不宣稱已具可還原備份。

**既有保存缺口仍在**：S09 看點快照已停，完賽讀端不支援歷史，不證所有歷史皆不存在；有限 E／C 公告投影、賽程歷程、PA build／manifest 與投手 box 修訂只證啟用後有限內容。上述正式 17 列僅含 E4 兩筆 START 公告片段、有限賽程、A285 一個 published build 及投打 facts 存在，不證原賽前保存、完整窗口或全部歷史時點可重建。raw 可覆寫、僅引用 ID 不一定可還原，Redis 48h 快取／覆寫鍵及 first/last seen 不等歷史封存；搬 host 或保留卷不會補回未存原判斷。按場次截止用目前修訂資料重算不等「當時已知版本」；缺原看點仍可做有依據回顧、短標限制，不事後補造原稿。

#### 以下既有操作的適用界線

本段目標未替代原只能本機取源、有限來源允許範圍、寫入安全、全晚門檻或 10:10 操作；以下命令未因本次文件整合改動。原 2026-06 網路結果保留當時效力，不當永久不可取代證明。§1 的舊即時訓練描述與 AGENTS 現役離線模型不同，§7.1 舊控制平面亦不作現行指示，模型與流程依 AGENTS／已安裝 wfx 及各卡正式來源；遇實質衝突先停受影響操作並回報，不從舊描述自行推權限。

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
  （適用範圍：本條指 **stats 單場 API 的 `Pitchers[]`／`RoleType`** 不得倒推先發；官網 www
  getgamedatas 的官方先發欄位 `HomePitcherAcnt`／`VisitingPitcherAcnt` 是另一來源，賽前送達見 §10
  〈先發查核時點〉，#292 S11。）
- final 後 TrackMan 可能延遲（2026-07-26 A-224／225 完賽當下仍 0），0 筆只標 pending。
- 觀測矩陣與 canary evidence：[`research/LIVE_GAME_BACKEND1_OBSERVATION.md`](research/LIVE_GAME_BACKEND1_OBSERVATION.md)。

### 有限先發打線公告保存（#238；預設關閉）

`cpbl-live-worker --persist-announcements` 在既有 stats 單場回應後，將 **2026 E/C** 的公告投影保存至 `cpbl.game_lineup_announcement_revisions`。它不增加資料請求、不補造歷史公告、不用完賽 box 倒填；一般 worker 不帶此旗標時保持原 Redis 更新行為。啟用前須完成 migration 074，並確認本機 DB／Redis 的單 writer 與資源窗口；不是在 production 開啟新的採集 writer。

```bash
# 必須在已授本機採集／DB／Redis窗口內；單 cycle 的公告寫入失敗會 exit 1。
uv run cpbl-live-worker --once --persist-announcements
# 必須在已授 backup／schema／production DML 窗口內；僅同步公告表。
LINEUP_ONLY=1 SKIP_SCRAPE=1 ./scripts/refresh-cpbl-prod.sh
```

內容或官方狀態改變會追加版本片段；同片段重觀測只延長 `last_seen_at`，自然鍵衝突不能覆寫既有原證。有限同步沿既有 production 備份與 migration 入口，於單一交易以自然鍵追加並合併較晚的 `last_seen_at`；不爬取、不同步其他資料表、不重建特徵或訓練，也不宣告整條 freshness 更新成功。對同自然鍵不同原證會整筆回滾。

報告 GET 只讀已保存版本；表尚未部署、無正面賽前證據、公告撤回／不完整、來源時間不確定時保持「未核」。已開始後的資料不能倒填先發公告；九人名單與正式完整母體是不同證據。這個模式不會恢復原本未保存的歷史。

### 季後 32 人資格名單（#284 S03；手動、需授權）

官方 32 人名單由需求方整理成 PRD v2「輸入格式」（[`design/PLAYOFFS_PRD_V2.md`](design/PLAYOFFS_PRD_V2.md)「名單解析與不可變提交」）後，在本機以 `cpbl-roster` 提交；它是三表 `series_roster`／`series_roster_member`／`roster_annotation_revision`（migration 076）唯一的會員 writer。正式站不建提交端點。

```bash
# 寫本機共享 cpbl 前須另登記資源租用；真實名單提交前由需求方人工核對 preview 的 32 人身份與官方來源（P3）。
uv run cpbl-roster preview roster.txt                       # 唯讀；草稿／規則違反非零退出、不寫 DB
uv run cpbl-roster submit roster.txt --confirm-hash <preview 的 membership_hash>
uv run cpbl-roster annotate roster.txt                      # 只改戰術角色，另存新版；會員不動
uv run cpbl-roster show --year 2026 --series C --team ACN011
```

#316多重角色使用獨立`roles-v2` JSON package，舊文字單值輸入保留。核准表與manifest不覆寫；姓名／ID／官方守位須在已提交會員內唯一核對，兩隊各32列，會員／來源hash完全相同。package包含預期最新版/hash及逐角色來源；角色固定順序只供序列化，不分主次。正式寫入前另依資源與唯一writer窗口核准，不把本機預覽當正式資料已更新。

```bash
uv run cpbl-roster preview approved-roles-v2.json --format roles-v2 --json --out role-preview.json
uv run cpbl-roster annotate approved-roles-v2.json --format roles-v2 --confirm-approval-hash <核准表SHA-256>
# 回復前以prewrite完整快照核對兩隊基準，package的expected版/hash須反映目前最新。
uv run cpbl-roster annotate restore-input.json --format roles-v2 --confirm-approval-hash <核准表SHA-256> \
  --restore-version <roster_id1>:<prewrite版本1> --restore-version <roster_id2>:<prewrite版本2>
```

v2在同一交易鎖兩隊後追加；任一隊失敗全rollback，同內容重送unchanged。`show`同時回annotation_version／role_format_version／revision_hash與完整陣列。資料回復只能追加完整v1/v2版本，再走名單專用同步對帳，之後才退程式；不可刪歷史、關閉不可變守衛或down migration。v1 hash與會員／來源hash不變。API v2舊scalar固定null，所有本專案消費端使用角色陣列；外部scalar消費者不等同支援多重角色。

`cpbl.rosters.sync`含v2歷史時要求兩次明確`--scope YEAR:KIND:TEAM`；plan／apply／reconcile必須使用同一兩隊allowlist。scoped模式只准兩端既有名單追加revision，交易內再驗scope，不插入會員或名單頭；未知格式／缺角色欄拒絕。正式入口仍只有ROSTER_ONLY鏈，不能用模組直接對正式寫入。入口以`ROSTER_SCOPES=2026:C:AAA011,2026:C:ACN011`明示兩隊，搭配`ROSTER_ONLY=1 SKIP_SCRAPE=1 BACKUP_DIR=<獨立絕對路徑>`；此變數只在該模式使用，其他模式維持原行為。plan的schema預檢不過回69，在備份與寫入前停止，不由同步執行migration；apply內部事後對帳沿用同一allowlist。

- **不可變**：每 (year, series, team) 一份；三表 UPDATE／DELETE／TRUNCATE 由觸發器拒絕，sync_table 式 `ON CONFLICT DO UPDATE` 也會被擋；每份恰 32 人由延遲約束在提交時保證。同內容重送回原 `roster_id`、不重算提交時間；不同內容拒絕並列差異。錯匯⛔ 不 routine 修改：停止對外宣稱已核，交需求方例外裁定、另卡處理。
- **身分**：`@id=` 或同年同隊（team_roster／一軍出賽／已提交名單）範圍內唯一精確姓名才解析；⛔ 不模糊比對、⛔ 不創假 ID。外籍三態：`players.country` 缺＝身分未知，不猜成本土，摘要標「外籍資格檢查不完整」；已核洋將 > 3 拒絕。參賽隊只驗 team_dim 存在，系列參賽資格需人工確認（S02 契約未核定）。
- **資格≠可用**：名單與角色不代表先發、當場 28 人登錄或可用；`show` 的本季 A 出賽以 LEFT JOIN 取得，沒有就是「無」，不是 0。
- **生產同步**：只走獨立 insert-only 路徑 `cpbl.rosters.sync`（先唯讀比對：無變更不備份不寫、內容不同 exit 70 拒絕不重試；有待插入才備份＋單交易插入＋事後雜湊對帳）。⛔ 不進 sync_table 清單、⛔ 不掛每日鏈；schema 只隨部署窗口套用（同步本身不 migrate）。每次同步須另取需求方授權。生產入口只有 `ROSTER_ONLY=1 SKIP_SCRAPE=1 BACKUP_DIR=<非每日預設的獨立目錄，絕對路徑> scripts/refresh-cpbl-prod.sh`（#284 T2；mock 證據 `tests/test_roster_only_mode.py`），⛔ 不得改用其他方式對生產執行。

**每日刷新現況（最後驗證 2026-07-19）**：本機 launchd 10:10 已成功完成爬取與 production 同步（`sync_ok=true`）。仍必須每天以 `refresh_status.py check --scheduled` 檢查；成功同步不等於資料語意正確——目前 `BUG-HELD-GAME-FRESHNESS1` 已證實未完成保留賽會污染 `last_game_date`，修復前不得僅以 freshness gate 判定資料正確。

### 本機每日爬取（launchd 每日 10:10；手動為 fallback）

launchd 在使用者登入態每日 **10:10** 觸發 `scripts/scrape-daily.sh`；腳本先寫
`state=running`，本機爬成功後才備份並同步 production。每日鏈（非 `fast`）另會整季重算
球種推算（v1＋v2，一二軍；2026-09-23 起），失敗記為退出碼 69（其餘照跑、仍會同步）。**時段紅線**：勿改到深夜／凌晨，
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

**安裝現況**（2026-09-23）：**已安裝並運行**——2026-09-20 裝上、09-21 首次排程觸發；需求方
09-23 決定保留，`scripts/schedule-registry.json` 的 `expected_installed` 已改為 `true`（原本是
#53 Phase A「交付碼與 plist 但不安裝」的刻意邊界）。忙碌跳過時 **exit 75**（不是 0，launchd
才分得出跳過與成功）；每次執行寫 `logs/schedule-history/com.cpbl.weekly-game-pitches.jsonl`，
供 `schedule_watch.py` 判缺席。

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
| `cpbl-roster {preview,submit,annotate,show,import-official-population}` | 季後 32 人資格名單：解析→預覽→帶 `--confirm-hash` 的單交易提交；**insert-only、提交後不可變**（不是 UPSERT） | 需求方貼官方名單後（見 §3「季後 32 人資格名單」） |
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

- **新任務入口**：GitHub Issue＋[user Project #10「cpbl-analytics vNext 任務看板」](https://github.com/users/ruan6047/projects/10)（`.wf/config.json`）；開卡／關卡由 PM 以 `gh` 執行。在本 repo 工作樹內直接用 `wfx` 獨立 venv 的 console script 取當下規則（不依賴 PATH；venv 不在 `~/.venvs/wfx` 就換成你的位置；該檔不存在依下方安裝段排查，`python -m wfx` 只作診斷；自動注入 `.wf/*.md`）：`"$HOME/.venvs/wfx/bin/wfx" --project-root "$(git rev-parse --show-toplevel)" brief --task 193 --role 執行者 --stage 執行`（Issue 號、角色、階段依任務替換，值域見 `wfx/rules/core/values.md`）。`wfx` 只提供 `brief`／`facts`／`write`（`write` 須依 `facts` 基準寫入），⛔ 不開卡／關卡。改動共享資源（本機 DB、服務、排程、既有 worktree）須依 vNext 規則取得資源租用。
- **舊卡凍結**：Project #4 舊卡已凍結——停止舊流程派工與 `wfcli` 寫入，後續逐張研究、承接或判定無需續做後才關閉。本節下方「⛔ 歷史唯讀」標記以下的 `wfcli`／Project #4／claim／lease 程序只供歷史查閱，⛔ 不得執行。
- **`wfx` 安裝（獨立環境）**：`wfx` 是 wheel `ai-workflow-vnext`（採用驗證版本 0.1.0，`requires-python >=3.14`），裝進**獨立的 Python 3.14 venv**；本專案 `uv` 環境維持 Python 3.12（`.python-version`），⛔ 不把 `wfx` 裝進本專案 `.venv`。⛔ 不以 `PYTHONPATH` 指向來源樹或來源樹 egg-info 充當安裝——必須是 `pip install` 該 wheel。安裝步驟以 wheel 內附的 `wfx/docs/ADOPTION.md` §1 為準：

  ```bash
  WFX_VENV="$HOME/.venvs/wfx"                              # 任選 repo 外的固定位置
  WFX_WHEEL="ai_workflow_vnext-0.1.0-py3-none-any.whl"     # 取得的 wheel 檔路徑
  python3.14 -m venv "$WFX_VENV"
  "$WFX_VENV/bin/python" -m pip install "$WFX_WHEEL"
  ls -l "$WFX_VENV/bin/wfx"                                # 安裝驗證：console script 必須存在
  "$WFX_VENV/bin/wfx" --project-root "$(git rev-parse --show-toplevel)" facts --adopt   # 採用檢查（不依賴 PATH）
  ```

  `command -v wfx` 為空但 `$WFX_VENV/bin/wfx` 存在＝只是 PATH 未設定（可 `source "$WFX_VENV/bin/activate"`），不是安裝缺陷；`$WFX_VENV/bin/wfx` 不存在才是安裝不完整，排查見 `wfx/docs/ADOPTION.md` §1。

> **⛔ 歷史唯讀（至 §7.2 前）**：以下為 Project #4 舊流程程序（`wfcli`、claim／lease、Ledger、`review_prompt.py`，契約見 [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)），已隨舊卡凍結停用，只供歷史查閱。舊制度的 Coordinator 規則（本機 Coordinator 為 ruan6047；未經使用者明確指派，AI 不得自行派工、認領或釋放其他卡）僅適用舊卡；vNext 下 PM 已獲授權管理流程與選卡。

- **Remote coordination（既有舊卡）**：舊卡 current-state 的唯一事實來源是 GitHub Issues＋[user Project #4「cpbl-analytics 任務看板」](https://github.com/users/ruan6047/projects/4)；Issue timeline 的結構化 comment 是 lifecycle 留痕。狀態寫入只可經 PM 祕書的 `wfcli`，不得直接改 GitHub UI。[`control-plane/events.jsonl`](control-plane/events.jsonl) 與 [`TASKS.md`](TASKS.md) 已於 cutover 封存唯讀，僅供歷史稽核。
- **lifecycle 寫入與分支（cutover 後）**：claim／handoff／review／merge／release 由 `wfcli` 寫入 Issue／Project，不跟執行分支走；執行分支不得改動 `docs/control-plane/**` 或封存的 `docs/TASKS.md`。merge 時這些路徑衝突以 main 為準；push 前使用 `git pull --ff-only`。
- **Local resource lock**：鎖根目錄固定為 `/private/tmp/cpbl-analytics-control-plane`（不進 git）；`mkdir` 的原子成功／失敗只保護暫時資源，**不得改 card state**。每個 claim 目錄保存 `card_id`、owner、worktree、`claimed_at`、`lease_expires_at`、`resources`；預設 lease 4 小時，可續約。共享可寫資源須逐一宣告，例如 `file:<path>`、`port:<n>`、`container:<name>`、`db:local:schema`、`db:production:schema`。

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
# ⚠️ 2026-08-17 起【僅服務 2026-08-04 cutover 之前的卡】——見下方警示，新卡跑它會得到錯誤答案
uv run python scripts/review_prompt.py <CARD_ID> | pbcopy
```

> ⚠️ **`review_prompt.py` 對 cutover 後的卡失效，而且是靜默的。** 它讀 `docs/control-plane/events.jsonl`，
> 而該檔已於 2026-08-04（`8271d7c`）宣告封存唯讀；此後的 handoff 由 `wfcli` 寫進 GitHub Issue，
> **不進那個檔**。對新卡執行它會回報「尚未交付查核——查無任何 handoff event」，**那是工具讀錯地方，
> 不是卡沒交付**。實測：`ML-UMP2`（cutover 前）正常運作並正確拒絕；`WP-DISCLOSURE-SYNC1` 與
> `OPS-SCHEDULE-FAILURE-BLIND1`（cutover 後）皆誤報查無 handoff。
>
> **新卡的派審詞目前只能手寫。** 這不是慣例而是缺口——根治見
> [`ai-workflow#66 WF-DISPATCH-FROM-HANDOFF1`](https://github.com/ruan6047/ai-workflow/issues/66)
> （核心痛點即「handoff 與手寫派審詞雙來源必然漂移」）。本註記只是止血。
>
> ⚠️ 這個缺口從 cutover 到 2026-08-17 無人發現，因為期間沒有人跑過這支被指定「就是給你跑的」工具。

- 遠端 event 的 `state_version` 由 1 單調遞增；handoff、review、merge、release 必填 source SHA 與 evidence。`occurred_at` 取寫入當下系統時鐘（先 `date`，禁估算／沿用——WF-18）。逾期前可由 owner 續約；回收前 Coordinator 必須檢查 worktree 的未提交變更，禁止靜默刪除工作內容。
- **release 必以終態落地**（WF-18）：免部署卡 release 即 `🏁完成`、需部署卡 `✅已驗證` 後才 release；結案五步（終態事件→封存→Ledger→lease／分支清理→對帳）見舊 canonical [`worktree-lifecycle.md` @ `f207d2e`](https://github.com/ruan6047/ai-workflow/blob/f207d2ecf80556d6b90beeb0438bf648288a5fd9/templates/worktree-lifecycle.md)，代 Coordinator 結案的查核者同樣適用。
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
- **bug 修復**：修復測試必須先對缺陷版本**跑紅**再轉綠，紅證據記入交付。統計／ML 變更「先跑紅」不適用，改依規劃寫明的紅線（違反即退回）驗證。
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

### 7.2.1 合併到 main（required check 已生效，2026-08-22）

main 有 ruleset `main must be green`（id `21194141`），required context 是 **`api` 與 `web` 兩個**。
`bypass_actors` 為空、`current_user_can_bypass` 為 never——**沒有人可以繞過，包含需求方**。

⚠️ 該 ruleset 另帶 `strict_required_status_checks_policy: true`（要求分支與 base 同步），
但**在下面這條 ff-only 程序上它構造上碰不到**：分支若落後，`git push` 會先被 git 自己以
`non-fast-forward` 擋下（實測 2026-08-22，`remote:` 的規則訊息完全沒出現）；分支若不落後，
strict 的條件本來就成立。⇒ **它只在走 PR merge 時才有作用，而本程序不走那條。**
⛔ 不要把它讀成「本流程多了一道保護」。

**⛔ 沒有那兩個綠 check 的 commit 推不上 main。** 三個方向皆實測（2026-08-22）：

| 情形 | 遠端回應 |
|---|---|
| 該 commit 上沒有 check | `- 2 of 2 required status checks are expected.` → 拒絕 |
| 有 check 但紅 | `- Required status check "api" is failing.` → 拒絕（SHA `451a86de5bea425a438de4214a40157bb61662e5`，[run 32569531859](https://github.com/ruan6047/cpbl-analytics/actions/runs/32569531859)；該 SHA 的 check-runs 至今仍是 `api = failure`） |
| 兩個都綠 | 推得上去 |

**⚠️ 分支頭的 check 名字不是 required 的名字。** `ci.yml` 的 name 表達式讓分支 push 產出的是
`api (branch head)` / `web (branch head)`；不帶後綴的 `api` / `web` **只由 `pull_request` 事件與
main push 產生**。⇒ **不開 PR 就永遠拿不到 required 的名字。**

#### 合併程序（需求方 2026-08-22 裁定採此案）

⚠️ **本程序全程不 `checkout main`**，因為本專案是多 worktree 實況、主 checkout 已佔用
`main`——在 feature worktree 執行 `git checkout main` 逐字得
`fatal: 'main' is already used by worktree at '/Users/ruanruan/Dev/cpbl-analytics'`。
⛔ **早期版本寫的 `checkout main` + `merge --ff-only` 在本 repo 從來就跑不起來**，那是憑
記憶寫的、不是實跑序列。下面每一步都已逐一實測，證據見本節末。

```bash
set -euo pipefail   # ⛔ 少了它，第 1、2 步失敗後仍會往下跑，第 3 步就對「過期 SHA」判綠

REPO=ruan6047/cpbl-analytics
BRANCH="<branch>"   # ⚠️ 佔位符必須留引號，否則 < 會被當成重導向
# ⛔ 這裡刻意沒有 PR=<N>：PR 編號由分支反查，見第 5 步

# 1. 分支 push → 產生 api (branch head) / web (branch head)
git push origin "$BRANCH"

# 2. 開 PR → pull_request run 把 api / web 掛上「分支頭 SHA」
#    （實測：merge ref 的 check-runs 是空的，所以掛的是分支頭不是 merge ref）
#    ⚠️ --fill 不可省：非互動下逐字得
#    `must provide --title and --body (or --fill ...) when not running interactively`
gh pr create --base main --head "$BRANCH" --fill

# 3. ⭐ 機械驗證兩個 required 都綠——⛔ 不是印出來讓人讀
SHA=$(git rev-parse "$BRANCH")
GREEN=$(gh api "repos/$REPO/commits/$SHA/check-runs" --jq '
  [.check_runs[] | select(.name=="api" or .name=="web")] as $r
  | (($r | map(.name) | unique) == ["api","web"])
    and ($r | map(.conclusion == "success") | all)')
if [ "$GREEN" != "true" ]; then echo "⛔ required check 未全綠，停"; exit 1; fi

# 4. ⭐ refspec push——不需 checkout main，多 worktree 下照樣成立。
#    非 fast-forward 時 git 自己會拒絕（`! [rejected] ... (non-fast-forward)`）；
#    ⚠️ 被拒代表 main 已前進，先 `git rebase origin/main` 再從第 1 步重跑（SHA 會變）
git push origin "$BRANCH:main"

# 4b. ⭐ 把本地 main 追上——⛔ 少了這步，wfcli 的收尾守衛會擋掉 release。
#     refspec push 本質上「不」更新本地 main ref（那正是它不需 checkout 的代價），
#     而 merge_verified_local 比對的就是本地 main，會判 diverged 並以 rc=5 拒絕。
#     兩條路互補、實測皆 rc=0：main 沒被 checkout 時直接更新 ref；被佔用時 git 會
#     逐字拒絕（`refusing to fetch into branch 'refs/heads/main' checked out at …`），
#     此時到「持有 main 的那個 worktree」快進。⛔ 不要假設它是主 checkout——那是
#     未經驗證的前提，若該處在別的分支，merge 會把 origin/main 併進錯的分支。
if ! git fetch -q origin main:main 2>/dev/null; then
  # ⛔ 這裡不能用逐行解析。porcelain 對路徑是原樣輸出：含空白時 awk $2 只取第一段，
  #    含換行時整筆紀錄會被拆成兩行、任何以行為單位的取法都拿不到完整路徑。
  #    實測含換行的 holder 路徑：逐行版取到 '…/holder/main'、git -C 隨即 rc=128。
  #    ⇒ 用 --porcelain -z（每筆屬性以 NUL 結尾）＋ read -r -d '' 逐筆讀。
  MAINWT=""; w=""
  while IFS= read -r -d '' rec; do
    case "$rec" in
      "worktree "*)            w=${rec#worktree } ;;
      "branch refs/heads/main") MAINWT=$w; break ;;
    esac
  done < <(git worktree list --porcelain -z)
  [ -n "$MAINWT" ] || { echo "⛔ 找不到持有 main 的 worktree，人工處理"; exit 1; }
  git -C "$MAINWT" merge --ff-only origin/main
fi

# 5. ⭐ 兩層綁定後才關 PR。⛔ 不接受人工填入的 PR 編號——填錯的那張若剛好也是
#    OPEN，第一層條件仍成立，就會關掉一張無關的 PR。編號一律由分支反查。
git fetch -q origin
if ! git merge-base --is-ancestor "$SHA" origin/main; then
  echo "⛔ main 未包含 $SHA — 合併沒成功，⛔ 絕對不要關 PR"; exit 1
fi
PRJ=$(gh pr list --repo "$REPO" --head "$BRANCH" --state open \
        --json number,headRefName,headRefOid)
case "$(echo "$PRJ" | jq 'length')" in
  0) echo "本分支無 open PR（直推使 head 成為 base 祖先後 GitHub 會自動標 merged），不動"
     exit 0 ;;
  1) : ;;
  *) echo "⛔ 本分支有多張 open PR，人工判斷，停"; exit 1 ;;
esac
BIND=$(echo "$PRJ" | jq -r --arg b "$BRANCH" --arg s "$SHA" \
         '.[0] | (.headRefName == $b and .headRefOid == $s)')
if [ "$BIND" != "true" ]; then
  echo "⛔ 該 PR 的 head 與 $BRANCH@$SHA 不符，停"; exit 1
fi
gh pr close "$(echo "$PRJ" | jq -r '.[0].number')" --repo "$REPO"
```

⚠️ **第 3 步的保守方向是刻意的**：判準要求**同名的每一筆** check-run 都 success。
若 API 同時保留舊的 failure 與 re-run 後的 success，判準會回 `false`——**即使 GitHub
自己可能已依最新一筆放行**。⛔ 這不修：判準寧可多擋一次讓人回頭看，也不要因為選錯
「哪一筆才算數」而放行一次不該過的合併。要通過就把失敗那筆 re-run 到綠、或推一個新
commit。⚠️ 本 repo 的歷史裡**沒有**同名 check 一紅一綠並存的實例，⇒ 該情境是依
API 語意推的，**未實測**。

⚠️ **第 3 步為什麼不能寫 `length == 2`**：一個 commit 若同時經過分支 push 與 main push，
`api`／`web` **各會出現兩次**——實測 `113f029a` 上 `total_count = 6`（`api` ×2、`web` ×2、
`api (branch head)`、`web (branch head)`）。`length == 2` 會**否決一個完全綠的 commit**。
判準必須是「兩個名字都在 **且** 全部 success」，⛔ 不是「剛好兩筆」。

⚠️ **第 5 步為什麼不留 `PR=<N>` 這個輸入**：留著它、再加一道「比對 headRefName」的檢查，
擋得住的只是「檢查有跑」；填錯的那張若剛好也是 OPEN，第一層 `--is-ancestor` 條件**照樣成立**。
⇒ 把編號改成由 `--head "$BRANCH"` 反查，**填錯這件事在構造上就不存在了**。

**逐步實測證據**（2026-08-22，皆以 `git rev-parse` 取得的真實 SHA）：

| 測項 | 輸入 | 實得 |
|---|---|---|
| 第 3 步判準 vs 全綠 | `113f029a12928097e3d56a85e172daf9c830ed89` | `true` |
| 第 3 步判準 vs 紅 | `451a86de5bea425a438de4214a40157bb61662e5` | `false` |
| 第 3 步判準 vs 無 check | `1c3bc2ecf9ed2ac8837bec2226eb455a3ab06ce2`（`total_count=0`） | `false` |
| 第 4 步 refspec push（feature worktree，main 被主 checkout 佔用） | `git push --dry-run origin HEAD:main` | `113f029a..31e97938  HEAD -> main` |
| 第 5 步條件 vs 未合併 SHA | `31e97938…` | 判「未合併」⇒ 不關 PR |
| 第 5 步條件 vs 已合併 SHA | `113f029a…` | 判「已合併」⇒ 才允許關 PR |
| 第 5 步綁定 vs 分支對＋SHA 對 | `ai/opus-5/OPS-CPBL-MERGE-GATE1` @ `8bd77018…` | `BIND=true` ⇒ 才會關 PR #170 |
| 第 5 步綁定 vs 分支對＋SHA 錯 | 同分支 @ 舊交付 `31e97938…` | `BIND=false` ⇒ ⛔ 停，不關 |
| 第 5 步綁定 vs 分支無 open PR | `ai/opus-5/DOC-ROADMAP-OPEN-DEFAULT-STALE1` | `length=0` ⇒ `exit 0`，不關 |

⚠️ **未驗到**：第 4 步的 `--dry-run` **不證明 ruleset 會放行**。ruleset 對 refspec push 的
三個方向已於前次探針實測（無 check → 拒、紅 → 拒、綠 → 過），但那三次與本表的
`--dry-run` 是**不同次執行**，⛔ 本表不宣稱它們是同一次取證。

**⚠️ 為什麼不用 GitHub 的 merge 按鈕**：⛔ **那條路在本 repo 從未實測過**——判斷它可行的
依據是姊妹 repo `ai-workflow` 於 2026-08-22 在同型 ruleset 下的三次 PR merge 全部成功，
且其 merge commit 上只有 1 個 check（來自 merge 之後的 main push）⇒ 推得 ruleset 評估的是
PR head 而非 merge 結果。**那是推論，不是本 repo 的觀測。**

**不採用它是需求方 2026-08-22 的政策選擇，⛔ 不是因為它被證明比較差。** 政策至今未變更；
是否改用 merge 按鈕須由需求方另行裁定。

> **舊制歷史（#193 起已無現行檢查支撐）**：當時的理由建立在舊制 commit trailer 守衛
> `tests/test_commit_trailers.py`——它只檢 `main..HEAD`，故 GitHub 產生的 merge commit 不受檢；
> ff-only 直推不新增 commit，merge 按鈕則會新增一筆只能靠人檢查 trailer 的 commit（當時即註明
> 「這是偏好，不是安全性判決」）。該守衛屬舊流程，已於 #193 自 active test suite 移除，⛔ 不再是現行檢查。

**⛔ 本機 `--no-ff` merge 後直推已不可行**（本 repo 2026-08-10～08-17 做過 14 次）：那個 merge commit
是新 SHA、沒有任何 check。實測（2026-08-22，雙親 merge commit）遠端逐字回：

```
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - 2 of 2 required status checks are expected.
 ! [remote rejected]   HEAD -> main (push declined due to repository rule violations)
```

**⚠️ PR 被自動標記為 merged 不代表有人按了 merge 按鈕**：直推使 head 成為 base 的祖先時，
GitHub 會自動標記。判斷是否經 PR 合併要看 `gh api repos/.../commits/<sha>/pulls` 與 commit 的雙親數。

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
- 逐場：`games`、`game_scoreboard`、`game_livelog`、`batting_gamelog`、`pitching_gamelog`、`game_features`、
  `pitching_game_flags`（migration 073：stats.cpbl 單場 API 逐投手官方旗標，救援成功／失敗等）。
- 當季累計：`batting_current`、`pitching_current`、`team_current`、`fielding_current`。**口徑不一致**：`team_current`＝當前半季，batting/pitching＝全年（fielding 已排除半季）——見 §8 陷阱與 [`reference/GLOSSARY.md`](reference/GLOSSARY.md)。
- 對戰/分項：`matchups`、`vs_team_splits`、`batting_splits`、`pitching_splits`。
- 進階：`advanced_stats`、`pitch_tracking`、`team_standings`、`refresh_log`。
- 慣例：無 ORM、psycopg3 參數化(`%s`)、走 `cpbl.db.conn()`；新 migration `00X_*.sql` 須 `IF NOT EXISTS`（migrate() 每次全跑）；player_id 10 碼字串對齊 opendata。

## 10. 晚間事件鏈（#268 WP3；#365 起**常設**：A／E／C 有排定比賽的夜晚才動作）

官方完賽或公告新賽程後，首頁／季後頁／日曆要在**同一晚**反映（需求方裁定，含 23:30 以後才公布的資料；**沒有鐘點截止**）。
#365（#343 WP2）起涵蓋一軍 A（例行賽也同晚送達；⛔ 不含 D，D 隔日由每日鏈處理），全年安裝，休賽季與無賽日靠**動作條件**靜默。
名稱仍是 `postseason_*`（job、腳本、狀態檔）：已不準確，但改名會連坐登記表、plist、本節與 #358 的 check 名，刻意保留。
重新安裝（bootstrap）、清 `halted`、晚間 prod 資料還原仍屬共享操作，須需求方授權。

- 入口：`bash scripts/postseason-evening.sh --help`（只印用法）；邏輯在 `src/cpbl/ingest/postseason_evening.py`。
- launchd 樣板：`ops/launchd/com.cpbl.postseason-evening.plist`（`StartInterval` 300 秒；留在 `ops/` 不改變清冊對 `scripts/` 排程的分類）。
  已登記於 `scripts/schedule-registry.json`（cadence `interval`）：偵測器只對帳 plist、安裝狀態與狀態檔 `halted`，不做週期缺席判定。
  #365 起登記為**長期** `expected_installed=true`（授權：#365 需求完成卡 6361271444、Q4 裁定 6361900121）；不再有「系列結束 bootout、改回 `false`」的例行步驟。
  與 #293 A7 的先後（#365 規劃 4 §5.4）：**分支 A**（#365 先於 A7 合併）＝不 bootout、不重新 bootstrap，`effective_from` 維持 2026-10-14，A7 不翻回休眠、只收尾；
  **分支 B**（A7 先於 #365 合併）＝A7 照原授權 bootout 並翻回休眠，#365 合併後在授權窗口重新 bootstrap，登記翻回 `true`、`effective_from`＝重新安裝日。
  休賽季狀態檔可能很久不更新（plan 回 `quiet` 不寫檔），偵測器不因此告警。
- 賽別：`POSTSEASON_EVENING_KINDS`（預設 `A,E,C`；只收不重複的 A／E／C，含 D 或其他值 exit 64）。晚間 scrape 讀它，⛔ 不讀 plist 的 `REFRESH_POSTSEASON_KINDS`（那是每日鏈／live worker 的設定，plist 裡保留不動）。
- 每次喚醒：
  0. **動作條件**（#365）：「一晚」＝台北 12:00 起到次日 09:45（延長賽跨 24:00 仍屬同一晚；09:45–12:00 不屬任何一晚）。
     讀 #364 J1 寫的今日賽程檔 `POSTSEASON_TODAY_SCHEDULE`（預設 `logs/daily-schedule-today.json`；只認 `schema_version == 1`、`stage` ∈ decide／after_scrape、`date`＝該晚；排定場＝`games[]` 中晚間賽別且 `game_date == date`，**不看 `present_status`**，其他欄位忽略）：
     該晚有晚間賽別的排定場，或狀態檔有待辦（`halted`、`pending_sync`、`signals_unsynced`、未結事件、目標窗內未終態的 box／PA）→ 照下列流程跑；
     兩者皆無 → `plan → quiet`：**不寫狀態檔、不連 DB、不連 stats、不取鎖**，連 `boxpa-plan --dry` 都不跑，log 只留這一行。
     賽程檔缺、壞、日期不是該晚 → `fallback_db`：連本機 DB 查該晚 `cpbl.games` 有無晚間賽別的場（⛔ 不判 quiet，避免 J1 沒跑時連坐晚間鏈）。
     判定與理由記在狀態檔 `gate`，log 另有「動作條件：…」一行；`plan --dry` 另印 `gate`、`kinds`、`targets`（該晚目標場）。
  1. `plan`：不取鎖；到期才以 httpx **唯讀**讀 `stats.cpbl.com.tw/api/proxy/v1/games/schedule`（**只查該晚有排定的賽別**∪待辦所屬賽別 × 上月／本月／下月＋未結事件所在月份；跨月界不放掉前月，stats 沒回到的場次不當作已解決），與本機 DB 比對。
     事件只有三類：stats `FINISHED` 但本機未完成、stats 有本機沒有的 `(year, kind, sno)`、日期或主客異動。沒有事件就結束，**不連 www**。
     stats 資料不寫賽程／狀態表、不作完賽依據（判準仍是 `cpbl.completion`）；唯一例外是 #268 D1 待更新訊號：新場次／異動寫本機 `cpbl.official_change_signals`（migration 075），同步對帳通過或偵測不再成立才寫 `resolved_at`，首頁／季後頁／日曆據此標「賽程待更新」（`official_change_not_ingested`）。此表隨三表一起同步到 prod（每日鏈與晚間鏈共用 `sync_postseason_results`，需求方裁定 6142744045）；本機表變了而三表沒變（www／同步失敗、對帳通過後才解決）時，晚間鏈另走一次**僅訊號變動**的同步（plan／sync-due 回 `signals`；同一條已驗證備份→同步→對帳路徑，同樣受 halted／68 停當晚／讓位 10:10 約束）。⚠️ prod 須先部署含 075 的映像，否則同步在此表失敗（同 073 前例）。
  2. 有事件：取 refresh lock，E／C 跑既有 `_postseason_games_step`、A 直呼既有 `scrape_games(year, year, "A")`（www getgamedatas），只抓冷卻已過的賽別（請求以賽別為單位，冷卻亦以賽別計）。每事件最多 3 次、間隔 ≥20 分鐘；
     挑戰類失敗第 2 次即停止當晚所有 www（`www_blocked_at`，隔日 12:00 後才解除）；10:10 前後（09:45–10:15）讓位給每日鏈。
     **`P-A-FETCH-GATE`**（#343 裁定 6361673244 第 1 項；放行集合依 #365 規劃 4、#343 PLAN-r6 §3.8）：該晚**每一場** A 的 stats 狀態都在放行白名單 `{FINISHED, POSTPONED}` 才對 A 發 www；
     `RESERVED`（保留賽可能帶非零比分）、`START`、`SCHEDULED`（含尚未開賽）、未知字、缺值、任一 A 列的 `PreExeDate` 不是嚴格 `YYYY-MM-DDTHH:MM:SS` 有效日期時刻（週日期、基本格式、時區尾碼等都不收）、最近一次 stats 讀取失敗一律擋
     （reason `a_reserved`／`a_in_progress_or_pending`／`a_status_unknown`／`a_date_unknown`／`probe_unavailable`）。閘門讀 stats 的**未去重原始 A 列**（狀態檔 `a_stats_rows`）：
     每列只解析一次，同一場取最新 `PreExeDate`（與回傳順序無關）、當晚判定都用這個解析值（不讀 `game_date` 字串），同時刻多筆時任一筆非放行即擋。stats 回應必須是明確的 `Data.Games` list（`[]`＝合法空月份）；
     `{}`、缺 `Data`／`Games`、`null` 都算讀取失敗（不會清空賽程）。擋下時結果抓取、box／PA 明細、先發時點都不抓 A（記 `a_fetch_gate`，不計次、不寫冷卻帳本）。
     保留賽那晚的 A 交隔日每日鏈。⚠️ 閘門只管 www 抓取，不管同步：該晚若本機已有其他待同步變化或待同步的異動訊號（`pending_sync`／`signals_unsynced`），
     既有的 `POSTSEASON_RESULTS_ONLY` 同步仍會照常執行並整表帶上 `games`（上游已接受的殘餘風險：手動或他卡路徑寫入的部分比分會隨之同步）。
     只擋 A；E／C 與 stats 逐球重抓不受影響；沒有關閉開關。代價（需求方已接受）：同晚多場時先結束者延到最後一場終局後送達；手動或他卡在賽中抓 A 仍會寫入部分比分。
     晚間鏈內部的 A 完賽判定用每日鏈判準 `daily_chain_completed_games_sql`（官方 final 或證據；比分不作依據），E／C 不變。
  3. 本機有變化：`POSTSEASON_RESULTS_ONLY=1 SKIP_SCRAPE=1 BACKUP_DIR=<晚間專用> bash scripts/refresh-cpbl-prod.sh`
     ＝已驗證備份 → 只同步 `games`／`game_schedule_status_revisions`／`game_source_revisions`／`official_change_signals` → `/api/info` data-only 對帳。
     不訓練、不 build-features、不 migration、不同步 074 公告表、**不寫 prod refresh 標記**。
- **每晚首次同步前備份一次**（#365，P-EVENING-BACKUP；需求方裁定 #343 6361011713 第 2 項、6361069621）：同一晚第一次寫 prod 的同步
  （`POSTSEASON_RESULTS_ONLY` 或 `POSTSEASON_BOXPA_ONLY`）照常備份並驗證，路徑＋sha256 記進狀態檔 `night_backup`；同晚之後的同步由
  `backup-plan` 判可沿用時帶 `REUSE_VERIFIED_BACKUP`／`_SHA256`，`refresh-cpbl-prod.sh` 在同一行程、緊接同步前重驗（存在、位於本次 BACKUP_DIR、sha256 相符）
  才略過備份，log 記 `沿用 night_backup=<路徑>`；任一不符就照常重備（fail closed）。09:45–12:00 的同步一律重備；首次備份在驗證前失敗不記，下一次仍算首次。
  每次喚醒的使用紀錄（結果同步與 box／PA 同步都算）寫進 `last-postseason-evening.json` 的 `backup_uses`；結果鏈有嘗試、或只有 box／PA 同步用到備份時，
  另寫本機 `refresh_log`（detail 的 `backup`：「沿用 night_backup=…」／「新備份 …」）。refresh_log 寫入失敗時紀錄保留在狀態檔，**下次執行到 `finish` 時**才補寫（`plan → quiet`、或結果鏈與 box／PA 都 idle 而提前退出的喚醒不會執行 finish，補寫可能延後；紀錄不會遺失）。
  回退：`touch logs/postseason-evening-backup-per-sync.enabled`＝每次同步都備份（`POSTSEASON_BACKUP_PER_SYNC_FLAG` 可改路徑；下次喚醒生效、不需重新 bootstrap），`rm` 即回每晚一次。
  代價（需求方已接受）：還原粒度變粗——同晚後面的同步若寫壞，只能退回該晚首次同步前。
- 備份範圍：`backup-prod-db.sh` 備的是**整庫**（cpbl schema＋主站 public）。晚間鏈用獨立的 `POSTSEASON_BACKUP_DIR`（預設
  `~/Library/Application Support/cpbl-analytics/backups-postseason-evening`，保留 3 份），**不輪替掉 10:10 的 7 份**；
  備份腳本自身在參數守衛後設 `umask 077`：新建目錄 0700、檔案 0600（每日與晚間共用；既有備份權限不回頭處理）。
  資料寫錯時只考慮還原 **cpbl schema**，⛔ 不還原主站 public；還原屬破壞性 prod 寫入，發生時交需求方決定。
- 排他：與每日／每週排程共用 `/private/tmp/cpbl-analytics-refresh.lock`。公告 owner 持有時有界等待；其他一律 exit 75，**不刪、不搶**（即使 pid 已死）。
- 紀錄：`logs/postseason-evening-state.json`（跨次狀態）、`logs/last-postseason-evening.json`（最終狀態與時點）、`logs/postseason-evening-YYYYMMDD.log`；
  本機 `refresh_log` 只在嘗試 www／同步時寫一列（scope `postseason-evening`）。
- 時點：T1＝stats 首次觀測（官方發佈的上界近似）、T2＝本機狀態修訂表首見、T3＝三表（＋訊號表）同步＋對帳完成、T4＝使用者可見（只能以正式 Chrome 抽樣）。
  跨過 24:00 照實記錄實際日期時刻，不改寫成賽事日；由隔日 10:10 補上的事件記 `unreached`（`resolved_outside_evening_chain`），**不算同晚達成**。
- 錯誤即停：data-only 對帳不等（refresh 回 68）→ 記失敗並**停止當晚**（`sync_blocked_at`，隔日 12:00 後重試未同步的變化）；
  其他同步非零（64–67、psql／schema 錯誤、備份失敗）→ 狀態檔 `halted`，launchd 觸發時另 `launchctl bootout`；之後每次喚醒直接退出，
  直到人工檢視後把 `logs/postseason-evening-state.json` 與 `logs/last-postseason-evening.json` 兩檔的 `halted` 都改回 `null`（偵測器讀後者，閒置喚醒不重寫它）。www 成功但本機 C 列仍為 0 → 只停該項（`needs_owner_decision`），交需求方，不換工具、不繞道。
- 晚間跑過後隔日 10:10 若出現挑戰類失敗：具名本機角色 bootout 本 job 並回報（以 `logs/last-launchd-status.json` 核對；本鏈不自動判讀它）。
- **TM 重抓**（#365，P-TM-RECHECK）：本機首見完賽（`finished_first_seen` 的 `finished_at`，沒有時用 `first_seen_finished_at`）後滿 `POSTSEASON_TM_RECHECK_MIN`
  分（預設 45；非正整數 exit 64）→ 目標窗內已送達（或更正待同步）的場以 `reopened_tm_recheck` 重開，每場只做一次（box／PA 紀錄 `tm_recheck {due_at, fetched_at, outcome}`，
  outcome ∈ changed／unchanged／failed／quota_exhausted），跑一次既有 `boxpa-tracking`（只打 stats、不連 www、
  不寫冷卻帳本），之後照既有 PA build → sync（同步額度仍以場計 2 次，不新增重試）。晚間鏈**沒有** E／C 進階 leaderboard 重抓（P-LB-RECHECK 已刪，#343 裁定 6361673244 第 2 項）。
- 回復（各自可單獨執行）：排程＝`launchctl bootout gui/$(id -u)/com.cpbl.postseason-evening` 並移除 LaunchAgents 連結；
  程式＝revert 本卡 PR（主 checkout fast-forward 後下一次喚醒即回舊碼；舊碼載入新狀態檔時多出的 `night_backup`／`gate`／`a_fetch_gate`／`backup_uses`／`tm_recheck` 原樣保留不讀；
  A7 之後才 revert 時，bootout 與 revert 授權一起向需求方請示，⛔ 不預先執行）；
  只退備份規則＝per-sync 旗標（見上）；資料＝見上方備份範圍（晚間出錯時先複製保全該晚 `night_backup` 再做任何操作）。
- 常設前提：Mac 晚間保持喚醒且登入（不改個人電源設定，只記錄）、登記表 `expected_installed=true` 且主 checkout 在含它的 main；
  因停止條件停用前先處置本機未解決的 `official_change_signals`（否則每日鏈會持續把它鏡像成公站「賽程待更新」）。

### 先發 23:00 時點（#342；旗標預設關，啟用另需授權）

依中職「官網於比賽前一天公布先發」慣例，每場前一天 23:00 固定抓官網一次、只更新先發投手並同步正式站（需求方裁定 #342 6405678916／6405698649）。邏輯在 `src/cpbl/ingest/starter_watch.py`，接線在 `postseason_evening`（plan／scrape／record-sync），⛔ 不新增 launchd job。

- 時點：每場 `F＝開賽前一天 23:00`（S＝狀態檔 stats `PreExeDate`；改期後新 S 的 F 自動成為新時點）。F 起第一次喚醒抓該賽別 getgamedatas 一次（同晚同賽別合併）；只對 stats `SCHEDULED`、本機兩隊先發未齊的 A／E／C 場（⛔ 不含 D）。共用賽別冷卻 20 分、挑戰停、`halted`、68 停當晚；被擋只延後、不計次，最遲 01:00，過了記 `missed`。休兵日也會醒（狀態檔賽程，或 23:00–01:00 唯讀查本機 `games` 當場比賽日）。
- 只寫先發：只更新目標場 `games.home_starter_id`／`away_starter_id`（只補不清；本機已有比分或 `delay_kind='保留'` 的列不動、不新增列），修訂表只記目標場賽前 entry（同組有終局／保留／非零比分整組不碰）。因此不受 `P-A-FETCH-GATE` 約束（閘門判定未改）；有變化才走既有 `POSTSEASON_RESULTS_ONLY` 同步。
- 失敗通知：抓取失敗（`failed`）、抓完先發仍空（`empty`）、01:00 前沒抓成（`missed`）、寫入後同步失敗（`sync_failed`）⇒ 本機通知（重用 `scripts/schedule_watch.py` 的 `notify`；⚠️ osascript rc=0 不是送達證據）＋持久檔 `logs/starter-watch-alert.json`（開賽後不再列）；由隔日 10:10 每日鏈補上。紀錄在狀態檔 `starter_watch`。
- log 辨識：本路徑寫進 `logs/postseason-evening-*.log` 的行以 `starter-watch ` 開頭；www 導頁記 `WWW_REQ card=342`／`WWW_NAV card=342`（src=342）。shell 既有的 `plan → scrape`、`scrape → changed`、`sync exit=` 等行照舊，`plan` 的理由為 `starter_watch` 時由 `starter-watch plan …` 行標出。
- 旗標：`logs/starter-watch.enabled`（`POSTSEASON_STARTER_WATCH_FLAG` 改路徑；持久檔 `POSTSEASON_STARTER_WATCH_ALERT`）。存在＝開，`touch`／`rm` 下次喚醒生效。`plan --dry` 另印 `starter_watch`（`enabled`、此刻的 23:00 目標，不查 DB）。
- 已知未解：開賽前 1 小時才公布等例外不處理（需求方 6405678916）。重播證據：`uv run python tests/starter_watch_replay_harness.py --out <報告.json>`（#342 exec-1 REPLAY）。
- 回復：`rm logs/starter-watch.enabled`（行為回到 #365 基準）；撤碼以 revert 合併 commit。

### 先發查核時點（#292 S11 A1；旗標預設關，啟用另需授權）

官方先發投手（www getgamedatas `HomePitcherAcnt`／`VisitingPitcherAcnt` → `games.home_starter_id`／`away_starter_id`，原始 payload 進 `game_schedule_status_revisions`）
除每日 10:10 鏈之外，由晚間鏈在下列時點再查一次（需求方裁定 #292 6184111089；容許窗 D9、重送 D2，規劃確認 6184976448）。邏輯在 `src/cpbl/ingest/starter_checkpoints.py`，接線在 `postseason_evening.plan`。

- 時點（S＝狀態檔中最近一次 stats `PreExeDate`；F＝本機觀測到該場「未完賽→完賽」轉變的時刻；**首次看到時就已完賽的場次沒有 F、不產生 F+60**，狀態檔 `finished_first_seen` 的舊字串值也不當錨點）：
  `S-60`（最遲 S−40，失敗不重送）、`S-30`（須早於開賽，開賽整點不算；失敗於 ≥20 分後重送 1 次，同樣須早於開賽）、`F+60`（最遲 F+90，失敗於 ≥20 分後重送 1 次）。
  launchd 每 300 秒喚醒，實際執行通常晚 0–5 分；挑戰類失敗不重送；鎖被占、冷卻、讓位 10:10 只延後不計次；超過最遲時刻記 `missed`（被挑戰停／對帳停擋下記 `blocked`），⛔ 事後補打。
  S−60／S−30 只對未開打場次（stats 狀態 `START`／`FINISHED`／`POSTPONED`／`RESERVED` 以外）；取不到 S ⇒ `start_time_unknown`；延賽／保留 ⇒ F+60 記 `no_final`，改期後依新 S 產生新時點，舊錨點的待辦一看到新時程即結清（`rescheduled`），⛔ 再以舊時刻抓取。www `GameDateTimeS` 只並列記錄（`www_start_raw`／`start_mismatch`），以 stats 為準。
- 抓取與送達都沿用既有路徑：plan 回 `scrape`（理由 `starter_checkpoint`；與同賽別事件合併成一次），只抓目標賽別，共用 www 冷卻帳本、挑戰停、`halted`／68 停當晚。
  本機 E／C 指紋（`local_signature`）含兩隊先發欄位與「每場目前觀測版本」（依 `last_seen_at` 的 payload_hash 集合），修正、撤回、**改回舊值（A→B→A）**都會觸發既有 `POSTSEASON_RESULTS_ONLY` 同步；同內容重抓不觸發。
- 旗標：`logs/postseason-starter-checkpoints.enabled`（可用 `POSTSEASON_STARTER_FLAG` 改路徑）。**存在＝開**：`touch` 開、`rm` 關，下次喚醒生效、不需重新 bootstrap；開啟前已到點的時點不補建。
  預覽（不連網、不碰 DB、不寫狀態）：`uv run python -m cpbl.ingest.postseason_evening plan --dry [--now 2026-10-17T12:00:00]`。
  輸出既有三鍵 `now`／`starter_enabled`／`points` 不變；#365 另加 `gate`（`decision`／`reason`）、`kinds`、`targets`（該晚目標場；賽程檔不可用時 dry 不查 DB、`targets` 為空）。
  #365 起 A 也會產生時點，但 `P-A-FETCH-GATE` 的放行集合只有 `FINISHED`／`POSTPONED`（`SCHEDULED` 不放行）：**A 的 S−60／S−30 在開賽前一律被擋**
  （記 `a_fetch_gate`、不計次，過最遲時刻記 `missed`），實際上抓不到 A 的賽前先發；A 的 F+60 要等該晚每一場 A 都 `FINISHED`／`POSTPONED` 才會放行。
  ⇒ A 的賽前先發公告若要同晚取得，須另案（#342），⛔ 不得以關閉閘門達成。
- 紀錄：狀態檔 `starter_checkpoints`（每時點 `key／point／phase／due_at／deadline_at／fired_at／attempts[]／outcome／sync_code`）、`finished_first_seen`；`last-postseason-evening.json` 的 `starter_checkpoints` 為摘要。
  outcome ∈ `changed／unchanged／failed／missed／blocked／start_time_unknown／no_final`；`phase`：S 兩點 `pregame`、F+60 `postgame`（**開賽後觀測，⛔ 不是賽前公告**）。
- ⚠️ 時間語意：`fired_at`、修訂列 `fetched_at`（首見）／`last_seen_at`（最後一次看到）都是**本機觀測時刻**，⛔ 不是官方公布時刻；任何層都不得產生或宣稱「公布時刻」。`last_seen_at` 只留最後一次，不能重建每次查詢歷史——查詢歷史以時點紀錄為準。
- 同步的提交邊界（演練見 #292 E4）：四表各自一次 `--single-transaction`、逐表提交。寫入前的參數／目錄（64）、本機 freshness 基準（65）、已驗證備份失敗 ⇒ 四表都未寫；第 k 表的寫入前檢查（欄位守衛、序列名 66、payload 斷言 67、序列遙測）或交易失敗 ⇒ 前 k−1 表已提交（`games` 投影可能先於修訂證據更新；舊修訂列不刪不改，下一次成功同步收斂）；68 ⇒ 四表已寫入。
- 正式站讀取（C-1 以 E-4 為錨點）：`GET /api/v1/games/4/report?season=2026&kind_code=E&context_only=true` 取 `journey_context.context_hash` →
  `GET /api/v1/games/4/report?season=2026&kind_code=E&next_kind=C&next_sno=1&context_hash=<hash>`，讀 `comparison.game.{away,home}_starter`；C-2 起錨點改前一場 C、讀 `next_game.*_starter`。另 `/api/v1/games/calendar` 的 `home_starter`／`away_starter`。
  已知限制（D7，A2 修）：A→B→A 時 report 的賽前選版仍依 `max(fetched_at)` 選到 B；日曆依 `games` 顯示 A。
- 停止與恢復（晚間鏈被時點連坐停止時）：① 先 `rm` 旗標；② 讀 `logs/postseason-evening-YYYYMMDD.log` 與同步 log 判斷失敗類別，production 狀態未明先停、交 PM，⛔ 盲目重跑；
  ③ 依上方〈錯誤即停〉把兩份狀態檔的 `halted` 改回 `null`；④ 若已 bootout：`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cpbl.postseason-evening.plist`（避開 09:30–10:30、21:00–21:15）；
  ⑤ 確認下一次喚醒 log `plan → idle`／`scrape`、`launchctl list | grep postseason-evening` 有載入、`last-postseason-evening.json` 的 halted 為 null、schedule-watchdog 未報 FAILED；⑥ 68（停當晚）不需人工，隔日 12:00 後自動重試，不調時段補洞。各步由具名本機角色在需求方授權下執行。
