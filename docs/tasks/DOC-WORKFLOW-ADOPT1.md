# DOC-WORKFLOW-ADOPT1 採用 WF-17 canonical 流程強化 〔T1；⚪B2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code　分支：依認領時 worktree 慣例（文件小改可直接 commit，B2 校讀不可省）
- 執行：待指派（建議 MODEL_ROUTING L1；文件同步搬移）　查核：待指派（B2 校讀；須 ≠ 執行）
- Initiative：—　spec 基線：ai-workflow WF-17（[PR #3](https://github.com/ruan6047/ai-workflow/pull/3)）
- DB：`none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 依賴：**WF-17 merge 後才可執行**（canonical 規則本體屬紅線，須跨家族或需求方 sign-off，執行者不得自 merge）。
- 範圍：WF-17 merge 後——
  1. bump `.ai-workflow` submodule 至含 WF-17 的 main。
  2. `docs/TEMPLATES.md` 補 `baseline-cascade.md`／`statistical-redline.md` 索引。
  3. `docs/MODEL_ROUTING.md`（專案版）補「路由決定於規劃期」節：開卡／Plan Gate 必填建議執行／查核層級＋理由（引用 L1–L4 層級不引用模型名）；claim 偏離留痕於 event evidence。
  4. `docs/CONTROL_PLANE_CONTRACT.md`「交付→查核→合併慣例」補查核防線：查核者核對子卡 `spec 基線` 版本＝父卡當前版本；`review_prompt.py` 自動帶入父卡基線版本（腳本改動若與 OPS-PROCESS-GUARD1 撞檔，依 lane 順序或併卡處理，`file:scripts/review_prompt.py` 資源宣告互斥）。
  5. 新卡自此採標準「驗收條件」「驗證」章節與路由建議行；存量卡沿慣例不回填。
- Discovery：—　Design：Design Gate N/A；純文件同步

## 驗收條件

- [ ] submodule 指標含 WF-17 merge SHA；stub 文件無 canonical 全文複製（只引用）。
- [ ] 專案 MODEL_ROUTING／CONTROL_PLANE_CONTRACT 增補與 canonical 條文一致、不轉述數字門檻。
- [ ] 與 OPS-PROCESS-GUARD1 的 `review_prompt.py` 改動無互相覆蓋（資源宣告或併卡留痕）。

## 驗證

- [ ] B2 校讀：查核者對照 WF-17 merge 後 canonical 原文逐項核對。

## Log

- 2026-07-26T16:15:00+08:00 register by Claude Fable 5@Claude Code（依 ruan6047 指示開卡；阻塞於 WF-17 merge）。
