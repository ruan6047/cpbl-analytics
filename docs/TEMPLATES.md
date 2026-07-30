# 協作文件範本索引

專案不複製 canonical 範本，以免與 `.ai-workflow` 演進分叉；新卡直接以 submodule 的下列範本建立，實例與 event 仍留在本專案 `docs/`。

- 一般任務卡：[`../.ai-workflow/templates/tasks-card.md`](../.ai-workflow/templates/tasks-card.md)
- 快線／慢線 bug 卡：[`../.ai-workflow/templates/bug-card.md`](../.ai-workflow/templates/bug-card.md)
- T3/T4 Discovery：[`discovery-brief.md`](../.ai-workflow/templates/discovery-brief.md)
- 使用者可見 T3/T4 的 Design：[`design-brief.md`](../.ai-workflow/templates/design-brief.md)
- 不確定性研究：[`research-plan.md`](../.ai-workflow/templates/research-plan.md)
- 大型 Initiative：[`initiative-card.md`](../.ai-workflow/templates/initiative-card.md)
- 基線變更 cascade（系列卡上游設計變更的下游傳播）：[`baseline-cascade.md`](../.ai-workflow/templates/baseline-cascade.md)
- 統計紅線區塊（T4 統計／ML／資料正確性卡必填）：[`statistical-redline.md`](../.ai-workflow/templates/statistical-redline.md)

純技術 T3/T4 必在卡片記錄 Design Gate `N/A` 的理由；既有卡不回填此格式，僅在新的 lifecycle event 後採用。

自 WF-17（2026-07-26）起，新卡採 canonical tasks-card 的**標準章節**「驗收條件」「驗證」（查核提示詞產生器與章節 lint 以此錨定，禁改寫為「目標與驗收」等變體），並在「執行／查核」行標注**路由建議**（引用 [`MODEL_ROUTING.md`](MODEL_ROUTING.md) 的 L1–L4 層級與理由，不引用模型名）；存量卡沿慣例不回填。

## 卡面 `review_independence`（查核獨立性要求）

本專案自 `DEV-REVIEW-INDEP-FIELD1`（2026-07-30）起，把「這張卡需要哪一種查核獨立性」從〈查核〉欄的中文自由文字**移出**，改成卡面 header 的機器可讀欄位。理由是路線問題而非實作品質：從中文自由文字反推流程門檻，連續三輪被否定句、引文、條件句與詞邊界打穿（`DEV-REVIEW-PROMPT-GUARD1`）。工具現在**只讀欄位，不讀語意**。

**寫法**：卡面 header（第一個 `## ` 標題之前）**獨立一行**，欄名 ASCII、值為有序清單。

```
- review_independence: [context]                 # 單一關卡：新 session 即可
- review_independence: [cross_family_or_human]   # 單一關卡：跨家族或人工，二擇一
- review_independence: [human, cross_family]     # 兩關：先需求方人工審，再跨家族查核
```

**值域**四個，語意如下——`context` 新 context／session 即可，不得為執行者本人；`cross_family` 跨模型家族的查核者，非執行者所屬家族；`cross_family_or_human` 跨模型家族或需求方人工，二擇一；`human` 需求方人工審，不得由 AI 代理。

**清單語意**：單一元素＝單一關卡；清單長度＝關卡數；**順序即關卡先後**。「兩者皆須」寫成兩個元素（`[cross_family, human]`），不要自造 `cross_family_and_human` 這種合成值。**「兩者皆須但不限順序」不支援**——掃描 119 張卡出現 0 次，需要時另行提案，不得私下用寫法暗示。

**填寫規則**：新卡**必填**；**Initiative 卡豁免**（不會被派查核，全庫 860 筆事件中 `INIT-*` 的 review 事件為 0 筆）；**封存卡一律不動**（其〈查核〉欄多已被覆寫成實際查核者與結論，回填等於改寫歷史紀錄）。

**活卡按需回填程序**（Q2 定案，本次不做批次回填）：某張活卡**將被產生查核提示詞時**才補這一行，且由**需求方逐張裁定**值，執行者不得代為推定。卡面語意不明時（例：`UX-TEAM-STYLE1` 的〈查核〉欄只寫一般查核，驗證段卻要求先人工審，兩者矛盾）標為**待需求方裁定並暫不填**——**嚴禁為了讓工具有東西可讀而猜值**。〈Design〉欄宣告的人工 Design Gate 是否也納入這個清單，屬另一張卡的範圍，本欄目前只表達〈查核〉方向的關卡。

**與〈查核〉欄的關係**：〈查核〉欄維持自由文字、繼續兼記實際查核者與結論，**永遠原文照登進提示詞**；欄位存在時它退為人可讀補充，機器可讀的要求以欄位為準。**欄位缺席不是「沒有額外要求」**——工具會明示缺欄並以卡面原文為準，不放寬。欄位寫壞（非清單／空清單／元素不在值域／同一張卡多行）一律 fail loud 拒絕產生提示詞，不當成缺席。

**這是留痕，不是保證**：欄位只記錄需求方宣告的要求，工具無法驗證實際查核者是否真的跨家族或真的是人。與 event log 的職權劃分見 [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)〈Event、claim 與 WIP〉。
