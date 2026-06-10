# CPBL Analytics

中華職棒（CPBL）資料管線、本季數據與**單場賽果預測**。
PersonalWebsite 主站的子專案,透過 `/api/info` 掛載到子網域並被主站 `InfoPoller` 輪詢。

## 這是什麼

- **資料**:歷史逐年由 [`ldkrsi/cpbl-opendata`](https://github.com/ldkrsi/cpbl-opendata)(MIT)回填;逐場結果與本季投打/團隊進階由官網爬蟲補足。
- **賽果預測**:選變因(勝率/得分/失分/近況/對戰/先發投手 ERA·WHIP·K9)→ 看雙方真實數字 + 主隊勝率;權重「歷史學出預設 + 手動微調」,誠實呈現單場 ~60% 的可預測天花板。
- **成績預測**(打擊 projection):Marcel baseline vs LightGBM 時間切分回測(保留中)。
- **服務**:FastAPI `/api/info`(子專案契約)+ `/outcome/*` + `/season/standings`。

> ⚠️ 賽果(勝負)預測需要逐場資料,cpbl-opendata 沒有,留待官網爬蟲就緒(Phase 2)。

## 架構

```
cpbl-opendata CSV ──(ingest)──▶ PostgreSQL (schema: cpbl)
                                      │
                          (features) ▼
                    aging curve + 回歸均值
                            ┌─────────┴─────────┐
                       Marcel baseline      LightGBM
                            └─────────┬─────────┘
                          時間切分回測 (MAE/RMSE)
                                      │
                                FastAPI /api/info
```

## 快速開始(本地)

```bash
# 1. 安裝 uv（若尚未安裝）: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync                                   # 建虛擬環境 + 裝依賴

# 2. 起本地 PostgreSQL
docker compose up -d db

# 3. 套 migration + 回填歷史(1990–2024)
cp .env.example .env
uv run cpbl-backfill

# 4. 爬官網逐場賽程/結果（解鎖賽果預測的 game-level 資料）
uv run cpbl-scrape-games 2023 2026    # 純 HTTP，無需 headless browser

# 4b. 爬本季投手/打者進階 + 團隊數據（先發 ERA/WHIP/K9、團隊 OPS/ERA/WHIP）
uv run cpbl-scrape-stats 2025 2026

# 4c. 建賽果預測特徵表（leakage-safe）
uv run cpbl-build-features

# 5. 成績預測：訓練 + 回測(印 Marcel vs LightGBM 對照表)
uv run cpbl-train

# 6. 起 API
uv run uvicorn cpbl.api.main:app --reload --port 4001
# → http://localhost:4001/api/info

# 7. 起前端（另開終端機）
cd web && npm install && API_URL=http://localhost:4001 npm run dev   # → :3000
```

## 前端（`web/`）

獨立 Next.js 15 app（App Router + Tailwind v4）。頁面:
- `/` 本季戰績榜（勝負/勝率/得失差 + 團隊 OPS/ERA/WHIP，Server Component）
- `/predict` **單場對戰預測卡**（Client）:今日賽事 + 任選兩隊模擬;勾變因、拖權重、看雙方真實數字與先發投手 ERA

## 專案結構

```
src/cpbl/
├── config.py             # 設定（env）
├── db.py                 # psycopg pool + migration runner
├── ingest/opendata.py    # cpbl-opendata 逐年回填（冪等 UPSERT）
├── ingest/cpbl_site.py   # 官網逐場爬蟲（anti-forgery token + getgamedatas）
├── features/batting.py   # 特徵工程（lag 1~3 季 + 年齡 + 聯盟均值）
├── models/marcel.py      # Marcel baseline
├── models/train.py      # LightGBM 訓練 + 時間切分回測 + 持久化
└── api/main.py          # FastAPI（/api/info + 查詢）
migrations/001_init.sql  # cpbl schema（season-level + ML 表）
```

## 整合到主站(Phase 3)

見主站 `docs/SUB_PROJECT_GUIDE.md`。重點:
1. 主站以 `git submodule` 把本 repo 掛在 `apps/subprojects/cpbl-analytics/`。
2. `docker-compose.prod.yml` 新增 service,`DATABASE_URL` 指向主站 postgres。
3. Nginx 加**精確比對** `server_name cpbl.ruan-ruan.com` block(優先於 wildcard)。
4. Admin API 建 project 記錄,`info_endpoint=http://cpbl-analytics:4001/api/info`。

## 資料來源與授權

歷史資料來自 [`ldkrsi/cpbl-opendata`](https://github.com/ldkrsi/cpbl-opendata)(MIT)。本專案僅供學習與個人作品集用途。
