# UX-TEAM-FIELD-HIST1 球隊頁歷史年守備位置圖〔T3；🟡資料補齊〕

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/UX-TEAM-FIELD-HIST1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：v0.2
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：讓球隊頁「賽季」頁籤在**歷史年度**也能顯示主力選手的守備位置圖。

## 背景（資料現況，勿腦補）

- `UX-TEAM-SPLIT-SCOPE1` 已為球隊頁加上年度軸（`?year=`，2018–當季 ∩ franchise 活躍年），
  賽季各區塊隨年度變動。
- 但「主力選手」的**守備位置圖**讀 `/api/v1/season/fielding`（來源 `fielding_current`），
  而 `fielding_current` **僅 2025–2026**；故 2018–2024 年度目前顯示退化文案
  「〈年〉年守備位置圖尚未提供（歷史守備待補）」（明示退化，不顯示誤導值）。
- `fielding_seasons` 有 **1990–2024**。補齊需 union 兩表並**對齊守位碼**
  （作法可參考守備生涯彙總：union 兩表 + 守位碼對齊）。
- DH 推算需維持既有語意：DH 不在守備資料，主守位須用「打擊出賽 − 守備出賽」推算，
  否則純 DH 球員會誤判為舊守位。

## 驗收條件

- [ ] 2018–2024 各年度球隊頁守備位置圖有值，且與官方該年守備出賽一致（抽驗數隊 × 數年）。
- [ ] DH 判定（打擊出賽 vs 守備出賽比例）在歷史年同樣成立，純 DH 球員不誤標舊守位。
- [ ] 當季（2025–2026）行為與數值**零回歸**。
- [ ] 兩表 union 不產生重複列或守位碼錯位；改名/轉隊球員歸屬正確。

## 驗證與依賴

- 驗證：多年度走查、`ruff`＋`pytest`（若動端點同步 `tests/test_route_snapshot.py` EXPECTED）、`tsc`、`build:check`。
- 依賴：UX-TEAM-SPLIT-SCOPE1（年度軸，已合併）。
- 預估範圍：S～M（後端聚合 union + 前端沿用既有 `FieldDiagram`）。

## Log

- 2026-07-25 註冊：源自 UX-TEAM-SPLIT-SCOPE1 上線後的已知缺口（需求方指示登記 follow-up）。
