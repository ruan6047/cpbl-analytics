# OPS-REVIEW-BASELINE1 查核提示詞帶入父卡 spec 基線版本 〔T2；⚪一般〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code　分支：依認領時 worktree 慣例
- 執行：Claude Fable 5@Claude Code　查核：Gemini 3.6 Flash (High)@Antigravity
- Initiative：—　spec 基線：canonical `templates/baseline-cascade.md` §5（WF-17）
- DB：`none`
- 部署：否　環境：—　PR：—　Merge SHA：`6089a653f6a5e97960f1af0169ca15c09d5f05c0`
- 範圍：DOC-WORKFLOW-ADOPT1 遞延的工具層 follow-up（當時 `file:scripts/review_prompt.py` 被 OPS-PROCESS-GUARD1 佔用，該卡已 🏁 結案、lane 已空）——
  1. `scripts/review_prompt.py`：卡片有 Initiative 父卡時，自動讀取父卡的 `spec 基線` 欄與本卡卡面的 `spec 基線` 欄，帶入提示詞並生成「版本一致性核對」查核項（不一致＝退回事由，見 `CONTROL_PLANE_CONTRACT.md` 基線版本查核防線）。
  2. 父卡或子卡無基線欄（存量卡）時明確標示「基線欄缺席，人工核對」，不得靜默省略該查核項。
  3. 測試比照 `tests/test_review_prompt.py`：覆蓋「有父卡且版本一致／不一致」「無父卡」「基線欄缺席」四情境。
- Discovery：—（T2，根因已知）
- Design：Design Gate N/A；純工具層

## 驗收條件

- [x] 有 Initiative 的卡產出的提示詞含父卡當前基線版本與核對指示；版本欄缺席時有明確人工核對提示。
- [x] 無 Initiative 的卡行為不變（不多出雜訊段落）。
- [x] 四情境測試全綠；對既有卡（如 GAME-RECAP-WP-CAL1，父卡 INIT-GAME-RECAP spec 基線 v1.3）實測輸出正確版本。

## 驗證

- [x] `uv run ruff check`＋`uv run pytest` 全綠；附實測提示詞輸出片段。

## Log

- 2026-07-26T17:05:00+08:00 register by Claude Fable 5@Claude Code（依 ruan6047 指示開卡；DOC-WORKFLOW-ADOPT1 handoff evidence 預告的 follow-up）。
- 2026-07-26T18:06:00+08:00 claim by Claude Fable 5@Claude Code.
- 2026-07-26T18:25:00+08:00 handoff by Claude Fable 5@Claude Code (3116d1e).
- 2026-07-26T18:45:00+08:00 review by Gemini 3.6 Flash (High)@Antigravity: APPROVE.
- 2026-07-26T18:46:00+08:00 merge by Gemini 3.6 Flash (High)@Antigravity (6089a65).
