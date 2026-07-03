# AI_RUNBOOK — cpbl-analytics 操作事實單一來源

> 給 AI/維護者的**操作手冊**：進來先讀這份，省去重新摸索。
> 分工：[`CLAUDE.md`](../CLAUDE.md) = 準則與紅線（為什麼）；本檔 = 怎麼做、跑什麼、有什麼坑（事實）。
> 兩者衝突時，以**現實 + 本檔**為準，並回頭修正過時的那份。最後核實：2026-06-22。

---

## 1. 一分鐘心智模型

- **雙軌 ML**：(1) **成績預測** [projection]：打擊 rate stat，離線 `cpbl-train`（Marcel vs LightGBM 時間切分回測）；(2) **賽果預測** [outcome]：單場主隊勝率，API request 時即時 fit 使用者選的特徵子集（**不離線訓練**）。
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

**⚠️ 生產每日 cron 實際沒在跑**：`cpbl.refresh_log` 為空、生產資料曾停在某日。生產新鮮度目前靠人工「本機爬 + 同步」。

### 本機每日自動爬取（launchd，免手動 CLI）

`scripts/scrape-daily.sh` + `scripts/com.cpbl.scrape-daily.plist`：launchd 每日 03:10 在本機跑
`cpbl-refresh-recent`（更新**本機** DB；上線仍須另跑 `refresh-cpbl-prod.sh`）。安裝：

```bash
ln -sf "$PWD/scripts/com.cpbl.scrape-daily.plist" ~/Library/LaunchAgents/com.cpbl.scrape-daily.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cpbl.scrape-daily.plist   # 啟用
launchctl kickstart -k gui/$(id -u)/com.cpbl.scrape-daily                             # 立即測跑
launchctl bootout gui/$(id -u)/com.cpbl.scrape-daily                                  # 停用
```

**AI 接手失敗的契約**（三個訊號源，由輕到重）：
1. `logs/last-status.json` — 最近一次 `{ok, exit_code, log, tail}`；`ok=false` 即需處理。
2. `logs/refresh-YYYYMMDD-HHMM.log` — 該次完整輸出（last-status.json 的 `log` 指向它）。
3. `SELECT * FROM cpbl.refresh_log WHERE ok=false ORDER BY refreshed_at DESC LIMIT 1` — app 層失敗（含 `note`、`detail.error`）。

`exit=127` = 本機 DB 容器沒開（OrbStack 未啟動）；token 抽不到 = 官網改版（見 `cpbl_site._new_session`）。

### 同步流程（本機 → 生產）

cpbl schema 各表皆冪等、資料同源，本機是 superset，故可整 schema 覆蓋（**只動 `cpbl` schema，不碰主站其他 schema**）：

```bash
# 1) 本機先爬到最新（見 §4 場景）
# 2) dump 本機 cpbl schema（含結構+資料）
PGPASSWORD=cpbl pg_dump -h localhost -p 5433 -U cpbl -d cpbl \
  --schema=cpbl --clean --if-exists --no-owner | gzip > /tmp/cpbl_sync.sql.gz
# 3) 灌入生產（生產 DB 帳密讀主站 .env 的 DB_USER/DB_NAME）
gunzip -c /tmp/cpbl_sync.sql.gz | \
  ssh root@45.76.100.29 'docker exec -i prod_pg psql -U <DB_USER> -d <DB_NAME>'
# 4) 驗證：API 新鮮度
curl -s https://cpbl.ruan-ruan.com/api/info | python3 -m json.tool
```
> 首次執行務必先 `pg_dump` 備份生產 cpbl schema。`--clean --if-exists` 會 drop 重建 cpbl 物件。

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
| `cpbl-scrape-detail` / `cpbl-scrape-fighting` | 選手對戰各隊/分項 / 投打對決 | 球員頁對戰刷新 |
| `cpbl-refresh-recent [fast]` | 抓昨天/今天：games+累計+(增量)對戰/分項/逐球，寫 `refresh_log` | 每日增量（本機跑） |
| `cpbl-build-championships` | 由 games(kind C) 推導歷年冠軍→標該年一軍球員+總教練(物化 `championship_members`，純 SQL 不爬) | 改冠軍邏輯後（已含於 refresh-recent） |
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

---

## 6. 前端地圖（`web/`，Next.js 15 App Router + Tailwind v4 + recharts）

- 路由：`/`(戰績) `/predict`(賽果卡) `/players/[id]`(旗艦) `/games`+`/games/[sno]`(賽況狀態板) `/batters` `/pitchers` `/matchups`。
- `lib/`：`client.ts`(Client fetch) `api.ts`(Server) `teams.ts`(隊色/字母徽章) `cols.ts`。
- 元件：`game-board.tsx`(ESPN 狀態板) `spray-chart` `zone-scatter` `perf-heatmap` `la-ev-scatter` `leaderboard` `matchup-card` `ui.tsx`(Card/StatTile/TeamLogo/PercentileBar)。
- 設計：日間 Navy+白；token 在 `globals.css @theme`；百分位藍↔紅發散。

---

## 7. 驗證與部署

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
| **pitch_tracking 覆蓋不全** | 球場端設備，無設備球場(大巨蛋/亞太主/嘉義/花蓮/新莊)整場 0；官方有的指標一律用官方全季值，勿用逐球重算。記憶 `pitch-tracking-venue-coverage` |
| **pitch_tracking 含二軍** | 有 `kind_code='D'`；逐球查詢**必須加 `kind_code='A'`** |
| **pitch_tracking `pitcher_name` 亂碼** | 編碼問題；比對一律用 `*_acnt`，勿用 name |
| **衍生欄恆 NULL** | `ops_plus/era_plus/fip` DB 永遠 NULL，由 API 即時算。記憶 `derived-stats-computed-live` |
| **分項主鍵** | `*_splits` 主鍵含 `item_name`（mig 022）；前端分類用 item_name 內容非 group_code |
| **官網 token** | `/schedule` inline JS 抽 `RequestVerificationToken`，放 **header**；不是 hidden input 的 `__RequestVerificationToken`（會 500） |
| **前端 env** | 用 `NEXT_PUBLIC_API_URL`，舊 README 的 `API_URL` 會連不到 |
| **同年多隊** | 球員一年多列(多 team_id)，季彙總查詢要 `GROUP BY player_id, year` 加總 |

---

## 9. DB schema 重點（`cpbl`，migrations 001–022）

- season/ML：`*_seasons`、`projections`、`model_versions`。
- 逐場：`games`、`game_scoreboard`、`game_livelog`、`batting_gamelog`、`pitching_gamelog`、`game_features`。
- 當季累計：`batting_current`、`pitching_current`、`team_current`、`fielding_current`。
- 對戰/分項：`matchups`、`vs_team_splits`、`batting_splits`、`pitching_splits`。
- 進階：`advanced_stats`、`pitch_tracking`、`team_standings`、`refresh_log`。
- 慣例：無 ORM、psycopg3 參數化(`%s`)、走 `cpbl.db.conn()`；新 migration `00X_*.sql` 須 `IF NOT EXISTS`（migrate() 每次全跑）；player_id 10 碼字串對齊 opendata。
