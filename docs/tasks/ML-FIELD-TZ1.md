# ML-FIELD-TZ1 Total Zone 型守備指標可行性研究〔T4；🔴紅線〕

> **本卡只做研究與可行性判定，不實作指標。** 是否進入實作屬另卡，需研究結論支持並經需求方核可。
> T4 依據：統計／ML 屬 canonical AI_WORKFLOW §5 紅線，紅線一律 T4。

- 需求：ruan6047　規劃：Claude（Opus 4.8）　分支：`ai/<執行者>/ML-FIELD-TZ1`
- 執行：待指派　查核：待指派（須 ≠ 執行，且須跨模型家族）
- Initiative：—　spec 基線：[`FIELDING_METRIC_DIRECTION.md`](../research/FIELDING_METRIC_DIRECTION.md)
- DB：`db_scope: read`　部署：否　環境：—

## 背景

現行能力卡守備軸 `RF = (PO+A)/G` 衡量「經手多少球」而非守備價值；改分母只修正時間基準，
不改變衡量對象（見 [`UX-ABILITY-FIELD1_PHASE1.md`](../research/UX-ABILITY-FIELD1_PHASE1.md)，
該卡 Phase 2 已依需求方裁決不執行）。

國外對「無座標資料」的處境有成熟解法：[Total Zone](https://www.baseball-reference.com/about/total_zone.shtml)
只需逐打席的「誰處理的」，估算超越期望的出局數。我們的 `game_livelog` 2018–2026 有約
**13.6 萬筆**可抽出守位的事件（逐球追蹤僅 5,998 筆），且可跨季累積以滿足
[UZR 文件](https://library.fangraphs.com/defense/uzr/)明訂的「三年才可下結論」門檻。

## 研究問題（本卡要回答的）

- [ ] **文字解析涵蓋率**：`game_livelog.content` 能穩定抽出「處理者守位＋球種類型（內野滾地／外野高飛／平飛…）」的比例多少？無法解析的殘餘屬哪類事件、是否有系統性偏誤？
- [ ] **期望值模型怎麼建**：以什麼為條件（球種類型×打者左右×投手左右×壘上狀況？）估算「同類球被該守位處理掉的機率」？CPBL 樣本能支撐多細的分層？
- [ ] **跨季累積與年代校正**：2018–2026 的守備環境是否可比？是否需比照 RE 矩陣的年代校正作法？
- [ ] **驗證方案**：無外部 ground truth 的情況下如何自我驗證？（候選：出局守恆恆等式、與官方守備率／RF 的相關性合理性、金手套獎作為弱訊號對照）
- [ ] **規模與風險評估**：若實作，工程量與「期望值模型建錯會產生看似精確實則錯誤的數字」的風險如何控制？

## 非目標

- 不實作指標、不改動能力卡、不寫入 DB。
- 不重啟 OAA／分區熱區法（[`UX-PLAYER-FIELDVIZ1_RESEARCH.md`](../research/UX-PLAYER-FIELDVIZ1_RESEARCH.md) §4 已以樣本量否決）。

## 驗證與依賴

- 驗證：所有數字須附取數 SQL；宣稱涵蓋率須以實查為據，不得估計。
- 依賴：無。
- 預估範圍：M（純研究）。
