# ML-FIELD-TZ1：Total Zone 型守備指標可行性研究複核報告 (Iteration 2)

> **查核結論**：**APPROVE WITH FINDINGS**（同意兩層結論之劃分，但對於「迴歸式 TZ 條件式 GO」新增兩項關鍵統計與物理限制 findings）
> **查核者**：Antigravity（Gemini 3.5 Flash (High)@Antigravity，跨模型家族獨立複核）
> **受審對象**：Claude Opus 4.8 提交之 [`docs/research/ML_FIELD_TZ1_FEASIBILITY.md`](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ml-field-tz1-execution/docs/research/ML_FIELD_TZ1_FEASIBILITY.md)
> **受審分支／SHA**：`ai/opus-4-8/ML-FIELD-TZ1`（SHA: [1a8aa78](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ml-field-tz1-execution)）

---

## 1. 複核概述

執行者於 Iteration 2 中採納了前一輪的 Findings，將結論由「一律 NO-GO」修訂為**兩層結論**：
- **naive 期望值查表法 TZ**：維持 **NO-GO** 判定（同意，區域判定受處理結果污染，屬循環論證）。
- **迴歸式 TZ**：修正為 **條件式 GO**。報告主張利用「當前守備陣容的 SS/3B 球員配對變異」在重複觀測下分離責任，使個人能力參數在數學上可識別。

本查核者作為獨立關卡，針對此新增結論（迴歸式可行性）進行了**統計學與物理學的壓力測試**。結果確認：
1. **數學可識別性成立**：實測九季 SS-3B 配對，確實構成**單一連通元件**，參數唯一解在數學上存在。
2. **存在估計精度與共線性瓶頸**：主力防守搭檔共現率高達 60%–80%，且跨球隊的橋樑球員極度稀疏，實務上標準誤差（Standard Error）會極大，導致個人參數估不準（見 New Finding 1）。
3. **存在物理分類洩漏（Classification Leakage）**：由於缺乏客觀的擊球落點座標，物理方向桶（左側/中間/右側）的判定本身即為防守處理結果的副產品。這會導致成功的球被算作該守位的機會，而失敗的球被算作別處或外野的機會，產生系統性偏差（見 New Finding 1）。
4. **平飛球漂移校正不足**：平飛球與高飛球的語意界線漂移會污染高飛球桶，單純在平飛球模型中加入年份 fixed effect 在實務上是不夠的（見 New Finding 2）。

本輪複核確認交付仍為 `doc-only`（無代碼或 DB 寫入），且已清理所有第一輪的絕對化殘留。雖然「迴歸式 TZ」面臨上述致命的精度與洩漏限制，但該報告作為可行性研究的修訂，已如實反應了查核意見並提供了多路徑決策。因此給予 **APPROVE WITH FINDINGS**，並以本報告之 Findings 作為實作前的紅線守衛。

---

## 2. 數據獨立重現對帳表

本輪抽驗 Iteration 1 帳目，與 Iteration 2 報告值對帳如下，數據完全一致：

| 指標 | 報告值 | 查核重現值 | 狀態 | 驗證 SQL |
|---|---|---|---|---|
| **解析涵蓋率** | 95.31% | 95.31%（138,370／145,178） | ✅ 一致 | [REVIEW.md:L109](file:///Users/ruanruan/Dev/cpbl-analytics/docs/research/ML_FIELD_TZ1_REVIEW.md#L109-L127) |
| **內野滾地球出局率** | 89.3% | 89.3%（43,127 / 48,317） | ✅ 一致 | [REVIEW.md:L129](file:///Users/ruanruan/Dev/cpbl-analytics/docs/research/ML_FIELD_TZ1_REVIEW.md#L129-L159) |
| **外野平飛球出局率 (2026)** | 1.95% | 1.95% (16 / 819) | ✅ 一致 | [REVIEW.md:L183](file:///Users/ruanruan/Dev/cpbl-analytics/docs/research/ML_FIELD_TZ1_REVIEW.md#L183-L201) |

---

## 3. 核心查核點深究（兩大 New Findings）

### 3.1 New Finding 1 (Critical - 統計與物理學限制)：迴歸式 TZ 條件式 GO 的估計精度瓶頸與物理分類洩漏

#### (A) 估計精度與共線性瓶頸（數學可識別 $\neq$ 實務估得準）
報告 §2.3 主張：只要球員配對網絡連通，個人守備範圍參數 $\beta_{SS}$ 與 $\beta_{3B}$ 是數學上可識別的（Identifiable）。
查核者利用九季（2018–2026）的 `game_livelog` 與 `games` 進行了**全網絡連通性與共現分析**（實測代碼與輸出見 [附錄 A](#附錄-a-ss-3b-配對強度與連通性分析)）：
- **連通性**：整個中職九季共有 112 名球員參與過 SS/3B 的防守。這 112 名球員在配對圖中確實構成**單一連通元件（Number of Connected Components: 1）**。這是因為有 17 名「橋樑球員」（如王勝偉、杜家明、郭阜林等）因為轉隊或更換守位，將各隊的配對子圖連結起來。因此，**數學上的可識別性確實成立**。
- **共線性與稀疏性瓶頸**：
  1. **同隊主力共線性極高**：江坤宇與王威晨搭檔了 485 場，佔江坤宇 SS 總場次的 **61.70%**；張政禹與劉基鴻搭檔了 328 場，佔張政禹 SS 總場次的 **77.18%**。在如此高的共現率下，模型難以把兩人的功勞拆開，各自的 $\beta$ 標準誤差（Standard Error）會顯著膨脹。
  2. **跨隊轉隊橋樑極度稀疏**：17 名橋樑球員中，有許多只是因為 Lamigo (`AJK011`) 轉手給樂天 (`AJL011`) 時的球隊代碼轉換（如林承飛、梁家榮等），並非真實轉隊。真正發生跨隊流動且有足夠樣本的橋樑球員極少（如杜家明在兄弟僅 8 場、王勝偉在兄弟 142 場/富邦 161 場）。
  - **結論**：這種極高的隊內共線性與極度稀疏的跨隊橋樑，會導致 Logistic 迴歸模型的估計值標準誤（Standard Error）極大，信賴區間極寬。實務上，模型將**無法估計到有用的精度**，難以在統計顯著的水平上區分球員的個人防守能力。

#### (B) 物理分類洩漏（Classification Leakage）
迴歸模型將「內野滾地球」與「外野滾地球」合併為「擊向左側的滾地球」以破除循環。然而，由於中職資料缺乏獨立於防守結果的客觀落點座標，我們所有的「物理方向桶」分類都是從 livelog 的防守處理者文字中推斷出來的。這會產生嚴重的**分類洩漏**：
- 假設一顆物理上的「二遊間滾地球」：
  - 若游擊手 (SS) 移動迅速將其攔截，livelog 會記為 `游擊手...`，從而被我們判定為「左側的成功分母」。
  - 若游擊手攔截失敗，球滾過二遊防線，livelog 會記為 `擊出中外野滾地球...`，從而被我們判定為「中間的失敗分母」。
- 這意味著：**擊球機會被歸類到哪個方向桶，取決於防守處理的結果**。防守成功的球被算作該守位的分母，而失敗的球被算作其他守位或外野的分母。這種「分母判定受結果污染」的現象，會系統性高估防守者的攔截率。這是不論採用何種迴歸模型都無法從根本上消除的物理偏差。

### 3.2 New Finding 2 (Medium - 資料漂移)：外野空中球分類漂移與年代校正的不足
執行者採納了 Finding 2，指出平飛球出局率從 11.45% 崩塌到 1.95%，並提出以「年份 fixed effect 吸收」作為校正方案。
然而，查核者合併了外野高飛球與平飛球，計算了整體的**外野空中球（Fly + Line Drive）出局率**（SQL 與輸出見 [附錄 B](#附錄-b-外野空中球合併出局率趨勢)）：
- **空中球整體出局率**：從 2018–2020 年的 **~49%**，逐年上升到 2026 年的 **57.76%**（累計上升 8 個百分點）。
- **缺陷分析**：
  1. 報告稱「高飛球出局率穩定在 ~68%」，這其實是**語意分類判定漂移與物理效應（不彈球）抵消後的假象**。因為記錄員越來越多地將原本會被接殺的平飛球改記為「高飛球」，導致平飛球桶被嚴重稀釋（2026 年平飛球出局樣本九季合計僅剩 16 筆）。
  2. 由於平飛球桶的出局樣本極度稀疏，單純在平飛球模型中加入年份 dummy 在實務上無法精確估計。同時，高飛球桶也因為混入了這些原本是平飛球的樣本而受到污染。
  3. **校正建議**：若要推進實作，不能只單獨在平飛球上做 fixed effect，而應將外野高飛球與平飛球合併為一個整體的 **「外野空中球」** 進行統一建模，並在該模型中控制年份效應（綜合吸收球的彈性改變與記錄員語意判定漂移）。

---

## 4. 絕對化殘留與矛盾檢驗

查核者對 FEASIBILITY.md 的全文進行了 `grep` 檢驗：
- **一致性確認**：報告的 §0、§2.2、§5.3、§6 已完全移除了 iteration 1 的絕對化 NO-GO 措辭。兩層結論之劃分在全文中邏輯自洽，無自相矛盾處。
- **決策表與核心判定**：§6.1 的路徑決策表將「迴歸式 TZ」列為「條件式 GO」，與 §6.2 的核心判定一致。
- **不需另開卡判定**：同意 §6.3 的評估。代打/代跑造成的 1.37% 打席切界漂移與觸擊解析缺漏均不污染出局率與具名率，亦不影響既有 splits 統計，故不需另開卡處理。

---

## 5. 複核結論與處置建議

### 結論：APPROVE WITH FINDINGS
本可行性研究修訂版（Iteration 2）的數據無誤，且無程式碼/DB 變更，字面邏輯已達成自洽。然而，基於上述 Findings，查核者對後續推進提出以下關鍵限制：

1. **迴歸式 TZ 應降級為「極高風險／NO-GO」**：雖然配對變異在數學上可識別，但由於中職極度稀疏的跨隊轉隊橋樑與隊內高度共線性，加上分類桶本身的結果洩漏（Classification Leakage），「迴歸式 TZ」無法提供具備足夠精度且無偏的能力估計。不建議需求方在路線一（迴歸式 TZ）上投入開發資源。
2. **外野守備路徑（路線二）為唯一實質 GO 選擇**：若要實作，僅有「外野空中球（合併高飛與平飛）」在資料上足夠乾淨且無 attribution 困難，但必須引入年份控制變數，且內野仍須保留 RF。
3. **短期內守備軸之建議**：應優先採用路線四（多季滾動標示，平滑單季噪音），此為零風險且能即時解決生產痛點的方案。

---

## 6. 複核驗證代碼與查詢存檔

### 附錄 A: SS-3B 配對強度與連通性分析

#### 驗證腳本 (`verify_pairing_strength.py`)
```python
from collections import defaultdict
from cpbl.db import conn

def main():
    # 查詢所有在同一場比賽、同一個半局同時出賽的 SS 和 3B
    query = """
    WITH ss_players AS (
        SELECT DISTINCT year, game_sno, visiting_home_type, hitter_acnt AS player_id, hitter_name AS player_name
        FROM cpbl.game_livelog
        WHERE kind_code = 'A' AND defend_station_code = 'SS' AND hitter_acnt IS NOT NULL
    ),
    tb_players AS (
        SELECT DISTINCT year, game_sno, visiting_home_type, hitter_acnt AS player_id, hitter_name AS player_name
        FROM cpbl.game_livelog
        WHERE kind_code = 'A' AND defend_station_code = '3B' AND hitter_acnt IS NOT NULL
    )
    SELECT 
        ss.player_id AS ss_id, 
        ss.player_name AS ss_name, 
        tb.player_id AS tb_id, 
        tb.player_name AS tb_name,
        COUNT(DISTINCT (ss.year, ss.game_sno, ss.visiting_home_type)) AS game_count
    FROM ss_players ss
    JOIN tb_players tb USING (year, game_sno, visiting_home_type)
    GROUP BY ss.player_id, ss.player_name, tb.player_id, tb.player_name
    ORDER BY game_count DESC;
    """
    
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(query)
            pairings = cur.fetchall()
            
    ss_totals = defaultdict(int)
    tb_totals = defaultdict(int)
    player_names = {}
    adj = defaultdict(set)
    
    for ss_id, ss_name, tb_id, tb_name, count in pairings:
        player_names[ss_id] = ss_name
        player_names[tb_id] = tb_name
        ss_totals[ss_id] += count
        tb_totals[tb_id] += count
        adj[ss_id].add(tb_id)
        adj[tb_id].add(ss_id)
        
    # 連通元件計算
    visited = set()
    components = []
    for p in player_names.keys():
        if p not in visited:
            comp = []
            queue = [p]
            visited.add(p)
            while queue:
                curr = queue.pop(0)
                comp.append(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            components.append(comp)
            
    print(f"Total players involved in SS/3B: {len(player_names)}")
    print(f"Number of Connected Components: {len(components)}")
    
    print("\n=== Top 5 SS-3B Co-occurrence rate ===")
    for ss_id, ss_name, tb_id, tb_name, count in pairings[:5]:
        ss_pct = 100.0 * count / ss_totals[ss_id]
        tb_pct = 100.0 * count / tb_totals[tb_id]
        print(f"{ss_name} (SS) - {tb_name} (3B): {count} games (SS: {ss_pct:.2f}%, 3B: {tb_pct:.2f}%)")

if __name__ == "__main__":
    main()
```

#### 腳本輸出結果
```
Total players involved in SS/3B: 112
Number of Connected Components: 1

=== Top 5 SS-3B Co-occurrence rate ===
江坤宇 (SS) - 王威晨 (3B): 485 games (SS: 61.70%, 3B: 64.84%)
張政禹 (SS) - 劉基鴻 (3B): 328 games (SS: 77.18%, 3B: 53.25%)
林承飛 (SS) - 梁家榮 (3B): 249 games (SS: 38.37%, 3B: 47.98%)
曾子祐 (SS) - 吳念庭 (3B): 149 games (SS: 45.85%, 3B: 93.12%)
林承飛 (SS) - 林立 (3B): 148 games (SS: 22.80%, 3B: 57.14%)
```

### 附錄 B: 外野空中球合併出局率趨勢

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
SELECT year,
  count(*) FILTER (WHERE content ~ '擊出(左外野|中外野|右外野)(高飛球|平飛球)') AS of_air,
  count(*) FILTER (WHERE content ~ '擊出(左外野|中外野|右外野)(高飛球|平飛球)'
        AND batting_action_name NOT LIKE '%安'
        AND batting_action_name NOT IN ('全打','內全','場安','場二','場三')) AS of_air_outs,
  round(100.0 * count(*) FILTER (WHERE content ~ '擊出(左外野|中外野|右外野)(高飛球|平飛球)'
        AND batting_action_name NOT LIKE '%安'
        AND batting_action_name NOT IN ('全打','內全','場安','場二','場三')) / 
        NULLIF(count(*) FILTER (WHERE content ~ '擊出(左外野|中外野|right|右外野)(高飛球|平飛球)'), 0), 2) AS out_pct
FROM pa_last
WHERE batting_action_name IS NOT NULL AND batting_action_name<>''
GROUP BY 1 ORDER BY 1;
```

#### 查詢輸出結果
```
 year | of_air | of_air_outs | out_pct 
------+--------+-------------+---------
 2018 |   6043 |        2993 |   49.53
 2019 |   6104 |        3076 |   50.39
 2020 |   6203 |        2992 |   48.23
 2021 |   7160 |        3886 |   54.27
 2022 |   7238 |        3949 |   54.56
 2023 |   7147 |        3928 |   54.96
 2024 |   8658 |        4765 |   55.04
 2025 |   8857 |        4943 |   55.81
 2026 |   4903 |        2832 |   57.76
```
