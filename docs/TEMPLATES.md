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
