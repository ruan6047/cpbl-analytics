---
card: GAME-RECAP-WP-STRENGTH1
document_type: plan-review-request
status: completed
result: GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW.md
review_class: T4-statistical
spec_baseline: v1.3
requester: ruan6047
prepared_at: 2026-07-26
---

# GAME-RECAP-WP-STRENGTH1 規劃獨立審核文件

> 本文件是給**非原規劃者的跨家族 AI 或人工 reviewer** 使用的審核封包，不是審核結論。請獨立判斷設計是否自洽、可執行、無資料洩漏 [data leakage]，不得因卡面已標示「凍結」而預設核可。

> 2026-07-26 已由 Google Gemini 3.6 Flash 跨家族審核，結果 `APPROVE`（P0–P2=0、P3=1）；正式紀錄見 [`GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW`](GAME-RECAP-WP-STRENGTH1_PLAN_REVIEW.md)。本 request 保留為審核輸入基線。

## 1. 審核目標與裁決

請審核 [`GAME-RECAP-WP-STRENGTH1`](../tasks/GAME-RECAP-WP-STRENGTH1.md) 在進入 📥Backlog 前，是否同時滿足：

1. 設計內部沒有互相矛盾的模型、時間窗口、特徵或驗收語意。
2. 所有特徵在對應比賽開打前可得，且訓練、inner selection、validation 嚴格分離。
3. 外部網站／論文只用於候選合理性，不被誤當成 CPBL 增益已證實。
4. 判定完整沿用 WP-VAL1 v2 並加上逐局帶硬門檻，沒有暗中放寬。
5. 執行範圍仍可控制在 M–L，且可復用既有唯讀 harness。

允許的最終裁決只有：

- `APPROVE`：沒有 P0–P2 阻擋 finding；P3／建議不得改變凍結模型或門檻。
- `REQUEST_CHANGES`：存在任何會造成錯誤結論、驗證洩漏、不可重現、規格矛盾或 M–L 明顯失真的 P0–P2 finding。

不得用 `APPROVE WITH FINDINGS` 包裝尚未解決的阻擋問題。這是**規劃查核**，不代表未來實作完成後的 T4 統計查核已通過。

## 2. 必讀資料（順序）

1. [`docs/AI_RUNBOOK.md`](../AI_RUNBOOK.md)
2. [`GAME-RECAP-WP-STRENGTH1` 卡面](../tasks/GAME-RECAP-WP-STRENGTH1.md)——被審主體
3. [`GAME-RECAP-WP-STRENGTH1_RESEARCH`](GAME-RECAP-WP-STRENGTH1_RESEARCH.md)——Tavily 原文重審與證據降級
4. [`GAME-RECAP-WP-VAL1_RESULTS`](GAME-RECAP-WP-VAL1_RESULTS.md)——重點 §3.1 偏差結構、§7 路徑
5. [`GAME-RECAP-WP-CAL1_RESULTS`](GAME-RECAP-WP-CAL1_RESULTS.md)——重點 §5 失效機制、§7 排除路線
6. [`winprob_val.py`](../../src/cpbl/models/winprob_val.py) 與 [`winprob_cal.py`](../../src/cpbl/models/winprob_cal.py)——harness 可復用性
7. [`outcome.py`](../../src/cpbl/features/outcome.py)——leakage-safe running-state 慣例與現有同季 starter 欄位風險
8. [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §8——父 spec v1.3
9. [canonical statistical-redline 範本](../../.ai-workflow/templates/statistical-redline.md)

若無法讀取任一項會影響裁決的必讀資料，應回 `REQUEST_CHANGES` 或明列 `UNVERIFIED`，不得靠檔名推測內容。

## 3. 被審設計摘要（僅供定位，裁決以原卡全文為準）

### 3.1 問題與方案

- 現行 `run_dist`／DP 是平均隊伍的局勢 WP，A scope 在時間外驗證呈 S 型偏差。
- CAL1 已證明事後 recency／衰減校準會修一處、破壞另一局帶；本卡禁止重開。
- 主方案固定為 L2 邏輯斯賽前先驗 `p0`，以 opening-anchor 的 logit offset 融入場中 `WP_situ`。
- 戰力條件化 `run_dist` 經樣本格數估算可行，但因硬分箱、每格七類分布與維護成本未選；不得在本卡 No-Go 後事後切換。

### 3.2 三期資料

| 時期 | 角色 |
|---|---|
| `≤2017` | 只供 2018 冷啟動 prior；不進 game-level fit／validation |
| `2018–2025` | 核心逐場可重建資料與 walk-forward 母體 |
| `≥2026` | 核心 running features 繼續；2026 是首要鎖箱 holdout；advanced／TrackMan 只作 shadow |

### 3.3 固定八項特徵

`prior_winpct_diff`、`winrate_diff`、`run_margin_diff`、`rest_days_diff`、`starter_kbb_adv`、`starter_recorded_strike_share_adv`、`starter_fip_proxy_adv`、`bullpen_kbb_adv`。

所有當季數值必須在套用該場結果前累積；現有同季最終 `starter_era_diff/whip/k9`、同季 standing、`pitching_current` 與 2026 leaderboard 回填均禁止。

### 3.4 時間切分與選型

對每個 `Y ∈ {2023,2024,2025,2026}`：

```text
inner fit       = 2018..Y-2
inner selection = Y-1
final refit     = 2018..Y-1
locked evaluate = Y
```

- `(kappa, lambda)` 只以 Y−1 逐場 Brier 選定。
- `gamma` 只以 Y−1 逐 PA Brier 選定。
- Y 不得反向改動 feature、網格、tie-break、融合式或門檻。
- 2026 advanced shadow 不得參與任何選型或 Go/No-Go。

### 3.5 驗收

- `full` 八特徵模型是唯一正式驗收候選。
- `team-only`／`team+starter`／`full` 消融 [ablation] 只作資料來源增量診斷，不得依 Y 結果切換模型。
- 每個驗證季 coverage、Brier 基準與相對 base 門檻；池化十分位 99% game-cluster CI；1–3／4–6／7–9 局帶絕對偏差及相對 base 惡化，全部是硬判定。
- DB 唯讀、seed `20260725`、`--out` scratch；不動既有 harness、production `winprob.py`、API、前端或 crawler。

## 4. 必答矛盾檢查

Reviewer 必須逐項回答 `PASS`／`FINDING`／`UNVERIFIED`，不得省略。

| ID | 必查問題 | 需核對的矛盾／失效模式 |
|---|---|---|
| C1 | 融合式是否真的滿足開場 `WP_adj=p0`？ | `p_base0` 是否來自同代 ruleset／run_dist；是否重複計入主場優勢；clip 與端點是否破壞等式 |
| C2 | `w(t)` 是否對所有 canonical 狀態定義完整？ | 上／下半局、outs 0–2、九局末、再見、和局進延長、10+ 局固定 0 是否自洽；是否與「強隊領先偏差」目標衝突 |
| C3 | Fractional tie label 是否與模型 loss 一致？ | `y=0.5` 套 binomial cross-entropy 的統計語意、最佳化器支援與 Brier／log-loss 評估是否一致 |
| C4 | 四個 walk-forward fold 是否仍屬有效時間外證據？ | 某季可先作前一 fold 的 validation、再作後一 fold 的 inner selection；池化時是否會被誤稱為互相獨立、同代或單一 untouched holdout |
| C5 | 2026 是否仍能稱為鎖箱 holdout？ | 規劃者已看過 2026 base/CAL1 結果；本卡 feature／hyperparameter 是否曾依 2026 結果調整；季中與季末重跑後如何避免再選型 |
| C6 | `kappa` prior 對每一列是否時間安全？ | 前季 player/team prior、fit-window league fallback、2018 冷啟動與訓練列 transformation 是否可能使用該場之後事件；「model-fit 統計」與「pregame feature」界線是否清楚 |
| C7 | `≤2017` 是否真的足以供 2018 冷啟動？ | `pitching_seasons` 是否具 K−BB/FIP 所需分子分母、team_id 轉隊聚合與 starter 對應；不足時 fallback 是否預註冊且不讀 2018 未來 |
| C8 | 八項 feature 的分母與方向是否一致？ | PA/BF 定義、BB 是否含 IBB、HBP、IP thirds、FIP 方向、主−客／客−主、缺值與零分母；`strike_cnt/pitch_cnt` 是否被誤稱 zone% |
| C9 | Bullpen running state 是否 leakage-safe？ | `role_type != '先發'` 的角色是否以歷史該場可知資料判定；不得使用目標場賽後實際出賽牛棚或同季最終 role |
| C10 | 先發名單 availability 與異動如何處理？ | `games` starter ID 是否確實 pregame 可知；缺值、臨時換投與賽後修訂是否 fail closed，coverage 0.98 是否可達 |
| C11 | 選型準則是否形成隱性雙重使用？ | 同一 Y−1 同時選 `(kappa,lambda)` 與 `gamma` 是否需要 nested-within-inner；p0 Brier 與 PA Brier 的不同權重是否可被合理解釋 |
| C12 | `full-only` 驗收與消融是否矛盾？ | 若 team-only 在 Y 顯著較佳，是否仍必須判 full No-Go；文件是否可能被執行者解讀為可事後切換 |
| C13 | WP-VAL1 v2 與 CAL1 門檻是否完整且只加嚴？ | coverage、Brier、十分位 n/CI、逐局帶 n/CI、相對惡化、10+ 揭露規則及未捨入值是否一致 |
| C14 | Cluster bootstrap 與多重檢查是否足以支撐判定？ | game-cluster 單位、單季／池化、跨 fold 非同分布；多個分箱／局帶的門檻是否與 VAL1 v2 完全一致而非新造寬鬆檢定 |
| C15 | 條件化 `run_dist` 的淘汰理由是否誠實？ | 3/5 分箱格數其實可行；卡面是否正確表述為工程／資料效率決策，而非偽稱樣本不可行或文獻證明較差 |
| C16 | 文獻主張是否超出原文？ | Yang=2001 MLB、Brown=batting average、CPBL=2019 四隊個別模型、FiveThirtyEight 舊方法頁轉址、官方 UI 只見 2026≠底層絕無歷史資料 |
| C17 | 2026 advanced shadow 是否可能污染 ADV1？ | 若現在揭露與 core 的相關性／方向，後續 ADV1 應使用何種新留出期；是否已明確禁止用 shadow 結果回改本卡 |
| C18 | M–L 估算是否可信？ | 新增三期 router、八項逐場 running features、nested fit、PA fusion、bootstrap、消融、artifact、測試與報告是否可能實為 XL；是否應分卡 |
| C19 | Harness 復用是否可行且不需修改既有 harness？ | `winprob_val/cal` 是否暴露足夠 helper；新增模組能否 `--out` scratch、單季重跑並保持 production path 不動 |
| C20 | spec／workflow routing 是否一致？ | spec baseline 必須仍為 INIT-GAME-RECAP v1.3；執行／查核填 L1–L4 而非模型名；查核須跨家族或人工；不得寫 lifecycle event |

## 5. 數值與資料主張查核表

以下不是要求 reviewer 相信，而是要求其確認「有來源、定義一致、不可被誤用」。若未親自重跑 DB，可標 `UNVERIFIED`，但須判斷這是否阻擋規劃核可。

| 主張 | 卡面數值／結論 | 查核要求 |
|---|---|---|
| 條件化格數 | 2018–2022 三箱 140/144、五箱 225/240；可用觀測 ≥99.70% | 核對 state/bin 定義、quantile 同值處理、`MIN_STATE_N=30` 與 pooled fallback 推論 |
| gamelog coverage | 2018–2026 A 完成場 100%；先發有效分母 5,098/5,102 | 核對 scope、完成場定義、join 重複、有效分母條件與資料截止日 |
| VAL1 偏差 | 低分箱約 +4.2～+6.0pt、高分箱 −4.3pt | 對照 VAL1 §3.1，確認不是錯用 CAL1 或 in-sample 數字 |
| CAL1 失效 | 全域校準改善池化但惡化早局帶 | 對照 CAL1 §5，確認本卡逐局硬門檻確實制度化該教訓 |
| 公開 advanced | 官方公開 UI 目前只可核對 2026 | 只能推論「無法公開重建 2018–2025 as-of」，不得推論聯盟底層絕無歷史資料 |

## 6. 審核邊界

### 本輪允許

- 唯讀閱讀 repo、git diff、既有 artifact 與本機 DB。
- 以 scratch `--out` 或 SQL `SELECT` 驗證卡面數字。
- 指出模型、統計、資料可得性、範圍估算或文件語意矛盾。

### 本輪禁止

- 修改卡面、研究報告、程式碼或 DB。
- 跑 crawler／refresh、寫 lifecycle event、claim 卡、建立 implementation branch、commit 或部署。
- 接觸 `LIVE-GAME-BACKEND1` lease 資源。
- 以驗證季結果提出事後最佳 feature／hyperparameter，或重開 CAL1 已排除的 recency／衰減校準。

## 7. Reviewer 回覆格式

請將回覆寫成獨立 review 文件或完整訊息，至少包含：

```markdown
# GAME-RECAP-WP-STRENGTH1 Plan Review

- Reviewer：<模型家族／人工識別>
- Reviewed commit / working-tree state：<SHA；若含未提交 diff 必須註明>
- Spec baseline check：v1.3 == INIT-GAME-RECAP current <PASS/FAIL>
- Verdict：APPROVE | REQUEST_CHANGES

## Findings

### F-01 [P0|P1|P2|P3] <標題>
- 位置：<檔案＋章節／行>
- 矛盾：<兩個互不相容的敘述或失效機制>
- 證據：<原文、程式、唯讀 SQL 或可重現推導>
- 影響：<為何會造成錯誤結論／不可執行>
- 必要修正：<最小可驗收修改；不得替規劃者直接改檔>

## C1–C20 Checklist

| ID | 結果 | 一句證據 |
|---|---|---|
| C1 | PASS/FINDING/UNVERIFIED | ... |

## 結論

<說明 verdict 是否阻擋轉 Backlog；重申本輪不是 implementation review>
```

Finding priority：

- `P0`：會造成資料洩漏、驗證季選型、錯誤 Go/No-Go 或破壞 production/statistical contract。
- `P1`：核心設計矛盾、不可實作、關鍵公式／窗口錯誤。
- `P2`：可重現性、coverage、資料語意、範圍估算或驗收缺口，可能導致錯誤交付。
- `P3`：不影響規劃正確性的文字清晰度或後續建議。

## 8. Backlinks

- [[GAME-RECAP-WP-STRENGTH1]]
- [[GAME-RECAP-WP-STRENGTH1_RESEARCH]]
- [[GAME-RECAP-WP-VAL1_RESULTS]]
- [[GAME-RECAP-WP-CAL1_RESULTS]]
- [[INIT-GAME-RECAP]]
