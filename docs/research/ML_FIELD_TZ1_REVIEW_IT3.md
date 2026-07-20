# ML-FIELD-TZ1：Total Zone 型守備指標可行性研究複核報告 (Iteration 3 - 收斂輪)

> **查核結論**：**APPROVE**（同意結案。執行者已如實收斂所有 iteration 2 的 Critical Findings，全文頭條與判定一致，且無矯枉過正）
> **查核者**：Antigravity（Gemini 3.5 Flash (High)@Antigravity，跨模型家族獨立複核，續任查核者）
> **受審對象**：Claude Opus 4.8 提交之 [`docs/research/ML_FIELD_TZ1_FEASIBILITY.md`](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ml-field-tz1-execution/docs/research/ML_FIELD_TZ1_FEASIBILITY.md)
> **受審分支／SHA**：`ai/opus-4-8/ML-FIELD-TZ1`（SHA: [d4bc597](file:///Users/ruanruan/Dev/cpbl-analytics/.claude/worktrees/ml-field-tz1-execution)）

---

## 1. 複核概述

本輪為 **ML-FIELD-TZ1 (Total Zone 可行性研究)** 的 **iteration 3 (收斂輪)** 複核。任務的核心在於查核執行者（Claude Opus 4.8）是否已根據本查核者於 iteration 2 提出的 Critical Findings，將可行性研究報告的判定進行「如實且精準」的收斂與降級，同時防止反映不足與矯枉過正，並確保全文頭條判定與查核判定一致，無殘留自相矛盾。

經查核：
1. **反映對齊與降級如實**：內野迴歸式 TZ 路線已從 iteration 2 的「條件式 GO／推薦」正式降級為 **「極高風險 → 實務 NO-GO」**，並在 §0 結論、§2.3 核心分析、§5.3 風險評估及 §6 判定與決策路徑中全面更新，標明「不建議投入開發資源」。
2. **無矯枉過正，保留數學事實**：報告正確保留了「配對變異使個人參數在數學上可識別（單一連通元件）」的統計學事實，並在其上精準劃分「可識別 ≠ 估得準（共線性 + 稀疏橋樑）」的估計精度瓶頸，表述恰當。
3. **分類洩漏（Classification Leakage）完整採納**：報告詳細重述了「物理方向桶歸屬由守備成敗決定（成功記本位，失敗滾去外野）」所導致的物理偏差，說明該偏差在無客觀落點座標下任何迴歸均無法消除，論述扎實。
4. **外野空中球合併校正與獨立重現**：外野空中球已從「分桶各自年代校正」修正為 **「合併高飛＋平飛為單一外野空中球 + 年份 fixed effect 統一吸收」**。本查核者獨立跑 SQL 重現九季合併出局率，數據為 **49.53% (2018) → 57.76% (2026)**（累計上升 8.23%），與報告所述完全一致。
5. **全文頭條一致，無殘留矛盾**：`grep` FEASIBILITY 全文確認，「條件式 GO」僅存在於外野空中球指標，迴歸式 TZ 的條件式 GO 僅保留於修訂註記歷史（§0、§2.3、§6.1、§7 表格中註明 iteration 2 歷程），正文無任何殘留。

因此，本輪給予 **APPROVE** 判定，同意此可行性研究報告結案。

---

## 2. 數據獨立重現與複驗對帳表

本輪針對外野空中球合併出局率進行獨立 SQL 重跑與對帳，結果如下：

| 指標 / 年份 | FEASIBILITY 報告值 | 查核重現值 | 狀態 | 驗證 SQL / 數據源 |
|---|---|---|---|---|
| **2018 合併外野空中球出局率** | 49.53% | 49.53%（2,993 / 6,043） | ✅ 一致 | 獨立 SQL (修正 typo 後) |
| **2021 合併外野空中球出局率** | 54.27% | 54.27%（3,886 / 7,160） | ✅ 一致 | 獨立 SQL (修正 typo 後) |
| **2026 合併外野空中球出局率** | 57.76% | 57.76%（2,832 / 4,903） | ✅ 一致 | 獨立 SQL (修正 typo 後) |

### 複驗 SQL
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
  count(*) FILTER (WHERE content ~ '擊出(left|左外野|中外野|right|右外野)(高飛球|平飛球)'
        AND batting_action_name NOT LIKE '%安'
        AND batting_action_name NOT IN ('全打','內全','場安','場二','場三')) AS of_air_outs,
  round(100.0 * count(*) FILTER (WHERE content ~ '擊出(左外野|中外野|右外野)(高飛球|平飛球)'
        AND batting_action_name NOT LIKE '%安'
        AND batting_action_name NOT IN ('全打','內全','場安','場二','場三')) / 
        NULLIF(count(*) FILTER (WHERE content ~ '擊出(左外野|中外野|右外野)(高飛球|平飛球)'), 0), 2) AS out_pct
FROM pa_last
WHERE batting_action_name IS NOT NULL AND batting_action_name<>''
GROUP BY 1 ORDER BY 1;
```

---

## 3. 三大查核點深究與收斂判定

### 3.1 查點 1：迴歸式 TZ 降級的「如實性與精準性」
- **反映不足檢查**：
  - **結論與表頭**：§0 的結論表格與 §6.1 路線一，已將「內野迴歸式 TZ」標記為 **「極高風險 → 實務 NO-GO」**，且在關鍵前提／限制中寫明 `不建議投入開發資源`。
  - **風險評估升級**：§5.3 風險評估表中，新增並將 `內野分類洩漏` 與 `內野共線性 + 稀疏橋樑` 列為 🔴 高風險。
  - **核心判定對齊**：§6.2 核心判定第 2 點寫道：`內野迴歸式 TZ：極高風險 → 實務 NO-GO ... 不建議在內野迴歸式 TZ 投入開發資源`。
- **矯枉過正檢查**：
  - 報告在 §2.3 與 §6.2 正確保留了「配對變異使參數數學上可識別」這一事實（中職九季 SS-3B 共 112 名球員確實構成單一連通元件），但緊接著指出其在估計精度上的實務瓶頸（同隊主力共現高達 60%–80% 造成共線性，跨隊橋樑極度稀疏使標準誤極大），這恰到好處地保留了統計學邊界，未將可識別性本身抹煞。
- **分類洩漏（Classification Leakage）的吸收**：
  - §2.3 關卡二中，執行者用非常生動的例子（二遊間滾地球成功記 SS 左側、失敗記中外野中間，使成敗反向污染方向桶）清晰說明了 Classification Leakage 的本質。這證明 it2 Review 提及的 Critical Finding 已被完整融入，無淡化。

### 3.2 查點 2：外野空中球合併校正的採納
- **合併建模**：§3.1 的結論與 §6.1 路線二中，已將原先的各自校正改為 **「合併高飛＋平飛為單一外野空中球」**。
- **漂移驗證**：報告中正確認識到平飛球單獨出局率的暴跌（11.45%→1.95%）會伴隨其樣本退化而無法單獨精確估計，且移走的接殺球流入了高飛球桶，導致高飛球看似平坦的假象。
- **年代效正**：改為將兩者合併並以年份 fixed effect 統一吸收（2018年 49.53% 上升至 2026年 57.76%），該方案與 it2 Review之建議完全吻合。

### 3.3 查點 3：兩份文件之一致性與全文無殘留矛盾
- **Grep 檢驗**：FEASIBILITY.md 全文中，「條件式 GO」僅出現在外野空中球範圍指標的判定中。
- **矛盾清理**：
  - 內野迴歸式 TZ 的「條件式 GO／推薦」已完全移出正文判定，僅保留於 §0 的警告備忘與 §7 的修訂紀錄（明確標明為 iteration 2 歷史）。
  - FEASIBILITY §6.2 的核心判定與本查核者在 REVIEW_IT2 §5 的處置建議完全一致。

---

## 4. 複核結論與處置建議

### 結論：APPROVE (同意結案)

本可行性研究報告（Iteration 3）已徹底且嚴謹地收斂了所有關鍵 findings。

給予需求方（Coordinator）的最終決策指引：
1. **內野守備指標**：在 CPBL 現有資料下（無獨立客觀擊球落點座標），內野**沒有**任何可信且精度足夠的個人守備價值指標（TZ naive 查表法與迴歸式配對法皆已被否決）。**內野路線確定 NO-GO，切勿投入任何開發資源**。
2. **外野守備指標**：唯一實質可行的路徑是 **「外野空中球範圍指標（合併高飛與平飛，控制年份）」**（路線二，條件式 GO），但該指標填不滿內野，故不能取代現行能力卡的守備軸。
3. **短期最優解**：應優先採行 **「多季滾動標示」**（路線四，XS 工作量），UI 僅顯示三年 rolling average 平滑單季噪音，這是零風險且能即時緩解單季 RF 守備軸波動的方案。
