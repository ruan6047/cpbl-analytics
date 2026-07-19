# DOC-GAME-RECAP1 賽事復盤產品規格獨立查核〔T3；⚪B2 權威文件〕

- 需求：ruan6047　規劃／撰寫：GPT-5@Codex　分支：B2 文件卡，依 Coordinator 決定是否直接提交
- 執行（獨立查核）：Claude（Opus 4.8，跨模型家族，≠ 原撰寫者 GPT-5@Codex）　複查／核可：需求方 ruan6047
- Initiative：INIT-GAME-RECAP　spec 基線：v1.2
- DB：`db_scope: none`；僅可唯讀核實既有 schema／API／前端
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：[`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md)、[`GAME_RECAP_DESIGN_BRIEF.md`](../design/GAME_RECAP_DESIGN_BRIEF.md)、[`INIT-GAME-RECAP.md`](INIT-GAME-RECAP.md) 與所有 `GAME-RECAP-*`／`UX-GAME-*` 子卡
- Discovery：需求方於 2026-07-16 確認非即時、隔日刷新、仍須 WP 曲線與逐打席理解
- Design：本卡即為 Design／Plan 權威文件查核；Design Gate 維持待需求方核可
- current-state：🏁完成；獨立查核（Claude Opus）verdict request-changes（F1–F4），需求方核可並修正升 spec v1.3 後 APPROVE；查核報告 [`../research/DOC-GAME-RECAP1_REVIEW.md`](../research/DOC-GAME-RECAP1_REVIEW.md)

## 查核目標

由非原撰寫者獨立確認規格是否忠實反映使用者需求、現有程式能力與專案工作流，並找出會造成錯誤實作、重複 Roadmap、資料誤導或無法驗收的缺口。查核者不得直接修改原文件。

## 驗收條件

- [ ] 產品定位同時滿足「不宣稱即時」與「可在隔日重建比賽當下」，沒有互相矛盾的文案或狀態。
- [ ] 現況盤點已核對實際 schema、WP 模型、API、賽事頁與 ML-SIM1／UX-OUTCOME-HOME 任務，不把既有能力誤列為新建。
- [ ] WP/WPA、打席分組、逐球對應、資料新鮮度與賽制邊界的統計／資料風險均有 fail-closed 與驗證要求。
- [ ] Initiative 依賴圖、所有子卡範圍、tier、DB scope、Design Gate、獨立查核與驗證命令符合 canonical Workflow。
- [ ] 任務切片無 XL 卡、無互相重疊 owner scope，且能在每個 checkpoint 留下可工作的系統。
- [ ] 所有可及性、行動版、效能與 Solopreneur 維運條件具可測試的驗收方式。

## 查核方法

- [ ] 唯讀檢查 `migrations/016_game_log.sql`、`018_pitch_tracking.sql`、`049_win_expectancy.sql`。
- [ ] 唯讀檢查 `src/cpbl/models/winprob.py`、games router、game page、`GameBoard`、`WinProbChart` 與 overview。
- [ ] 對照 `docs/TASKS.md`、ML-SIM1、UX-OUTCOME-HOME、UX-MATCHUP1/2，確認無重複或錯誤依賴。
- [ ] 檢查所有 Markdown 相對連結、Mermaid 語法與卡片欄位。
- [ ] Review 報告逐項列 `severity｜證據｜處置建議`，並給出 `approve` 或 `request-changes`；不得以「看起來合理」代替證據。

## 交付與後續

- 查核通過：需求方可核可目前 spec 基線；Coordinator 再註冊 Initiative／子卡 lifecycle events。
- 查核退回：原撰寫者修正同一份 spec 與卡片、升版並交回同一查核者複查。
- 預估範圍：S（文件與程式事實核對，不實作功能）。

## Log

- 2026-07-16 proposed by GPT-5@Codex → 依需求方要求開立獨立文件查核卡；尚未正式 handoff、尚未指定 reviewer、尚無 review iteration 或 lifecycle event。
- 2026-07-16 author preflight by GPT-5@Codex → 交付前完成結構性自查並升至 v1.2；此紀錄不是獨立審查結果，正式結論須在需求方交付後由另一 AI 產生。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；尚未 claim 或指定 reviewer。
- 2026-07-19 claim by Claude（Opus 4.8）→ 需求方 ruan6047 明確指示「依規範執行 DOC-GAME-RECAP1」；以跨模型家族獨立查核者身分 claim，唯讀核對 spec／Design Brief／Initiative／子卡 vs 實際 migration／model／API／前端。
- 2026-07-19 review by Claude → verdict **request-changes**：技術立論（§3.3／§7／§8）逐行對到程式證據全通過；退回項為現況盤點時效性漂移（F1）與三項卡片一致性缺陷（F2–F4）。報告見 [`../research/DOC-GAME-RECAP1_REVIEW.md`](../research/DOC-GAME-RECAP1_REVIEW.md)。
- 2026-07-19 approve by ruan6047 → 需求方回覆「審核過關」並指示合併與修正；F1–F4 已修正、spec 升 v1.3、INIT／DOC 卡同步；核可 spec 基線 v1.3。
