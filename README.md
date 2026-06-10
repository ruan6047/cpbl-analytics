# CPBL Analytics

中華職棒（CPBL）資料管線與**球員成績預測** [projection]。
PersonalWebsite 主站的子專案,透過 `/api/info` 掛載到子網域並被主站 `InfoPoller` 輪詢。

## 這是什麼

- **資料**:歷史逐年成績由 [`ldkrsi/cpbl-opendata`](https://github.com/ldkrsi/cpbl-opendata)(MIT)回填(1990–2024)。
- **模型**:打擊 rate stat(AVG/OBP/SLG/OPS)的成績預測。以棒球界標準的 **Marcel** 為 baseline,**LightGBM** 必須在時間切分回測上打贏它才算有價值。
- **服務**:FastAPI 提供 `/api/info`(子專案契約)+ 投影查詢端點。

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

# 4. 訓練 + 回測(印 Marcel vs LightGBM 對照表)
uv run cpbl-train

# 5. 起 API
uv run uvicorn cpbl.api.main:app --reload --port 4001
# → http://localhost:4001/api/info
# → http://localhost:4001/api/v1/projections/batting?stat=ops
```

## 專案結構

```
src/cpbl/
├── config.py            # 設定（env）
├── db.py                # psycopg pool + migration runner
├── ingest/opendata.py   # cpbl-opendata 回填（冪等 UPSERT）
├── features/batting.py  # 特徵工程（lag 1~3 季 + 年齡 + 聯盟均值）
├── models/marcel.py     # Marcel baseline
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
