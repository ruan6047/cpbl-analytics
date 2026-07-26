# DOC-WORKFLOW-ADOPT1 採用 WF-17 canonical 流程強化 〔T1；⚪B2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code　分支：依認領時 worktree 慣例（文件小改可直接 commit，B2 校讀不可省）
- 執行：待指派（建議 MODEL_ROUTING L1；文件同步搬移）　查核：待指派（B2 校讀；須 ≠ 執行）
- Initiative：—　spec 基線：ai-workflow WF-17（[PR #3](https://github.com/ruan6047/ai-workflow/pull/3)）
- DB：`none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 依賴：**已解除**——WF-17 已 merge（ruan6047 sign-off，canonical merge SHA `e0b1c1e`，PR #3 MERGED、卡已封存）。
- 範圍：WF-17 merge 後——
  1. bump `.ai-workflow` submodule 至含 WF-17 的 main。
  2. `docs/TEMPLATES.md` 補 `baseline-cascade.md`／`statistical-redline.md` 索引。
  3. `docs/MODEL_ROUTING.md`（專案版）補「路由決定於規劃期」節：開卡／Plan Gate 必填建議執行／查核層級＋理由（引用 L1–L4 層級不引用模型名）；claim 偏離留痕於 event evidence。
  4. `docs/CONTROL_PLANE_CONTRACT.md`「交付→查核→合併慣例」補查核防線：查核者核對子卡 `spec 基線` 版本＝父卡當前版本；`review_prompt.py` 自動帶入父卡基線版本（腳本改動若與 OPS-PROCESS-GUARD1 撞檔，依 lane 順序或併卡處理，`file:scripts/review_prompt.py` 資源宣告互斥）。
  5. 新卡自此採標準「驗收條件」「驗證」章節與路由建議行；存量卡沿慣例不回填。
- Discovery：—　Design：Design Gate N/A；純文件同步

## 驗收條件

- [x] submodule 指標含 WF-17 merge SHA；stub 文件無 canonical 全文複製（只引用）。→ bump 至 `fcf4102`（含 e0b1c1e）；三份文件皆連結 canonical，未複述全文
- [x] 專案 MODEL_ROUTING／CONTROL_PLANE_CONTRACT 增補與 canonical 條文一致、不轉述數字門檻。
- [x] 與 OPS-PROCESS-GUARD1 的 `review_prompt.py` 改動無互相覆蓋（資源宣告或併卡留痕）。→ 腳本層完全未動；遞延決策留痕於 claim event 與 CONTROL_PLANE_CONTRACT 條文（follow-up 於該卡結案後）

## 驗證

- [ ] B2 校讀：查核者對照 WF-17 merge 後 canonical 原文逐項核對。

## Log

- 2026-07-26T16:15:00+08:00 register by Claude Fable 5@Claude Code（依 ruan6047 指示開卡；阻塞於 WF-17 merge）。
- 2026-07-26T16:26:00+08:00 note by Claude Fable 5@Claude Code → 依賴解除：ruan6047 sign-off 後 WF-17 merge（e0b1c1e）並封存；本卡可認領。submodule bump 目標＝canonical main `3219858`。
- 2026-07-26T16:37:00+08:00 claim by Claude Fable 5@Claude Code（需求方派工）；iteration 0；T1 B2 直接 commit（卡面授權）；資源與 OPS-PROCESS-GUARD1 零撞檔，review_prompt.py 工具層遞延。
- 2026-07-26T16:45:00+08:00 handoff by Claude Fable 5@Claude Code → 🔍待查核（B2 校讀，須 ≠ 執行）；bump 目標修正為 `fcf4102`（封存卡 Log 補齊 commit，見 canonical git log）；證據見 handoff event。
