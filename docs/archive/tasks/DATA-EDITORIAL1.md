# DATA-EDITORIAL1 Google Sheet 編輯資料管道〔T4；🔴資料寫入／正確性〕

> **⏸ 擱置／封存（2026-07-19）**：T4 實作已跨家族查核並合併至 `main`（`1bdf5c6`），但
> production migration、Google Sheet ingest 與部署均未執行。待其他項目完成後，須重新開卡、重新
> 取得 production sign-off，才可恢復；不得直接執行本卡的操作步驟。

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/DATA-EDITORIAL1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: schema`；CARD_ID 隔離 namespace；`migration_phase: expand`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../../PRODUCT_UX_BLUEPRINT.md) §8.5、§9 Phase 7
- Discovery：應援文化、主題日與季節內容需要可維護來源　Design：Design Gate N/A；先建單向資料契約，不開 UI

## 目標與驗收

- [ ] 定義 Google Sheet → 驗證 → 冪等 ingest → PostgreSQL 契約，含來源、有效期間、更新者識別、撤回狀態與錯誤列報告；公開 API 維持唯讀。
- [ ] schema／migration 可重跑，錯誤資料 fail closed，不以 Sheet 即時直連公開頁；credentials 不進 repo、log 或輸出。
- [ ] 完成 staging fixture、資料對帳、rollback／清理與操作文件；沒有足量真實資料前不建立應援文化、主題日或橫幅 UI 卡。

## 驗證與依賴

- 驗證：migration rerun、ingest unit／integration、壞資料與撤回案例、secrets audit、T4 rehearsal 與獨立查核。
- 依賴：不阻塞 Phase 0–2；production 寫入另取 migration lane 與備份。
- 預估範圍：M；國際賽不在 scope。
