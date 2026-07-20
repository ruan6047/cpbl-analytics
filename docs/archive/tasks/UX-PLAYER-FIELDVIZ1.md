# UX-PLAYER-FIELDVIZ1 球員守備呈現（身分圖＋價值卡）〔T3；⚪一般〕

> **GATE-002 開工閘門已完成**（2026-07-20）：需求方 ruan6047 已就方案、機會數校正與
> 揭露文案位置完成討論並裁決「可以開工」。Design Brief v2 已核可。

- 需求：ruan6047　規劃：Claude（Opus 4.8）　分支：`ai/<執行者>/UX-PLAYER-FIELDVIZ1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋UX-PLAYER-IA1
- DB：`db_scope: read`（唯讀查詢 `fielding_innings`；不新增表、不寫入）　部署：是　環境：production
- 範圍：[`UX-PLAYER-FIELDVIZ1-BRIEF.md`](../design/UX-PLAYER-FIELDVIZ1-BRIEF.md) v2
- Discovery／Design：[`UX-PLAYER-FIELDVIZ1_RESEARCH.md`](../research/UX-PLAYER-FIELDVIZ1_RESEARCH.md)

## 目標與驗收

- [ ] **元件 C 守位身分圖**：球場示意圖標注守過的守位與局數（2018+）／出賽數（更早），多守位分別標注並加「多守位」標記；**不以顏色編碼好壞**。
- [ ] **元件 A 守備價值卡**：依守位群分流——外野 A/9、內野 DP/9・TC/9・守備率、一壘只列計數不做價值宣稱、捕手 CS%＋RA/9、投手不做。
- [ ] **機會數校正**：率值一律以守備局數為分母；2018 前不出現率值；未達 100 局不給聯盟對照並標示樣本不足；每個率旁附局數。
- [ ] **揭露**：外野助殺阻嚇悖論置於指標旁 inline；其餘脈絡收頁尾資料說明。
- [ ] 二軍（`kind_code='D'`）不得進入任一元件。

## 驗證與依賴

- 驗證：純函式測試（局數換算、門檻判定、守位分流、空態）、四情境瀏覽器走查（多守位／純投手／退役／無守備）、375px、`tsc`、`build:check`、`ruff`、`pytest`（新端點同步加 route 快照 EXPECTED）。
- 依賴：UX-PLAYER-SECTIONS1（已 🏁完成，資源互斥解除）。
- 預估範圍：**M**（v1 誤判為 S／純前端；實需擴充 `/fielding` 端點回傳局數與聯盟對照，見 Brief §4）。
- 非目標：球員級分區熱區圖（研究文件 §4 已否決）、逐年守位變遷（需 API `scope=yearly`，另卡）、分項明細圖表化（另卡）。
