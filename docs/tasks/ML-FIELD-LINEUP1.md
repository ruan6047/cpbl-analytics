# ML-FIELD-LINEUP1 逐局守備陣容重建可行性與 canonical contract〔T4；🔴統計／資料正確性紅線〕

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/ML-FIELD-LINEUP1`
- 執行：待指派　查核：待指派（跨模型家族或人工，須 ≠ 執行）
- Initiative：`INIT-OFFICIAL-DATA1`　spec 基線：[`../research/OFFICIAL_DATA_GAP1_RESULTS.md`](../research/OFFICIAL_DATA_GAP1_RESULTS.md) §4、[`../research/ML_FIELD_TZ1_FEASIBILITY.md`](../research/ML_FIELD_TZ1_FEASIBILITY.md)
- DB：`db_scope: read`（本卡只研究／定契約；實作若需 schema／回填另開 expand＋migrate 卡）
- 部署：否　環境：—　PR：—　Merge SHA：—
- Discovery：需求方 2026-07-22 指示依新落點資料補齊前置卡
- Design：N/A——純技術研究，不產出使用者可見排名

## 研究問題

- 能否由先發守位訊號、`defend_station_code`、更換守備／更換選手事件，重建每半局九個守位？
- 換防、代打後守備、多人連續替換、捕手／投手異動、延長賽的狀態機是否唯一？
- 哪些事件只能回 `unknown`，不可用下一個接殺結果倒推守備者以免 outcome leakage？
- 與 box／球季守備局數的 team/game/player 守恆誤差是多少？coverage 是否足以支援 OAA feasibility？
- canonical key、revision、重建版本與 source change invalidation 應如何定義？

## 交付與 Go／No-Go

- 交付研究報告、狀態機 contract、至少 30 場人工抽樣與全季 coverage／守恆 SQL。
- 若不能在不看擊球結果的條件下唯一重建外野守備者，OAA 路線 NO-GO 或只限可證實 innings。
- 通過後另開 additive schema 與 materialization data-migration 子卡；不得在本卡偷渡寫入。

## Log

- 2026-07-22 register by GPT-5@Codex（依 ruan6047 指示）；補齊既有 `ML-FIELD-OAA-VAL1` 引用但不存在的正式前置卡。
