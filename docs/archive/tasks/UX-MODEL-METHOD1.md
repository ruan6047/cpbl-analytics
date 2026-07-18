# UX-MODEL-METHOD1 模型方法與限制頁〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/fable-5/UX-MODEL-METHOD1`（已合併、已清理）
- 執行：Fable-5@Claude Code　查核：GPT-5@Codex（二輪：首輪兩 P1／二輪一 P2，均同分支修正後通過）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：`0658299`（reviewed `eba3c3d`，pull --rebase 壓平樹一致）
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.14、§6、§7
- Discovery：舊 `/predict` 混合產品互動與模型教育　Design：需求方核可 `/methodology` 不佔主要導覽、由模型 badge deep-link

## 目標與驗收

- [x] `/methodology` 依賽前勝率、WP、PA 結果分布、matchup credibility、推定球種分段，逐項列問題、期間、baseline、validation、限制與版本。
- [x] 所有已上線模型 badge 可 deep-link 至穩定 anchor；「模型敏感度區間」與非信賴區間紅線一致。
- [x] no-go、研究保留與尚未通過 gate 的模型不產生公開能力暗示，頁面在模型 artifact 缺席時仍可讀。

## 驗證與依賴

- 驗證：內容事實查核、anchor／鍵盤／mobile 走查、`tsc`、`build:check`。
- 依賴：只引用已核可模型報告；不等待未來 Stuff+／projection。
- 預估範圍：M。

## Log

- 07-18 claim（CLAIM-002）：Coordinator ruan6047 批次開工，worktree 自 main@4bad8b1 分出，dev port 3011／4011。
- 07-18 執行（Fable-5@Claude Code）：內容集中 `web/src/lib/methodology-content.ts`（六欄，事實取自 ML-SIM1／ML-MATCHUP1／ML-PT2／sabr／GAME-RECAP spec 並經生產 backtest 端點覆核）＋`app/methodology/page.tsx`（anchor 沿 `methodology-anchors.ts` 契約、賽前段抓 `/outcome/pregame/backtest`＋`/outcome/backtest` 即時對照、artifact 缺席退回報告快照仍可讀）＋`api.ts` 型別＋契約測試。ruff／pytest 283／npm test 40／tsc／build:check 綠，本機走查 anchor／鍵盤／375px／深色／斷線 fallback。轉 🔍待查核（HANDOFF-003）。
- 07-18 查核 GPT-5@Codex 首輪 REQUEST CHANGES 兩項 P1：(1) 分支與已合併 `dailySummary` 在 `api.ts` 衝突須 rebase 保留兩者；(2) 跨頁「天敵」紅線，須改「對戰劣勢候選」並擴禁詞測試。
- 07-18 二輪修正（Fable-5，同分支）：rebase 到 main 解衝突（dailySummary＋兩 backtest 端點並存）＋文案改「對戰劣勢／優勢候選」＋禁詞測試掃全文；整合分支 aca523c 重驗 ruff／pytest 283／npm test 64／tsc／build:check 綠，補實機 anchor／鍵盤／375px／無 console error 走查。轉 🔍待查核（HANDOFF-004）。
- 07-18 查核二輪 PASS，留一項 P2：fix commit 誤列 UX-MATCHUP1 查核者 Gemini 的 `Reviewed-by` trailer。amend 移除（aca523c→eba3c3d，僅 message 變更、程式碼 diff 為空）。轉 🔍待查核（HANDOFF-005）。
- 07-18 查核通過、需求方指示執行後續流程 → 代行合併（MERGE-006）：merge --no-ff reviewed eba3c3d，pull --rebase 壓平為整合 SHA `0658299`（樹等同 reviewed）。main ruff／pytest 309／npm test 64／tsc／build:check 綠。
- 07-18 部署（RELEASE-007）：cpbl-analytics CI run 29641664506 綠；主站 submodule bump 2e3053c→5164805（PersonalWebsite commit 50c986a）、CI 29641956395 綠、Deploy 29642037898 成功。production 驗證：`/api/info` 200 status=running；`/methodology` 200，ISR revalidate 後線上回測表（pregame gate／benchmark 對照）渲染、文案「對戰劣勢／優勢候選」、無「天敵」、模型敏感度區間／站上沒有的模型皆在。worktree／分支／lease 清理完成。
