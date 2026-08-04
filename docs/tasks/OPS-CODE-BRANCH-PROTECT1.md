# OPS-CODE-BRANCH-PROTECT1 程式碼 main 的 branch protection 與 required checks〔T3；🟡流程〕

- 需求：ruan6047（2026-08-04 批准「重切窄卡進 Backlog」——PR-GUARD1 封存後的遺產範圍）　規劃：Claude Fable 5@Claude Code（PM 祕書）
- 執行：待指派（建議 L2；GitHub remote rules 已知模式）　查核：待指派（新 context；≠ 執行）
- Initiative：WF-22　spec 基線：決議 v1　review_independence: [context]
- 服務的原始目標：main 的機械防線——單人＋AI 艦隊模型下，誤推不得直達生產源頭
- DB：`db_scope: none`　分支：`ai/<執行者>/OPS-CODE-BRANCH-PROTECT1`
- 資源：`.github/workflows/ci.yml`（如需）、GitHub `main` remote rules
- 硬依賴：`DEV-TRAILER-GUARD-PR-CHECKOUT1` merge（api job 於 PR checkout 必須可綠，否則 required 即無差別鎖死——PR-GUARD1 Discovery 已證）

## 核心痛點（三問）

- **痛點**：cutover 後 control-plane 離開 git，main 只剩程式碼與文件，但仍無任何機械守衛——直推、紅 CI merge 都不會被擋。
- **成功怎麼觀察**：以行為證據驗收——direct push main 被拒；api＋web required checks 綠才可 merge；祕書快照與 B1 記錄文件的落 main 路徑有明確且可運作的設計（不因保護而癱瘓）。
- **最大未驗證前提**：branch protection／repository ruleset 對單人 repo 的能力面——PR-GUARD1 時期實測 protection API 404，UI／ruleset 路徑未驗；祕書每日 snapshot commit 與保護的相容設計（bypass actor、auto-merge PR、或 snapshot 改走 PR）未定。

## 範圍與紅線

1. 只管程式碼面：control-plane 已不在 git，不重演 PR-GUARD1 的 lifecycle 契約改造。
2. 交付以**行為證據**驗收（拒絕紀錄、成功 merge 紀錄），不接受設定截圖。
3. 不建立常設 bypass；緊急 bypass 須需求方明示並留痕。
4. snapshot／B1 路徑設計是本卡一級交付物，不得「先鎖再說」把日常流程鎖死。

## 驗收

- [ ] direct push main 被拒的實際輸出。
- [ ] 含紅 required check 的 PR 無法 merge、綠色後可 merge 的實際案例各一。
- [ ] snapshot／B1 落 main 路徑設計文件化並實跑一次。

## Log

- 2026-08-04 register by Claude Fable 5@Claude Code（PM 祕書，依需求方批准重切）；📥Backlog。前身 `OPS-CONTROL-PLANE-PR-GUARD1` 已封存，其 Discovery（CI 基線、check 名稱）可沿用。
