# OPS-PROCESS-GUARD1 流程守門機械化（review_prompt＋CI 前端測試） 〔T2；⚪一般〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code　分支：依認領時 worktree 慣例
- 執行：待指派（建議 MODEL_ROUTING L2；已知根因的腳本／CI 修正）　查核：待指派（獨立輕量查核；須 ≠ 執行）
- Initiative：—　spec 基線：—
- DB：`none`
- 部署：否（CI 與本機腳本層）　環境：—　PR：—　Merge SHA：—
- 範圍（2026-07-26 流程審視實測產出）：
  1. `scripts/review_prompt.py`：章節 matcher 由 `startswith("驗收條件","驗證")` 放寬為標題含「驗收」「驗證」「Gate」；抓不到任何章節時輸出 stderr 警告，不得靜默退化為「依卡片全文驗收」。實測 21/33 卡命中 fallback 且無告警（含 OPS-REMOTE-* 整條車道與 GAME-RECAP-PA1-* 系列）。
  2. 卡片章節 lint：以 pytest 測試落地（比照 `tests/test_workflow_ledger.py`）——新 lifecycle event 後的活卡須含 review_prompt 可錨定的驗收章節；存量卡沿 `TEMPLATES.md` 慣例不回填、僅新事件後生效。
  3. `.github/workflows/ci.yml` web job 加 `npm test`（實測 165 契約測試／0.3s，現況 CI 只跑 `tsc --noEmit`，設計系統與產品紅線契約測試改壞不擋）；`CLAUDE.md` push 前清單同步補 `cd web && npm test`。
- Discovery：—（T2，根因已知）
- Design：Design Gate N/A；純工具／CI 層

## 驗收條件

- [ ] review_prompt 對現存 33 卡：產出非 fallback 章節或 stderr 警告，二者必居其一；新增測試覆蓋標題五種變體（驗收條件／目標與驗收／驗收／驗收與回滾／Gate 與驗證）。
- [ ] 章節 lint 以 pytest 形式進 CI，紅會擋 merge；生效範圍明確界定為「新 lifecycle event 後的卡」。
- [ ] CI web job 跑 `npm test`；在分支上以一次故意弄紅驗證會擋（驗證後還原）。
- [ ] `CLAUDE.md` 驗證清單含 web 測試。

## 驗證

- [ ] `uv run ruff check`＋`uv run pytest`＋`cd web && npm test` 全綠；附 CI run 連結。
- [ ] 以一張標題漂移的存量卡（如 `INGEST-GAME-TM-REFACTOR1`，僅有「Gate 與驗證」）實測 matcher 與警告路徑。

## Log

- 2026-07-26T16:15:00+08:00 register by Claude Fable 5@Claude Code（依 ruan6047 指示開卡；源自流程審視會話實測證據）。
