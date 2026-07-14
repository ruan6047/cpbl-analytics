# VENUE-PARK1 — API Contract 與資料驗證報告

> 供 UX-VENUE1 直接消費的契約 + 本卡資料回填/方法論的驗證留痕。
> 方法論紅線同步寫在 `src/cpbl/api/routers/venues.py` 模組 docstring，改公式先讀。

## 1. API Contract（3 個新端點，全 GET、唯讀）

`{venue}` 用**短名**（`games.venue`／`venue_dim.venue` 口徑，如 `大巨蛋`、`新莊`）。
歷史別名自動歸一：`桃園`→`樂天桃園`、`亞太副場`→`亞太副`（同座球場）。
查無資料回 404。

### 1.1 `GET /api/v1/venues/{venue}/factors?from_year=2018&to_year=<今年>`

Park factor（主客對照法），一軍例行賽（kind A），逐季＋跨季合併。

```jsonc
{
  "venue": "大巨蛋", "kind_code": "A", "from_year": 2018, "to_year": 2026,
  "method": "matched-team",
  "method_note": "…", "data_floor_note": "逐場資料自 2018 年起…",
  "seasons": [{
    "year": 2024, "games": 38.0, "low_sample": false,   // < 30 場 → true
    "factors": {                                          // r/hr/xbh/h/bb/so 六項
      "hr": {"observed": 29.0, "expected": 42.1, "pf": 0.689}
    }
  }],
  "pooled": { "games": 124.0, "low_sample": false, "factors": { /* 同上結構 */ } },
  "excluded_team_games": 0    // 無法估基準而排除的隊-場數（該隊該季只在此場打）
}
```

- **PF > 1＝該球場放大該事件**；`xbh`＝二安+三安（不含 HR）。
- **公式**：observed＝該場所有「隊-場」的事件合計；expected＝Σ(該隊同季其他球場
  場均 × 在該場場數)；PF＝obs/exp。合併＝分季 obs/exp 各自加總再相除。
- **UI 義務**：`low_sample=true` 必須可見（如淡化/標籤）；顯示 `games` 樣本；
  文案禁止寫成因果斷言（「不容易全壘打」→「HR 產出低於同隊他場基準 34%（124 場）」）。

### 1.2 `GET /api/v1/venues/{venue}/stats?from_year=2018&to_year=<今年>`

球場打擊環境逐年（splits 球場 family 全選手合計）＋聯盟同年基準。

```jsonc
{
  "venue": "新莊", "item_name": "新北市立新莊棒球場", "kind_code": "A",
  "seasons": [{ "year": 2024, "pa": 4124, "ab": …, "h": …, "hr": …,
                "doubles": …, "triples": …,
                "avg": 0.271, "obp": 0.34, "slg": 0.359, "ops": 0.699,
                "hr_pct": 1.4, "so_pct": 17.8, "bb_pct": 8.9,
                "go": 1063, "fo": 1074, "go_ao": 0.99 }],
  "league": [ /* 同結構，全球場合計＝聯盟基準，同年對照 */ ],
  "note": "GO/AO＝滾地/飛球型非安打擊球比（官方口徑，含失誤上壘與犧打）…"
}
```

- **GO/AO 是官方口徑**（滾地/飛球型非安打擊球，含失誤上壘與犧打），
  不是逐球 batted-ball GB/FB——前端命名用「滾飛出局比 GO/AO」，勿寫「滾飛球比」。

### 1.3 `GET /api/v1/venues/{venue}/players?role=batting|pitching&min_pa=100&min_outs=90&limit=8`

在該球場生涯表現與自身生涯基準差距最大的選手（兩端各 `limit` 名）。

```jsonc
{
  "venue": "大巨蛋", "item_name": "臺北大巨蛋", "role": "batting",
  "thresholds": {"min_pa": 100, "min_outs": 90},
  "best":  [{ "player_id": "…", "name": "李凱威", "venue_pa": 208,
              "venue_avg": 0.339, "venue_ops": 0.8303, "venue_hr": 2,
              "career_pa": 2648, "career_ops": 0.7306, "delta_ops": 0.0997 }],
  "worst": [ /* 同結構，delta 最負端 */ ],
  "note": "生涯口徑（官方分項 year=9999，含 2018 以前）…"
}
```

- 投手欄位：`venue_ip / venue_era / venue_k_pct / career_ip / career_era / delta_era`
  （delta_era 越負＝該球場防禦率越好；`best` 已按此排序）。
- **資料為生涯口徑且涵蓋 2018 以前**（來源＝官方生涯分項，非本卡重算）。
- **UI 義務**：差距是描述性統計，不是能力/剋場結論；`venue_pa`/`venue_ip` 必須同列顯示。

### 1.4 既有端點（不變）

球場規格（座席/外野距離/室內/主隊/場均觀眾）沿用 `GET /api/v1/venues` 列表，
UX-VENUE1 以短名自列表挑出該場。

## 2. 資料回填驗證報告（2018–2025 splits）

### 2.1 執行方式與範圍

- 直接呼叫 `build_splits(year, ("A","D"))`，2018–2025 逐年，每年每 kind 單一交易
  DELETE+INSERT（冪等，可重跑）。
- **刻意不跑 `build_career`**：生涯(9999)＝base＋**2026 本季**，base 錨定於 2026 快照；
  若對歷史年呼叫會把生涯表改寫成 base+該年。⚠️ `cpbl-build-splits <year>` CLI 會
  連跑 build_career，**歷史回填不可用該 CLI**，須直接呼叫 `build_splits()`。
- C/E（季後賽）未回填：與現行本季 build 口徑一致（kinds 預設 A/D）；PF 亦不含季後。

### 2.2 結果（全綠，零未知詞彙）

| 年 | A bsplit/psplit | A PA | D bsplit/psplit | D PA |
|---|---|---|---|---|
| 2018 | 5137/3621 | 18,865 | 5215/3372 | 9,533 |
| 2019 | 5290/3937 | 18,791 | 6622/4476 | 11,694 |
| 2020 | 4707/3397 | 19,315 | 9268/6117 | 18,303 |
| 2021 | 7181/5044 | 22,982 | 7665/5054 | 12,916 |
| 2022 | 7406/4930 | 22,805 | 10007/6433 | 12,972 |
| 2023 | 6980/5101 | 22,867 | 9005/6410 | 17,876 |
| 2024 | 8147/6054 | 27,403 | 8390/6124 | 16,679 |
| 2025 | 8077/5941 | 27,024 | 8631/6545 | 15,754 |

PA 量級核對：一軍 240 場季 ≈18.8k、300 場 ≈23k、360 場 ≈27k（≈78 PA/場）✓。

### 2.3 歷史詞彙補丁（14 詞，逐詞 content 原文定案）

安打型：`內二`（二壘內野安打→2B）、`場三`（三壘場地安打→3B）。
滾地型（→go）：`三殺`、`中滾/左滾/右滾`（外野手處理滾地球）、`投/捕`（觸擊截斷詞）、
`雙誤`（雙殺打上壘-失誤上壘）、`觸傳球`（＝三呎線語意）、`觸球`（碰觸界內球出局）。
飛球型（→fo）：`飛`（截斷詞）、`犧飛誤`（犧飛+失誤，計 sf）。
**不歸滾飛**（比照「違規」）：`失`（失誤上壘無守位前綴，滾/飛逐例不一，不猜方向，
2018–25 A/D 共 28 例）、`裁決`（促請裁決/打序錯誤出局，5 例）——此 ~33 例 PA/AB 有計、
go/fo 缺口為已知且可忽略（單年 <0.02% PA）。

### 2.4 已知限制（誠實揭露，UI 必守）

1. **歷史年重算無官方同刻快照可對照**（官方 apart 只有本季）。信任鏈＝T1 官方
   單場 gamelog 加總（無重建）＋ T2 詞彙 fail-loud＋同一引擎已通過 2026 官方對照
   harness（GO R²=0.91 擬合定案，見 splits-recompute-semantics）。
2. **資料下限 2018**：1990–2017 無逐場歸因，任何球場統計不含該期間；
   選手極端表現例外（官方生涯分項含全生涯）。
3. **樣本小是常態**：單球場單季 4–66 場；low_sample 旗標與 games 數是契約的一部分。
4. **僅本機 DB**：生產未同步（歷史資料照慣例先不同步；splits 為 derived，
   同步時 local→prod 鏡像即可，見 memory splits-recompute-semantics / data-sync）。

### 2.5 PF 抽驗（方向與公認事實一致）

- 大巨蛋 pooled（2024–26，124 場）：HR 0.661、R 0.83 ——顯著壓制，逐季一致
  （0.689/0.592/0.883）；符合 400 呎中外野＋高牆的公認特性。
- 新莊 2024（54 場）：HR 1.33 ——短外野牆，公認 HR 友善。
- 桃園別名合併後 2018–2026 連續 9 季（489 場）、pooled HR 0.998 ——大樣本長期中性。
- 花蓮/斗六/台東等 <30 場一律 low_sample=true。
