# ML-UMP2 身高比例逐打者代理帶重跑結果

> 狀態：待跨家族／人工 T4 查核
> 範圍：2026 一軍例行賽，`kind_code='A'`，本機 DB 快照 2026-07-16
> 代理帶：`height_scaled_proxy_v2`，`top=0.535×height`、`bottom=0.270×height`、水平半寬 0.253m
> 價值模型：`count_run_v1_alpha250_2018_2025`，2,000 次 game-cluster bootstrap

## 結論

**方向性產品繼續 NO-GO。**

身高比例帶沒有消除 ML-UMP1 的根本不穩定性：在 v2 帶對稱 ±1/2/3/5cm 後，18/18 位主審與 6/6 隊仍會出現方向翻轉，嚴格零翻轉 gate 失敗。因此不能對外說「本場／本季判決差異偏向 X 隊」，即使不呈現分數也不行。

state value 是聯盟平均狀態價值差，不是實際得失分、因果效果、裁判能力或「裁判送分」。

## 資料 gate

| 項目 | 結果 | 判定 |
|---|---:|---|
| unique-linked called pitches | 24,382 | 母體 |
| distinct hitters | 157 | 母體 |
| 有身高 pitches | 24,382 / 24,382（100%） | PASS |
| 有身高 hitters | 157 / 157（100%） | PASS |
| 無 player／無 height | 0 / 0 pitches | PASS |
| 最終可評分 | 24,379 | 另排除 3 顆非法 post-call count |
| 主審／球隊覆蓋 | 18 / 6 | PASS |
| TrackMan 場次覆蓋 | 166 / 203（81.77%） | 仍有非隨機場地缺口 |

原始 audit 只有 2,400/24,382 pitches（9.84%）與 24/157 hitters（15.29%）有身高；本卡只對精確出現於 called-pitch 母體的 133 位缺身高打者重跑官網 bio ingest，133/133 成功寫入本機 `players`。研究 loader 仍 fail closed，沒有固定帶 fallback。

## 主結果與敏感度

| 檢查 | 結果 | 解讀 |
|---|---:|---|
| v2 proxy disagreements | 2,708 / 24,379（11.11%） | 只是代理帶與實際判決不同 |
| v2 聚合 state value | -158.461 | 不是實際失分 |
| fixed v1 同樣本 state value | +85.693 | v1→v2 中心估計已整體換號 |
| fixed v1→v2 主審換號 | 18 / 18 | 帶定義主導方向 |
| fixed v1→v2 球隊換號 | 6/6 for；6/6 against | 帶定義主導方向 |
| v2 ±1/2/3/5cm 主審翻轉 | 18 / 18 | 主 gate FAIL |
| v2 ±1/2/3/5cm 球隊翻轉 | 6 / 6 | 主 gate FAIL |
| leave-one-venue-out 翻轉 | 主審 0/18；球隊 0/6 | 未挽救 zone 不穩定 |
| home/away 主審翻轉 | 0 / 18 | 非主要失敗來源 |
| month 主審翻轉 | 2 / 18 | 額外時間不穩定 |
| 既有 50cm filter | 排除 1 顆；0 換號 | 不影響結論 |

2,000 次 bootstrap 中，17/18 主審的總 state-value 95% 區間不跨 0，6/6 隊的 for 與 against 區間也都不跨 0。這不能拯救方向性：區間衡量的是「給定 v2 定義」下的抽樣不確定性，而主 gate 失敗是代理帶邊界稍微改變就全面翻轉的定義不確定性。

## 球緣 secondary sensitivity

依官方球周長 22.9–23.5cm 取中點，半徑為 0.036924m；球心到 v2 矩形帶的歐氏距離小於等於半徑即視為觸帶。

- proxy disagreements 由 2,708 降為 2,539。
- 相對 v2 球心主情境，17/18 主審換號、6/6 隊 for 與 6/6 隊 against 換號。
- 此情境依 spec 不進主 gate，但它提供更強的方向脆弱證據。

## 決策

1. 不進 API、UI 或 production table。
2. 不顯示主審／球隊方向性文案，不論是否隱藏數值。
3. `height_scaled_proxy_v2` 可保留為離線研究 scenario，不得晉級為規則真值。
4. 若未來要重啟方向性研究，需新資料來源提供逐球姿態 `sz_top/sz_bot`，不是再調整人為比例。

## 重現

```bash
uv run cpbl-research-umpire-impact audit --season 2026 --kind A
uv run cpbl-research-umpire-impact score-height-v2 \
  --season 2026 --kind A --bootstrap 2000 \
  --output artifacts/umpire-impact-v2
```

ignored artifacts：`artifacts/umpire-impact-v2/summary.json`、`pitch_audit.jsonl`。
