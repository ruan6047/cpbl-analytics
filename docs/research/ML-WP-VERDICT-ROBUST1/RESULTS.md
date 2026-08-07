# ML-WP-VERDICT-ROBUST1：Go/No-Go 判定的 seed 穩健性與判定詞彙

- 卡：`ruan6047/cpbl-analytics#101`（T3，`db_scope=read`）
- 基準：`876ce9ff7d596ce65f28f0cc7f5207ebcf6a3c32`
- spec 基線：`ML-WP-VAL-RESAMPLE1` 交付報告 §5／§6-F2 ＋ 三準則裁決 `#98` comment `5208856434`
  （成文於 `.ai-workflow/templates/statistical-redline.md` 失效模式 #7／#9／#10）
- 資料截止：`2026-08-07`（本機 DB）。**母體逐日增長是正常狀態**（統計紅線 #9），
  下列場數為當日值：A 1,856 場／141,072 打席、D 1,171 場／89,449 打席、
  C 25 場／1,927 打席、E 13 場／985 打席。
- 全程唯讀，未寫任何 DB 表；未動 `api/routers/recap.py`（#100）、`winprob_cal.py`（#104）、
  `winprob_strength.py`（#102）、`web/`、任何既有研究報告內文（#105）。

---

## §0 結論

**判定機制換代（v2 → v3），四個 scope 全部重跑，門檻數值一個都沒動。**

| scope | 已發布 artifact | RESAMPLE1（v2・上午） | 今日 × v2 | **今日 × v3** | 規則造成的變化 |
|---|---|---|---|---|---|
| A 一軍例行 | unsupported | unsupported | unsupported | **unsupported** | 否 |
| C 一軍總冠軍賽 | unsupported | unsupported | unsupported | **insufficient_evidence** | 是 |
| D 二軍例行 | unsupported | **supported** | **supported** | **unsupported** | 是 |
| E 一軍季後挑戰賽 | unsupported（pre-FIX1） | unsupported | unsupported | **insufficient_evidence** | 是 |

（表由 `compare_verdicts.py` 產生，見 [`verdict_comparison.md`](verdict_comparison.md) 表 1。）

三件值得先講的事：

1. **D 的「翻面」是 Monte Carlo 雜訊，不是證據**。v2 用單一 seed 的 99% CI 端點判 D 池化
   十分位 2，今日那個 seed 抽到 CI `[-0.0005, 0.0967]`——差 0.0005 就含 0，於是 D 被判
   `supported`。同一批資料換成跨 seed 池化重抽，該分箱在 12,000 次重抽下**顯著**
   （`p_one=0.00225`），|dev|=+0.0501 超界 → `unsupported`。v3 讓 D 回到已發布 artifact
   的判定，而且這次是**確定性**的。
2. **C／E 從「測了，不準」改成「測不了」**。兩者的決定性閘門（proxy 池化 ECE > 0.05）
   在自己的樣本量下**不可能通過**：完美校準零假設的期望 ECE，C 是 0.07685、E 是 0.12224，
   都高於門檻 0.05（E 甚至高於自己的觀測值 0.08548）。那不是判準，是雜訊產生器。
3. **沒有任何 scope 因為改判定而取得上線資格**。v2 下可上線的 scope 是 `['D']`，
   v3 下是 `[]`（`no_scope_gained_shipping_eligibility: true`，由 `compare_verdicts.py`
   機器判定）。本卡只可能讓判定變嚴或變誠實，不可能變寬。

---

## §1 病灶：v2 的兩個缺陷

### 1.1 硬性判定吃 bootstrap seed 的運氣

v2 的池化分箱閘門是「`|dev|` 超過 ±0.03 **且** 99% game-cluster CI 排除 0」。那個 CI 由
**單一 seed（20260725）的 500 次重抽**估出來——而 500 次重抽估 0.5% 分位數，實際上只倚賴
約 2.5 個次序統計量。Monte Carlo 誤差因此大到足以讓邊界分箱的 Go/No-Go 翻面。

`ML-WP-VAL-RESAMPLE1` §5 已量過症狀（A 十分位 7 為 5/12 seed 顯著、D 十分位 2 為 7–8/12），
本卡在今日資料上重量並擴到全部決定性分箱（[`budget_trace.md`](budget_trace.md) 表 A）：

| 分箱 | dev | 12 個 seed 中判「顯著」的數目 | v2 實際採用的那個 seed 判 |
|---|---:|---:|---|
| A-7 | −0.0364 | **6/12**（正好對半，多數決在這裡沒有定義） | 不顯著 |
| A-9 | −0.0140 | **8/12** | 顯著 |
| D-2 | +0.0501 | **11/12** | **不顯著** ← D 的整個判定掛在這一票上 |

D-2 那一列是最傷的：12 個 seed 有 11 個說顯著，而 v2 恰好用到那 1 個說不顯著的。
整個 scope 的 Go/No-Go 由此翻面。

### 1.2 判定詞彙把「測了，不準」與「測不了」壓成同一格

v2 只有 `supported` / `proxy_with_warning` / `unsupported` 三值，於是：

- C（25 場）與 E（13 場）因為一道**在該樣本量下不可能通過**的 ECE 門檻被判 `unsupported`，
  讀起來像「模型校準不良」——但兩者的池化 Brier 都**贏**全押主場基準
  （C 0.15027 vs 0.25676、E 0.14842 vs 0.23764）。
- `winprob_val.py:645`（基準行號）連「**無可評樣本**」都回 `unsupported`：一次都沒評過，
  卻報「評過了，不合格」。

這正是三準則裁決推論的違例：**判定詞彙必須能表達「樣本不足以判定」**。

---

## §2 修法：為什麼是這個方案

### 2.1 把「不可約的抽樣不確定度」與「可約的 Monte Carlo 誤差」分開

這是整個修法的樞紐。CI 要量的是**抽樣不確定度**（換一批比賽，偏差會差多少）——那是不可約的，
本來就該進判定。但 v2 的翻面來自**另一種**隨機性：同一批比賽、只是重抽的骰子不同。
那是純實作雜訊，多抽幾次就能壓下去，**不該有資格決定 Go/No-Go**。

v3 因此改判**母體語意等價、但估得準**的量：單尾機率
`p_one = P(重抽的 dev 跨過 0)` 與 `α_one = (1−ci)/2 = 0.005` 的比較。`p_one` 是所有重抽的
**平均**，不是極端分位數，其 Monte Carlo 誤差就是標準的二項誤差，可以直接量出來：
對 `p̂` 配一個 Wilson 區間（`z = 3`，**計算容忍度**，不是統計顯著水準），再拿整條區間與
`α_one` 比。

> **「99% CI 排除 0」與「`p_one < α_one`」的關係要講精確（ROBUST1-R1-01 修正）。**
> 兩者在**精確算術下等價**：CI 排除 0 ⟺ `k ≤ floor(α_one·(n−1))`，
> `p_one < α_one` ⟺ `k ≤ ceil(α_one·n) − 1`，兩式對所有整數 `n` 相同
> （以 `Fraction` 窮舉 `n = 2..300,000`，反例 **0** 個；由
> `test_tail_probability_and_percentile_ci_agree_exactly_but_not_in_floating_point` 釘住）。
> **但它不是實作層的精確恆等**，本實作有兩處有限樣本偏離，方向都是「更難判顯著」：
>
> 1. `α_one` 由 `(1 − ci)/2` 以二進位浮點算出，`0.99 → 0.0050000000000000044 ≠ 1/200`。
>    `k` 正好落在 `α_one·n` 邊界時兩式分岔——實測 `n=6,000` 的 `k=30`、`n=12,000` 的 `k=60`：
>    `p_one < α_one` 為真，而百分位 CI **不**排除 0。
> 2. `_percentile_ci()` 回傳前把端點捨入到小數第 4 位，真實下界若是微小正值（如 `3e-5`）
>    會被讀成 `0.0`，於是「排除 0」判否。
>
> 判定實際採用的是**Wilson 區間對 `α_one` 的比較**，不是上面任一個式子，故這兩處偏離
> 不影響本卡任何判定（三態機制在邊界只會更保守）。之所以要改這句話：它是判定機制的
> **核心語意**，後人會拿它當恆等式繼續往上推導。

| Wilson 區間相對 α_one 的位置 | 判 |
|---|---|
| 整段在 α_one 之下 | `significant`（再多抽也不會翻） |
| 整段在 α_one 之上 | `not_significant` |
| 跨過 α_one | **`undetermined`**——目前的重抽預算解析不出來 |

**這一格就是 v2 缺的東西**：v2 在這種情況下會按 seed 運氣隨機丟進 significant 或
not_significant，而且不留痕。

### 2.2 為什麼不是「多 seed 多數決」

多數決是派工包點名的候選，本卡實測後**否決**它，理由不只是「7/12 也是任意數字」：

- **A-7 的票數是 6/12**。多數決在這裡沒有定義，還要再加一條處理平手的規則。
- **A-9 的票數是 8/12**，多數決會判它「顯著」。但把同一批重抽池化起來、一路加碼到
  96,000 次，這個分箱**始終** `undetermined`——多數決會把一個真的判不動的統計量寫成定論。
- 更根本的：12 個 seed × 500 次 = 6,000 次重抽，多數決只用到其中「每 500 次一組的極端分位數
  落在哪邊」這個粗糙訊號，**丟掉了 6,000 個重抽值裡的絕大部分資訊**。同樣的計算量，池化後
  直接估尾機率，精度高一個量級。這是估計效率問題，不是口味問題。

也否決了「只回報 CI、不做二元判定」：`verdict_for()` 的下游（`/api/info` 指標、對外文案、
CAL1 的比較）需要一個可程式化的結論。把二元判定丟掉只是把同一個決策推給讀者臨場心算，
而讀者手上沒有 MC 誤差資訊。**正解是保留判定、但讓它有第三態**。

### 2.3 新方案自己的任意性在哪裡——以及怎麼把它降到最小

誠實地列：v3 引入三個新旋鈕。

**(a) 註冊 seed 集大小（12）。** 若判定停在固定 seed 數，「註冊了幾個 seed」就會變成新的
任意數字直接左右 Go/No-Go——**而且本卡實測到它真的會**：D-2 在 6,000 次重抽下 `undetermined`、
12,000 次下 `significant`。若我停在 12 個 seed，D 會被判 `insufficient_evidence`，
而那個結論的真正意思只是「我沒抽夠」。

處置：**預算自動加碼**。解析不出來就把 seed 集倍增，直到解析得出來或撞上限
（`_escalate()`）。seed 集大小因此不再影響結果，只影響速度。

**(b) 重抽上限 `BOOT_MAX_REPS = 96,000`。** 這是唯一還會左右結果的任意數字。但它的性質
比 v2 的 seed 好得多：撞上限是**可觀測、可回報的事件**（`hit_reps_cap`），撞到就明說
「這個統計量在 96,000 次重抽內判不動」，不會假裝有答案。今日全 scope 只有 A-9 撞上限，
而它 |dev|=0.0140 < 0.03，**無論顯著與否都不影響判定**。上限的代價是時間：A 池化
1,856 場跑滿 96,000 次約 20 秒。

**(c) MC 容忍度 `z = 3`（≈99.7%）。** 它管的是「再抽一次會不會改答案」，不參與任何科學推論。
調大只會讓更多統計量落入 `undetermined`（保守方向），不會讓任何東西通過。

還有一個**不是**任意性、但值得寫下來的約束：重抽總數必須大到「一次都沒跨過 0」能被判成
significant。`k=0` 時 Wilson 上界 ≈ `z²/(N+z²)`，要小於 `α_one=0.005` 需要 `N > 1,791`。
註冊預算 12 × 500 = 6,000 有 3.3 倍餘裕；少於 4 個 seed 則連完全乾淨的分箱都會被判成
`undetermined`。這條由 `test_registered_boot_budget_can_resolve_a_clean_tail` 釘住。

### 2.4 「測不了」怎麼機械判定（不准寫死「場數 < N」）

新增判定值 `insufficient_evidence`。判準全部可計算，且隨指標與門檻變動：

| 閘門 | 「判不動」的判準 |
|---|---|
| 池化十分位偏差 | 偏差絕對值超界（門檻未動）但顯著性 `undetermined` → 進 `insufficient` |
| 逐季 Brier vs 全押主場 | Δ 的整場重抽三態；`undetermined`／`not_significant` → 該季無判別力，不再一票否決 |
| proxy 池化 ECE | 完美校準零假設下的期望 ECE 若已超過門檻 → 門檻 `unreachable`；觀測值若落在 H0 的 p95 內 → `undetermined` |
| coverage | 純計數、無抽樣成分 → 維持硬性（今日全 scope coverage = 1.0，未觸發） |

零假設 ECE 的算法沿用 `RESEARCH-VERDICT-AUDIT1/analyze_gates.py`（`E[ECE] = Σ w_b·se_b·√(2/π)`
＋ 20,000 次 Monte Carlo 取分位數，`se_b` 用同一份 game-cluster bootstrap SE，不引入新的
變異假設）。本卡把它從**事後稽核腳本**收進 harness 本體——「這道門檻在這個樣本量下可不可能
通過」應該是判定的一部分，不是要有人事後另外算一次。

交叉驗證：`null_ece_reference()` 對 A scope 算出 `0.00986`，與 `analyze_gates.py` 在已發布
artifact 上算出的 `0.00986` **逐位相同**（兩支獨立實作、不同輸入路徑）。

優先序：`unsupported` > `insufficient_evidence` > `proxy_with_warning` > `supported`。
有一道閘門**解析得出來的失敗**就是真失敗；沒有真失敗但有測不了的閘門，就不得宣稱通過。
`insufficient_evidence` **不是通過**——處置與 `unsupported` 相同（不上線），改的只有理由。

### 2.5 沒有改的東西

- `THRESHOLDS` 區塊與基準 `876ce9f` **逐字元相同**（`git diff` 可直接驗證）。v3 的新旋鈕
  刻意住在 `THRESHOLDS` 之外，讓「有沒有偷改門檻」是一個機械可驗的問題；
  `test_thresholds_are_untouched_by_the_verdict_rework` 逐鍵釘住八個值。
- 重抽的**抽樣序列**沒有換。v3 把逐場重抽向量化了（12 seed × 500 次在 v2 的純 Python 迴圈下
  太慢），但索引序列逐個重現 `random.Random(seed).choices()`；
  `test_vectorised_resampling_draws_the_same_games_as_the_v2_loop` 以 v2 的參考實作釘住
  逐位相等。若向量化順手改了抽樣，判定的變化就無法歸因於「機制改了」。

---

## §3 全 scope 逐項對照

方法：v2 與 v3 **跑在同一份 `verdict_metrics.json` 上**，故兩者差異只能來自規則，
不可能來自母體漂移（`ML-WP-VAL-RESAMPLE1` 的教訓：不切開就會把資料變動記成規則的效果）。
v2 由 `compare_verdicts.py::legacy_verdict_for()` 重放，它讀 artifact 內逐分箱保留的
`dev_ci_legacy_seed`（seed 20260725 的單一 seed CI），與基準 `verdict_for()` 逐行等價。

完整表格見 [`verdict_comparison.md`](verdict_comparison.md)（表 1–5）。逐 scope 判讀：

### A（一軍例行，1,856 場）→ `unsupported` **不變**

四條硬性理由完全相同：池化十分位 1／2／3／8 的偏差 +4.24／+5.55／+6.12／−4.47pt 超界且顯著。
四個分箱在 12 個 seed 下**全部 12/12**、在 6,000 次重抽下即定案、加碼到 96,000 次仍不變
（`p_one` 全部 ≤ 0.0003）。**A 的核心宣稱對 seed 與預算完全穩健**，這是本卡的不放寬對照組。

兩處讀法變了但不影響判定：

- A-7（−3.65pt；`budget_trace.md` 記 −3.64pt，差在 `pred`／`actual` 是否先各自捨入到
  小數第 4 位，不影響任何判定。超界）：v2 那個 seed 判不顯著、12 seed 投票 6/12（多數決在這裡沒有定義）。
  v3 池化 96,000 次後 `p_one=0.008365`、MC 區間 `[0.00753, 0.00929]` 整段在 `α_one=0.005`
  之上 → **確定性地判 `not_significant`**。RESAMPLE1 §5 說「A 十分位 7 的新顯著是雜訊，
  不得寫進對外文案」——v3 把這個結論從人工判讀變成機制內建。
- A-9（−1.40pt，**未**超界）：8/12 seed；加碼到上限 96,000 次後 `p_one=0.004802`、
  MC 區間 `[0.00418, 0.00552]` 仍跨過 `α_one=0.005` → `undetermined`、`hit_reps_cap=true`。
  這是全卡唯一撞上限的統計量，也是「多數決會出錯」最直接的證據：8/12 的多數決會宣告它顯著，
  而真正的尾機率就壓在門檻上、96,000 次重抽都分不出來。因為幅度沒超界，兩套規則下都不構成
  失敗；v3 額外把「這個統計量判不動」明白記進 artifact。

### C（一軍總冠軍賽，25 場）→ `unsupported` → **`insufficient_evidence`**

v2 的唯一硬性理由是 `proxy 池化 ECE 0.11001 > 0.05`。v3 判定該門檻 `unreachable`：

- 完美校準零假設的期望 ECE = **0.07685**，已高於門檻 0.05。
- 觀測值 0.11001 落在 H0 的 p95 = 0.12020 **之內**——與完美校準不可區分。
- 內部佐證：`significant_bins = []`，十個十分位沒有一個顯著（且 C 的分箱 n 全 < 1,000，
  本來就進不了決定性閘門）。
- 模型其實贏基準：池化 Brier 0.15027 vs 全押主場 0.25676。

另外 C2024／C2025 的逐季 Brier 閘門在 v3 下判 `not_significant`（Δ 的 99% CI 分別
`[-0.1989, 0.0242]`、`[-0.1955, 0.1121]`，都含 0）——這兩季各只有 5 場，本來就沒有判別力。
**兩者都進 `insufficient`，沒有任何一條變成硬性失敗，也沒有任何一條被放行。**

### D（二軍例行，1,171 場）→ 今日 × v2 `supported` → **`unsupported`**

唯一決定性分箱是池化十分位 2（+5.01pt，n=6,389）：

| | 判定依據 | 結果 |
|---|---|---|
| v2（單一 seed 20260725） | 99% CI `[-0.0005, 0.0967]` | 含 0 → 不顯著 → **supported** |
| 12 seed 投票 | 11/12 判顯著 | — |
| v3（池化 12,000 次重抽） | `p_one = 0.00225`、MC 區間 `[0.00127, 0.00397]` 整段 < 0.005 | **顯著** → **unsupported** |

即 v2 的 `supported` 是 1/12 的抽樣實現造成的。v3 在 6,000 次下判 `undetermined`、
自動加碼到 12,000 次後定案，**與已發布 artifact 的 `unsupported` 一致**，而且不再隨 seed 擺盪。

> **這一格同時回答了 `#98` §7-D1 與 `RESEARCH-VERDICT-AUDIT1` §3.1-D 留給需求方的選擇題。**
> 兩張卡當時的三個選項是 (a) 維持 unsupported 但改寫理由為「顯著性隨重抽擺盪」、
> (b) 依機械判定翻 supported、(c) 先修判定機制再重跑定案。需求方選了 (c)，本卡就是 (c)，
> 而定案結果是：**顯著性並沒有真的在擺盪，是 500 次重抽估不準極端分位數**。
> 加碼到 12,000 次後它穩定地顯著。故 (a) 的措辭「顯著性隨重抽實現擺盪」若寫進對外文案，
> 今天看是**不準確**的——擺盪的是估計量，不是被估的東西。

三個仍需揭露、但不改變判定的事實：D-3（+4.19pt）與 D-4（+3.05pt）幅度超界但確定性地不顯著；
`decile_max_dev` 的 v1 點估計旗標逐季仍在（僅供參考，不進判定）。

### E（一軍季後挑戰賽，13 場）→ `unsupported` → **`insufficient_evidence`**

v2 的兩條硬性理由**兩條都失效**：

1. `E2025 Brier 0.28588 未勝過主場常數基準 0.25301`——E2025 只有 4 場。Δ = +0.03287、
   99% CI `[-0.1735, 0.1835]`、`p_one = 0.3832`：與 0 完全不可區分。
2. `proxy 池化 ECE 0.08548 > 0.05`——完美校準零假設的期望 ECE 是 **0.12224**，
   **比觀測值還高**。門檻 0.05 遠低於 13 場的雜訊底線。

模型贏基準：池化 Brier 0.14842 vs 0.23764。E 的處置不變（不上線），但成因是**永遠拿不到樣本**
（每季 3–4 場），不是模型被測出不好。

---

## §4 驗證

- `uv run ruff check`：PASS
- `uv run pytest`：**1470 passed, 9 skipped**（基準 1454/10）。+15 為新增測試；另有 1 筆由
  skip 轉 pass，是環境造成的（`requires CARD_ID-isolated PostgreSQL` 一類的條件 skip，
  本機 DB 起著時會實跑），**collected 總數兩邊皆 1,479，未新增或移除任何既有測試**。
- `uv run python -m cpbl.models.winprob_val --out docs/research/ML-WP-VERDICT-ROBUST1/verdict_metrics.json`
  ——全 scope 重跑約 21 秒；stdout 完整表格留在 [`verdict_run_stdout.txt`](verdict_run_stdout.txt)。
  **`--out` 一律導向本卡目錄**；預設路徑 `docs/research/game_recap_wp_val1_metrics.json` 是
  #100 要重生成的檔，本卡一個位元都沒碰。
- `uv run python docs/research/ML-WP-VERDICT-ROBUST1/compare_verdicts.py --check`：
  `CHECK OK：交付內容與腳本重生成結果逐位相同`
- `uv run python docs/research/ML-WP-VERDICT-ROBUST1/budget_trace.py`：邊界分箱的預算軌跡
- 回歸：`docs/research/ML-WP-VAL-RESAMPLE1/bin_stability.py`（已交付、不在寫入集，
  以 `--out` 導向暫存路徑執行）仍可跑，且其獨立算出的 seed 票數與本卡逐位吻合
  （A-7 6/12、D-2 11/12、A bin2/3/8 12/12）——兩條獨立程式路徑互證。
- 回歸：`docs/research/RESEARCH-VERDICT-AUDIT1/analyze_gates.py --check` 仍 `CHECK OK`。

### artifact 紀律

沿用 `RESEARCH-VERDICT-AUDIT1` 的做法：**產物內不放 wall-clock 時戳**（否則每次重跑都把
worktree 弄髒，「重跑後 worktree 髒了」就不再是訊號），provenance 由交付 commit 承擔。
`compare_verdicts.py` 有 `--check`。

`verdict_metrics.json` 與 `budget_trace.json` 依賴 DB，是 **as-of 2026-08-07 的快照**
（母體逐日增長，統計紅線 #9），同日稍後重跑場數會略大；查核者重跑要看的是**判定與決策軌跡
是否一致**，不是位元相同。`compare_verdicts.py --check` 才是「分析由腳本產生、非人工謄寫」
的那道保證。

---

## §4.1 更正：`1f50742` 的 commit message 敘述（ROBUST1-R1-01）

`1f50742` 的 commit message 寫「百分位法下『CI 排除 0』⟺ p_one < α_one」，把一個
**母體語意的等價**寫成了實作層的精確恆等。該 commit 已推出去，**不改寫歷史**，
更正記在這裡：

> 正確敘述：兩者在**精確算術下**等價（`Fraction` 窮舉 n=2..300,000，反例 0 個），
> 但實作層在邊界有兩處有限樣本偏離——`α_one` 的二進位浮點表示，以及 `_percentile_ci()`
> 端點捨入到小數第 4 位。偏離方向都是「更難判顯著」，判定實際採用的是 Wilson 區間
> 對 `α_one` 的比較，故不影響任何結論。詳見 §2.1 的引用區塊。

**這是同一家族的第三次**（`#98` 宣稱某測試「上抽前會紅」而實際不會；ai-workflow `#10`
把裁決的「延伸而非取代」寫成新的互斥引用規則；本卡把近似寫成恆等）。三次的**碼都是對的**，
錯的都是描述證據的那句話。本卡的處置除了改字，還把該敘述**變成可執行的斷言**
（`test_tail_probability_and_percentile_ci_agree_exactly_but_not_in_floating_point`
同時釘住「精確算術下等價」與「浮點/捨入下的兩個已知偏離」），讓下一個人改壞它時會紅。

---

## §5 範圍外發現（只列出，不處置）

- **G1（要緊，承接 RESAMPLE1 §6-F5）｜生產 `run_dist` artifact 仍與本機 DB 不一致**。
  本卡重跑的 `counting_machine_check` 依然是 `MISMATCH`（48 個狀態 vs 48 個狀態）。
  這是 VAL1 不變量 2 的實體，意思是**生產 `/recap-wp` 的 scorer 跑在一份與 harness 不同的
  分布上**。與本卡無關（唯讀），但 artifact 重生成（#100）時必須把 `cpbl.run_dist` 一起納入。
- **G2｜極小叢集數下 bootstrap 的「解析得出來」可能是假的**。C2021／C2022（各 4 場）與
  E2022–E2024（各 3 場）的逐季 Brier 閘門在 v3 下判 `significant`（模型勝基準）。3–4 個
  叢集的重抽分布最多只有 3–4 個相異值，尾機率是粗糙的離散量，「顯著」在這裡不宜當結論。
  今日它們全部落在 pass 方向、且 C／E 已因其他閘門判 `insufficient_evidence`，**不影響任何
  scope 的結論**；但若日後有 scope 的判定掛在這種季上，需要一道叢集數下限的可計算判準
  （不得寫死數字）。已在報告記錄，未加閘門。
- **G3｜非決定性分箱也會觸發預算加碼**。加碼是以「整個統計量還有沒有 undetermined 分箱」
  為條件，於是 A-9（|dev| 未超界、判不動也不影響結果）把 A 的全部池化分箱一路推到
  96,000 次重抽。代價是 A scope 多花約 15 秒。要修需要把門檻知識下推到重抽函式，
  分層上不划算，故留著。
- **G4｜`verdict_for()` 的 proxy 揭露句原本寫錯**。基準版寫「模型分布借自他 scope
  （C←A、**E←D**）」，但 `TRAIN_PROXY` 自 FIX1 起已是 `{"C": "A", "E": "A"}`。本卡在重寫該
  函式時順手改成 `E←A`。這是**碼內文案的事實修正**，不是研究報告內文（#105 的範圍）；
  若查核者認為連這也該留給別張卡，可要求還原。

---

## §6 待需求方裁決

- **P1｜`insufficient_evidence` 的對外詞彙**。卡面寫的是「新增『樣本不足』判定」，
  程式上我用 `insufficient_evidence`（證據不足）而非 `insufficient_sample`（樣本不足），
  因為它要吃下三種來源：**無可評樣本**、**門檻在此樣本量下不可達**（C／E，真的是樣本問題）、
  **決定性統計量在重抽上限內判不動**（D-2 型態，是計算預算問題）。D 今日並未落在這一格，
  但機制上它可能落在。若需求方希望對外只出現「樣本不足」一種說法，需要決定第三種來源
  要不要另立名字。**#100 的對外文案要用哪個詞，等這個裁決。**
- **P2｜D scope 的對外理由改寫**。`#98` §7-D1 與 AUDIT1 §3.1-D 都在等這個。本卡的定案是
  「顯著性沒有真的在擺盪，是估計量不準」，因此 (a) 選項的措辭「顯著性隨重抽實現擺盪」
  **今天已不準確**。建議措辭：D 二軍例行的池化十分位 2 偏差 +5.0pt 超出 ±3pt 上限且顯著
  （12,000 次 game-cluster 重抽，`p_one=0.0023`）→ `unsupported`。請需求方確認。
- **P3｜`BOOT_MAX_REPS = 96,000` 這個上限**。它是 v3 唯一還會左右結果的任意數字。今日只有
  A-9 撞頂且不影響判定。若日後常態撞頂，我的立場是**調高上限**（那是算力問題），
  而不是改判定規則——但這條紀律需要需求方認可才算數。
- **P4｜G2 的叢集數下限**。要不要為「叢集數過少時 bootstrap 的三態不予採信」加一道可計算
  閘門？加了會讓 C／E 的逐季閘門全部落入 `insufficient`（更誠實但更囉嗦），不加則保留一個
  已知會給出脆弱「顯著」的角落。今日不影響任何判定，故未動。
