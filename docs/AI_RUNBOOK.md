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
| **本機** | docker compose `db`（PG 17，**port 5433**） | `uvicorn cpbl.api.main:app --port 4001` | `web/` Next.js `:3000`（`NEXT_PUBLIC_API_URL`，**不是** `API_URL`） |
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

**鐵則：官網爬蟲只能在本機跑，不能在 VPS 跑。** VPS 機房 IP 打 `www.cpbl.com.tw` 回 **404**（Cloudflare 擋資料中心 IP；2026-06-22 實測 `prod_cpbl_api` 內 `cpbl-scrape-games` 全 kind 404）。住宅 IP 正常。詳見記憶 `data-sync-local-to-prod`。

### 官網反爬（Playwright；2026-06 起）

主站有 HiNet CDN JS 挑戰，純 httpx 回 428 → 爬蟲走 **Playwright**（`ingest/_browser.py`
單例 session：開頁過挑戰 + page context 內 fetch 發 AJAX）。依賴：
`uv sync --group scrape && uv run playwright install chromium`。

- 挑戰**機率性**觸發；`_browser.py` 內建重載退避自癒（`page_html(require=)`/`post()`/`_goto()`）。
- **失敗勿立刻重跑**：連續冷啟動會讓 HiNet 節流升級（token 時好時壞→fetch 全掛→重定向迴圈，
  2026-07-03 實測）。先冷卻 **15–20 分鐘**再單次重試。
- 端點/token/解析錨點/改版排查 → **[`CPBL_SITE_MAP.md`](CPBL_SITE_MAP.md)**（爬蟲事實單一來源）。

**⚠️ 生產每日 cron 實際沒在跑**：`cpbl.refresh_log` 為空、生產資料曾停在某日。生產新鮮度目前靠人工「本機爬 + 同步」。

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
| `cpbl-scrape-stats <from> <to>` | 投打進階 + 團隊累計(ERA/WHIP/K9/OPS…) | 當季累計刷新 |
| `cpbl-scrape-standings <year>` | 官方戰績(含上下半季/勝差/H2H/近十場) | 戰績刷新 |
| `cpbl-scrape-pitches [delay]` | 逐球 TrackMan（**投手中心**，全投手→自動涵蓋所有場次） | 逐球刷新 |
| `cpbl-scrape-advanced` | 官方進階 + 官方 PR(stats.cpbl) | 進階數據刷新 |
| `cpbl-scrape-detail` / `cpbl-scrape-fighting` | 選手對戰各隊/分項 / 投打對決 | **分項/vs各隊已改重算停爬**（見 build-splits）；detail 僅剩季後 C/E 生涯補抓、fighting 供投打對決 |
| `cpbl-refresh-recent [fast]` | 抓昨天/今天：games+累計+(增量)對戰/逐球 + **重算分項寫回**，寫 `refresh_log` | 每日增量（本機跑） |
| `cpbl-build-splits [year] [kinds]` | **重算**本季 splits+vs各隊四表並寫回 + 生涯(base+本季)（純 DB 不爬，**生產可自跑**） | 已含於 refresh；手動重建分項 |
| `cpbl-anchor-career <season> <csv_dir>` | 錨定生涯基底（官方生涯−官方本季同刻相減，一次性/重錨） | 跨年 roll 或重錨（見其 docstring） |
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
- `lib/`：`client.ts`(Client fetch) `api.ts`(Server) `teams.ts`(隊色/字母徽章) `cols.ts`。
- 元件：`game-board.tsx`(ESPN 狀態板) `spray-chart` `zone-scatter` `perf-heatmap` `la-ev-scatter` `leaderboard` `matchup-card` `ui.tsx`(Card/StatTile/TeamLogo/PercentileBar)。
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
```

- 遠端 event 的 `state_version` 由 1 單調遞增；handoff、review、merge、release 必填 source SHA 與 evidence。逾期前可由 owner 續約；回收前 Coordinator 必須檢查 worktree 的未提交變更，禁止靜默刪除工作內容。
- 同一卡族（原卡及 `<CARD_ID>-FIX<n>`）共用一個 worktree。merge 者在卡族全數結案後依序移除 worktree、刪本地分支、刪遠端分支。
- 對 DB 的 claim 另依 [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) 取得資源 lease；schema 與 data migration 不可並行。

```bash
# 改完一定要過：
uv run ruff check                 # 後端
cd web && npx tsc --noEmit        # 前端
# 改成績模型還要：容器內 cpbl-train 看回測對照表未退化
```

**部署 = push-to-deploy（在主站操作）**：
1. 本 repo：commit + push（CI 只跑 lint + tsc，**不部署**）。
2. 主站 `~/Dev/PersonalWebsite`：`apps/subprojects/cpbl-analytics` checkout 到新 commit → `git add` 該 submodule → commit（**只動 submodule 一行**，勿夾帶主站其他未提交變更，VPS 是 `git reset --hard origin/main`）→ push。
3. 主站 CI 成功 → `deploy.yml` 自動 SSH 到 VPS：`submodule update` + `docker compose -f docker-compose.prod.yml build/up` + 健康檢查 + nginx 重啟。約 12 分鐘（build 兩個映像）。
4. 監看：`gh run list --workflow Deploy`；驗證：`curl https://cpbl.ruan-ruan.com/api/info`。

> 純前端版面微調期間先不部署（見記憶 `no-deploy-during-layout-tweaks`），累積到滿意再一次上線。

---

## 8. 已知陷阱（踩過的，勿重蹈）

| 陷阱 | 事實 / 對策 |
|---|---|
| **VPS 不能爬官網** | 機房 IP 被擋 → 本機爬 + 同步（§3）。記憶 `data-sync-local-to-prod` |
| **爬蟲失敗連續重跑** | HiNet 節流會升級，症狀惡化。冷卻 15–20 分再單次重試；排查照 `CPBL_SITE_MAP.md` §5 |
| **「找不到 token」偶發** | 多半是挑戰未過（機率性），非官網改版；`page_html(require=)` 會自癒。冷卻後仍 100% 失敗才是改版 |
| **pitch_tracking 覆蓋不全** | 球場端設備，無設備球場(大巨蛋/亞太主/嘉義/花蓮/新莊)整場 0；官方有的指標一律用官方全季值，勿用逐球重算。記憶 `pitch-tracking-venue-coverage` |
| **pitch_tracking 含二軍** | 有 `kind_code='D'`；逐球查詢**必須加 `kind_code='A'`** |
| **pitch_tracking `pitcher_name` 亂碼** | 編碼問題；比對一律用 `*_acnt`，勿用 name |
| **衍生欄恆 NULL** | `ops_plus/era_plus/fip` DB 永遠 NULL，由 API 即時算。記憶 `derived-stats-computed-live` |
| **分項主鍵** | `*_splits` 主鍵含 `item_name`（mig 022）；前端分類用 item_name 內容非 group_code |
| **官網 token** | `/schedule` inline JS 抽 `RequestVerificationToken`，放 **header**；不是 hidden input 的 `__RequestVerificationToken`（會 500） |
| **前端 env** | 用 `NEXT_PUBLIC_API_URL`，舊 README 的 `API_URL` 會連不到 |
| **同年多隊** | 球員一年多列(多 team_id)，季彙總查詢要 `GROUP BY player_id, year` 加總 |
| **build 污染 dev 快取** | `next build` 與 `next dev` 共用 `web/.next` → dev 跑著時跑 build，dev 讀到對不上的 `./NNN.js`／`Internal Server Error`。**已有 `prebuild` 守衛**（`web/scripts/guard-build.mjs`）：偵測 :3000 有 dev 就中止 `npm run build`。**驗證一律用 `npm run build:check`**（獨立 `.next-check`，守衛不擋、不影響 dev）。萬一仍中招：停 dev → `rm -rf web/.next` → 重啟 dev |

---

## 9. DB schema 重點（`cpbl`，migrations 001–022）

- season/ML：`*_seasons`、`projections`、`model_versions`。
- 歷史冠軍：`championships`（1990–2025 逐年官方來源＋franchise）→ `championship_members`（離線重建成員）。
- 逐場：`games`、`game_scoreboard`、`game_livelog`、`batting_gamelog`、`pitching_gamelog`、`game_features`。
- 當季累計：`batting_current`、`pitching_current`、`team_current`、`fielding_current`。
- 對戰/分項：`matchups`、`vs_team_splits`、`batting_splits`、`pitching_splits`。
- 進階：`advanced_stats`、`pitch_tracking`、`team_standings`、`refresh_log`。
- 慣例：無 ORM、psycopg3 參數化(`%s`)、走 `cpbl.db.conn()`；新 migration `00X_*.sql` 須 `IF NOT EXISTS`（migrate() 每次全跑）；player_id 10 碼字串對齊 opendata。
