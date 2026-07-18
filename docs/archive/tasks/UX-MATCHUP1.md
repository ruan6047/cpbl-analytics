# UX-MATCHUP1 `/matchups` 查詢式頁面重製〔T4；🔴統計／ML〕

- 需求：ruan6047　規劃：GPT-5@Codex（`matchups-redesign.md`）　分支：`ai/fable-5/UX-MATCHUP1`
- 執行：Fable-5@Claude Code（07-18）　查核：Gemini-3.5-Flash(High)@Antigravity（跨模型家族，APPROVE、P0–P2=0，`docs/UX-MATCHUP1_REVIEW.md`）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋ML-MATCHUP1
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：`948bb21`（reviewed `e81af6b`，pull --rebase 壓平 merge 節點、內容等同性已驗證）

## 驗收條件

- [x] 沒有洞察時仍可查詢樣本與基礎實績；通過閘門才顯示 baseline 差、credibility 與 coverage，禁止「天敵」確定語氣。
- [x] 覆蓋率不足、先驗無法估計、候選未過 credibility、C–E 無 baseline 四種 fail-closed 狀態各有獨立版面與文案。
- [x] 年度／career／range、隊伍／個人、coverage 與 sample_scope 不混淆；375 px、鍵盤與 deep-link 可用。

## 驗證與依賴

- 驗證：四種空狀態 fixture、角色翻轉／低樣本／C–E 契約、瀏覽器走查、T4 獨立查核、`tsc`、`build:check`。
- 依賴：MATCHUP-DATA1、ML-MATCHUP1 已結案；完成後才能 claim UX-MATCHUP2、UX-PA-SIM-MATCHUP1。
- 預估範圍：M。

## Log

- 07-15 WF-12 遷移：維持 Backlog。
- 2026-07-17 baseline v0.2 → fail-closed 改為常態版面，洞察卡不再是 hero。
- 07-18 claim（CLAIM-003）：Coordinator 批次開工指派 Fable-5@Claude Code；worktree 自 main@4bad8b1。
- 07-18 實作（e81af6b，單一邏輯 commit，範圍純 `web/src/app/matchups/**`）：api.ts 型別鏡射＋fetchers；search-combobox（ARIA/鍵盤/debounce）；matchups-client（URL 即狀態 deep-link：role/pid/scope/from/to/kind/team/opp/pick/sort/order）；opponents-table（server-side 排序、available_count 揭露截斷長尾）；pair-card（A/C/E 分段＋進階展開＋逐年彙總標示）；insight-state＋insight-section（fail-closed 四狀態獨立版面、判定全取 API 明示欄位、候選語氣、主角視角 delta 翻號、sensitivity badge）；insight-fixtures＋14 例 node:test 契約測試（含天敵禁詞、角色翻轉鏡像、判定順序、coverage/query_sample 不混淆）。
- 07-18 驗證：npm test 49、tsc、build:check、ruff、pytest 283 全綠；瀏覽器走查（3013/4013）覆蓋成功態（林泓育，數值與 ML-MATCHUP1 快照一致）、四種 fail-closed 真實案例（潘威倫 18% 覆蓋／林泓育本季先驗缺席／蔣銲 gated／kind=C）、range 誠實空狀態、隊伍篩選限縮、375px、鍵盤全流程、深色模式。轉 🔍待查核（HANDOFF-004）。
- 07-18 跨家族查核（REVIEW-005 @ b3b3993）：APPROVE、P0–P2 findings=0，報告 `docs/UX-MATCHUP1_REVIEW.md`。
- 07-18 合併（MERGE-006）：整合 SHA 948bb21（rebase 壓平如實留痕），合併後 ruff／pytest 283／npm test 59／build:check 全綠。
- 07-18 部署：主站 submodule bump 99b38a6→3595148（PersonalWebsite 2fea76d），Deploy 與 production 驗證見 RELEASE 事件。
