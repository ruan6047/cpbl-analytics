# DOC-WORKFLOW-ADOPT2 採用 WF-18 canonical 流程強化＋F-01 歷史補帳 〔T1；⚪B2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code　分支：依認領時 worktree 慣例（文件小改可直接 commit，B2 校讀不可省）
- 執行：待指派（建議 L1；文件同步＋機械補帳）　查核：待指派（B2 校讀；須 ≠ 執行）
- Initiative：—　spec 基線：ai-workflow WF-18（merge `b9af568`，[PR #4](https://github.com/ruan6047/ai-workflow/pull/4) MERGED）
- DB：`none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 依賴：**已解除**——WF-18 已 merge（Gemini 跨家族 APPROVE＋ruan6047 sign-off）。
- 範圍：
  1. bump `.ai-workflow` submodule 至含 WF-18 的 main tip。
  2. `docs/CONTROL_PLANE_CONTRACT.md`「交付→查核→合併慣例」：「merge 者仍不得是該卡執行者」句補 §2.1 例外條款引用（APPROVE/sign-off＋需求方授權＋Reviewed-by＋事件記授權來源）；補 release 終態語意與結案清單引用（canonical §0＋worktree-lifecycle）；補 `occurred_at` 取系統時鐘一句。
  3. **F-01 歷史補帳**（Gemini WF-18 查核 informational finding）：掃描 `events.jsonl` 中最後事件非終態（非 `🏁完成`／`🛑已停止`）但卡檔已封存的卡，逐卡追加終態 status 事件（append-only 補帳，不改歷史事件）；已知名單含 UX-TOKEN-HYGIENE1、UX-NAV-INTEGRATE1、UX-ENTITY-LINKS1、UX-DESIGN-CONFORM1、UX-TEAM-SPLIT-SCOPE1、GAME-RECAP-WP-VAL1、UX-UMPIRE-SCOPE1、UX-PLAYER-IA1（🚨已升級者依其真實結局定終態，勿一律填 🏁）。
  4. `docs/AI_RUNBOOK.md` §7.1 補結案清單與終態語意引用（不複述 canonical 全文）。
- Discovery：—　Design：Design Gate N/A；純文件同步與 event 補帳

## 驗收條件

- [x] submodule 指標含 WF-18 merge SHA `b9af568`。→ bump 至 `5b23262`；三處增補皆引用連結
- [x] CONTROL_PLANE_CONTRACT 例外條款引用與 canonical §2.1 語意一致（三前提＋雙留痕＋「授權只豁免誰按下 merge」原句保留）。
- [x] 全庫掃描：所有已封存卡最後事件**已皆為終態**——F-01 名單的卡片均有後續終態事件或仍為合法活卡，實際補帳需求＝零（零追加，符合不改歷史原則；掃描指令留 handoff evidence 供重跑）。
- [x] `workflow_ledger.py --check` 通過；Ledger 無殭屍卡；pytest 三套 guard 18 passed。

## 驗證

- [ ] B2 校讀：查核者抽 2 條契約增補對照 canonical 原文、抽 3 筆補帳事件對照 archive 索引列。

## Log

- 2026-07-26T19:16:00+08:00 register by Claude Fable 5@Claude Code（依 WF-18 依賴註記開卡；WF-18 已 merge b9af568，開卡即可認領）。
- 2026-07-26 claim＋執行（需求方派工）；handoff → 🔍待查核；SHA 9fbe64d；F-01 實測零缺口，詳 handoff event。
