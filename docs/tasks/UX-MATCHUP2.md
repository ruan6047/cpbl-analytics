# UX-MATCHUP2 投打對決整合球員個人頁〔T4；🔴統計／ML〕

- 需求：ruan6047　規劃：GPT-5@Codex（`matchups-redesign.md`）　分支：`ai/fable-5/UX-MATCHUP2`
- 執行：Fable-5@Claude Code（07-22）　查核：待指派（跨模型家族或人工，且 ≠ 執行；HANDOFF-004）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋UX-MATCHUP1
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：共用 UX-MATCHUP1 的基礎實績、洞察與 fail-closed 元件，整合至球員頁「分項與對戰」。

## 驗收條件

- [ ] 球員頁只整合共用元件／deep-link，不複製 EB 判斷或另造空狀態；樣本、coverage、credibility 與 baseline 同區。
- [ ] 描述性歷史洞察與未來預測清楚區分；首版不嵌入 `pa_sim`。
- [ ] 打者、投手、無年度 coverage、低樣本與 API error 在核可球員 IA 中皆能退化。

## 驗證與依賴

- 驗證：共用元件契約、球員角色 fixture、375 px／鍵盤走查、T4 獨立查核、`tsc`、`build:check`。
- 依賴：UX-MATCHUP1、UX-PLAYER-SECTIONS1；與球員頁卡序列化。
- 預估範圍：S–M。

## Log

- 07-15 WF-12 遷移：維持 Backlog。
- 2026-07-17 baseline v0.2 → 延後至球員 IA 遷移完成，首版不含 PA 模擬。
- 07-22 claim（CLAIM-003）：需求方指派 Fable-5@Claude Code 執行；依賴 UX-MATCHUP1、UX-PLAYER-SECTIONS1 均已結案。worktree 自 main@f9c5ac2（`.claude/worktrees/ux-matchup2-workspace-setup-d6660d`）。
- 07-22 handoff（HANDOFF-004）：執行完成交跨家族查核，被審 SHA 3c52ad9。範圍：抽離共用 MatchupExplorer→球員頁分項與對戰整合＋deep-link；需求方人工走查三項回饋（對手下拉只列交手隊／移除頁尾導覽／洞察 compact 收合）均已修並實測。本機 tsc／132 web tests／build:check 綠。連帶另開 MATCHUP-DATA2 修對手歷史隊別歸屬。
- 07-22 review RETURN（REVIEW-005，Codex GPT-5 跨家族，iteration 2）：P1＝compact 摘要泛化『樣本不足』破壞四態契約。修正 handoff（HANDOFF-006，被審 f310af8）：摘要改取 INSIGHT_COPY[state.kind].title 各態專屬標題、加回歸測試；tsc／133 web tests／build:check 綠，三態瀏覽器重驗一致。
