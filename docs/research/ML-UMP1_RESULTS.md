---
title: ML-UMP1 好球帶判決差異研究結果
date: 2026-07-15
status: implementation-review-pending
tags:
  - cpbl
  - machine-learning
  - umpire-impact
  - research
aliases:
  - 好球帶判決差異
---

# ML-UMP1 好球帶判決差異研究結果

規格：[[umpire-impact-research]]；任務：[[ML-UMP1]]。

## 判決

| 層級 | 結論 | 理由 |
|---|---|---|
| count-aware run-value 引擎 | **GO（研究元件）** | 2025 untouched test 的 NLL 勝過 count-agnostic baseline，MAE 未退化 |
| count-aware WP | **NO-SHIP** | Brier／LogLoss 點估計雖略優，但兩者 game-cluster 95% interval 都跨 0 |
| 固定代理帶的主審／球隊方向性產品 | **NO-GO** | 18/18 主審、6/6 球隊在 ±1/2/3/5cm 情境至少一次翻轉；2026 場次 coverage 僅 82.5% |
| API／UI／production table | **不得進入** | 固定代理帶不是規則真值，且獨立跨家族實測查核尚未完成 |

本研究的正值只代表「實際判決相對 `fixed_zone_proxy_v1`，提高打擊方的聯盟平均狀態價值」。它不是實際增加的得分、因果效果，也不是裁判好壞排名。

## 資料與排除 waterfall

資料快照為 2026-07-15，一軍例行賽 A。

| 階段 | 顆數 | 相對前一步 |
|---|---:|---:|
| TrackMan called pitches | 24,270 | — |
| 有進壘位置 | 24,270 | 100.000% |
| TrackMan ↔ livelog 唯一連結 | 24,195 | 99.691% |
| 唯一連結後合法 post-count | 24,192 | 99.988% |
| 最終可評分 | 24,192 | 99.679% of raw |

另計的全體合法 post-count 為 24,226／24,270（99.819%）；其中 41 顆同時落在非唯一連結，故 waterfall 依「先唯一連結、再球數」只排除 3 顆，避免重複計數。唯一連結列的 catcher／半局／賽前比分缺值為 0。

歷史建模資料：2018–2025 共 2,335 場、645,705 個合法 pre-pitch states；每場最後半局一律排除，避免再見或資料截斷系統性低估 remaining runs。完整支持集最大觀察值為 13 分，沒有沿用 production `K_CAP=6`。

## 模型與時間切分

```text
train       2018–2023  450,447 states
validation  2024        98,271 states
test        2025        96,987 states
scoring     2026        24,192 called pitches
```

`alpha` 只以 2024 multinomial NLL 選擇；候選範圍 1–5,000，最終為 250。2025 test 未參與調參；2026 scoring 使用 2018–2025 final refit。state 分布按 `(side, bases, outs, balls, strikes)` 建立，稀疏格回縮到 `(side, bases, outs)`，再回縮到全域分布。

### Run-value gate

| 2025 metric | count-aware | count-agnostic | 差（候選 − baseline） |
|---|---:|---:|---:|
| multinomial NLL | 0.817024 | 0.817893 | -0.000868 |
| expected-runs MAE | 0.630080 | 0.632828 | -0.002748 |

2,000 次 paired game-cluster bootstrap：

- NLL delta 95% interval：`[-0.001692, +0.000016]`
- MAE delta 95% interval：`[-0.003265, -0.002193]`

預先 gate 要求 NLL 點估計改善且 MAE 不退化，故通過。NLL interval 幾乎貼 0 並略跨 0，證據強度應描述為「小幅且不確定」，不可宣稱顯著優勢。

### WP gate

| 2025 metric | count-aware | 現有 state baseline |
|---|---:|---:|
| Brier | 0.161367 | 0.161402 |
| LogLoss | 0.483381 | 0.483475 |
| calibration intercept | -0.0874 | -0.0975 |
| calibration slope | 1.2336 | 1.2400 |
| ECE | 0.02946 | 0.03052 |

2,000 次 paired game-cluster bootstrap：

- Brier delta 95% interval：`[-0.000170, +0.000098]`
- LogLoss delta 95% interval：`[-0.000432, +0.000232]`

兩者都跨 0，未達「至少一項 interval 不跨 0」的預先 gate，因此逐球 artifact 的 `wp_ball`、`wp_strike`、`delta_wp_home` 全為 `null`。

十分位 reliability 顯示候選模型在中低機率段偏高估、較高機率段偏低估；例如 0.3–0.4 bin 為預測 0.350／實際 0.283（n=7,764），0.7–0.8 bin 為預測 0.750／實際 0.790（n=7,594）。這與 calibration slope > 1 一致。

## 狀態轉移人工驗算

下表是 2018–2025 final refit 的 `U_R(s, Ball)`／`U_R(s, Strike)`，單位為該半局剩餘得分期望。

| pre-call state | Ball | Strike | Ball − Strike | backoff |
|---|---:|---:|---:|---|
| 0-0、空壘、0 out | 0.5492 | 0.4620 | 0.0872 | false |
| 3-2、空壘、0 out | 0.8902 | 0.2747 | 0.6155 | false |
| 3-2、滿壘、0 out | 3.3047 | 1.6247 | 1.6800 | false |
| 3-2、滿壘、2 out | 1.8009 | 0.0000 | 1.8009 | false |
| 0-2、空壘、2 out | 0.0633 | 0.0000 | 0.0633 | false |

滿壘四壞的 `Ball` 已包含 1 分立即得分與下一打者 0-0 的剩餘價值；兩出局第三好球直接結束半局，故 `Strike=0`。2026 scoring 有 260／24,192 顆（1.07%）因局部估計違反結構單調條件而回退到父狀態。

## 2026 描述性聚合

主分析有 2,661／24,192 顆（11.00%）實際判決與固定代理帶不同；全體 `sum_delta_runs_offense=84.4218`。此總和在主審、打擊方 `state_value_for`、守備方 `state_value_against` 三種聚合完全守恆。

以下依姓名排序，不是排名。區間每次同時重抽歷史場次重建 value table，並重抽 2026 scoring games，共 2,000 replicates。

| 主審 | games | called | proxy diff | point total | bootstrap 2.5% / 50% / 97.5% | zone sensitive | venue sensitive |
|---|---:|---:|---:|---:|---:|:---:|:---:|
| 劉世偉 | 9 | 1,331 | 146 | 3.877 | 0.416 / 3.834 / 8.817 | yes | no |
| 吳家維 | 11 | 1,751 | 185 | 5.717 | 0.501 / 5.401 / 12.503 | yes | no |
| 尤志欽 | 13 | 1,917 | 199 | 5.113 | 0.146 / 4.989 / 11.089 | yes | no |
| 張展榮 | 5 | 725 | 74 | 2.588 | -0.372 / 2.467 / 7.079 | yes | no |
| 彭楚雲 | 9 | 1,362 | 131 | 6.467 | 1.115 / 6.106 / 13.305 | yes | no |
| 木內九二生 | 13 | 1,782 | 211 | 6.381 | -0.782 / 5.944 / 16.730 | yes | no |
| 林金達 | 7 | 1,017 | 124 | 4.639 | -1.006 / 4.247 / 13.631 | yes | no |
| 楊崇煇 | 11 | 1,568 | 178 | 4.757 | -0.175 / 4.646 / 11.278 | yes | no |
| 江春緯 | 11 | 1,763 | 191 | 10.118 | 2.925 / 9.814 / 19.682 | yes | no |
| 王俊宏 | 7 | 997 | 111 | 1.056 | -1.681 / 1.076 / 3.984 | yes | yes |
| 紀華文 | 11 | 1,595 | 162 | 3.855 | -0.480 / 3.743 / 10.015 | yes | no |
| 羅鈞鴻 | 9 | 1,225 | 131 | 0.429 | -3.320 / 0.395 / 4.521 | yes | yes |
| 范元淦 | 8 | 1,198 | 134 | 5.455 | 1.376 / 5.312 / 10.201 | yes | no |
| 蔡豐澤 | 10 | 1,471 | 160 | 6.530 | 2.300 / 6.408 / 11.979 | yes | no |
| 邱景彥 | 9 | 1,311 | 165 | 5.215 | 0.757 / 5.007 / 10.893 | yes | no |
| 鄭惟丞 | 5 | 666 | 75 | 3.918 | -0.124 / 3.580 / 10.946 | yes | no |
| 陳乃瑞 | 7 | 993 | 106 | 2.888 | -1.220 / 2.585 / 7.667 | yes | no |
| 陳均瑋 | 10 | 1,520 | 178 | 5.420 | 0.131 / 4.899 / 12.576 | yes | no |

固定代理帶邊界對稱收縮／擴張 1、2、3、5cm 後，18 位主審與 6 隊的方向都至少翻轉一次；因此上表只能作 audit 描述，不可作方向性結論。Leave-one-venue-out 另使王俊宏、羅鈞鴻翻轉；球隊未因單一球場排除而翻轉。

## Coverage

2026 已完成 200 場中，TrackMan scoring 涵蓋 165 場（82.5%）。主要缺口：

| 球場 | tracked / completed |
|---|---:|
| 嘉義市 | 0 / 6 |
| 花蓮 | 0 / 2 |
| 台東 | 0 / 1 |
| 大巨蛋 | 6 / 20 |
| 亞太主 | 20 / 28 |

天母、洲際、澄清湖為完整覆蓋；其他場地詳見 ignored artifact `artifacts/umpire-impact/summary.json`。在場地缺失可能與球隊／主審排班共同變動時，不能把 observed subset 當成全季隨機樣本。

## 方法限制與來源

CPBL 規則好球帶的垂直邊界依打者站姿而變，但現有 `pitch_tracking` 沒有 `sz_top`／`sz_bot`；因此 `0.253m × 0.423–1.077m` 只重現既有 UI 固定代理帶，不是逐球規則 ground truth。規則依據：[CPBL 2025 棒球規則 PDF](https://cpbl.com.tw/files/file_pool/1/0p065549820043528193/2025%E6%A3%92%E7%90%83%E8%A6%8F%E5%89%87%28%E5%AE%98%E7%B6%B2%E7%94%A8%29.pdf)。

狀態價值與勝率框架參考 count-aware run expectancy／win probability 文獻：[Albert (2010)](https://doi.org/10.2202/1559-0410.1279)、[Deshpande & Wyner (2017)](https://doi.org/10.1515/jqas-2017-0027)。裁判偏誤研究的識別風險參考 [Parsons et al. (2011)](https://pubs.aeaweb.org/doi/10.1257/aer.101.4.1410)，但本研究沒有宣稱因果效果。

## 可重現命令與 artifacts

```bash
uv run cpbl-research-umpire-impact audit --season 2026 --kind A
uv run cpbl-research-umpire-impact validate --kind A --bootstrap 2000
uv run cpbl-research-umpire-impact score --season 2026 --kind A \
  --bootstrap 2000 --output artifacts/umpire-impact
```

- `artifacts/umpire-impact/pitch_audit.jsonl`：24,192 行、約 20MB，不 commit。
- `artifacts/umpire-impact/summary.json`：主審／球隊聚合、bootstrap、zone 與 venue sensitivity，不 commit。
- `model_version=count_run_v1_alpha250_2018_2025`。

下一步不是加 UI，而是由不同模型家族或人工查核者獨立重跑 audit、validation、終結球案例與 artifact 對帳。只有 findings 清零後，run-value 元件才可作後續研究基礎；固定代理帶排行與 WP 仍維持 no-go。
