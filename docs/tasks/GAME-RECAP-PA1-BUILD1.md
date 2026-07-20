# GAME-RECAP-PA1-BUILD1 canonical PA builder、對帳與回填〔T4；🔴資料正確性／data migration〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/GAME-RECAP-PA1-BUILD1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：[`GAME-RECAP-PA1_CONTRACT.md`](../design/GAME-RECAP-PA1_CONTRACT.md) §「PA 狀態機與穩定 ID」至「發布門檻與紅燈測試」
- DB：`db_scope: data-migration`；`migration_phase: migrate`。認領時須取得本機／production 對應表的 data lane lock，執行前備份並定義可續跑與復原程序。
- 部署：是　環境：production　PR：—　Merge SHA：—
- Discovery：`GAME-RECAP-DATA1` Checkpoint 1 已核可
- Design：Design Gate N/A；純資料管線，public consumer 另由後續 API／UX 卡交付
- current-state：📥Backlog；等待 TAXONOMY1、EXPAND1 通過與 production data-migration sign-off。

## 目標與驗收

- [ ] 實作每日批次 builder，依 taxonomy 將來源 revision 物化為 deterministic、持久化的 `pa_id`、event membership 與 ordered pitch mapping。
- [ ] 面對晚到或修正來源，以 reconciliation 記錄處理；無法一對一延續時 fail closed，禁止靜默 delete-and-reinsert 或變更已發布 ID。
- [ ] 完成歷史回填與可續跑的批次程序；對每年／球場／賽制輸出 box PA、candidate／ready／unreliable PA、mapped／failed pitch 與 unknown reason。
- [ ] 紅燈與整合測試涵蓋同局重複投打、換投、代打、缺球、無設備、晚到資料與相同 revision 重跑；達到需求方核可的對帳門檻才可發布 build。
- [ ] production rehearsal、備份／回復、資料 QA 與跨模型家族或人工 review 均通過；尚不新增 WP／WPA 或前端功能。

## 依賴與交付

- 依賴：`GAME-RECAP-PA1-TAXONOMY1`、`GAME-RECAP-PA1-EXPAND1` 均完成並通過獨立查核。
- 後續：僅在 published build 的對帳門檻通過後，解除 `GAME-RECAP-WP-VAL1`、`GAME-RECAP-WP-API1` 與精確逐球 UI 的資料前置。
- 非目標：不以 builder 成功取代 public API contract、WP 校準或 UX 驗收。
