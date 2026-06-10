# CLAUDE.md — cpbl-analytics 專案 AI 運行準則

## 專案概覽

中華職棒 [CPBL] 資料管線與**球員成績預測** [projection] 服務。
PersonalWebsite 主站的子專案,透過 `/api/info` 掛載到子網域並被主站 `InfoPoller` 每 5 分鐘輪詢。

獨立 git repo（位於 `~/Dev/cpbl-analytics`），之後以 git submodule 掛回主站
`apps/subprojects/cpbl-analytics/`。**與主站完全解耦**：自己的 CI、自己的 Docker build。

---

## 核心定位與邊界（先讀，避免走錯方向）

| 主題 | 事實 | 為什麼重要 |
|---|---|---|
| **ML 目標** | 做的是**成績預測**（AVG/OBP/SLG/OPS rate stat），**不是賽果預測** | 賽果（勝負）預測需要**逐場**資料；現有資料源沒有 |
| **資料粒度** | 來源 `cpbl-opendata` 只有**逐年彙總**，最早 1990 | 任何「逐場 / 單場 box score」需求都無法用現有資料滿足 |
| **驗收標準** | LightGBM 必須在**時間切分回測**上打贏 Marcel baseline 才算有價值 | 打不贏 baseline = 模型沒學到東西，這是誠實的工程紅線 |
| **賽果預測前置** | 需先做官網逐場爬蟲（Phase 2，見下） | 不要在沒有逐場表時嘗試做賽果模型 |

---

## 技術棧

| 層面 | 技術 |
|---|---|
| 語言 / 套件管理 | Python 3.12（釘在 `.python-version`）/ **uv** |
| Web | FastAPI / uvicorn |
| 資料庫 | PostgreSQL 17 / **psycopg3**（raw SQL，無 ORM）/ schema `cpbl` |
| 資料處理 | polars / 標準庫 csv（ingest 對缺欄位寬容） |
| ML | LightGBM（主模型）/ Marcel（baseline）/ scikit-learn（metrics） |
| 設定 | pydantic-settings（讀 `.env`） |
| 容器 | Docker（本機由 **OrbStack** 提供） |

---

## 專案結構

```
cpbl-analytics/
├── migrations/001_init.sql       # cpbl schema：season-level 表 + ML 表
├── src/cpbl/
│   ├── config.py                 # 設定（env → Settings）
│   ├── db.py                     # psycopg3 connection pool + migrate()
│   ├── ingest/
│   │   ├── opendata.py           # cpbl-opendata 逐年回填（冪等 UPSERT）
│   │   ├── cpbl_site.py          # 官網逐場爬蟲（getgamedatas，見下方契約）
│   │   ├── cpbl_stats.py         # 官網 /stats 投手/打者進階 + 團隊數據爬蟲
│   │   ├── run_backfill.py       # CLI：migrate + backfill
│   │   ├── run_scrape.py         # CLI：爬逐場賽程/結果
│   │   └── run_scrape_stats.py   # CLI：爬本季投打進階 + 團隊
│   ├── features/
│   │   ├── batting.py            # 成績預測特徵（lag 1~3 季 + 年齡 + 聯盟均值）
│   │   └── outcome.py            # 賽果預測特徵（leakage-safe running state + 先發投手）
│   ├── models/
│   │   ├── marcel.py             # Marcel baseline（加權 5/4/3 + 回歸均值 + 年齡曲線）
│   │   ├── train.py              # 成績預測：LightGBM 訓練 + 回測 + 持久化
│   │   ├── outcome.py            # 賽果預測（舊：特徵子集回測準確率探索）
│   │   └── matchup.py            # 賽果預測（主：單場對戰卡 + 定向預設權重）
│   └── api/main.py               # FastAPI（/api/info + /outcome + /season/standings）
├── web/                          # 獨立 Next.js 15 前端（App Router + Tailwind v4 + recharts）
├── migrations/                   # 001_init…007；games/game_features/pitching|batting|team_current
├── Dockerfile                    # uv build → python slim runtime（裝 libgomp1）
└── docker-compose.yml            # 本地：自帶 PG（port 5433）+ api
```

---

## 開發指令

```bash
uv sync                                   # 建 venv + 裝依賴
docker compose up -d db                   # 起本地 PostgreSQL（5433）
cp .env.example .env
uv run cpbl-backfill                       # 套 migration + 回填歷史（逐年）
uv run cpbl-scrape-games 2023 2026         # 爬官網逐場賽程/結果（純 HTTP）
uv run cpbl-scrape-stats 2025 2026         # 爬本季投手/打者進階 + 團隊數據
uv run cpbl-build-features                 # 建賽果預測特徵表（leakage-safe）
uv run cpbl-train                          # 成績預測：訓練 + 回測（Marcel vs LGBM）
uv run uvicorn cpbl.api.main:app --reload --port 4001
cd web && npm install && NEXT_PUBLIC_API_URL=http://localhost:4001 npm run dev   # 前端 :3000
```

> 賽果預測**不需離線訓練步驟**：模型在 API request 時依使用者選的特徵子集即時 fit
> （見 `models/matchup.py`，預設權重=各變因單獨標準化係數、定向後正=有利主隊）。
> 成績預測（打擊 projection）才有 `cpbl-train` 離線步驟。
> current 系列表（pitching/batting/team）與 games 一樣要定期重跑爬蟲（上線掛 cron）。

### ⚠️ macOS 上的 LightGBM（重要）

macOS host 原生跑 LightGBM 會缺 `libomp.dylib`。**不要 `brew install libomp` 污染 host**，
改在容器內跑需要 LightGBM 的步驟（`train`）：

```bash
docker compose build api
docker compose run --rm api cpbl-train     # 容器內已有 libgomp1，LightGBM 可用
```

`backfill` 不需 LightGBM，可直接在 host 跑。

---

## 修改程式碼的準則

### 資料庫

1. **不使用 ORM**：所有 SQL 直接寫在模組內，用 psycopg3 參數化（`%s`），嚴禁字串拼接 SQL。
2. **連線**：一律走 `cpbl.db.conn()` context manager（自動 commit/rollback），不要自開連線。
3. **Migration**：新增放 `migrations/`，檔名 `00X_description.sql`，內容必須 `IF NOT EXISTS`（migrate() 會每次全跑，需冪等）。不要改動已存在的 migration。
4. **Schema**：所有表在 `cpbl` schema 下。ID 與 `cpbl-opendata` 對齊（player_id 為 10 碼字串），確保未來逐場資料能以相同 ID 疊加。

### Ingest（回填）

1. **冪等**：所有寫入用 `INSERT ... ON CONFLICT ... DO UPDATE`，可重複執行不產生重複列。
2. **容缺欄位**：各年度 CSV 欄位會變動（如 IBB 2021 才加入），用 `r.get(col)` + `_to_int/_to_float` 容錯，**嚴禁假設欄位一定存在**。
3. **同年多隊**：傳出的球員一年可有多列（多 team_id），PK 含 team_id；查詢彙總時記得 `GROUP BY player_id, year` 加總。

### ML

1. **Marcel 是紅線**：任何新模型/特徵都要在 `train.py` 的時間切分回測上與 Marcel 比較，**回測印出的對照表必須顯示新模型勝出**才可採用。
2. **嚴禁資料洩漏** [data leakage]：特徵只能用 `target_year` 之前的資料。回歸均值用 `target_year - 1` 的聯盟 rate，切分用 `TEST_FROM`（target_year ≥ 此值為測試）。
3. **計數型 vs rate**：目前只預測 rate stat。計數型（HR、RBI 總數）需先有上場時間模型，未做前不要硬湊。
4. **產出持久化**：模型 metrics 寫 `cpbl.model_versions`，預測寫 `cpbl.projections`（回測列填 actual，下季投影 actual 為 NULL）。模型檔存 `ARTIFACT_DIR`。

### 賽果預測（`models/outcome.py`）— 互動式特徵子集

1. **不訓練黑箱再讓使用者關特徵**（統計上錯誤：模型沒學過缺特徵的世界）。正解是
   使用者選定子集後**即時 fit 一個只用該子集的邏輯回歸**，回傳該組合的回測準確率。
2. **`home_field` 控制 intercept**，不是當欄位標準化（常數欄標準化後會被歸零，主場
   優勢會消失）。選它 = `fit_intercept=True`；不選 = 強制 50% 基準。
3. **誠實第一**：永遠同時回傳「全押主場」基準準確率對照。單場勝負天花板 ~60%，
   產品價值在透明與教育，不是擊敗賭盤——禁止用浮誇數字包裝。
4. **leakage**：特徵全在 `features/outcome.py` 以逐場 running state 於「套用該場結果前」
   算出；completed 判定為 `home_score + away_score > 0`（未開打為 0-0）。

### API

1. **`/api/info` 不可拋錯**：這是主站 InfoPoller 契約，任何情況回 200；資料未就緒時 status 退化為 `maintenance`、metrics 盡量帶。
2. **唯讀**：API 只做查詢，不觸發訓練/寫入（訓練是離線批次 `cpbl-train`）。
3. **metrics 設計**：`/api/info` 的 metrics 刻意展示「活的 ML 系統」（model_version、回測 MAE、投影數）。新增展示指標時延續此精神。

---

## 子專案契約（與主站整合）

`GET /api/info` 必須回傳（主站 5 秒 timeout、非 200 視為不可達）：

```json
{ "status": "running", "version": "0.1.0", "metrics": { ... } }
```

- `status`: `running` | `maintenance` | `stopped`
- `metrics`: 自由 JSONB，主站原樣存 Redis（`project_info:{id}`，TTL 10min）

整合步驟見主站 `docs/SUB_PROJECT_GUIDE.md`。重點：Nginx 用**精確比對**
`server_name cpbl.ruan-ruan.com`（優先於 wildcard）；`info_endpoint` 用 Docker 內網
URL（`http://cpbl-analytics:4001/api/info`）。

---

## 資料來源地貌（爬蟲擴充前必讀）

| 來源 | 內容 | 技術特性 |
|---|---|---|
| `github.com/ldkrsi/cpbl-opendata`（MIT） | **逐年** 球員/球隊成績，1990-2024 | 現成 CSV，已用於回填 |
| `cpbl.com.tw`（官網主站） | 逐場 box score、賽程 | **Vue SPA**，資料走內部 AJAX，初始 HTML 無資料 → 純 requests 解 HTML 行不通 |
| `stats.cpbl.com.tw`（官方進階數據） | TrackMan 進階指標 | 獨立站，Phase 2+ |

### 官網逐場 endpoint（已實測確認，見 `ingest/cpbl_site.py`）

純 HTTP，**不需 headless browser**。流程：

1. `GET /schedule` → 拿 session cookie + 從 inline JS 抽 token：
   正規表式 `RequestVerificationToken:\s*'([^']+)'`。
   ⚠️ **不是** hidden input 的 `__RequestVerificationToken`（那個會 500）。
2. `POST /schedule/getgamedatas`：
   - Header：`RequestVerificationToken: <上面抽到的 token>`（放 header，非 body）
   - Body：`calendar=YYYY/01/01` + `location=` + `kindCode=A`（A=一軍例行賽）
   - 回 `{"Success": true, "GameDatas": "<JSON 字串>"}`，GameDatas 需**二次** `json.loads`。
3. 回傳含 GameSno / 比分 / 主客隊 / 先發投手 / 勝敗投（`*Acnt` 即 player_id）。

擴充其他資料（box score 打席明細）時沿用同一 token 流程；官網改版導致抽不到
token 時 `_new_session()` 會丟錯，據此判斷需更新正規表式。

---

## Roadmap

- **Phase 1（已完成）**：opendata 回填 + 打擊成績預測（Marcel vs LightGBM）+ `/api/info` + 投影查詢。
- **Phase 1.5（已完成）**：官網逐場爬蟲（games 表，含比分/先發投手）；獨立 Next.js 前端（投影排行 + 球員逐年圖表）。
- **Phase 2（已完成）**：**賽果預測** — game_features（leakage-safe）+ 即時 fit 特徵子集探索器（`/predict` 頁 + `/api/v1/outcome/*`）+ 今日賽事勝率預測。
- **Phase 3（下一步）**：投手成績預測；box score 打席明細；進階數據（TrackMan）；`/api/info` 併入賽果模型指標。
- **Phase 4**：submodule + compose + nginx 接主站正式上線（前端走 cpbl 子網域）。

---

## Git 版控準則（對齊主站）

1. **Conventional Commits**。標題行英文、祈使句、小寫開頭、不加句點；body 用繁體中文說明「為什麼」。
   - type：`feat` `fix` `refactor` `docs` `chore` `test` `ci` `perf`
   - scope：`ingest` `features` `models` `api` `infra`（可省略）
2. **一個邏輯變更一個 commit**。
3. **嚴禁 commit**：`.env`、`data/`、`artifacts/`、`.venv/`、credentials。
4. push 前確認 `uv run ruff check` 通過、`cpbl-train` 回測未退化。

---

## 給 AI 的工作備忘

- 條件不足強制反問，**嚴禁腦補**資料欄位 / 官網結構（先用 gh/WebFetch 查證）。
- 觀點或前提有誤直接指出（例：有人要求用 opendata 做賽果預測 → 必須指出資料粒度不符）。
- 改完跑驗證：`uv run ruff check` + 容器內 `cpbl-train` 看回測對照表。
- 涉及 LightGBM/原生相依，預設容器內執行，不在 macOS host 裝 build 依賴。
