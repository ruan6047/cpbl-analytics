---
title: "INGEST-SPLITS-PA-SPLIT1 分項重算是否同樣重複計打席"
card_id: INGEST-SPLITS-PA-SPLIT1
status: awaiting-independent-review
role: executor（Claude Fable 5）
date: 2026-07-30
iteration: 3
tags:
  - cpbl
  - splits
  - data-correctness
---

# 結論：**有偏差，已量化到選手 × 分項 × 全發布欄位**

`splits_calc.py` 因與 `GAME-RECAP-PA1-FIX1` 同型的島切分缺陷而重複計打席。
全量數字（2018–2026、kind A/C/D/E、4,279 場／1,334,970 事件；本文**所有數字**由
`scripts/verify_splits_pa_split1.py` 的 artifact 程式化萃取——
`ingest_splits_pa_split1_metrics.json`、`ingest_splits_pa_split1_player_delta.json`）：

| 項目 | 數值 |
|---|---:|
| canonical 跨打者 transition（`build_islands` 列舉） | **296**（判準：`pinch_hit_slot` 216／`count_continues` 80） |
| ↳ prev 片段被幽靈島規則擋掉 | 210 |
| ↳ prev 片段整段無 `batting_action_name` 略過 | 3 |
| ↳ **實際被重複計為 PA** | **83 筆／82 場**（A:43、D:37、C:2、E:1；判準 `count_continues` 79／`pinch_hit_slot` 4） |
| H1 打序位移：受影響 (場次, 球隊) | **82**（位移分布：81 組位移 1、1 組位移 2＝`2020/A/22` 客隊） |
| H1：其後被錯誤歸類打序的 PA | **1,291 筆** |
| 選手層級 delta（完整發布欄位，見下） | **2,435 個 row／17,997 個格／314 位唯一選手**（batting_splits 249、pitching_splits 65） |

逐年：2018:7／2019:8／2020:13／2021:5／2022:14／2023:16／2024:8／2025:10／2026:2。
重複記的結果詞：三振 34、四壞 11、一安 7、投滾 4、游滾 4、右飛 3、中飛 3、界飛 2、
死球 2、內安 2、二安 2、游飛 2、二滾 2、雙殺／犧飛／一滾／二飛／三滾各 1。

## iteration 1 為何漏 22 筆（REVIEW-004 Critical；根因敘述依 REVIEW-007/008 修正）

iteration 1 的腳本把 **legacy 後島的首列——帶新打者 acnt 的 `is_change_player` 公告列——**
直接當作續打席事件傳入 `continues_same_plate_appearance()`；canonical `build_islands()`
則是跳過公告列（附掛於前島）、以**第一個 usable 成員列**判定。餵錯事件的後果分兩路：

- `count_continues` 路徑：判準讀到的是公告列的欄位而非新打者首個真實列——有時仍會通過
  （61 筆因此被找到），有時不會（**漏 18 筆**）；
- `pinch_hit_slot` 路徑：判準要求公告列**已附掛於前島**（`_trailing_change_rows`），
  legacy 切法把公告列放進後島、前島尾端恆空——該路徑無從成立（**漏 4 筆**）。

逐筆分類由 artifact `iteration1_missed_classification` 程式化產生（對照 `3b07d04`
的舊 artifact）：**漏 22 筆＝`count_continues` 18＋`pinch_hit_slot` 4**，61 ⊂ 83。
兩位跨家族查核者的獨立重建同此分布。
（iteration 2 曾把 22 筆全數歸因 `pinch_hit_slot`——不實，已依 REVIEW-007 F3／
REVIEW-008 F2 修正。）

## H1 成立：82 個 (場次, 球隊)、1,291 筆後續 PA 打序被污染

`flush()` 以 `pa_seq` 累加重建打序（`order = seq % 9 + 1`）。多出的 PA 使該隊其後所有 PA
的打序歸屬整體位移 1；分布為 81 組位移 1、1 組位移 2（`2020/A/22` 客隊同場兩筆 spurious）。
無 modulo-9 抵銷（最大位移僅 2）。依 REVIEW-007 的界定：此為**「legacy 相對 corrected」**
的量化，不擴張為絕對真實打序的保證。家族 10 也是選手層級 delta 的最大宗
（batting_splits 的 2,435 row 中家族 10 佔 1,284）。

## 選手層級量化：完整發布欄位（REVIEW-007 F2 處置）

**方法與三道保真／不變量：**

1. **T2 模擬器保真**：named-column 模擬器 legacy 模式與 `calc_t2` 輸出**逐格相等**
   （18 個已發布 (year, kind) 全過；artifact `simulator_fidelity_vs_calc_t2`）。
2. **組裝層保真**：在記憶體重現 `build_splits` 的 writer row（T1＋gofo 併入＋T2 覆蓋
   → `_meta`＋`_bat_rates`），assembled legacy row 與 **DB 已發布列逐格比對：
   226,553／226,553 全等**（batting 133,386＋pitching 93,167；artifact
   `assembly_fidelity_vs_published`）——組裝層完整重現了發布管線。
3. **corrected 路徑機器不變量**（REVIEW-007 對「corrected 無保真」的補位）：
   逐 (year,kind) 強制檢查 bat 家族 4／pit 家族 5 的 PA 總量 = legacy − spurious 數、
   以及**逐投手**家族 5 投球數（strikes/balls/pitch_cnt）守恆——投球數不得在投手間搬移。
   18 pairs 全過（artifact `corrected_invariants`）。

**corrected 語意**（僅合併 83 個缺陷邊界，其餘與 legacy 同構，使 delta 嚴格對應缺陷）：

- 打者歸屬＝canonical `charged_hitter`（9.15(b)，見 H3）。
- **投球數依每列實際 `pitcher_acnt` 保留**（REVIEW-007 F1 處置）；打席結果責任
  預設維持 calc_t2 的末顆投球錨定（與 legacy 完成段同錨，故不產生人工位移），
  唯一例外是記錄規則 **9.16(h)(1)**：後援以 2-0/2-1/3-0/3-1/3-2 接手且該打席四壞
  → 記前任投手（原文 `docs/reference/棒球規則.txt` p.174）。
- 跨投手合併島實際只有 **2 例**，且結果皆非四壞、9.16(h)(1) 均不適用
  （artifact `cross_pitcher_cases` 附逐投手球數對帳）：
  `2020/D/81` 6 局下三振（前任 2 好 3 壞＋後援 1 好；責任＝後援）、
  `2022/D/140` 5 局上二飛（前任 1 好 3 壞＋後援 4 好；責任＝後援）。
  iteration 2 曾把前任的投球數整島搬給後援——已修正，守恆由上述不變量強制。

**結果**（artifact `player_delta_summary`；兩份 artifact 摘要一致由 assertion 強制）：

- **2,435 個發布 row 受影響／17,997 個格／314 位唯一選手**
  （batting_splits 249、pitching_splits 65）。
- 欄位分布（前幾名）：`plate_appearances` 2,304、`ops` 1,734、`obp` 1,715、
  `at_bats` 1,651、`slg` 1,528、`avg` 1,515、`so` 963、`goao` 902——
  **衍生率欄（avg/obp/slg/ops/goao）已全數納入**（REVIEW-007 F2）。
- 影響最大者（整數計數欄 Σ|delta|，跨表聚合到唯一 acnt；rate 欄不入排名）：
  高國麟 174、鄭鎧文 166、范國宸 158、李宗賢 157、潘傑楷 136、江坤宇 133、
  林哲瑄 130、李聖裕 130……（完整 15 名見 artifact）。
- `batting_vs_team`／`pitching_vs_team` 來自 T1（gamelog 加總、不經 livelog 島重建），
  本缺陷零影響，不列 diff。
- 範圍註記：3 場 C/E（`2022/C/2`、`2023/E/1`、`2024/C/2`）無年度分項表，不產生已發布
  偏差；生涯 9999 base 錨定官方且 C/E 凍結、accrual 僅取本季 A/D，故生涯目前僅經
  2026 A/D 的 2 場受影響（跨年 roll 前若未修正，歷史偏差將被捲入 base）。

### box 逐場交叉驗證（外部對照，非自比）

以官方逐場 box（`batting_gamelog`，爬蟲直寫、不經 `splits_calc`）對 82 個受影響場次
逐人對照單場 PA（寬過濾：任一版本 ≠ box 即列）：

- **legacy 有 88 筆逐人不吻合；corrected 後只剩 7 筆**（artifact `box_crosscheck`）。
- 7 筆殘留中：2 筆是 `2018/A/116` 的官方歸屬偏離（見 H3）；5 筆是 legacy 同樣存在的
  背景低估雜訊（splits＜box，方向與本缺陷相反，成因另案）。
- iteration 1 無法解釋的 `0000001754` +1 已解釋：`2025/A/68` 正是漏掉的 22 筆之一。

## H2：當前 harness 是自比；當年對帳**不可重現**，多數受影響場次從未被對過帳

**當前對照組**：`cpbl-verify-splits` 讀 `batting_splits` 等表當「官方值」，但
`cpbl-build-splits` 自 2026-07-06（Phase 1，commit `36e3334`）起把重算值寫回同一批表
且含於每日 refresh——**當前跑 harness 是重算值自比，零資訊**。本卡的外部對照因此改用
box（上節）。

**當年對帳是否涵蓋受影響場次**——分三類，皆有出處：

1. **2018–2025 年度分項（77 場 A/D）：從未對過帳。** 官方 apart 頁只爬過
   `(2026, A)` 與生涯 9999（`cpbl_player_detail.py` `APART_COMBOS` 常數）；
   2018–2025 的分項列是 2026-07-14 由 VENUE-PARK1 `cpbl-build-splits <year>` 回填的
   **純重算值**（各年度全部列 `updated_at` = 2026-07-14，DB 實查；VENUE-PARK1 結案
   紀錄見 `docs/archive/TASKS_ARCHIVE.md` L123–130）。
2. **2026/A/58（06-24）：名義上在 Phase 0 對帳母體內，但結果不可考。**
   Phase 0 harness（2026-07-06，commit `3a66169`）對照當時新爬的 2026/A 官方值，
   收斂後仍有 3,248 筆殘差，僅以 commit message 總量數字留存、**無逐格 artifact**。
3. **2026/D/131：從未有官方對照**（官方 apart 本季僅 A 有資料，
   `cpbl_player_detail.py` L197 註）。

**可重現快照：不存在。** 查找範圍：本機 DB（07-06 起被 DELETE+INSERT 覆寫）、生產 DB
（07-14 起由本機同步）、備份（`backup-cpbl-prod.sh` keep 7，現存最早 2026-07-25，
全部晚於覆寫）、git（無官方值或 harness 逐格輸出的 committed artifact）、raw payload
（`cpbl_player_detail` 解析後直接 upsert，無 apart 快照表；migrations 全查）。

**恢復路徑（供修正卡）**：官方站 `/team/apart` 仍提供 year × kindCode 下拉
（`docs/CPBL_SITE_MAP.md` L196），修正後可另開爬卡取歷年官方值作驗收對照；
在那之前 box 是唯一未被污染的既有對照，本卡已實證其可用性。

## H3：官方口徑——只計一個打席；歸屬依 9.15(b)，**含打席數本身**

規則原文（`docs/reference/棒球規則.txt` p.170–171）：

> 9.15(b)「擊球員於第 2 好球後退出，替代的擊球員以三振完成打擊，記為**最初擊球員**的
> 三振與打數，若替代擊球員以其他結果完成打擊（包括四壞球），皆視為**該替代擊球員**之行為。」
> 【註】「同一打席中分別由 3 位球員替換出場打擊，最後被三振時，其中**被判第 2 好球**之
> 擊球員，應被記為三振及打數。」
> 9.14(a)原註「……若四壞球關係到 2 名以上之代打員時，參照 9.15(b)之規定。」

83 筆的結果詞路徑窮舉（紅線 4）：**三振 34 筆**走 9.15(b) 前段（22 筆原打者已被判第 2
好球 → 歸原打者；12 筆代打者自吃第 2 好球 → 歸代打者；不死三振變體 0 筆，
`STRIKEOUT_ACTIONS` 已涵蓋）；**四壞 11 筆**走 9.14(a)原註 → 9.15(b) 後段歸代打者；
**其餘 38 筆**（安打／出局等）皆為「其他結果」→ 歸代打者。歸屬判定引用 canonical
`charged_hitter`（`pa_build.py`，FIX1 定案），不重新定義。

**修正 iteration 1 的詮釋錯誤**：iteration 1 據 `2025/A/84` box（7091 `PA=1, AB=0`）
推論「官方把打席數記給完成者」。逐場重算證明該 PA=1 是 7091 **10 局自己的犧短**；
被中斷打席的 PA 與 AB/SO 一併記給被判第 2 好球者 6738（box `PA=3=AB`；若 PA 記完成者
會得出 `PA=2 < AB=3`，違反 PA≥AB 恆等式）。**歸屬是整個打席跟著 9.15(b) 走**，
與 canonical PA 表把 `hitter_acnt` 記給 charged 的語意一致。

**已知官方實務偏離一例**：`2018/A/116` 7 局下，3551 於 1-2（第 2 好球為其揮棒落空）
退場、1240 接手看第 3 好球——依 9.15(b) 應記 3551，官方 box 卻把完整 K
（`PA=1,AB=1,SO=1`）記給 1240、3551 該打席零記錄（livelog 逐球佐證）。2025 年官方
（84 場）則正確依規則。修正卡需裁定跟規則還是跟官方單場實務（幅度 1 PA）。

## 邊界與未做

- **本卡未修**（紅線 5）：`splits_calc.py` 零改動；未跑 `cpbl-build-splits`；
  未寫任何分項表（artifact `readonly_guard` 前後全等）。
- box 對照的背景低估雜訊（受影響場次內 5 筆逐人，方向與本缺陷相反、corrected 前後不變）
  成因未查明，屬另案。`2019/A/173`（已知來源損壞場）不在 82 場之列。
- 打席結果的投手責任只在 9.16(h)(1) 四壞情形轉移；calc_t2 對**未合併島**的
  跨投手打席同樣採末顆投球錨定，其與 9.16(h) 的全面對齊屬 calc_t2 語意問題、
  超出本缺陷範圍（修正卡註記）。

## 建議

開修正卡（`db_scope: data-migration`）：`splits_calc.flush()` 切界改引用 canonical
`continues_same_plate_appearance`／`build_islands`，歸屬引用 `charged_hitter`，
重算 2018–2026 × A/D 四表＋生涯 accrual。驗收對照建議：
(1) 本卡 box 逐場交叉驗證（88 → 7 應可複現）；
(2) **完整發布欄位** delta artifact 作為預期變更清單（重算前後 diff 應與其一致，
    含 avg/obp/slg/ops/goao）；
(3) 逐投手投球數守恆與 PA 總量不變量納入修正卡驗收；
(4) 若需官方年度分項對照，另開爬卡取 `/team/apart` 歷年值（見 H2）。
`2018/A/116` 的官方偏離一例需在修正卡中裁定歸屬口徑（規則 vs 官方實務，幅度 1 PA）。
