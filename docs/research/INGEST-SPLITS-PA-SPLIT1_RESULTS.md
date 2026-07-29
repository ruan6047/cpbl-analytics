---
title: "INGEST-SPLITS-PA-SPLIT1 分項重算是否同樣重複計打席"
card_id: INGEST-SPLITS-PA-SPLIT1
status: awaiting-independent-review
role: executor（Claude Fable 5）
date: 2026-07-30
iteration: 2
tags:
  - cpbl
  - splits
  - data-correctness
---

# 結論：**有偏差，已量化到選手層級**

`splits_calc.py` 因與 `GAME-RECAP-PA1-FIX1` 同型的島切分缺陷而重複計打席。
全量數字（2018–2026、kind A/C/D/E、4,279 場／1,334,970 事件，
`scripts/verify_splits_pa_split1.py` 產生，逐筆入 `ingest_splits_pa_split1_metrics.json`
與 `ingest_splits_pa_split1_player_delta.json`）：

| 項目 | 數值 |
|---|---:|
| canonical 跨打者 transition（`build_islands` 列舉） | **296** |
| ↳ prev 片段被幽靈島規則擋掉 | 210 |
| ↳ prev 片段整段無 `batting_action_name` 略過 | 3 |
| ↳ **實際被重複計為 PA** | **83 筆／82 場**（A:43、D:37、C:2、E:1） |
| H1 打序位移：受影響 (場次, 球隊) | **82**（最大位移 2：`2020/A/22` 客隊） |
| H1：其後被錯誤歸類打序的 PA | **1,291 筆** |
| 選手層級 delta（見下） | **8,737 個非零格／337 位選手** |

逐年：2018:7／2019:8／2020:13／2021:5／2022:14／2023:16／2024:8／2025:10／2026:2。
重複記的結果詞前幾名：三振 34、四壞 11、一安 7、投滾 4、游滾 4、右飛 3、中飛 3、界飛 2。

**與開卡基線一致（83／82 場）**——iteration 1 的 61 筆「作廢開卡數字」的宣告是錯的，見下節。

## iteration 1 為何得到 61（查核 Critical 的複現與根因）

iteration 1 直接拿 **legacy island 的 prev** 呼叫 `continues_same_plate_appearance()`。
但該判準的 `pinch_hit_slot` 路徑要求「`更換代打` 公告列附掛於前一島」
（`_trailing_change_rows(island)`）；legacy 切法以 `(inning, vh, hitter)` 切界，
公告列帶著**新打者**的 acnt，一律被切進**後一島**——因此 legacy prev 的尾端永遠沒有公告列，
`pinch_hit_slot` 全數漏判，只剩 `count_continues` 能命中。61 筆是正確 83 筆的**真子集**
（本輪 artifact 逐筆比對舊 `3b07d04` artifact：61 ⊂ 83，漏 22 筆）。

本輪改法（查核者的處置建議）：先以 canonical `build_islands()` 列舉 296 個真實 transition
（島內相鄰成員列打者相異 ⇔ 一次被接受的合併），再映射回 `splits_calc.flush()` 實際切出的
legacy island（映射逐筆檢核：全部 transition 的 prev/next 都落在**相鄰** legacy island，
`anomalies` 為空；每筆 counted prev 的 next 島也都 counted，即真雙計而非單純錯歸屬）、
依 flush 原始順序執行三道過濾。去向 210／3／83 與查核者獨立重現值完全一致。

## H1 成立：82 個 (場次, 球隊)、1,291 筆後續 PA 打序被污染

`flush()` 以 `pa_seq` 累加重建打序（`order = seq % 9 + 1`）。多出的 PA 使該隊其後所有 PA
的打序歸屬整體位移 1；`2020/A/22` 客隊同場有兩筆 spurious，位移量 2。
重複計數本身 83 筆，但污染面是 1,291 筆的家族 10（`ORDER_NAMES`）分箱——
這在選手層級 delta 中同樣是最大宗（8,737 個非零格中家族 10 佔 5,776）。

## 選手層級量化（iteration 1 Finding 2 的補交付）

方法：在腳本內以 **named-column 模擬器**重現 `calc_t2`，並以「與 `calc_t2` 輸出逐格相等」
作保真閘（18 個已發布 (year, kind) 全數通過，見 artifact `simulator_fidelity_vs_calc_t2`）；
再以 corrected 模式（僅合併 83 個 counted 缺陷邊界，歸屬引用 canonical `charged_hitter`）
在**記憶體中**重算，與 legacy 逐格相減。**未寫任何表**（`db_scope: read` 維持；
artifact `readonly_guard` 記錄四張分項表執行前後筆數與 `max(updated_at)` 不變）。

- **8,737 個非零格／337 位選手**，逐格明細（選手 × side × family × `item_name` × 欄位 ×
  legacy/corrected/delta）在 `ingest_splits_pa_split1_player_delta.json`。
- 分布：打者家族 10（棒次）5,776 格、家族 3/4/5/6/7 共 1,734 格；投手家族 3/5/6/7/8 共
  1,158 格；家族 1/8/9 的 go/fo 補充 69 格。
- 影響最大者（Σ|delta|）：高國麟 174、范國宸 158、鄭鎧文 156、李宗賢 154……（見 artifact
  `player_delta_summary.top_players_by_abs_delta`；大值全來自家族 10 的整段位移）。
- 單一選手單格的重複計數幅度多為 ±1（一個 PA 的量）；打序位移則是「整段搬家」
  （某棒次的整條 season line 少一筆、鄰棒多一筆），對家族 10 的比率欄影響最可見。
- 範圍註記：3 場 C/E（`2022/C/2`、`2023/E/1`、`2024/C/2`）**無年度分項表**
  （`batting_splits` 僅 2018–2026 × A/D ＋生涯 9999），不產生已發布偏差；
  生涯 9999 的 base 錨定官方且 C/E 凍結、accrual 僅取本季 A/D，故生涯目前僅經
  2026 A/D 的 2 場受影響（跨年 roll 前若未修正，歷史偏差將被捲入 base）。

### box 逐場交叉驗證（外部對照，非自比）

以官方逐場 box（`batting_gamelog`，爬蟲直寫、不經 `splits_calc`）對 82 個受影響場次
逐人對照單場 PA（寬過濾：任一版本 ≠ box 即列）：

- **legacy 有 88 筆逐人不吻合；corrected 後只剩 7 筆**（artifact `box_crosscheck`）。
- 7 筆殘留中：2 筆是 `2018/A/116` 的官方歸屬偏離（見 H3）；5 筆是 legacy 同樣存在的
  背景低估雜訊（splits＜box，方向與本缺陷相反，iteration 1 已觀察到、成因另案）。
- iteration 1 在 2025/A 家族 4 對照中「無法解釋的 `0000001754` +1」**本輪已解釋**：
  `2025/A/68` 正是漏掉的 22 筆之一（1754 的二滾片段被雙計）。corrected 後
  2025/A 的 splits＞box 殘差**全數消失**。

## H2：當前 harness 是自比；當年對帳**不可重現**，且多數受影響場次從未被對過帳

**當前對照組**：`cpbl-verify-splits` 讀 `batting_splits` 等表當「官方值」，
但 `cpbl-build-splits` 自 2026-07-06（Phase 1，commit `36e3334`）起把重算值寫回同一批表
且含於每日 refresh——**當前跑 harness 是重算值自比，零資訊**（紅線 2 成立，
iteration 1 此判定正確）。本卡的外部對照因此改用 box（上節）。

**當年對帳是否涵蓋受影響場次**——分三類，皆有出處：

1. **2018–2025 年度分項（77 場 A/D）：從未對過帳。** 官方 apart 頁只爬過
   `(2026, A)` 與生涯 9999（`cpbl_player_detail.py` `APART_COMBOS` 常數）；
   2018–2025 的 `batting_splits`／`pitching_splits` 列是 2026-07-14 由 VENUE-PARK1
   `cpbl-build-splits <year>` 回填的**純重算值**（該年度全部列 `updated_at` = 2026-07-14，
   本輪 DB 實查；VENUE-PARK1 結案紀錄見 `docs/archive/TASKS_ARCHIVE.md` L123–130）。
   DB 中從來不存在這些年份的官方年度分項值。
2. **2026/A/58（06-24，kind A）：名義上在 Phase 0 對帳母體內，但結果不可考。**
   Phase 0 harness（2026-07-06，commit `3a66169`）對照的是當時新爬的 2026/A 官方值，
   收斂後仍有 **3,248 筆殘差**，僅以 commit message 的總量數字留存
   （「T2 各家族 91–98.6%，殘差大宗歸因官方端快照滯後」），**無逐格 artifact**——
   無法判定本場的 ±1 當時是否被看見或被歸因掩蓋。
3. **2026/D/131：從未有官方對照。** 官方 apart 本季僅 A 有資料
   （`cpbl_player_detail.py` L197 註）。

**可重現快照：不存在。** 已查找的證據範圍：

- 本機 DB：官方爬值於 07-06 被 Phase 1 `DELETE+INSERT` 覆寫，其後每日 refresh 持續覆寫。
- 生產 DB：07-14 起由本機同步（VENUE-PARK1 結案紀錄），無獨立官方副本。
- 備份：`scripts/backup-cpbl-prod.sh` 輪替保留 7 份，現存最早 `cpbl-prod-20260725-*.sql.gz`
  （2026-07-25），全部晚於 07-06 覆寫。
- git：無任何官方分項值或 harness 逐格輸出的 committed artifact（`docs/`、repo 全樹搜尋）；
  Phase 0 結果只存在於 commit `3a66169` 訊息。
- raw payload：`cpbl_player_detail` 解析後直接 upsert，無 apart 頁快照表
  （migrations 全查，僅 `*_splits_career_base` 為官方錨定值，係生涯層級、非年度）。

**恢復路徑（供修正卡）**：官方站 `/team/apart` 仍提供 year × kindCode 下拉
（`docs/CPBL_SITE_MAP.md` L196），修正後可另開爬卡取歷年官方值作驗收對照；
在那之前，box（`batting_gamelog`）是唯一未被污染的既有對照，本卡已實證其可用性。

## H3：官方口徑——只計一個打席；歸屬依 9.15(b)，**含打席數本身**

規則原文（`docs/reference/棒球規則.txt` p.170–171）：

> 9.15(b)「擊球員於第 2 好球後退出，替代的擊球員以三振完成打擊，記為**最初擊球員**的
> 三振與打數，若替代擊球員以其他結果完成打擊（包括四壞球），皆視為**該替代擊球員**之行為。」
> 【註】「同一打席中分別由 3 位球員替換出場打擊，最後被三振時，其中**被判第 2 好球**之
> 擊球員，應被記為三振及打數。」
> 9.14(a)原註「……若四壞球關係到 2 名以上之代打員時，參照 9.15(b)之規定。」

83 筆的結果詞路徑窮舉（紅線 4）：**三振 34 筆**走 9.15(b) 前段
（其中 22 筆原打者已被判第 2 好球 → 歸原打者；12 筆代打者自吃第 2 好球 → 歸代打者；
不死三振變體 0 筆，`STRIKEOUT_ACTIONS` 已涵蓋）；**四壞 11 筆**走 9.14(a)原註 → 9.15(b)
後段歸代打者；**其餘 38 筆**（安打／滾飛出局等）皆為「其他結果」→ 歸代打者。
歸屬判定引用 canonical `charged_hitter`（`pa_build.py`，FIX1 定案），不重新定義。

**修正 iteration 1 的一個詮釋錯誤**：iteration 1 據 `2025/A/84` box（7091 `PA=1, AB=0`）
推論「官方把打席數記給完成者」。本輪逐場重算證明該 PA=1 其實是 7091 **10 局自己的犧短**；
被中斷打席的 PA 與 AB/SO 一併記給被判第 2 好球者 6738（box `PA=3=AB`；
若 PA 記完成者會得出 6738 `PA=2 < AB=3`，違反 PA≥AB 恆等式）。
「官方只計一個打席」的結論不變，但**歸屬是整個打席跟著 9.15(b) 走**——
與 canonical PA 表把 `hitter_acnt` 記給 charged 的語意一致。

**已知官方實務偏離一例**：`2018/A/116` 7 局下，3551 於 1-2（第 2 好球為其揮棒落空）退場、
1240 接手看第 3 好球——依 9.15(b) 應記 3551，但官方 box 把完整 K（`PA=1,AB=1,SO=1`）
記給 1240、3551 該打席零記錄（livelog 逐球與 box 皆在 artifact/本文佐證）。
2025 年官方（84 場）則正確依規則。此為官方端記錄實務不一致，
量化影響＝該場兩人各 ±1 PA/AB/SO 的歸屬差；修正卡需決定跟規則還是跟官方單場實務。

## 邊界與未做

- **本卡未修**（紅線 5）：`splits_calc.py` 零改動；未跑 `cpbl-build-splits`；
  未寫任何分項表（artifact `readonly_guard` 前後全等）。
- box 對照的背景低估雜訊（splits＜box，受影響場次內共 5 筆逐人；2025/A 季總淨 −15）
  與本缺陷方向相反、corrected 前後不變，成因未查明，屬另案。
- `2019/A/173`（已知來源損壞場）不在 82 場之列（artifact 可查）。

## 建議

開修正卡（`db_scope: data-migration`）：`splits_calc.flush()` 切界改引用 canonical
`continues_same_plate_appearance`／`build_islands`，歸屬引用 `charged_hitter`，
重算 2018–2026 × A/D 四張分項表＋生涯 accrual。驗收對照建議：
(1) 本卡的 box 逐場交叉驗證腳本（88 → 7 應可複現）；
(2) 選手層級 delta artifact 作為預期變更清單（重算前後 diff 應與其一致）；
(3) 若需官方年度分項對照，另開爬卡取 `/team/apart` 歷年值（見 H2 恢復路徑）。
`2018/A/116` 的官方偏離一例需在修正卡中裁定歸屬口徑（規則 vs 官方實務，幅度 1 PA）。
