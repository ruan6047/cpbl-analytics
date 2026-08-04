# INGEST-SPLITS-IBB-GHOST1 零投球手勢故四的分項語意查證〔T3；🔴資料正確性（研究先行）〕

- 需求：ruan6047（2026-08-04 依 `INGEST-SPLITS-IMPORT-RESTATE1` 範圍外發現批准開卡）　規劃：Claude Fable 5@Claude Code（PM 祕書，三問經需求方批註）
- 執行：待指派（建議 L3；官方語意實查＋對帳前提重驗，未知根因）　查核：待指派（跨家族或人工；資料正確性紅線）
- Initiative：INIT-OFFICIAL-DATA1　spec 基線：v1　review_independence: [cross_family]
- 服務的原始目標：分項資料正確性（vs-投手分項不得系統性少計真打席）
- DB：`db_scope: read`（研究階段；若證實需修，第二階段另行 write 授權並更新卡面，PM 派工時明示）
- 分支：`ai/<執行者>/INGEST-SPLITS-IBB-GHOST1`　資源（研究階段）：無寫入

## 核心痛點（三問，需求方 2026-08-04 已批）

- **痛點**：`splits_calc` 幽靈島規則（濾無投球假島）把零投球的手勢故意四壞——**真打席**——整島丟棄；2025 A/D 全季 26 席、全體投手一致受影響。且與 `INGEST-SPLITS-RECALC1`「官方值 17,997 格全命中」的宣稱至少一個前提矛盾：官方若計入故四則全命中不該成立，官方若也排除則此為語意而非缺陷。
- **成功怎麼觀察**：對官方 vs-左右投分項在零投球故四上的語意得到**可證偽結論**（以官網實際數字驗證，非推導）。計入 → 修幽靈島規則＋重驗 RECALC1 對帳；排除 → 語意寫入 `docs/reference/GLOSSARY.md` 結案。
- **最大未驗證前提**：官方「末球錨定」對**無末球**打席的實際處理——零投球打席沒有末球，官方自己怎麼歸類 vs-左/右投，必須實查不能推導。

## 已知事實（來源：RESTATE1 交付 4f3c66e）

- 定位方法與 26 席清單見 `docs/research/INGEST-SPLITS-IMPORT-RESTATE1_RESULTS.md`（殘差 2 席逐席定位起點）。
- 規則譜系：9.14(d) 手勢故四零投球正是 SCORELESS 卡曾被打穿的同一條規則（見記憶 rule-premise-and-reconciliation-limits）——「列舉≠推導」教訓的分項版。
- RECALC1 對帳 artifact 是重驗前提的基準，不得以新推導取代原始 grid。

## 紅線（違反即退回）

1. **查證先於修改**：官方語意未以實查數字證實「計入」前，不得動 `src/cpbl/ingest/splits_calc.py`。
2. **官方數字實查**：結論必須引用官網分項頁面的實際數值對照（含至少一名 2025 年吃過手勢故四的打者的 vs-左/右投打席數），不得由規則文本推導。
3. RECALC1 前提重驗必須對照原始 17,997 grid artifact，完整性宣稱由指令輸出產生。

## 驗收

- [ ] 官方語意結論（計入／排除）附實查證據，可證偽。
- [ ] 分流結論落地：計入 → 第二階段修正方案與 write 授權需求提交 PM；排除 → GLOSSARY 條目 PR。
- [ ] RECALC1「全命中」前提與本結論的相容性說明（矛盾如何解消）。

## Log

- 2026-08-04 register by Claude Fable 5@Claude Code（PM 祕書，依需求方批准「開研究卡進 Backlog」）；📥Backlog。來源：RESTATE1 執行者依紅線 1 停手回報的範圍外發現。
