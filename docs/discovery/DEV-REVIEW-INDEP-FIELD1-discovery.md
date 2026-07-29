# DEV-REVIEW-INDEP-FIELD1 Discovery：卡面獨立性要求能不能變成機器可讀欄位

> 卡片：[`../tasks/DEV-REVIEW-INDEP-FIELD1.md`](../tasks/DEV-REVIEW-INDEP-FIELD1.md)　執行者：Claude Opus 5@Claude Code　日期：2026-07-29
> **本文件只回答 Discovery 四問，不含實作。** 改碼須待 `DEV-REVIEW-PROMPT-GUARD1` 合併（同檔互斥）。

## 資料基礎（可重現）

掃描全部卡片的卡面 header〈查核〉欄（第一個 `## ` 標題之前、以 `-` 開頭且含 `查核：` 的行）：

```bash
python3 - <<'PY'
import pathlib
for d in ("docs/tasks","docs/archive/tasks"):
    for p in sorted(pathlib.Path(d).glob("*.md")):
        field = None
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "): break
            if line.lstrip().startswith("-") and "查核：" in line:
                field = line.split("查核：",1)[1].strip(); break
        print(f"{p.stem}\t{field}")
PY
```

**母體 119 張**（活卡 35、封存 84）。欄位缺席 4 張：`INIT-GAME-RECAP`、`INIT-OFFICIAL-DATA1`、`INIT-PRODUCT-UX`（三張皆 Initiative 卡）、`DOC-GAME-RECAP1`。

有欄的 115 張依字樣分類：

| 類別 | 張數 | 代表寫法 |
|---|---|---|
| 無強化要求 | 54 | `待指派（建議 L2；≠ 執行）` |
| 含「跨家族」＋「人工」 | 44 | `待指派（跨模型家族或人工，且 ≠ 執行）` |
| 只含「跨家族」 | 17 | `Antigravity（Gemini 3.6 Flash，跨家族，≠ 執行，APPROVE）` |

## Q1：值域夠不夠？

**候選 enum（`context`／`cross_family_or_human`／`human`／`cross_family_and_human`）在字面上涵蓋得了現況，但那是因為現況本身沒把真正的複雜度寫進欄位。** 兩個實測發現：

**發現 1：44 張「跨家族＋人工」全部是 OR 寫法，零 AND、零順序。** 逐張檢視結果一致（`跨模型家族或人工`／`跨家族或人工`），無一張在欄位裡表達「兩者皆須」或「先 A 後 B」。若只看欄位，值域甚至只需要三個值——`human` 與 `cross_family_and_human` 在 115 張裡各出現 **0 次**。

**發現 2：多關卡要求確實存在，但寫在正文而不是欄位。** 另掃出 **5 張**卡的正文含「先本地人工審再交跨家族查核」這類順序要求，而其欄位是普通寫法：`UX-ENTITY-LINKS1`、`UX-ENTITY-LINKS2`、`TEAM-STYLE1`、`DEV-REVIEW-PROMPT-GATE1`、本卡。**其中 `UX-ENTITY-LINKS2` 與 `UX-ENTITY-LINKS3` 這個月實際各跑了兩關**（需求方本地人工審 → 跨家族終局查核），是已發生的流程而非假想。

→ **結論**：只在欄位上做 enum，抓不到本專案實際在跑的兩關卡流程。**順序必須納入值域，或明確宣告不納入並指定它改寫在哪裡**（例如另一個 `review_gates` 陣列欄位，或維持正文但在欄位標記 `multi_gate`）。**不得默默把它留在正文——那正是本卡要離開的「規則寫在自由文字裡」。**

## Q2：既有卡怎麼辦？

**建議只要求新卡，活卡按需回填，封存卡一律不動。** 理由：

- 封存 84 張的欄位**多數已被覆寫成「實際查核者＋結論」**（見 Q3），回填等於改寫歷史紀錄。
- 活卡 35 張中，34 張有欄位、寫法高度一致（OR 形式或 plain），機械回填成本低但**收益只在未來會被產生提示詞的那幾張**。
- 缺欄的 4 張有 3 張是 Initiative 卡——Initiative 不會被派查核，**應在範本層宣告 Initiative 卡不需此欄**，而不是硬填一個值。

**缺欄位時工具的行為（卡面紅線 2）**：明示「未找到，這不代表沒有額外要求」＋以卡面原文為準，**不得回退成「所以只要新 context 就好」**。`DEV-REVIEW-PROMPT-GUARD1` iteration 3 已實作此行為，本卡沿用即可。

## Q3：欄位與自由文字衝突時以誰為準？

**這一問的前提在掃描中被推翻了：〈查核〉欄目前身兼兩用，不是一個「要求」欄位。**

- 待指派時它記**要求**：`待指派（跨模型家族或人工，且 ≠ 執行）`。
- 查核完成後它被**覆寫為實際查核者與結論**：`Antigravity（Gemini 3.6 Flash，跨家族，≠ 執行，APPROVE）`、`Gemini 3.6 Flash@Antigravity（跨模型家族 APPROVE @ 46bdd9e，零阻塞）`、`Claude Opus 4.8（跨模型家族；iteration 2 APPROVE）`。上表「只含跨家族」的 17 張多屬此類。

**一個同時承載「要求」與「結果」的欄位，塞不進 enum。** 這是值域之外的結構問題，且它解釋了為什麼自由文字推斷會失敗——工具讀到的可能根本不是要求，而是事後的紀錄。

→ **建議**：新欄位**獨立於現有〈查核〉欄**（例如 header 另加一行 `review_independence: cross_family_or_human`），現有欄位維持自由文字、繼續兼記實際查核者。**兩者衝突時以新欄位為流程門檻、以自由文字為人可讀補充**；但這個分工必須寫進 `CONTROL_PLANE_CONTRACT.md`，否則就是再造一個「靠人記得」。

## Q4：欄位是宣告，不是保證——要不要驗證？

**建議接受它只是留痕，並且明講。**

工具能驗的是「卡面宣告了什麼」，不能驗「實際查核者是否真的跨家族」——那需要一個可信的查核者身分來源，本專案沒有（查核結論目前由需求方**人工轉錄**成 event，actor 字串是人打的，本 session 就有兩筆記為「待補正」）。

**可行的低成本強化**：`review_prompt.py` 產生提示詞時，把宣告值與**上一輪 review event 的 actor**並列印出，讓人一眼看出「宣告要跨家族、上輪是 Claude」這種矛盾。**這是輔助判讀，不是保證**——必須在文件與輸出裡都寫清楚，否則本卡就複製了它要治的病（宣稱有保證但其實沒有）。

## 需求方裁定（2026-07-29，ruan6047）

兩項均已定案，記於此並同步 `HANDOFF-003` 事件：

1. **順序納入值域。** 多關卡要求不得繼續留在正文。
2. **新欄位獨立於現有〈查核〉欄。** 現有欄位維持自由文字、繼續兼記實際查核者與結論。

### 依裁定推導的欄位形態（方向，非定案細節）

順序既然要納入，**用有序清單比用列舉每種組合的 enum 名穩**——`cross_family_and_human` 這種合成名一旦要表達順序就會爆炸（`human_then_cross_family`、`cross_family_then_human`…）。建議：

```
review_independence: [human, cross_family]     # 先人工審，再跨家族（LINKS2／LINKS3 實際流程）
review_independence: [cross_family_or_human]   # 單一關卡，二擇一（現況 44 張）
review_independence: [context]                 # 單一關卡，新 session 即可（現況 54 張）
```

- **單一元素＝單一關卡**，清單長度即關卡數，順序即先後。
- 值本身仍是原候選集（`context`／`cross_family_or_human`／`human`／`cross_family`），**不再需要 `cross_family_and_human`**——兩者皆須就是兩個元素。
- 「兩者皆須但不限順序」若確實存在，第二段須決定是否需要額外表達；**本次掃描 115 張裡 0 次**，建議先不支援並在契約明寫不支援。

**上述為 Discovery 的推導，值域最終形態由第二段實作定案並經查核**；此處只確保裁定不被實作階段悄悄改掉。

## 給執行第二段（改碼）的前置條件

1. `DEV-REVIEW-PROMPT-GUARD1` 合併（同檔互斥解除）。**這是唯一剩餘的阻塞。**
2. ~~需求方對 Q1 順序與 Q3 欄位歸屬的裁定~~ → **已於 2026-07-29 定案（見上）。**

## 待驗證假設（未在本次 Discovery 內證實）

- 「活卡回填成本低」基於欄位寫法一致的觀察，**未實際試填**。
- 「Initiative 卡不需此欄」基於三張缺欄卡皆為 Initiative 的觀察，**未查證是否有 Initiative 曾被派查核**。
