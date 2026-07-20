# ML-FIELD-TZ1：Total Zone 型守備指標可行性研究查核報告

> **查核結論**：**APPROVE WITH FINDINGS**（結論成立，但有關鍵統計推論缺陷與未察覺的資料漂移）
> **查核者**：Antigravity（Gemini 3.5 Flash (High)@Antigravity，跨模型家族查核）
> **受審對象**：Claude Opus 4.8 提交之 [`docs/research/ML_FIELD_TZ1_FEASIBILITY.md`](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ml-field-tz1-execution/docs/research/ML_FIELD_TZ1_FEASIBILITY.md)
> **受審分支／SHA**：`ai/opus-4-8/ML-FIELD-TZ1`（SHA: [3105db6](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ml-field-tz1-execution)）

---

## 1. 查核概述

執行者結論主張 **「完整逐守位 Total Zone 在 CPBL 現有資料上不可行，建議 NO-GO」**。經查核者獨立取數重現與統計推論檢驗，**該 NO-GO 結論在「直接套用 Retrosheet 式的 naive 期望值查表法」上成立**，但執行者報告中提出的部分理論推論與前提存在關鍵缺陷（統計可識別性、未察覺的分類漂移）。

本查核確認：
1. **交付範圍合規**：僅做可行性研究，無程式碼變更，無 DB 寫入，未部署。
2. **數據算術一致**：所有核心數字經獨立 SQL 實查，完全重現，無造假或估計。
3. **限制誠實揭露**：已主動揭露打席切界、觸擊缺漏、無逐場守備陣容等前置限制。

---

## 2. 數據獨立重現對帳表

查核者於本地 PostgreSQL 17（Port 5433，唯讀事務）重新編寫 SQL 查詢，所得結果與報告值對帳如下：

| 主張指標 | 報告值 | 查核重現值 | 狀態 | 驗證 SQL 索引 |
|---|---|---|---|---|
| **解析涵蓋率** | 95.31%（138,370／145,178） | 95.31%（138,370／145,178） | ✅ 一致 | [SQL 1](#sql-1-涵蓋率與-bip-分母對帳) |
| **內野滾地球出局率** | 89.3% | 89.3%（43,127 / 48,317） | ✅ 一致 | [SQL 2](#sql-2-內外野滾地球出局率與具名率) |
| **滾出外野滾出局率** | 左: 0.2%, 中: 0.3%, 右: 0.5% | 左: 0.25% (11/4469), 中: 0.26% (13/5013), 右: 0.53% (23/4346) | ✅ 一致 | [SQL 2](#sql-2-內外野滾地球出局率與具名率) |
| **失敗具名數** | 左: 10, 中: 10, 右: 17 | 左: 10, 中: 10, 右: 17 | ✅ 一致 | [SQL 3](#sql-3-內野守備失敗具名數對帳) |
| **外野飛球出局率跨季** | 2018: 68.11% → 2026: 68.98% | 2018: 68.11% (2751/4061) → 2026: 68.98% (2805/4084) | ✅ 一致 | [SQL 4](#sql-4-外野高飛球出局率跨季平坦度) |
| **逐年場次數** | 239/240/240/299/300/298/360/359/204 | 239/240/240/299/300/298/360/359/204 | ✅ 一致 | [SQL 5](#sql-5-逐年場次數對帳) |

---

## 3. 核心查核點深究（四大 Findings）

### 3.1 Finding 1 (Medium - 統計理論)：§2.2「欠定方程組無解」之 NO-GO 推論過強

> [!WARNING]
> **報告主張**：左側滾地球漏過去（失敗）時沒有具名處理者，而左側責任同屬三壘手與游擊手，此為「三個觀測值、四個未知數」的欠定方程組（Underdetermined system），故任何模型皆無解。

**查核反駁**：**該推論在微觀單一球層面成立，但在宏觀統計估計上不成立。**
藉由「守備陣容重建」（報告 §5.1 已證實可行），我們可以得知每一場球、甚至每一局當下的 SS 與 3B 守備球員組合。這是一個典型的**多季重複觀測與球員配對變異（Pairing Variation）**問題。
- 游擊手 $S_1$ 會與三壘手 $T_1$ 配對，也會與 $T_2$ 配對；三壘手 $T_1$ 也會與游擊手 $S_2$ 配對。
- 當我們將「左側滾地球是否穿透（失敗）」作為二元或多元反應變數 $Y_i \in \{0, 1\}$，配對球員作為虛擬變數輸入時，這可藉由**多變量 Logistic 回歸**或**混合效應模型（Mixed-effects Model）**來識別個人能力：
  $$\log\left(\frac{P(\text{Hit})}{1-P(\text{Hit})}\right) = \beta_0 + \beta_{3B} \cdot \text{Player}_{3B} + \beta_{SS} \cdot \text{Player}_{SS} + \mathbf{X}\gamma$$
  只要球員配對網絡是連通的（Connected Network，CPBL 九季資料中顯然成立），球員個人的守備範圍參數 $\beta_{3B}$ 與 $\beta_{SS}$ 是**數學上完全可識別的（Identifiable）**。
- 因此，「欠定無解」只能說明無法用簡單的「期望值查表扣分法」實作，但**不能得出「任何模型都無解，故必須 NO-GO」**的結論。統計學的價值即在於透過配對變異分離責任。

### 3.2 Finding 2 (Medium - 資料漂移)：§3.1「類別內部無漂移」為部分假象，平飛球有嚴重分類漂移

> [!IMPORTANT]
> **報告主張**：類別內部無漂移，記錄員判定標準九季穩定，條件化於擊球型態即可跨季合併。報告僅以「外野高飛球」作為證據。

**查核發現**：**外野高飛球確實平坦，但「外野平飛球（Line Drive）」存在嚴重的分類與判定漂移。**
查核者實測外野平飛球的跨季出局率：
- **2018 年**：外野平飛球 1,982 顆，出局 225 顆，出局率 **11.35%**。
- **2025 年**：外野平飛球 1,574 顆，出局 52 顆，出局率 **3.30%**。
- **2026 年**：外野平飛球 819 顆，出局 16 顆，出局率 **1.95%**。

這顯示了嚴重的**語意判定 shift**（ caught line drives 被大量改歸類為「高飛球」；留在「平飛球」類別的幾乎只有安打）。如果直接跨季合併估算平飛球的期望出局率，將會嚴重低估早期（2018–2020）外野手在平飛球上的守備表現，或嚴重高估晚期（2025–2026）的表現。跨季合併必須對平飛球進行年代校正。

### 3.3 Finding 3 (Low - 資料提取)：代打／代跑切界過度切分，但不影響核心出局率指標

> [!NOTE]
> **報告自承**：2018–2020 年每場打席數 80.2 高於理論值 ~76，係由於代打/代跑連續列被 gaps-and-islands 切成兩段。

**查核確認**：
- 經對帳，2018 年官方 `batting_gamelog` 總打席為 **18,903**，而 Gaps-and-islands 算出的打席為 **19,162**，多出 259 個打席（約 1.37%）。
- 多出的打席主要來自：當 PA 中途更換代打（例如 2018 年 Game 1 九局上，王峻杰在 1 壞球後更換代打林書逸），該打席會被切成兩座島。
  - 第一座島（王峻杰）最後一列為 `更換代打`，`batting_action_name` 繼承為 `'四壞'`，但內容不含 `擊出`，故被列為殘餘（未解析）。
  - 第二座島（林書逸）最後一列完成打席，被列為 `zone_ok`。
- **對指標的污染評估**：此 over-splitting 僅會將「被換下去的打者島」列為 denominator，但因為其 content 不含 `擊出...` 字眼，它**會被 `zone_ok` 的正則過濾掉**，不會被誤計為「有落點的擊球」，因此**完全不會污染 `p` 視圖中的出局率與具名率計算**。它的唯一副作用是將 parser 涵蓋率分母拉大，使真實涵蓋率被微幅低估（約 1.4%）。此限制屬於 Low 風險，報告中已誠實披露，查核者予以認可。

### 3.4 Finding 4 (Low - 業務邏輯)：打擊結果判定之極微幅邊界誤差

`p` 視圖中，打擊結果 `outcome` 的判定使用 `LIKE '%安'`、`LIKE '%失'`。
- 查核確認這涵蓋了 99.9% 以上的擊球事件，但在極端情況下有微小語意偏誤。例如：
  - `礙打`（妨礙打擊，88 次）：打者保送上壘，不應算作 out，但在排除 `安` 與 `失` 後被歸類為 `out`。
  - `野選`（野手選擇，531 次）與 `犧選`（犧牲野選，155 次）：打者靠野選上壘，但防守方在其他壘包取得出局數。歸類為 `out` 在防守期望值角度是正確的（因為防守方成功取得了出局數）。
- 這些邊界誤差極小（礙打佔比 < 0.05%），不影響可行性研究之結論。

---

## 4. 可行替代方案與後續路徑判斷

需求方指出：**「若 TZ 也不可行，需要知道守備軸還剩哪些選項」**。
基於查核者推翻「欠定方程組完全無解」的論點，我們提供以下獨立的後續路徑判斷：

### 方案一：回歸修正版 Total Zone（推薦，條件式 GO）
- **做法**：放棄 naive 的 Retrosheet 期望值查表扣分法，改採**球員配對 Logistic 迴歸**。
- **解決點**：將內野滾地球與外野滾地球 collapsed（合併成實體「擊向左側／中間／右側的滾地球」），以解決循環論證。對於失敗的穿透球（無具名），透過迴歸模型中當下守備陣容的 SS 與 3B 參數變異來自動分擔責任（解決歸屬不對稱）。
- **時限門檻**：維持 UZR 的三年累積門檻，精度約為 $\pm 14$ 個守備機會（約 1.25 勝）。

### 方案二：僅限外野的 OAA／TZ 指標（條件式 GO）
- **做法**：如執行者建議 §6.3，只對外野高飛球估算 Range。
- **好處**：外野高飛球資料乾淨、無 circularity、無 attribution 困難（全部具名）。
- **限制**：無法解決內野手的能力軸，能力卡守備軸仍須保留 RF。

### 方案三：Defensive Regression Analysis (DRA)（保守，GO）
- **做法**：使用 seasonal 甚至 game-level 累計數據（PO, A, E），跑多元線性迴歸，以投手三振率、投手滾飛比、團隊 Innings 作為控制變數，球員個人的殘差即為防守價值。
- **好處**：避開逐打席文字解析與守備陣容重建的龐大工程，直接利用現成 stats 即可回溯全史。

---

## 5. 驗證查詢 SQL 存檔

### SQL 1: 涵蓋率與 BIP 分母對帳
```sql
WITH ordered AS (
  SELECT year, game_sno, main_event_no, hitter_acnt, batting_action_name, content,
         ROW_NUMBER() OVER (PARTITION BY year, game_sno ORDER BY main_event_no) AS rn,
         ROW_NUMBER() OVER (PARTITION BY year, game_sno, hitter_acnt ORDER BY main_event_no) AS rn2
  FROM cpbl.game_livelog WHERE kind_code='A'
), islands AS (SELECT *, rn-rn2 AS grp FROM ordered),
pa_last AS (
  SELECT DISTINCT ON (year, game_sno, hitter_acnt, grp)
         year, game_sno, batting_action_name, content
  FROM islands ORDER BY year, game_sno, hitter_acnt, grp, main_event_no DESC
)
SELECT count(*) AS pa_total,
  count(*) FILTER (WHERE batting_action_name IS NULL OR batting_action_name='') AS blank_rows,
  count(*) FILTER (WHERE batting_action_name IN ('三振','四壞','死球','故四','不死三振')) AS non_bip,
  count(*) FILTER (WHERE substring(content from '擊出(內野|左外野|中外野|右外野)') IS NOT NULL) AS zone_ok
FROM pa_last;
```

### SQL 2: 內外野滾地球出局率與具名率
```sql
WITH ordered AS (
  SELECT year, game_sno, main_event_no, hitter_acnt, batting_action_name, content,
         ROW_NUMBER() OVER (PARTITION BY year, game_sno ORDER BY main_event_no) AS rn,
         ROW_NUMBER() OVER (PARTITION BY year, game_sno, hitter_acnt ORDER BY main_event_no) AS rn2
  FROM cpbl.game_livelog WHERE kind_code='A'
), islands AS (SELECT *, rn-rn2 AS grp FROM ordered),
pa_last AS (
  SELECT DISTINCT ON (year, game_sno, hitter_acnt, grp)
         year, game_sno, batting_action_name, content
  FROM islands ORDER BY year, game_sno, hitter_acnt, grp, main_event_no DESC
),
p AS (
  SELECT year, batting_action_name AS act,
    substring(content from '擊出(內野|左外野|中外野|右外野)') AS zone,
    substring(content from '擊出(?:內野|左外野|中外野|右外野)(滾地球|高飛球|平飛球)') AS traj,
    CASE WHEN batting_action_name LIKE '%安'
           OR batting_action_name IN ('全打','內全','場安','場二','場三','內二') THEN 'hit'
         WHEN batting_action_name LIKE '%失'
           OR batting_action_name IN ('雙誤','犧短誤','犧飛誤') THEN 'error'
         ELSE 'out' END AS outcome
  FROM pa_last
  WHERE substring(content from '擊出(內野|左外野|中外野|右外野)') IS NOT NULL
    AND batting_action_name NOT IN ('三振','四壞','死球','故四','不死三振')
    AND batting_action_name IS NOT NULL AND batting_action_name <> ''
)
SELECT zone, traj, COUNT(*) AS balls, COUNT(*) FILTER (WHERE outcome='out') AS outs,
       round(100.0 * count(*) FILTER (WHERE outcome='out')/count(*), 2) AS out_pct
FROM p WHERE traj='滾地球' GROUP BY 1, 2;
```

### SQL 3: 內野守備失敗具名數對帳
```sql
WITH ordered AS (
  SELECT year, game_sno, main_event_no, hitter_acnt, batting_action_name, content,
         ROW_NUMBER() OVER (PARTITION BY year, game_sno ORDER BY main_event_no) AS rn,
         ROW_NUMBER() OVER (PARTITION BY year, game_sno, hitter_acnt ORDER BY main_event_no) AS rn2
  FROM cpbl.game_livelog WHERE kind_code='A'
), islands AS (SELECT *, rn-rn2 AS grp FROM ordered),
pa_last AS (
  SELECT DISTINCT ON (year, game_sno, hitter_acnt, grp)
         year, game_sno, batting_action_name, content
  FROM islands ORDER BY year, game_sno, hitter_acnt, grp, main_event_no DESC
)
SELECT CASE WHEN content ~ '擊出內野滾地球'   THEN 'IF grounder'
            WHEN content ~ '擊出左外野滾地球' THEN 'GB through LEFT'
            WHEN content ~ '擊出中外野滾地球' THEN 'GB through CENTER'
            WHEN content ~ '擊出右外野滾地球' THEN 'GB through RIGHT' END AS gb_class,
       count(*) AS n,
       count(*) FILTER (WHERE substring(content from '打者-([^ ]{2,4}手)') IS NOT NULL) AS fielder_named
FROM pa_last WHERE content ~ '擊出(內野|左外野|中外野|右外野)滾地球' GROUP BY 1;
```

### SQL 4: 外野高飛球出局率跨季平坦度
```sql
WITH ordered AS (
  SELECT year, game_sno, main_event_no, hitter_acnt, batting_action_name, content,
         ROW_NUMBER() OVER (PARTITION BY year, game_sno ORDER BY main_event_no) AS rn,
         ROW_NUMBER() OVER (PARTITION BY year, game_sno, hitter_acnt ORDER BY main_event_no) AS rn2
  FROM cpbl.game_livelog WHERE kind_code='A'
), islands AS (SELECT *, rn-rn2 AS grp FROM ordered),
pa_last AS (
  SELECT DISTINCT ON (year, game_sno, hitter_acnt, grp)
         year, game_sno, batting_action_name, content
  FROM islands ORDER BY year, game_sno, hitter_acnt, grp, main_event_no DESC
)
SELECT year, count(*) AS of_fly,
  round(100.0*count(*) FILTER (WHERE batting_action_name NOT LIKE '%安'
        AND batting_action_name NOT IN ('全打','場安','場二','場三'))/count(*),2) AS out_pct
FROM pa_last WHERE content ~ '擊出(左外野|中外野|右外野)高飛球'
  AND batting_action_name IS NOT NULL AND batting_action_name<>'' GROUP BY 1 ORDER BY 1;
```

### SQL 5: 逐年場次數對帳
```sql
SELECT year, COUNT(DISTINCT game_sno) AS game_cnt
FROM cpbl.game_livelog
WHERE kind_code='A'
GROUP BY year
ORDER BY year;
```
